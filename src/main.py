"""FastAPI application factory with full startup sequence."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.openai.endpoint import router as openai_router
from src.api.service.extensions import router as extensions_router
from src.api.service.health import router as health_router
from src.api.service.sessions import router as sessions_router
from src.core.config import load_engine_config
from src.core.extension_loader import ExtensionLoader
from src.core.logging_config import get_logger, setup_logging
from src.core.prewarm_pool import PreWarmPool
from src.core.prompt_expander import PromptExpander
from src.core.provider_factory import create_provider_factory, create_resume_provider_factory
from src.core.session_index import JSONSessionIndex
from src.core.session_manager import SessionManager
from src.core.subprocess_monitor import SubprocessMonitor

logger = get_logger(__name__)


def create_app(
    client_factory=None,
    skip_prewarm: bool = False,
    config_path: str = "config.yaml",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        client_factory: Async callable that returns a provider instance
            (overrides the config-driven factory — useful for testing).
        skip_prewarm: If True, skip pre-warm pool fill (for testing).
        config_path: Path to the YAML configuration file.
    """
    config = load_engine_config(config_path)
    setup_logging(config.engine.log_level)

    # Prevent "cannot be launched inside another Claude Code session" error
    # regardless of which provider is selected.
    os.environ.pop("CLAUDECODE", None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- STARTUP SEQUENCE ---
        logger.info("Starting Core Engine (provider=%s)...", config.provider)

        # 1. Store config
        app.state.config = config

        # 2. Scan extensions
        extension_loader = ExtensionLoader(config.engine.project_cwd)
        extension_config = extension_loader.scan()
        app.state.extension_loader = extension_loader
        app.state.extension_config = extension_config
        logger.info(
            "Extensions scanned: %d MCP servers, %d skills, %d commands",
            len(extension_config.mcp_servers),
            len(extension_config.skills),
            len(extension_config.commands),
        )

        # 3. Init session index
        index_dir = config.engine.session_index_dir.replace(
            "~", str(__import__("pathlib").Path.home())
        )
        session_index = JSONSessionIndex(index_dir)
        session_index.init()
        app.state.session_index = session_index
        logger.info("Session index initialized at %s", index_dir)

        # 4. Create prompt expander
        prompt_expander = PromptExpander(extension_loader)
        app.state.prompt_expander = prompt_expander

        # 5. Create pre-warm pool and fill
        factory = client_factory or create_provider_factory(config, extension_config)

        # LiteLLM is in-process — no benefit from pre-warming
        pool_size = config.engine.prewarm_pool_size
        if config.provider == "litellm":
            pool_size = 0

        pool = PreWarmPool(target_size=pool_size, client_factory=factory)
        if not skip_prewarm:
            try:
                await pool.fill()
            except RuntimeError as exc:
                logger.critical("Pre-warm pool fill failed: %s", exc)
                raise
        app.state.pool = pool

        # 6. Create subprocess monitor
        monitor = SubprocessMonitor(
            max_rss_mb=config.engine.max_session_rss_mb,
            max_duration_seconds=config.engine.max_session_duration_seconds,
        )
        await monitor.start()
        app.state.subprocess_monitor = monitor

        # 7. Create session manager
        resume_factory = create_resume_provider_factory(config, extension_config)
        session_manager = SessionManager(
            pool=pool,
            session_index=session_index,
            subprocess_monitor=monitor,
            client_factory=factory,
            max_sessions=config.engine.max_sessions,
            resume_client_factory=resume_factory,
        )
        app.state.session_manager = session_manager

        logger.info("Core Engine started successfully")

        yield

        # --- SHUTDOWN SEQUENCE ---
        logger.info("Shutting down Core Engine...")

        # Stop monitor
        await monitor.stop()

        # Destroy active sessions
        for session_id in list(session_manager._sessions.keys()):
            try:
                await session_manager.destroy_session(session_id)
            except Exception as exc:
                logger.warning("Error destroying session %s: %s", session_id, exc)

        # Drain unused pre-warmed clients (terminates their subprocesses)
        await pool.drain()

        logger.info("Core Engine shutdown complete")

    app = FastAPI(
        title="Core Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    origins = [o.strip() for o in config.engine.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Liveness probe (available immediately, no dependencies)
    @app.get("/api/v1/health/live")
    async def health_live():
        return {"status": "ok"}

    # Register routers
    app.include_router(openai_router)
    app.include_router(sessions_router)
    app.include_router(health_router)
    app.include_router(extensions_router)

    # Serve built frontend SPA (after all API routes so /api/* takes priority)
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def get_app() -> FastAPI:
    """Factory function for uvicorn --factory mode."""
    return create_app()
