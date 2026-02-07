# Architecture Gap Analysis: claudesdk_integration.md

> Analysis Date: 2026-02-06
> Analyst: architecture-analyst
> Source: Claude Agent SDK official docs, Context7 MCP, GitHub repo, web research

---

## Executive Summary

- **The documented API surface is largely accurate** for the core `query()`, `ClaudeAgentOptions`, `@tool`, and `create_sdk_mcp_server` APIs. Import paths and basic signatures match the official SDK.
- **Multiple major SDK features are entirely missing** from the documentation: Subagents/AgentDefinition, Hooks system, Structured Outputs, Session Management (resume/fork), and the `ClaudeSDKClient` interactive client pattern.
- **The `ClaudeAgentOptions` dataclass is severely under-documented**; the current doc shows ~8 fields while the actual SDK exposes 30+ fields including `model`, `system_prompt`, `agents`, `hooks`, `output_format`, `max_budget_usd`, `max_thinking_tokens`, `env`, `add_dirs`, and more.
- **A2A patterns (sections 4 and 5) are speculative**; they document community/hypothetical integration approaches, not official SDK features. The `a2a_client` import and A2A-MCP bridge package are third-party and may not be maintained.
- **Production architecture (section 6) has inaccuracies** in the `ClaudeSDKClient` WebSocket pattern, showing methods (`client.query()` with `client.receive_response()`) that don't match the actual client API pattern.

---

## Gap Analysis: Documented vs Available (Per Pattern)

### Pattern 1: MCP Server Integration

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| Transport types | stdio, HTTP, SSE, In-Process | stdio, HTTP/streamable-HTTP, SSE (legacy), In-Process | Minor: "streamable HTTP" is the current standard; SSE is marked legacy |
| `mcp_servers` config | Dict with `command`/`args`/`env` for stdio; `type`/`url`/`headers` for HTTP/SSE | Same structure confirmed | Accurate |
| `allowed_tools` format | `mcp__<server>__<tool>` | Same format confirmed | Accurate |
| Wildcard tool patterns | Not shown | `mcp__github__*` wildcard supported (shown in section 6 but not section 1) | Should document wildcard patterns in section 1 |
| `McpServerConfig` type | Not referenced | Official type in SDK | Should reference the type |
| Config file path support | Not documented | `mcp_servers` accepts `str | Path` pointing to a JSON config file | Missing |

**Verdict**: Mostly accurate. Minor gaps around transport terminology and config file support.

### Pattern 2: Custom Tools (@tool Decorator)

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| `@tool` decorator signature | `@tool("name", "desc", {"param": type})` | Same signature confirmed | Accurate |
| Return format | `{"content": [{"type": "text", "text": "..."}]}` | Same format, plus optional `is_error` field | Missing `is_error` field |
| `create_sdk_mcp_server` | `create_sdk_mcp_server(name=, version=, tools=)` | Same signature confirmed | Accurate |
| Import path | `from claude_agent_sdk import tool, create_sdk_mcp_server` | Same confirmed | Accurate |
| Tool input typing | `args: dict` | `args: dict[str, Any]` preferred with `from typing import Any` | Minor typing improvement |

**Verdict**: Accurate. Minor enhancement opportunity for `is_error` and typing.

### Pattern 3: Skills Integration

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| Skill file structure | `.claude/skills/<name>/SKILL.md` | Same confirmed | Accurate |
| Skill frontmatter | Shows `name`, `description`, `allowed-tools` | Confirmed pattern | Accurate |
| `setting_sources` config | `["user", "project"]` | `list[SettingSource]` type in SDK | Accurate values |
| Skill invocation | "Claude auto-matches based on description" | Skills are invoked via the `Skill` tool, matching by description or explicit `/command` | Could be more precise |

**Verdict**: Accurate but could add more detail on how skills are triggered.

### Pattern 4: A2A REST Pattern

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| Pattern type | Custom tool wrapping REST calls | Not an SDK-native pattern | Correct as a custom integration pattern |
| `AGENT_REGISTRY` | Referenced but not defined | User-defined | Should note it's user-defined |
| Session management | Manual dict-based | User-implemented | Correct characterization |
| Error handling | Missing | Should include timeouts, retries, error responses | Gap |

**Verdict**: This is a valid integration pattern but is not SDK-native. Should be clearly labeled as a custom/community pattern.

### Pattern 5: A2A Protocol Pattern

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| A2A-MCP Bridge | `npx a2a-mcp-server` | Third-party package (GongRzhe/A2A-MCP-Server) | Should note third-party status and check maintenance |
| `from a2a_client import A2AClient` | Option B custom code | No official `a2a_client` Python SDK | Speculative import; should note this is hypothetical |
| Tool names | `mcp__a2a__discover_agents`, etc. | Depend on the actual MCP server implementation | Should note these are specific to the bridge |

**Verdict**: Useful conceptual pattern but relies on third-party/hypothetical libraries. Should add disclaimers.

### Pattern 6: Complete Service Architecture

| Aspect | Documented | Actual SDK | Gap |
|--------|-----------|------------|-----|
| FastAPI integration | `@app.post` with `query()` | Valid pattern | Accurate |
| WebSocket pattern | `ClaudeSDKClient` with `client.query()` + `client.receive_response()` | Actual SDK uses this pattern confirmed | Mostly accurate |
| `ClaudeSDKClient` import | `from claude_agent_sdk import ClaudeSDKClient` | Confirmed | Accurate |
| Wildcard tools | `mcp__github__*` | Supported | Accurate |
| `permission_mode` | `"acceptEdits"` | Valid value | Accurate |

**Verdict**: Mostly accurate. WebSocket pattern could use better error handling and streaming event handling.

---

## Missing Patterns (Not Documented At All)

### 1. Subagents / Multi-Agent Orchestration (HIGH PRIORITY)

The SDK supports programmatic subagent definitions via `AgentDefinition`, which is a **major feature** completely absent from the documentation.

**What's available:**
- `agents` parameter in `ClaudeAgentOptions`: `dict[str, AgentDefinition]`
- `AgentDefinition` with fields: `description`, `prompt`, `tools`, `model` (sonnet/opus/haiku/inherit)
- Subagents invoked via the `Task` tool
- `parent_tool_use_id` field on messages to track subagent context
- Subagents cannot spawn their own subagents (important constraint)
- Subagent session resume via `agentId` + `session_id`

**Source**: `from claude_agent_sdk import AgentDefinition`

### 2. Hooks System (HIGH PRIORITY)

The SDK has a comprehensive hooks system for intercepting and controlling agent behavior. Entirely missing.

**Hook events available:**
- `PreToolUse` - Inspect/block tool calls before execution
- `PostToolUse` - Review tool output, add context, halt on errors
- `PostToolUseFailure` - Handle tool execution failures
- `Notification` - Agent notifications
- `UserPromptSubmit` - Intercept user prompts
- `SessionStart` / `SessionEnd` - Session lifecycle
- `Stop` - Agent stop event
- `SubagentStart` / `SubagentStop` - Subagent lifecycle
- `PreCompact` - Before context compaction
- `PermissionRequest` - Custom permission handling

**Key types**: `HookMatcher`, `HookEvent`, `HookInput`, `HookContext`, `HookJSONOutput`

### 3. Structured Outputs (MEDIUM-HIGH PRIORITY)

The SDK supports schema-validated JSON output. Not documented.

**What's available:**
- `output_format` parameter in `ClaudeAgentOptions`
- `OutputFormat` type with `type: "json_schema"` support
- Result messages include `structured_output` field with validated data
- Supports standard JSON Schema features: object, array, string, integer, number, boolean, null, enum, const, etc.
- Now GA (no longer requires beta header)

### 4. Session Management (MEDIUM PRIORITY)

Conversation persistence, resume, and forking capabilities. Not documented beyond minimal `ClaudeSDKClient` usage.

**What's available:**
- `resume` parameter: Session ID string to resume a conversation
- `fork_session` parameter: Branch a conversation without modifying the original
- `continue_conversation` parameter: Continue most recent conversation
- Session IDs returned in system init messages
- Sessions persisted to disk by default (`~/.claude/projects/`)

### 5. Model Configuration and Budget Controls (LOW-MEDIUM PRIORITY)

**Missing parameters:**
- `model`: Select Claude model (e.g., `"claude-sonnet-4-5"`, `"claude-opus-4-6"`)
- `fallback_model`: Fallback if primary model fails
- `max_budget_usd`: Cost cap for a session
- `max_thinking_tokens`: Control extended thinking token budget
- `betas`: Enable beta features via `list[SdkBeta]`

### 6. Message Types and Streaming Events (LOW-MEDIUM PRIORITY)

The documentation does not describe the message types yielded by `query()`.

**Available types:**
- `AssistantMessage` - Claude's text responses
- `TextBlock` - Text content block within messages
- `ToolUseBlock` - Tool invocation block
- `ToolResultBlock` - Tool result block
- `ResultMessage` - Final result with `session_id`, `result`, `cost_usd`
- `StreamEvent` - Partial streaming events (when `include_partial_messages=True`)

### 7. Permission Callback (`can_use_tool`) (LOW PRIORITY)

Custom permission logic via callback function. Not documented.

**What's available:**
- `can_use_tool` parameter: `CanUseTool | None`
- Allows programmatic permission decisions per tool invocation
- Alternative to static `allowed_tools` / `disallowed_tools` lists

### 8. Environment and Directory Configuration (LOW PRIORITY)

**Missing parameters:**
- `env`: Pass environment variables to the agent process
- `add_dirs`: Additional directories Claude can access
- `extra_args`: Additional CLI arguments
- `cli_path`: Custom Claude Code CLI path

---

## Outdated Content

| Item | Current State | Recommended Update |
|------|--------------|-------------------|
| SSE transport | Listed as primary transport type | Mark as legacy; recommend "streamable HTTP" as the modern alternative |
| Resource links | `https://platform.claude.com/docs/en/agent-sdk/overview` | Verify URL is still valid; some content has moved to `https://docs.claude.com/en/docs/agent-sdk/` |
| `ClaudeAgentOptions` field list | Shows ~8 fields in examples | Update to show awareness of 30+ fields, at minimum the commonly-used ones |
| Git workflow in CLAUDE.md | References branch `claude/claude-md-ml2jl5ov0fptxwbm-aIvno` | Should reference `main` or be removed |
| No mention of `claude-opus-4-6` or `claude-sonnet-4-5` | Models not referenced | Add model selection examples |

---

## Code Example Accuracy

### Import Paths (All Verified Correct)

```python
from claude_agent_sdk import query, ClaudeAgentOptions          # Correct
from claude_agent_sdk import tool, create_sdk_mcp_server        # Correct
from claude_agent_sdk import ClaudeSDKClient                    # Correct
from claude_agent_sdk import AssistantMessage, TextBlock        # Correct (not shown in docs)
from claude_agent_sdk import AgentDefinition                    # Correct (not shown in docs)
from claude_agent_sdk import HookMatcher                        # Correct (not shown in docs)
```

### API Signatures (Verified)

| API | Documented Signature | Actual Signature | Match? |
|-----|---------------------|------------------|--------|
| `query()` | `query(prompt=str, options=ClaudeAgentOptions)` | `query(*, prompt: str \| AsyncIterable, options: ClaudeAgentOptions \| None)` | Yes (prompt can also be async iterable - not documented) |
| `@tool` | `@tool("name", "desc", {"param": type})` | Same | Yes |
| `create_sdk_mcp_server` | `create_sdk_mcp_server(name=, version=, tools=)` | Same | Yes |
| `ClaudeSDKClient` | Context manager with `.query()` and `.receive_response()` | Confirmed | Yes |

### Minor Code Issues

1. **Section 2, line 108**: `json.dumps(results)` but `json` is not imported. Add `import json`.
2. **Section 4, line 258**: `await asyncio.sleep(1)` but `asyncio` is not imported at the top of the function. Add `import asyncio`.
3. **Section 5, line 339**: `json.dumps(...)` used but `json` not imported.
4. **Section 6**: No error handling around `query()` calls - production code should have try/except for connection errors, timeouts, etc.

---

## Recommendations (Prioritized)

### P0 - Critical (Should address immediately)

1. **Add Subagents/Multi-Agent Pattern (New Section 7)**
   - Document `AgentDefinition`, `agents` parameter, `Task` tool invocation
   - Include example with parallel subagents and pipeline patterns
   - Note constraint: subagents cannot spawn subagents

2. **Add Hooks System Pattern (New Section 8)**
   - Document all 12 hook events
   - Include `PreToolUse` and `PostToolUse` examples
   - Show `HookMatcher` configuration
   - Cover permission hooks for subagent tool approval

3. **Add Structured Outputs Pattern (New Section 9)**
   - Document `output_format` with `json_schema` type
   - Show how to define schemas and access `structured_output` in results
   - Note GA status (no beta header needed)

### P1 - High (Should address soon)

4. **Add Session Management Section**
   - Document `resume`, `fork_session`, `continue_conversation`
   - Show session ID capture from init messages
   - Include fork/resume workflow example

5. **Expand `ClaudeAgentOptions` Reference**
   - Add a comprehensive reference table of all 30+ fields
   - Group by category: Tool Config, Model Config, Session, Execution Constraints, Hooks, Environment
   - Add `model`, `max_budget_usd`, `max_thinking_tokens`, `env` to examples

6. **Add Message Types Documentation**
   - Document `AssistantMessage`, `TextBlock`, `ToolUseBlock`, `ToolResultBlock`, `ResultMessage`
   - Show proper message iteration and type checking patterns

### P2 - Medium (Should address in next iteration)

7. **Add Disclaimers to A2A Patterns**
   - Mark A2A REST and A2A Protocol sections as "Community/Custom Patterns"
   - Note third-party status of A2A-MCP bridge
   - Clarify that `a2a_client` is hypothetical

8. **Fix Missing Imports in Code Examples**
   - Add `import json` where `json.dumps` is used
   - Add `import asyncio` where `asyncio.sleep` is used
   - Add `from typing import Any` for type hints

9. **Update Transport Types**
   - Note SSE as legacy
   - Document "streamable HTTP" as the modern transport

10. **Add Error Handling to Production Examples**
    - Show try/except patterns around `query()` calls
    - Document common exceptions and error scenarios
    - Add timeout handling examples

### P3 - Low (Nice to have)

11. **Add `can_use_tool` Permission Callback Pattern**
    - Document custom permission logic
    - Show use case: dynamic tool approval based on context

12. **Add Environment/Directory Configuration Examples**
    - Document `env`, `add_dirs`, `extra_args` parameters
    - Show multi-directory access patterns

13. **Add Model Selection Guide**
    - Reference current model IDs (`claude-opus-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5`)
    - Document `model` and `fallback_model` usage
    - Show `max_thinking_tokens` for extended reasoning

14. **Verify and Update Resource URLs**
    - Check all external links are still valid
    - Add links to new SDK documentation pages (hooks, subagents, sessions, structured outputs)

---

## Summary Metrics

| Category | Count |
|----------|-------|
| Documented patterns | 6 |
| Missing patterns (should add) | 8 |
| Outdated items | 5 |
| Code accuracy issues | 4 (all minor) |
| P0 recommendations | 3 |
| P1 recommendations | 3 |
| P2 recommendations | 4 |
| P3 recommendations | 4 |

---

## Research Sources

- [Claude Agent SDK Docs - Python API Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Claude Agent SDK Python - GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Agent SDK - Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Claude Agent SDK - Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Claude Agent SDK - Structured Outputs](https://platform.claude.com/docs/en/agent-sdk/structured-outputs)
- [Claude Agent SDK - Sessions](https://platform.claude.com/docs/en/agent-sdk/sessions)
- [Claude Agent SDK - Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [A2A-MCP Bridge](https://github.com/GongRzhe/A2A-MCP-Server)
- Context7 MCP: `/websites/platform_claude_en_agent-sdk` (624 snippets, High reputation)
- Context7 MCP: `/anthropics/claude-agent-sdk-python` (40 snippets, High reputation)
