"""Filesystem scanner for MCP servers, skills, and commands (TASK-003)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.core.logging_config import get_logger
from src.core.models import CommandInfo, ExtensionConfig, MCPServerConfig, SkillInfo

logger = get_logger(__name__)

BLOCKED_ENV_VARS = frozenset({
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "PATH",
    "PYTHONPATH",
    "NODE_PATH",
})

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_KV_RE = re.compile(r"^(\w+)\s*:\s*(.+)$", re.MULTILINE)
_DESCRIPTION_COMMENT_RE = re.compile(r"^#\s*Description:\s*(.+)$", re.MULTILINE)


class ExtensionLoader:
    """Discovers MCP servers, skills, and commands relative to a project directory."""

    def __init__(self, base_dir: str):
        self._base_dir = base_dir
        self._skill_paths: dict[str, str] = {}

    def scan(self) -> ExtensionConfig:
        """Scan the project directory for extensions. Returns ExtensionConfig."""
        config = ExtensionConfig()
        self._skill_paths.clear()

        self._scan_mcp_json(config)
        self._scan_skills(config)
        self._scan_commands(config)

        return config

    def read_skill_content(self, skill_name: str) -> str:
        """Load the markdown body of a SKILL.md (after YAML frontmatter).

        Returns empty string if skill not found or on read error.
        """
        skill_dir = self._skill_paths.get(skill_name)
        if not skill_dir:
            return ""

        skill_md = os.path.join(skill_dir, "SKILL.md")
        try:
            with open(skill_md, "r") as f:
                content = f.read()
        except (OSError, IOError):
            return ""

        match = _FRONTMATTER_RE.match(content)
        if match:
            return content[match.end():].strip()
        return content.strip()

    def _scan_mcp_json(self, config: ExtensionConfig) -> None:
        """Parse mcp.json if present. Graceful on errors."""
        mcp_path = os.path.join(self._base_dir, "mcp.json")
        if not os.path.exists(mcp_path):
            return

        try:
            with open(mcp_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning("Failed to parse mcp.json: %s", exc)
            return

        servers = data.get("mcpServers", {})
        for name, server_data in servers.items():
            env = server_data.get("env", {})
            sanitized_env = {
                k: v for k, v in env.items() if k not in BLOCKED_ENV_VARS
            }
            config.mcp_servers[name] = MCPServerConfig(
                name=name,
                command=server_data.get("command", ""),
                args=server_data.get("args", []),
                env=sanitized_env,
                transport=server_data.get("transport", "stdio"),
                description=server_data.get("description"),
            )

    def _scan_skills(self, config: ExtensionConfig) -> None:
        """Scan skill directories and extract metadata from SKILL.md."""
        skill_search_dirs = [
            os.path.join(self._base_dir, ".claude", "skills"),
            os.path.join(self._base_dir, "skills"),
        ]

        for search_dir in skill_search_dirs:
            if not os.path.isdir(search_dir):
                continue

            for entry in sorted(os.listdir(search_dir)):
                skill_dir = os.path.join(search_dir, entry)
                if not os.path.isdir(skill_dir):
                    continue

                skill_md = os.path.join(skill_dir, "SKILL.md")
                if not os.path.isfile(skill_md):
                    continue

                # Track for read_skill_content
                self._skill_paths[entry] = skill_dir

                # Use relative path from base_dir for the skill directory path
                rel_path = os.path.relpath(skill_dir, self._base_dir)
                config.skill_directories.append(rel_path)

                name, description = self._extract_skill_metadata(skill_md, entry)
                config.skills.append(
                    SkillInfo(
                        name=name,
                        description=description,
                        path=rel_path,
                        invoke_prefix=f"/{name}",
                    )
                )

    def _extract_skill_metadata(
        self, skill_md_path: str, dir_name: str
    ) -> tuple[str, str]:
        """Extract name and description from SKILL.md YAML frontmatter.

        Returns (name, description). Falls back to dir_name and "(no description)".
        """
        try:
            with open(skill_md_path, "r") as f:
                content = f.read()
        except (OSError, IOError):
            logger.warning("Cannot read SKILL.md at %s", skill_md_path)
            return dir_name, "(no description)"

        match = _FRONTMATTER_RE.match(content)
        if not match:
            logger.warning(
                "No YAML frontmatter found in %s, using fallback metadata",
                skill_md_path,
            )
            return dir_name, "(no description)"

        frontmatter = match.group(1)
        metadata = dict(_YAML_KV_RE.findall(frontmatter))

        name = metadata.get("name", dir_name).strip()
        description = metadata.get("description", "").strip()
        if not description:
            logger.warning(
                "No description in frontmatter for %s, using fallback",
                skill_md_path,
            )
            description = "(no description)"

        return name, description

    def _scan_commands(self, config: ExtensionConfig) -> None:
        """Scan commands directory and extract metadata."""
        commands_dir = os.path.join(self._base_dir, "commands")
        if not os.path.isdir(commands_dir):
            return

        for entry in sorted(os.listdir(commands_dir)):
            cmd_path = os.path.join(commands_dir, entry)
            if not os.path.isfile(cmd_path):
                continue

            rel_path = os.path.relpath(cmd_path, self._base_dir)
            description = self._extract_command_description(cmd_path)

            config.commands.append(
                CommandInfo(
                    name=entry,
                    description=description,
                    path=rel_path,
                    invoke_prefix=f"/{entry}",
                )
            )

    def _extract_command_description(self, cmd_path: str) -> str:
        """Extract description from a command file.

        Checks for companion command.json first, then scans for
        '# Description: ...' comment pattern in the file.
        """
        json_path = cmd_path + ".json"
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r") as f:
                    data = json.load(f)
                desc = data.get("description", "").strip()
                if desc:
                    return desc
            except (json.JSONDecodeError, OSError):
                pass

        try:
            with open(cmd_path, "r") as f:
                content = f.read()
        except (OSError, IOError):
            logger.warning("Cannot read command file %s", cmd_path)
            return "(no description)"

        match = _DESCRIPTION_COMMENT_RE.search(content)
        if match:
            return match.group(1).strip()

        return "(no description)"
