"""Tests for SubprocessMonitor (TASK-006)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.subprocess_monitor import SubprocessMonitor


@pytest.fixture
def callbacks():
    return {
        "on_warning": AsyncMock(),
        "on_terminate": AsyncMock(),
    }


@pytest.fixture
def monitor(callbacks):
    return SubprocessMonitor(
        max_rss_mb=2048,
        max_duration_seconds=14400,
        on_warning=callbacks["on_warning"],
        on_terminate=callbacks["on_terminate"],
    )


class TestRegisterUnregister:
    def test_register_and_unregister(self, monitor):
        monitor.register("sess-1", pid=12345)
        assert monitor.is_tracked("sess-1") is True

        monitor.unregister("sess-1")
        assert monitor.is_tracked("sess-1") is False

    def test_unregister_nonexistent(self, monitor):
        monitor.unregister("nonexistent")  # no error


class TestCheckRSS:
    @pytest.mark.asyncio
    async def test_check_rss_fires_warning(self, monitor, callbacks):
        monitor.register("sess-1", pid=12345)

        # Mock reading /proc/<pid>/status to return high VmRSS
        fake_status = "VmRSS:\t2200000 kB\n"
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = lambda s, *a: None
            mock_open.return_value.read.return_value = fake_status

            await monitor.check_rss()

        callbacks["on_warning"].assert_called_once()
        call_args = callbacks["on_warning"].call_args
        assert call_args[0][0] == "sess-1"
        assert call_args[0][1]["reason"] == "memory"
        assert call_args[0][1]["rss_mb"] >= 2048


class TestCheckDuration:
    @pytest.mark.asyncio
    async def test_check_duration_warning_at_90_percent(self, monitor, callbacks):
        # 90% of 14400s = 12960s = 3h36m ago
        started = datetime.now(timezone.utc) - timedelta(seconds=12960)
        monitor.register("sess-1", pid=12345, started_at=started)

        await monitor.check_duration()

        callbacks["on_warning"].assert_called_once()
        call_args = callbacks["on_warning"].call_args
        assert call_args[0][0] == "sess-1"
        assert call_args[0][1]["reason"] == "duration"
        assert call_args[0][1]["remaining_seconds"] <= 1440

    @pytest.mark.asyncio
    async def test_check_duration_terminate_at_100_percent(self, monitor, callbacks):
        # Past limit: 4h1m ago
        started = datetime.now(timezone.utc) - timedelta(seconds=14460)
        monitor.register("sess-1", pid=12345, started_at=started)

        await monitor.check_duration()

        callbacks["on_terminate"].assert_called_once()
        call_args = callbacks["on_terminate"].call_args
        assert call_args[0][0] == "sess-1"
        assert call_args[0][1] == "duration_limit"


class TestCleanupZombies:
    @pytest.mark.asyncio
    async def test_cleanup_zombies_reaps_defunct(self, monitor, caplog):
        import logging

        monitor.register("sess-1", pid=12345)

        with caplog.at_level(logging.INFO), patch("os.waitpid", return_value=(12345, 0)) as mock_waitpid:
            await monitor.cleanup_zombies()

        mock_waitpid.assert_called_once_with(12345, 1)  # os.WNOHANG = 1
        assert monitor.is_tracked("sess-1") is False
        assert any("zombie" in r.message.lower() or "reaped" in r.message.lower() for r in caplog.records)


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_and_stop_tasks(self, monitor):
        await monitor.start()
        assert monitor._running is True

        await monitor.stop()
        assert monitor._running is False


class TestGracePeriod:
    @pytest.mark.asyncio
    async def test_duration_grace_period_for_inflight_query(self, monitor, callbacks):
        started = datetime.now(timezone.utc) - timedelta(seconds=14460)
        monitor.register("sess-1", pid=12345, started_at=started)
        monitor.mark_query_active("sess-1")

        await monitor.check_duration()

        # Should NOT terminate immediately when query is active
        callbacks["on_terminate"].assert_not_called()
        # Should fire warning instead
        callbacks["on_warning"].assert_called()
