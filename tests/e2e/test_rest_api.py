"""E2E tests for REST API endpoints (TASK-012)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock


@dataclass
class FakeClient:
    """Minimal fake SDK client for session creation."""

    pid: int = 99999

    async def query(self, prompt: str):
        yield {"type": "text", "content": "Hello"}

    async def close(self):
        pass


class TestSessionCRUD:
    """Test session creation and listing through the full app stack."""

    def test_create_session(self, client, app):
        """POST /api/v1/sessions creates a session when factory is provided."""
        # Patch the session manager's client factory to return a fake client
        original_factory = app.state.session_manager._client_factory

        async def fake_factory():
            return FakeClient()

        app.state.session_manager._client_factory = fake_factory

        try:
            resp = client.post("/api/v1/sessions", json={})
            assert resp.status_code == 201
            data = resp.json()
            assert "session_id" in data
            assert data["status"] == "creating"
        finally:
            app.state.session_manager._client_factory = original_factory

    def test_list_sessions_returns_array(self, client):
        resp = client.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_extensions_returns_expected_shape(self, client):
        resp = client.get("/api/v1/extensions")
        assert resp.status_code == 200
        data = resp.json()
        assert "mcp_servers" in data
        assert "skills" in data
        assert "commands" in data
        assert "all_slash_commands" in data
        assert "total_count" in data
        assert isinstance(data["mcp_servers"], list)
        assert isinstance(data["skills"], list)
        assert isinstance(data["commands"], list)
        assert isinstance(data["all_slash_commands"], list)
        assert isinstance(data["total_count"], int)

    def test_delete_nonexistent_session_returns_204(self, client):
        """Delete is idempotent - returns 204 even if session doesn't exist in memory."""
        resp = client.delete("/api/v1/sessions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 204
