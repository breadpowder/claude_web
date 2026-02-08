# Task Groups: core-engine (Phase 1 MVP)

**Total Tasks**: 28
**Total Phases**: 8
**Organization**: By User Story (story-phase pattern)

---

## Phase 1: Setup
**Purpose**: Project initialization and shared configuration
**Tasks**: 2
**Dependencies**: None (start here)

| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-001 | Initialize Python project with uv and pyproject.toml | P0 | [P] |
| TASK-002 | Initialize Vite + React 19 frontend scaffold | P0 | [P] |

**Note**: TASK-001 and TASK-002 can run in parallel (backend and frontend are independent).

---

## Phase 2: Foundational (BLOCKS all story phases)
**Purpose**: Core infrastructure that MUST complete before ANY user story
**Tasks**: 5
**Dependencies**: Phase 1

| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-003 | Implement configuration module and Pydantic data models | P0 | - |
| TASK-004 | Implement SQLite schema and SessionRepository | P0 | [P] after TASK-003 |
| TASK-005 | Implement API key authentication middleware | P0 | [P] after TASK-003 |
| TASK-009 | Implement WebSocket message type definitions | P1 | [P] after TASK-003 |
| TASK-016 | Implement structlog JSON logging | P1 | [P] after TASK-003 |

**Note**: TASK-003 must complete first. Then TASK-004, TASK-005, TASK-009, TASK-016 can run in parallel.

**Checkpoint**: Foundation ready -- all models defined, DB operational, auth working, message types defined, logging configured.

---

## Phase 3: US-001 - Pre-Warmed Session Start (P1) -- MVP
**Goal**: User opens browser and gets a ready session within 3 seconds. Backend serves the full application.
**Independent Test**: Start platform with pool=1. Open browser. Verify "Ready" in < 3s.
**User Story Reference**: specs/user-stories.md US-001
**Acceptance Scenarios**:
1. Given pool filled, When user opens chat, Then "Ready" in < 3s
2. Given pool empty, When user opens chat, Then "Preparing..." with progress indicator
3. Given session assigned, When pool detects empty slot, Then replenish in background
4. Given all pre-warms fail, When startup, Then readiness probe 503

### Backend Implementation
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-006 | Implement ExtensionLoader | P0 | [P] |
| TASK-007 | Implement PreWarmPool | P0 | [P] (after TASK-006 available) |
| TASK-010 | Implement SessionManager | P0 | - (depends on TASK-006, 007, 004, 008) |
| TASK-013 | Implement WebSocket handler | P0 | - (depends on TASK-010, 005, 009) |
| TASK-014 | Implement REST API endpoints | P1 | [P] (after TASK-010, 005) |
| TASK-015 | Implement FastAPI application entry point | P0 | - (depends on TASK-010, 013, 014) |

### Frontend Implementation (parallel track)
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-020 | Implement Zustand stores | P0 | - (depends on TASK-002) |
| TASK-021 | Implement WebSocket hook | P0 | - (depends on TASK-020) |
| TASK-022 | Implement ChatLayout, Sidebar, SessionList | P1 | - (depends on TASK-020, 021) |

**Checkpoint**: US-001 is independently functional and testable. Backend serves API and WebSocket. Frontend connects and creates sessions.

---

## Phase 4: US-002/US-003/US-005 - Streaming Chat + Tool Transparency + Input Controls (P1)
**Goal**: Full chat experience with streaming tokens, tool use cards, and keyboard shortcuts.
**Independent Test**: Send message, verify streaming tokens, trigger tool use, press Ctrl+Shift+X to interrupt.
**User Story Reference**: specs/user-stories.md US-002, US-003, US-005
**Acceptance Scenarios (US-002)**:
1. Given active session, When user sends message, Then streaming begins in < 2s
2. Given streaming, When user observes, Then typing indicator visible, tokens appended
3. Given response complete, When ResultMessage received, Then cost shown, input re-enabled
4. Given error mid-stream, Then partial preserved, "retry" suggested
**Acceptance Scenarios (US-003)**:
1. Given tool invoked, Then ToolUseCard with name and "Executing..."
2. Given tool completes, Then "Complete (X.Xs)" with result
3. Given tool fails, Then "Error" in red with reason
**Acceptance Scenarios (US-005)**:
1. Given input focused, When Enter, Then message sent
2. Given streaming, When Ctrl+Shift+X, Then interrupted
3. Given empty input, When Enter, Then nothing sent
4. Given query in flight, When typing, Then input responsive

### Frontend Implementation
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-023 | Implement MessageList and message components | P0 | [P] |
| TASK-024 | Implement InputBar with keyboard shortcuts | P0 | [P] |
| TASK-025 | Implement StatusBar and AuthGate | P1 | [P] |

**Note**: TASK-023, TASK-024, TASK-025 can run in parallel (independent UI components).

**Checkpoint**: US-002, US-003, US-005 independently functional. Full chat with streaming, tools, and controls.

---

## Phase 5: US-004 - Session Memory Limits (P1)
**Goal**: Sessions auto-terminate on memory/duration limits. Zombie processes cleaned.
**Independent Test**: Set low RSS threshold, monitor session, verify warning and termination.
**User Story Reference**: specs/user-stories.md US-004
**Acceptance Scenarios**:
1. Given session at 90% duration, Then warning sent
2. Given session at 100% duration, no query, Then terminated
3. Given session at 100% duration, query active, Then wait 30s grace then terminate
4. Given RSS > threshold, Then graceful restart with resume
5. Given zombie process, Then detected and reaped

### Backend Implementation
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-008 | Implement SubprocessMonitor | P0 | - |
| TASK-011 | Implement SessionManager monitor integration | P0 | - (depends on TASK-008, 010) |

**Checkpoint**: US-004 independently functional. Sessions monitored, limits enforced, zombies cleaned.

---

## Phase 6: US-006 - Session Resume (P2)
**Goal**: Users can close browser and return to find conversation intact.
**Independent Test**: Create session, send messages, close browser, reopen, verify messages displayed.
**User Story Reference**: specs/user-stories.md US-006
**Acceptance Scenarios**:
1. Given active session, When browser closed, Then session stays "idle" for 30 min
2. Given return within 30 min, Then session resumed automatically
3. Given return after 30 min, Then new session with resume=old_id
4. Given corrupted SDK data, Then fresh session with notification

### Implementation
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-012 | Implement session resume capability | P1 | - (depends on TASK-010) |
| TASK-019 | Implement idle session timeout | P1 | [P] (depends on TASK-010) |

**Checkpoint**: US-006 independently functional. Sessions persist and resume correctly.

---

## Phase 7: US-007 - Error Messages with Context (P2)
**Goal**: All errors provide actionable messages instead of raw SDK errors.
**Independent Test**: Trigger API timeout, rate limit, tool failure. Verify user-friendly messages.
**User Story Reference**: specs/user-stories.md US-007
**Acceptance Scenarios**:
1. Given API 429, Then "AI service temporarily busy, retrying..."
2. Given tool failure, Then ToolUseCard shows error, Claude explains
3. Given session terminated (memory), Then "Restarted for performance, conversation preserved"

### Implementation
| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-018 | Implement error message translation layer | P1 | - (depends on TASK-003, 009) |
| TASK-026 | Implement ErrorMessage and SystemMessage components | P1 | - (depends on TASK-020) |

**Checkpoint**: US-007 independently functional. All errors are user-friendly and actionable.

---

## Phase 8: Polish & Integration
**Purpose**: Full integration, Docker deployment, end-to-end testing
**Tasks**: 3
**Dependencies**: All desired story phases complete

| Task ID | Title | Priority | Parallel? |
|---------|-------|----------|-----------|
| TASK-027 | Implement App.tsx and full frontend integration | P0 | - |
| TASK-028 | End-to-end integration tests | P0 | - (depends on TASK-015) |
| TASK-017 | Implement Dockerfile and Docker build | P1 | [P] (after TASK-015) |

**Checkpoint**: Full platform functional. Docker image builds. Integration tests pass.

---

## Phase Dependencies

```
Phase 1: Setup (TASK-001 || TASK-002)
    |
    v
Phase 2: Foundational (TASK-003 -> [TASK-004 || TASK-005 || TASK-009 || TASK-016])
    |
    +-----> Phase 3: US-001 (Backend: TASK-006,007,010,013,014,015 | Frontend: TASK-020,021,022)
    |           |
    |           +-----> Phase 4: US-002/003/005 (Frontend: TASK-023 || TASK-024 || TASK-025)
    |           |
    |           +-----> Phase 5: US-004 (TASK-008 -> TASK-011)
    |           |
    |           +-----> Phase 6: US-006 (TASK-012 || TASK-019)
    |           |
    |           +-----> Phase 7: US-007 (TASK-018 || TASK-026)
    |           |
    |           +-----> Phase 8: Polish (TASK-027 -> TASK-028 || TASK-017)
```

**Notes**:
- Phase 1 tasks run in parallel (backend/frontend independent)
- Phase 3 has two parallel tracks: backend and frontend
- Phases 4, 5, 6, 7 can run in parallel after Phase 3
- Phase 8 depends on all desired story phases

## Implementation Strategy

### MVP First (US-001 Only)
1. Complete Setup + Foundational -> Foundation ready
2. Complete US-001 (Phase 3) -> Backend API + Frontend shell -> Test independently -> MVP!
3. **STOP and VALIDATE** before proceeding

### Incremental Delivery
1. Add US-002/003/005 (Phase 4) -> Full chat experience -> Validate
2. Add US-004 (Phase 5) -> Session monitoring -> Validate
3. Add US-006 (Phase 6) -> Resume capability -> Validate
4. Add US-007 (Phase 7) -> Error polishing -> Validate
5. Polish (Phase 8) -> Docker + Integration tests -> Ship

### Subagent Allocation (for implementation phase)
- **Subagent 1**: Phase 1 + Phase 2 (Setup + Foundational)
- **Subagent 2**: Phase 3 Backend (TASK-006, 007, 010, 013, 014, 015)
- **Subagent 3**: Phase 3 Frontend + Phase 4 (TASK-020-025)
- **Subagent 4**: Phase 5 (TASK-008, 011)
- **Subagent 5**: Phase 6 + 7 (TASK-012, 019, 018, 026)
- **Subagent 6**: Phase 8 (TASK-027, 028, 017)

---

*End of Task Groups*
