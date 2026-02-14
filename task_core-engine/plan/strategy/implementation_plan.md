# Implementation Plan: Core Engine MVP

> **Feature**: core-engine
> **Date**: 2026-02-14
> **Authority**: ADR-001 (Platform Strategy), ADR-002 (Technical Architecture)
> **Primary Output**: Integration contracts for downstream implementation

---

## 1. Problem Statement Summary

### Goal

Build the production operations layer for Claude Agent SDK: a Python/FastAPI backend that wraps SDK CLI subprocesses, exposes AG-UI protocol for frontends, OpenAI-compliant streaming API for server-to-server agentic calls, and REST API for data operations. Deploy as a single Docker container on 16GB host supporting 10 concurrent sessions with sub-3-second session start via pre-warming pool.

### Success Criteria

| Criteria | Target | Measurement |
|----------|--------|-------------|
| Time to first response (pre-warmed) | < 3 seconds | Session assignment + first AG-UI text event |
| Time to first response (cold start) | < 35 seconds | Subprocess init + first AG-UI text event |
| Concurrent sessions | Up to 10 on 16GB host | Load test with memory monitoring |
| Session crash rate | < 0.1% | Crashed / total per day |
| AG-UI event delivery latency | < 200ms | SDK event to AG-UI event delivery |
| OpenAI API first chunk latency | < 3 seconds (pre-warmed) | Request to first SSE chunk |
| Docker startup to first chat | < 90 seconds | Startup probe pass time |

---

## 2. Reference Documents

| Document | Path | Purpose |
|----------|------|---------|
| Architecture | `task_core-engine/plan/strategy/architecture.md` | Component diagrams, data flow, error handling matrix |
| Decision Log | `task_core-engine/plan/decision-log.md` | Technology decisions with rationale |
| Feature Spec | `task_core-engine/specs/feature-spec.md` | Requirements, constraints, guardrails |
| User Stories | `task_core-engine/specs/user-stories.md` | Acceptance criteria |
| Edge Cases | `task_core-engine/specs/edge-case-resolutions.md` | Design decisions for 36 HIGH risk cases |
| Control Flows | `task_core-engine/specs/control-flows/*.md` | Step-by-step flows for US-001, US-002, US-004, US-008 |
| ADR-001 | `docs/adr/ADR-001-platform-strategy.md` | Platform and language decisions |
| ADR-002 | `docs/adr/ADR-002-technical-architecture.md` | Technical architecture decisions D3-D10 |

---

## 3. Feature Planning Details

### 3.1 Backend Core Components

#### SessionManager

- **File**: `src/core/session_manager.py`
- **Responsibility**: Orchestrate session lifecycle (create, query, interrupt, destroy, resume)
- **Dependencies**: PreWarmPool, SubprocessMonitor, JSONSessionIndex, ExtensionLoader
- **Key behaviors**:
  - `create_session()` attempts pool assignment first, cold start fallback
  - `query(session_id, prompt)` delegates to ClaudeSDKClient.query(), yields SDK stream events
  - `interrupt(session_id)` calls client.interrupt()
  - `destroy_session(session_id)` cleans up subprocess, updates index
  - `resume_session(session_id)` creates new client with `resume=session_id` parameter
  - Enforces one active run per session_id (G-003)
  - Enforces max 10 concurrent sessions (Decision 10)
- **User Stories**: US-001, US-002, US-004, US-006, US-009

#### PreWarmPool

- **File**: `src/core/prewarm_pool.py`
- **Responsibility**: Maintain pool of pre-initialized ClaudeSDKClient instances in asyncio.Queue
- **Key behaviors**:
  - `fill(size)` initializes N clients on startup; blocks readiness probe until at least 1 succeeds (G-002)
  - `get()` returns pre-warmed client or None (non-blocking)
  - `replenish()` background task to fill empty slots; 5-min backoff on rate limit (EC-014)
  - Pool size configurable via `PREWARM_POOL_SIZE` env var (default 2)
  - Pool slots count toward 10-session max
- **User Stories**: US-001

#### SubprocessMonitor

- **File**: `src/core/subprocess_monitor.py`
- **Responsibility**: Monitor session subprocess health; enforce limits; cleanup
- **Key behaviors**:
  - `check_rss()` reads `/proc/<pid>/status` VmRSS every 30s; threshold 2GB (configurable)
  - `check_duration()` compares elapsed vs max every 60s; warning at 90%, terminate at 100%
  - `cleanup_zombies()` scans child processes every 60s; kills orphans; reaps zombies
  - `check_disk()` monitors ~/.claude/ disk usage every 300s; cleanup at 80%, restart at 100%
  - Graceful restart: wait for in-flight query (up to 30s), then SIGTERM, wait 5s, SIGKILL
  - Emits AG-UI custom events for session_warning, session_restarting, session_terminated
- **User Stories**: US-004

#### JSONSessionIndex

- **File**: `src/core/session_index.py`
- **Responsibility**: Persist session metadata as JSON files with atomic I/O
- **Key behaviors**:
  - `init()` creates directory and empty index on first startup (EC-NEW-001)
  - `read(session_id)` returns session metadata
  - `write(session_id, metadata)` atomic write: temp file + rename with file lock
  - `list()` returns all sessions sorted by last_active_at
  - `cleanup_old(days=30)` removes entries for terminated sessions older than threshold
  - Recovery: on corrupted JSON, attempts .bak file recovery, else re-creates empty (EC-NEW-011)
- **User Stories**: US-006, US-009

#### ExtensionLoader

- **File**: `src/core/extension_loader.py`
- **Responsibility**: Scan filesystem for mcp.json, skills, commands; pass config to SDK
- **Key behaviors**:
  - `scan()` reads mcp.json, scans ./skills/, scans ./commands/ (called on startup + each new session)
  - Returns config suitable for ClaudeAgentOptions (mcp_servers, setting_sources)
  - Sanitizes extension env vars (blocklist: LD_PRELOAD, LD_LIBRARY_PATH, PATH, PYTHONPATH, NODE_PATH)
  - Logs parse errors gracefully; session starts without failed extensions
- **User Stories**: US-010

#### OptionsBuilder

- **File**: `src/core/options_builder.py`
- **Responsibility**: Build ClaudeAgentOptions from extensions + platform defaults + session overrides
- **Key behaviors**:
  - Merges mcp_servers from ExtensionLoader
  - Sets setting_sources for skill discovery
  - Applies platform defaults: permission_mode="acceptEdits", max_turns=20
  - Applies session overrides: resume, model selection
  - For OpenAI API sessions: adapts allowed_tools based on request.tools

### 3.2 API Layer

#### AG-UI Endpoint

- **File**: `src/api/agui_endpoint.py`
- **Responsibility**: Handle AG-UI protocol interactions between frontend and agent
- **Key behaviors**:
  - Receives RunAgentInput (thread_id, run_id, messages, tools, context, state)
  - Translates SDK stream events to AG-UI events via ag_ui.encoder.EventEncoder
  - Supports run actions: start, cancel, resume (human-in-the-loop)
  - Emits custom events for platform notifications (session_warning, session_terminated)
  - Returns StreamingResponse with SSE content type

#### OpenAI-Compliant API Endpoint

- **File**: `src/api/openai_endpoint.py`
- **Responsibility**: Provide OpenAI-compatible chat completions endpoint for server-to-server
- **Key behaviors**:
  - Parses OpenAI request format (model, messages, stream, tools, max_tokens)
  - Ignores unsupported parameters silently (EC-NEW-008)
  - Streaming mode: SSE with choices[].delta.content chunks + [DONE] sentinel
  - Non-streaming mode: single JSON response with choices[].message.content
  - Manages short-lived sessions (acquire from pool, release after response)

#### OpenAI Adapter

- **File**: `src/api/openai_adapter.py`
- **Responsibility**: Translate between OpenAI message format and SDK prompt format; translate SDK events to OpenAI SSE chunks
- **Key behaviors**:
  - `messages_to_prompt(messages)` converts OpenAI messages array to SDK prompt string
  - `sdk_event_to_chunk(event)` translates SDK stream events to OpenAI delta format
  - `format_error(status, message)` produces OpenAI-format error responses
  - `format_usage(result)` extracts token usage from ResultMessage

#### REST API Endpoints

- **File**: `src/api/rest_endpoints.py`
- **Responsibility**: Standard REST for session CRUD, health, extensions
- **Key behaviors**:
  - All endpoints documented in Section 4.1
  - No authentication required (Decision 8)
  - JSON responses with consistent error format

### 3.3 Frontend Components

#### Zustand Stores

- **File**: `frontend/src/stores/`
  - `chatStore.ts` -- messages per session, optimistic UI
  - `sessionStore.ts` -- active session, session list, lifecycle state
  - `toolStore.ts` -- tool call state, approval dialogs
  - `uiStore.ts` -- loading state, error state, input focus

#### AG-UI Client

- **File**: `frontend/src/lib/agui-client.ts`
- **Responsibility**: Connect to AG-UI endpoint, parse SSE events, dispatch to Zustand stores
- **Key behaviors**:
  - Uses fetch + ReadableStream (or EventSource) for SSE consumption
  - Dispatches events to appropriate Zustand store by event type
  - Handles custom events (session_warning, session_terminated)
  - Manages run lifecycle (start, cancel, resume)

#### React Components

- `ChatPanel.tsx` -- main chat container
- `MessageList.tsx` -- renders messages from chatStore
- `MessageBubble.tsx` -- individual message (user or assistant)
- `ToolUseCard.tsx` -- collapsible tool call display (name, status, result)
- `InputBar.tsx` -- text input with Enter to send, interrupt shortcut
- `SessionList.tsx` -- sidebar with session list, create new, switch
- `ApprovalDialog.tsx` -- human-in-the-loop tool approval (US-011)
- `ErrorBanner.tsx` -- contextual error messages (US-007)
- `SessionWarning.tsx` -- duration/memory warning banner

### 3.4 Infrastructure

#### Dockerfile

- **File**: `Dockerfile`
- **Responsibility**: Single container with backend + frontend static assets
- **Key behaviors**:
  - Multi-stage build: frontend build stage (Vite) + backend runtime stage (Python)
  - FastAPI serves frontend static files + API endpoints
  - Health check: `GET /api/v1/health/live`
  - Env vars for configuration (see Section 4.4)

---

## 4. Integration Contracts

### 4.1 API Endpoints

#### AG-UI Endpoint

```
POST /agent/run
Content-Type: application/json
Accept: text/event-stream

Request (RunAgentInput):
  thread_id: string          -- Session/thread identifier
  run_id: string             -- Unique run identifier (client-generated UUID)
  messages: Message[]        -- Conversation history
  tools: ToolDefinition[]    -- Available tools (from extension config)
  context: ContextItem[]     -- Additional context
  state: object              -- Client state snapshot
  forwarded_props: object    -- Additional properties

Response: SSE stream of AG-UI events (see Section 4.2)

Error Responses:
  404: {"error": "Session not found"}
  409: {"error": "Run already in progress for this session"}  (EC-NEW-004)
  503: {"error": "Server at capacity"}
```

#### OpenAI-Compliant Chat Completions

```
POST /v1/chat/completions
Content-Type: application/json

Request:
  model: string              -- Model identifier (mapped internally to Claude)
  messages: OpenAIMessage[]  -- Array of {role, content} objects
  stream: boolean            -- true for SSE, false for sync (default: false)
  tools: OpenAITool[]        -- Optional tool definitions
  max_tokens: integer        -- Optional token limit
  temperature: number        -- Optional (silently ignored if unsupported)

Response (stream: true): SSE stream
  data: {"id":"chatcmpl-xxx","choices":[{"index":0,"delta":{"content":"text"}}]}
  data: {"id":"chatcmpl-xxx","choices":[{"index":0,"delta":{"tool_calls":[...]}}]}
  data: {"id":"chatcmpl-xxx","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{...}}
  data: [DONE]

Response (stream: false): JSON
  {"id":"chatcmpl-xxx","choices":[{"index":0,"message":{"role":"assistant","content":"text"}}],"usage":{...}}

Error Responses:
  400: {"error":{"type":"invalid_request","message":"..."}}
  503: {"error":{"type":"server_error","message":"Service temporarily at capacity. Retry in 30 seconds."}}
       Header: Retry-After: 30
  500: {"error":{"type":"server_error","message":"..."}}
  429: {"error":{"type":"rate_limit","message":"..."}}
```

#### REST API

```
GET /api/v1/sessions
Response: {"sessions": [SessionSummary]}

POST /api/v1/sessions
Request: {"resume_session_id": string (optional)}
Response (201): {"session_id": string, "status": "ready"|"creating", "source": "pre-warm"|"cold", "estimated_seconds": number (if creating)}
Response (503): {"error": "Server at capacity. Maximum 10 sessions."}

GET /api/v1/sessions/{session_id}
Response: SessionDetail
Response (404): {"error": "Session not found"}

DELETE /api/v1/sessions/{session_id}
Response (204): (no body)
Response (404): {"error": "Session not found"}

GET /api/v1/sessions/{session_id}/tool-results/{tool_use_id}
Response: {"tool_use_id": string, "content": string, "truncated": false}
Response (404): {"error": "Tool result not found"}

GET /api/v1/health/live
Response: {"status": "ok"}

GET /api/v1/health/ready
Response: {"status": "ready"|"not_ready", "pool_depth": number, "active_sessions": number, "max_sessions": number}
Response (503 if not ready): {"status": "not_ready", "reason": "Pool empty"}

GET /api/v1/extensions
Response: {"mcp_servers": [MCPServerInfo], "skills": [SkillInfo], "commands": [CommandInfo]}
```

### 4.2 Frontend-Backend Data Contracts

#### AG-UI Event Types (Backend -> Frontend)

**Lifecycle Events**:
```
RunStartedEvent:
  type: "RUN_STARTED"
  thread_id: string
  run_id: string

RunFinishedEvent:
  type: "RUN_FINISHED"
  thread_id: string
  run_id: string

RunErrorEvent:
  type: "RUN_ERROR"
  thread_id: string
  run_id: string
  error: {type: string, message: string}
```

**Text Message Events**:
```
TextMessageStartEvent:
  type: "TEXT_MESSAGE_START"
  message_id: string
  role: "assistant"

TextMessageContentEvent:
  type: "TEXT_MESSAGE_CONTENT"
  message_id: string
  delta: string                -- Text chunk

TextMessageEndEvent:
  type: "TEXT_MESSAGE_END"
  message_id: string
```

**Tool Call Events**:
```
ToolCallStartEvent:
  type: "TOOL_CALL_START"
  tool_call_id: string
  tool_call_name: string       -- e.g. "mcp__github__list_issues"
  parent_message_id: string

ToolCallArgsEvent:
  type: "TOOL_CALL_ARGS"
  tool_call_id: string
  delta: string                -- JSON args chunk

ToolCallEndEvent:
  type: "TOOL_CALL_END"
  tool_call_id: string

ToolResultEvent:
  type: "TOOL_RESULT"
  tool_call_id: string
  content: string              -- Result text (truncated if >1MB)
  truncated: boolean           -- If true, full result at REST endpoint
```

**State Events**:
```
StateSnapshotEvent:
  type: "STATE_SNAPSHOT"
  snapshot: object             -- Full agent state

StateDeltaEvent:
  type: "STATE_DELTA"
  delta: JSONPatch[]           -- Incremental state changes
```

**Custom Events (Platform-Specific)**:
```
CustomEvent:
  type: "CUSTOM"
  name: string                 -- Event name (see below)
  value: object                -- Event payload

Custom event names and payloads:

"session_warning":
  value: {reason: "duration"|"memory", remaining_seconds: number, message: string}

"session_terminated":
  value: {reason: "duration_limit"|"memory_limit"|"error", message: string, resume_session_id: string}

"session_restarting":
  value: {reason: "memory_limit", message: string}

"session_resumed":
  value: {session_id: string, message: string}
```

#### AG-UI Client Actions (Frontend -> Backend)

**Start Run**:
```
POST /agent/run with RunAgentInput body
```

**Cancel Run**:
```
Mechanism: Client aborts the HTTP request (closes the SSE connection)
Backend detects disconnect, aborts the in-flight run
```

**Resume Run (Human-in-the-loop)**:
```
POST /agent/run with RunAgentInput including:
  messages: [...previous, {role: "tool_result", tool_use_id: string, content: string, is_error: boolean}]
```

#### Zustand Store Shapes

```
ChatStore:
  messages: Record<string, ChatMessage[]>  -- keyed by session_id
  addUserMessage(sessionId, text): void
  addAssistantMessage(sessionId, messageId, content): void
  addToolCall(sessionId, toolCallId, toolName, status, result): void
  updateToolCall(sessionId, toolCallId, updates): void

SessionStore:
  sessions: SessionSummary[]
  activeSessionId: string | null
  runState: "idle" | "running" | "error"
  setActiveSession(sessionId): void
  createSession(): Promise<string>
  refreshSessions(): Promise<void>

ToolStore:
  pendingApprovals: ApprovalRequest[]
  approveToolCall(toolCallId): void
  rejectToolCall(toolCallId): void

UIStore:
  isSending: boolean
  error: {message: string, action: string} | null
  warning: {message: string, remainingSeconds: number} | null
  clearError(): void
  clearWarning(): void
```

### 4.3 Component Integration Specs

#### SessionManager <-> PreWarmPool

```
Interface:
  PreWarmPool.get() -> ClaudeSDKClient | None
  PreWarmPool.replenish() -> None (background task)
  PreWarmPool.size() -> int (current pool depth)
  PreWarmPool.fill(target: int) -> bool (at least 1 success required)

Contract:
  - get() is non-blocking; returns None if pool empty
  - replenish() runs as asyncio.Task; does not block caller
  - fill() blocks until at least 1 client initialized OR all attempts fail
  - Each client in pool has a ClaudeAgentOptions built by OptionsBuilder
```

#### SessionManager <-> SubprocessMonitor

```
Interface:
  SubprocessMonitor.register(session_id, pid) -> None
  SubprocessMonitor.unregister(session_id) -> None
  SubprocessMonitor.start() -> None (launches background tasks)
  SubprocessMonitor.stop() -> None (cancels background tasks)

Contract:
  - register() called when session created (after subprocess PID captured)
  - unregister() called when session destroyed
  - Monitor emits events via callback: on_warning(session_id, event), on_terminate(session_id, reason)
  - SessionManager handles callbacks: notify user via AG-UI, trigger restart/cleanup
```

#### SessionManager <-> JSONSessionIndex

```
Interface:
  JSONSessionIndex.init() -> None (create dir + file if missing)
  JSONSessionIndex.create(session_id, metadata) -> None
  JSONSessionIndex.update(session_id, updates) -> None
  JSONSessionIndex.get(session_id) -> SessionMetadata | None
  JSONSessionIndex.list() -> list[SessionMetadata]
  JSONSessionIndex.delete(session_id) -> None

Contract:
  - All write operations are atomic (temp file + rename)
  - All write operations acquire file lock via filelock
  - Read operations do not require lock (atomic rename guarantees consistency)
  - SessionMetadata includes: session_id, status, created_at, last_active_at, message_count, title, terminated_reason
```

#### AG-UI Endpoint <-> SessionManager

```
Interface:
  SessionManager.query(session_id, prompt) -> AsyncIterator[SDKEvent]
  SessionManager.interrupt(session_id) -> None
  SessionManager.is_run_active(session_id) -> bool

Contract:
  - query() yields SDK stream events as they arrive
  - AG-UI endpoint translates each SDK event to AG-UI event type
  - If is_run_active() returns True, reject new run with error (G-003)
  - interrupt() sends abort signal; subsequent events may still arrive before stream ends
```

#### OpenAI Endpoint <-> SessionManager

```
Interface:
  SessionManager.acquire_session() -> tuple[session_id, ClaudeSDKClient] | None
  SessionManager.release_session(session_id) -> None
  SessionManager.query(session_id, prompt) -> AsyncIterator[SDKEvent]

Contract:
  - acquire_session() gets a session for the API call (from pool or creates new)
  - Returns None if at capacity (endpoint returns 503)
  - release_session() returns session to pool or destroys it
  - OpenAI endpoint manages session lifecycle (acquire -> query -> release) per request
```

#### ExtensionLoader <-> OptionsBuilder

```
Interface:
  ExtensionLoader.scan() -> ExtensionConfig
  ExtensionConfig:
    mcp_servers: dict[str, MCPServerConfig]
    skill_directories: list[str]
    commands: list[CommandConfig]
    env_vars: dict[str, str] (sanitized)

Contract:
  - scan() re-reads filesystem each call (cheap, < 1ms)
  - OptionsBuilder merges ExtensionConfig into ClaudeAgentOptions
  - Invalid mcp.json: returns empty mcp_servers, logs error
  - Missing directories: returns empty lists, no error
```

### 4.4 User Input Specs

#### Environment Variables (Platform Configuration)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ANTHROPIC_API_KEY` | string | required | Claude API key |
| `PREWARM_POOL_SIZE` | int | 2 | Number of pre-warmed sessions |
| `MAX_SESSIONS` | int | 10 | Maximum concurrent sessions |
| `MAX_SESSION_DURATION_SECONDS` | int | 14400 | Session duration limit (4h) |
| `MAX_SESSION_RSS_MB` | int | 2048 | RSS threshold for graceful restart |
| `SESSION_INDEX_DIR` | string | ~/.claude-web/sessions | Session index file location |
| `HOST` | string | 0.0.0.0 | Server bind address |
| `PORT` | int | 8000 | Server port |
| `CORS_ORIGINS` | string | * | Allowed CORS origins (comma-separated) |
| `LOG_LEVEL` | string | INFO | Logging level |

#### Chat Input Validation (Frontend -> Backend)

| Field | Validation | Error Message |
|-------|------------|---------------|
| message text | Non-empty, max 32,000 chars | "Message cannot be empty" / "Message too long (max 32,000 characters)" |
| session_id | Valid UUID format, exists in index | "Invalid session ID" / "Session not found" |
| run_id | Valid UUID format | "Invalid run ID" |

#### OpenAI API Request Validation

| Field | Validation | Error Response |
|-------|------------|---------------|
| model | Required string | 400: "model is required" |
| messages | Required, non-empty array | 400: "messages is required and must be non-empty" |
| messages[].role | One of: system, user, assistant, tool | 400: "Invalid message role" |
| messages[].content | Required string | 400: "Message content is required" |
| stream | Optional boolean (default false) | 400: "stream must be a boolean" |
| tools | Optional array | Validated if present; invalid tools logged and ignored |
| max_tokens | Optional positive integer | 400: "max_tokens must be a positive integer" |
| temperature, top_p, etc. | Optional | Silently ignored (EC-NEW-008) |

---

## 5. Data Models

### SessionMetadata (JSON Session Index)

```
SessionMetadata:
  session_id: string (UUID)
  status: "pre-warmed" | "creating" | "active" | "idle" | "terminated"
  source: "pre-warm" | "cold"
  created_at: string (ISO 8601)
  last_active_at: string (ISO 8601)
  message_count: int
  title: string (auto-generated from first user message, max 100 chars)
  cost_usd: float (if available from SDK)
  terminated_reason: string | null ("duration_limit" | "memory_limit" | "user_request" | "error")
  subprocess_pid: int | null
  is_resumable: boolean
```

### Session Index File Structure

```
~/.claude-web/sessions/
  index.json          -- Array of SessionMetadata objects
  index.json.bak      -- Backup from previous successful write
  index.json.lock     -- Lock file managed by filelock
```

### ChatMessage (Frontend Zustand Store)

```
ChatMessage:
  id: string (UUID)
  session_id: string
  role: "user" | "assistant" | "tool_use" | "tool_result" | "error"
  content: string
  timestamp: string (ISO 8601)
  tool_calls: ToolCallInfo[] (for assistant messages with tools)
  is_partial: boolean (true while streaming)
  cost_usd: number | null

ToolCallInfo:
  tool_call_id: string
  tool_name: string
  status: "executing" | "complete" | "error"
  input_args: string (JSON)
  result: string | null
  result_truncated: boolean
  execution_duration_ms: number | null
```

### ExtensionConfig

```
MCPServerConfig:
  name: string
  command: string
  args: string[]
  env: Record<string, string> (sanitized)
  transport: "stdio"

SkillInfo:
  name: string
  path: string (directory path)
  has_skill_md: boolean

CommandInfo:
  name: string
  path: string
```

### Health Response

```
LivenessResponse:
  status: "ok"

ReadinessResponse:
  status: "ready" | "not_ready"
  pool_depth: int
  active_sessions: int
  max_sessions: int
  reason: string | null (if not_ready)
```

---

## 6. Risks and Mitigations

| Risk | Severity | Probability | Mitigation | Owner |
|------|----------|-------------|------------|-------|
| SDK memory leak causes OOM | CRITICAL | High | 4h duration limit (configurable); 2GB RSS threshold with graceful restart; container memory limit as safety net | Backend |
| 30s cold start when pool exhausted | HIGH | Medium | Pre-warm pool (mandatory, size >= 2); cold start UI with progress indicator; pool auto-replenishment | Backend |
| AG-UI protocol immaturity | HIGH | Medium | Use ag_ui.core for types (protocol compliance); custom SSE streaming on FastAPI (full control); monitor spec changes | Backend |
| SDK breaking changes | HIGH | High (80%) | Pin version ~=0.1.30 (patch updates only); 1 day/month upgrade testing budget; test in staging before production | Backend |
| Zombie subprocess accumulation | MEDIUM | Medium | PID tracking on session create; SIGTERM/SIGKILL on destroy; periodic zombie scan every 60s | Backend |
| JSON session index corruption | MEDIUM | Medium | Atomic writes (temp + rename); file locking; .bak recovery; session content preserved in SDK JSONL files | Backend |
| Anthropic launches hosted Claude Code | CRITICAL | Medium (40%) | Ship MVP fast; differentiate on extension model and domain-specific UIs; monitor announcements | Product |
| No auth allows unauthorized access | HIGH | Low (internal network) | VPN/firewall; auth boundary designed to be addable in Phase 2 without restructuring | Ops |
| AG-UI event delivery failure for large payloads | MEDIUM | Low | Truncate tool results > 1MB; full result available via REST endpoint | Backend |
| Pre-warm pool fails on startup | HIGH | Low | Validate API key first; fail startup if all pre-warm attempts fail; clear error logging | Backend |

---

## 7. Next Steps

### Immediate (After Architecture Approval)

1. Run `sdlc-task-breakdown --name core-engine` to create JIRA-format task breakdown from this implementation plan
2. Tasks will be organized by component with dependencies and effort estimates
3. Implementation order follows critical path: SessionManager + PreWarmPool first (P0), then AG-UI endpoint, then OpenAI API, then REST API, then frontend, then Docker

### Phase 1 MVP Critical Path

```
Week 1: Core backend
  SessionManager + PreWarmPool + SubprocessMonitor + JSONSessionIndex
  ExtensionLoader + OptionsBuilder

Week 2: API layer
  AG-UI endpoint + event translation
  OpenAI-compliant API + adapter
  REST API endpoints

Week 3: Frontend
  Zustand stores + AG-UI client
  React components (ChatPanel, MessageList, InputBar, ToolUseCard)
  Session management UI (SessionList, create, switch, resume)

Week 4: Integration + Docker
  End-to-end integration testing
  Dockerfile + docker-compose
  Health checks + startup validation
  Load testing (10 concurrent sessions on 16GB)
```

### Phase 2 Handoff Points

| Phase 1 Boundary | Phase 2 Extension |
|-------------------|-------------------|
| No auth (all endpoints open) | JWT/Keycloak middleware + AG-UI/REST headers |
| JSONSessionIndex | SQLite migration (if user count grows) |
| ExtensionLoader (filesystem scan) | PluginRegistry (manifest validation, lifecycle, secrets) |
| File-based extensions | Hot-reload via filesystem watcher |
| No cost tracking | Per-user cost tracking and caps |
| No RBAC | Three-role permission system |
| In-process extensions (no isolation) | Subprocess isolation for plugins |

---

*End of Implementation Plan*
