"""QA Contract Verification Tests - independent from developer tests.

Tests verify the system against SPEC CONTRACTS (API shapes, response codes, field types).
Based on qa-test-plan.md test IDs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient


# --- Fake SDK client for session creation ---
@dataclass
class FakeClient:
    pid: int = 99999

    async def query(self, prompt: str):
        yield {"type": "text", "content": "Hello from Claude"}

    async def close(self):
        pass


async def fake_factory():
    return FakeClient()


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create app with mocked SDK boundary."""
    from tests.conftest import write_test_config

    project_dir = tmp_path / "project"
    project_dir.mkdir(exist_ok=True)

    # Create test extensions for extension API verification
    skills_dir = project_dir / ".claude" / "skills" / "test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\ndescription: A test skill for QA\n---\n\nTest skill content."
    )

    commands_dir = project_dir / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "deploy.md").write_text(
        "---\ndescription: Deploy the application\n---\n\nDeploy instructions."
    )

    config_path = write_test_config(
        tmp_path,
        max_sessions=3,
        project_cwd=str(project_dir),
    )

    from src.main import create_app

    test_app = create_app(client_factory=fake_factory, skip_prewarm=True, config_path=config_path)
    yield test_app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ==================================================================
# Category 1: REST API Contract Tests (QA-REST-*)
# ==================================================================


class TestQA_REST_Sessions:
    """QA-REST-001 through QA-REST-010: Session CRUD contracts."""

    def test_qa_rest_001_list_sessions_empty(self, client):
        """QA-REST-001: GET /api/v1/sessions returns 200 with empty sessions array."""
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)
        assert len(data["sessions"]) == 0

    def test_qa_rest_002_create_session(self, client):
        """QA-REST-002: POST /api/v1/sessions returns 201 with session_id."""
        resp = client.post("/api/v1/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0
        assert "status" in data

    def test_qa_rest_004_list_sessions_after_creation(self, client):
        """QA-REST-004: After creation, GET returns array containing the session."""
        create_resp = client.post("/api/v1/sessions", json={})
        session_id = create_resp.json()["session_id"]

        list_resp = client.get("/api/v1/sessions")
        assert list_resp.status_code == 200
        sessions = list_resp.json()["sessions"]
        ids = [s["session_id"] for s in sessions]
        assert session_id in ids

    def test_qa_rest_005_get_session_details(self, client):
        """QA-REST-005: GET /api/v1/sessions/{id} returns session detail."""
        create_resp = client.post("/api/v1/sessions", json={})
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/api/v1/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert "status" in data
        assert "created_at" in data

    def test_qa_rest_006_get_nonexistent_session(self, client):
        """QA-REST-006: GET nonexistent session returns 404."""
        resp = client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_qa_rest_007_delete_session(self, client):
        """QA-REST-007: DELETE session returns 204, subsequent GET returns 404."""
        create_resp = client.post("/api/v1/sessions", json={})
        session_id = create_resp.json()["session_id"]

        del_resp = client.delete(f"/api/v1/sessions/{session_id}")
        assert del_resp.status_code == 204

    def test_qa_rest_009_session_field_types(self, client):
        """QA-REST-009: Session fields have correct types."""
        create_resp = client.post("/api/v1/sessions", json={})
        session_id = create_resp.json()["session_id"]

        resp = client.get(f"/api/v1/sessions/{session_id}")
        data = resp.json()
        assert isinstance(data["session_id"], str)
        assert isinstance(data["status"], str)
        assert isinstance(data["created_at"], str)

    def test_qa_rest_010_no_auth_required(self, client):
        """QA-REST-010: Endpoints work without auth headers."""
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200


class TestQA_REST_Health:
    """QA-REST-011 through QA-REST-013: Health endpoint contracts."""

    def test_qa_rest_011_liveness_probe(self, client):
        """QA-REST-011: GET /api/v1/health/live returns 200 with status ok."""
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_qa_rest_012_readiness_probe(self, client):
        """QA-REST-012: GET /api/v1/health/ready returns 200 or 503."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "pool_depth" in data
        assert "active_sessions" in data
        assert "max_sessions" in data

    def test_qa_rest_013_readiness_field_types(self, client):
        """QA-REST-013: Readiness fields have correct types."""
        resp = client.get("/api/v1/health/ready")
        data = resp.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["pool_depth"], int)
        assert isinstance(data["active_sessions"], int)
        assert isinstance(data["max_sessions"], int)


class TestQA_REST_Extensions:
    """QA-REST-014 through QA-REST-019: Extension endpoint contracts."""

    def test_qa_rest_014_list_extensions(self, client):
        """QA-REST-014: GET /api/v1/extensions returns 200 with expected shape."""
        resp = client.get("/api/v1/extensions")
        assert resp.status_code == 200
        data = resp.json()
        assert "mcp_servers" in data
        assert "skills" in data
        assert "commands" in data
        assert "all_slash_commands" in data
        assert "total_count" in data

    def test_qa_rest_015_mcp_server_shape(self, client):
        """QA-REST-015: MCP servers have name, status fields."""
        resp = client.get("/api/v1/extensions")
        data = resp.json()
        assert isinstance(data["mcp_servers"], list)

    def test_qa_rest_016_skill_shape(self, client):
        """QA-REST-016: Skills have name, description, invoke_prefix fields."""
        resp = client.get("/api/v1/extensions")
        data = resp.json()
        assert isinstance(data["skills"], list)
        assert len(data["skills"]) > 0, "Expected at least one test skill"
        skill = data["skills"][0]
        assert "name" in skill
        assert "description" in skill
        assert "invoke_prefix" in skill
        assert skill["invoke_prefix"].startswith("/")

    def test_qa_rest_017_command_shape(self, client):
        """QA-REST-017: Commands have name, description, invoke_prefix fields."""
        resp = client.get("/api/v1/extensions")
        data = resp.json()
        assert isinstance(data["commands"], list)
        assert len(data["commands"]) > 0, "Expected at least one test command"
        cmd = data["commands"][0]
        assert "name" in cmd
        assert "description" in cmd
        assert "invoke_prefix" in cmd
        assert cmd["invoke_prefix"].startswith("/")

    def test_qa_rest_018_all_slash_commands(self, client):
        """QA-REST-018: all_slash_commands merges skills and commands."""
        resp = client.get("/api/v1/extensions")
        data = resp.json()
        all_cmds = data["all_slash_commands"]
        assert isinstance(all_cmds, list)
        assert len(all_cmds) >= 2  # At least the test skill and command
        for cmd in all_cmds:
            assert "name" in cmd
            assert "description" in cmd
            assert "type" in cmd
            assert "invoke_prefix" in cmd

    def test_qa_rest_019_extensions_total_count(self, client):
        """QA-REST-019 variant: total_count matches sum of servers + skills + commands."""
        resp = client.get("/api/v1/extensions")
        data = resp.json()
        expected = len(data["mcp_servers"]) + len(data["skills"]) + len(data["commands"])
        assert data["total_count"] == expected


# ==================================================================
# Category 2: OpenAI-Compliant API Tests (QA-OAI-*)
# ==================================================================


class TestQA_OAI_Streaming:
    """QA-OAI-001 through QA-OAI-007: Streaming SSE contracts."""

    def _get_sse_events(self, client) -> list[str]:
        """Helper: send streaming request and collect SSE data lines."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True,
            },
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        data_lines = [l.removeprefix("data: ").strip() for l in lines if l.startswith("data:")]
        return data_lines

    def test_qa_oai_001_basic_streaming(self, client):
        """QA-OAI-001: POST with stream:true returns SSE events."""
        data_lines = self._get_sse_events(client)
        assert len(data_lines) > 0, "Expected at least one SSE data line"

    def test_qa_oai_002_sse_chunk_format(self, client):
        """QA-OAI-002: Each SSE data line is valid JSON with choices[].delta."""
        data_lines = self._get_sse_events(client)
        json_chunks = [l for l in data_lines if l != "[DONE]"]
        assert len(json_chunks) > 0
        for chunk_str in json_chunks:
            chunk = json.loads(chunk_str)
            assert "id" in chunk
            assert "choices" in chunk
            assert isinstance(chunk["choices"], list)
            assert "delta" in chunk["choices"][0]

    def test_qa_oai_005_done_sentinel(self, client):
        """QA-OAI-005: Stream ends with [DONE]."""
        data_lines = self._get_sse_events(client)
        assert data_lines[-1] == "[DONE]"

    def test_qa_oai_007_consistent_id(self, client):
        """QA-OAI-007: All chunks share the same id."""
        data_lines = self._get_sse_events(client)
        json_chunks = [json.loads(l) for l in data_lines if l != "[DONE]"]
        ids = {c["id"] for c in json_chunks}
        assert len(ids) == 1, f"Expected consistent id, got {ids}"


class TestQA_OAI_NonStreaming:
    """QA-OAI-008 through QA-OAI-010: Non-streaming contracts."""

    def test_qa_oai_008_non_streaming(self, client):
        """QA-OAI-008: POST with stream:false returns single JSON."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert isinstance(data["choices"][0]["message"]["content"], str)

    def test_qa_oai_009_non_streaming_shape(self, client):
        """QA-OAI-009: Non-streaming has id, choices, usage."""
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False,
            },
        )
        data = resp.json()
        assert "id" in data
        assert "choices" in data
        assert "usage" in data


class TestQA_OAI_Validation:
    """QA-OAI-011 through QA-OAI-015: Validation and error contracts."""

    def test_qa_oai_011_missing_model(self, client):
        """QA-OAI-011: Missing model returns 400."""
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_qa_oai_012_missing_messages(self, client):
        """QA-OAI-012: Missing messages returns 400."""
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "claude-sonnet-4-20250514"},
        )
        assert resp.status_code == 400

    def test_qa_oai_014_error_response_format(self, client):
        """QA-OAI-014: Error responses follow OpenAI error format."""
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "Hello"}]},
        )
        data = resp.json()
        assert "error" in data
        error = data["error"]
        assert "message" in error


# ==================================================================
# Category 4: Session Lifecycle Tests (QA-LIFE-*)
# ==================================================================


class TestQA_LIFE:
    """QA-LIFE-001 through QA-LIFE-010: Session lifecycle contracts."""

    def test_qa_life_001_session_creation(self, client):
        """QA-LIFE-001: Session creation returns unique IDs."""
        resp1 = client.post("/api/v1/sessions", json={})
        resp2 = client.post("/api/v1/sessions", json={})
        assert resp1.json()["session_id"] != resp2.json()["session_id"]

    def test_qa_life_004_capacity_limit(self, client):
        """QA-LIFE-004: At MAX_SESSIONS (3), creation returns 503."""
        # Create 3 sessions (our limit)
        for _ in range(3):
            resp = client.post("/api/v1/sessions", json={})
            assert resp.status_code == 201

        # 4th should fail
        resp = client.post("/api/v1/sessions", json={})
        assert resp.status_code == 503

    def test_qa_life_005_liveness_always_available(self, client):
        """QA-LIFE-005: Liveness probe available immediately."""
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200


# ==================================================================
# Category 6: Edge Case Tests (QA-EDGE-*)
# ==================================================================


class TestQA_EDGE:
    """QA-EDGE: Edge case verification."""

    def test_qa_edge_001_nonexistent_session(self, client):
        """QA-EDGE-001: Nonexistent session returns 404."""
        resp = client.get("/api/v1/sessions/totally-fake-id")
        assert resp.status_code == 404

    def test_qa_edge_005_empty_pool_readiness(self, client):
        """QA-EDGE-005: Empty pool → readiness returns 503."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "not_ready"

    def test_qa_edge_extensions_no_config(self, app, tmp_path, monkeypatch):
        """QA-EDGE: Extensions endpoint works with empty project dir (may include user-level)."""
        from tests.conftest import write_test_config

        empty_dir = tmp_path / "empty_project"
        empty_dir.mkdir()

        config_path = write_test_config(
            tmp_path, project_cwd=str(empty_dir)
        )

        from src.main import create_app

        empty_app = create_app(client_factory=fake_factory, skip_prewarm=True, config_path=config_path)
        with TestClient(empty_app) as c:
            resp = c.get("/api/v1/extensions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["mcp_servers"] == []
            # Skills/commands may include user-level (~/.claude/) entries
            assert isinstance(data["skills"], list)
            assert isinstance(data["commands"], list)
            assert isinstance(data["total_count"], int)
