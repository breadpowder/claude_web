"""FastAPI application factory (TASK-001)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import Settings
from src.core.logging_config import setup_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: components will be wired here in TASK-009
        app.state.settings = settings
        yield
        # Shutdown: cleanup will be wired here in TASK-009

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

    return app


app = create_app()
