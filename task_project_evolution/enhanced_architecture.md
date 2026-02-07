# Enhanced Architecture Design: claude_sdk_pattern

> A Pluggable Claude Code Web Platform
>
> Version: 1.1 | Date: 2026-02-06
> Based on: Claude Agent SDK v0.1.30, React 19, FastAPI, Python 3.12
> Revision: Addresses architecture review findings (subprocess lifecycle, security, error recovery, observability, frontend performance)

---

## 1. Vision and Principles

### What This System Is

`claude_sdk_pattern` is a web-based platform that exposes Claude Code as a service. It wraps the Claude Agent SDK behind a FastAPI backend and a React 19 frontend, allowing users to interact with Claude Code through a browser. The distinguishing characteristic is its **pluggable extension model**: operators and developers can extend the platform by registering custom tools, MCP servers, skills, and HTTP endpoints -- all without modifying the core platform.

Think of it as "Claude Code, but deployed as a web application with an extension marketplace." The core engine is the Claude Agent SDK (which itself manages the Claude Code CLI as a subprocess). Everything else -- the tools Claude can use, the workflows it can follow, the UI panels the user sees -- is a plugin.

### Design Principles

1. **SDK-First**: The Claude Agent SDK is the engine. The platform does not re-implement agent logic; it configures and orchestrates the SDK. Every capability maps to a real SDK parameter on `ClaudeAgentOptions` or `ClaudeSDKClient`.

2. **Plugin-as-Capability**: Every extension is a plugin. MCP servers, custom tools, skills, and API endpoints all register through the same Plugin Registry. The registry translates plugin declarations into SDK configuration.

3. **Streaming-Native**: All communication between the backend and frontend uses WebSocket streaming. The SDK yields messages as an async iterator; those messages flow through the WebSocket to the React UI with no buffering.

4. **Secure by Default**: The SDK runs inside a sandboxed container. Plugins declare their required permissions. The permission system (`can_use_tool` callback) enforces authorization at every tool invocation. No plugin gets blanket access.

5. **One Subprocess per Session**: The Claude Agent SDK spawns the Claude Code CLI as a subprocess. This is a fundamental architectural constraint. Each user session maps to one subprocess. Horizontal scaling means scaling containers, not threads.

6. **Separation of Concerns**: The backend owns session lifecycle, plugin orchestration, and SDK communication. The frontend owns rendering, user interaction, and plugin UI slots. They communicate exclusively through the WebSocket protocol.

---

## 2. System Architecture Overview

```
                        +-----------------------+
                        |    Browser (React 19) |
                        |                       |
                        |  ChatApp              |
                        |   +-- ChatPanel       |
                        |   |    +-- MessageList|
                        |   |    +-- InputBar   |
                        |   |    +-- ToolPanel  |
                        |   +-- PluginSlots     |
                        |        +-- Custom UI  |
                        +-----------+-----------+
                                    |
                             WebSocket (JSON)
                                    |
                        +-----------+-----------+
                        |  FastAPI Gateway       |
                        |                        |
                        |  /ws/v1/chat           |
                        |  /api/v1/plugins       |
                        |  /api/v1/sessions      |
                        |  /api/v1/admin         |
                        +-----------+------------+
                                    |
                        +-----------+------------+
                        |  Core Engine            |
                        |                         |
                        |  SessionManager         |
                        |  PluginRegistry         |
                        |  PermissionGate         |
                        |  HookDispatcher         |
                        |  OptionsBuilder         |
                        +-----------+-------------+
                                    |
                        +-----------+-------------+
                        |  Claude Agent SDK        |
                        |                          |
                        |  ClaudeSDKClient         |
                        |  (manages CLI subprocess)|
                        +-----------+--------------+
                                    |
               +--------------------+--------------------+
               |                    |                    |
        +------+------+    +-------+------+    +--------+-----+
        | MCP Servers  |    |  Custom Tools |    |   Skills     |
        | (stdio/HTTP) |    |  (@tool)      |    |  (SKILL.md)  |
        +--------------+    +--------------+    +--------------+
```

### Key Relationships

- The React frontend maintains a single WebSocket connection per chat session.
- The FastAPI gateway manages authentication, routing, and the REST API for plugin/session management.
- The Core Engine is the coordination layer: it builds `ClaudeAgentOptions` from the Plugin Registry, manages `ClaudeSDKClient` instances, dispatches hooks, and enforces permissions.
- The Claude Agent SDK is a thin wrapper around the Claude Code CLI subprocess. It provides `query()` for one-shot exchanges and `ClaudeSDKClient` for multi-turn conversations.
- Plugins register capabilities (tools, MCP configs, skills, endpoints) that the Core Engine injects into `ClaudeAgentOptions` at session creation time.

---

## 3. Backend Architecture (FastAPI + Claude Agent SDK)

### 3.1 Core Engine: ClaudeSDKClient as the Chat Driver

The platform uses `ClaudeSDKClient` (not `query()`) as the primary interface to the SDK. This choice is deliberate:

- `ClaudeSDKClient` maintains session state across multiple exchanges, which is required for a chat application.
- It supports hooks, custom tools, interrupts, and streaming input -- none of which `query()` supports.
- It enables follow-up questions that build on previous context within the same session.

Each active chat session maps to one `ClaudeSDKClient` instance. The client is held as an async context manager whose lifecycle is managed by the `SessionManager`.

**Subprocess initialization latency.** The Claude Code CLI subprocess takes 20-30 seconds to initialize (reported in GitHub issue anthropics/claude-agent-sdk-python#333). This is because the CLI bundles a Node.js runtime that must boot V8, load shell snapshots, and establish API connections. To mitigate this, the platform implements a **pre-warming pool**: on startup, the `SessionManager` initializes a configurable number of `ClaudeSDKClient` instances (controlled by `CLAUDE_SDK_PATTERN_PREWARM_POOL_SIZE`, default 2). When a user opens a chat, they receive a pre-warmed client immediately. The pool replenishes asynchronously in the background. If the pool is empty, the user waits for cold initialization; the frontend shows a "Preparing your session..." status during this time.

**Memory growth and session duration limits.** The CLI subprocess accumulates memory over extended sessions, with RSS growing from ~2.5 GiB to 24-26 GiB in extreme cases (GitHub issue anthropics/claude-code#13126). Shell snapshots in `~/.claude/` can grow to 1.5 GiB. To prevent OOM crashes, the platform enforces:
- A maximum session duration (`CLAUDE_SDK_PATTERN_MAX_SESSION_DURATION_SECONDS`, default 14400 = 4 hours). The `SessionManager` monitors session age and initiates graceful shutdown when the limit is reached, notifying the user via WebSocket and offering session resume.
- Memory monitoring per subprocess. The `SessionManager` periodically checks RSS of the CLI process (via `/proc/<pid>/status` on Linux). If RSS exceeds `CLAUDE_SDK_PATTERN_MAX_SESSION_RSS_MB` (default 4096), the session is flagged for graceful restart.
- Cache cleanup between sessions. When a `ClaudeSDKClient` is destroyed, the `SessionManager` clears the session's working directory and shell snapshot cache from `~/.claude/`. In ephemeral container deployments, this is handled automatically by container destruction.

The interaction loop is: the user sends a message via WebSocket, the handler calls `client.query(message)`, then iterates over `client.receive_response()` and forwards each message to the WebSocket. Message types include `AssistantMessage` (with `TextBlock` and `ToolUseBlock` content), `ToolResultBlock`, `StreamEvent` (when `include_partial_messages` is enabled), and `ResultMessage` (which carries `session_id`, `result`, `cost_usd`, and optionally `structured_output`).

### 3.2 Plugin Registry

The Plugin Registry holds all registered plugins and translates them into SDK configuration at session creation time. Plugin metadata and configuration (including encrypted secrets) are persisted to the database, so plugin state survives server restarts. On startup, the registry loads persisted plugin records from the database, re-discovers plugins from the filesystem, and reconciles: new plugins on disk are added, removed plugins are marked inactive, and existing plugins retain their configuration and activation status.

**Registry responsibilities:**
- Discover plugins from the filesystem (the `plugins/` directory)
- Validate plugin manifests against the expected schema
- Register plugins by type (tool, MCP, skill, endpoint)
- Build the `mcp_servers`, `allowed_tools`, `agents`, and `hooks` dictionaries that feed into `ClaudeAgentOptions`
- Track plugin state (active, disabled, errored)

**How the registry builds options:**

The `OptionsBuilder` class (in `src/claude_sdk_pattern/core/options_builder.py`) queries the Plugin Registry and constructs a `ClaudeAgentOptions` instance for a given session. It merges:

- **MCP plugin configs** into the `mcp_servers` dict. Each MCP plugin declares its server type (stdio, HTTP, or SDK) and configuration. The builder merges them with a namespaced key.
- **Tool plugin configs** into an in-process MCP server via `create_sdk_mcp_server()`. All `@tool`-decorated functions from tool plugins are bundled into one or more SDK MCP servers and added to `mcp_servers`.
- **Skill plugin configs** by ensuring `setting_sources` includes `"project"` and the skill directories are accessible via `add_dirs`.
- **Subagent definitions** from plugins that declare agents, merging them into the `agents` dict as `AgentDefinition` instances.
- **Hook registrations** from plugins, merging them into the `hooks` dict keyed by `HookEvent`.
- **Allowed/disallowed tool lists** aggregated from all active plugins, with the permission system as the final gatekeeper.

### 3.3 WebSocket Streaming

The WebSocket endpoint at `/ws/v1/chat` is the primary communication channel between frontend and backend.

**Upstream (client to server) message types:**
- `user_message`: A chat message from the user
- `interrupt`: Request to interrupt the current operation (calls `client.interrupt()`)
- `session_command`: Session management commands (resume, fork)
- `plugin_config`: Runtime plugin enable/disable

**Downstream (server to client) message types:**
- `text`: Partial or complete text from Claude (`TextBlock`)
- `tool_use`: Tool invocation notification (`ToolUseBlock` with tool name and input)
- `tool_result`: Tool execution result (`ToolResultBlock`)
- `stream_event`: Partial message update (when `include_partial_messages=True`)
- `result`: Final result with session_id, cost, and optional structured_output
- `error`: Error notification
- `status`: Session status updates (thinking, executing tool, idle)

The handler iterates over `client.receive_response()` and maps each SDK message type to the appropriate downstream WebSocket message. For real-time partial updates, the `include_partial_messages` flag is set to `True` on `ClaudeAgentOptions`, which causes the SDK to yield `StreamEvent` messages as Claude generates tokens.

### 3.4 Session Management

Sessions are the unit of conversation state. The platform supports three session patterns, all backed by the SDK:

- **New session**: Default. Each `ClaudeSDKClient` instance starts a new session. The `session_id` is captured from the `ResultMessage` after the first exchange.
- **Resume session**: Pass `resume=<session_id>` in `ClaudeAgentOptions` to continue a previous conversation. The SDK loads the session from its on-disk store (`~/.claude/projects/`).
- **Fork session**: Pass `resume=<session_id>` together with `fork_session=True` to branch a conversation without modifying the original. Useful for "what if" explorations.
- **Continue conversation**: Pass `continue_conversation=True` to continue the most recent conversation without specifying a session ID.

The platform stores session metadata (session_id, user_id, created_at, last_active, plugin_set) in its own database. The actual conversation history is managed by the SDK on disk.

The `SessionManager` class (in `src/claude_sdk_pattern/core/session_manager.py`) handles:
- Mapping user IDs to active `ClaudeSDKClient` instances
- Session timeout and cleanup (destroying idle clients)
- Session metadata persistence
- Passing resume/fork parameters to `ClaudeAgentOptions`

### 3.5 Hooks Integration

The SDK hooks system allows intercepting agent behavior at key lifecycle points. The platform uses hooks for security enforcement, logging, and plugin-provided behavior modification.

**Hook events the platform uses:**

| Hook Event | Platform Use |
|------------|-------------|
| `PreToolUse` | Permission enforcement, input validation, audit logging. The `PermissionGate` registers a `PreToolUse` hook with a `HookMatcher` that matches all tools. It checks the tool name and input against the plugin's declared permissions and the user's authorization level. Returns a deny decision with reason if unauthorized. |
| `PostToolUse` | Result logging, cost tracking, error detection. Plugins can register `PostToolUse` hooks to inspect tool outputs (e.g., a compliance plugin that scans for PII in results). |
| `PostToolUseFailure` | Error reporting and retry logic. Forwards failure details to the frontend via WebSocket. |
| `UserPromptSubmit` | Prompt-level guardrails. Inspects user messages before they reach Claude. Used for injection detection, message length enforcement, and tenant isolation (see Section 3.10). |
| `Notification` | Forwarded to the frontend as status updates. |
| `SubagentStart` / `SubagentStop` | Tracks subagent lifecycle for the frontend's agent visualization panel. |
| `SessionStart` / `SessionEnd` | Session lifecycle tracking for metrics and audit logging. |
| `PreCompact` | Logs when context compaction occurs, useful for debugging long sessions. |
| `Stop` | Session cleanup trigger. |

Hooks are registered via `HookMatcher` objects in `ClaudeAgentOptions.hooks`. Each `HookMatcher` specifies an optional `matcher` string (tool name pattern), a list of async hook functions, and a `timeout` in seconds.

The `HookDispatcher` class (in `src/claude_sdk_pattern/core/hook_dispatcher.py`) aggregates hooks from the core platform and from all active plugins, then passes the merged hook configuration to `OptionsBuilder`.

### 3.6 Structured Outputs

The platform supports structured output mode via the `output_format` parameter on `ClaudeAgentOptions`. When a session is configured for structured output:

- The `output_format` is set to `{"type": "json_schema", "schema": <json_schema>}` where the schema is a standard JSON Schema definition.
- The `ResultMessage` from the SDK will contain a `structured_output` field with the validated data, alongside the normal `result` text.
- The `ResultMessage.subtype` indicates success (`"success"`) or failure (`"error_max_structured_output_retries"`) if the agent could not produce valid output after multiple attempts.

This is used by endpoint plugins that need machine-readable output (e.g., a plugin that extracts invoice data and returns it as structured JSON to an upstream system).

### 3.7 Subagent Orchestration

The platform allows plugins to define subagents via `AgentDefinition`. These are registered through the Plugin Registry and merged into `ClaudeAgentOptions.agents`.

Each `AgentDefinition` contains:
- `description` (str, required): Natural language description of when to use this agent. Claude uses this to decide when to invoke the subagent.
- `prompt` (str, required): The subagent's system prompt.
- `tools` (list of str, optional): Allowed tool names. If omitted, the subagent inherits all parent tools.
- `model` (one of "sonnet", "opus", "haiku", "inherit", optional): Model override for this subagent.

**Constraints:**
- Subagents cannot spawn their own subagents (SDK limitation).
- The `Task` tool must be in the parent agent's `allowed_tools` for subagent invocation to work.
- Subagents should not include `Task` in their own `tools` array.

The parent agent invokes subagents via the `Task` tool. The platform tracks subagent lifecycle through `SubagentStart` and `SubagentStop` hooks, which the frontend uses to show agent activity in the UI.

Subagent sessions can potentially be resumed by capturing the `agentId` from the Task tool result and using it with `resume=<session_id>` on a subsequent query. **Caveat**: The SDK documentation on subagent session resume is sparse. This capability should be verified experimentally before being exposed as a platform feature. The platform will initially support subagent resume as an experimental feature behind a feature flag (`CLAUDE_SDK_PATTERN_ENABLE_SUBAGENT_RESUME`, default false).

### 3.8 Sandbox Configuration

The SDK supports programmatic sandbox configuration via `SandboxSettings` on `ClaudeAgentOptions`. The platform sets sandbox defaults for all sessions:

- `enabled: True` -- all bash commands run inside the SDK's sandbox.
- `allowUnsandboxedCommands: False` by default. Plugins can request unsandboxed access, which requires explicit user authorization through the `can_use_tool` callback.

For production deployments, the entire SDK process runs inside a container (Docker, gVisor, or Firecracker VM) as described in the official hosting guide. The platform recommends the **ephemeral session** pattern: spin up a new container per user session, destroy it on disconnect. This provides process isolation, resource limits, network control, and ephemeral filesystems.

**Resource requirements per SDK instance**: The official docs recommend 1 GiB RAM, 5 GiB disk, 1 CPU as a minimum. However, real-world sessions commonly reach 2.5+ GiB RSS (GitHub issue anthropics/claude-code#13126), so production deployments should allocate 4 GiB RAM per container to allow headroom. The dominant cost is API tokens, not compute -- container hosting costs approximately $0.05/hour while API tokens typically exceed this by 10-100x.

### 3.9 Permission System

The permission system has three layers:

1. **Static tool lists**: `allowed_tools` and `disallowed_tools` on `ClaudeAgentOptions`. The `OptionsBuilder` constructs these from the merged plugin declarations.

2. **Dynamic callback**: The `can_use_tool` parameter accepts an async function with the signature `(tool_name: str, input_data: dict, context: ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`. The platform's `PermissionGate` implements this callback. It checks:
   - Is the tool declared by any active plugin?
   - Does the user have authorization for this tool category?
   - For `Bash` with `dangerouslyDisableSandbox`, is the specific command in the allowlist?

   The `PermissionResultAllow` return type supports an `updated_input` field, which the `PermissionGate` uses for input sanitization -- for example, stripping sensitive environment variable references from Bash commands before execution. The `PermissionResultDeny` return type includes a `reason` field that Claude sees, allowing it to adjust its approach.

3. **Hooks-based enforcement**: The `PreToolUse` hook provides a second layer of enforcement. Unlike `can_use_tool` (which is a simple allow/deny), hook-based enforcement can return a `permissionDecisionReason` that Claude sees, allowing it to adjust its approach.

Plugins declare their required permissions in their manifest. The permission system validates these declarations against the operator's configuration at registration time.

### 3.10 Security Architecture

Security is a cross-cutting concern for a platform that gives users access to a shell-capable AI agent. The security design spans authentication, authorization, network protection, prompt-level guardrails, and secret management.

**Authentication.** The platform uses JWT-based authentication with refresh tokens. The `src/claude_sdk_pattern/api/auth.py` module implements:
- Login endpoint (`POST /api/v1/auth/login`) that validates credentials and returns an access token (short-lived, 15 minutes) and a refresh token (long-lived, 7 days).
- Token validation middleware applied to all REST endpoints and the WebSocket upgrade handshake. The WebSocket connection sends the JWT as a query parameter during upgrade (since WebSocket does not support custom headers in the browser).
- User identity is extracted from the JWT and propagated to the `SessionManager` and `PermissionGate` for per-user authorization decisions.

**Authorization (RBAC).** Three roles are defined:
- `admin`: Full access. Can manage plugins, view all sessions, configure platform settings.
- `operator`: Can enable/disable plugins, configure plugin secrets, view session metrics.
- `user`: Can create sessions, send messages, and use activated plugins. Cannot modify plugin configuration.

The role is encoded in the JWT claims. FastAPI dependency functions (`require_role("admin")`, `require_role("operator")`) enforce role checks on each endpoint.

**CORS policy.** The FastAPI app configures CORS middleware with an explicit origin allowlist (`CLAUDE_SDK_PATTERN_ALLOWED_ORIGINS`). In development, this defaults to `http://localhost:5173` (Vite dev server). In production, it must be set to the frontend's deployed origin. The WebSocket upgrade also validates the `Origin` header.

**Rate limiting.** Two layers of rate limiting are enforced:
- REST API: Per-user rate limits via a token bucket algorithm, implemented as FastAPI middleware. Default: 60 requests/minute for standard endpoints, 10 requests/minute for session creation (which triggers expensive SDK initialization).
- WebSocket messages: Per-session rate limits on `user_message` type. Default: 20 messages/minute. Excess messages receive a `rate_limited` error response via WebSocket. This prevents runaway API costs from buggy or malicious clients.

**Prompt injection defense.** The platform registers a `UserPromptSubmit` hook (added to the hooks table in Section 3.5) that inspects user messages before they reach Claude. The hook implementation in `src/claude_sdk_pattern/core/prompt_guard.py`:
- Scans for common injection patterns (system prompt override attempts, role-playing instructions, data exfiltration commands).
- Enforces a maximum message length (`CLAUDE_SDK_PATTERN_MAX_MESSAGE_LENGTH`, default 32000 characters).
- In multi-tenant deployments, ensures messages cannot reference other users' session IDs or working directories.

This is a defense-in-depth measure. The SDK's own safety mechanisms are the primary defense; the `UserPromptSubmit` hook provides an additional platform-level layer.

**Plugin secret management.** Plugin secrets (API keys, tokens) provided during the configure step (Section 5.2) are stored encrypted at rest. The `src/claude_sdk_pattern/plugins/secret_store.py` module:
- Encrypts secrets using Fernet symmetric encryption with a key derived from `CLAUDE_SDK_PATTERN_SECRET_KEY`.
- Stores encrypted values in the database (SQLite or PostgreSQL, depending on deployment).
- Decrypts secrets only when building `ClaudeAgentOptions.env` for a session, and only for the specific plugin's declared environment variables.
- Never exposes raw secrets through the REST API. The `GET /api/v1/plugins/{name}/config` endpoint returns secret field names with masked values.

For container deployments, secrets can alternatively be injected via Kubernetes Secrets or a vault service, bypassing the platform's secret store entirely.

### 3.11 Error Recovery

The architecture must handle failures as clearly as it handles the happy path. The primary failure modes are CLI subprocess crashes, API outages, and plugin errors.

**CLI subprocess crash recovery.** When the CLI subprocess is killed (by OOM, signal, or internal error), the `ClaudeSDKClient` raises `ProcessError`. The WebSocket handler wraps the `client.receive_response()` iteration in a try/except that catches `ProcessError` and `CLIConnectionError`. The recovery flow:
1. The handler sends a WebSocket message `{type: "error", code: "subprocess_crash", message: "Session interrupted. Attempting recovery..."}` to the frontend.
2. The `SessionManager` captures the `session_id` from the crashed session's metadata.
3. A new `ClaudeSDKClient` is created with `resume=<session_id>` to restore conversation context. If the resume succeeds, the frontend receives a `{type: "status", status: "recovered"}` message and can continue the conversation.
4. If the resume fails (e.g., session data is corrupted), the user receives an error message explaining that the session could not be recovered, with an option to start a new session.
5. The crash event is logged with the session ID, user ID, subprocess PID, and available memory at the time of crash for post-mortem analysis.

**API outage circuit breaker.** The `src/claude_sdk_pattern/core/circuit_breaker.py` module implements a circuit breaker for the Anthropic API. If `client.query()` fails with connection errors N times in a sliding window (default: 5 failures in 60 seconds), the circuit opens. While open:
- New `client.query()` calls are short-circuited with an immediate error, avoiding cascading timeouts.
- The frontend receives `{type: "error", code: "api_unavailable", message: "Claude API is temporarily unavailable. Retrying..."}`.
- The circuit breaker periodically attempts a probe query. When the probe succeeds, the circuit closes and normal operation resumes.

**Plugin failure in active sessions.** When an MCP server crashes or becomes unresponsive during an active session:
- The SDK reports the tool failure through the normal message stream (`PostToolUseFailure` hook fires).
- The platform sends `{type: "tool_error", tool: "<plugin_name>", message: "..."}` to the frontend.
- The session continues; Claude will see the tool failure and adapt (e.g., skip the unavailable tool or try an alternative approach).
- The `PluginRegistry` marks the plugin as "degraded" and logs the failure. It does not remove tools from the in-flight session's configuration mid-conversation.

**Auto-interrupt for hung queries.** The `SessionManager` monitors wall-clock time per query. If a query exceeds `CLAUDE_SDK_PATTERN_QUERY_TIMEOUT_SECONDS` (default 600 = 10 minutes), it calls `client.interrupt()` and sends a timeout notification to the frontend. The `max_turns` parameter provides an additional safeguard against infinite tool-execution loops.

### 3.12 Observability

**Structured logging.** All platform components use the `structlog` library configured in `src/claude_sdk_pattern/config/logging.py`. Log format is JSON with the following standard fields: `timestamp`, `level`, `logger`, `event`, `correlation_id`, `session_id`, `user_id`. The correlation ID is generated when a WebSocket message arrives and propagated through all downstream calls. The SDK's CLI subprocess writes to stderr; the platform captures stderr output and logs it with the associated session_id for correlation.

**Metrics.** The platform exposes Prometheus-compatible metrics via the `/metrics` endpoint (using the `prometheus-fastapi-instrumentator` library). Key metrics:
- `csp_active_sessions` (gauge): Number of active `ClaudeSDKClient` instances.
- `csp_session_init_duration_seconds` (histogram): Time to initialize a new SDK client (tracks the 20-30s cold start problem).
- `csp_query_duration_seconds` (histogram): Wall-clock time per `client.query()` call.
- `csp_tool_executions_total` (counter): Tool executions by tool name and status (success/failure).
- `csp_api_cost_usd_total` (counter): Cumulative API cost from `ResultMessage.cost_usd`.
- `csp_websocket_connections` (gauge): Active WebSocket connections.
- `csp_subprocess_rss_bytes` (gauge): RSS memory per CLI subprocess.
- `csp_prewarm_pool_size` (gauge): Available pre-warmed clients.
- `csp_circuit_breaker_state` (gauge): Circuit breaker state (0=closed, 1=open, 2=half-open).

**Health checks.** The admin API exposes:
- `GET /api/v1/health/live`: Returns 200 if the FastAPI process is running. Used as a Kubernetes liveness probe.
- `GET /api/v1/health/ready`: Returns 200 if the platform can accept new sessions (pre-warm pool is non-empty or cold start is available, API key is configured, database is reachable). Used as a Kubernetes readiness probe.
- `GET /api/v1/health/startup`: Returns 200 once initial plugin discovery and pre-warming are complete. Used as a Kubernetes startup probe.

**Cost tracking and alerting.** Every `ResultMessage.cost_usd` is captured and aggregated per session and per user. The `src/claude_sdk_pattern/core/cost_tracker.py` module:
- Persists per-session cost to the database.
- Exposes per-user and platform-wide cost summaries via `GET /api/v1/admin/costs`.
- Compares cumulative cost against `CLAUDE_SDK_PATTERN_COST_ALERT_THRESHOLD_USD` (default: no threshold). When exceeded, emits a warning log and optionally sends a webhook notification to `CLAUDE_SDK_PATTERN_COST_ALERT_WEBHOOK_URL`.

### 3.13 Graceful Shutdown

When the server receives SIGTERM (e.g., during Kubernetes rolling deployment), the shutdown protocol:
1. Stop accepting new WebSocket connections and REST requests (FastAPI's lifespan shutdown begins).
2. Send `{type: "status", status: "server_shutting_down"}` to all active WebSocket connections.
3. Wait up to `CLAUDE_SDK_PATTERN_SHUTDOWN_GRACE_SECONDS` (default 30) for in-flight queries to complete. For each active session, call `client.interrupt()` if the query is still running after half the grace period.
4. Close all WebSocket connections.
5. Destroy all `ClaudeSDKClient` instances (which terminates CLI subprocesses).
6. Close database connections and flush logs.

Users who are mid-conversation receive the shutdown notification and can reconnect after deployment completes, using session resume to continue their conversation.

---

## 4. Frontend Architecture (React 19)

### 4.1 Component Hierarchy

```
ChatApp (root)
 +-- Header
 |    +-- SessionSelector
 |    +-- PluginToggle
 +-- ChatPanel (main content area)
 |    +-- MessageList
 |    |    +-- MessageBubble (text)
 |    |    +-- ToolUseCard (tool invocation + result)
 |    |    +-- StreamingIndicator (partial message)
 |    |    +-- AgentActivityCard (subagent start/stop)
 |    +-- InputBar
 |         +-- TextInput
 |         +-- AttachmentButton
 |         +-- SendButton
 |         +-- InterruptButton
 +-- SidePanel (collapsible)
 |    +-- ToolPanel (active tools list)
 |    +-- AgentPanel (active subagents)
 |    +-- PluginSlots (plugin-injected UI)
 +-- SettingsDrawer
      +-- PluginManager
      +-- SessionSettings
      +-- PermissionEditor
```

### 4.2 Plugin UI Slots

Plugins can inject UI components into predefined **slots** in the frontend layout. Each slot is a named mount point where plugin-provided React components render.

**Available slots:**
- `side-panel`: Full panel in the collapsible sidebar. Used for tool visualizations, dashboards, or configuration UIs.
- `message-renderer`: Custom renderer for specific message types. A plugin can register a renderer for its tool's output (e.g., a chart plugin renders chart data inline in the message list).
- `input-extension`: Additional controls above or below the input bar. Used for mode selectors, context pickers, or file uploaders.
- `settings-section`: Section in the settings drawer for plugin-specific configuration.
- `header-action`: Buttons or indicators in the header bar.

Plugin UI components are loaded dynamically. The plugin manifest declares the slot name and the path to a pre-built JavaScript bundle that exports a React component. The frontend's `PluginSlotRenderer` component mounts these dynamically using React's `lazy()` and `Suspense`.

**Plugin UI build pipeline.** Plugin developers build their React components as standalone JavaScript bundles using Vite (or any bundler) with React externalized. The platform provides a `@claude_sdk_pattern/plugin-sdk` npm package that:
- Exports TypeScript type definitions for the plugin component API (the props the platform passes to slot components).
- Configures React as an external dependency so plugin bundles do not duplicate it.
- Provides a `PluginContext` hook that gives plugin components access to the WebSocket connection (for sending custom messages), the session state, and the user identity.

**Dependency isolation.** React must be externalized from all plugin bundles to prevent version mismatches. The platform's Vite config exposes React and ReactDOM as globals. Plugin bundles reference these globals rather than bundling their own copies.

**Style isolation.** Plugin UI components render inside a CSS scope created by the `PluginSlotRenderer`. Each plugin's root element receives a `data-plugin="<plugin_name>"` attribute, and the platform injects a scoping rule that prevents plugin styles from leaking out. For stronger isolation, plugin developers can use CSS Modules (recommended) or shadow DOM (supported but not required). The platform does not enforce a specific CSS strategy but documents the scoping convention in the plugin development guide.

### 4.3 Streaming Display

The frontend handles three levels of message granularity:

1. **Complete messages** (`text` type): Rendered as full `MessageBubble` components. Markdown is rendered using a CommonMark-compatible library.

2. **Partial messages** (`stream_event` type): When `include_partial_messages` is enabled, the backend sends token-by-token updates. The frontend accumulates these into a buffer and renders the in-progress message with a streaming cursor. React 19's `useTransition` wraps the buffer updates to keep the UI responsive during rapid token arrival.

3. **Tool events** (`tool_use` and `tool_result` types): Rendered as `ToolUseCard` components that show the tool name, input parameters (collapsed by default), execution status (spinner while running), and result. The card animates from "executing" to "complete" when the `tool_result` arrives.

### 4.4 React 19 Features

- **useTransition**: Wraps streaming message buffer updates. Token-by-token updates are low-priority transitions that do not block user input.
- **Suspense**: Used for lazy-loading plugin UI components and for the initial session load.
- **Server Components**: Not used in v1. The frontend is a client-side SPA that communicates via WebSocket. Server components may be adopted in a future version if the frontend moves to a Next.js-based architecture.
- **use() hook**: Used to read the initial session state and plugin list from promises resolved during app initialization.

### 4.5 Accessibility

The chat UI targets WCAG 2.1 AA compliance. Key accessibility requirements:

- **ARIA live regions**: The `MessageList` component uses `aria-live="polite"` so screen readers announce new messages without interrupting the user. Tool execution status changes use `aria-live="assertive"` for important state transitions (e.g., tool failure).
- **Keyboard navigation**: All interactive elements (messages, tool cards, input bar, side panel, settings) are reachable via Tab navigation. The message list supports arrow key navigation between messages. The `InterruptButton` is keyboard-accessible with a shortcut (Ctrl+Shift+X).
- **Focus management**: When a new message arrives during active typing, focus stays on the input bar. When the user scrolls to the bottom, focus moves to the latest message only if the input bar is not focused. Focus trapping is applied to modal dialogs (settings drawer, plugin manager).
- **Color contrast**: All text meets WCAG AA contrast ratios (4.5:1 for normal text, 3:1 for large text). Status indicators (streaming, executing, error) use both color and icon/text labels so they are distinguishable without color vision.
- **Reduced motion**: The `prefers-reduced-motion` media query disables the streaming cursor animation, tool card state transitions, and panel collapse animations.

### 4.6 WebSocket Client

The frontend maintains a singleton WebSocket connection per session, managed by a `ChatConnection` class. This class:

- Establishes the connection to `/ws/v1/chat` with authentication headers.
- Dispatches incoming messages to the appropriate React state updaters via a message type router.
- Buffers outgoing messages if the connection is temporarily interrupted.
- Handles reconnection with exponential backoff. On reconnect, the client sends a `{type: "session_command", command: "sync", last_message_seq: N}` message. The backend responds with any messages the client missed since sequence number N, enabling state recovery after network interruption. Each downstream message includes a monotonically increasing `seq` field for this purpose.
- Provides an `interrupt()` method that sends an interrupt command upstream.

**State management** uses Zustand with state selectors rather than `useReducer` with a single context. This is a deliberate choice for streaming performance: during active token streaming (potentially 30+ tokens per second), a single context would re-render the entire component tree on every update. Zustand's selector model ensures that only components subscribed to the changed state slice re-render. The store is organized into slices:
- `messages` slice: The message list. Only `MessageList` and its children subscribe.
- `streaming` slice: The in-progress partial message buffer. Only `StreamingIndicator` subscribes.
- `session` slice: Session metadata (id, status, cost). Only `Header` and `SessionSelector` subscribe.
- `plugins` slice: Active plugin state. Only `SidePanel` and `PluginSlotRenderer` subscribe.
- `tools` slice: Active tool execution status. Only `ToolPanel` and `ToolUseCard` subscribe.

The `useChatConnection` hook dispatches incoming WebSocket messages to the appropriate Zustand store actions. This decouples the network layer from the state layer.

---

## 5. Plugin System Design

### 5.1 Plugin Manifest Format

Every plugin is a directory containing a `plugin.json` manifest and the plugin's implementation files.

The manifest declares:
- **manifest_version**: Schema version of the manifest format (currently `"1"`). When the platform changes the manifest schema, it increments this version. The Plugin Registry rejects manifests with unsupported versions and logs a warning with a migration guide URL.
- **identity**: name, version, description, author
- **platform_version**: Minimum compatible platform version (semver range, e.g., `">=1.0.0"`). The Plugin Registry checks this against the running platform version during validation.
- **type**: one of `tool`, `mcp`, `skill`, `endpoint`
- **capabilities**: what the plugin provides (tool definitions, MCP server config, skill paths, API routes)
- **permissions**: what tools/resources the plugin needs
- **ui** (optional): frontend component declarations with slot assignments
- **hooks** (optional): hook event registrations
- **agents** (optional): subagent definitions
- **config_schema** (optional): JSON Schema for plugin-specific configuration

### 5.2 Registration Lifecycle

```
discover --> validate --> register --> configure --> activate
    |            |            |             |            |
    |            |            |             |            +-- Plugin is live;
    |            |            |             |                capabilities injected
    |            |            |             |                into OptionsBuilder
    |            |            |             |
    |            |            |             +-- Operator provides
    |            |            |                 config values
    |            |            |                 (API keys, settings)
    |            |            |
    |            |            +-- Manifest parsed,
    |            |                plugin stored in
    |            |                Registry with
    |            |                "registered" status
    |            |
    |            +-- Manifest schema validation,
    |                dependency check,
    |                permission review
    |
    +-- Scan plugins/ directory,
        or receive upload via
        /api/v1/plugins endpoint
```

**Deactivation** reverses the process: the plugin is removed from the active set, its capabilities are withdrawn from `OptionsBuilder`, and any running MCP server subprocesses are terminated.

**Error handling**: If a plugin fails during activation (e.g., its MCP server crashes on startup), the plugin is moved to "errored" status and excluded from session configuration. The error is logged and surfaced to the operator via the admin API.

### 5.3 Four Plugin Types

#### Tool Plugins

Tool plugins provide custom `@tool`-decorated Python functions that run in-process.

- **Implementation**: A Python module containing one or more functions decorated with `@tool(name, description, params)`.
- **Registration**: The Plugin Registry imports the module, collects the `@tool` instances, and bundles them into an in-process MCP server via `create_sdk_mcp_server()`.
- **SDK integration**: The resulting `McpSdkServerConfig` is added to `ClaudeAgentOptions.mcp_servers` under the plugin's namespace.
- **Tool naming**: Tools are accessible as `mcp__<plugin_name>__<tool_name>`.

#### MCP Plugins

MCP plugins declare external MCP server connections.

- **Implementation**: The manifest specifies the MCP server configuration (transport type, command/URL, environment variables).
- **Supported transports**: stdio (local subprocess), HTTP/Streamable HTTP (remote), SSE (legacy, supported for backward compatibility).
- **Registration**: The Plugin Registry validates the configuration and stores it.
- **SDK integration**: The server config dict is added directly to `ClaudeAgentOptions.mcp_servers`.
- **Tool naming**: Tools are accessible as `mcp__<server_name>__<tool_name>`. Wildcard patterns like `mcp__<server_name>__*` can be used in `allowed_tools`.

#### Skill Plugins

Skill plugins provide markdown-based workflow extensions.

- **Implementation**: A directory containing `SKILL.md` and optional reference/example files, following the standard Claude Code skill format.
- **Registration**: The Plugin Registry copies or symlinks the skill directory into the project's `.claude/skills/` directory (or uses `add_dirs` to make it accessible).
- **SDK integration**: `setting_sources` must include `"project"` in `ClaudeAgentOptions`. The `Skill` tool must be in `allowed_tools`.
- **Invocation**: Skills are context-matched by Claude based on their description, or explicitly invoked via `/command` syntax.

#### Endpoint Plugins

Endpoint plugins expose custom HTTP endpoints through the FastAPI gateway.

- **Implementation**: A Python module defining FastAPI route handlers.
- **Registration**: The Plugin Registry imports the module and mounts its router on the FastAPI app under `/api/v1/plugins/<plugin_name>/`.
- **SDK integration**: Endpoint plugins can trigger SDK queries internally (e.g., an endpoint that accepts a webhook, processes it, and sends a prompt to Claude).
- **Use cases**: Webhook receivers, custom REST APIs that leverage Claude as a backend, health check endpoints for monitoring.

### 5.4 Plugin Isolation and Error Boundaries

- **Process isolation**: Tool plugins run in-process (they are `@tool` functions), which means a malicious or buggy tool plugin could crash the Python process, block the async event loop, or consume unbounded memory. The SDK sandbox only applies to commands executed by the CLI, not to Python tool functions. To mitigate this: tool plugins from untrusted sources should be reviewed before activation, and the platform logs all tool function execution times to detect blocking behavior. For stronger isolation in future versions, tool plugins could be moved to separate processes communicating via stdio MCP transport. MCP plugins run as subprocesses managed by the SDK. If an MCP server crashes, the SDK handles the error; it does not bring down the main process.
- **Timeout enforcement**: Each hook registration includes a `timeout` parameter. Tool execution timeouts are managed by the SDK.
- **Error propagation**: Plugin errors during session execution are caught by the Core Engine, logged, and forwarded to the frontend as error messages. The session continues with the failed plugin's tools unavailable.
- **Frontend isolation**: Plugin UI components render inside React error boundaries. A crashing plugin component does not break the main chat interface.
- **Resource limits**: In container deployments, all plugins share the container's resource allocation. The platform does not enforce per-plugin resource limits in v1; this is a future enhancement.

---

## 6. Updated Project Structure

```
claude_sdk_pattern/
+-- pyproject.toml                          # uv-managed, Python 3.12
+-- .python-version                         # 3.12
+-- src/
|   +-- claude_sdk_pattern/
|       +-- __init__.py
|       +-- main.py                         # FastAPI app entry point
|       +-- core/
|       |   +-- __init__.py
|       |   +-- engine.py                   # ClaudeSDKClient lifecycle management
|       |   +-- options_builder.py          # Builds ClaudeAgentOptions from registry
|       |   +-- session_manager.py          # Session create/resume/fork/cleanup
|       |   +-- hook_dispatcher.py          # Aggregates and dispatches hooks
|       |   +-- permission_gate.py          # can_use_tool callback implementation
|       |   +-- prompt_guard.py             # UserPromptSubmit hook for injection defense
|       |   +-- circuit_breaker.py          # API outage circuit breaker
|       |   +-- cost_tracker.py             # Per-session and per-user cost aggregation
|       +-- plugins/
|       |   +-- __init__.py
|       |   +-- registry.py                # Plugin discovery, validation, registration
|       |   +-- manifest.py                # Manifest schema and parsing
|       |   +-- loader.py                  # Dynamic plugin loading
|       |   +-- types.py                   # Plugin type definitions
|       |   +-- secret_store.py            # Encrypted plugin secret storage
|       +-- api/
|       |   +-- __init__.py
|       |   +-- auth.py                    # JWT authentication and RBAC middleware
|       |   +-- websocket.py               # /ws/v1/chat WebSocket handler
|       |   +-- sessions.py                # /api/v1/sessions REST endpoints
|       |   +-- plugins_api.py             # /api/v1/plugins REST endpoints
|       |   +-- admin.py                   # /api/v1/admin REST endpoints
|       |   +-- health.py                  # /api/v1/health liveness/readiness/startup probes
|       +-- models/
|       |   +-- __init__.py
|       |   +-- messages.py                # WebSocket message schemas
|       |   +-- session.py                 # Session metadata models
|       |   +-- plugin.py                  # Plugin metadata models
|       +-- config/
|           +-- __init__.py
|           +-- settings.py                # Application settings (env vars, defaults)
|           +-- logging.py                 # Structured logging configuration (structlog)
+-- frontend/
|   +-- package.json
|   +-- tsconfig.json
|   +-- vite.config.ts
|   +-- src/
|       +-- App.tsx                         # Root component
|       +-- components/
|       |   +-- ChatApp.tsx
|       |   +-- ChatPanel.tsx
|       |   +-- MessageList.tsx
|       |   +-- MessageBubble.tsx
|       |   +-- ToolUseCard.tsx
|       |   +-- StreamingIndicator.tsx
|       |   +-- InputBar.tsx
|       |   +-- SidePanel.tsx
|       |   +-- PluginSlotRenderer.tsx
|       |   +-- AgentActivityCard.tsx
|       +-- hooks/
|       |   +-- useChatConnection.ts
|       |   +-- usePluginSlots.ts
|       +-- store/
|       |   +-- chatStore.ts               # Zustand store with message/streaming/session/plugin slices
|       |   +-- selectors.ts               # Memoized state selectors
|       +-- types/
|           +-- messages.ts
|           +-- plugins.ts
+-- plugins/
|   +-- example-tool/
|   |   +-- plugin.json
|   |   +-- tools.py
|   +-- example-mcp/
|   |   +-- plugin.json
|   +-- example-skill/
|       +-- plugin.json
|       +-- SKILL.md
+-- docs/
|   +-- mkdocs.yml
|   +-- index.md
|   +-- architecture.md
|   +-- plugin-guide.md
|   +-- deployment.md
|   +-- api-reference.md
+-- tests/
|   +-- conftest.py
|   +-- unit/
|   |   +-- test_options_builder.py
|   |   +-- test_plugin_registry.py
|   |   +-- test_permission_gate.py
|   +-- integration/
|   |   +-- test_websocket_flow.py
|   |   +-- test_session_lifecycle.py
|   |   +-- test_plugin_loading.py
|   +-- e2e/
|       +-- test_chat_flow.py
+-- scripts/
|   +-- dev.sh                             # Start dev server (backend + frontend)
|   +-- docker-build.sh                    # Build production container
+-- docker/
|   +-- Dockerfile                         # Production container image
|   +-- docker-compose.yml                 # Local development stack
+-- .env.example                           # Template for environment variables
+-- .gitignore
+-- LICENSE                                # MIT
```

---

## 7. Data Flow

### 7.1 User Message to Streamed Response

```
User types message in InputBar
        |
        v
React dispatches via ChatConnection.send({type: "user_message", text: "..."})
        |
        v
WebSocket message arrives at FastAPI /ws/v1/chat handler
        |
        v
Handler looks up active ClaudeSDKClient for this session
  (or creates one via SessionManager if new session)
        |
        v
OptionsBuilder queries PluginRegistry
  -> merges mcp_servers from all active MCP and tool plugins
  -> merges allowed_tools from all plugins + operator config
  -> merges hooks from HookDispatcher
  -> sets can_use_tool to PermissionGate callback
  -> sets sandbox, model, max_turns, etc.
  -> returns ClaudeAgentOptions
        |
        v
client.query(user_message) is called
        |
        v
Claude Agent SDK sends message to CLI subprocess
  CLI subprocess calls Claude API, streams response
        |
        v
async for message in client.receive_response():
        |
        +--[AssistantMessage with TextBlock]
        |       -> send WebSocket: {type: "text", content: "..."}
        |
        +--[AssistantMessage with ToolUseBlock]
        |       -> send WebSocket: {type: "tool_use", tool: "...", input: {...}}
        |       (SDK executes tool, then yields ToolResultBlock)
        |       -> send WebSocket: {type: "tool_result", result: "..."}
        |
        +--[StreamEvent (partial)]
        |       -> send WebSocket: {type: "stream_event", delta: "..."}
        |
        +--[ResultMessage]
                -> capture session_id, cost_usd
                -> send WebSocket: {type: "result", session_id: "...", cost: 0.05}
                -> if structured_output present, include in result
        |
        v
Frontend MessageList renders each message as it arrives
  ToolUseCard shows execution status in real-time
  StreamingIndicator shows partial text with cursor
```

### 7.2 Plugin Registration Flow

```
Operator places plugin directory in plugins/
  (or uploads via POST /api/v1/plugins)
        |
        v
PluginRegistry.discover() scans plugins/ directory
  -> finds plugin.json manifests
        |
        v
PluginRegistry.validate(manifest)
  -> checks schema, required fields, version compatibility
  -> checks declared permissions against operator policy
        |
        v
PluginRegistry.register(plugin)
  -> stores plugin metadata with status "registered"
        |
        v
Operator configures plugin via PUT /api/v1/plugins/{name}/config
  -> provides API keys, environment variables, settings
        |
        v
PluginRegistry.activate(plugin)
  -> for tool plugins: imports module, collects @tool functions, calls create_sdk_mcp_server()
  -> for MCP plugins: validates server config is reachable
  -> for skill plugins: copies/symlinks SKILL.md to .claude/skills/
  -> for endpoint plugins: mounts FastAPI router
  -> status changes to "active"
        |
        v
Next session creation picks up the new plugin's capabilities
  via OptionsBuilder
```

---

## 8. Configuration System

### 8.1 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
| `ANTHROPIC_BASE_URL` | No | Override API endpoint (for proxy deployments) |
| `CLAUDE_SDK_PATTERN_SECRET_KEY` | Yes | Secret for session token signing |
| `CLAUDE_SDK_PATTERN_DB_URL` | No | Database URL for session metadata (default: SQLite) |
| `CLAUDE_SDK_PATTERN_PLUGINS_DIR` | No | Plugin directory path (default: `./plugins`) |
| `CLAUDE_SDK_PATTERN_MAX_SESSIONS` | No | Maximum concurrent sessions (default: 10) |
| `CLAUDE_SDK_PATTERN_SESSION_TIMEOUT` | No | Idle session timeout in seconds (default: 1800) |
| `CLAUDE_SDK_PATTERN_SANDBOX_ENABLED` | No | Enable SDK sandbox (default: true) |
| `CLAUDE_SDK_PATTERN_DEFAULT_MODEL` | No | Default Claude model (default: "claude-sonnet-4-5") |
| `CLAUDE_SDK_PATTERN_MAX_BUDGET_USD` | No | Per-session cost cap (default: none) |
| `CLAUDE_SDK_PATTERN_MAX_TURNS` | No | Maximum agent turns per query (default: 20) |
| `CLAUDE_SDK_PATTERN_LOG_LEVEL` | No | Logging level (default: INFO) |
| `CLAUDE_SDK_PATTERN_PREWARM_POOL_SIZE` | No | Number of pre-warmed SDK clients (default: 2) |
| `CLAUDE_SDK_PATTERN_MAX_SESSION_DURATION_SECONDS` | No | Maximum session duration before forced cleanup (default: 14400 = 4h) |
| `CLAUDE_SDK_PATTERN_MAX_SESSION_RSS_MB` | No | RSS threshold per subprocess before graceful restart (default: 4096) |
| `CLAUDE_SDK_PATTERN_QUERY_TIMEOUT_SECONDS` | No | Wall-clock timeout per query before auto-interrupt (default: 600) |
| `CLAUDE_SDK_PATTERN_ALLOWED_ORIGINS` | No | CORS allowed origins, comma-separated (default: http://localhost:5173) |
| `CLAUDE_SDK_PATTERN_MAX_MESSAGE_LENGTH` | No | Maximum user message length in characters (default: 32000) |
| `CLAUDE_SDK_PATTERN_COST_ALERT_THRESHOLD_USD` | No | Cost alert threshold (default: none) |
| `CLAUDE_SDK_PATTERN_COST_ALERT_WEBHOOK_URL` | No | Webhook URL for cost alerts (default: none) |
| `CLAUDE_SDK_PATTERN_SHUTDOWN_GRACE_SECONDS` | No | Graceful shutdown wait time (default: 30) |
| `HTTP_PROXY` / `HTTPS_PROXY` | No | Route SDK traffic through proxy |

### 8.2 Application Settings

The `src/claude_sdk_pattern/config/settings.py` module uses Pydantic `BaseSettings` to load configuration from environment variables and an optional `.env` file. Settings are typed, validated, and accessible throughout the application via dependency injection.

### 8.3 Plugin Manifests

Plugin configuration lives in `plugin.json` within each plugin directory. The manifest schema is defined in `src/claude_sdk_pattern/plugins/manifest.py` and validated at registration time.

### 8.4 SDK Configuration

The `ClaudeAgentOptions` instance is built fresh for each session by `OptionsBuilder`. It is not cached because the active plugin set may change between sessions. Key SDK parameters:

- `model`: Set from `CLAUDE_SDK_PATTERN_DEFAULT_MODEL` or per-session override
- `max_turns`: Set from `CLAUDE_SDK_PATTERN_MAX_TURNS`
- `max_budget_usd`: Set from `CLAUDE_SDK_PATTERN_MAX_BUDGET_USD`
- `sandbox`: Set from `CLAUDE_SDK_PATTERN_SANDBOX_ENABLED`
- `permission_mode`: Set to `"acceptEdits"` rather than `"default"`. The `"default"` mode attempts interactive terminal prompts which do not work in a headless web deployment (no TTY). The `"acceptEdits"` mode auto-accepts edit operations while the `can_use_tool` callback and `PreToolUse` hook handle all authorization decisions programmatically
- `include_partial_messages`: Set to `True` for streaming display
- `setting_sources`: Set to `["project"]` when skill plugins are active
- `cwd`: Set to the session's working directory
- `env`: Merged from platform environment and plugin-declared environment variables

---

## 9. Scaling Considerations

### The Subprocess Constraint

The Claude Agent SDK operates by spawning the Claude Code CLI as a subprocess. This is not a lightweight API call -- it is a long-running process that maintains shell state, filesystem context, and conversation history. This has direct implications for scaling:

- **One subprocess per session**: Each active chat session requires one CLI subprocess. The official docs recommend 1 GiB RAM per instance as a minimum, but real-world evidence shows memory growing to 2.5+ GiB per session in typical use and up to 24-26 GiB in extended sessions (GitHub issue anthropics/claude-code#13126). With realistic overhead from FastAPI, the Plugin Registry, and MCP subprocesses, a conservative estimate is **4-8 concurrent sessions** on a 16 GiB / 8 vCPU machine. The `CLAUDE_SDK_PATTERN_MAX_SESSIONS` setting should be tuned based on observed RSS per session in the operator's workload.

- **Horizontal scaling via containers**: The recommended approach is to run each session in its own container (the "ephemeral session" pattern from the official hosting docs). Container orchestrators (Kubernetes, ECS, Fly Machines) handle scheduling and scaling.

- **Session affinity**: Because each `ClaudeSDKClient` instance holds a subprocess, sessions are bound to their host machine. Load balancers must use session affinity (sticky sessions) or route session-specific requests to the correct container.

- **Cost model**: The dominant cost is API tokens, not compute. Container hosting costs approximately $0.05/hour per instance. API token costs depend on usage but typically exceed compute costs by 10-100x.

### Recommended Deployment Patterns

For **low-scale** deployments (1-10 concurrent users): A single server running the FastAPI app with multiple `ClaudeSDKClient` instances. The `CLAUDE_SDK_PATTERN_MAX_SESSIONS` setting caps concurrency.

For **medium-scale** deployments (10-100 concurrent users): Container-per-session using a sandbox provider (Modal, E2B, Fly Machines, Cloudflare Sandboxes). A central gateway routes WebSocket connections to the appropriate container. Session metadata is stored in a shared database.

For **high-scale** deployments (100+ concurrent users): Kubernetes cluster with a custom operator that manages container lifecycle. Session state externalized to a database. Container auto-scaling based on session count. A proxy layer handles credential injection and network controls.

---

## 10. Addressing P0/P1 Gaps from Architecture Analysis

The architecture analysis identified several critical gaps. This section maps each gap to where it is addressed in this design.

| Gap | Priority | Resolution |
|-----|----------|------------|
| Subagents / AgentDefinition | P0 | Section 3.7 -- Plugins can declare subagents; OptionsBuilder merges them into `ClaudeAgentOptions.agents` |
| Hooks system | P0 | Section 3.5 -- HookDispatcher aggregates hooks from core and plugins; PreToolUse used for security |
| Structured outputs | P0 | Section 3.6 -- OutputFormat support via `output_format` parameter on ClaudeAgentOptions |
| Session management (resume/fork) | P1 | Section 3.4 -- SessionManager handles resume, fork_session, and continue_conversation |
| Expanded ClaudeAgentOptions | P1 | Section 8.4 -- OptionsBuilder sets all relevant parameters including model, max_budget_usd, sandbox, env, add_dirs |
| Message types documentation | P1 | Section 3.3 -- WebSocket protocol documents all message types from SDK (AssistantMessage, TextBlock, ToolUseBlock, ToolResultBlock, StreamEvent, ResultMessage) |
| can_use_tool permission callback | P2 | Section 3.9 -- PermissionGate implements the can_use_tool callback with correct SDK signature (PermissionResultAllow/PermissionResultDeny with input sanitization) |
| ClaudeSDKClient vs query() distinction | P2 | Section 3.1 -- Explicitly uses ClaudeSDKClient as the primary interface, with rationale |
| SSE transport deprecation | P2 | Section 5.3 (MCP Plugins) -- Notes SSE as legacy, recommends HTTP/Streamable HTTP |
| Sandbox configuration | P2 | Section 3.8 -- SandboxSettings integration with container deployment pattern |
| File checkpointing | P3 | Not addressed in v1. Can be added as a plugin that enables `enable_file_checkpointing` and exposes `rewind_files()` via a custom endpoint |
| Tool search | P3 | Not addressed in v1. Can be enabled by setting `ENABLE_TOOL_SEARCH` environment variable when tool count is high |

---

## 11. Open Design Decisions

These items require further discussion before implementation:

1. **Database choice for session metadata**: SQLite for single-server, PostgreSQL for multi-server. The `SessionManager` uses an abstract repository interface so the backing store can be swapped.

2. **Plugin distribution format**: v1 uses filesystem directories. Future versions may support a package registry (similar to npm) for plugin distribution.

3. **Multi-tenancy model**: v1 assumes a single operator with multiple users. True multi-tenancy (isolated plugin sets per tenant, per-tenant API keys, per-tenant budgets) requires additional namespace isolation in the Plugin Registry and a tenant-aware authorization model.

4. **Frontend build and deployment**: v1 builds the React app as a static SPA served by FastAPI's `StaticFiles`. Future versions may adopt a dedicated CDN or SSR framework.

5. **WebSocket vs SSE**: The current design uses WebSocket for all streaming. An alternative is SSE for server-to-client streaming (the high-volume path) combined with REST for upstream commands (user messages, interrupts). SSE offers simpler proxy compatibility, automatic browser reconnection, and HTTP/2 multiplexing. WebSocket provides lower latency for bidirectional messages. The WebSocket choice is maintained in v1 because the interrupt command and plugin_config messages benefit from a persistent bidirectional channel, but this should be revisited if proxy compatibility issues arise in production.

6. **Testing strategy**: The test structure is defined but the testing approach needs specification: how to test plugins in isolation (mock registry and SDK stub), how to integration-test with the real SDK (recorded responses or capped API budget), how to test WebSocket flows (async test client), and how to test frontend components (Vitest with React Testing Library). A `conftest.py` with SDK stubs and a plugin test harness should be the first implementation deliverable.

7. **Internationalization**: v1 is English-only. All user-facing strings in the frontend should be externalized into a locale file from the start to avoid a costly retrofit later.

---

## 12. Review Response Matrix

This section tracks how each finding from the architecture review (v1.0) was addressed in v1.1.

| Review Finding | Severity | Resolution in v1.1 |
|----------------|----------|---------------------|
| Subprocess lifecycle (20-30s init, memory growth to 24 GiB) | Critical | Section 3.1: Pre-warming pool, session duration limits, RSS monitoring, cache cleanup |
| Security design missing (auth, CORS, rate limiting, prompt injection, secrets) | Critical | Section 3.10: JWT+RBAC auth, CORS allowlist, two-layer rate limiting, UserPromptSubmit hook, Fernet-encrypted secret store |
| Error recovery undefined for subprocess crashes | Critical | Section 3.11: ProcessError catch with session resume, circuit breaker for API outages, plugin failure handling, auto-interrupt for hung queries |
| can_use_tool callback signature incorrect | High | Section 3.9: Corrected to `(tool_name, input_data, context) -> PermissionResultAllow/Deny` with `updated_input` for sanitization |
| Frontend state management bottleneck (useReducer re-renders) | High | Section 4.6: Replaced with Zustand store with 5 state slices and selectors |
| UserPromptSubmit hook missing from hooks table | High | Section 3.5: Added to hooks table; Section 3.10: Detailed prompt_guard implementation |
| No observability (logging, metrics, health checks, tracing) | High | Section 3.12: structlog JSON logging, Prometheus metrics (10 key metrics), 3 health probe endpoints, cost tracking |
| No graceful shutdown protocol | Medium | Section 3.13: SIGTERM handler with connection draining, interrupt for in-flight queries, configurable grace period |
| permission_mode="default" may prompt in headless env | Medium | Section 8.4: Changed to "acceptEdits" with programmatic authorization |
| No API versioning | Medium | All endpoints prefixed with /api/v1/ and /ws/v1/ |
| Resource estimates too optimistic | Medium | Section 3.8, Section 9: Updated to 4 GiB per container, 4-8 concurrent sessions per 16 GiB server |
| Plugin UI build pipeline undefined | Medium | Section 4.2: Plugin SDK npm package, React externalization, CSS scoping convention |
| No accessibility design | Medium | Section 4.5: WCAG AA targets, ARIA live regions, keyboard navigation, focus management, reduced motion |
| Plugin manifest versioning missing | Low | Section 5.1: manifest_version and platform_version fields added |
| Plugin state not persisted across restarts | Low | Section 3.2: Registry state persisted to database with filesystem reconciliation on startup |
| Tool plugin isolation weak (in-process) | Low | Section 5.4: Documented risk, added review requirement, logged execution times, future path to subprocess isolation |
| Subagent resume unverified | Low | Section 3.7: Marked as experimental behind feature flag |
| WebSocket reconnection state recovery | Low | Section 4.6: Message sequence numbers with sync-on-reconnect protocol |
