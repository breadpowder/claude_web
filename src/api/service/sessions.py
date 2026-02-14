"""Session CRUD REST endpoints (TASK-008)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.exceptions import CapacityError, SessionNotFoundError
from src.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(request: Request):
    """List all session summaries."""
    index = request.app.state.session_index
    sessions = index.list()
    # Sort by last_active_at descending
    sessions.sort(key=lambda s: s.get("last_active_at", ""), reverse=True)
    return {"sessions": sessions}


@router.post("", status_code=201)
async def create_session(request: Request):
    """Create a new session."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    session_manager = request.app.state.session_manager
    resume_id = body.get("resume_session_id")

    try:
        if resume_id:
            result = await session_manager.resume_session(resume_id)
        else:
            result = await session_manager.create_session()
        return result
    except CapacityError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request):
    """Get session detail."""
    index = request.app.state.session_index
    session = index.get(session_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request):
    """Destroy a session."""
    session_manager = request.app.state.session_manager
    try:
        await session_manager.destroy_session(session_id)
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found"},
        )
