"""Integration tests for platform startup sequence (TASK-009)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import Settings
from src.core.extension_loader import ExtensionLoader
from src.core.prewarm_pool import PreWarmPool
from src.core.prompt_expander import PromptExpander
from src.core.session_index import JSONSessionIndex
from src.core.session_manager import SessionManager
from src.core.subprocess_monitor import SubprocessMonitor
from src.main import create_app


@dataclass
class FakeClient:
    session_id: str = ""
    pid: int = 99999

    async def query(self, prompt: str):
        yield {"type": "text", "content": "Hello"}

    async def close(self):
        pass


async def _good_factory():
    return FakeClient()


async def _bad_factory():
    raise RuntimeError("Invalid API key")


@pytest.fixture(autouse=True)
def set_env(tmp_path, monkeypatch):
    """Set required env vars for tests."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SESSION_INDEX_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("PROJECT_CWD", str(tmp_path / "project"))
    monkeypatch.setenv("PREWARM_POOL_SIZE", "1")
    (tmp_path / "project").mkdir(exist_ok=True)


class TestStartupSequence:
    """Test the startup sequence by simulating what the lifespan does."""

    @pytest.mark.asyncio
    async def test_successful_startup_components(self, tmp_path):
        """Verify all components are created in correct sequence."""
        settings = Settings()

        # Step 1: Scan extensions
        loader = ExtensionLoader(settings.project_cwd)
        config = loader.scan()
        assert config is not None

        # Step 2: Init session index
        index = JSONSessionIndex(str(tmp_path / "sessions"))
        index.init()
        assert (tmp_path / "sessions" / "index.json").exists()

        # Step 3: Prompt expander
        expander = PromptExpander(loader)
        assert expander is not None

        # Step 4: Pre-warm pool
        pool = PreWarmPool(target_size=1, client_factory=_good_factory)
        await pool.fill()
        assert pool.size() >= 1

        # Step 5: Subprocess monitor
        monitor = SubprocessMonitor()
        await monitor.start()
        assert monitor._running is True
        assert len(monitor._tasks) >= 3

        # Step 6: Session manager
        sm = SessionManager(
            pool=pool,
            session_index=index,
            subprocess_monitor=monitor,
            client_factory=_good_factory,
            max_sessions=10,
        )
        assert sm.active_session_count() == 0

        # Cleanup
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_prewarm_failure_raises(self):
        """All pre-warm failures should raise RuntimeError."""
        pool = PreWarmPool(target_size=2, client_factory=_bad_factory)
        with pytest.raises(RuntimeError, match="pre-warm|failed"):
            await pool.fill()

    @pytest.mark.asyncio
    async def test_monitor_tasks_running_and_stoppable(self):
        monitor = SubprocessMonitor()
        await monitor.start()
        assert monitor._running is True
        assert len(monitor._tasks) >= 3

        await monitor.stop()
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_sessions(self, tmp_path):
        """Verify shutdown destroys all active sessions."""
        index = JSONSessionIndex(str(tmp_path / "sessions"))
        index.init()
        monitor = SubprocessMonitor()
        pool = PreWarmPool(target_size=1, client_factory=_good_factory)
        await pool.fill()

        sm = SessionManager(
            pool=pool,
            session_index=index,
            subprocess_monitor=monitor,
            client_factory=_good_factory,
            max_sessions=10,
        )

        await sm.create_session()
        assert sm.active_session_count() == 1

        # Simulate shutdown
        for session_id in list(sm._sessions.keys()):
            await sm.destroy_session(session_id)
        assert sm.active_session_count() == 0


class TestRouterRegistration:
    @pytest.mark.asyncio
    async def test_liveness_probe_always_available(self):
        app = create_app(client_factory=_good_factory, skip_prewarm=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_routers_registered_on_app(self):
        """Check that routes are registered (by inspecting app.routes)."""
        app = create_app(client_factory=_good_factory, skip_prewarm=True)
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/chat/completions" in route_paths
        assert "/api/v1/sessions" in route_paths
        assert "/api/v1/health/ready" in route_paths
        assert "/api/v1/extensions" in route_paths
        assert "/api/v1/health/live" in route_paths

    @pytest.mark.asyncio
    async def test_agui_not_registered_phase1a(self):
        """AG-UI router should NOT be registered in Phase 1a."""
        app = create_app(client_factory=_good_factory, skip_prewarm=True)
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/agent/run" not in route_paths
