"""E2E tests for edge cases and error handling (TASK-012)."""

from __future__ import annotations


class TestEdgeCases:
    """Verify error handling and edge-case responses."""

    def test_nonexistent_session_returns_404(self, client):
        resp = client.get("/api/v1/sessions/nonexistent-session-id")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_delete_nonexistent_session_is_idempotent(self, client):
        """Delete is idempotent - returns 204 even for unknown session IDs."""
        resp = client.delete("/api/v1/sessions/nonexistent-session-id")
        assert resp.status_code == 204

    def test_readiness_with_empty_pool_returns_503(self, client):
        """With PREWARM_POOL_SIZE=0, pool is empty so readiness returns 503."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "reason" in data
