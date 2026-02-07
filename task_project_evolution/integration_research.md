# Integration Research Report

> Research conducted: 2026-02-06
> Scope: Claude Agent SDK, MCP Protocol, A2A Protocol, Claude Code SDK

---

## Executive Summary

- **Claude Agent SDK is confirmed valid**: The core APIs documented (`query()`, `ClaudeAgentOptions`, `@tool`, `create_sdk_mcp_server`) are all still current and accurate in `claude-agent-sdk` v0.1.30 (released 2026-02-05). The original `claude-code-sdk` PyPI package is **deprecated** and replaced by `claude-agent-sdk`.
- **MCP Protocol has evolved significantly**: The 2025-03-26 spec revision replaced the SSE transport with **Streamable HTTP** as the standard remote transport. The current docs list SSE as a transport type, which is now deprecated in favor of Streamable HTTP. The two standard transports are now **stdio** and **Streamable HTTP**.
- **A2A Protocol is at Release Candidate v1.0**: Major evolution from earlier versions. Now under Linux Foundation governance. Supports JSON-RPC 2.0, gRPC, and HTTP/REST bindings. Breaking changes from earlier versions (kind discriminator removed, agent card restructured).
- **ClaudeAgentOptions has many new fields not documented**: The current doc is missing ~20+ fields that now exist, including `agents` (subagent definitions), `hooks`, `can_use_tool`, `plugins`, `sandbox`, `output_format`, `max_budget_usd`, `fallback_model`, `betas`, `fork_session`, `max_thinking_tokens`, and more.
- **New patterns to document**: Programmatic subagents, hooks system, structured outputs, sandbox configuration, file checkpointing, plugins, tool search, permission callbacks, and the Claude Code subprocess SDK (TypeScript/Python).

---

## Claude Agent SDK Status

### Package Information
- **PyPI Package**: `claude-agent-sdk` (replaces deprecated `claude-code-sdk`)
- **Latest Version**: 0.1.30 (2026-02-05)
- **Python Requirement**: >= 3.10
- **npm Package**: `@anthropic-ai/claude-agent-sdk` (replaces `@anthropic-ai/claude-code` for programmatic use)
- **CLI Bundled**: The SDK bundles the Claude Code CLI automatically

### Core API - Still Valid
All documented APIs remain valid:

| API | Status | Notes |
|-----|--------|-------|
| `query()` | **Valid** | Async iterator, creates new session each time |
| `ClaudeAgentOptions` | **Valid** | Significantly expanded with new fields (see below) |
| `@tool` decorator | **Valid** | Returns `SdkMcpTool` instance |
| `create_sdk_mcp_server()` | **Valid** | Returns `McpSdkServerConfig` |
| `ClaudeSDKClient` | **Valid** | Expanded with new methods |

### New `ClaudeAgentOptions` Fields (Not in Current Docs)

The following fields have been added to `ClaudeAgentOptions` since the documentation was written:

| Field | Type | Purpose |
|-------|------|---------|
| `tools` | `list[str] \| ToolsPreset \| None` | Tools configuration with presets |
| `continue_conversation` | `bool` | Continue the most recent conversation |
| `resume` | `str \| None` | Session ID to resume |
| `max_budget_usd` | `float \| None` | Maximum budget in USD for the session |
| `disallowed_tools` | `list[str]` | Blocklist for tools |
| `model` | `str \| None` | Model selection |
| `fallback_model` | `str \| None` | Fallback model |
| `betas` | `list[SdkBeta]` | Beta features (e.g., "context-1m-2025-08-07") |
| `output_format` | `OutputFormat \| None` | JSON Schema structured outputs |
| `cwd` | `str \| Path \| None` | Working directory (was documented) |
| `cli_path` | `str \| Path \| None` | Custom CLI path |
| `settings` | `str \| None` | Path to settings file |
| `add_dirs` | `list[str \| Path]` | Additional accessible directories |
| `env` | `dict[str, str]` | Environment variables |
| `extra_args` | `dict[str, str \| None]` | Additional CLI arguments |
| `can_use_tool` | `CanUseTool \| None` | Tool permission callback |
| `hooks` | `dict[HookEvent, list[HookMatcher]] \| None` | Hook configurations |
| `user` | `str \| None` | User identifier |
| `include_partial_messages` | `bool` | Enable `StreamEvent` messages |
| `fork_session` | `bool` | Fork session when resuming |
| `agents` | `dict[str, AgentDefinition] \| None` | Programmatic subagent definitions |
| `plugins` | `list[SdkPluginConfig]` | Load custom plugins |
| `sandbox` | `SandboxSettings \| None` | Sandbox configuration |
| `max_thinking_tokens` | `int \| None` | Maximum thinking tokens |
| `enable_file_checkpointing` | `bool` | File change tracking for rewinding |

### New `ClaudeSDKClient` Methods

| Method | Purpose |
|--------|---------|
| `rewind_files(user_message_uuid)` | Restore files to state at specified message |
| `interrupt()` | Send interrupt signal during streaming |

### New Types

| Type | Purpose |
|------|---------|
| `AgentDefinition` | Subagent config (description, prompt, tools, model) |
| `StreamEvent` | Partial message streaming events |
| `HookMatcher` | Hook matching configuration |
| `HookContext` | Context passed to hook callbacks |
| `PermissionResultAllow` / `PermissionResultDeny` | Permission callback results |
| `PermissionUpdate` | Programmatic permission updates |
| `SandboxSettings` | Sandbox behavior configuration |
| `SdkPluginConfig` | Plugin loading configuration |
| `OutputFormat` | Structured output validation (JSON Schema) |
| `SystemPromptPreset` | Preset system prompt with optional append |

### Key Behavioral Notes

1. **`query()` does NOT support custom tools**: Custom tools (via `@tool`) require `ClaudeSDKClient`, not `query()`. The current docs show `query()` with custom tools, which is partially misleading - custom MCP tools require streaming input mode.
2. **`setting_sources` defaults to None**: When omitted, no filesystem settings are loaded (isolation for SDK apps). Must include `"project"` to load CLAUDE.md files.
3. **Wildcard tool patterns**: `allowed_tools` now supports wildcards like `"mcp__github__*"`.

### What's Deprecated
- `debug_stderr` field on `ClaudeAgentOptions` - replaced by `stderr` callback
- `claude-code-sdk` PyPI package - replaced by `claude-agent-sdk`

---

## MCP Protocol Status

### Specification Version
- **Current Spec**: 2025-03-26 revision
- **Next Spec**: Tentatively June 2026

### Transport Types - CRITICAL UPDATE

The MCP protocol now defines **two** standard transports:

| Transport | Status | Use Case |
|-----------|--------|----------|
| **stdio** | **Current** | Local processes, subprocess communication |
| **Streamable HTTP** | **Current (NEW)** | Remote APIs, cloud-hosted servers |
| **SSE** | **DEPRECATED** | Replaced by Streamable HTTP |
| **In-Process** | **SDK-specific** | Not in MCP spec; handled by SDK MCP servers |

**Key change**: SSE transport has been superseded by **Streamable HTTP**, which uses HTTP POST and GET requests with optional SSE streaming for server-to-client messages. The server provides a single endpoint that handles both POST (for client messages) and GET (for server-initiated streams).

### Streamable HTTP Features
- Single endpoint path for both POST and GET
- Optional `Mcp-Session-Id` header for session management
- Supports both stateful and stateless server designs
- Compatible with standard HTTP infrastructure (load balancers, proxies)
- SSE is used within Streamable HTTP for streaming responses, but the transport itself is "Streamable HTTP", not "SSE"

### SDK Agent SDK MCP Transport Support

The Agent SDK currently supports these config types:

| Config Type | Maps to |
|-------------|---------|
| `McpStdioServerConfig` | stdio transport |
| `McpSSEServerConfig` | SSE transport (type: "sse") |
| `McpHttpServerConfig` | HTTP transport (type: "http") |
| `McpSdkServerConfig` | In-process SDK server (type: "sdk") |

Note: The SDK still supports SSE config alongside HTTP for backwards compatibility, even though the MCP spec has deprecated standalone SSE.

### MCP Python SDK (FastMCP)
The official MCP Python SDK (`mcp` package) now uses `FastMCP` as the primary server framework:
- Default transport: `streamable-http` (runs at `http://localhost:8000/mcp`)
- Supports stateless (`stateless_http=True`) and stateful modes
- Can be mounted in Starlette/ASGI apps
- CORS support with `Mcp-Session-Id` header exposure
- Decorator-based: `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`

### New MCP Features
- **Tool Search**: Auto-mode that activates when MCP tools exceed 10% of context window. Configured via `ENABLE_TOOL_SEARCH` env var.
- **OAuth 2.1 Authorization**: MCP spec now includes authorization support, though SDK doesn't handle OAuth flows automatically.
- **MCP Resources**: `ListMcpResources` and `ReadMcpResource` tools available in Agent SDK for accessing MCP resources (not just tools).

---

## A2A Protocol Status

### Specification Version
- **Latest Release**: Release Candidate v1.0 (latest released: 0.3.0)
- **Previous versions**: 0.2.6, 0.2.5, 0.2.4, 0.2.0, 0.1.0
- **Governance**: Now under Linux Foundation (originally Google)

### Core Concepts (Validated)
| Concept | Status | Notes |
|---------|--------|-------|
| Agent Cards | **Current** | Extended card structure relocated |
| Task Lifecycle | **Current** | States: working, completed, failed, canceled, rejected |
| Context & Messages | **Current** | Parts support text, files, structured data |
| Discovery | **Current** | Via Agent Cards |

### Protocol Bindings (Expanded)
The A2A protocol now supports three bindings (current docs only show REST):

| Binding | Description |
|---------|-------------|
| **JSON-RPC 2.0** | Method-based communication (was documented as "A2A Protocol") |
| **gRPC** | Service-based streaming (NEW - not documented) |
| **HTTP/REST** | URL and HTTP verb patterns (was documented as "REST Pattern") |

### Breaking Changes from Earlier Versions
1. **Kind Discriminator Removed**: Earlier versions used discriminator fields; current versions rely on field presence
2. **Extended Agent Card Relocation**: Repositioned within Agent Card structure
3. **Task states renamed**: Now uses "working" instead of previous terminology

### A2A-MCP Bridge Status

**GongRzhe/A2A-MCP-Server** (referenced in current docs):
- **Status**: Active, released May 2025
- **Installation**: npm (`npx a2a-mcp-server`), pip (`a2a-mcp-server`), or Smithery
- **Tools Exposed**: `register_agent`, `send_message`, `send_message_stream`, `get_task_result`

**Current doc discrepancy**: The documented tools (`discover_agents`, `send_task`, `get_task`, `cancel_task`) do NOT match the actual bridge tools (`register_agent`, `send_message`, `send_message_stream`, `get_task_result`).

**Alternative**: `regismesquita/MCP_A2A` - Lighter Python bridge with `register servers`, `list agents`, `call agent` tools.

---

## Claude Code SDK (Subprocess SDK)

### What It Is
The Claude Code SDK is a wrapper around the Claude Code CLI that enables programmatic agent creation. It works by spawning the Claude Code CLI as a subprocess and communicating via JSON over stdio.

### Available In
| Language | Package | Status |
|----------|---------|--------|
| **Python** | `claude-agent-sdk` (PyPI) | Official, v0.1.30 |
| **TypeScript** | `@anthropic-ai/claude-agent-sdk` (npm) | Official |
| **Ruby** | `claude-code-sdk-ruby` | Community |
| **Go** | `claude-code-sdk-go` | Community (unofficial) |
| **JavaScript** | `claude-code-js` | Community |

### Key Architecture Note
The Agent SDK is NOT a direct API client - it spawns the Claude Code CLI as a subprocess. This means:
- Claude Code CLI is bundled/required
- Communication is over process stdin/stdout
- The SDK manages the CLI lifecycle
- All Claude Code capabilities (tools, MCP, skills) are available

### Creation Workflow
Anthropic provides a `/new-sdk-app` skill in Claude Code that scaffolds new SDK projects with proper setup for both TypeScript and Python.

---

## Accuracy Check - Issues in Current Documentation

### Line-by-Line Issues

| Line(s) | Issue | Severity |
|----------|-------|----------|
| 1 | Title "Claude SDK Integration Patterns" - should clarify this is "Claude Agent SDK" | Low |
| 28-33 | Transport table lists **SSE** as current; SSE is **deprecated** in MCP spec (replaced by Streamable HTTP) | **High** |
| 33 | Lists **In-Process** as a transport type; this is SDK-specific, not an MCP transport | Medium |
| 45 | Import `from claude_agent_sdk` is correct | OK |
| 59-60 | HTTP config uses `"type": "http"` - valid but should note this maps to Streamable HTTP | Medium |
| 63-66 | SSE config `"type": "sse"` - still works in SDK but SSE is deprecated in MCP spec | **High** |
| 77 | `query()` with MCP servers works for stdio/HTTP/SSE but NOT for custom SDK tools | Medium |
| 99 | Import of `tool, create_sdk_mcp_server` - correct | OK |
| 102 | `@tool` signature is correct | OK |
| 116-119 | `create_sdk_mcp_server` usage is correct | OK |
| 123-128 | Using `query()` with custom tools - **potentially misleading**, custom MCP tools may require streaming input mode via `ClaudeSDKClient` | **High** |
| 158-159 | `setting_sources=["user", "project"]` - correct for loading skills | OK |
| 164-167 | `allowed_tools=["Skill", "Read", "Write", "Bash"]` - correct | OK |
| 226 | Import pattern correct | OK |
| 297-324 | A2A bridge with `npx a2a-mcp-server` - correct command | OK |
| 311-315 | Tool names `discover_agents`, `send_task`, `get_task`, `cancel_task` - **INCORRECT**, actual tools are `register_agent`, `send_message`, `send_message_stream`, `get_task_result` | **High** |
| 332 | `from a2a_client import A2AClient` - **hypothetical**, no official `a2a_client` Python SDK with this API | Medium |
| 376 | `ClaudeSDKClient` import - correct | OK |
| 392-409 | `ClaudeAgentOptions` missing many new fields | Medium |
| 420-427 | `ClaudeSDKClient` WebSocket example uses `client.receive_response()` - correct method name | OK |
| 445 | Resource URL `https://platform.claude.com/docs/en/agent-sdk/overview` - correct | OK |
| 447 | A2A Protocol URL `https://a2a-protocol.org/latest/` - correct | OK |
| 448 | A2A-MCP Bridge URL `https://github.com/GongRzhe/A2A-MCP-Server` - correct | OK |

### Summary of Critical Issues
1. **SSE listed as current transport** - should be marked deprecated, Streamable HTTP should be the documented remote transport
2. **A2A-MCP bridge tool names are wrong** - completely different tool names than what the bridge actually exposes
3. **`query()` shown with custom tools** - custom SDK MCP tools may require `ClaudeSDKClient` with streaming input, not simple `query()`
4. **Missing 20+ ClaudeAgentOptions fields** - significant API surface undocumented

---

## New Patterns to Document

### 1. Programmatic Subagents
Define subagents via `ClaudeAgentOptions.agents` with `AgentDefinition` (description, prompt, tools, model). Enables multi-agent orchestration without external frameworks.

### 2. Hooks System
Pre/Post tool use hooks, user prompt hooks, stop hooks, subagent stop hooks, and pre-compact hooks. Enables security validation, logging, prompt modification, and behavior control.

### 3. Structured Outputs
`OutputFormat` with JSON Schema validation for agent results. Forces output to conform to a schema.

### 4. Sandbox Configuration
`SandboxSettings` for command execution sandboxing, network restrictions, filesystem access control. Includes `autoAllowBashIfSandboxed`, `excludedCommands`, and permission fallback for unsandboxed commands.

### 5. File Checkpointing
`enable_file_checkpointing=True` + `client.rewind_files(user_message_uuid)` for restoring files to previous states.

### 6. Plugins
`SdkPluginConfig` for loading custom plugins from local paths. Extends SDK functionality.

### 7. Permission Callbacks (`can_use_tool`)
Programmatic tool permission system with `PermissionResultAllow` (can modify input) and `PermissionResultDeny` (can interrupt). Replaces manual permission management.

### 8. Tool Search
Automatic MCP tool discovery when tool definitions exceed context window threshold. Configured via `ENABLE_TOOL_SEARCH` environment variable.

### 9. Streamable HTTP Transport Pattern
Updated MCP remote transport pattern using Streamable HTTP instead of SSE. Including FastMCP server examples.

### 10. MCP Resources
`ListMcpResources` and `ReadMcpResource` tools for accessing MCP server resources (data, not just tools).

### 11. Session Management Patterns
`continue_conversation`, `resume`, `fork_session` for conversation continuity across SDK calls.

### 12. ClaudeSDKClient Advanced Patterns
Interrupt handling, streaming input via async generators, multi-turn conversations with context retention.

---

## References

- [Claude Agent SDK Python - GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Claude Agent SDK - PyPI](https://pypi.org/project/claude-agent-sdk/)
- [Agent SDK Python API Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Agent SDK Custom Tools](https://platform.claude.com/docs/en/agent-sdk/custom-tools)
- [Agent SDK MCP Integration](https://platform.claude.com/docs/en/agent-sdk/mcp)
- [Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [MCP Specification 2025-03-26 Transports](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [MCP Python SDK - GitHub](https://github.com/modelcontextprotocol/python-sdk)
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/)
- [A2A-MCP Bridge - GitHub](https://github.com/GongRzhe/A2A-MCP-Server)
- [MCP Transport Future](http://blog.modelcontextprotocol.io/posts/2025-12-19-mcp-transport-future/)
- [@anthropic-ai/claude-agent-sdk - npm](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
