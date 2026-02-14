# Implementation Plan: core-engine (Phase 1 MVP)

> **Feature**: claude_sdk_pattern Core Engine
> **Date**: 2026-02-07
> **Phase**: 1 (Weeks 1-4)
> **Reference**: architecture.md, decision-log.md

---

## 1. Problem Statement Summary

**Goal**: Build a web platform that wraps the Claude Agent SDK, enabling a single user to chat with Claude agents through a browser with multiple concurrent sessions, file-based extensions (mcp.json, skills, commands), and acceptable startup latency (<3s via pre-warming pool).

**Success Criteria**:
- User can chat via web browser with <3s response time (pre-warmed)
- User can create, switch between, and manage multiple independent sessions
- Agent uses MCP servers from mcp.json, skills from ./skills/, commands from ./commands/
- Up to 10 concurrent sessions on a single 16GB host without OOM
- Session runs for 2+ hours without OOM crash
- `docker run` starts a working instance within 90 seconds

---

## 2. Reference Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Architecture | `task_core-engine/plan/strategy/architecture.md` | Component diagrams, data flows |
| Decision Log | `task_core-engine/plan/decision-log.md` | Technology choices with rationale |
| Feature Spec | `task_core-engine/specs/feature-spec.md` | Requirements, NFRs, guardrails |
| User Stories | `task_core-engine/specs/user-stories.md` | Acceptance criteria (Given/When/Then) |
| Edge Cases | `task_core-engine/specs/edge-case-resolutions.md` | HIGH risk edge case resolutions |
| Control Flows | `task_core-engine/specs/control-flows/` | Step-by-step user journeys |
| Tech Feasibility | `task_core-engine/requirement/team_findings/technical_feasibility.md` | SDK APIs, known limitations |

---

## 3. Feature Planning Details

### 3.1 Configuration and Models (Layer 0)

**What to build**: Environment variable configuration, Pydantic data models for sessions, WebSocket messages, and extension configs. SQLite schema.

**Files to create**:
- `src/claude_sdk_pattern/config.py`
- `src/claude_sdk_pattern/models/session.py`
- `src/claude_sdk_pattern/models/messages.py`
- `src/claude_sdk_pattern/models/extensions.py`
- `src/claude_sdk_pattern/db/migrations.py`

**Configuration variables** (all from environment):

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| CLAUDE_SDK_PATTERN_API_KEY | str | required | API key for auth |
| ANTHROPIC_API_KEY | str | required | Claude API key |
| PREWARM_POOL_SIZE | int | 2 | Pre-warm pool target depth |
| MAX_SESSIONS | int | 10 | Max concurrent sessions (10 feasible on 16GB host at ~750MB baseline per session) |
| MAX_SESSION_DURATION_SECONDS | int | 14400 | 4 hours |
| MAX_SESSION_RSS_MB | int | 2048 | 2 GB (~3x the ~750MB baseline; corrected from previous 4GB based on actual ~500MB-1GB baseline per GitHub #4953) |
| SESSION_IDLE_TIMEOUT_SECONDS | int | 1800 | 30 minutes |
| PREWARM_TIMEOUT_SECONDS | int | 60 | Max wait per pre-warm |
| DATABASE_URL | str | sqlite:///data/sessions.db | SQLite path |
| HOST | str | 0.0.0.0 | Bind address |
| PORT | int | 8000 | Bind port |
| LOG_LEVEL | str | INFO | structlog level |
| PROJECT_DIR | str | . | Root for mcp.json, skills/, commands/ |

**Dependencies on**: None (foundation layer)

### 3.2 Session Repository (Layer 1)

**What to build**: aiosqlite-based repository for session metadata persistence.

**File to create**: `src/claude_sdk_pattern/db/repository.py`

**Interface**:
- `SessionRepository.__init__(db_path: str) -> None`
- `SessionRepository.initialize() -> None`: Create tables if not exist
- `SessionRepository.save(metadata: SessionMetadata) -> None`
- `SessionRepository.get(session_id: str) -> Optional[SessionMetadata]`
- `SessionRepository.list_active() -> list[SessionMetadata]`
- `SessionRepository.update_activity(session_id: str, message_count: int, cost: float) -> None`
- `SessionRepository.mark_terminated(session_id: str, reason: str) -> None`

**Dependencies on**: models/session, db/migrations, config

### 3.3 Extension Loader (Layer 1)

**What to build**: Filesystem scanner for mcp.json, skills directories, and commands. Builds ClaudeAgentOptions-compatible config.

**File to create**: `src/claude_sdk_pattern/core/extension_loader.py`

**Interface**:
- `ExtensionLoader.__init__(project_dir: str) -> None`
- `ExtensionLoader.load_options() -> ExtensionConfig`: Re-scan all sources, return config
- `ExtensionLoader.get_mcp_servers() -> dict`: Parse mcp.json
- `ExtensionLoader.get_skill_directories() -> list[str]`: List discovered skill dirs
- `ExtensionLoader.get_commands() -> list[CommandDef]`: List discovered commands

**Behavior**:
- `load_options()` re-reads from disk on every call (hot-detection per FR-011c)
- Invalid mcp.json: log error, return empty mcp_servers (do not crash)
- Missing ./skills/ or ./commands/: silently skip (directories are optional)
- mcp.json format matches Claude Code: `{"mcpServers": {"name": {"command": "...", "args": [...], "env": {...}}}}`

**Dependencies on**: models/extensions, config

### 3.4 Pre-Warm Pool (Layer 2)

**What to build**: asyncio.Queue-based pool of ready ClaudeSDKClient instances with background replenishment.

**File to create**: `src/claude_sdk_pattern/core/prewarm_pool.py`

**Interface**:
- `PreWarmPool.__init__(pool_size: int, extension_loader: ExtensionLoader) -> None`
- `PreWarmPool.startup_fill() -> bool`: Block until at least 1 slot filled; return False if all fail
- `PreWarmPool.get() -> Optional[ClaudeSDKClient]`: Non-blocking get from queue
- `PreWarmPool.replenish() -> None`: Background task to fill pool to target
- `PreWarmPool.invalidate() -> None`: Drain pool (extensions changed)
- `PreWarmPool.depth() -> int`: Current pool size
- `PreWarmPool.shutdown() -> None`: Drain and cleanup all clients

**Pre-warm process**:
1. Call ExtensionLoader.load_options() to get current config
2. Create ClaudeSDKClient with options
3. Enter async context manager (starts subprocess)
4. Place client in queue
5. If creation fails (rate limit, API error): log, backoff, retry

**Dependencies on**: extension_loader, config

### 3.5 Subprocess Monitor (Layer 2)

**What to build**: Background monitoring for RSS memory, session duration, and zombie process cleanup.

**File to create**: `src/claude_sdk_pattern/core/subprocess_monitor.py`

**Interface**:
- `SubprocessMonitor.__init__(config: Config) -> None`
- `SubprocessMonitor.start(session_manager: SessionManager) -> None`: Launch background tasks
- `SubprocessMonitor.stop() -> None`: Cancel background tasks
- `SubprocessMonitor.get_rss(pid: int) -> Optional[int]`: RSS in bytes from /proc or ps
- `SubprocessMonitor.check_all() -> list[MonitorAction]`: Check all sessions, return actions

**Monitor actions** returned from check_all():
- `MonitorAction(type="warn_duration", session_id, remaining_seconds)`
- `MonitorAction(type="terminate_duration", session_id)`
- `MonitorAction(type="restart_memory", session_id, rss_mb)`
- `MonitorAction(type="force_kill_memory", session_id, rss_mb)` (RSS > 2x threshold)
- `MonitorAction(type="cleanup_zombie", pid)`

**Platform compatibility**:
- Linux: read `/proc/<pid>/status` for VmRSS
- macOS (development): use `ps -o rss= -p <pid>`

**Dependencies on**: config, models/session

### 3.6 Session Manager (Layer 3)

**What to build**: Central orchestrator for session lifecycle. Coordinates pool, monitor, extensions, and repository.

**File to create**: `src/claude_sdk_pattern/core/session_manager.py`

**Interface**:
- `SessionManager.__init__(pool, monitor, loader, repo, config) -> None`
- `SessionManager.create_session() -> SessionState`: Acquire from pool or cold start
- `SessionManager.query(session_id: str, prompt: str) -> AsyncIterator[SDKMessage]`: Stream response
- `SessionManager.interrupt(session_id: str) -> None`: Abort in-flight query
- `SessionManager.list_sessions() -> list[SessionSummary]`
- `SessionManager.get_session(session_id: str) -> Optional[SessionState]`
- `SessionManager.destroy_session(session_id: str) -> None`: Cleanup subprocess
- `SessionManager.resume_session(session_id: str) -> SessionState`: Resume from SDK storage
- `SessionManager.shutdown() -> None`: Graceful shutdown all sessions

**Session state tracking** (in-memory dict):
- `sessions: dict[str, SessionState]` where SessionState contains: session_id, client (ClaudeSDKClient), pid, created_at, last_active, status, is_query_active

**Query flow**:
1. Validate session exists and status is active/idle
2. Set is_query_active = True
3. Call client.query(prompt)
4. Iterate client.receive_response()
5. Yield each SDK message (AssistantMessage, ToolUseBlock, ToolResultBlock, ResultMessage)
6. On ResultMessage: update session metadata (cost, message count, last_active)
7. Set is_query_active = False

**Dependencies on**: prewarm_pool, subprocess_monitor, extension_loader, repository, config

### 3.7 WebSocket Handler (Layer 4)

**What to build**: FastAPI WebSocket endpoint that accepts connections, authenticates, routes messages, and streams SDK responses.

**File to create**: `src/claude_sdk_pattern/api/websocket.py`

**Endpoint**: `@app.websocket("/ws/v1/chat")`

**Connection lifecycle**:
1. Accept WebSocket upgrade
2. Read API key from query parameter or header
3. Validate against configured key
4. If invalid: close with 1008 (Policy Violation)
5. Send session_list to client
6. Enter message loop: receive client messages, route to SessionManager, stream responses

**Message routing**:
- `user_message` -> SessionManager.query() -> stream responses as WebSocket frames
- `interrupt` -> SessionManager.interrupt()
- `create_session` -> SessionManager.create_session() -> send session_ready
- `switch_session` -> Send message history for target session (from DB/cache)

**Connection deduplication** (G-003):
- Maintain `active_connections: dict[str, WebSocket]`
- On new connection for existing session_id: send "session_opened_elsewhere" to old, close old

**Dependencies on**: session_manager, auth, message_types

### 3.8 REST API (Layer 4)

**What to build**: REST endpoints for session management and health check.

**File to create**: `src/claude_sdk_pattern/api/rest.py`

**Endpoints**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /api/v1/sessions | API key | List all sessions |
| POST | /api/v1/sessions | API key | Create new session |
| GET | /api/v1/sessions/{id} | API key | Get session details |
| DELETE | /api/v1/sessions/{id} | API key | Destroy session |
| GET | /api/v1/health/live | None | Liveness probe (process alive) |
| GET | /api/v1/health/ready | None | Readiness probe (pool has capacity) |
| GET | /api/v1/extensions | API key | List loaded extensions (mcp servers, skills, commands) |

**Dependencies on**: session_manager, auth

### 3.9 Application Entry Point (Layer 5)

**What to build**: FastAPI application factory with startup/shutdown lifecycle events.

**File to create**: `src/claude_sdk_pattern/main.py`

**Startup sequence**:
1. Load configuration from environment
2. Initialize structlog
3. Initialize SessionRepository (create tables)
4. Initialize ExtensionLoader
5. Initialize PreWarmPool
6. Call pool.startup_fill() -- blocks until at least 1 pre-warm succeeds
7. If startup_fill() returns False: log CRITICAL, exit(1)
8. Initialize SubprocessMonitor
9. Initialize SessionManager
10. Mount WebSocket handler
11. Mount REST routes
12. Serve static frontend files
13. Start SubprocessMonitor background tasks

**Shutdown sequence**:
1. Stop accepting new connections
2. Notify all connected WebSockets: "server_shutting_down"
3. Wait up to 30s for in-flight queries
4. SessionManager.shutdown() -- destroy all sessions
5. PreWarmPool.shutdown() -- drain pool
6. Close database connection

**Dependencies on**: All components

---

## 4. Integration Contracts

### 4.1 API Endpoints

#### GET /api/v1/sessions

**Request**:
- Header: `X-API-Key: <key>`

**Response** (200):
```
{
  "sessions": [
    {
      "session_id": "abc123",
      "status": "active",
      "created_at": "2026-02-07T10:30:00Z",
      "last_active_at": "2026-02-07T11:15:00Z",
      "message_count": 12,
      "total_cost_usd": 0.48,
      "is_resumable": true
    }
  ]
}
```

**Error responses**:
- 401: `{"error": "unauthorized", "message": "Invalid API key"}`

#### POST /api/v1/sessions

**Request**:
- Header: `X-API-Key: <key>`
- Body: `{}` (empty, no parameters for MVP)

**Response** (201):
```
{
  "session_id": "abc123",
  "status": "active",
  "source": "pre-warmed",
  "created_at": "2026-02-07T10:30:00Z"
}
```

**Error responses**:
- 401: `{"error": "unauthorized", "message": "Invalid API key"}`
- 503: `{"error": "capacity_exceeded", "message": "Server at capacity. Max sessions: 10"}`

#### DELETE /api/v1/sessions/{session_id}

**Request**:
- Header: `X-API-Key: <key>`

**Response** (200):
```
{
  "session_id": "abc123",
  "status": "terminated",
  "reason": "user_requested"
}
```

**Error responses**:
- 401: `{"error": "unauthorized", "message": "Invalid API key"}`
- 404: `{"error": "not_found", "message": "Session not found"}`

#### GET /api/v1/health/live

**Request**: No auth required.

**Response** (200):
```
{"status": "ok"}
```

#### GET /api/v1/health/ready

**Request**: No auth required.

**Response** (200):
```
{
  "status": "ready",
  "pool_depth": 2,
  "active_sessions": 1,
  "max_sessions": 5
}
```

**Response** (503):
```
{
  "status": "not_ready",
  "reason": "pool_empty",
  "active_sessions": 5,
  "max_sessions": 5
}
```

#### GET /api/v1/extensions

**Request**:
- Header: `X-API-Key: <key>`

**Response** (200):
```
{
  "mcp_servers": {
    "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
    "postgres": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-postgres"]}
  },
  "skills": [
    {"name": "code-review", "path": "./skills/code-review/SKILL.md"}
  ],
  "commands": [
    {"name": "deploy", "path": "./commands/deploy"}
  ]
}
```

### 4.2 WebSocket Message Contracts

#### Client -> Server Messages

**user_message**: Send a chat message to a session.
```
{
  "type": "user_message",
  "session_id": "abc123",
  "text": "How many active users last month?",
  "seq": 5
}
```
- Validation: text must be non-empty, max 32,000 characters
- Rejected if query already in flight for this session (returns error)

**interrupt**: Abort the current streaming response.
```
{
  "type": "interrupt",
  "session_id": "abc123"
}
```
- Idempotent: safe to send even if no query is active

**create_session**: Request a new session.
```
{
  "type": "create_session"
}
```

**switch_session**: Switch active view to a different session.
```
{
  "type": "switch_session",
  "session_id": "def456"
}
```

**destroy_session**: Terminate and clean up a session.
```
{
  "type": "destroy_session",
  "session_id": "abc123"
}
```

#### Server -> Client Messages

**session_list**: Sent on initial connection. List of all sessions.
```
{
  "type": "session_list",
  "sessions": [
    {
      "session_id": "abc123",
      "status": "active",
      "created_at": "2026-02-07T10:30:00Z",
      "last_active_at": "2026-02-07T11:15:00Z",
      "message_count": 12
    }
  ]
}
```

**session_ready**: Session created and ready for messages.
```
{
  "type": "session_ready",
  "session_id": "abc123",
  "status": "ready",
  "source": "pre-warmed"
}
```

**session_creating**: Session being created via cold start.
```
{
  "type": "session_creating",
  "estimated_seconds": 30
}
```

**message_received**: Acknowledgment that user message was received.
```
{
  "type": "message_received",
  "seq": 5
}
```

**stream_delta**: Streaming text token from Claude.
```
{
  "type": "stream_delta",
  "session_id": "abc123",
  "delta": "I'll",
  "seq": 6
}
```

**tool_use**: Claude is invoking a tool.
```
{
  "type": "tool_use",
  "session_id": "abc123",
  "tool_use_id": "tu_123",
  "tool": "mcp__postgres__execute_sql",
  "input": {"query": "SELECT COUNT(*) FROM users WHERE last_active > ..."},
  "seq": 20
}
```

**tool_result**: Tool execution completed.
```
{
  "type": "tool_result",
  "session_id": "abc123",
  "tool_use_id": "tu_123",
  "result": {"count": 45231},
  "status": "success",
  "duration_ms": 1200,
  "seq": 21
}
```
- status values: "success" | "error"
- On error: result contains `{"error": "Connection refused"}`

**response_complete**: Claude finished responding.
```
{
  "type": "response_complete",
  "session_id": "abc123",
  "cost_usd": 0.024,
  "turn_count": 3,
  "seq": 35
}
```

**stream_error**: Error during streaming.
```
{
  "type": "stream_error",
  "session_id": "abc123",
  "error": "Response interrupted due to API timeout",
  "partial_preserved": true,
  "suggested_action": "retry",
  "seq": 25
}
```

**stream_interrupted**: User-initiated interrupt completed.
```
{
  "type": "stream_interrupted",
  "session_id": "abc123",
  "seq": 26
}
```

**session_warning**: Session approaching limits.
```
{
  "type": "session_warning",
  "session_id": "abc123",
  "reason": "duration",
  "remaining_seconds": 1440,
  "message": "Session will end in 24 minutes. Save your work."
}
```

**session_terminated**: Session ended.
```
{
  "type": "session_terminated",
  "session_id": "abc123",
  "reason": "duration_limit",
  "message": "Session ended (4-hour limit reached).",
  "resume_url": "/chat?resume=abc123"
}
```

**session_restarting**: Session restarting due to memory.
```
{
  "type": "session_restarting",
  "session_id": "abc123",
  "reason": "memory_limit",
  "message": "Session restarting to maintain performance. Your conversation will be preserved."
}
```

**error**: General error.
```
{
  "type": "error",
  "code": "query_in_progress",
  "message": "Please wait for the current response to complete."
}
```
- Error codes: "query_in_progress", "session_not_found", "invalid_message", "invalid_json", "capacity_exceeded", "internal_error"

### 4.3 Frontend-Backend Data Contracts

#### SessionSummary (used in session_list and REST API)

| Field | Type | Description |
|-------|------|-------------|
| session_id | string | UUID |
| status | "creating" or "active" or "idle" or "terminated" | Current state |
| created_at | string (ISO 8601) | When session was created |
| last_active_at | string (ISO 8601) | Last message timestamp |
| message_count | integer | Total messages exchanged |
| total_cost_usd | number | Cumulative API cost |
| is_resumable | boolean | Whether session can be resumed |

#### ToolUseDisplay (used in tool_use and tool_result messages)

| Field | Type | Description |
|-------|------|-------------|
| tool_use_id | string | Unique ID for this tool invocation |
| tool | string | Tool name (e.g., "mcp__postgres__execute_sql") |
| input | object | Tool input parameters (JSON) |
| status | "executing" or "success" or "error" | Current execution state |
| result | object or null | Tool result (null while executing) |
| duration_ms | integer or null | Execution time (null while executing) |
| error | string or null | Error message (null if success) |

#### ExtensionInfo (used in GET /api/v1/extensions)

| Field | Type | Description |
|-------|------|-------------|
| mcp_servers | object | Map of server name to config (command, args, env) |
| skills | array of {name, path} | Discovered skill directories |
| commands | array of {name, path} | Discovered command files |

### 4.4 User Input Validation Specs

| Input | Max Length | Allowed Characters | Validation Rule | Error Message |
|-------|-----------|-------------------|-----------------|---------------|
| User message text | 32,000 chars | Any UTF-8 | Non-empty after trim; max length | "Message is empty" or "Message exceeds 32,000 character limit" |
| API key (header) | 256 chars | ASCII printable | Exact match with configured key | "Invalid API key" |
| session_id (param) | 36 chars | UUID format | Must exist in session map | "Session not found" |
| seq (field) | N/A | Positive integer | Monotonically increasing per connection | "Invalid sequence number" |

---

## 5. Data Models

### 5.1 SessionMetadata (SQLite)

| Field | Type | Nullable | Default | Description |
|-------|------|----------|---------|-------------|
| session_id | TEXT PK | No | generated UUID | Session identifier |
| user_id | TEXT | No | "default" | Placeholder for Phase 2 multi-user |
| status | TEXT | No | "creating" | creating/active/idle/terminated |
| created_at | TEXT | No | now() | ISO 8601 timestamp |
| last_active_at | TEXT | No | now() | Last message time |
| subprocess_pid | INTEGER | Yes | NULL | CLI subprocess PID |
| message_count | INTEGER | No | 0 | Total messages |
| total_cost_usd | REAL | No | 0.0 | Cumulative API cost |
| is_resumable | BOOLEAN | No | TRUE | Can this session be resumed |
| terminated_reason | TEXT | Yes | NULL | Why session ended |

### 5.2 SessionState (In-Memory)

| Field | Type | Description |
|-------|------|-------------|
| session_id | str | UUID |
| client | ClaudeSDKClient | SDK client instance |
| pid | int | Subprocess PID (for monitoring) |
| created_at | datetime | Creation time |
| last_active_at | datetime | Last activity |
| status | SessionStatus enum | creating/active/idle/restarting/terminated |
| is_query_active | bool | Whether a query is currently in flight |
| websocket | Optional[WebSocket] | Active WebSocket connection (if any) |
| options | ClaudeAgentOptions | Options used to create this session |

### 5.3 ExtensionConfig (Runtime)

| Field | Type | Description |
|-------|------|-------------|
| mcp_servers | dict[str, MCPServerConfig] | From mcp.json |
| setting_sources | list[str] | ["user", "project"] if skills exist |
| skill_directories | list[str] | Paths to discovered skill dirs |
| commands | list[CommandDef] | Discovered command definitions |
| loaded_at | datetime | When config was last loaded |

### 5.4 MCPServerConfig

| Field | Type | Description |
|-------|------|-------------|
| command | str | Executable command (e.g., "npx") |
| args | list[str] | Command arguments |
| env | Optional[dict[str, str]] | Environment variables for the server |

---

## 6. Risks and Mitigations

| Risk | Probability | Impact | Mitigation in Architecture |
|------|------------|--------|---------------------------|
| **SDK memory leak causes OOM** | High | Server crash | SubprocessMonitor: RSS monitoring every 30s, 2GB threshold (~3x baseline) triggers graceful restart (EC-004); 4h duration limit (EC-003); 16GB host supports up to 10 sessions with headroom |
| **Pre-warm pool exhaustion** | Medium | Users wait 30s | Cold start fallback with progress UI (EC-001); pool replenishes in background; readiness probe checks pool depth |
| **Zombie subprocess accumulation** | Medium | Gradual memory leak | SubprocessMonitor: periodic zombie cleanup every 60s; PID tracking for all sessions (G-001); SIGTERM/SIGKILL protocol |
| **SDK breaking changes** | High | Parts of platform break | Pin to ~0.1.30; ExtensionLoader isolates SDK config building; budget 1 day/month for upgrade testing |
| **WebSocket drops in production** | Medium | User loses streaming context | Basic reconnection (client-side); full message replay deferred to Phase 2 (EC-036); server buffers results for 60s on disconnect |
| **Invalid mcp.json crashes session** | Low | Session fails to start | ExtensionLoader validates JSON syntax; invalid config logged, excluded; session starts with remaining valid extensions |
| **Anthropic launches hosted Claude Code** | Medium | Reduced differentiation | Ship fast (4 weeks); differentiate on self-hosted + extension model; pivot to niche if needed |

---

## 7. Next Steps

After this plan is approved:

1. **Run `sdlc-task-breakdown --name core-engine`** to generate JIRA-format task cards from this implementation plan
2. **Create feature branch**: `feature/core-engine-mvp`
3. **Initialize project**: pyproject.toml with uv, Vite frontend scaffold
4. **Build in dependency order**: Layer 0 -> Layer 5 as specified in architecture Section 8
5. **Integration test at each layer**: Ensure contracts are honored before building next layer

**Handoff artifacts**:
- `task_core-engine/plan/strategy/implementation_plan.md` (this document)
- `task_core-engine/plan/strategy/architecture.md`
- `task_core-engine/plan/decision-log.md`
- `task_core-engine/plan/status.md`

---

*End of Implementation Plan*
