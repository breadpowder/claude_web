"""Application configuration via environment variables (TASK-001)."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings class reading all environment variables.

    All fields have typed defaults except anthropic_api_key which is required.
    """

    anthropic_api_key: str
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
