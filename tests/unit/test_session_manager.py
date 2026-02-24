"""Tests for SessionManager (TASK-005)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import CapacityError, ConcurrentRunError
from src.core.session_manager import SessionManager


@dataclass
class FakeClient:
    """Minimal stand-in for SDKClient."""

    session_id: str = ""
    pid: int = 99999

    async def query(self, prompt: str):
        yield {"type": "text", "content": "Hello from SDK"}

    async def close(self):
        pass


def _make_session_manager(pool_clients=None, max_sessions=10, resume_client_factory=None):
    """Create a SessionManager with fake dependencies."""
    pool = MagicMock()
    if pool_clients:
        pool.get.side_effect = pool_clients + [None] * 10
    else:
        pool.get.return_value = None
    pool.size.return_value = len(pool_clients) if pool_clients else 0
    pool.replenish = AsyncMock()

    index = MagicMock()
    index.create.side_effect = lambda sid, meta: {
        "session_id": sid,
        "status": "creating",
        "source": meta.get("source", "cold"),
    }
    index.update.side_effect = lambda sid, updates: {"session_id": sid, **updates}
    index.get.return_value = {"session_id": "test", "status": "terminated", "is_resumable": True}

    monitor = MagicMock()
    monitor.register = MagicMock()
    monitor.unregister = MagicMock()
    monitor.mark_query_active = MagicMock()
    monitor.mark_query_complete = MagicMock()

    async def _cold_start_factory():
        client = FakeClient()
        client.session_id = str(uuid.uuid4())
        client.pid = 99999
        return client

    sm = SessionManager(
        pool=pool,
        session_index=index,
        subprocess_monitor=monitor,
        client_factory=_cold_start_factory,
        max_sessions=max_sessions,
        resume_client_factory=resume_client_factory,
    )
    return sm, pool, index, monitor


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_from_pool(self):
        client = FakeClient(session_id="pooled-1", pid=11111)
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        result = await sm.create_session()
        assert result["source"] == "pre-warm"
        assert sm.active_session_count() == 1

    @pytest.mark.asyncio
    async def test_create_session_cold_start_fallback(self):
        sm, pool, index, monitor = _make_session_manager(pool_clients=[])

        result = await sm.create_session()
        assert result["source"] == "cold"
        assert sm.active_session_count() == 1

    @pytest.mark.asyncio
    async def test_create_session_at_capacity_returns_error(self):
        sm, pool, index, monitor = _make_session_manager(max_sessions=2)

        await sm.create_session()
        await sm.create_session()

        with pytest.raises(CapacityError, match="capacity|maximum"):
            await sm.create_session()
        assert sm.active_session_count() == 2

    @pytest.mark.asyncio
    async def test_create_session_from_pool_triggers_replenish(self):
        """When a client is acquired from pool, replenish is triggered."""
        client = FakeClient(session_id="pooled-1", pid=11111)
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        await sm.create_session()

        # Give the background task a moment to be created
        await asyncio.sleep(0.05)
        pool.replenish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cold_start_does_not_trigger_replenish(self):
        """When pool is empty and cold start is used, replenish is NOT triggered."""
        sm, pool, index, monitor = _make_session_manager(pool_clients=[])

        await sm.create_session()

        await asyncio.sleep(0.05)
        pool.replenish.assert_not_awaited()


class TestQuery:
    @pytest.mark.asyncio
    async def test_query_yields_events(self):
        client = FakeClient(session_id="query-1", pid=11111)
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        result = await sm.create_session()
        session_id = result["session_id"]

        events = []
        async for event in sm.query(session_id, "hello"):
            events.append(event)

        assert len(events) >= 1
        assert any("content" in e for e in events)

    @pytest.mark.asyncio
    async def test_query_persists_sdk_session_id(self):
        """After a query completes, sdk_session_id is persisted to the index."""
        client = FakeClient(session_id="sdk-session-abc", pid=11111)
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        result = await sm.create_session()
        session_id = result["session_id"]

        async for _ in sm.query(session_id, "hello"):
            pass

        # session_id property on client should have been persisted
        index.update.assert_called_with(session_id, {"sdk_session_id": "sdk-session-abc"})

    @pytest.mark.asyncio
    async def test_query_rejects_concurrent_run(self):
        client = FakeClient(session_id="concurrent-1", pid=11111)

        # Make a slow client that yields events with a delay
        async def slow_query(prompt):
            await asyncio.sleep(0.5)
            yield {"type": "text", "content": "done"}

        client.query = slow_query
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        result = await sm.create_session()
        session_id = result["session_id"]

        # Start first query
        async def consume_first():
            async for _ in sm.query(session_id, "first"):
                pass

        task = asyncio.create_task(consume_first())
        await asyncio.sleep(0.05)  # let it start

        with pytest.raises(ConcurrentRunError, match="already in progress"):
            async for _ in sm.query(session_id, "second"):
                pass

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestDestroy:
    @pytest.mark.asyncio
    async def test_destroy_session_cleans_subprocess(self):
        client = FakeClient(session_id="destroy-1", pid=11111)
        sm, pool, index, monitor = _make_session_manager(pool_clients=[client])

        result = await sm.create_session()
        session_id = result["session_id"]

        await sm.destroy_session(session_id)
        assert sm.active_session_count() == 0
        monitor.unregister.assert_called_with(session_id)
        index.update.assert_called()
        # Check the last update was to set status=terminated
        last_call_updates = index.update.call_args[0][1]
        assert last_call_updates["status"] == "terminated"


class TestResume:
    @pytest.mark.asyncio
    async def test_resume_session_with_sdk_session_id(self):
        """Resume uses the resume_client_factory with the SDK session id."""
        resumed_client = FakeClient(session_id="resumed-sdk-id", pid=22222)
        resume_factory = AsyncMock(return_value=resumed_client)

        sm, pool, index, monitor = _make_session_manager(
            resume_client_factory=resume_factory,
        )
        # Set up the index to return an entry with sdk_session_id
        index.get.return_value = {
            "session_id": "old-session-id",
            "status": "terminated",
            "is_resumable": True,
            "sdk_session_id": "sdk-abc-123",
        }

        result = await sm.resume_session("old-session-id")
        assert result["session_id"] != "old-session-id"
        assert result["source"] == "resume"
        assert sm.active_session_count() == 1

        # Verify the resume factory was called with the SDK session id
        resume_factory.assert_awaited_once_with("sdk-abc-123")

    @pytest.mark.asyncio
    async def test_resume_falls_back_without_sdk_session_id(self):
        """If no sdk_session_id is stored, falls back to fresh client."""
        resume_factory = AsyncMock()

        sm, pool, index, monitor = _make_session_manager(
            resume_client_factory=resume_factory,
        )
        # No sdk_session_id in the old entry
        index.get.return_value = {
            "session_id": "old-session-id",
            "status": "terminated",
            "is_resumable": True,
        }

        result = await sm.resume_session("old-session-id")
        assert result["source"] == "resume"
        assert sm.active_session_count() == 1

        # resume_factory should NOT have been called (no sdk_session_id)
        resume_factory.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resume_falls_back_on_error(self):
        """If resume factory raises, falls back to fresh client."""
        resume_factory = AsyncMock(side_effect=RuntimeError("resume failed"))

        sm, pool, index, monitor = _make_session_manager(
            resume_client_factory=resume_factory,
        )
        index.get.return_value = {
            "session_id": "old-session-id",
            "status": "terminated",
            "sdk_session_id": "sdk-abc-123",
        }

        result = await sm.resume_session("old-session-id")
        assert result["source"] == "resume"
        assert sm.active_session_count() == 1

        # The old session should be marked as non-resumable
        index.update.assert_any_call("old-session-id", {"is_resumable": False})

    @pytest.mark.asyncio
    async def test_resume_without_resume_factory(self):
        """If no resume_client_factory is provided, falls back to regular factory."""
        sm, pool, index, monitor = _make_session_manager()
        index.get.return_value = {
            "session_id": "old-session-id",
            "status": "terminated",
            "sdk_session_id": "sdk-abc-123",
        }

        result = await sm.resume_session("old-session-id")
        assert result["source"] == "resume"
        assert sm.active_session_count() == 1
