# Decision Log: Core Engine MVP

> **Feature**: core-engine
> **Date**: 2026-02-14
> **Authority**: ADR-001 (Platform Strategy), ADR-002 (Technical Architecture)

---

## Decision 1: AG-UI Server Implementation Strategy

**Date**: 2026-02-14
**Status**: Approved

### Context

ADR-002 Decision 3 mandates AG-UI protocol for frontend communication. The AG-UI Python server SDK exists (`ag-ui-protocol` package with `ag_ui.core` for event types and `ag_ui.encoder` for SSE encoding). The question is whether to use the SDK or implement the event stream directly on FastAPI.

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| A: Use ag-ui-protocol Python SDK | Standard event types and encoder; less custom code; protocol-compliant event names | Additional dependency; SDK maturity unknown; may not cover custom events | Medium |
| B: Implement AG-UI events directly on FastAPI | Full control; no dependency risk; can add custom events freely; thin protocol (JSON over SSE) | Must maintain event type definitions ourselves; risk of protocol drift | Low |
| C: Hybrid -- use ag_ui.core for types, custom SSE encoder | Standard types from SDK; custom streaming logic for FastAPI integration; best of both | Two codebases to maintain (types from SDK, streaming from us) | Low |

### Selected Option

**Option C: Hybrid approach**

### Rationale

- AG-UI event types (`RunStartedEvent`, `TextMessageContentEvent`, `ToolCallStartEvent`, etc.) from `ag_ui.core` ensure protocol compliance
- The `EventEncoder` from `ag_ui.encoder` handles SSE formatting correctly
- Custom events for platform-specific notifications (session_warning, session_terminated, session_restarting) are supported by AG-UI's custom event mechanism
- ADR-002 Decision 3 trade-off explicitly states: "Event stream can be implemented directly on FastAPI; protocol is lightweight JSON events over HTTP"
- FastAPI's `StreamingResponse` with async generators is the natural fit

### Edge Case Implications

| Edge Case | How This Handles It |
|-----------|-------------------|
| EC-NEW-002: Stream interrupted | HTTP-based; client re-establishes connection and retries |
| EC-NEW-003: Large tool result | Truncate in AG-UI event; full result via REST fallback |
| EC-NEW-004: Concurrent runs | Backend rejects with AG-UI error event (one run per session) |
| EC-NEW-005: Cancel race condition | Idempotent cancel; completed runs ignored |
| EC-NEW-006: Custom events | AG-UI supports custom event types by design |

### Strategic Assessment

- **Solves current problem**: YES -- AG-UI event streaming to frontend
- **Handles edge cases**: YES -- all 5 AG-UI edge cases covered
- **Supports future growth**: YES -- custom events extensible for Phase 2+ features
- **Extensibility score**: 9/10

---

## Decision 2: OpenAI-Compliant API Translation Layer

**Date**: 2026-02-14
**Status**: Approved

### Context

ADR-002 Decision 3 mandates an OpenAI-compliant streaming API for server-to-server agentic calls. The platform must translate between Claude SDK stream events and OpenAI SSE format (`choices[].delta.content`, `tool_calls`, `finish_reason`, `usage`).

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| A: Custom translation layer on FastAPI | Full control; no dependency; matches exact OpenAI format | Must maintain format compliance manually; risk of format drift | Low |
| B: Use sse-starlette library for SSE transport | Battle-tested SSE implementation; handles connection management | Only provides transport, not format translation | Low |
| C: Reference claude-code-openai-wrapper patterns | Proven message_adapter.py and SSE patterns; same SDK | No license (cannot use code); patterns only as reference | Low |

### Selected Option

**Option A + B: Custom translation with sse-starlette transport**

### Rationale

- sse-starlette (MIT) provides reliable SSE transport on FastAPI
- Custom adapter translates SDK events to OpenAI format (message_adapter pattern from wrapper reference)
- OpenAI format is stable and well-documented (A-008 confirmed)
- Unsupported parameters silently ignored for maximum compatibility (EC-NEW-008)

### Edge Case Implications

| Edge Case | How This Handles It |
|-----------|-------------------|
| EC-NEW-007: No session available | 503 with Retry-After header, OpenAI error format |
| EC-NEW-008: Unsupported parameters | Ignore silently, log warning |
| EC-NEW-009: Session terminated mid-stream | SSE error event + [DONE] sentinel |

### Strategic Assessment

- **Solves current problem**: YES -- any OpenAI-compatible client can call the platform
- **Handles edge cases**: YES -- all 3 OpenAI API edge cases covered
- **Supports future growth**: YES -- version endpoint for format evolution
- **Extensibility score**: 8/10

---

## Decision 3: Session State Management Architecture

**Date**: 2026-02-14
**Status**: Approved

### Context

The platform must manage multiple concurrent SDK sessions (up to 10), each backed by a CLI subprocess. Session metadata must persist in JSON files (ADR-002 Decision 5). The pre-warming pool must use asyncio.Queue (ADR-002 Decision 4).

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| A: Single SessionManager class with internal state | Simple; one place for all session logic; easy to test | Large class; mixing concerns (pool, monitoring, index, lifecycle) | Medium |
| B: Decomposed into SessionManager + PreWarmPool + SubprocessMonitor + JSONSessionIndex | Clean separation of concerns; each component independently testable; matches spec entities | More files; inter-component coordination required | Low |
| C: Actor model (one actor per session) | True isolation; natural for subprocess model | Complex; Python asyncio actors are not standard; overkill for 10 sessions | High |

### Selected Option

**Option B: Decomposed architecture**

### Rationale

- SessionManager orchestrates, delegates to specialized components
- PreWarmPool manages asyncio.Queue of pre-initialized ClaudeSDKClient instances
- SubprocessMonitor handles RSS tracking, duration limits, zombie cleanup (matches US-004 control flow entities)
- JSONSessionIndex handles atomic file I/O with locking (matches Decision 5)
- Each component maps cleanly to spec entities and edge cases
- Testing is straightforward: mock dependencies, test each component independently

### Edge Case Implications

| Edge Case | Component | How Handled |
|-----------|-----------|-------------|
| EC-001: Pool empty | PreWarmPool | Returns None; SessionManager falls back to cold start |
| EC-003: Duration limit mid-query | SubprocessMonitor | 30s grace period; interrupt if exceeded |
| EC-004: RSS exceeds threshold | SubprocessMonitor | Flag for graceful restart after query completes |
| EC-007: Corrupted resume data | SessionManager | try/except on resume; fall back to fresh session |
| EC-NEW-001: First startup | JSONSessionIndex | Create directory and initial empty JSON file |
| EC-NEW-010: Concurrent writes | JSONSessionIndex | File locking via filelock library |
| EC-NEW-011: Corrupted index | JSONSessionIndex | Recover from .bak file or re-create empty |

### Strategic Assessment

- **Solves current problem**: YES -- manages 10 concurrent sessions with monitoring
- **Handles edge cases**: YES -- all 10 session lifecycle edge cases covered
- **Supports future growth**: YES -- components replaceable (e.g., JSONSessionIndex -> SQLite in Phase 2)
- **Extensibility score**: 9/10

---

## Decision 4: Frontend Architecture (React + Zustand + AG-UI Client)

**Date**: 2026-02-14
**Status**: Approved

### Context

ADR-002 Decision 7 mandates Zustand with slice pattern. Decision 3 mandates AG-UI protocol for frontend communication. Phase 1 renders full messages (not token-by-token streaming).

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| A: Custom AG-UI client + Zustand stores | Full control; no framework lock-in; matches our exact event handling needs | Must implement SSE parsing and event dispatch | Low |
| B: Use @ag-ui/client library + Zustand | Standard client; handles SSE parsing; typed events | Additional dependency; may not integrate cleanly with Zustand | Medium |
| C: Use CopilotKit (AG-UI reference implementation) | Full AG-UI frontend; React hooks for events | Heavy dependency; opinionated UI; may conflict with our custom components | High |

### Selected Option

**Option A: Custom AG-UI client + Zustand stores**

### Rationale

- AG-UI is lightweight JSON over SSE; parsing is trivial (EventSource API or fetch + ReadableStream)
- Zustand stores map naturally to AG-UI event categories: chatStore (messages), sessionStore (lifecycle), toolStore (tool calls)
- Custom components (MessageList, InputBar, ToolUseCard) required anyway per FR-008
- Full message rendering (not streaming) simplifies state management -- buffer events, render on text_message_end
- Phase 2 can adopt @ag-ui/client if needed without architectural changes

### Strategic Assessment

- **Solves current problem**: YES -- React UI with AG-UI event handling
- **Handles edge cases**: YES -- custom event handling for platform-specific events
- **Supports future growth**: PARTIAL -- may need to add token streaming in Phase 1.1 if A-010 is invalidated
- **Extensibility score**: 8/10

---

## Decision 5: Extension Discovery Strategy

**Date**: 2026-02-14
**Status**: Approved

### Context

ADR-002 Decision 6 mandates a lightweight ExtensionLoader that scans the filesystem for mcp.json, ./skills/, and ./commands/. No plugin runtime, no lifecycle management.

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| A: Scan once on startup only | Simplest; no file watching; predictable | Changes require full restart | Low |
| B: Scan on startup + re-scan on new session creation (hot-detection) | Changes picked up by new sessions; no restart for new extensions; matches FR-011c | Slightly more I/O per session creation; filesystem read on each session | Low |
| C: Filesystem watcher (watchdog) | Real-time detection; no restart needed | Complex; race conditions; Phase 2 feature per ADR-002 Decision 6 trade-off | Medium |

### Selected Option

**Option B: Scan on startup + re-scan on new session creation**

### Rationale

- FR-011c specifies "re-scanned when new session created" for hot-detection
- ADR-002 Decision 6 defers filesystem watching to Phase 2
- Filesystem reads are cheap (< 1ms for directory listing + JSON parse)
- Active sessions are unaffected by filesystem changes (already loaded)
- New sessions get current state of extensions

### Edge Case Implications

| Edge Case | How Handled |
|-----------|-------------|
| EC-NEW-013: mcp.json deleted while running | New sessions start without MCP; active sessions unaffected |
| EC-NEW-014: MCP server binary not found | SDK reports error; session starts but that server unavailable |
| EC-NEW-015: Malformed SKILL.md | SDK ignores; logged with file path |
| EC-116: Env var injection | Sanitize; blocklist dangerous vars |

### Strategic Assessment

- **Solves current problem**: YES -- extensions discovered and passed to SDK
- **Handles edge cases**: YES -- all 5 extension edge cases covered
- **Supports future growth**: YES -- can add filesystem watcher in Phase 2 without changing interface
- **Extensibility score**: 8/10

---

## Decision Traceability Matrix

| Tech Decision | User Stories Affected | Edge Cases Handled | ADR Decisions |
|--------------|----------------------|-------------------|---------------|
| AG-UI hybrid (D1) | US-002, US-003, US-005, US-007, US-011 | EC-NEW-002 to EC-NEW-006 | D3 |
| OpenAI API translation (D2) | US-008 | EC-NEW-007 to EC-NEW-009 | D3 |
| Session decomposition (D3) | US-001, US-004, US-006, US-009 | EC-001, EC-003, EC-004, EC-007, EC-NEW-001, EC-NEW-010 to EC-NEW-012 | D4, D5, D10 |
| Frontend architecture (D4) | US-002, US-003, US-005 | EC-NEW-004, EC-NEW-005 | D3, D7 |
| Extension discovery (D5) | US-010 | EC-NEW-013 to EC-NEW-015, EC-116 | D6 |

---

*End of Decision Log*
