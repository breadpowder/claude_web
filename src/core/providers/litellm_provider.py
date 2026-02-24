"""LiteLLM provider — in-process LLM calls via the litellm SDK."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncGenerator

from src.core.config import LiteLLMConfig
from src.core.llm_provider import LLMProvider
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class LiteLLMProvider(LLMProvider):
    """LLM provider using ``litellm.acompletion()`` for in-process API calls.

    No subprocess is spawned — the provider calls the LLM API directly from
    the Python process.  This means the prewarm pool is not needed (set
    ``engine.prewarm_pool_size: 0`` in config).
    """

    def __init__(self, config: LiteLLMConfig):
        self._config = config
        self._session_id = str(uuid.uuid4())
        self._current_task: asyncio.Task | None = None

    # -- LLMProvider interface ------------------------------------------------

    async def connect(self) -> None:
        """No-op — in-process provider, nothing to spawn."""
        logger.debug("LiteLLMProvider ready (in-process, no subprocess)")

    async def query(self, prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        import litellm  # lazy import — only needed when this provider is active

        messages = [{"role": "user", "content": prompt}]

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
        }
        if self._config.api_key:
            kwargs["api_key"] = self._config.api_key
        if self._config.api_base:
            kwargs["api_base"] = self._config.api_base
        # Pass through extra params (temperature, max_tokens, etc.)
        kwargs.update(self._config.extra)

        tool_call_index = 0

        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if choice is None:
                continue

            delta = choice.delta

            # Text content
            if delta and getattr(delta, "content", None):
                yield {"type": "text", "content": delta.content}

            # Tool calls
            if delta and getattr(delta, "tool_calls", None):
                for tc in delta.tool_calls:
                    yield {
                        "type": "tool_use",
                        "id": tc.id or f"call_{uuid.uuid4().hex[:24]}",
                        "name": tc.function.name if tc.function else "",
                        "arguments": tc.function.arguments if tc.function else "{}",
                    }
                    tool_call_index += 1

            # Finish
            if choice.finish_reason:
                usage: dict[str, Any] = {}
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "input_tokens": getattr(chunk.usage, "prompt_tokens", 0) or 0,
                        "output_tokens": getattr(chunk.usage, "completion_tokens", 0) or 0,
                    }
                yield {
                    "type": "result_metadata",
                    "num_turns": 1,
                    "total_cost_usd": 0,
                    "duration_ms": 0,
                    "usage": usage,
                }

    async def interrupt(self) -> None:
        """Cancel the running async task if any."""
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def close(self) -> None:
        """No-op — no subprocess or connection to tear down."""
        logger.debug("LiteLLMProvider closed (in-process, no cleanup)")

    @property
    def session_id(self) -> str | None:
        return self._session_id
