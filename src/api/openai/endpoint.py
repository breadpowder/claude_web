"""OpenAI-compliant chat completions endpoint (TASK-007)."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from src.api.openai.adapter import (
    format_error,
    generate_request_id,
    make_final_chunk,
    make_non_streaming_response,
    messages_to_prompt,
    sdk_event_to_chunk,
    warn_unsupported_params,
)
from src.core.exceptions import CapacityError
from src.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    """OpenAI-compatible chat completions endpoint."""
    body = await request.json()

    # Validate required fields
    if "model" not in body:
        return JSONResponse(
            status_code=400,
            content=format_error(400, "model is required", "invalid_request"),
        )

    messages = body.get("messages", [])
    if not messages:
        return JSONResponse(
            status_code=400,
            content=format_error(400, "messages is required", "invalid_request"),
        )

    stream = body.get("stream", False)
    warn_unsupported_params(body)

    session_manager = request.app.state.session_manager
    prompt_expander = getattr(request.app.state, "prompt_expander", None)
    extension_config = getattr(request.app.state, "extension_config", None)

    # Acquire session
    try:
        session_id, _ = await session_manager.acquire_session()
    except CapacityError:
        resp = JSONResponse(
            status_code=503,
            content=format_error(503, "Service temporarily at capacity. Retry in 30 seconds."),
        )
        resp.headers["Retry-After"] = "30"
        return resp

    request_id = generate_request_id()

    # Convert messages to prompt
    prompt, _ = messages_to_prompt(
        messages,
        prompt_expander=prompt_expander,
        extension_config=extension_config,
    )

    if stream:
        return EventSourceResponse(
            _stream_response(
                session_manager, session_id, prompt, request_id,
            ),
            media_type="text/event-stream",
        )
    else:
        return await _non_streaming_response(
            session_manager, session_id, prompt, request_id,
        )


async def _stream_response(
    session_manager,
    session_id: str,
    prompt: str,
    request_id: str,
) -> AsyncGenerator[dict, None]:
    """Generate SSE events for streaming response."""
    tool_call_index = 0
    try:
        async for event in session_manager.query(session_id, prompt):
            chunk, tool_call_index = sdk_event_to_chunk(
                event, request_id, tool_call_index
            )
            if chunk is not None:
                yield {"data": json.dumps(chunk)}

        # Final chunk
        final = make_final_chunk(request_id)
        yield {"data": json.dumps(final)}

    except Exception as exc:
        logger.error("Stream error for session %s: %s", session_id, exc)
        error_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
            "error": {
                "type": "server_error",
                "message": f"Session terminated: {exc}",
            },
        }
        yield {"data": json.dumps(error_chunk)}
    finally:
        yield {"data": "[DONE]"}
        await session_manager.release_session(session_id)


async def _non_streaming_response(
    session_manager,
    session_id: str,
    prompt: str,
    request_id: str,
) -> JSONResponse:
    """Buffer response and return single JSON."""
    content_parts = []
    try:
        async for event in session_manager.query(session_id, prompt):
            if "content" in event:
                content_parts.append(event["content"])
            elif event.get("type") == "text":
                content_parts.append(event.get("content", event.get("text", "")))

        content = "".join(content_parts)
        return JSONResponse(
            content=make_non_streaming_response(request_id, content)
        )
    except Exception as exc:
        logger.error("Query error for session %s: %s", session_id, exc)
        return JSONResponse(
            status_code=500,
            content=format_error(500, str(exc)),
        )
    finally:
        await session_manager.release_session(session_id)
