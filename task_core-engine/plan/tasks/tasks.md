# Task Breakdown: core-engine (Phase 1 MVP)

**Generated From**: Phase 1 Implementation Plan
**Total Tasks**: 28
**Estimated Total Effort**: 48 hours
**Organization**: By User Story (story-phase pattern)

---

## References
- **Implementation Plan**: `plan/strategy/implementation_plan.md`
- **Architecture**: `plan/strategy/architecture.md`
- **Decisions**: `plan/decision-log.md`
- **User Stories**: `specs/user-stories.md`
- **Edge Case Resolutions**: `specs/edge-case-resolutions.md`

---

## TASK-001: Initialize Python project with uv and pyproject.toml

### Task Description
Create the Python project skeleton using uv. Set up pyproject.toml with all Phase 1 dependencies (FastAPI, uvicorn, aiosqlite, structlog, pydantic, claude-agent-sdk ~0.1.30). Create the src/claude_sdk_pattern/ package structure with all subdirectories (core/, api/, db/, models/).

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: N/A - Setup task
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 1 (Setup)

### Dependencies
- **Blocked By**: None
- **Blocks**: TASK-002, TASK-003, TASK-004, TASK-005

### Integration Contract Reference
- **Contract**: Architecture Section 7 (Project Structure)
- **Type**: Project Scaffold

### Task Steps
1. Initialize uv project with `uv init`
2. Configure pyproject.toml with project metadata and all Phase 1 dependencies
3. Create src/claude_sdk_pattern/ package with __init__.py
4. Create subdirectories: core/, api/, db/, models/ each with __init__.py
5. Create tests/ directory with unit/ and integration/ subdirectories
6. Verify `uv sync` installs all dependencies successfully

### Acceptance Criteria
- [ ] AC1: `uv sync` completes without errors and all Phase 1 dependencies are installed
- [ ] AC2: Package structure matches architecture.md Section 7 layout
- [ ] AC3: `python -c "import claude_sdk_pattern"` succeeds

---

## TASK-002: Initialize Vite + React 19 frontend scaffold

### Task Description
Create the frontend/ directory with a Vite + React 19 + TypeScript project. Install Zustand, Radix UI, and Tailwind CSS. Set up the types/ directory with WebSocket message and session type definitions matching the contracts in implementation_plan.md Section 4.2-4.3.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: N/A - Setup task
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 1 (Setup)

### Dependencies
- **Blocked By**: None
- **Blocks**: TASK-020, TASK-021, TASK-022

### Integration Contract Reference
- **Contract**: Architecture Section 7 (Frontend Structure)
- **Type**: Project Scaffold

### Task Steps
1. Create frontend/ directory, initialize Vite + React 19 + TypeScript project
2. Install Zustand, Radix UI primitives, Tailwind CSS
3. Create types/messages.ts with all WebSocket message type definitions from Section 4.2
4. Create types/session.ts with SessionSummary, ToolUseDisplay, ExtensionInfo types from Section 4.3
5. Verify `npm run build` succeeds

### Acceptance Criteria
- [ ] AC1: `npm run dev` starts the Vite dev server without errors
- [ ] AC2: TypeScript types in types/messages.ts match all 15 WebSocket message types from Section 4.2
- [ ] AC3: TypeScript types in types/session.ts match SessionSummary, ToolUseDisplay, ExtensionInfo from Section 4.3

---

## TASK-003: Implement configuration module and Pydantic data models

### Task Description
Create config.py with Pydantic Settings for all 13 environment variables from implementation_plan.md Section 3.1. Create Pydantic models for SessionMetadata, SessionState, SessionSummary, SessionStatus enum, all WebSocket message types (client-to-server and server-to-client), ExtensionConfig, MCPServerConfig, CommandDef, and MonitorAction.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: N/A - Foundational
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 2 (Foundational)

### Dependencies
- **Blocked By**: TASK-001
- **Blocks**: TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.1 (Config), Section 4.2-4.4 (Messages), Section 5 (Data Models)
- **Type**: Data Contract

### Task Steps
1. Create config.py with Pydantic BaseSettings class for all 13 env vars with defaults
2. Create models/session.py with SessionMetadata, SessionState, SessionSummary, SessionStatus enum
3. Create models/messages.py with all client-to-server and server-to-client WebSocket message models
4. Create models/extensions.py with ExtensionConfig, MCPServerConfig, CommandDef
5. Add validation rules per Section 4.4 (message text max 32k, API key max 256, session_id UUID format)

### Acceptance Criteria
- [ ] AC1: Config loads all 13 env vars with correct defaults per Section 3.1 table
- [ ] AC2: All 5 client-to-server message types validated by Pydantic (user_message, interrupt, create_session, switch_session, destroy_session)
- [ ] AC3: All 13 server-to-client message types serializable (session_list, session_ready, session_creating, message_received, stream_delta, tool_use, tool_result, response_complete, stream_error, stream_interrupted, session_warning, session_terminated, error)
- [ ] AC4: Input validation rejects empty messages, messages > 32k chars, invalid UUID session_ids

---

## TASK-004: Implement SQLite schema and SessionRepository

### Task Description
Create the SQLite schema for the sessions table matching Section 5.1 and implement the SessionRepository class with aiosqlite. The repository provides async CRUD operations for session metadata persistence.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-006 - Session Resume (also used by US-001, US-002)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 2 (Foundational)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: TASK-010

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.2 (Session Repository), Section 5.1 (SessionMetadata Schema)
- **Type**: Data Contract

### Task Steps
1. Create db/migrations.py with SQLite table creation for sessions table (10 columns per Section 5.1)
2. Create db/repository.py with SessionRepository class
3. Implement initialize() to create tables if not exist
4. Implement save(), get(), list_active(), update_activity(), mark_terminated()
5. Write integration tests using real aiosqlite (no mocking)

### Acceptance Criteria
- [ ] AC1: sessions table created with all 10 columns matching Section 5.1 (session_id TEXT PK, user_id, status, created_at, last_active_at, subprocess_pid, message_count, total_cost_usd, is_resumable, terminated_reason)
- [ ] AC2: save() persists and get() retrieves a SessionMetadata with all fields intact
- [ ] AC3: list_active() returns only sessions with status in ("creating", "active", "idle"), excludes "terminated"

---

## TASK-005: Implement API key authentication middleware

### Task Description
Create the auth module with API key validation for both REST endpoints (via header middleware) and WebSocket connections (via query parameter or header during upgrade). The key is compared against CLAUDE_SDK_PATTERN_API_KEY from config.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start (auth is prerequisite for session access)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 2 (Foundational)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: TASK-013, TASK-014

### Integration Contract Reference
- **Contract**: Implementation Plan Section 4.1 (API Endpoints - auth header), Section 4.4 (User Input Validation - API key)
- **Type**: API Endpoint / User Input Spec

### Task Steps
1. Create api/auth.py with verify_api_key dependency for FastAPI
2. Implement REST middleware that extracts X-API-Key header and validates against config
3. Implement WebSocket auth helper that validates key during upgrade handshake
4. Return 401 with `{"error": "unauthorized", "message": "Invalid API key"}` on failure
5. Ensure API key never appears in logs or error responses (G-009)

### Acceptance Criteria
- [ ] AC1: Valid X-API-Key header returns 200 on protected REST endpoints
- [ ] AC2: Invalid or missing API key returns 401 with exact error body `{"error": "unauthorized", "message": "Invalid API key"}`
- [ ] AC3: API key value never appears in log output or error responses

---

## TASK-006: Implement ExtensionLoader

### Task Description
Create the ExtensionLoader class that scans the filesystem for mcp.json, ./skills/ directories, and ./commands/ files. Builds ClaudeAgentOptions-compatible configuration. Re-reads from disk on every call for hot-detection (FR-011c).

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start (extensions loaded at session creation)
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 3 (US-001)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: TASK-008, TASK-010

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.3 (Extension Loader), Section 4.3 (ExtensionInfo), Section 5.3-5.4 (ExtensionConfig, MCPServerConfig)
- **Type**: Component Spec

### Task Steps
1. Create core/extension_loader.py with ExtensionLoader class
2. Implement get_mcp_servers() to parse mcp.json from project root (Claude Code format)
3. Implement get_skill_directories() to scan ./skills/<name>/SKILL.md
4. Implement get_commands() to scan ./commands/ directory
5. Implement load_options() that aggregates all sources into ExtensionConfig
6. Handle errors: invalid JSON logged and skipped, missing directories silently skipped

### Acceptance Criteria
- [ ] AC1: Valid mcp.json with 2 servers returns ExtensionConfig with both servers' command, args, and env fields
- [ ] AC2: Missing mcp.json returns ExtensionConfig with empty mcp_servers (no crash)
- [ ] AC3: Invalid JSON in mcp.json logs error and returns empty mcp_servers (does not crash)
- [ ] AC4: ./skills/code-review/SKILL.md discovered and included in skill_directories list

---

## TASK-007: Implement PreWarmPool

### Task Description
Create the PreWarmPool class with asyncio.Queue-based pool of ready ClaudeSDKClient instances. Implements startup_fill() that blocks until at least 1 slot is filled (G-002), background replenishment, and pool invalidation.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 3 (US-001)

### Dependencies
- **Blocked By**: TASK-003, TASK-006
- **Blocks**: TASK-010

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.4 (Pre-Warm Pool), Architecture Section 6.2 (PreWarmPool)
- **Type**: Component Spec

### Task Steps
1. Create core/prewarm_pool.py with PreWarmPool class
2. Implement __init__ with asyncio.Queue and configurable pool_size
3. Implement startup_fill() that blocks until >= 1 slot filled, returns False if all fail
4. Implement get() as non-blocking Queue.get_nowait, returning None if empty
5. Implement replenish() as background asyncio task with backoff on rate limit (EC-014)
6. Implement invalidate() to drain queue and shutdown() for cleanup

### Acceptance Criteria
- [ ] AC1: startup_fill() returns True when at least 1 client is successfully created
- [ ] AC2: startup_fill() returns False when all creation attempts fail
- [ ] AC3: get() returns a client from pool in < 100ms when pool has slots
- [ ] AC4: get() returns None when pool is empty (non-blocking)

---

## TASK-008: Implement SubprocessMonitor

### Task Description
Create the SubprocessMonitor class that runs background asyncio tasks to monitor RSS memory (every 30s), session duration (every 60s), and clean up zombie processes (every 60s). Returns MonitorAction objects describing what actions to take.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-004 - Session Memory Limits
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 4 (US-004)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: TASK-010

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.5 (Subprocess Monitor), Architecture Section 6.5 (SubprocessMonitor)
- **Type**: Component Spec

### Task Steps
1. Create core/subprocess_monitor.py with SubprocessMonitor class
2. Implement get_rss(pid) with platform detection: /proc/<pid>/status on Linux, `ps -o rss=` on macOS
3. Implement check_all() that iterates active sessions, checks RSS and duration, returns MonitorAction list
4. Implement start() to launch background asyncio tasks for RSS (30s), duration (60s), zombie cleanup (60s)
5. Implement zombie detection: list child processes, identify PIDs not in active sessions, SIGTERM/SIGKILL

### Acceptance Criteria
- [ ] AC1: get_rss() returns RSS in bytes for a known PID (or None for invalid PID)
- [ ] AC2: check_all() returns MonitorAction(type="warn_duration") when session elapsed >= 90% of max
- [ ] AC3: check_all() returns MonitorAction(type="terminate_duration") when session elapsed >= 100% of max
- [ ] AC4: check_all() returns MonitorAction(type="restart_memory") when session RSS exceeds MAX_SESSION_RSS_MB

---

## TASK-009: Implement WebSocket message type definitions

### Task Description
Create the api/message_types.py module that defines the message routing logic: parse incoming WebSocket JSON into typed client messages, and provide factory functions for creating server-to-client response messages. This bridges between raw JSON and the Pydantic models.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-002 - Streaming Chat Conversation
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 2 (Foundational)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: TASK-013

### Integration Contract Reference
- **Contract**: Implementation Plan Section 4.2 (WebSocket Message Contracts)
- **Type**: Data Contract

### Task Steps
1. Create api/message_types.py with parse_client_message(raw_json: str) function
2. Implement routing: parse "type" field, validate against appropriate Pydantic model
3. Create factory functions for each server message type (create_stream_delta, create_tool_use, etc.)
4. Handle invalid JSON with clear error response (EC-029)
5. Handle unknown message types with error response

### Acceptance Criteria
- [ ] AC1: parse_client_message correctly routes all 5 client message types to their Pydantic models
- [ ] AC2: Invalid JSON returns error message with code "invalid_json"
- [ ] AC3: Factory functions produce JSON-serializable dicts matching exact contract shapes from Section 4.2

---

## TASK-010: Implement SessionManager

### Task Description
Create the SessionManager class that orchestrates session lifecycle. Coordinates PreWarmPool, SubprocessMonitor, ExtensionLoader, and SessionRepository. Manages the in-memory sessions dict, handles create/query/interrupt/destroy/resume operations.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start, US-002 - Streaming Chat
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5
- **Phase**: Phase 3 (US-001)

### Dependencies
- **Blocked By**: TASK-003, TASK-004, TASK-006, TASK-007, TASK-008
- **Blocks**: TASK-011, TASK-013, TASK-014

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.6 (Session Manager), Architecture Section 6.1 (SessionManager)
- **Type**: Component Spec

### Task Steps
1. Create core/session_manager.py with SessionManager class
2. Implement create_session(): acquire from pool (or cold start), load extensions, persist metadata, track PID
3. Implement query(session_id, prompt) as async iterator: validate session, set is_query_active, iterate SDK messages, yield stream events, update metadata on completion
4. Implement interrupt(session_id): call client.interrupt(), set is_query_active=False
5. Implement list_sessions(), get_session(), destroy_session() with SIGTERM/SIGKILL cleanup
6. Implement shutdown() for graceful cleanup of all sessions

### Acceptance Criteria
- [ ] AC1: create_session() returns SessionState with valid session_id, client, pid, and status "active"
- [ ] AC2: create_session() uses pre-warmed client when pool has capacity (source="pre-warmed")
- [ ] AC3: query() yields stream events (stream_delta, tool_use, tool_result, response_complete) matching contract types
- [ ] AC4: destroy_session() sends SIGTERM, waits 5s, sends SIGKILL if needed, removes from sessions dict
- [ ] AC5: Capacity check rejects new sessions when active count >= MAX_SESSIONS with "capacity_exceeded" error

---

## TASK-011: Implement SessionManager monitor integration

### Task Description
Connect the SubprocessMonitor's check_all() output to SessionManager actions. When monitor detects duration warnings, duration termination, memory restart, or zombies, SessionManager executes the corresponding lifecycle operations and sends WebSocket notifications.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-004 - Session Memory Limits
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 4 (US-004)

### Dependencies
- **Blocked By**: TASK-010
- **Blocks**: TASK-015

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.5-3.6, Control Flow us-004-session-limits.md
- **Type**: Component Spec

### Task Steps
1. Add process_monitor_actions(actions: list[MonitorAction]) method to SessionManager
2. Handle "warn_duration": send session_warning WebSocket message with remaining_seconds
3. Handle "terminate_duration": wait for in-flight query (30s grace), then destroy_session
4. Handle "restart_memory": notify user via session_restarting, destroy old, create new with resume
5. Handle "cleanup_zombie": SIGTERM/SIGKILL orphaned PID, log warning

### Acceptance Criteria
- [ ] AC1: Duration warning at 90% sends session_warning with correct remaining_seconds
- [ ] AC2: Duration termination waits for in-flight query up to 30s grace period before destroying
- [ ] AC3: Memory restart creates new session with resume=old_session_id after cleanup
- [ ] AC4: Zombie cleanup sends SIGTERM then SIGKILL for orphaned PIDs not in active sessions

---

## TASK-012: Implement session resume capability

### Task Description
Add resume functionality to SessionManager. When resuming, create a new ClaudeSDKClient with resume=session_id parameter so the SDK loads previous conversation context from disk. Handle corrupted session data gracefully (EC-007).

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-006 - Session Resume
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 5 (US-006)

### Dependencies
- **Blocked By**: TASK-010
- **Blocks**: None

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.6 (resume_session), User Stories US-006
- **Type**: Component Spec

### Task Steps
1. Add resume_session(session_id: str) method to SessionManager
2. Look up session metadata from repository, verify is_resumable=True
3. Create new ClaudeSDKClient with resume=session_id parameter
4. Handle resume failure (corrupted data): log, start fresh session, notify user (EC-007)
5. Update session metadata with new PID and status

### Acceptance Criteria
- [ ] AC1: resume_session() creates new client with previous conversation context intact
- [ ] AC2: resume_session() on non-resumable session returns error "Session not found or not resumable"
- [ ] AC3: Corrupted SDK session data triggers fresh session with user notification "Previous session could not be restored"

---

## TASK-013: Implement WebSocket handler

### Task Description
Create the WebSocket endpoint at /ws/v1/chat. Handles authentication, message routing, streaming response relay, connection deduplication (G-003), and error handling. This is the primary client-server communication channel.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-002 - Streaming Chat Conversation, US-005 - Chat Input and Controls
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5
- **Phase**: Phase 3 (US-001) - needed for session flow

### Dependencies
- **Blocked By**: TASK-005, TASK-009, TASK-010
- **Blocks**: TASK-015

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.7 (WebSocket Handler), Section 4.2 (Message Contracts)
- **Type**: API Endpoint

### Task Steps
1. Create api/websocket.py with WebSocket endpoint at /ws/v1/chat
2. Implement connection lifecycle: accept, authenticate (API key), send session_list, enter message loop
3. Route client messages: user_message to query(), interrupt to interrupt(), create_session, switch_session, destroy_session
4. Stream SDK responses as WebSocket frames: stream_delta, tool_use, tool_result, response_complete
5. Enforce one-connection-per-session (G-003): track active connections, close old on duplicate
6. Handle errors: query_in_progress rejection (EC-032), invalid JSON (EC-029), session_not_found

### Acceptance Criteria
- [ ] AC1: Valid API key allows WebSocket upgrade; invalid key returns 1008 Policy Violation close
- [ ] AC2: user_message routes to SessionManager.query() and streams back stream_delta frames
- [ ] AC3: interrupt message calls SessionManager.interrupt() and sends stream_interrupted
- [ ] AC4: Duplicate connection for same session_id closes old connection with "session_opened_elsewhere"
- [ ] AC5: Sending user_message while query in flight returns error with code "query_in_progress"

---

## TASK-014: Implement REST API endpoints

### Task Description
Create REST endpoints for session management and health checks. All session endpoints require API key auth. Health endpoints are unauthenticated.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start (health/ready), US-004 - Session Memory Limits (session management)
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5
- **Phase**: Phase 3 (US-001)

### Dependencies
- **Blocked By**: TASK-005, TASK-010
- **Blocks**: TASK-015

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.8 (REST API), Section 4.1 (API Endpoints)
- **Type**: API Endpoint

### Task Steps
1. Create api/rest.py with FastAPI router
2. Implement GET /api/v1/sessions (list all sessions with SessionSummary response)
3. Implement POST /api/v1/sessions (create new session, return 201 or 503)
4. Implement DELETE /api/v1/sessions/{session_id} (destroy, return 200 or 404)
5. Implement GET /api/v1/health/live (return {"status": "ok"})
6. Implement GET /api/v1/health/ready (check pool depth and active sessions)
7. Implement GET /api/v1/extensions (list loaded extensions)

### Acceptance Criteria
- [ ] AC1: GET /api/v1/sessions returns session list matching SessionSummary contract (7 fields each)
- [ ] AC2: POST /api/v1/sessions returns 201 with session_id when capacity available, 503 when at max
- [ ] AC3: DELETE /api/v1/sessions/{id} returns 200 with status "terminated" or 404 if not found
- [ ] AC4: GET /api/v1/health/live returns 200 always; /ready returns 503 when pool empty and at capacity
- [ ] AC5: All session endpoints return 401 when API key is missing or invalid

---

## TASK-015: Implement FastAPI application entry point

### Task Description
Create main.py with the FastAPI application factory. Wire all components together in correct startup sequence (config, logging, DB, extensions, pool, monitor, session manager, routes). Implement graceful shutdown.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start (startup), US-013 - Graceful Shutdown
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 3 (US-001)

### Dependencies
- **Blocked By**: TASK-010, TASK-013, TASK-014
- **Blocks**: TASK-016, TASK-017

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.9 (Application Entry Point)
- **Type**: Component Spec

### Task Steps
1. Create main.py with create_app() factory function
2. Implement startup event: load config, init structlog, init DB, init ExtensionLoader, init PreWarmPool, call startup_fill(), init SubprocessMonitor, init SessionManager, mount routes
3. If startup_fill() returns False: log CRITICAL, exit(1)
4. Implement shutdown event: stop new connections, notify WebSockets "server_shutting_down", wait 30s for in-flight, shutdown session manager and pool, close DB
5. Mount static file serving for frontend build output

### Acceptance Criteria
- [ ] AC1: Application starts successfully with valid ANTHROPIC_API_KEY and reaches "ready" state
- [ ] AC2: Application exits with code 1 if all pre-warm attempts fail
- [ ] AC3: SIGTERM triggers graceful shutdown: in-flight queries complete, all subprocesses cleaned
- [ ] AC4: Static files served from frontend build directory at root path

---

## TASK-016: Implement structlog JSON logging

### Task Description
Configure structlog for JSON-formatted logging with correlation IDs and session context. All log entries include timestamp, level, event name, and optional session_id. Ensure API keys are never logged (G-009).

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-007 - Error Messages with Context (logging supports debugging)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 2 (Foundational)

### Dependencies
- **Blocked By**: TASK-003
- **Blocks**: None

### Integration Contract Reference
- **Contract**: Feature Spec FR-026 (Structured JSON Logging), Architecture Section 7 (structlog)
- **Type**: Component Spec

### Task Steps
1. Create a logging configuration function in config.py or a dedicated logging module
2. Configure structlog with JSON renderer, timestamp processor, level filter from LOG_LEVEL env var
3. Add session_id and correlation_id binding support via structlog.contextvars
4. Add secret filtering processor: scrub any value matching API key patterns from log output
5. Verify all existing components use structlog.get_logger() consistently

### Acceptance Criteria
- [ ] AC1: Log output is valid JSON with timestamp, level, and event fields
- [ ] AC2: Session-scoped logs include session_id field when bound
- [ ] AC3: API key values are never present in any log output (tested by injecting key into log context)

---

## TASK-017: Implement Dockerfile and Docker build

### Task Description
Create a multi-stage Dockerfile that builds both the Python backend and React frontend. The container should start a working instance accessible via browser. Include a healthcheck script.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: N/A - Deployment (FR-012)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 7 (Polish)

### Dependencies
- **Blocked By**: TASK-015
- **Blocks**: None

### Integration Contract Reference
- **Contract**: Feature Spec FR-012 (Docker containerization)
- **Type**: Component Spec

### Task Steps
1. Create Dockerfile with multi-stage build: Node.js stage for frontend, Python stage for backend
2. Frontend stage: npm install, npm run build, output to /app/static
3. Backend stage: uv sync, copy src/ and static/, expose PORT
4. Create scripts/healthcheck.sh that curls /api/v1/health/live
5. Add HEALTHCHECK instruction to Dockerfile

### Acceptance Criteria
- [ ] AC1: `docker build` completes in < 5 minutes
- [ ] AC2: `docker run` with required env vars starts the application and /api/v1/health/live returns 200
- [ ] AC3: Browser can access the React UI via the container's exposed port

---

## TASK-018: Implement error message translation layer

### Task Description
Create an error handling module that translates raw SDK errors, API errors, and internal exceptions into user-friendly WebSocket error messages per G-008. Each error includes what happened, why, and suggested action.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-007 - Error Messages with Context
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 6 (US-007)

### Dependencies
- **Blocked By**: TASK-003, TASK-009
- **Blocks**: None

### Integration Contract Reference
- **Contract**: Implementation Plan Section 4.2 (error, stream_error messages), User Stories US-007
- **Type**: Component Spec

### Task Steps
1. Create an error translation module (in api/ or core/)
2. Map SDK exceptions to user-friendly messages: API timeout -> "Response interrupted. You can retry."
3. Map rate limit (429) to "The AI service is temporarily busy. Retrying automatically..."
4. Map session terminated (memory) to "Session restarted for performance. Conversation preserved."
5. Ensure no raw SDK error strings reach the client (G-008)

### Acceptance Criteria
- [ ] AC1: API timeout produces stream_error with suggested_action="retry" and partial_preserved=true
- [ ] AC2: Rate limit (429) produces error with message about temporary unavailability
- [ ] AC3: Session termination (memory) produces session_restarting with preservation message
- [ ] AC4: No raw SDK exception messages appear in any WebSocket error frame

---

## TASK-019: Implement idle session timeout

### Task Description
Add idle timeout tracking to SessionManager. Sessions without activity for SESSION_IDLE_TIMEOUT_SECONDS (default 30 min) transition to "idle" state and eventually are cleaned up. This prevents resource waste from abandoned sessions.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-006 - Session Resume (idle timeout triggers transition to resumable state)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 5 (US-006)

### Dependencies
- **Blocked By**: TASK-010
- **Blocks**: None

### Integration Contract Reference
- **Contract**: Implementation Plan Section 3.1 (SESSION_IDLE_TIMEOUT_SECONDS), User Stories US-006 scenario 1
- **Type**: Component Spec

### Task Steps
1. Add idle check to SubprocessMonitor or SessionManager background task
2. Track last_active_at on every query completion
3. When idle timeout exceeded: transition session status to "idle"
4. After additional grace period: terminate subprocess but keep metadata (is_resumable=True)
5. User returning triggers resume flow (US-006 scenario 3)

### Acceptance Criteria
- [ ] AC1: Session transitions to "idle" after SESSION_IDLE_TIMEOUT_SECONDS without activity
- [ ] AC2: Idle session subprocess is terminated but metadata preserved with is_resumable=True
- [ ] AC3: Active query resets the idle timer (session with in-flight query never goes idle)

---

## TASK-020: Implement Zustand stores (message, session, streaming)

### Task Description
Create three Zustand stores for the React frontend: useMessageStore (messages per session, streaming buffer), useSessionStore (session list, active session), and useStreamingStore (streaming state, connection status). These provide the state management layer for all UI components.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-002 - Streaming Chat Conversation, US-005 - Chat Input and Controls
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 3 (US-001) - frontend track

### Dependencies
- **Blocked By**: TASK-002
- **Blocks**: TASK-022, TASK-023, TASK-024, TASK-025

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (Zustand stores), Frontend types from Section 4.2-4.3
- **Type**: Component Spec

### Task Steps
1. Create stores/messageStore.ts with messages-per-session map, append/finalize actions
2. Create stores/sessionStore.ts with session list, activeSessionId, create/switch/destroy actions
3. Create stores/streamingStore.ts with isStreaming, connectionStatus, pendingInterrupt flags
4. Ensure selector patterns for efficient re-renders (no full-store subscriptions)
5. Add streaming buffer: append delta tokens, finalize on response_complete

### Acceptance Criteria
- [ ] AC1: messageStore appends stream_delta tokens to active message and finalizes on response_complete
- [ ] AC2: sessionStore tracks active session and switches without losing message history for other sessions
- [ ] AC3: streamingStore.isStreaming is true during active query, false after response_complete or interrupt

---

## TASK-021: Implement WebSocket hook (useWebSocket)

### Task Description
Create the useWebSocket React hook that manages the WebSocket connection lifecycle: connect with API key, handle reconnection, dispatch incoming messages to appropriate Zustand stores, and provide send functions for client messages.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-002 - Streaming Chat Conversation, US-001 - Pre-Warmed Session Start
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 3 (US-001) - frontend track

### Dependencies
- **Blocked By**: TASK-002, TASK-020
- **Blocks**: TASK-022, TASK-023, TASK-024

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (WebSocket Client), Implementation Plan Section 4.2 (Message Contracts)
- **Type**: Component Spec

### Task Steps
1. Create hooks/useWebSocket.ts with connection management
2. Connect to /ws/v1/chat with API key in header/query param
3. Parse incoming messages by type, dispatch to correct Zustand store
4. Provide sendMessage(text, sessionId), sendInterrupt(sessionId), sendCreateSession(), sendSwitchSession(sessionId) functions
5. Handle connection errors and basic reconnection (reconnect after 3s on disconnect)

### Acceptance Criteria
- [ ] AC1: WebSocket connects to /ws/v1/chat and receives session_list on connection
- [ ] AC2: Incoming stream_delta messages dispatch to messageStore and update streaming buffer
- [ ] AC3: sendMessage sends properly formatted user_message with session_id and seq
- [ ] AC4: Connection drop triggers automatic reconnection attempt after 3 seconds

---

## TASK-022: Implement ChatLayout, Sidebar, and SessionList components

### Task Description
Create the main layout structure: ChatLayout (sidebar + chat panel), Sidebar container, and SessionList component. SessionList displays all sessions with last-active timestamp and message count. Supports creating new sessions and switching between them.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-001 - Pre-Warmed Session Start (session creation from UI)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 3 (US-001) - frontend track

### Dependencies
- **Blocked By**: TASK-020, TASK-021
- **Blocks**: TASK-027

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (Component tree), Section 4.3 (SessionSummary)
- **Type**: Component Spec

### Task Steps
1. Create components/ChatLayout.tsx with sidebar + chat panel layout
2. Create components/Sidebar.tsx containing SessionList
3. Create components/SessionList.tsx displaying sessions from sessionStore
4. Create components/SessionItem.tsx showing session name, last-active, message count
5. Wire "New Session" button to sendCreateSession() and session click to sendSwitchSession()

### Acceptance Criteria
- [ ] AC1: SessionList renders all sessions from sessionStore with status, last_active_at, message_count
- [ ] AC2: Clicking a session switches active session and loads its message history
- [ ] AC3: "New Session" button triggers create_session WebSocket message and shows session_creating state

---

## TASK-023: Implement MessageList and message components

### Task Description
Create the MessageList container with UserMessage, AssistantMessage, and ToolUseCard child components. MessageList auto-scrolls on new messages. AssistantMessage supports streaming token display with typing indicator. ToolUseCard shows tool execution status.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-002 - Streaming Chat Conversation, US-003 - Tool Use Transparency
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 4 (US-002/US-003) - frontend track

### Dependencies
- **Blocked By**: TASK-020, TASK-021
- **Blocks**: TASK-027

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (MessageList, AssistantMessage, ToolUseCard), Section 4.2 (stream_delta, tool_use, tool_result)
- **Type**: Component Spec

### Task Steps
1. Create components/MessageList.tsx with auto-scroll behavior
2. Create components/UserMessage.tsx for user message bubbles
3. Create components/AssistantMessage.tsx with streaming token display and typing indicator (animated cursor)
4. Create components/ToolUseCard.tsx with tool name, status (executing/complete/error), collapse/expand
5. Wire to messageStore: subscribe to messages for active session, render in order

### Acceptance Criteria
- [ ] AC1: Stream delta tokens render progressively in AssistantMessage with visible typing indicator
- [ ] AC2: ToolUseCard shows "Executing..." during tool_use, updates to "Complete (X.Xs)" on tool_result
- [ ] AC3: Tool error shows "Error" status in red with error reason from tool_result
- [ ] AC4: MessageList auto-scrolls to bottom when new messages arrive

---

## TASK-024: Implement InputBar with keyboard shortcuts

### Task Description
Create the InputBar component with textarea, send button, and keyboard shortcuts. Enter sends message, Ctrl+Shift+X interrupts current stream. Input bar is disabled during query processing and re-enabled on response_complete.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-005 - Chat Input and Controls
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 4 (US-005) - frontend track

### Dependencies
- **Blocked By**: TASK-020, TASK-021
- **Blocks**: TASK-027

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (InputBar), User Stories US-005
- **Type**: Component Spec

### Task Steps
1. Create components/InputBar.tsx with textarea and send button
2. Implement Enter key handler: validate non-empty, call sendMessage()
3. Implement Ctrl+Shift+X handler: call sendInterrupt() during active stream
4. Disable send during active query; re-enable on response_complete or stream_interrupted
5. Client-side validation: reject empty messages, enforce 32k char limit

### Acceptance Criteria
- [ ] AC1: Enter key sends message via WebSocket and clears input; message appears in MessageList
- [ ] AC2: Ctrl+Shift+X sends interrupt command during streaming; "[Response interrupted]" shown in message
- [ ] AC3: Empty message (after trim) is not sent; no WebSocket message dispatched
- [ ] AC4: Input bar remains responsive during streaming (not blocked, text can be typed)

---

## TASK-025: Implement StatusBar and AuthGate components

### Task Description
Create StatusBar showing connection status, active session info, and cost. Create AuthGate component that prompts for API key on first visit and validates before allowing access to chat.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-002 - Streaming Chat (cost display), US-001 (auth gate)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 4 (US-002) - frontend track

### Dependencies
- **Blocked By**: TASK-020, TASK-021
- **Blocks**: TASK-027

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (StatusBar, AuthGate)
- **Type**: Component Spec

### Task Steps
1. Create components/StatusBar.tsx showing connection status (connected/disconnected/reconnecting)
2. Display active session info: session_id, message_count
3. Display cost from response_complete messages
4. Create components/AuthGate.tsx with API key input form
5. Store API key in localStorage; use for WebSocket connection

### Acceptance Criteria
- [ ] AC1: StatusBar shows "Connected" when WebSocket is open, "Reconnecting..." on disconnect
- [ ] AC2: Cost information from response_complete is displayed in StatusBar
- [ ] AC3: AuthGate blocks access until valid API key is provided; invalid key shows error message

---

## TASK-026: Implement ErrorMessage and SystemMessage components

### Task Description
Create ErrorMessage component for actionable error display (with retry button) and SystemMessage component for session warnings and termination notices. These provide the UI layer for US-007 error messages.

### Task Priority
**Priority**: P1 (High)

### Story Reference
- **User Story**: US-007 - Error Messages with Context
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 6 (US-007) - frontend track

### Dependencies
- **Blocked By**: TASK-020
- **Blocks**: TASK-027

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (ErrorMessage, SystemMessage), Section 4.2 (error, session_warning, session_terminated)
- **Type**: Component Spec

### Task Steps
1. Create components/ErrorMessage.tsx with error text and retry button
2. Create components/SystemMessage.tsx for session_warning and session_terminated messages
3. ErrorMessage: parse suggested_action from stream_error; show "Retry" button if action="retry"
4. SystemMessage: show warning banner for session_warning; termination dialog for session_terminated with resume link
5. Wire to messageStore: render in message flow at correct position

### Acceptance Criteria
- [ ] AC1: stream_error with suggested_action="retry" shows error message with clickable Retry button
- [ ] AC2: session_warning renders as a warning banner with remaining time
- [ ] AC3: session_terminated renders with termination reason and "Start New Session" / "Resume" links

---

## TASK-027: Implement App.tsx and full frontend integration

### Task Description
Create the top-level App.tsx that composes all components: AuthGate wrapping ChatLayout, which contains Sidebar (SessionList) and ChatPanel (MessageList + InputBar + StatusBar). Ensure all WebSocket events flow correctly through stores to components.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001, US-002, US-003, US-005 (all frontend stories converge here)
- **Acceptance Criteria**: AC1, AC2, AC3
- **Phase**: Phase 4 (US-002) - frontend integration

### Dependencies
- **Blocked By**: TASK-022, TASK-023, TASK-024, TASK-025, TASK-026
- **Blocks**: TASK-028

### Integration Contract Reference
- **Contract**: Architecture Section 6.7 (Component tree), Section 7 (Frontend structure)
- **Type**: Component Spec

### Task Steps
1. Create App.tsx composing AuthGate -> ChatLayout -> [Sidebar, ChatPanel]
2. ChatPanel contains MessageList + InputBar + StatusBar
3. Ensure Zustand stores properly hydrate from WebSocket session_list on connection
4. Test full flow: auth -> connect -> create session -> send message -> see streaming response
5. Add responsive layout (min 360px width per FR-008)

### Acceptance Criteria
- [ ] AC1: Full user journey works: enter API key -> see session list -> create session -> chat
- [ ] AC2: Switching sessions preserves message history for each session independently
- [ ] AC3: Layout is responsive down to 360px width without horizontal scrolling

---

## TASK-028: End-to-end integration tests

### Task Description
Write integration tests that validate the full backend flow: WebSocket connection, session creation from pool, streaming chat, tool use transparency, interrupt, session termination, and health endpoints. Use real aiosqlite and httpx async test client.

### Task Priority
**Priority**: P0 (Critical)

### Story Reference
- **User Story**: US-001, US-002, US-003, US-004, US-005 (all stories validated)
- **Acceptance Criteria**: AC1, AC2, AC3, AC4
- **Phase**: Phase 7 (Polish)

### Dependencies
- **Blocked By**: TASK-015
- **Blocks**: None

### Integration Contract Reference
- **Contract**: All contracts from Implementation Plan Section 4
- **Type**: Integration Test

### Task Steps
1. Create tests/integration/test_websocket_flow.py: connect, auth, send message, receive stream
2. Create tests/integration/test_session_lifecycle.py: create, list, query, interrupt, destroy, resume
3. Create tests/integration/test_extension_loading.py: mcp.json parsing, skills discovery, missing files
4. Create tests/integration/test_health_endpoints.py: /live, /ready responses under various states
5. All tests use real aiosqlite database (tmpdir), httpx async client for REST, websocket test client for WS

### Acceptance Criteria
- [ ] AC1: WebSocket flow test: connect -> auth -> create_session -> user_message -> stream_delta -> response_complete
- [ ] AC2: Session lifecycle test: create -> list (appears) -> destroy -> list (gone)
- [ ] AC3: Extension loading test: valid mcp.json loaded; invalid mcp.json skipped with log warning
- [ ] AC4: Health endpoint test: /live returns 200; /ready returns 503 when pool empty

---

## Contract Coverage Matrix

| Contract Type | Section | Tasks Covering |
|--------------|---------|----------------|
| API Endpoints | 4.1 | TASK-014 (REST), TASK-005 (auth) |
| WebSocket Messages (Client->Server) | 4.2 | TASK-009, TASK-013 |
| WebSocket Messages (Server->Client) | 4.2 | TASK-009, TASK-013 |
| Frontend-Backend Data Contracts | 4.3 | TASK-003, TASK-002 (types) |
| User Input Validation | 4.4 | TASK-003, TASK-024 |
| SessionMetadata Schema | 5.1 | TASK-004 |
| SessionState Model | 5.2 | TASK-003 |
| ExtensionConfig Model | 5.3 | TASK-003, TASK-006 |
| MCPServerConfig Model | 5.4 | TASK-003, TASK-006 |

## User Story Coverage Matrix

| User Story | Priority | Acceptance Scenarios | Tasks Covering | Tests Covering | Phase | Checkpoint |
|------------|----------|---------------------|----------------|----------------|-------|------------|
| US-001 | P1 | 4 scenarios | TASK-006,007,010,013,014,015,022 | TASK-028 (integration) | Phase 3 | Yes |
| US-002 | P1 | 4 scenarios | TASK-009,010,013,020,021,023 | TASK-028 (integration) | Phase 4 | Yes |
| US-003 | P1 | 4 scenarios | TASK-023 | TASK-028 (integration) | Phase 4 | Yes |
| US-004 | P1 | 5 scenarios | TASK-008,011 | TASK-028 (integration) | Phase 4 | Yes |
| US-005 | P1 | 4 scenarios | TASK-024 | TASK-028 (integration) | Phase 4 | Yes |
| US-006 | P2 | 4 scenarios | TASK-004,012,019 | TASK-028 (integration) | Phase 5 | Yes |
| US-007 | P2 | 4 scenarios | TASK-018,026 | TASK-028 (integration) | Phase 6 | Yes |

---

*End of Task Breakdown*
