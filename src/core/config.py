"""Application configuration loaded from config.yaml."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, model_validator

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in string values.

    Empty env vars resolve to empty string (not the literal ``${VAR}``).
    """
    if isinstance(value, str):

        def _replacer(match: re.Match) -> str:
            return os.environ.get(match.group(1), "")

        return _ENV_VAR_PATTERN.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def load_config(path: str = "config.yaml") -> dict:
    """Read a YAML config file and resolve ``${ENV_VAR}`` references.

    Returns the raw (resolved) dict — call :func:`load_engine_config` for a
    validated :class:`EngineConfig` instance.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with open(config_path) as fh:
        raw = yaml.safe_load(fh) or {}

    return _resolve_env_vars(raw)


def load_engine_config(path: str = "config.yaml") -> EngineConfig:
    """Load, pre-process, and validate configuration from a YAML file.

    LiteLLM pass-through parameters (anything besides ``model``,
    ``api_key``, ``api_base``) are collected into
    :pyattr:`LiteLLMConfig.extra`.
    """
    raw = load_config(path)

    # Separate known litellm keys from pass-through params
    litellm_section = raw.get("litellm")
    if isinstance(litellm_section, dict):
        known_keys = {"model", "api_key", "api_base"}
        extra = {k: v for k, v in litellm_section.items() if k not in known_keys}
        clean = {k: v for k, v in litellm_section.items() if k in known_keys}
        if extra:
            clean["extra"] = extra
        raw["litellm"] = clean

    return EngineConfig(**raw)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class BedrockConfig(BaseModel):
    """AWS Bedrock provider configuration."""

    model: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    region: str = "us-east-1"
    # Auth method 1: Access keys
    access_key_id: str = ""
    secret_access_key: str = ""
    session_token: str = ""
    # Auth method 2: Profile
    profile: str = ""
    # Auth method 3: Bearer token
    bearer_token: str = ""


class LiteLLMConfig(BaseModel):
    """LiteLLM provider configuration.

    ``extra`` holds pass-through kwargs forwarded to
    ``litellm.acompletion()`` (e.g. ``temperature``, ``max_tokens``).
    """

    model: str = "anthropic/claude-sonnet-4-5-20250929"
    api_key: str = ""
    api_base: str = ""
    extra: dict = {}


class EngineSettings(BaseModel):
    """Platform / engine settings."""

    prewarm_pool_size: int = 2
    max_sessions: int = 10
    max_session_duration_seconds: int = 3600
    max_session_rss_mb: int = 512
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    log_level: str = "INFO"
    project_cwd: str = "."
    session_index_dir: str = "~/.claude-web/sessions"


class EngineConfig(BaseModel):
    """Root configuration — built from ``config.yaml``."""

    provider: Literal["bedrock", "litellm"] = "bedrock"
    bedrock: BedrockConfig = BedrockConfig()
    litellm: LiteLLMConfig = LiteLLMConfig()
    engine: EngineSettings = EngineSettings()

    @model_validator(mode="after")
    def validate_provider_config(self) -> EngineConfig:
        if self.provider == "bedrock":
            if not self.bedrock.region:
                raise ValueError(
                    "bedrock.region is required when provider is 'bedrock'"
                )
        elif self.provider == "litellm":
            if not self.litellm.api_key:
                raise ValueError(
                    "litellm.api_key is required when provider is 'litellm'"
                )
        return self
