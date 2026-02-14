"""Tests for ExtensionLoader (TASK-003)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.core.extension_loader import ExtensionLoader


@pytest.fixture
def project_dir(tmp_path):
    """Provide a temp directory simulating PROJECT_CWD."""
    return tmp_path


@pytest.fixture
def loader(project_dir):
    return ExtensionLoader(str(project_dir))


class TestScanEmptyDirectory:
    def test_scan_empty_directory(self, loader):
        config = loader.scan()
        assert config.mcp_servers == {}
        assert config.skill_directories == []
        assert config.skills == []
        assert config.commands == []


class TestScanMCPJson:
    def test_scan_valid_mcp_json(self, loader, project_dir):
        mcp_json = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_TOKEN": "tok"},
                }
            }
        }
        (project_dir / "mcp.json").write_text(json.dumps(mcp_json))

        config = loader.scan()
        assert "github" in config.mcp_servers
        assert config.mcp_servers["github"].command == "npx"
        assert config.mcp_servers["github"].args == [
            "-y",
            "@modelcontextprotocol/server-github",
        ]
        assert config.mcp_servers["github"].env == {"GITHUB_TOKEN": "tok"}
        assert config.mcp_servers["github"].transport == "stdio"

    def test_scan_invalid_mcp_json_graceful(self, loader, project_dir, caplog):
        (project_dir / "mcp.json").write_text("{not valid json")

        config = loader.scan()
        assert config.mcp_servers == {}
        assert any("mcp.json" in r.message.lower() for r in caplog.records)

    def test_scan_sanitizes_env_vars(self, loader, project_dir):
        mcp_json = {
            "mcpServers": {
                "test": {
                    "command": "node",
                    "args": ["server.js"],
                    "env": {
                        "LD_PRELOAD": "/evil.so",
                        "PATH": "/bad",
                        "PYTHONPATH": "/bad",
                        "NODE_PATH": "/bad",
                        "SAFE_VAR": "ok",
                    },
                }
            }
        }
        (project_dir / "mcp.json").write_text(json.dumps(mcp_json))

        config = loader.scan()
        sanitized_env = config.mcp_servers["test"].env
        assert "LD_PRELOAD" not in sanitized_env
        assert "PATH" not in sanitized_env
        assert "PYTHONPATH" not in sanitized_env
        assert "NODE_PATH" not in sanitized_env
        assert sanitized_env["SAFE_VAR"] == "ok"

    def test_mcp_server_optional_description(self, loader, project_dir):
        mcp_json = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "server"],
                    "description": "GitHub integration via MCP",
                }
            }
        }
        (project_dir / "mcp.json").write_text(json.dumps(mcp_json))

        config = loader.scan()
        assert config.mcp_servers["github"].description == "GitHub integration via MCP"


class TestScanSkills:
    def test_scan_discovers_skills(self, loader, project_dir):
        skill_dir = project_dir / ".claude" / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: code-review\ndescription: Review code\n---\nInstructions."
        )

        config = loader.scan()
        assert len(config.skill_directories) == 1
        assert config.skill_directories[0].endswith("skills/code-review")

    def test_scan_extracts_skill_metadata(self, loader, project_dir):
        skill_dir = project_dir / ".claude" / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: code-review\ndescription: Review code for quality and best practices\n---\nInstructions here."
        )

        config = loader.scan()
        assert len(config.skills) == 1
        assert config.skills[0].name == "code-review"
        assert (
            config.skills[0].description
            == "Review code for quality and best practices"
        )
        assert config.skills[0].invoke_prefix == "/code-review"
        assert config.skills[0].type == "skill"

    def test_scan_skill_no_frontmatter_uses_fallback(
        self, loader, project_dir, caplog
    ):
        skill_dir = project_dir / ".claude" / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Just some markdown content, no frontmatter.")

        config = loader.scan()
        assert len(config.skills) == 1
        assert config.skills[0].name == "code-review"
        assert config.skills[0].description == "(no description)"
        assert any("frontmatter" in r.message.lower() for r in caplog.records)


class TestScanCommands:
    def test_scan_extracts_command_metadata(self, loader, project_dir):
        cmd_dir = project_dir / "commands"
        cmd_dir.mkdir(parents=True)
        (cmd_dir / "deploy").write_text(
            "#!/bin/bash\n# Description: Deploy to staging environment\necho deploy"
        )

        config = loader.scan()
        assert len(config.commands) == 1
        assert config.commands[0].name == "deploy"
        assert config.commands[0].description == "Deploy to staging environment"
        assert config.commands[0].invoke_prefix == "/deploy"
        assert config.commands[0].type == "command"
        assert config.commands[0].invoke_method == "manual"


class TestReadSkillContent:
    def test_read_skill_content_returns_body(self, loader, project_dir):
        skill_dir = project_dir / ".claude" / "skills" / "code-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: code-review\ndescription: desc\n---\n## Instructions\nReview the code carefully."
        )
        # Must scan first to populate skill paths
        loader.scan()

        result = loader.read_skill_content("code-review")
        assert "## Instructions" in result
        assert "Review the code carefully." in result
        assert "---" not in result
        assert "name: code-review" not in result

    def test_read_skill_content_missing_skill(self, loader, project_dir):
        loader.scan()
        result = loader.read_skill_content("nonexistent")
        assert result == ""
