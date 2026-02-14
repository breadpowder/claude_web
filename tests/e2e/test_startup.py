"""E2E tests for application startup (TASK-012)."""

from __future__ import annotations


class TestAppStartup:
    """Verify the app starts and health endpoints respond."""

    def test_app_starts_without_errors(self, client):
        """The app fixture creates the app; if we get here it started."""
        assert client is not None

    def test_liveness_probe_returns_200(self, client):
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_readiness_probe_returns_200_or_503(self, client):
        resp = client.get("/api/v1/health/ready")
        # Pool is empty (PREWARM_POOL_SIZE=0), so 503 is expected
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "pool_depth" in data
        assert "active_sessions" in data
        assert "max_sessions" in data
