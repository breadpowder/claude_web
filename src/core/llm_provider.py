"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class LLMProvider(ABC):
    """Abstract base class for LLM provider implementations.

    Every provider must support the same lifecycle:
    ``connect()`` → ``query()`` (repeatable) → ``close()``.

    The ``query()`` method yields the internal event dict format:

    * ``{"type": "text", "content": "..."}``
    * ``{"type": "tool_use", "id": "...", "name": "...", "arguments": "..."}``
    * ``{"type": "tool_result", "tool_use_id": "...", "content": "...", "is_error": bool}``
    * ``{"type": "result_metadata", "num_turns": int, "total_cost_usd": float, ...}``
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialise the provider (e.g. spawn subprocess, validate keys)."""

    @abstractmethod
    async def query(self, prompt: str) -> AsyncGenerator[dict[str, Any], None]:
        """Send *prompt* and yield event dicts until the response completes."""
        # Trick so the method is recognised as an async generator by type-checkers.
        yield {}  # pragma: no cover

    @abstractmethod
    async def interrupt(self) -> None:
        """Interrupt an in-flight query."""

    @abstractmethod
    async def close(self) -> None:
        """Release all resources held by this provider."""

    @property
    @abstractmethod
    def session_id(self) -> str | None:
        """Provider-assigned session identifier (available after first query)."""

    @property
    def pid(self) -> int | None:
        """PID of an underlying subprocess, or ``None``."""
        return None
