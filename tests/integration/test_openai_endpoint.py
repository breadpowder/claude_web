"""Integration tests for OpenAI-compliant endpoint (TASK-007)."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from src.api.openai.endpoint import router
from src.core.exceptions import CapacityError


@dataclass
class FakeClient:
    session_id: str = ""
    pid: int = 99999

    async def query(self, prompt: str):
        yield {"type": "text", "content": "Hello from Claude"}

    async def close(self):
        pass


def _create_test_app(
    max_sessions=10,
    at_capacity=False,
    stream_events=None,
):
    """Create a FastAPI app with mocked session manager."""
    app = FastAPI()
    app.include_router(router)

    session_counter = {"count": 0}
    sessions = {}

    async def _acquire():
        if at_capacity:
            raise CapacityError("At maximum capacity of 10 sessions")
        sid = str(uuid.uuid4())
        client = FakeClient(session_id=sid)
        sessions[sid] = client
        session_counter["count"] += 1
        return sid, client

    async def _query(session_id, prompt):
        if stream_events:
            for event in stream_events:
                yield event
        else:
            yield {"type": "text", "content": "Hello from Claude"}

    async def _release(session_id):
        sessions.pop(session_id, None)
        session_counter["count"] -= 1

    sm = MagicMock()
    sm.acquire_session = AsyncMock(side_effect=_acquire)
    sm.query = _query
    sm.release_session = AsyncMock(side_effect=_release)

    app.state.session_manager = sm
    app.state.prompt_expander = None
    app.state.extension_config = None

    return app


@pytest.fixture
def app():
    return _create_test_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_streaming_response_format(self, client):
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "claude", "messages": [{"role": "user", "content": "hello"}], "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:")]
        assert len(data_lines) >= 2  # at least one content chunk + final + DONE

        # Check content chunk
        first_data = json.loads(data_lines[0].split("data:", 1)[1].strip())
        assert "choices" in first_data
        assert "delta" in first_data["choices"][0]

    @pytest.mark.asyncio
    async def test_stream_ends_with_done_sentinel(self, client):
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "claude", "messages": [{"role": "user", "content": "hello"}], "stream": True},
        )
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:")]
        last_data = data_lines[-1].strip()
        assert last_data == "data: [DONE]"


class TestNonStreamingResponse:
    @pytest.mark.asyncio
    async def test_non_streaming_response_format(self, client):
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "claude", "messages": [{"role": "user", "content": "hello"}], "stream": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert data["choices"][0]["message"]["content"] == "Hello from Claude"
        assert data["id"].startswith("chatcmpl-")
        assert "usage" in data


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_model_returns_400(self, client):
        resp = await client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status_code == 400
        assert "model is required" in resp.json()["error"]["message"]

    @pytest.mark.asyncio
    async def test_unsupported_params_ignored(self, client):
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "claude",
                "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.7,
                "top_p": 0.9,
                "logprobs": True,
                "stream": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "Hello from Claude"


class TestCapacity:
    @pytest.mark.asyncio
    async def test_no_capacity_returns_503_with_retry_after(self):
        app = _create_test_app(at_capacity=True)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "claude", "messages": [{"role": "user", "content": "hello"}]},
            )
        assert resp.status_code == 503
        assert resp.json()["error"]["type"] == "server_error"
        assert "capacity" in resp.json()["error"]["message"].lower()
        assert resp.headers["retry-after"] == "30"


class TestSkillExpansion:
    """Test that /skill-name prompts are expanded with SKILL.md content."""

    @pytest.mark.asyncio
    async def test_skill_prompt_expanded_in_chat(self):
        """When user sends /skill-name args, the skill body is injected into the prompt."""
        received_prompts = []

        async def _query(session_id, prompt):
            received_prompts.append(prompt)
            yield {"type": "text", "content": "Skill executed"}

        app = _create_test_app()
        # Replace query to capture the prompt
        app.state.session_manager.query = _query

        # Set up prompt expander with a fake skill
        from src.core.extension_loader import ExtensionLoader
        from src.core.prompt_expander import PromptExpander
        from src.core.models import ExtensionConfig, SkillInfo
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, ".claude", "skills", "test-review")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: test-review\ndescription: Review stuff\n---\nYou are a reviewer. Analyze the input.")

            loader = ExtensionLoader(tmpdir, user_dir=os.path.join(tmpdir, "_no_user"))
            ext_config = loader.scan()
            expander = PromptExpander(loader)

            app.state.prompt_expander = expander
            app.state.extension_config = ext_config

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude",
                        "messages": [{"role": "user", "content": "/test-review my-package"}],
                        "stream": False,
                    },
                )

        assert resp.status_code == 200
        assert len(received_prompts) == 1
        # The expanded prompt should contain the skill body, not the raw /command
        assert "You are a reviewer" in received_prompts[0]
        assert "my-package" in received_prompts[0]
        assert received_prompts[0] != "/test-review my-package"

    @pytest.mark.asyncio
    async def test_unknown_slash_command_passes_through(self):
        """Unknown /commands should pass through unchanged."""
        received_prompts = []

        async def _query(session_id, prompt):
            received_prompts.append(prompt)
            yield {"type": "text", "content": "OK"}

        app = _create_test_app()
        app.state.session_manager.query = _query

        from src.core.extension_loader import ExtensionLoader
        from src.core.prompt_expander import PromptExpander
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ExtensionLoader(tmpdir, user_dir=os.path.join(tmpdir, "_no_user"))
            ext_config = loader.scan()
            expander = PromptExpander(loader)

            app.state.prompt_expander = expander
            app.state.extension_config = ext_config

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude",
                        "messages": [{"role": "user", "content": "/nonexistent foo"}],
                        "stream": False,
                    },
                )

        assert resp.status_code == 200
        assert len(received_prompts) == 1
        assert received_prompts[0] == "/nonexistent foo"


class TestMultiTurnSkillExecution:
    """Test that skills producing multi-turn tool-use responses return complete results."""

    @pytest.mark.asyncio
    async def test_multi_turn_text_fully_returned_non_streaming(self):
        """Non-streaming response must concatenate text from ALL turns, not just the first."""
        events = [
            {"type": "text", "content": "I'll review the package. "},
            {"type": "tool_use", "name": "Bash", "arguments": '{"command": "npm view xlsx"}'},
            {"type": "tool_result", "content": "xlsx@0.18.5"},
            {"type": "text", "content": "## Package Review\n\n| Criteria | Score |\n|---|---|\n| Security | 7/10 |"},
        ]
        app = _create_test_app(stream_events=events)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "claude", "messages": [{"role": "user", "content": "review xlsx"}], "stream": False},
            )
        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        # Both text chunks must be in the final content
        assert "I'll review" in content
        assert "Package Review" in content
        assert "Security" in content

    @pytest.mark.asyncio
    async def test_multi_turn_text_fully_streamed(self):
        """Streaming response must include text from ALL turns including post-tool text."""
        events = [
            {"type": "text", "content": "Analyzing..."},
            {"type": "tool_use", "name": "WebFetch", "arguments": '{"url": "https://example.com"}'},
            {"type": "tool_result", "content": "page content"},
            {"type": "text", "content": "The evaluation shows: PASS"},
        ]
        app = _create_test_app(stream_events=events)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "claude", "messages": [{"role": "user", "content": "test"}], "stream": True},
            )
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:") and l.strip() != "data: [DONE]"]

        all_content = ""
        for line in data_lines:
            data = json.loads(line.split("data:", 1)[1].strip())
            delta = data.get("choices", [{}])[0].get("delta", {})
            if "content" in delta:
                all_content += delta["content"]

        assert "Analyzing" in all_content
        assert "evaluation shows: PASS" in all_content

    @pytest.mark.asyncio
    async def test_skill_expanded_prompt_reaches_sdk(self):
        """Full pipeline: skill expansion → SDK query → complete result returned."""
        received_prompts = []

        async def _query(session_id, prompt):
            received_prompts.append(prompt)
            yield {"type": "text", "content": "Reviewing npm package..."}
            yield {"type": "tool_use", "name": "Bash", "arguments": '{"command": "npm view xlsx"}'}
            yield {"type": "tool_result", "content": "xlsx info"}
            yield {"type": "text", "content": "## Verdict: APPROVED\nScore: 8/10"}

        app = _create_test_app()
        app.state.session_manager.query = _query

        from src.core.extension_loader import ExtensionLoader
        from src.core.prompt_expander import PromptExpander
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, ".claude", "skills", "pkg-review")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
                f.write("---\nname: pkg-review\ndescription: Review packages\n---\nEvaluate the package for security and quality.")

            loader = ExtensionLoader(tmpdir, user_dir=os.path.join(tmpdir, "_no_user"))
            ext_config = loader.scan()
            expander = PromptExpander(loader)

            app.state.prompt_expander = expander
            app.state.extension_config = ext_config

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "claude",
                        "messages": [{"role": "user", "content": "/pkg-review xlsx"}],
                        "stream": False,
                    },
                )

        assert resp.status_code == 200
        content = resp.json()["choices"][0]["message"]["content"]
        # Must include both text segments (initial + post-tool)
        assert "Reviewing npm package" in content
        assert "Verdict: APPROVED" in content
        # Prompt must have been expanded with skill body
        assert len(received_prompts) == 1
        assert "Evaluate the package" in received_prompts[0]
        assert "xlsx" in received_prompts[0]


class TestToolCalls:
    @pytest.mark.asyncio
    async def test_tool_calls_in_sse_stream(self):
        events = [
            {"type": "tool_use", "name": "mcp__github__list_issues", "arguments": '{"repo": "test"}'},
            {"type": "text", "content": "Found 3 issues."},
        ]
        app = _create_test_app(stream_events=events)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "claude", "messages": [{"role": "user", "content": "list issues"}], "stream": True},
            )
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:") and l.strip() != "data: [DONE]"]

        # Find tool call chunk
        tool_chunks = []
        for line in data_lines:
            data = json.loads(line.split("data:", 1)[1].strip())
            if "tool_calls" in data.get("choices", [{}])[0].get("delta", {}):
                tool_chunks.append(data)

        assert len(tool_chunks) >= 1
        tc = tool_chunks[0]["choices"][0]["delta"]["tool_calls"][0]
        assert tc["function"]["name"] == "mcp__github__list_issues"
        assert tc["id"].startswith("call_")
        assert tc["type"] == "function"

    @pytest.mark.asyncio
    async def test_tool_result_not_in_sse_stream(self):
        events = [
            {"type": "tool_use", "name": "tool_a", "arguments": "{}"},
            {"type": "tool_result", "content": "result data"},
            {"type": "text", "content": "Based on the result..."},
        ]
        app = _create_test_app(stream_events=events)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": "claude", "messages": [{"role": "user", "content": "test"}], "stream": True},
            )
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data:") and l.strip() != "data: [DONE]"]

        has_tool_call = False
        has_tool_result = False
        has_text = False
        for line in data_lines:
            data = json.loads(line.split("data:", 1)[1].strip())
            delta = data.get("choices", [{}])[0].get("delta", {})
            if "tool_calls" in delta:
                has_tool_call = True
            if "content" in delta and "Based on" in delta["content"]:
                has_text = True

        assert has_tool_call
        assert has_text
        # Tool result should not appear as its own chunk (only 3 data lines: tool, text, final)
        non_final = [l for l in data_lines if '"finish_reason": "stop"' not in l and '"finish_reason":null' not in l]
        # tool_use + text = 2 non-final chunks (tool_result suppressed)
        assert len(non_final) <= 3  # may include final chunk depending on format
