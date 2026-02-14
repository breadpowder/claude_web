"""Tests for PromptExpander (TASK-NEW-001)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.models import CommandInfo, ExtensionConfig, SkillInfo
from src.core.prompt_expander import PromptExpander


@pytest.fixture
def loader():
    """Fake ExtensionLoader with read_skill_content method."""
    mock = MagicMock()
    mock.read_skill_content.return_value = "## Instructions\nReview code carefully."
    return mock


@pytest.fixture
def config_with_skill():
    return ExtensionConfig(
        skills=[
            SkillInfo(
                name="code-review",
                description="Review code",
                path=".claude/skills/code-review",
                invoke_prefix="/code-review",
            )
        ]
    )


@pytest.fixture
def config_with_command():
    return ExtensionConfig(
        commands=[
            CommandInfo(
                name="deploy",
                description="Deploy to staging",
                path="commands/deploy",
                invoke_prefix="/deploy",
            )
        ]
    )


class TestExpandKnownSkill:
    def test_expand_known_skill(self, loader, config_with_skill):
        expander = PromptExpander(loader)
        result = expander.expand("/code-review review this function", config_with_skill)

        assert "## Instructions" in result.expanded_prompt
        assert "Review code carefully." in result.expanded_prompt
        assert "User request: review this function" in result.expanded_prompt
        assert "/code-review" not in result.expanded_prompt
        assert result.matched_extension == "code-review"
        assert result.extension_type == "skill"

    def test_expand_skill_with_only_name_no_args(self, loader, config_with_skill):
        expander = PromptExpander(loader)
        result = expander.expand("/code-review", config_with_skill)

        assert "## Instructions" in result.expanded_prompt
        assert "User request:" in result.expanded_prompt
        assert result.matched_extension == "code-review"


class TestExpandPassthrough:
    def test_expand_unrecognized_prefix(self, loader):
        config = ExtensionConfig()
        expander = PromptExpander(loader)
        result = expander.expand("/nonexistent do something", config)

        assert result.expanded_prompt == "/nonexistent do something"
        assert result.matched_extension is None
        assert result.extension_type is None

    def test_expand_no_slash_prefix(self, loader, config_with_skill):
        expander = PromptExpander(loader)
        result = expander.expand("explain this code", config_with_skill)

        assert result.expanded_prompt == "explain this code"
        assert result.matched_extension is None
        assert result.extension_type is None

    def test_expand_slash_only_message(self, loader, config_with_skill):
        expander = PromptExpander(loader)
        result = expander.expand("/", config_with_skill)

        assert result.expanded_prompt == "/"
        assert result.matched_extension is None


class TestExpandCommand:
    def test_expand_known_command_logs_warning(self, loader, config_with_command, caplog):
        expander = PromptExpander(loader)
        result = expander.expand("/deploy to staging", config_with_command)

        assert result.expanded_prompt == "/deploy to staging"
        assert result.matched_extension == "deploy"
        assert result.extension_type == "command"
        assert any("unsupported" in r.message.lower() or "command" in r.message.lower() for r in caplog.records)


class TestExpandFallback:
    def test_expand_empty_skill_content_fallback(self, config_with_skill, caplog):
        loader = MagicMock()
        loader.read_skill_content.return_value = ""

        expander = PromptExpander(loader)
        result = expander.expand("/code-review do stuff", config_with_skill)

        assert result.expanded_prompt == "/code-review do stuff"
        assert any("empty" in r.message.lower() or "fallback" in r.message.lower() for r in caplog.records)
