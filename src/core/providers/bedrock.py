"""Bedrock provider — wraps SDKClient for AWS Bedrock via claude-code-sdk."""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from claude_code_sdk import ClaudeCodeOptions

from src.core.config import BedrockConfig, EngineSettings
from src.core.llm_provider import LLMProvider
from src.core.logging_config import get_logger
from src.core.models import ExtensionConfig
from src.core.sdk_client import SDKClient

logger = get_logger(__name__)


class BedrockProvider(LLMProvider):
    """LLM provider backed by AWS Bedrock via claude-code-sdk subprocess.

    Credentials are propagated to ``os.environ`` at :meth:`connect` time so
    the SDK subprocess inherits them.
    """

    def __init__(
        self,
        config: BedrockConfig,
        engine: EngineSettings,
        extension_config: ExtensionConfig | None = None,
        resume_session_id: str | None = None,
    ):
        self._config = config
        self._engine = engine
        self._extension_config = extension_config
        self._resume_session_id = resume_session_id
        self._client: SDKClient | None = None

    # -- LLMProvider interface ------------------------------------------------

    async def connect(self) -> None:
        self._propagate_env()
        options = self._build_options()
        self._client = SDKClient(options)
        await self._client.connect()

    async def query(self, prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        if self._client is None:
            raise RuntimeError("BedrockProvider is not connected")
        async for event in self._client.query(prompt):
            yield event

    async def interrupt(self) -> None:
        if self._client is not None:
            await self._client.interrupt()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    @property
    def session_id(self) -> str | None:
        return self._client.session_id if self._client else None

    @property
    def pid(self) -> int | None:
        return self._client.pid if self._client else None

    # -- Internal helpers -----------------------------------------------------

    def _propagate_env(self) -> None:
        """Push Bedrock credentials into ``os.environ`` for SDK subprocesses."""
        env_map = {
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "AWS_REGION": self._config.region,
            "AWS_ACCESS_KEY_ID": self._config.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self._config.secret_access_key,
            "AWS_SESSION_TOKEN": self._config.session_token,
            "AWS_PROFILE": self._config.profile,
            "AWS_BEARER_TOKEN_BEDROCK": self._config.bearer_token,
        }
        for key, value in env_map.items():
            if value:
                os.environ.setdefault(key, value)

        # Prevent "cannot be launched inside another Claude Code session"
        os.environ.pop("CLAUDECODE", None)

    def _build_options(self) -> ClaudeCodeOptions:
        opts: dict[str, Any] = {
            "permission_mode": "bypassPermissions",
            "cwd": self._engine.project_cwd,
            "max_turns": 30,
        }

        if self._config.model:
            opts["model"] = self._config.model

        if self._resume_session_id:
            opts["resume"] = self._resume_session_id

        # MCP servers from extension config
        if self._extension_config and self._extension_config.mcp_servers:
            mcp_servers = {}
            for name, server in self._extension_config.mcp_servers.items():
                mcp_servers[name] = {
                    "command": server.command,
                    "args": server.args,
                    "env": server.env,
                }
            opts["mcp_servers"] = mcp_servers

        return ClaudeCodeOptions(**opts)
