"""Application configuration via environment variables (TASK-001)."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings class reading all environment variables.

    Supports two provider modes:
    - Anthropic API: Set ANTHROPIC_API_KEY
    - AWS Bedrock: Set CLAUDE_CODE_USE_BEDROCK=1 + AWS credentials
    """

    # Provider: Anthropic API (direct)
    anthropic_api_key: str = ""

    # Provider: AWS Bedrock
    claude_code_use_bedrock: str = ""
    aws_region: str = ""
    aws_bearer_token_bedrock: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_session_token: str = ""
    aws_profile: str = ""

    # Model override (Bedrock uses different model IDs)
    anthropic_model: str = ""

    # Platform settings
    prewarm_pool_size: int = 2
    max_sessions: int = 10
    max_session_duration_seconds: int = 14400
    max_session_rss_mb: int = 2048
    session_index_dir: str = "~/.claude-web/sessions"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"
    log_level: str = "INFO"
    project_cwd: str = "."

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def use_bedrock(self) -> bool:
        return self.claude_code_use_bedrock == "1"

    @model_validator(mode="after")
    def validate_provider(self) -> Settings:
        if not self.use_bedrock and not self.anthropic_api_key:
            raise ValueError(
                "Either ANTHROPIC_API_KEY or CLAUDE_CODE_USE_BEDROCK=1 (with AWS credentials) must be set. "
                "See .env.example for configuration options."
            )
        if self.use_bedrock and not self.aws_region:
            raise ValueError(
                "AWS_REGION is required when using Bedrock (CLAUDE_CODE_USE_BEDROCK=1)"
            )
        return self
