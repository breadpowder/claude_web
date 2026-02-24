"""Tests for YAML-based configuration (config.py)."""

from __future__ import annotations

import os
import textwrap

import pytest
from pydantic import ValidationError


class TestLoadConfig:
    """Test raw YAML loading and env-var resolution."""

    def test_load_config_reads_yaml(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("provider: litellm\n")

        from src.core.config import load_config

        raw = load_config(str(cfg))
        assert raw["provider"] == "litellm"

    def test_load_config_resolves_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "sk-secret-123")
        cfg = tmp_path / "config.yaml"
        cfg.write_text("litellm:\n  api_key: ${TEST_API_KEY}\n")

        from src.core.config import load_config

        raw = load_config(str(cfg))
        assert raw["litellm"]["api_key"] == "sk-secret-123"

    def test_load_config_unset_env_resolves_to_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
        cfg = tmp_path / "config.yaml"
        cfg.write_text("bedrock:\n  access_key_id: ${NONEXISTENT_VAR_XYZ}\n")

        from src.core.config import load_config

        raw = load_config(str(cfg))
        assert raw["bedrock"]["access_key_id"] == ""

    def test_load_config_file_not_found(self):
        from src.core.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_nested_env_vars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_REGION", "us-west-2")
        monkeypatch.setenv("MY_KEY", "AKIA1234")
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            textwrap.dedent("""\
            bedrock:
              region: ${MY_REGION}
              access_key_id: ${MY_KEY}
            """)
        )

        from src.core.config import load_config

        raw = load_config(str(cfg))
        assert raw["bedrock"]["region"] == "us-west-2"
        assert raw["bedrock"]["access_key_id"] == "AKIA1234"


class TestLoadEngineConfig:
    """Test full config loading with validation."""

    def _write_config(self, tmp_path, content: str, monkeypatch=None):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(textwrap.dedent(content))
        return str(cfg)

    def test_bedrock_defaults(self, tmp_path):
        path = self._write_config(
            tmp_path,
            """\
            provider: bedrock
            bedrock:
              region: us-east-1
            """,
        )

        from src.core.config import load_engine_config

        config = load_engine_config(path)
        assert config.provider == "bedrock"
        assert config.bedrock.region == "us-east-1"
        assert config.engine.prewarm_pool_size == 2
        assert config.engine.max_sessions == 10
        assert config.engine.host == "0.0.0.0"
        assert config.engine.port == 8000

    def test_litellm_valid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "sk-test")
        path = self._write_config(
            tmp_path,
            """\
            provider: litellm
            litellm:
              model: anthropic/claude-sonnet-4-5-20250929
              api_key: ${TEST_KEY}
            """,
        )

        from src.core.config import load_engine_config

        config = load_engine_config(path)
        assert config.provider == "litellm"
        assert config.litellm.api_key == "sk-test"
        assert config.litellm.model == "anthropic/claude-sonnet-4-5-20250929"

    def test_litellm_missing_api_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        path = self._write_config(
            tmp_path,
            """\
            provider: litellm
            litellm:
              model: anthropic/claude-sonnet-4-5-20250929
              api_key: ""
            """,
        )

        from src.core.config import load_engine_config

        with pytest.raises(ValidationError, match="litellm.api_key"):
            load_engine_config(path)

    def test_bedrock_missing_region_raises(self, tmp_path):
        path = self._write_config(
            tmp_path,
            """\
            provider: bedrock
            bedrock:
              region: ""
            """,
        )

        from src.core.config import load_engine_config

        with pytest.raises(ValidationError, match="bedrock.region"):
            load_engine_config(path)

    def test_litellm_extra_params_collected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "sk-test")
        path = self._write_config(
            tmp_path,
            """\
            provider: litellm
            litellm:
              model: anthropic/claude-sonnet-4-5-20250929
              api_key: ${TEST_KEY}
              temperature: 0.7
              max_tokens: 4096
            """,
        )

        from src.core.config import load_engine_config

        config = load_engine_config(path)
        assert config.litellm.extra["temperature"] == 0.7
        assert config.litellm.extra["max_tokens"] == 4096

    def test_engine_settings_override(self, tmp_path):
        path = self._write_config(
            tmp_path,
            """\
            provider: bedrock
            bedrock:
              region: us-west-2
            engine:
              prewarm_pool_size: 5
              max_sessions: 20
              port: 9090
              log_level: DEBUG
            """,
        )

        from src.core.config import load_engine_config

        config = load_engine_config(path)
        assert config.engine.prewarm_pool_size == 5
        assert config.engine.max_sessions == 20
        assert config.engine.port == 9090
        assert config.engine.log_level == "DEBUG"

    def test_invalid_provider_raises(self, tmp_path):
        path = self._write_config(
            tmp_path,
            """\
            provider: openai
            """,
        )

        from src.core.config import load_engine_config

        with pytest.raises(ValidationError):
            load_engine_config(path)
