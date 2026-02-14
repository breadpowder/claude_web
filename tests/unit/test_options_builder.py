"""Tests for OptionsBuilder (TASK-003)."""

from __future__ import annotations

import pytest

from src.core.models import ExtensionConfig, MCPServerConfig
from src.core.options_builder import OptionsBuilder


class TestOptionsBuilder:
    def test_options_builder_produces_options(self):
        config = ExtensionConfig(
            mcp_servers={
                "github": MCPServerConfig(
                    name="github",
                    command="npx",
                    args=["-y", "server"],
                    env={"GITHUB_TOKEN": "tok"},
                )
            },
            skill_directories=["/path/to/skills/code-review"],
        )

        options = OptionsBuilder.build(config)
        assert "github" in options["mcp_servers"]
        assert options["permission_mode"] == "acceptEdits"
        assert options["max_turns"] == 20
        assert "user" in options["setting_sources"]
        assert "project" in options["setting_sources"]

    def test_options_builder_empty_config(self):
        config = ExtensionConfig()

        options = OptionsBuilder.build(config)
        assert options["mcp_servers"] == {}
        assert options["permission_mode"] == "acceptEdits"
        assert options["max_turns"] == 20
