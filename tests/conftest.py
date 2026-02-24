"""Shared test fixtures — provides helpers for config.yaml-based testing."""

from __future__ import annotations

import yaml


def write_test_config(
    tmp_path,
    *,
    provider: str = "bedrock",
    project_cwd: str | None = None,
    session_index_dir: str | None = None,
    prewarm_pool_size: int = 0,
    max_sessions: int = 10,
    log_level: str = "WARNING",
    cors_origins: str = "*",
    bedrock_region: str = "us-east-1",
    litellm_api_key: str = "test-key",
    **engine_overrides,
) -> str:
    """Write a temporary ``config.yaml`` and return its path.

    Callers can override any engine setting via keyword arguments.
    """
    engine = {
        "prewarm_pool_size": prewarm_pool_size,
        "max_sessions": max_sessions,
        "host": "0.0.0.0",
        "port": 8000,
        "cors_origins": cors_origins,
        "log_level": log_level,
        "project_cwd": project_cwd or str(tmp_path / "project"),
        "session_index_dir": session_index_dir or str(tmp_path / "sessions"),
    }
    engine.update(engine_overrides)

    config = {
        "provider": provider,
        "bedrock": {"region": bedrock_region},
        "litellm": {"model": "anthropic/claude-sonnet-4-5-20250929", "api_key": litellm_api_key},
        "engine": engine,
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config, default_flow_style=False))

    # Ensure the project directory exists
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)

    return str(config_path)
