"""Tests for Settings configuration (TASK-001)."""

import os

import pytest
from pydantic import ValidationError


class TestSettingsDefaults:
    """Test that Settings loads correct defaults."""

    def test_settings_loads_defaults(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        # Clear any other env vars that might interfere
        for key in [
            "PREWARM_POOL_SIZE", "MAX_SESSIONS", "MAX_SESSION_DURATION_SECONDS",
            "MAX_SESSION_RSS_MB", "SESSION_INDEX_DIR", "HOST", "PORT",
            "CORS_ORIGINS", "LOG_LEVEL", "PROJECT_CWD",
        ]:
            monkeypatch.delenv(key, raising=False)

        from src.core.config import Settings
        settings = Settings()

        assert settings.prewarm_pool_size == 2
        assert settings.max_sessions == 10
        assert settings.max_session_duration_seconds == 14400
        assert settings.max_session_rss_mb == 2048
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.cors_origins == "*"
        assert settings.log_level == "INFO"
        assert settings.project_cwd == "."

    def test_settings_requires_provider(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
        monkeypatch.chdir(tmp_path)  # Avoid reading project .env

        from src.core.config import Settings
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)
        assert "anthropic_api_key" in str(exc_info.value).lower() or "bedrock" in str(exc_info.value).lower()

    def test_settings_reads_env_overrides(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("PREWARM_POOL_SIZE", "5")
        monkeypatch.setenv("MAX_SESSIONS", "20")
        monkeypatch.setenv("PORT", "9090")

        from src.core.config import Settings
        settings = Settings()

        assert settings.prewarm_pool_size == 5
        assert isinstance(settings.prewarm_pool_size, int)
        assert settings.max_sessions == 20
        assert settings.port == 9090
