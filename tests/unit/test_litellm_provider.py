"""Tests for LiteLLM provider event translation."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import LiteLLMConfig


# ---------------------------------------------------------------------------
# Helpers to build mock litellm streaming chunks
# ---------------------------------------------------------------------------


@dataclass
class MockDelta:
    content: str | None = None
    tool_calls: list | None = None


@dataclass
class MockChoice:
    delta: MockDelta = field(default_factory=MockDelta)
    finish_reason: str | None = None


@dataclass
class MockUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 20


@dataclass
class MockChunk:
    choices: list[MockChoice] = field(default_factory=list)
    usage: MockUsage | None = None


async def _async_iter(items):
    """Turn a list into an async iterator."""
    for item in items:
        yield item


class TestLiteLLMProviderQuery:
    """Test that LiteLLM streaming chunks translate to internal event format."""

    @pytest.mark.asyncio
    async def test_text_content_events(self):
        chunks = [
            MockChunk(choices=[MockChoice(delta=MockDelta(content="Hello "))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(content="world"))]),
            MockChunk(choices=[MockChoice(delta=MockDelta(), finish_reason="stop")]),
        ]

        # Patch litellm.acompletion directly (module is installed, import is lazy)
        with patch("litellm.acompletion", new=AsyncMock(return_value=_async_iter(chunks))):
            from src.core.providers.litellm_provider import LiteLLMProvider

            provider = LiteLLMProvider(LiteLLMConfig(api_key="test-key"))
            await provider.connect()

            events = []
            async for event in provider.query("Say hello"):
                events.append(event)

        text_events = [e for e in events if e["type"] == "text"]
        assert len(text_events) == 2
        assert text_events[0]["content"] == "Hello "
        assert text_events[1]["content"] == "world"

        result_events = [e for e in events if e["type"] == "result_metadata"]
        assert len(result_events) == 1
        assert result_events[0]["num_turns"] == 1

    @pytest.mark.asyncio
    async def test_tool_call_events(self):
        tool_call = MagicMock()
        tool_call.id = "call_abc123"
        tool_call.function.name = "get_weather"
        tool_call.function.arguments = '{"city": "NYC"}'

        chunks = [
            MockChunk(
                choices=[MockChoice(delta=MockDelta(tool_calls=[tool_call]))]
            ),
            MockChunk(choices=[MockChoice(delta=MockDelta(), finish_reason="stop")]),
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=_async_iter(chunks))):
            from src.core.providers.litellm_provider import LiteLLMProvider

            provider = LiteLLMProvider(LiteLLMConfig(api_key="test-key"))
            await provider.connect()

            events = []
            async for event in provider.query("What's the weather?"):
                events.append(event)

        tool_events = [e for e in events if e["type"] == "tool_use"]
        assert len(tool_events) == 1
        assert tool_events[0]["id"] == "call_abc123"
        assert tool_events[0]["name"] == "get_weather"
        assert tool_events[0]["arguments"] == '{"city": "NYC"}'

    @pytest.mark.asyncio
    async def test_finish_with_usage(self):
        chunks = [
            MockChunk(
                choices=[MockChoice(delta=MockDelta(), finish_reason="stop")],
                usage=MockUsage(prompt_tokens=100, completion_tokens=50),
            ),
        ]

        with patch("litellm.acompletion", new=AsyncMock(return_value=_async_iter(chunks))):
            from src.core.providers.litellm_provider import LiteLLMProvider

            provider = LiteLLMProvider(LiteLLMConfig(api_key="test-key"))
            await provider.connect()

            events = []
            async for event in provider.query("test"):
                events.append(event)

        result = [e for e in events if e["type"] == "result_metadata"][0]
        assert result["usage"]["input_tokens"] == 100
        assert result["usage"]["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_extra_params_forwarded(self):
        chunks = [
            MockChunk(choices=[MockChoice(delta=MockDelta(), finish_reason="stop")]),
        ]

        mock_acompletion = AsyncMock(return_value=_async_iter(chunks))

        with patch("litellm.acompletion", new=mock_acompletion):
            from src.core.providers.litellm_provider import LiteLLMProvider

            config = LiteLLMConfig(
                api_key="test-key",
                extra={"temperature": 0.7, "max_tokens": 1024},
            )
            provider = LiteLLMProvider(config)
            await provider.connect()

            events = []
            async for event in provider.query("test"):
                events.append(event)

            call_kwargs = mock_acompletion.call_args[1]
            assert call_kwargs["temperature"] == 0.7
            assert call_kwargs["max_tokens"] == 1024

    @pytest.mark.asyncio
    async def test_session_id_is_stable(self):
        from src.core.providers.litellm_provider import LiteLLMProvider

        provider = LiteLLMProvider(LiteLLMConfig(api_key="test-key"))
        sid = provider.session_id
        assert sid is not None
        assert provider.session_id == sid  # stable across calls

    @pytest.mark.asyncio
    async def test_connect_and_close_are_noops(self):
        from src.core.providers.litellm_provider import LiteLLMProvider

        provider = LiteLLMProvider(LiteLLMConfig(api_key="test-key"))
        await provider.connect()  # should not raise
        await provider.close()  # should not raise
