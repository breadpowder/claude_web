"""Extension listing REST endpoint (TASK-008)."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1", tags=["extensions"])


@router.get("/extensions")
async def list_extensions(request: Request):
    """List all loaded extensions with enriched metadata."""
    extension_config = request.app.state.extension_config

    mcp_servers = []
    for name, server in extension_config.mcp_servers.items():
        mcp_servers.append({
            "name": name,
            "description": server.description,
            "transport": server.transport,
            "status": "configured",
            "tool_count": None,
        })

    skills = [asdict(s) for s in extension_config.skills]
    commands = [asdict(c) for c in extension_config.commands]

    all_slash_commands = []
    for skill in extension_config.skills:
        all_slash_commands.append({
            "name": skill.name,
            "description": skill.description,
            "type": skill.type,
            "invoke_prefix": skill.invoke_prefix,
        })
    for cmd in extension_config.commands:
        all_slash_commands.append({
            "name": cmd.name,
            "description": cmd.description,
            "type": cmd.type,
            "invoke_prefix": cmd.invoke_prefix,
        })

    total_count = len(mcp_servers) + len(skills) + len(commands)

    return {
        "mcp_servers": mcp_servers,
        "skills": skills,
        "commands": commands,
        "all_slash_commands": all_slash_commands,
        "total_count": total_count,
    }
