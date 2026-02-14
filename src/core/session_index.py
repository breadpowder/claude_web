"""JSON-based session index with atomic file I/O (TASK-002)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from filelock import FileLock

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class JSONSessionIndex:
    """Persists session metadata in a JSON file with atomic writes and file locking."""

    def __init__(self, directory: str):
        self._dir = directory
        self._file = os.path.join(directory, "index.json")
        self._bak = self._file + ".bak"
        self._lock = FileLock(self._file + ".lock")

    def init(self) -> None:
        """Create directory and empty index.json if missing. Idempotent."""
        os.makedirs(self._dir, exist_ok=True)
        if not os.path.exists(self._file):
            self._write([])

    def create(self, session_id: str, metadata: dict) -> dict:
        """Create a new session entry. Returns the full session metadata."""
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "session_id": session_id,
            "status": "creating",
            "source": metadata.get("source", "cold"),
            "created_at": now,
            "last_active_at": now,
            "message_count": 0,
            "title": "",
            "cost_usd": 0.0,
            "terminated_reason": None,
            "subprocess_pid": None,
            "is_resumable": True,
        }
        with self._lock:
            sessions = self._read()
            sessions.append(entry)
            self._write(sessions)
        return entry

    def update(self, session_id: str, updates: dict) -> dict | None:
        """Update fields on an existing session. Returns updated entry or None."""
        with self._lock:
            sessions = self._read()
            for session in sessions:
                if session["session_id"] == session_id:
                    session.update(updates)
                    if "last_active_at" not in updates:
                        session["last_active_at"] = datetime.now(timezone.utc).isoformat()
                    self._write(sessions)
                    return session
        return None

    def get(self, session_id: str) -> dict | None:
        """Get session metadata by ID. Returns None if not found."""
        sessions = self._read()
        for session in sessions:
            if session["session_id"] == session_id:
                return session
        return None

    def list(self) -> list[dict]:
        """List all session metadata entries."""
        return self._read()

    def delete(self, session_id: str) -> bool:
        """Remove a session entry. Returns True if found and removed."""
        with self._lock:
            sessions = self._read()
            filtered = [s for s in sessions if s["session_id"] != session_id]
            if len(filtered) == len(sessions):
                return False
            self._write(filtered)
            return True

    def cleanup_old(self, days: int = 30) -> int:
        """Remove terminated sessions older than `days`. Returns count removed."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._lock:
            sessions = self._read()
            kept = []
            removed = 0
            for s in sessions:
                if s["status"] == "terminated":
                    last_active = datetime.fromisoformat(s["last_active_at"])
                    if last_active.tzinfo is None:
                        last_active = last_active.replace(tzinfo=timezone.utc)
                    if last_active < cutoff:
                        removed += 1
                        continue
                kept.append(s)
            if removed > 0:
                self._write(kept)
            return removed

    def _read(self) -> list[dict]:
        """Read sessions from index file, with backup recovery on corruption."""
        try:
            with open(self._file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Corrupt index.json detected, attempting .bak recovery")
            return self._recover_from_backup()
        except FileNotFoundError:
            return []

    def _recover_from_backup(self) -> list[dict]:
        """Attempt to recover from .bak file."""
        try:
            with open(self._bak, "r") as f:
                data = json.load(f)
            logger.info("Recovery from .bak successful")
            # Restore the main file
            self._write(data)
            return data
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            logger.error("Backup recovery failed, re-creating empty index")
            self._write([])
            return []

    def _write(self, sessions: list[dict]) -> None:
        """Atomic write: write to temp file, create backup, rename."""
        # Create backup of current file if it exists
        if os.path.exists(self._file):
            try:
                with open(self._file, "r") as f:
                    content = f.read()
                with open(self._bak, "w") as f:
                    f.write(content)
            except (OSError, IOError):
                pass

        # Atomic write via temp file + rename
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(sessions, f, indent=2)
            os.replace(tmp_path, self._file)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
