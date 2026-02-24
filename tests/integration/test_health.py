"""Tests for health endpoints and CORS."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import write_test_config


@pytest.fixture
def client(tmp_path):
    config_path = write_test_config(tmp_path)

    from src.main import create_app
    app = create_app(config_path=config_path)
    return TestClient(app)


class TestHealthEndpoints:
    """Test health and liveness probes."""

    def test_health_live_endpoint(self, client):
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCORS:
    """Test CORS middleware configuration."""

    def test_cors_middleware_configured(self, tmp_path):
        config_path = write_test_config(
            tmp_path, cors_origins="http://localhost:3000"
        )

        from src.main import create_app
        app = create_app(config_path=config_path)
        test_client = TestClient(app)

        response = test_client.options(
            "/api/v1/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
