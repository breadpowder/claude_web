"""Prompt expander for skill/command preprocessing (TASK-NEW-001)."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.logging_config import get_logger
from src.core.models import ExtensionConfig

logger = get_logger(__name__)


@dataclass
class ExpandResult:
    """Result of prompt expansion."""

    expanded_prompt: str
    matched_extension: str | None = None
    extension_type: str | None = None


class PromptExpander:
    """Detects /extension-name prefixes and expands with SKILL.md content."""

    def __init__(self, extension_loader):
        self._loader = extension_loader

    def expand(self, message: str, config: ExtensionConfig) -> ExpandResult:
        """Expand a user message if it starts with a known /extension-name prefix.

        Returns ExpandResult with the expanded prompt and match metadata.
        """
        if not message.startswith("/") or len(message.strip()) <= 1:
            return ExpandResult(expanded_prompt=message)

        # Parse the first token as extension name
        parts = message[1:].split(None, 1)
        ext_name = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if not ext_name:
            return ExpandResult(expanded_prompt=message)

        # Check skills
        skill_names = {s.name for s in config.skills}
        if ext_name in skill_names:
            content = self._loader.read_skill_content(ext_name)
            if not content:
                logger.warning(
                    "Empty skill content for '%s', fallback to original message",
                    ext_name,
                )
                return ExpandResult(expanded_prompt=message)

            expanded = f"{content}\n\nUser request: {rest}"
            return ExpandResult(
                expanded_prompt=expanded,
                matched_extension=ext_name,
                extension_type="skill",
            )

        # Check commands
        command_names = {c.name for c in config.commands}
        if ext_name in command_names:
            logger.warning(
                "Command execution unsupported in Phase 1a: /%s",
                ext_name,
            )
            return ExpandResult(
                expanded_prompt=message,
                matched_extension=ext_name,
                extension_type="command",
            )

        # Unrecognized prefix - passthrough
        return ExpandResult(expanded_prompt=message)
