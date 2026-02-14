"""OpenAI format translation adapter (TASK-007)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from src.core.logging_config import get_logger
from src.core.models import ExtensionConfig
from src.core.prompt_expander import ExpandResult, PromptExpander

logger = get_logger(__name__)

UNSUPPORTED_PARAMS = frozenset({
    "temperature", "top_p", "logprobs", "top_logprobs",
    "presence_penalty", "frequency_penalty", "logit_bias",
    "seed", "stop", "response_format",
})


def generate_request_id() -> str:
    """Generate an OpenAI-style request ID."""
    return f"chatcmpl-{uuid.uuid4().hex[:29]}"


def messages_to_prompt(
    messages: list[dict],
    prompt_expander: PromptExpander | None = None,
    extension_config: ExtensionConfig | None = None,
) -> tuple[str, ExpandResult | None]:
    """Convert OpenAI messages array to SDK prompt string.

    Returns (prompt_string, expand_result_or_none).
    """
    if not messages:
        return "", None

    # Build context from message history
    parts = []
    for msg in messages[:-1]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            parts.append(f"[System]: {content}")
        elif role == "assistant":
            parts.append(f"[Assistant]: {content}")
        else:
            parts.append(f"[User]: {content}")

    # Handle the last message (may have slash command)
    last_msg = messages[-1]
    last_content = last_msg.get("content", "")
    expand_result = None

    if prompt_expander and extension_config and last_content.startswith("/"):
        expand_result = prompt_expander.expand(last_content, extension_config)
        last_content = expand_result.expanded_prompt

    if parts:
        parts.append(last_content)
        return "\n\n".join(parts), expand_result
    return last_content, expand_result


def sdk_event_to_chunk(
    event: dict,
    request_id: str,
    tool_call_index: int,
) -> tuple[dict | None, int]:
    """Translate an SDK event to an OpenAI SSE chunk.

    Returns (chunk_dict_or_none, updated_tool_call_index).
    ToolResultBlock events are suppressed (return None).
    """
    event_type = event.get("type", "")

    if event_type == "tool_use":
        chunk = _make_chunk(
            request_id,
            delta={
                "tool_calls": [
                    {
                        "index": tool_call_index,
                        "id": f"call_{uuid.uuid4().hex[:24]}",
                        "type": "function",
                        "function": {
                            "name": event.get("name", ""),
                            "arguments": event.get("arguments", "{}"),
                        },
                    }
                ]
            },
        )
        return chunk, tool_call_index + 1

    if event_type == "tool_result":
        # Suppress tool results from SSE stream
        return None, tool_call_index

    if event_type == "text" or "content" in event:
        content = event.get("content", event.get("text", ""))
        chunk = _make_chunk(
            request_id,
            delta={"content": content},
        )
        return chunk, tool_call_index

    return None, tool_call_index


def make_final_chunk(request_id: str, usage: dict | None = None) -> dict:
    """Create the final SSE chunk with finish_reason=stop."""
    chunk = _make_chunk(request_id, delta={}, finish_reason="stop")
    if usage:
        chunk["usage"] = usage
    else:
        chunk["usage"] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    return chunk


def make_non_streaming_response(
    request_id: str, content: str, usage: dict | None = None
) -> dict:
    """Build a complete non-streaming OpenAI response."""
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "claude-agent",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def format_error(status: int, message: str, error_type: str = "server_error") -> dict:
    """Format an OpenAI-compatible error response."""
    return {
        "error": {
            "message": message,
            "type": error_type,
            "code": status,
        }
    }


def warn_unsupported_params(request_body: dict) -> None:
    """Log warnings for any unsupported parameters in the request."""
    found = [p for p in UNSUPPORTED_PARAMS if p in request_body]
    if found:
        logger.warning("Ignoring unsupported parameters: %s", ", ".join(found))


def _make_chunk(
    request_id: str,
    delta: dict,
    finish_reason: str | None = None,
) -> dict:
    """Build an OpenAI SSE chunk dict."""
    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "claude-agent",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
