"""Integration tests for platform startup sequence."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import load_engine_config
from src.core.extension_loader import ExtensionLoader
from src.core.prewarm_pool import PreWarmPool
from src.core.prompt_expander import PromptExpander
from src.core.session_index import JSONSessionIndex
from src.core.session_manager import SessionManager
from src.core.subprocess_monitor import SubprocessMonitor
from src.main import create_app
from tests.conftest import write_test_config


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


class TestStartupSequence:
    """Test the startup sequence by simulating what the lifespan does."""

    @pytest.mark.asyncio
    async def test_successful_startup_components(self, tmp_path):
        """Verify all components are created in correct sequence."""
        config_path = write_test_config(
            tmp_path, prewarm_pool_size=1
        )
        config = load_engine_config(config_path)

        # Step 1: Scan extensions
        loader = ExtensionLoader(config.engine.project_cwd)
        ext_config = loader.scan()
        assert ext_config is not None

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


class TestNestedSessionEnvCleanup:
    """Test that CLAUDECODE env var is removed to prevent nested session errors."""

    @pytest.mark.asyncio
    async def test_claudecode_env_removed_on_startup(self, tmp_path, monkeypatch):
        """create_app must unset CLAUDECODE so SDK subprocess won't refuse to start."""
        import os
        monkeypatch.setenv("CLAUDECODE", "1")

        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)

        assert os.environ.get("CLAUDECODE") is None

    @pytest.mark.asyncio
    async def test_claudecode_env_absent_stays_absent(self, tmp_path):
        """If CLAUDECODE is not set, startup should not fail."""
        import os
        os.environ.pop("CLAUDECODE", None)

        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)

        assert os.environ.get("CLAUDECODE") is None


class TestUserLevelExtensionLoading:
    """Test that extensions are loaded from ~/.claude/ in addition to project dir."""

    def test_user_skills_loaded_on_startup(self, tmp_path, monkeypatch):
        """Startup should discover skills from ~/.claude/skills/."""
        from starlette.testclient import TestClient

        # Create a user-level skill
        user_claude = tmp_path / "fake_user_claude"
        skill_dir = user_claude / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\ndescription: A test skill\n---\nDo something."
        )

        # Patch ExtensionLoader to use our fake user dir
        original_init = ExtensionLoader.__init__

        def patched_init(self, base_dir, user_dir=None):
            original_init(self, base_dir, user_dir=str(user_claude))

        monkeypatch.setattr(ExtensionLoader, "__init__", patched_init)

        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)

        with TestClient(app) as client:
            resp = client.get("/api/v1/extensions")

        skills = resp.json()["skills"]
        skill_names = [s["name"] for s in skills]
        assert "test-skill" in skill_names

    def test_project_skills_override_user_skills(self, tmp_path, monkeypatch):
        """Project-level skill with same name takes priority over user-level."""
        from starlette.testclient import TestClient

        # User-level skill
        user_claude = tmp_path / "fake_user_claude"
        user_skill = user_claude / "skills" / "dupe-skill"
        user_skill.mkdir(parents=True)
        (user_skill / "SKILL.md").write_text(
            "---\nname: dupe-skill\ndescription: User version\n---\nUser body."
        )

        # Project-level skill with same name
        project_dir = tmp_path / "project"
        proj_skill = project_dir / ".claude" / "skills" / "dupe-skill"
        proj_skill.mkdir(parents=True)
        (proj_skill / "SKILL.md").write_text(
            "---\nname: dupe-skill\ndescription: Project version\n---\nProject body."
        )

        original_init = ExtensionLoader.__init__

        def patched_init(self, base_dir, user_dir=None):
            original_init(self, base_dir, user_dir=str(user_claude))

        monkeypatch.setattr(ExtensionLoader, "__init__", patched_init)

        config_path = write_test_config(
            tmp_path, project_cwd=str(project_dir)
        )
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)

        with TestClient(app) as client:
            resp = client.get("/api/v1/extensions")

        skills = resp.json()["skills"]
        dupe_skills = [s for s in skills if s["name"] == "dupe-skill"]
        assert len(dupe_skills) == 1
        assert dupe_skills[0]["description"] == "Project version"


class TestSDKOptionsConfiguration:
    """Test that SDK options are correctly built for skill execution."""

    def test_bedrock_provider_includes_max_turns(self, tmp_path):
        """BedrockProvider must set max_turns so multi-turn tool use completes."""
        from src.core.config import BedrockConfig, EngineSettings
        from src.core.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            config=BedrockConfig(region="us-east-1"),
            engine=EngineSettings(project_cwd=str(tmp_path)),
        )
        opts = provider._build_options()
        assert opts.max_turns is not None
        assert opts.max_turns >= 10

    def test_bedrock_provider_mcp_servers_correctly_built(self, tmp_path):
        """MCP server config must be correctly translated to SDK options."""
        from src.core.config import BedrockConfig, EngineSettings
        from src.core.models import ExtensionConfig, MCPServerConfig
        from src.core.providers.bedrock import BedrockProvider

        ext_config = ExtensionConfig(
            mcp_servers={
                "github": MCPServerConfig(
                    name="github",
                    command="npx",
                    args=["-y", "server"],
                    env={"TOKEN": "abc"},
                    transport="stdio",
                )
            }
        )
        provider = BedrockProvider(
            config=BedrockConfig(region="us-east-1"),
            engine=EngineSettings(project_cwd=str(tmp_path)),
            extension_config=ext_config,
        )
        opts = provider._build_options()
        assert isinstance(opts.mcp_servers, dict)
        assert "github" in opts.mcp_servers
        server = opts.mcp_servers["github"]
        assert server["command"] == "npx"
        assert server["args"] == ["-y", "server"]
        assert server["env"] == {"TOKEN": "abc"}

    def test_bedrock_provider_permission_mode_bypass(self, tmp_path):
        """SDK must use bypassPermissions for headless service operation."""
        from src.core.config import BedrockConfig, EngineSettings
        from src.core.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            config=BedrockConfig(region="us-east-1"),
            engine=EngineSettings(project_cwd=str(tmp_path)),
        )
        opts = provider._build_options()
        assert opts.permission_mode == "bypassPermissions"

    def test_npm_available_in_environment(self):
        """npm must be available in PATH for skills that require it."""
        import shutil
        npm_path = shutil.which("npm")
        assert npm_path is not None, "npm not found in PATH; skills requiring npm will fail"


class TestRouterRegistration:
    @pytest.mark.asyncio
    async def test_liveness_probe_always_available(self, tmp_path):
        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_routers_registered_on_app(self, tmp_path):
        """Check that routes are registered (by inspecting app.routes)."""
        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/v1/chat/completions" in route_paths
        assert "/api/v1/sessions" in route_paths
        assert "/api/v1/health/ready" in route_paths
        assert "/api/v1/extensions" in route_paths
        assert "/api/v1/health/live" in route_paths

    @pytest.mark.asyncio
    async def test_agui_not_registered_phase1a(self, tmp_path):
        """AG-UI router should NOT be registered in Phase 1a."""
        config_path = write_test_config(tmp_path)
        app = create_app(client_factory=_good_factory, skip_prewarm=True, config_path=config_path)
        route_paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/agent/run" not in route_paths
