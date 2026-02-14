"""Tests for PreWarmPool (TASK-004)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from src.core.prewarm_pool import PreWarmPool


@dataclass
class FakeClient:
    """Minimal stand-in matching ClaudeSDKClient interface."""

    query: AsyncMock = None

    def __post_init__(self):
        if self.query is None:
            self.query = AsyncMock()


async def _good_factory() -> FakeClient:
    return FakeClient()


async def _bad_factory() -> FakeClient:
    raise RuntimeError("Invalid API key")


class TestFill:
    @pytest.mark.asyncio
    async def test_fill_creates_clients(self):
        pool = PreWarmPool(target_size=2, client_factory=_good_factory)
        await pool.fill()
        assert pool.size() == 2

    @pytest.mark.asyncio
    async def test_fill_fails_on_all_invalid(self):
        pool = PreWarmPool(target_size=2, client_factory=_bad_factory)
        with pytest.raises(RuntimeError, match="pre-warm|failed"):
            await pool.fill()
        assert pool.size() == 0


class TestGet:
    @pytest.mark.asyncio
    async def test_get_returns_client_when_available(self):
        pool = PreWarmPool(target_size=1, client_factory=_good_factory)
        await pool.fill()
        client = pool.get()
        assert client is not None
        assert hasattr(client, "query")

    @pytest.mark.asyncio
    async def test_get_returns_none_when_empty(self):
        pool = PreWarmPool(target_size=0, client_factory=_good_factory)
        client = pool.get()
        assert client is None

    @pytest.mark.asyncio
    async def test_get_decreases_pool_depth(self):
        pool = PreWarmPool(target_size=2, client_factory=_good_factory)
        await pool.fill()
        assert pool.size() == 2
        pool.get()
        assert pool.size() == 1


class TestReplenish:
    @pytest.mark.asyncio
    async def test_replenish_fills_empty_slots(self):
        pool = PreWarmPool(target_size=2, client_factory=_good_factory)
        await pool.fill()
        pool.get()  # take one out
        assert pool.size() == 1

        await pool.replenish()
        assert pool.size() == 2

    @pytest.mark.asyncio
    async def test_replenish_backs_off_on_rate_limit(self, caplog):
        call_count = 0

        async def _rate_limit_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                raise RuntimeError("rate limit exceeded")
            return FakeClient()

        pool = PreWarmPool(
            target_size=1,
            client_factory=_rate_limit_then_ok,
            backoff_seconds=0.1,  # short for testing
        )
        # Fill fails, but we want to test replenish behavior
        # Start with empty pool by not calling fill
        await pool.replenish()

        # After replenish with backoff retry, pool should eventually fill
        assert pool.size() == 1
        assert any("rate limit" in r.message.lower() or "backoff" in r.message.lower() for r in caplog.records)
