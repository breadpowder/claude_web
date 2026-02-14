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


def _content_block_to_event(block) -> dict[str, Any] | None:
    """Convert a ContentBlock to the dict format the adapter expects."""
    if isinstance(block, TextBlock):
        return {"type": "text", "content": block.text}
    if isinstance(block, ToolUseBlock):
        return {
            "type": "tool_use",
            "name": block.name,
            "arguments": json.dumps(block.input),
        }
    if isinstance(block, ToolResultBlock):
        return {"type": "tool_result"}
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
