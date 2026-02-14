"""Tests for JSONSessionIndex (TASK-002)."""

import asyncio
import json
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def index_dir(tmp_path):
    return tmp_path / "sessions"


@pytest.fixture
def index(index_dir):
    from src.core.session_index import JSONSessionIndex
    return JSONSessionIndex(str(index_dir))


class TestInit:
    def test_init_creates_directory_and_file(self, index, index_dir):
        index.init()
        assert index_dir.exists()
        index_file = index_dir / "index.json"
        assert index_file.exists()
        assert json.loads(index_file.read_text()) == []

    def test_init_is_idempotent(self, index, index_dir):
        index.init()
        index.init()
        index_file = index_dir / "index.json"
        assert json.loads(index_file.read_text()) == []


class TestCreateAndGet:
    def test_create_writes_metadata_atomically(self, index, index_dir):
        index.init()
        session_id = str(uuid.uuid4())
        result = index.create(session_id, {"source": "cold"})

        assert result["session_id"] == session_id
        assert result["status"] == "creating"
        assert result["source"] == "cold"
        assert result["message_count"] == 0
        assert result["is_resumable"] is True
        bak_file = index_dir / "index.json.bak"
        assert bak_file.exists()

    def test_get_returns_correct_metadata(self, index):
        index.init()
        session_id = str(uuid.uuid4())
        index.create(session_id, {"source": "pre-warm"})

        metadata = index.get(session_id)
        assert metadata is not None
        assert metadata["session_id"] == session_id
        assert metadata["status"] == "creating"
        assert isinstance(metadata["created_at"], str)
        # ISO 8601 format check
        assert "T" in metadata["created_at"]

    def test_get_returns_none_for_missing(self, index):
        index.init()
        result = index.get("nonexistent-id")
        assert result is None


class TestUpdate:
    def test_update_modifies_fields(self, index):
        index.init()
        session_id = str(uuid.uuid4())
        index.create(session_id, {"source": "cold"})

        index.update(session_id, {"status": "active", "message_count": 5})
        metadata = index.get(session_id)
        assert metadata["status"] == "active"
        assert metadata["message_count"] == 5


class TestList:
    def test_list_returns_all_sessions(self, index):
        index.init()
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for sid in ids:
            index.create(sid, {"source": "cold"})

        sessions = index.list()
        assert len(sessions) == 3
        listed_ids = {s["session_id"] for s in sessions}
        assert listed_ids == set(ids)


class TestDelete:
    def test_delete_removes_session(self, index):
        index.init()
        session_id = str(uuid.uuid4())
        index.create(session_id, {"source": "cold"})

        index.delete(session_id)
        assert index.get(session_id) is None
        assert len(index.list()) == 0


class TestCorruptionRecovery:
    def test_corrupted_json_recovers_from_backup(self, index, index_dir):
        index.init()
        session_id_1 = str(uuid.uuid4())
        index.create(session_id_1, {"source": "cold"})
        # Second write causes .bak to contain [session_id_1]
        session_id_2 = str(uuid.uuid4())
        index.create(session_id_2, {"source": "cold"})

        # Corrupt the index file
        index_file = index_dir / "index.json"
        index_file.write_text("{not valid json")

        # Should recover from .bak (which has session_id_1 only)
        sessions = index.list()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == session_id_1


class TestCleanup:
    def test_cleanup_old_removes_terminated(self, index):
        from datetime import datetime, timedelta, timezone
        index.init()

        # Active session
        active_id = str(uuid.uuid4())
        index.create(active_id, {"source": "cold"})
        index.update(active_id, {"status": "active"})

        # Terminated 60 days ago
        old_id = str(uuid.uuid4())
        index.create(old_id, {"source": "cold"})
        old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        index.update(old_id, {
            "status": "terminated",
            "last_active_at": old_time,
        })

        # Terminated 10 days ago
        recent_id = str(uuid.uuid4())
        index.create(recent_id, {"source": "cold"})
        recent_time = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        index.update(recent_id, {
            "status": "terminated",
            "last_active_at": recent_time,
        })

        index.cleanup_old(days=30)

        sessions = index.list()
        session_ids = {s["session_id"] for s in sessions}
        assert active_id in session_ids
        assert old_id not in session_ids
        assert recent_id in session_ids
        assert len(sessions) == 2


class TestConcurrency:
    def test_concurrent_creates_no_corruption(self, index):
        index.init()
        uuids = [str(uuid.uuid4()) for _ in range(5)]

        async def run_creates():
            await asyncio.gather(
                *[asyncio.to_thread(index.create, uid, {"source": "cold"}) for uid in uuids]
            )

        asyncio.run(run_creates())

        sessions = index.list()
        assert len(sessions) == 5
        session_ids = {s["session_id"] for s in sessions}
        assert session_ids == set(uuids)

        # Verify JSON is valid
        index_dir = Path(index._dir)
        data = json.loads((index_dir / "index.json").read_text())
        assert len(data) == 5
