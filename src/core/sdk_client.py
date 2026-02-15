"""Claude Code SDK client wrapper (bridges SDK types to internal dict events)."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class SDKClient:
    """Wraps a Claude Code SDK session with the interface SessionManager expects.

    Provides `.query(prompt)` → async generator of dict events compatible
    with the OpenAI adapter's `sdk_event_to_chunk()`.
    """

    def __init__(self, options: ClaudeCodeOptions):
        self._options = options

    async def query(self, prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        """Send prompt to Claude Code CLI and yield dict events."""
        async for message in query(prompt=prompt, options=self._options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    event = _content_block_to_event(block)
                    if event is not None:
                        yield event
            elif isinstance(message, ResultMessage):
                logger.debug(
                    "Query complete: turns=%s, cost=$%.4f",
                    message.num_turns,
                    message.total_cost_usd,
                )
                usage = {}
                if hasattr(message, "usage") and message.usage:
                    if isinstance(message.usage, dict):
                        usage = message.usage
                    else:
                        usage = {
                            "input_tokens": getattr(message.usage, "input_tokens", 0),
                            "output_tokens": getattr(message.usage, "output_tokens", 0),
                        }
                yield {
                    "type": "result_metadata",
                    "num_turns": message.num_turns,
                    "total_cost_usd": message.total_cost_usd,
                    "duration_ms": getattr(message, "duration_ms", 0) or 0,
                    "usage": usage,
                }


def _content_block_to_event(block) -> dict[str, Any] | None:
    """Convert a ContentBlock to the dict format the adapter expects."""
    if isinstance(block, TextBlock):
        return {"type": "text", "content": block.text}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "arguments": json.dumps(block.input),
        }
    if isinstance(block, ToolResultBlock):
        # Forward tool_use_id, content, and is_error for the frontend
        content = ""
        if block.content:
            if isinstance(block.content, str):
                content = block.content
            elif isinstance(block.content, list):
                # ContentBlock list — extract text parts
                parts = []
                for part in block.content:
                    if hasattr(part, "text"):
                        parts.append(part.text)
                    elif isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                content = "\n".join(parts)
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": content,
            "is_error": getattr(block, "is_error", False) or False,
        }
    return None


def build_sdk_options(settings, extension_config=None) -> ClaudeCodeOptions:
    """Build ClaudeCodeOptions from app Settings and extension config."""
    opts: dict[str, Any] = {
        "permission_mode": "bypassPermissions",
        "cwd": settings.project_cwd,
        "max_turns": 30,
    }

    if settings.anthropic_model:
        opts["model"] = settings.anthropic_model

    # MCP servers from extension config
    if extension_config and extension_config.mcp_servers:
        mcp_servers = {}
        for name, server in extension_config.mcp_servers.items():
            mcp_servers[name] = {
                "command": server.command,
                "args": server.args,
                "env": server.env,
            }
        opts["mcp_servers"] = mcp_servers

    return ClaudeCodeOptions(**opts)


def create_client_factory(settings, extension_config=None):
    """Return an async factory callable that creates SDKClient instances."""
    sdk_options = build_sdk_options(settings, extension_config)

    async def factory():
        return SDKClient(sdk_options)

    return factory
