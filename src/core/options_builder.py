"""OptionsBuilder: merges ExtensionConfig into ClaudeAgentOptions (TASK-003)."""

from __future__ import annotations

from src.core.models import ExtensionConfig


class OptionsBuilder:
    """Stateless builder that produces ClaudeAgentOptions from ExtensionConfig."""

    @staticmethod
    def build(config: ExtensionConfig) -> dict:
        """Build ClaudeAgentOptions dict from extension config and platform defaults."""
        mcp_servers = {}
        for name, server in config.mcp_servers.items():
            mcp_servers[name] = {
                "command": server.command,
                "args": server.args,
                "env": server.env,
                "transport": server.transport,
            }

        return {
            "mcp_servers": mcp_servers,
            "permission_mode": "acceptEdits",
            "max_turns": 20,
            "setting_sources": ["user", "project"],
        }
