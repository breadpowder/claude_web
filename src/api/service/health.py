"""Health check REST endpoints (TASK-008)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/ready")
async def readiness_probe(request: Request):
    """Readiness probe with pool and session metrics."""
    pool = request.app.state.pool
    session_manager = request.app.state.session_manager
    settings = request.app.state.settings

    pool_depth = pool.size()
    active_sessions = session_manager.active_session_count()
    max_sessions = settings.max_sessions

    if pool_depth == 0:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "pool_depth": pool_depth,
                "active_sessions": active_sessions,
                "max_sessions": max_sessions,
                "reason": "Pool empty",
            },
        )

    return {
        "status": "ready",
        "pool_depth": pool_depth,
        "active_sessions": active_sessions,
        "max_sessions": max_sessions,
    }
