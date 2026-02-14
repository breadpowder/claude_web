# Architecture: core-engine (Phase 1 MVP)

> **Feature**: claude_sdk_pattern Core Engine
> **Date**: 2026-02-07
> **Phase**: 1 (MVP, Weeks 1-4)
> **Scope**: Single-user platform with pre-warming, streaming chat, file-based extensions, multiple sessions

---

## 1. System Overview

The core engine is a web platform that wraps the Claude Agent SDK, exposing agent capabilities through a React chat interface over WebSocket. It manages SDK subprocess lifecycle (pre-warming, memory monitoring, cleanup), loads extensions from the filesystem (mcp.json, skills, commands), and provides session management for multiple concurrent conversations.

**What it is**: The production operations layer for Claude Agent SDK.
**What it is NOT**: A general-purpose chat UI, a multi-LLM platform, or a plugin marketplace.

---

## 2. Component Diagram

```
+=====================================================================+
|                         Browser (React 19)                           |
|                                                                      |
|  +----------------+  +-----------+  +----------+  +---------------+  |
|  | SessionList    |  | InputBar  |  | Message  |  | ToolUseCard   |  |
|  | (switch/new)   |  | (send/    |  | List     |  | (tool status) |  |
|  |                |  |  interrupt)|  | (stream) |  |               |  |
|  +-------+--------+  +-----+-----+  +-----+----+  +-------+-------+  |
|          |                  |              |                |          |
|          +------------------+--------------+----------------+         |
|                             |                                         |
|                    [Zustand Store: messages, sessions, streaming]     |
|                             |                                         |
|                     WebSocket Client                                  |
+==========================|============================================+
                           | wss://host/ws/v1/chat
                           | (JSON frames, API key in header)
+==========================|============================================+
|                     FastAPI (uvicorn)                                  |
|                          |                                            |
|  +-----------------------+------------------------+                   |
|  |                                                |                   |
|  |  +------------------+    +------------------+  |                   |
|  |  | WebSocketHandler |    | REST API         |  |                   |
|  |  | /ws/v1/chat      |    | /api/v1/sessions |  |                   |
|  |  | - auth           |    | /api/v1/health   |  |                   |
|  |  | - msg routing    |    | - session list   |  |                   |
|  |  | - stream relay   |    | - session create |  |                   |
|  |  | - interrupt      |    | - health/live    |  |                   |
|  |  +--------+---------+    +--------+---------+  |                   |
|  |           |                       |             |                   |
|  +-----------+-----------------------+-------------+                  |
|              |                                                        |
|  +-----------v-------------------------------------------------+      |
|  |                   SessionManager                             |     |
|  |  - sessions: dict[session_id, SessionState]                  |     |
|  |  - create_session() -> assign from pool or cold start        |     |
|  |  - query(session_id, prompt) -> stream SDK messages           |     |
|  |  - interrupt(session_id) -> abort in-flight query            |     |
|  |  - list_sessions() -> all sessions for user                  |     |
|  |  - destroy_session(session_id) -> cleanup subprocess         |     |
|  +------+---------+-------------+---------------------------+---+     |
|         |         |             |                           |         |
|  +------v---+ +---v--------+ +-v------------------+ +------v------+  |
|  | PreWarm  | | Subprocess | | ExtensionLoader    | | SessionRepo |  |
|  | Pool     | | Monitor    | | - read mcp.json    | | (aiosqlite) |  |
|  | (Queue)  | | - RSS poll | | - scan ./skills/   | | - metadata  |  |
|  | - get()  | | - duration | | - scan ./commands/ | | - persist   |  |
|  | - fill() | | - zombies  | | - build options    | | - resume    |  |
|  +------+---+ +------+-----+ +---------+----------+ +------+------+  |
|         |            |                  |                    |         |
|  +------v------------v------------------v--------------------v-----+  |
|  |                    ClaudeSDKClient (per session)                 |  |
|  |  - async context manager wrapping CLI subprocess                |  |
|  |  - query(prompt) -> send user message                           |  |
|  |  - receive_response() -> async iterator of SDK messages          |  |
|  |  - interrupt() -> abort current query                           |  |
|  |  - subprocess PID tracked for monitoring                        |  |
|  +--+---------------------------+----------------------------------+  |
|     |                           |                                     |
|     v                           v                                     |
|  [Claude Code CLI subprocess]  [MCP Server subprocesses (stdio)]     |
|  (~500MB-1GB baseline RAM)     (from mcp.json entries)               |
|                                                                       |
+=======================================================================+
         |
         v
  [Anthropic Claude API]
  (messages, tool use, streaming)
```

---

## 3. Data Flow Diagram

### 3.1 Session Creation Flow

```
User opens browser
        |
        v
React app loads --> WebSocket connect to /ws/v1/chat
        |                      |
        |               [Auth: API key in header]
        |                      |
        |              +-------v--------+
        |              | WebSocket      |
        |              | Handler        |
        |              | validates key  |
        |              +-------+--------+
        |                      |
        |              +-------v--------+
        |              | SessionManager |
        |              | .get_or_create |
        |              +-------+--------+
        |                      |
        |            +---------+---------+
        |            |                   |
        |     [Pool has slot]    [Pool empty]
        |            |                   |
        |     +------v------+   +--------v--------+
        |     | PreWarmPool  |  | Cold start       |
        |     | .get()       |  | ClaudeSDKClient()|
        |     | (<100ms)     |  | (20-30s)         |
        |     +------+------+  +--------+---------+
        |            |                   |
        |            +----->+<-----------+
        |                   |
        |          +--------v--------+
        |          | ExtensionLoader |
        |          | .load_options() |
        |          | (re-scan files) |
        |          +--------+--------+
        |                   |
        |          +--------v--------+
        |          | SessionRepo     |
        |          | .save_metadata()|
        |          +--------+--------+
        |                   |
        v                   v
    UI: "Ready"     WebSocket: {type: "session_ready", session_id: "..."}
```

### 3.2 Chat Message Flow

```
User types message, presses Enter
        |
        v
InputBar --> Zustand: optimistic add to messages
        |
        v
WebSocket send: {type: "user_message", text: "...", session_id: "...", seq: N}
        |
        v
+------------------+
| WebSocketHandler |
| route to session |
+--------+---------+
         |
+--------v---------+
| SessionManager   |
| .query(sid, msg) |
+--------+---------+
         |
+--------v---------+
| ClaudeSDKClient  |
| .query(prompt)   |
+--------+---------+
         |
         |--- SDK streams AssistantMessage (delta tokens)
         |    |
         |    +--> WebSocket: {type: "stream_delta", delta: "...", seq: N+1}
         |         |
         |         +--> Zustand: append to streaming buffer
         |              |
         |              +--> MessageList: render token
         |
         |--- SDK streams ToolUseBlock
         |    |
         |    +--> WebSocket: {type: "tool_use", tool: "...", input: {...}, seq: N+K}
         |         |
         |         +--> Zustand: add tool_use entry
         |              |
         |              +--> ToolUseCard: render "Executing..."
         |
         |--- SDK streams ToolResultBlock
         |    |
         |    +--> WebSocket: {type: "tool_result", result: {...}, duration_ms: X, seq: N+K+1}
         |         |
         |         +--> Zustand: update tool_use entry
         |              |
         |              +--> ToolUseCard: render "Complete (X.Xs)"
         |
         |--- SDK returns ResultMessage
              |
              +--> WebSocket: {type: "response_complete", cost_usd: 0.02, seq: N+M}
                   |
                   +--> Zustand: finalize message, update session metadata
                        |
                        +--> InputBar: re-enable
```

### 3.3 Subprocess Monitoring Flow

```
[Every 30 seconds -- background asyncio task]
        |
        v
+-------------------+
| SubprocessMonitor |
| .check_all()     |
+--------+----------+
         |
    For each active session:
         |
    +----v-----+
    | Read RSS  |    Read /proc/<pid>/status -> VmRSS
    +----+-----+
         |
    +----v-----------+
    | RSS < threshold |---> No action
    +----+-----------+
         |
    [RSS >= threshold]
         |
    +----v-----------------+
    | Query in flight?     |
    +----+-----------+-----+
         |           |
      [Yes]        [No]
         |           |
    [Wait for       +----v-----------------+
     completion     | Flag for graceful    |
     up to 30s]     | restart              |
         |          +----+-----------------+
         |               |
         +--------->+<---+
                    |
           +--------v--------+
           | Notify user     |
           | via WebSocket   |
           | "Restarting..." |
           +--------+--------+
                    |
           +--------v--------+
           | SIGTERM -> wait  |
           | 5s -> SIGKILL   |
           +--------+--------+
                    |
           +--------v--------+
           | Create new      |
           | session with    |
           | resume=sid      |
           +--------+--------+
                    |
           +--------v--------+
           | Notify user     |
           | "Resumed"       |
           +-----------------+

[Every 60 seconds -- zombie cleanup]
        |
        v
    List child processes
    For each PID not in active sessions:
        SIGTERM -> wait 5s -> SIGKILL
        Log warning, increment metric
```

---

## 4. Control Flow with Edge Cases

### 4.1 Session Start (from control-flows/us-001)

```
                    [User Opens Browser]
                          |
                          v
+---------------------------------------------------------+
|                    Load React App                        |
|  Serve static assets from FastAPI /static               |
+---------------------------------------------------------+
                          |
                          v
+---------------------------------------------------------+
|                WebSocket Connect                         |
|  URL: /ws/v1/chat                                       |
|  Header: X-API-Key: <key>                               |
+----------+----------------------------------------------+
           |
     +-----+------+
     |             |
 [Valid key]   [Invalid key]
     |             |
     v             v
[Accept WS]    +---------------------------+
     |         | EC-098: 401 Unauthorized   |
     |         | "Invalid API key"          |
     |         +---------------------------+
     v
+---------------------------------------------------------+
|            SessionManager.create_session()               |
+----------+----------------------------------------------+
           |
     +-----+------------+
     |                   |
 [Pool has slot]    [Pool empty]
     |                   |
     v                   v
[Assign from pool]  +---------------------------+
[< 100ms]          | EC-001: Cold start         |
     |              | WS: {type: "session_       |
     |              |  creating", est: 30}       |
     |              | UI: progress indicator     |
     |              | Duration: 20-30s           |
     |              +-------------+-------------+
     |                            |
     +----------->+<--------------+
                  |
                  v
+---------------------------------------------------------+
|          ExtensionLoader.load_options()                  |
|  - Read mcp.json from project root                      |
|  - Scan ./skills/<name>/SKILL.md                        |
|  - Scan ./commands/<name>                               |
|  - Build ClaudeAgentOptions                             |
+---------------------------------------------------------+
                  |
                  v
+---------------------------------------------------------+
|          WS: {type: "session_ready",                    |
|            session_id: "abc123", status: "ready"}        |
+---------------------------------------------------------+
                  |
                  v
+---------------------------------------------------------+
|          Background: PreWarmPool.replenish()              |
|          (if pool depth dropped below target)            |
|                                                          |
|          EC-014: If rate-limited, backoff 5 min          |
+---------------------------------------------------------+

Pre-startup edge cases (before user arrives):
  EC-022: All pre-warms fail -> readiness probe 503 -> no traffic
  EC-098: Invalid API key -> fail startup -> exit code 1
```

### 4.2 Chat Streaming with Tool Use (from control-flows/us-002)

```
[User Sends Message]
        |
        v
+---------------------------------------------------------+
| Validate: non-empty, < 32k chars                        |
| WS send: {type: "user_message", text: "...", seq: N}    |
+-----+---------------------------------------------------+
      |
      +----------->+
                   |
      [Query in flight already?]
           |               |
        [Yes]           [No]
           |               |
           v               v
  +------------------+  +-----------------------+
  | EC-032: Reject   |  | SDK: client.query()   |
  | "Query in        |  | WS: {type: "message_  |
  |  progress"       |  |  received", seq: N}    |
  +------------------+  +-----------+-----------+
                                    |
                               [SDK streams]
                                    |
              +---------------------+---------------------+
              |                     |                     |
         [TextDelta]          [ToolUseBlock]         [ResultMessage]
              |                     |                     |
              v                     v                     v
   WS: {type: "stream_    WS: {type: "tool_use",   WS: {type: "response_
    delta", delta: "I'll    tool: "mcp__pg__sql",    complete",
    ", seq: N+1}            input: {...},             cost_usd: 0.024,
                            seq: N+K}                 seq: N+M}
              |                     |
              |              [Tool executes]
              |                     |
              |              WS: {type: "tool_result",
              |                result: {...},
              |                duration_ms: 1200,
              |                seq: N+K+1}
              |                     |
              +<----[More text]-----+
              |
         [Stream continues until ResultMessage]

Edge cases during streaming:
  EC-009: Tab closed -> buffer results 60s -> interrupt if no reconnect
  EC-020: New message while streaming -> queue client-side
  EC-035: Disconnect mid-tool -> tool continues -> buffer results
  EC-028: High token rate -> React useTransition batches
  EC-050: Large tool_result -> truncate >1MB (Phase 2)
```

### 4.3 Interrupt Flow

```
[User Presses Ctrl+Shift+X]
        |
        v
WS send: {type: "interrupt", session_id: "abc123"}
        |
        v
+---------------------------------------------------------+
| WebSocketHandler routes to SessionManager.interrupt()    |
+---------------------------------------------------------+
        |
        v
+---------------------------------------------------------+
| ClaudeSDKClient.interrupt()                              |
| SDK sends abort signal to subprocess                     |
+---------------------------------------------------------+
        |
        v
+---------------------------------------------------------+
| SDK stream ends with partial result                      |
| WS: {type: "stream_interrupted", seq: N+K}             |
| UI: "[Response interrupted]" indicator                   |
| InputBar: re-enabled                                     |
+---------------------------------------------------------+
```

---

## 5. Error Handling Matrix

| Component | Error Type | Edge Case | Response | Recovery |
|-----------|-----------|-----------|----------|----------|
| WebSocketHandler | Invalid API key | EC-098 | 401 on WS upgrade | User re-enters key |
| WebSocketHandler | Malformed JSON | EC-029 | WS error frame: "invalid_json" | Client retries with valid JSON |
| WebSocketHandler | Duplicate session connection | EC-010 | Close old connection: "Session opened elsewhere" | User picks one tab |
| SessionManager | Pool exhausted | EC-001 | Cold start fallback with progress UI | Pool replenishes in background |
| SessionManager | Cold start timeout (>60s) | EC-022 | WS error: "Session creation failed" | User retries |
| SessionManager | SDK subprocess crash | EC-119 | WS error: "Session error. Restart available." | Resume in new session |
| PreWarmPool | Rate limited during fill | EC-014 | Backoff 5 min; log warning | Automatic retry after backoff |
| PreWarmPool | All pre-warms fail at startup | EC-022 | Readiness probe 503; fail startup | Operator fixes root cause |
| SubprocessMonitor | RSS exceeds 2GB (~3x baseline) | EC-004 | Graceful restart after current query | Auto-resume in new session |
| SubprocessMonitor | Duration limit (4h) | EC-003 | Warning at 90%; terminate at 100% with 30s grace | User starts new session |
| SubprocessMonitor | Zombie process detected | EC-120 | SIGTERM/SIGKILL + log | Automatic cleanup |
| ExtensionLoader | Invalid mcp.json | N/A | Log error; session starts without MCP servers | User fixes mcp.json |
| ExtensionLoader | Missing skill directory | N/A | Log warning; skill excluded | User creates SKILL.md |
| SDK | API timeout mid-stream | EC-106 | WS: "Response interrupted"; partial preserved | User retries |
| SDK | API rate limit (429) | EC-100 | WS: "AI service busy, retrying..." | Basic retry with backoff |

---

## 6. Component Design (Phase 1)

### 6.1 SessionManager

**Responsibility**: Owns the lifecycle of all sessions. Maps session IDs to ClaudeSDKClient instances. Coordinates with PreWarmPool, SubprocessMonitor, and ExtensionLoader.

**State Machine**:
```
[creating] --> [active] --> [idle] --> [terminated]
                  |            |
                  v            v
            [restarting]  [terminated]
```

**Key interfaces**:
- `create_session(user_id: str) -> SessionState`: Acquire from pool or cold start, load extensions, persist metadata
- `query(session_id: str, prompt: str) -> AsyncIterator[SDKMessage]`: Send prompt, yield streaming messages
- `interrupt(session_id: str) -> None`: Abort in-flight query
- `list_sessions() -> list[SessionSummary]`: All sessions with last-active timestamp
- `get_session(session_id: str) -> SessionState`: Session metadata and status
- `destroy_session(session_id: str) -> None`: SIGTERM/SIGKILL subprocess, remove from map, update DB
- `shutdown() -> None`: Graceful shutdown of all sessions

**Guardrails enforced**: G-001 (PID tracking), G-003 (one connection per session), G-003a (multiple concurrent sessions), G-006 (duration cap)

### 6.2 PreWarmPool

**Responsibility**: Maintain a pool of ready-to-use ClaudeSDKClient instances to eliminate cold start latency.

**Key interfaces**:
- `get() -> Optional[ClaudeSDKClient]`: Non-blocking; returns pre-warmed client or None
- `replenish() -> None`: Background task to fill pool to target size
- `invalidate() -> None`: Drain pool (called when extensions change)
- `depth() -> int`: Current pool size (for health checks)
- `startup_fill() -> bool`: Block until at least 1 slot filled; return False if all fail

**Configuration**:
- `PREWARM_POOL_SIZE`: Target pool depth (default: 2, minimum: 1)
- `PREWARM_TIMEOUT_SECONDS`: Max wait for single pre-warm (default: 60)
- `PREWARM_BACKOFF_SECONDS`: Pause after rate limit (default: 300)

**Guardrails enforced**: G-002 (block readiness until 1 slot filled)

### 6.3 WebSocketHandler

**Responsibility**: Accept WebSocket connections, authenticate, route messages between client and SessionManager, enforce one-connection-per-session.

**Message protocol** (client -> server):
- `{type: "user_message", text: str, session_id: str, seq: int}`
- `{type: "interrupt", session_id: str}`
- `{type: "create_session"}`
- `{type: "switch_session", session_id: str}`

**Message protocol** (server -> client):
- `{type: "session_ready", session_id: str, status: str, source: str}`
- `{type: "session_creating", estimated_seconds: int}`
- `{type: "session_list", sessions: list[SessionSummary]}`
- `{type: "message_received", seq: int}`
- `{type: "stream_delta", delta: str, seq: int}`
- `{type: "tool_use", tool: str, input: dict, seq: int}`
- `{type: "tool_result", result: dict, duration_ms: int, seq: int}`
- `{type: "response_complete", cost_usd: float, session_id: str, seq: int}`
- `{type: "stream_error", error: str, partial_preserved: bool, seq: int}`
- `{type: "stream_interrupted", seq: int}`
- `{type: "session_warning", reason: str, remaining_seconds: int, message: str}`
- `{type: "session_terminated", reason: str, message: str, resume_url: str}`
- `{type: "error", code: str, message: str}`

**Connection management**:
- Track active connections: `dict[session_id, WebSocket]`
- On new connection for existing session_id: close old connection with "Session opened elsewhere"
- On disconnect: if query in flight, buffer results for 60s then interrupt

**Guardrails enforced**: G-003 (one active connection per session_id), G-008 (no raw SDK errors to user)

### 6.4 ExtensionLoader

**Responsibility**: Scan filesystem for mcp.json, skills, and commands. Build ClaudeAgentOptions fields. Re-scan on new session creation (hot-detection).

**Key interfaces**:
- `load_options() -> ExtensionConfig`: Scan all sources, return merged config
- `get_mcp_servers() -> dict`: Parse mcp.json, return mcp_servers dict for ClaudeAgentOptions
- `get_setting_sources() -> list[str]`: Return ["user", "project"] if skills directory exists
- `get_commands() -> list[CommandDef]`: Scan ./commands/ directory

**File sources**:
- `mcp.json` in project root: MCP server definitions (same format as Claude Code)
- `./skills/<name>/SKILL.md`: Skill definitions (passed via setting_sources)
- `./commands/<name>`: Custom slash commands

**Hot-detection**: On each `load_options()` call (i.e., each new session creation), re-read files from disk. No file watcher needed for MVP; new sessions automatically pick up changes (FR-011c).

**Guardrails enforced**: G-003b (use same mechanism as Claude Code)

### 6.5 SubprocessMonitor

**Responsibility**: Monitor subprocess health (RSS memory, duration) and cleanup (zombies, orphaned processes).

**Background tasks** (asyncio):
- RSS check every 30 seconds for all active sessions
- Duration check every 60 seconds for all active sessions
- Zombie cleanup every 60 seconds

**Key interfaces**:
- `start() -> None`: Launch background monitoring tasks
- `stop() -> None`: Cancel background tasks
- `get_rss(pid: int) -> int`: Read RSS from /proc/<pid>/status (Linux) or ps (macOS dev)
- `check_duration(session: SessionState) -> Optional[str]`: Returns warning/terminate/None
- `cleanup_zombies() -> int`: Reap zombie processes, return count cleaned

**Thresholds** (configurable via env vars):
- `MAX_SESSION_DURATION_SECONDS`: Default 14400 (4 hours)
- `MAX_SESSION_RSS_MB`: Default 2048 (2 GB, ~3x the ~750MB baseline; corrected from previous 4GB)
- `DURATION_WARNING_PERCENT`: Default 90

**Guardrails enforced**: G-006 (duration cap), G-007 (graceful restart, not hard kill)

### 6.6 SessionRepository (aiosqlite)

**Responsibility**: Persist session metadata to SQLite for session list, resume, and operational queries.

**Schema**:
```
Table: sessions
  - session_id: TEXT PRIMARY KEY
  - user_id: TEXT NOT NULL (single user for MVP, placeholder for Phase 2)
  - status: TEXT NOT NULL (creating|active|idle|terminated)
  - created_at: TEXT NOT NULL (ISO 8601)
  - last_active_at: TEXT NOT NULL (ISO 8601)
  - subprocess_pid: INTEGER
  - message_count: INTEGER DEFAULT 0
  - total_cost_usd: REAL DEFAULT 0.0
  - is_resumable: BOOLEAN DEFAULT TRUE
  - terminated_reason: TEXT
```

**Key interfaces**:
- `save(session: SessionMetadata) -> None`
- `update_activity(session_id: str, message_count: int, cost: float) -> None`
- `get(session_id: str) -> Optional[SessionMetadata]`
- `list_active() -> list[SessionMetadata]`
- `mark_terminated(session_id: str, reason: str) -> None`

### 6.7 React Chat UI Components

**Component tree**:
```
App
+-- AuthGate (checks API key validity)
+-- ChatLayout
    +-- Sidebar
    |   +-- SessionList (list of sessions, create new, switch)
    |   +-- SessionItem (session name, last-active, message count)
    +-- ChatPanel
        +-- MessageList (scrollable, auto-scroll on new messages)
        |   +-- UserMessage (user's text)
        |   +-- AssistantMessage (Claude's streaming text)
        |   +-- ToolUseCard (tool name, status, result, collapse/expand)
        |   +-- ErrorMessage (actionable error with retry button)
        |   +-- SystemMessage (session warnings, termination)
        +-- InputBar (textarea, send button, interrupt shortcut)
        +-- StatusBar (connection status, session info, cost)
```

**Zustand stores**:
- `useMessageStore`: Messages per session, streaming buffer, append/finalize
- `useSessionStore`: Session list, active session ID, create/switch/destroy
- `useStreamingStore`: Is streaming, connection status, pending interrupt

**Key interactions**:
- Enter in InputBar -> send user_message via WebSocket -> optimistic add to messages
- Ctrl+Shift+X -> send interrupt via WebSocket -> show "[Interrupted]" in message
- Click session in SessionList -> send switch_session via WebSocket -> load messages
- Click "New Session" -> send create_session via WebSocket -> wait for session_ready

---

## 7. Proposed Project Structure

```
claude_sdk_pattern/
+-- pyproject.toml                 # uv-managed, dependencies
+-- Dockerfile                     # Multi-stage: Python backend + React frontend
+-- mcp.json                       # User's MCP server config (example provided)
+-- skills/                        # User's skill definitions
|   +-- example/
|       +-- SKILL.md
+-- commands/                      # User's custom commands
+-- src/
|   +-- claude_sdk_pattern/
|       +-- __init__.py
|       +-- main.py                # FastAPI app factory, startup/shutdown events
|       +-- config.py              # Environment variable configuration
|       +-- core/
|       |   +-- __init__.py
|       |   +-- session_manager.py  # SessionManager class
|       |   +-- prewarm_pool.py     # PreWarmPool class
|       |   +-- subprocess_monitor.py # SubprocessMonitor class
|       |   +-- extension_loader.py  # ExtensionLoader class
|       +-- api/
|       |   +-- __init__.py
|       |   +-- websocket.py        # WebSocketHandler, /ws/v1/chat
|       |   +-- rest.py             # REST endpoints: sessions, health
|       |   +-- auth.py             # API key middleware
|       |   +-- message_types.py    # WebSocket message type definitions
|       +-- db/
|       |   +-- __init__.py
|       |   +-- repository.py       # SessionRepository (aiosqlite)
|       |   +-- migrations.py       # Schema creation
|       +-- models/
|           +-- __init__.py
|           +-- session.py           # SessionState, SessionMetadata, SessionSummary
|           +-- messages.py          # WebSocket message models (Pydantic)
|           +-- extensions.py        # ExtensionConfig, MCP server config models
+-- frontend/
|   +-- package.json
|   +-- vite.config.ts
|   +-- tsconfig.json
|   +-- index.html
|   +-- src/
|       +-- main.tsx                 # React entry point
|       +-- App.tsx                  # Top-level layout
|       +-- stores/
|       |   +-- messageStore.ts      # Zustand: messages per session
|       |   +-- sessionStore.ts      # Zustand: session list and active
|       |   +-- streamingStore.ts    # Zustand: streaming state
|       +-- hooks/
|       |   +-- useWebSocket.ts      # WebSocket connection management
|       |   +-- useChat.ts           # Send message, handle responses
|       +-- components/
|       |   +-- ChatLayout.tsx       # Main layout: sidebar + chat panel
|       |   +-- Sidebar.tsx          # Session list container
|       |   +-- SessionList.tsx      # List of sessions
|       |   +-- SessionItem.tsx      # Individual session entry
|       |   +-- ChatPanel.tsx        # Message list + input bar
|       |   +-- MessageList.tsx      # Scrollable message container
|       |   +-- UserMessage.tsx      # User message bubble
|       |   +-- AssistantMessage.tsx # Assistant message with streaming
|       |   +-- ToolUseCard.tsx      # Tool execution display
|       |   +-- ErrorMessage.tsx     # Actionable error display
|       |   +-- InputBar.tsx         # Message input with shortcuts
|       |   +-- StatusBar.tsx        # Connection and session status
|       |   +-- AuthGate.tsx         # API key entry screen
|       +-- types/
|       |   +-- messages.ts          # WebSocket message type definitions
|       |   +-- session.ts           # Session types
|       +-- utils/
|           +-- websocket.ts         # WebSocket client with reconnection
+-- tests/
|   +-- unit/
|   |   +-- test_extension_loader.py
|   |   +-- test_session_manager.py
|   |   +-- test_prewarm_pool.py
|   |   +-- test_subprocess_monitor.py
|   +-- integration/
|       +-- test_websocket_flow.py   # End-to-end WebSocket chat
|       +-- test_session_lifecycle.py # Create, query, resume, destroy
|       +-- test_extension_loading.py # mcp.json, skills, commands
+-- scripts/
    +-- dev.sh                       # Start backend + frontend for development
    +-- healthcheck.sh               # Docker health check script
```

---

## 8. Dependency Graph (Build Order)

The following shows component dependencies and recommended build sequence.

```
Layer 0 (No dependencies -- build first):
  +-- config.py (environment variable parsing)
  +-- models/ (Pydantic models for sessions, messages, extensions)
  +-- db/migrations.py (SQLite schema creation)

Layer 1 (Depends on Layer 0):
  +-- db/repository.py (SessionRepository, depends on models + migrations)
  +-- core/extension_loader.py (depends on models/extensions)
  +-- api/auth.py (depends on config)

Layer 2 (Depends on Layer 1):
  +-- core/prewarm_pool.py (depends on extension_loader, config)
  +-- core/subprocess_monitor.py (depends on models/session, config)

Layer 3 (Depends on Layer 2):
  +-- core/session_manager.py (depends on prewarm_pool, subprocess_monitor,
  |                            extension_loader, repository)
  +-- api/message_types.py (depends on models/messages)

Layer 4 (Depends on Layer 3):
  +-- api/websocket.py (depends on session_manager, message_types, auth)
  +-- api/rest.py (depends on session_manager, auth)

Layer 5 (Depends on Layer 4):
  +-- main.py (wires everything: FastAPI app, startup/shutdown events)

Frontend (parallel track, can start at Layer 0):
  Phase F1: types/, stores/ (message and session types, Zustand stores)
  Phase F2: hooks/ (WebSocket connection, chat logic)
  Phase F3: components/ (UI components, compose with hooks)
  Phase F4: App.tsx, integration with backend
```

**Recommended build sequence** (2 developers: 1 backend, 1 frontend):

| Week | Backend | Frontend |
|------|---------|----------|
| 1 | Layer 0-2: config, models, DB, extension_loader, prewarm_pool | F1-F2: types, stores, WebSocket hook |
| 2 | Layer 3: session_manager, subprocess_monitor | F3: MessageList, InputBar, ToolUseCard |
| 3 | Layer 4-5: websocket handler, REST API, main.py | F3-F4: SessionList, ChatLayout, integration |
| 4 | Integration testing, Docker, bug fixes | Polish, error states, responsive layout |

---

## 9. Phase 2/3 Extension Points

These are NOT designed in Phase 1 but the architecture accommodates them:

| Future Feature | Extension Point | How Architecture Supports It |
|---------------|-----------------|------------------------------|
| PluginRegistry (Phase 2) | Wraps ExtensionLoader | ExtensionLoader returns ExtensionConfig; PluginRegistry adds lifecycle on top |
| OptionsBuilder (Phase 2) | Replaces direct config build | SessionManager calls OptionsBuilder instead of ExtensionLoader.load_options() |
| JWT Auth (Phase 2) | Replaces API key middleware | api/auth.py swapped from key check to JWT decode; WebSocket refresh protocol added |
| RBAC (Phase 2) | Added to SessionManager and WebSocket | SessionManager checks user role before operations; WebSocket checks permissions |
| Cost tracking (Phase 2) | ResultMessage.total_cost_usd already captured | SessionRepo stores cost; new CostTracker aggregates per user |
| WebSocket reconnection sync (Phase 2) | Sequence numbers already in protocol | Add message buffer per session; replay on reconnect |
| PostgreSQL (Phase 2) | Replace SessionRepository | repository.py interface stays same; implementation swapped to asyncpg |
| Circuit breaker (Phase 3) | Wraps SDK query calls | SessionManager.query() wrapped with aiobreaker decorator |
| Prometheus metrics (Phase 3) | Instrument existing components | Add prometheus-fastapi-instrumentator + custom gauges/counters |
| Container-per-session (Phase 3) | External orchestration | SessionManager becomes a thin proxy to container management API. Deferred from MVP: single-host with 10 sessions on 16GB is feasible given corrected ~750MB baseline. Container-per-session provides isolation benefits, not memory necessity. |

---

## 10. Complexity Tracking

| Component | Estimated LOC | Risk | Rationale |
|-----------|--------------|------|-----------|
| SessionManager | 300-400 | Medium-High | Core orchestration, many edge cases |
| PreWarmPool | 150-200 | Medium | asyncio queue + background tasks |
| SubprocessMonitor | 200-250 | Medium | /proc parsing, signal handling |
| ExtensionLoader | 100-150 | Low | File reading, JSON parsing |
| WebSocketHandler | 250-350 | Medium | Bidirectional message routing |
| REST API | 100-150 | Low | Session list, health check |
| Auth middleware | 50-80 | Low | Key validation |
| SessionRepository | 100-150 | Low | CRUD with aiosqlite |
| React UI (total) | 800-1200 | Medium | 12 components + 3 stores + 2 hooks |
| **Backend total** | **1250-1730** | | |
| **Frontend total** | **800-1200** | | |
| **Grand total** | **2050-2930** | | |

### 10.1 Capacity Estimates (Corrected)

Based on corrected memory baseline data (GitHub #4953 evidence: ~500MB-1GB per subprocess, not previously stated 2.5GB):

| Parameter | Value | Basis |
|-----------|-------|-------|
| Subprocess baseline RAM | ~500MB-1GB (~750MB midpoint) | Actual GitHub issue evidence |
| 10 sessions baseline | ~7.5GB (10 x 750MB) | Midpoint calculation |
| 10 sessions with leak headroom | ~15GB (10 x 1.5GB conservative) | 2x buffer for memory growth over session lifetime |
| OS + FastAPI + React build serving | ~1-2GB | Platform overhead |
| **Minimum server RAM (10 sessions)** | **16GB (tight) / 32GB (comfortable)** | Total: ~7.5GB baseline + ~2GB overhead + headroom |
| Pre-warm pool (2-3 slots) | ~1.5-2.25GB | 2-3 x ~750MB, included in session count |
| RSS restart threshold per session | 2GB (~3x baseline) | Triggers graceful restart before unbounded growth |
| Cold start latency | 20-30 seconds | Unchanged; pool of 2-3 covers burst creation |
| Session duration cap | 4 hours | Mitigates unbounded memory growth risk |

**Conclusion**: 10 concurrent sessions is comfortably feasible on a 16GB host given the corrected ~500MB-1GB baseline. The previous estimate of "2-3 sessions per 16GB server" was based on an incorrect 2.5GB baseline. Container-per-session is a Phase 3 optimization for isolation and scaling, not an MVP requirement for memory management.

---

*End of Architecture*
