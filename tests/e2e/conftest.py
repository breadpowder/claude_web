"""E2E test fixtures - app created via create_app() with mocked SDK boundary."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test app with mocked SDK components."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-e2e")
    monkeypatch.setenv("MAX_SESSIONS", "3")
    monkeypatch.setenv("PREWARM_POOL_SIZE", "0")
    monkeypatch.setenv("PROJECT_CWD", str(tmp_path / "project"))
    monkeypatch.setenv("SESSION_INDEX_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    (tmp_path / "project").mkdir(exist_ok=True)

    from src.main import create_app

    test_app = create_app(skip_prewarm=True)
    yield test_app


@pytest.fixture
def client(app):
    """Create test client."""
    with TestClient(app) as c:
        yield c
