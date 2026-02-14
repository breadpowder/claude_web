"""Subprocess monitoring for resource limits and zombie cleanup (TASK-006)."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from src.core.logging_config import get_logger

logger = get_logger(__name__)

_VMRSS_RE = re.compile(r"VmRSS:\s+(\d+)\s+kB")


class SubprocessMonitor:
    """Monitors subprocess RSS, duration limits, and zombie processes."""

    def __init__(
        self,
        max_rss_mb: int = 2048,
        max_duration_seconds: int = 14400,
        on_warning: Callable[..., Coroutine[Any, Any, Any]] | None = None,
        on_terminate: Callable[..., Coroutine[Any, Any, Any]] | None = None,
        grace_period_seconds: int = 30,
    ):
        self._max_rss_mb = max_rss_mb
        self._max_duration_seconds = max_duration_seconds
        self._on_warning = on_warning
        self._on_terminate = on_terminate
        self._grace_period_seconds = grace_period_seconds
        self._sessions: dict[str, dict] = {}
        self._active_queries: set[str] = set()
        self._tasks: list[asyncio.Task] = []
        self._running = False

    def register(
        self,
        session_id: str,
        pid: int,
        started_at: datetime | None = None,
    ) -> None:
        """Track a subprocess for monitoring."""
        self._sessions[session_id] = {
            "pid": pid,
            "started_at": started_at or datetime.now(timezone.utc),
        }

    def unregister(self, session_id: str) -> None:
        """Remove a subprocess from monitoring."""
        self._sessions.pop(session_id, None)
        self._active_queries.discard(session_id)

    def is_tracked(self, session_id: str) -> bool:
        """Check if a session is being tracked."""
        return session_id in self._sessions

    def mark_query_active(self, session_id: str) -> None:
        """Mark a session as having an in-flight query."""
        self._active_queries.add(session_id)

    def mark_query_complete(self, session_id: str) -> None:
        """Mark a session query as complete."""
        self._active_queries.discard(session_id)

    async def check_rss(self) -> None:
        """Check RSS of all tracked subprocesses via /proc/<pid>/status."""
        for session_id, info in list(self._sessions.items()):
            pid = info["pid"]
            try:
                with open(f"/proc/{pid}/status", "r") as f:
                    content = f.read()
                match = _VMRSS_RE.search(content)
                if not match:
                    continue
                rss_kb = int(match.group(1))
                rss_mb = rss_kb / 1024
                if rss_mb >= self._max_rss_mb and self._on_warning:
                    await self._on_warning(
                        session_id,
                        {"reason": "memory", "rss_mb": rss_mb},
                    )
            except FileNotFoundError:
                logger.debug("Process %d not found in /proc", pid)
            except (OSError, IOError) as exc:
                logger.warning("Error reading /proc/%d/status: %s", pid, exc)

    async def check_duration(self) -> None:
        """Check session durations against limits."""
        now = datetime.now(timezone.utc)
        for session_id, info in list(self._sessions.items()):
            elapsed = (now - info["started_at"]).total_seconds()
            remaining = self._max_duration_seconds - elapsed

            if remaining <= 0:
                # Past limit
                if session_id in self._active_queries:
                    # Grace period for in-flight queries
                    if self._on_warning:
                        await self._on_warning(
                            session_id,
                            {
                                "reason": "duration",
                                "remaining_seconds": 0,
                                "grace_period": True,
                            },
                        )
                else:
                    if self._on_terminate:
                        await self._on_terminate(session_id, "duration_limit")
            elif remaining <= self._max_duration_seconds * 0.1:
                # Within 10% of limit (90%+ elapsed)
                if self._on_warning:
                    await self._on_warning(
                        session_id,
                        {"reason": "duration", "remaining_seconds": remaining},
                    )

    async def cleanup_zombies(self) -> None:
        """Detect and reap zombie child processes."""
        for session_id, info in list(self._sessions.items()):
            pid = info["pid"]
            try:
                result_pid, _ = os.waitpid(pid, os.WNOHANG)
                if result_pid != 0:
                    logger.info("Reaped zombie process %d for session %s", pid, session_id)
                    self.unregister(session_id)
            except ChildProcessError:
                # Not a child of this process, skip
                pass
            except OSError as exc:
                logger.debug("waitpid error for %d: %s", pid, exc)

    async def start(self) -> None:
        """Launch all background monitoring tasks."""
        self._running = True
        self._tasks = [
            asyncio.create_task(self._loop(self.check_rss, 30)),
            asyncio.create_task(self._loop(self.check_duration, 60)),
            asyncio.create_task(self._loop(self.cleanup_zombies, 60)),
        ]
        logger.info("SubprocessMonitor started with %d background tasks", len(self._tasks))

    async def stop(self) -> None:
        """Cancel all background monitoring tasks."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("SubprocessMonitor stopped")

    async def _loop(self, check_fn, interval_seconds: int) -> None:
        """Run a check function in a loop with sleep interval."""
        while self._running:
            try:
                await check_fn()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Monitor check failed: %s", exc)
            await asyncio.sleep(interval_seconds)
