"""Tests for OpenAI adapter translation functions (TASK-007)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.openai.adapter import (
    format_error,
    generate_request_id,
    make_final_chunk,
    make_non_streaming_response,
    messages_to_prompt,
    sdk_event_to_chunk,
    warn_unsupported_params,
)
from src.core.models import ExtensionConfig, SkillInfo
from src.core.prompt_expander import PromptExpander


class TestMessagesToPrompt:
    def test_single_user_message(self):
        messages = [{"role": "user", "content": "hello"}]
        prompt, result = messages_to_prompt(messages)
        assert prompt == "hello"
        assert result is None

    def test_multi_turn_conversation(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "A programming language."},
            {"role": "user", "content": "Tell me more."},
        ]
        prompt, _ = messages_to_prompt(messages)
        assert "[System]: You are helpful." in prompt
        assert "[User]: What is Python?" in prompt
        assert "[Assistant]: A programming language." in prompt
        assert "Tell me more." in prompt

    def test_slash_command_triggers_prompt_expansion(self):
        loader = MagicMock()
        loader.read_skill_content.return_value = "## Review Instructions\nBe thorough."
        expander = PromptExpander(loader)

        config = ExtensionConfig(
            skills=[
                SkillInfo(
                    name="code-review",
                    description="Review code",
                    path=".claude/skills/code-review",
                    invoke_prefix="/code-review",
                )
            ]
        )

        messages = [{"role": "user", "content": "/code-review review this function"}]
        prompt, expand_result = messages_to_prompt(
            messages, prompt_expander=expander, extension_config=config
        )
        assert "## Review Instructions" in prompt
        assert "Be thorough." in prompt
        assert "User request: review this function" in prompt
        assert "/code-review" not in prompt
        assert expand_result is not None
        assert expand_result.matched_extension == "code-review"

    def test_unrecognized_slash_command_passes_through(self):
        loader = MagicMock()
        expander = PromptExpander(loader)
        config = ExtensionConfig()

        messages = [{"role": "user", "content": "/nonexistent do something"}]
        prompt, _ = messages_to_prompt(
            messages, prompt_expander=expander, extension_config=config
        )
        assert prompt == "/nonexistent do something"


class TestSdkEventToChunk:
    def test_text_event(self):
        request_id = "chatcmpl-test"
        chunk, idx = sdk_event_to_chunk(
            {"type": "text", "content": "Hello"}, request_id, 0
        )
        assert chunk is not None
        assert chunk["choices"][0]["delta"]["content"] == "Hello"
        assert idx == 0

    def test_tool_use_event(self):
        request_id = "chatcmpl-test"
        event = {
            "type": "tool_use",
            "name": "mcp__github__list_issues",
            "arguments": '{"repo": "test"}',
        }
        chunk, idx = sdk_event_to_chunk(event, request_id, 0)
        assert chunk is not None
        tool_call = chunk["choices"][0]["delta"]["tool_calls"][0]
        assert tool_call["function"]["name"] == "mcp__github__list_issues"
        assert tool_call["index"] == 0
        assert tool_call["id"].startswith("call_")
        assert tool_call["type"] == "function"
        assert idx == 1

    def test_multiple_tool_calls_sequential_index(self):
        request_id = "chatcmpl-test"
        chunk1, idx = sdk_event_to_chunk(
            {"type": "tool_use", "name": "tool_a", "arguments": "{}"}, request_id, 0
        )
        chunk2, idx = sdk_event_to_chunk(
            {"type": "tool_use", "name": "tool_b", "arguments": "{}"}, request_id, idx
        )
        assert chunk1["choices"][0]["delta"]["tool_calls"][0]["index"] == 0
        assert chunk2["choices"][0]["delta"]["tool_calls"][0]["index"] == 1

    def test_tool_result_forwarded(self):
        request_id = "chatcmpl-test"
        chunk, idx = sdk_event_to_chunk(
            {
                "type": "tool_result",
                "tool_use_id": "toolu_123",
                "content": "result text",
                "is_error": False,
            },
            request_id,
            0,
        )
        assert chunk is not None
        tool_result = chunk["choices"][0]["delta"]["tool_result"]
        assert tool_result["tool_use_id"] == "toolu_123"
        assert tool_result["content"] == "result text"
        assert tool_result["is_error"] is False
        assert idx == 0  # tool_call_index unchanged for results

    def test_tool_result_error_forwarded(self):
        request_id = "chatcmpl-test"
        chunk, idx = sdk_event_to_chunk(
            {
                "type": "tool_result",
                "tool_use_id": "toolu_456",
                "content": "Validation failed",
                "is_error": True,
            },
            request_id,
            0,
        )
        assert chunk is not None
        tool_result = chunk["choices"][0]["delta"]["tool_result"]
        assert tool_result["is_error"] is True

    def test_result_metadata_forwarded(self):
        request_id = "chatcmpl-test"
        chunk, idx = sdk_event_to_chunk(
            {
                "type": "result_metadata",
                "num_turns": 3,
                "total_cost_usd": 0.0012,
                "duration_ms": 2400,
                "usage": {"input_tokens": 1200, "output_tokens": 890},
            },
            request_id,
            2,
        )
        assert chunk is not None
        assert "meta" in chunk
        assert chunk["meta"]["num_turns"] == 3
        assert chunk["meta"]["total_cost_usd"] == 0.0012
        assert chunk["meta"]["duration_ms"] == 2400
        assert chunk["meta"]["usage"]["input_tokens"] == 1200
        assert idx == 2


class TestFinalChunk:
    def test_make_final_chunk(self):
        chunk = make_final_chunk("chatcmpl-test")
        assert chunk["choices"][0]["finish_reason"] == "stop"
        assert "usage" in chunk
        assert chunk["usage"]["prompt_tokens"] >= 0


class TestNonStreamingResponse:
    def test_make_non_streaming_response(self):
        resp = make_non_streaming_response("chatcmpl-test", "Hello world")
        assert resp["id"] == "chatcmpl-test"
        assert resp["choices"][0]["message"]["role"] == "assistant"
        assert resp["choices"][0]["message"]["content"] == "Hello world"
        assert "usage" in resp


class TestFormatError:
    def test_format_error(self):
        err = format_error(503, "At capacity")
        assert err["error"]["message"] == "At capacity"
        assert err["error"]["type"] == "server_error"
        assert err["error"]["code"] == 503


class TestRequestId:
    def test_generate_request_id(self):
        rid = generate_request_id()
        assert rid.startswith("chatcmpl-")


class TestUnsupportedParams:
    def test_warn_unsupported_params(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            warn_unsupported_params({"temperature": 0.7, "top_p": 0.9, "model": "claude"})
        assert any("unsupported" in r.message.lower() for r in caplog.records)
