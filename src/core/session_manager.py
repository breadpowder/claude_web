"""Central session lifecycle orchestrator (TASK-005)."""

from __future__ import annotations

import uuid
from typing import Any, AsyncGenerator, Callable, Coroutine

from src.core.exceptions import CapacityError, ConcurrentRunError, SessionNotFoundError
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class SessionManager:
    """Orchestrates session creation, query execution, and lifecycle management."""

    def __init__(
        self,
        pool,
        session_index,
        subprocess_monitor,
        client_factory: Callable[[], Coroutine[Any, Any, Any]],
        max_sessions: int = 10,
    ):
        self._pool = pool
        self._index = session_index
        self._monitor = subprocess_monitor
        self._client_factory = client_factory
        self._max_sessions = max_sessions
        self._sessions: dict[str, Any] = {}  # session_id -> client
        self._active_runs: set[str] = set()

    def active_session_count(self) -> int:
        """Return number of active sessions."""
        return len(self._sessions)

    async def create_session(self) -> dict:
        """Create a new session from pool or cold start.

        Returns session metadata dict.
        Raises CapacityError if at max capacity.
        """
        if self.active_session_count() >= self._max_sessions:
            raise CapacityError(
                f"At maximum capacity of {self._max_sessions} sessions"
            )

        session_id = str(uuid.uuid4())

        # Try pool first
        client = self._pool.get()
        if client is not None:
            source = "pre-warm"
        else:
            client = await self._client_factory()
            source = "cold"

        self._sessions[session_id] = client
        entry = self._index.create(session_id, {"source": source})

        pid = getattr(client, "pid", None)
        if pid:
            self._monitor.register(session_id, pid)

        logger.info("Session created: %s (source=%s)", session_id, source)
        return entry

    async def query(
        self, session_id: str, prompt: str
    ) -> AsyncGenerator[dict, None]:
        """Execute a query on a session. Yields stream events.

        Raises ConcurrentRunError if session already has an active run.
        Raises SessionNotFoundError if session does not exist.
        """
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        if session_id in self._active_runs:
            raise ConcurrentRunError(
                f"Query already in progress for session {session_id}"
            )

        self._active_runs.add(session_id)
        self._monitor.mark_query_active(session_id)
        try:
            client = self._sessions[session_id]
            async for event in client.query(prompt):
                yield event
        finally:
            self._active_runs.discard(session_id)
            self._monitor.mark_query_complete(session_id)

    async def interrupt(self, session_id: str) -> None:
        """Interrupt an active query on a session."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session {session_id} not found")

        client = self._sessions[session_id]
        if hasattr(client, "interrupt"):
            await client.interrupt()

    async def destroy_session(self, session_id: str) -> None:
        """Destroy a session: cleanup subprocess, update index, unregister."""
        client = self._sessions.pop(session_id, None)
        self._active_runs.discard(session_id)

        if client and hasattr(client, "close"):
            await client.close()

        self._index.update(session_id, {
            "status": "terminated",
            "terminated_reason": "destroyed",
        })
        self._monitor.unregister(session_id)

        logger.info("Session destroyed: %s", session_id)

    async def resume_session(self, old_session_id: str) -> dict:
        """Resume a terminated session by creating a new client with resume parameter.

        Returns new session metadata.
        """
        session_id = str(uuid.uuid4())

        try:
            client = await self._client_factory()
        except Exception:
            logger.warning(
                "Resume failed for %s, falling back to fresh session",
                old_session_id,
            )
            self._index.update(old_session_id, {"is_resumable": False})
            client = await self._client_factory()

        self._sessions[session_id] = client
        entry = self._index.create(session_id, {"source": "resume"})

        pid = getattr(client, "pid", None)
        if pid:
            self._monitor.register(session_id, pid)

        logger.info("Session resumed: %s -> %s", old_session_id, session_id)
        return entry

    async def acquire_session(self) -> tuple[str, Any]:
        """Acquire a session for short-lived API use.

        Returns (session_id, client) tuple.
        """
        result = await self.create_session()
        session_id = result["session_id"]
        return session_id, self._sessions[session_id]

    async def release_session(self, session_id: str) -> None:
        """Release a short-lived API session."""
        await self.destroy_session(session_id)
