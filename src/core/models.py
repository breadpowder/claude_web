"""Data models for extension configuration (TASK-003)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"
    description: str | None = None


@dataclass
class SkillInfo:
    """Metadata for a discovered skill."""

    name: str
    description: str
    path: str
    invoke_prefix: str
    type: str = "skill"


@dataclass
class CommandInfo:
    """Metadata for a discovered command."""

    name: str
    description: str
    path: str
    invoke_prefix: str
    type: str = "command"
    invoke_method: str = "manual"


@dataclass
class ExtensionConfig:
    """Aggregated extension configuration from filesystem scan."""

    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    skill_directories: list[str] = field(default_factory=list)
    skills: list[SkillInfo] = field(default_factory=list)
    commands: list[CommandInfo] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
