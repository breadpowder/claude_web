"""Claude Code SDK client wrapper (bridges SDK types to internal dict events)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, AsyncGenerator

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class SDKClient:
    """Wraps a Claude Code SDK bidirectional client.

    Uses ``ClaudeSDKClient`` (streaming mode) so the subprocess is spawned
    once at ``connect()`` time and kept alive for subsequent queries.  This
    is the key to real pre-warming: the factory calls ``connect()`` so the
    pool holds clients whose subprocess is already running.
    """

    def __init__(self, options: ClaudeCodeOptions):
        self._options = options
        self._client = ClaudeSDKClient(options)
        self._sdk_session_id: str | None = None

    async def connect(self) -> None:
        """Spawn the underlying subprocess (no prompt sent yet)."""
        await self._client.connect()
        logger.debug("SDKClient connected (subprocess spawned)")

    async def query(self, prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        """Send *prompt* and yield dict events until the response completes."""
        await self._client.query(prompt)
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    event = _content_block_to_event(block)
                    if event is not None:
                        yield event
            elif isinstance(message, ResultMessage):
                # Capture SDK session id for future resume
                self._sdk_session_id = message.session_id

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

    async def interrupt(self) -> None:
        """Send interrupt signal to the subprocess."""
        await self._client.interrupt()

    async def close(self) -> None:
        """Disconnect and terminate the subprocess."""
        await self._client.disconnect()
        logger.debug("SDKClient disconnected")

    @property
    def session_id(self) -> str | None:
        """SDK-assigned session id (available after the first query completes)."""
        return self._sdk_session_id

    @property
    def pid(self) -> int | None:
        """PID of the underlying subprocess, or None if not connected."""
        transport = getattr(self._client, "_transport", None)
        if transport is None:
            return None
        process = getattr(transport, "_process", None)
        if process is None:
            return None
        return getattr(process, "pid", None)


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
                # ContentBlock list -- extract text parts
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


def build_sdk_options(
    settings, extension_config=None, *, resume: str | None = None
) -> ClaudeCodeOptions:
    """Build ClaudeCodeOptions from app Settings and extension config.

    Args:
        settings: Application settings.
        extension_config: Optional extension configuration with MCP servers.
        resume: Optional SDK session id to resume a previous conversation.
    """
    opts: dict[str, Any] = {
        "permission_mode": "bypassPermissions",
        "cwd": settings.project_cwd,
        "max_turns": 30,
    }

    if settings.anthropic_model:
        opts["model"] = settings.anthropic_model

    if resume:
        opts["resume"] = resume

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
    """Return an async factory callable that creates *connected* SDKClient instances.

    The returned clients have a live subprocess ready for queries -- this is
    what makes the pre-warm pool effective.
    """
    sdk_options = build_sdk_options(settings, extension_config)

    async def factory() -> SDKClient:
        client = SDKClient(sdk_options)
        await client.connect()
        return client

    return factory


def create_resume_client_factory(settings, extension_config=None):
    """Return an async callable that creates a *connected* SDKClient with resume.

    Usage::

        factory = create_resume_client_factory(settings, ext_cfg)
        client = await factory(old_sdk_session_id)
    """

    async def factory(resume_session_id: str) -> SDKClient:
        opts = build_sdk_options(
            settings, extension_config, resume=resume_session_id
        )
        client = SDKClient(opts)
        await client.connect()
        return client

    return factory
