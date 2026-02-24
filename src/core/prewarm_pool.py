"""Pre-warm pool for ClaudeSDKClient instances (TASK-004)."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine

from src.core.logging_config import get_logger

logger = get_logger(__name__)

# Default backoff on rate limit: 5 minutes
DEFAULT_BACKOFF_SECONDS = 300.0


class PreWarmPool:
    """Maintains ready-to-use ClaudeSDKClient instances in an asyncio.Queue."""

    def __init__(
        self,
        target_size: int,
        client_factory: Callable[[], Coroutine[Any, Any, Any]],
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ):
        self._target_size = target_size
        self._factory = client_factory
        self._backoff_seconds = backoff_seconds
        self._queue: asyncio.Queue = asyncio.Queue()

    def size(self) -> int:
        """Return current number of available clients in the pool."""
        return self._queue.qsize()

    def get(self) -> Any | None:
        """Non-blocking get: returns a client or None if pool is empty."""
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def fill(self) -> None:
        """Initialize pool with target_size clients.

        Blocks until at least 1 succeeds. Raises RuntimeError if all fail.
        """
        if self._target_size <= 0:
            return

        results = await asyncio.gather(
            *[self._create_client() for _ in range(self._target_size)],
            return_exceptions=True,
        )

        successes = 0
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Pre-warm client creation failed: %s", result)
            else:
                await self._queue.put(result)
                successes += 1

        if successes == 0:
            raise RuntimeError(
                f"All {self._target_size} pre-warm attempts failed"
            )

        logger.info("Pre-warm pool filled: %d/%d clients ready", successes, self._target_size)

    async def replenish(self) -> None:
        """Refill pool to target size. Backs off on rate limit errors."""
        slots_needed = self._target_size - self.size()
        for _ in range(slots_needed):
            try:
                client = await self._create_client()
                await self._queue.put(client)
            except RuntimeError as exc:
                if "rate limit" in str(exc).lower():
                    logger.warning(
                        "Rate limit during replenish, backoff %.0fs",
                        self._backoff_seconds,
                    )
                    await asyncio.sleep(self._backoff_seconds)
                    # Retry once after backoff
                    try:
                        client = await self._create_client()
                        await self._queue.put(client)
                    except Exception as retry_exc:
                        logger.error("Replenish retry failed: %s", retry_exc)
                else:
                    logger.error("Replenish failed: %s", exc)
            except Exception as exc:
                logger.error("Replenish failed: %s", exc)

    async def drain(self) -> None:
        """Close all pooled clients and empty the queue.

        Must be called during shutdown to terminate pre-warmed subprocesses.
        """
        closed = 0
        while not self._queue.empty():
            try:
                client = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if hasattr(client, "close"):
                try:
                    await client.close()
                    closed += 1
                except Exception as exc:
                    logger.warning("Error closing pooled client: %s", exc)
        if closed:
            logger.info("Drained pre-warm pool: %d clients closed", closed)

    async def _create_client(self) -> Any:
        """Create a single client via the factory."""
        return await self._factory()
