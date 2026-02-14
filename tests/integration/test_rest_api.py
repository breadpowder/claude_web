"""Integration tests for REST API endpoints (TASK-008)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.api.service.sessions import router as sessions_router
from src.api.service.health import router as health_router
from src.api.service.extensions import router as extensions_router
from src.core.exceptions import CapacityError
from src.core.models import (
    CommandInfo,
    ExtensionConfig,
    MCPServerConfig,
    SkillInfo,
)


def _create_test_app(
    sessions=None,
    at_capacity=False,
    pool_depth=2,
    extension_config=None,
):
    """Create a FastAPI app with mocked dependencies."""
    app = FastAPI()
    app.include_router(sessions_router)
    app.include_router(health_router)
    app.include_router(extensions_router)

    if sessions is None:
        sessions = []

    # Session index
    index = MagicMock()
    index.list.return_value = sessions
    index.get.side_effect = lambda sid: next(
        (s for s in sessions if s["session_id"] == sid), None
    )
    index.create.side_effect = lambda sid, meta: {
        "session_id": sid,
        "status": "creating",
        "source": meta.get("source", "cold"),
    }

    # Session manager
    active_count = {"count": len(sessions)}

    async def _create():
        if at_capacity:
            raise CapacityError("At maximum capacity of 10 sessions")
        sid = str(uuid.uuid4())
        active_count["count"] += 1
        return {"session_id": sid, "status": "creating", "source": "cold"}

    async def _destroy(sid):
        active_count["count"] -= 1

    sm = MagicMock()
    sm.create_session = AsyncMock(side_effect=_create)
    sm.destroy_session = AsyncMock(side_effect=_destroy)
    sm.active_session_count.side_effect = lambda: active_count["count"]

    # Pool
    pool = MagicMock()
    pool.size.return_value = pool_depth

    # Settings
    settings = MagicMock()
    settings.max_sessions = 10

    # Extension config
    if extension_config is None:
        extension_config = ExtensionConfig()

    app.state.session_index = index
    app.state.session_manager = sm
    app.state.pool = pool
    app.state.settings = settings
    app.state.extension_config = extension_config

    return app


@pytest.fixture
def basic_sessions():
    return [
        {
            "session_id": "sess-1",
            "status": "active",
            "created_at": "2026-02-14T10:00:00+00:00",
            "last_active_at": "2026-02-14T10:30:00+00:00",
            "message_count": 5,
        },
        {
            "session_id": "sess-2",
            "status": "creating",
            "created_at": "2026-02-14T11:00:00+00:00",
            "last_active_at": "2026-02-14T11:00:00+00:00",
            "message_count": 0,
        },
    ]


class TestListSessions:
    @pytest.mark.asyncio
    async def test_list_sessions_returns_summaries(self, basic_sessions):
        app = _create_test_app(sessions=basic_sessions)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2
        for s in data["sessions"]:
            assert "session_id" in s
            assert "status" in s
            assert "created_at" in s
            assert "last_active_at" in s
            assert "message_count" in s


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_returns_201(self):
        app = _create_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/sessions", json={})
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["source"] in ["pre-warm", "cold"]
        assert len(data["session_id"]) == 36

    @pytest.mark.asyncio
    async def test_create_session_at_capacity_returns_503(self):
        app = _create_test_app(at_capacity=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/sessions", json={})
        assert resp.status_code == 503
        assert "capacity" in resp.json()["error"].lower() or "maximum" in resp.json()["error"].lower()


class TestGetSession:
    @pytest.mark.asyncio
    async def test_get_session_returns_detail(self, basic_sessions):
        app = _create_test_app(sessions=basic_sessions)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sessions/sess-1")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-1"

    @pytest.mark.asyncio
    async def test_get_session_not_found_returns_404(self):
        app = _create_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sessions/nonexistent-uuid")
        assert resp.status_code == 404
        assert "not found" in resp.json()["error"].lower()


class TestDeleteSession:
    @pytest.mark.asyncio
    async def test_delete_session_returns_204(self, basic_sessions):
        app = _create_test_app(sessions=basic_sessions)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete("/api/v1/sessions/sess-1")
        assert resp.status_code == 204


class TestReadinessProbe:
    @pytest.mark.asyncio
    async def test_readiness_probe_returns_metrics(self):
        app = _create_test_app(pool_depth=2)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["pool_depth"] >= 0
        assert data["active_sessions"] >= 0
        assert data["max_sessions"] == 10

    @pytest.mark.asyncio
    async def test_readiness_probe_returns_503_when_not_ready(self):
        app = _create_test_app(pool_depth=0)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "reason" in data


class TestExtensions:
    def _config_with_extensions(self):
        return ExtensionConfig(
            mcp_servers={
                "github": MCPServerConfig(
                    name="github",
                    command="npx",
                    args=["-y", "server"],
                    description="GitHub integration via MCP",
                )
            },
            skills=[
                SkillInfo(
                    name="code-review",
                    description="Review code for quality and best practices",
                    path=".claude/skills/code-review",
                    invoke_prefix="/code-review",
                )
            ],
            commands=[
                CommandInfo(
                    name="deploy",
                    description="Deploy to staging environment",
                    path="commands/deploy",
                    invoke_prefix="/deploy",
                )
            ],
        )

    @pytest.mark.asyncio
    async def test_extensions_endpoint_returns_loaded(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        assert resp.status_code == 200
        data = resp.json()
        assert "mcp_servers" in data
        assert "skills" in data
        assert "commands" in data

    @pytest.mark.asyncio
    async def test_extensions_skills_include_metadata(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        skills = resp.json()["skills"]
        assert len(skills) == 1
        assert skills[0]["name"] == "code-review"
        assert skills[0]["description"] == "Review code for quality and best practices"
        assert skills[0]["invoke_prefix"] == "/code-review"
        assert skills[0]["type"] == "skill"
        assert "path" in skills[0]

    @pytest.mark.asyncio
    async def test_extensions_commands_include_metadata(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        commands = resp.json()["commands"]
        assert len(commands) == 1
        assert commands[0]["name"] == "deploy"
        assert commands[0]["invoke_prefix"] == "/deploy"
        assert commands[0]["type"] == "command"
        assert commands[0]["invoke_method"] == "manual"
        assert "description" in commands[0]

    @pytest.mark.asyncio
    async def test_extensions_all_slash_commands_array(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        data = resp.json()
        assert "all_slash_commands" in data
        assert len(data["all_slash_commands"]) == 2
        types = {s["type"] for s in data["all_slash_commands"]}
        assert "skill" in types
        assert "command" in types
        for s in data["all_slash_commands"]:
            assert "name" in s
            assert "description" in s
            assert "type" in s
            assert "invoke_prefix" in s

    @pytest.mark.asyncio
    async def test_extensions_mcp_servers_include_metadata(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        servers = resp.json()["mcp_servers"]
        assert len(servers) == 1
        assert servers[0]["name"] == "github"
        assert servers[0]["transport"] == "stdio"
        assert servers[0]["status"] == "configured"
        assert "tool_count" in servers[0]

    @pytest.mark.asyncio
    async def test_extensions_total_count(self):
        config = self._config_with_extensions()
        app = _create_test_app(extension_config=config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        assert resp.json()["total_count"] == 3

    @pytest.mark.asyncio
    async def test_extensions_empty_returns_empty_arrays(self):
        app = _create_test_app(extension_config=ExtensionConfig())
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/extensions")
        data = resp.json()
        assert data["mcp_servers"] == []
        assert data["skills"] == []
        assert data["commands"] == []
        assert data["all_slash_commands"] == []
        assert data["total_count"] == 0


class TestNoAuth:
    @pytest.mark.asyncio
    async def test_endpoints_no_auth_required(self):
        app = _create_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/sessions")
        assert resp.status_code != 401
        assert resp.status_code != 403
