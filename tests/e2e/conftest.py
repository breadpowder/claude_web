"""E2E test fixtures - app created via create_app() with mocked SDK boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_test_config


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test app with mocked SDK components."""
    config_path = write_test_config(
        tmp_path,
        prewarm_pool_size=0,
        max_sessions=3,
    )

    from src.main import create_app

    test_app = create_app(skip_prewarm=True, config_path=config_path)
    yield test_app


@pytest.fixture
def client(app):
    """Create test client."""
    with TestClient(app) as c:
        yield c
