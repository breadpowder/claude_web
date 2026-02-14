"""FastAPI application factory with full startup sequence (TASK-001, TASK-009)."""

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
from src.core.config import Settings
from src.core.extension_loader import ExtensionLoader
from src.core.logging_config import get_logger, setup_logging
from src.core.models import ExtensionConfig
from src.core.options_builder import OptionsBuilder
from src.core.prewarm_pool import PreWarmPool
from src.core.prompt_expander import PromptExpander
from src.core.session_index import JSONSessionIndex
from src.core.session_manager import SessionManager
from src.core.subprocess_monitor import SubprocessMonitor

logger = get_logger(__name__)


async def _default_client_factory():
    """Default client factory placeholder. Replaced in production with real SDK client creation."""
    raise NotImplementedError("Real SDK client factory not configured")


def create_app(
    client_factory=None,
    skip_prewarm: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        client_factory: Async callable that returns a ClaudeSDKClient instance.
        skip_prewarm: If True, skip pre-warm pool fill (for testing).
    """
    settings = Settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # --- STARTUP SEQUENCE (architecture.md Section 3.3) ---
        logger.info("Starting Core Engine...")

        # 1. Store settings
        app.state.settings = settings

        # 2. Scan extensions
        extension_loader = ExtensionLoader(settings.project_cwd)
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
        index_dir = settings.session_index_dir.replace("~", str(__import__("pathlib").Path.home()))
        session_index = JSONSessionIndex(index_dir)
        session_index.init()
        app.state.session_index = session_index
        logger.info("Session index initialized at %s", index_dir)

        # 4. Create prompt expander
        prompt_expander = PromptExpander(extension_loader)
        app.state.prompt_expander = prompt_expander

        # 5. Create pre-warm pool and fill
        factory = client_factory or _default_client_factory
        pool = PreWarmPool(
            target_size=settings.prewarm_pool_size,
            client_factory=factory,
        )
        if not skip_prewarm:
            try:
                await pool.fill()
            except RuntimeError as exc:
                logger.critical("Pre-warm pool fill failed: %s", exc)
                raise
        app.state.pool = pool

        # 6. Create subprocess monitor
        monitor = SubprocessMonitor(
            max_rss_mb=settings.max_session_rss_mb,
            max_duration_seconds=settings.max_session_duration_seconds,
        )
        await monitor.start()
        app.state.subprocess_monitor = monitor

        # 7. Create session manager
        session_manager = SessionManager(
            pool=pool,
            session_index=session_index,
            subprocess_monitor=monitor,
            client_factory=factory,
            max_sessions=settings.max_sessions,
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

        logger.info("Core Engine shutdown complete")

    app = FastAPI(
        title="Core Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    origins = [o.strip() for o in settings.cors_origins.split(",")]
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
