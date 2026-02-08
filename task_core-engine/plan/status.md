# Planning Status Log: core-engine

> **Feature**: claude_sdk_pattern Core Engine (Phase 1 MVP)
> **Date Started**: 2026-02-07
> **Status**: Architecture Complete - Pending Review

---

## Step 1: Requirements Analysis

**Completed**: 2026-02-07

### Input Documents Reviewed
- `specs/feature-spec.md` - 13 Phase 1 FRs (FR-001 through FR-013a), 15 NFRs, 10 constraints, 10 guardrails
- `specs/user-stories.md` - 16 user stories across 4 epics, 7 in Phase 1 scope (US-001 through US-007)
- `specs/business-case.md` - ROI ~13 months, target 5-50 person self-hosted teams
- `specs/edge-case-resolutions.md` - 38 HIGH risk edge cases, 37 resolved, 1 pending (EC-075)
- `specs/control-flows/` - 4 control flow diagrams (US-001, US-002, US-004, US-008)
- `requirement/team_findings/technical_feasibility.md` - SDK readiness MEDIUM-HIGH, 8 component gap analysis
- `requirement/team_findings/open_source_research.md` - 6 platforms analyzed, 12 component library recommendations
- `requirement/team_findings/edge_case_matrix.md` - 141 edge cases across 7 components
- `requirement/team_findings/devils_advocate.md` - 13 challenges, all addressed in PRD scope decisions

### Key Findings
1. **Phase 1 scope is well-bounded**: Single-user, API key auth, SQLite, file-based extensions only (mcp.json, skills, commands). No plugin registry, no RBAC, no cost tracking.
2. **Pre-warming pool is mandatory**: 20-30s cold start is a proven UX blocker. Devil's Advocate challenged this, but PRD explicitly requires it (FR-001, NFR-001).
3. **WebSocket over SSE**: PRD chose WebSocket for bidirectional interrupt support (Ctrl+Shift+X). SSE would require separate REST endpoint for user-to-server messages.
4. **Extensions use Claude Code mechanism**: mcp.json, ./skills/, ./commands/ are loaded via ClaudeAgentOptions.mcp_servers and setting_sources. No custom abstraction layer.
5. **Multiple concurrent sessions**: User can create, switch between, and manage parallel conversations.
6. **Memory constraint is the primary operational risk**: ~500MB-1GB baseline (per GitHub issue evidence), grows to 24GB+ over extended sessions (#4953, OPEN). 4GB RSS threshold triggers graceful restart.

### Boundary Decisions (What is OUT for Phase 1)
- No PluginRegistry (formal manifest-based system deferred to Phase 2)
- No OptionsBuilder merging (lightweight: read mcp.json + scan skills/commands, build ClaudeAgentOptions directly)
- No PermissionGate/RBAC (API key auth = full access)
- No cost tracking/caps (monitor via API dashboard)
- No circuit breaker (basic error handling only)
- No Prometheus metrics (structlog for observability)
- No WebSocket reconnection sync with message replay (Phase 2)
- No Plugin UI slots

---

## Step 1.5: Constitution Check

**No `.sdlc/constitution.md` found in project root.**
**No `.sdlc/project-context.md` found in project root.**

WARNING: No project constitution found. Proceeding without constitution validation. Recommend running `sdlc-constitution` to create one after this planning phase.

Prior tech decisions from existing codebase (`claudesdk_integration.md`):
- Claude Agent SDK is the core framework
- Python async/await patterns established
- MCP integration patterns documented (stdio, HTTP, in-process)
- No conflicting tech decisions found

---

## Step 2: Gap Analysis

**Completed**: 2026-02-07

### Existing Codebase
- Repository is documentation-only (`claudesdk_integration.md`)
- No existing application code, tests, or infrastructure
- All components must be built from scratch

### Components to Build (Phase 1)

| Component | SDK Support | Custom Build Required | Complexity |
|-----------|-------------|----------------------|------------|
| SessionManager | Partial (ClaudeSDKClient lifecycle) | Session mapping, timeouts, multi-session, PID tracking | Medium-High |
| PreWarmPool | None | asyncio.Queue, background replenishment, pool health | Medium |
| WebSocketHandler | None | Bidirectional message translation, auth, interrupt | Medium |
| ExtensionLoader | Partial (SDK reads mcp.json, skills natively) | File scanning, config building, hot-detection on new session | Low-Medium |
| SubprocessMonitor | None | RSS monitoring via /proc, duration limits, zombie cleanup | Medium |
| React Chat UI | None | MessageList, InputBar, ToolUseCard, SessionList, Zustand store | Medium |
| API Key Auth | None | Middleware for REST + WebSocket auth validation | Low |
| Docker Container | None | Multi-stage build (Python backend + React frontend) | Low |

### Reusable from SDK
- ClaudeSDKClient: async context manager for subprocess lifecycle
- query() / receive_response(): streaming message iteration
- ClaudeAgentOptions: configuration passing (mcp_servers, setting_sources, allowed_tools)
- Session resume: `resume=<session_id>` parameter
- Built-in tools: Bash, Read, Write, Edit, Glob, Grep (no configuration needed)

---

## Step 3: Open Source Research Summary

**Completed**: 2026-02-07 (from requirement/team_findings/open_source_research.md)

### Phase 1 Dependencies (All license-verified)

| Need | Library | License | Rationale |
|------|---------|---------|-----------|
| Web framework | FastAPI + uvicorn | MIT / BSD-3 | Async-native, mature WebSocket support |
| WebSocket | Starlette (built-in) | BSD-3 | Zero additional dependencies |
| Session storage | aiosqlite | MIT | Embedded, no external deps for MVP |
| Logging | structlog | MIT/Apache 2.0 | Async-aware, correlation IDs |
| Frontend framework | React 19 + Vite | MIT | useTransition for streaming |
| State management | Zustand | MIT | Selector-based re-renders for streaming |
| UI primitives | Radix UI + Tailwind CSS | MIT | Accessible, unstyled components |
| Package manager | uv | MIT/Apache 2.0 | Fast Python packaging |
| Testing | pytest + httpx | MIT / BSD-3 | Async test support |

### Libraries Deferred to Phase 2+
- PyJWT (JWT auth), slowapi (rate limiting), aiobreaker (circuit breaker)
- cryptography/Fernet (secret encryption), pluggy (hook system)
- prometheus-fastapi-instrumentator (metrics)
- asyncpg (PostgreSQL migration)

---

## Step 4: Impact Assessment

**Completed**: 2026-02-07

### Performance Implications
- Pre-warm pool: ~500MB-1GB x pool_size baseline memory (~1-2GB for pool=2)
- Each active session: ~500MB-1GB baseline RSS, growing over time due to memory leak (#4953, OPEN)
- Max concurrent sessions on 16GB server: ~3-5 at startup, constrained to 2-3 sustained (due to memory growth)
- First response time: <3s (pre-warmed) vs 20-30s (cold start)

### Security Considerations
- API key must never appear in logs or error messages (G-009)
- SDK sandbox applies to Bash tool; other tools run in-process
- No plugin isolation in Phase 1 (acceptable: operator-controlled extensions)

### Backward Compatibility
- Greenfield project; no backward compatibility concerns
- mcp.json format matches Claude Code convention (forward-compatible)

### Risk Assessment

| Risk | Severity | Mitigation in Architecture |
|------|----------|---------------------------|
| SDK memory leak (OOM) | CRITICAL | RSS monitoring, 4h duration limit, graceful restart |
| 30s cold start | HIGH | Pre-warming pool (mandatory, size >= 1) |
| Zombie subprocesses | HIGH | PID tracking, SIGTERM/SIGKILL cleanup, periodic scan |
| SDK breaking changes | MEDIUM | Pin to ~0.1.30, test upgrades monthly |
| WebSocket reliability | MEDIUM | Basic reconnection; full sync deferred to Phase 2 |
| Anthropic launches hosted Claude Code | CRITICAL | Ship fast (4 weeks), differentiate on extension model |

---

## Step 5: Decisions Recorded

See `plan/decision-log.md` for full options analysis and rationale.

---

## Step 6: Architecture Documented

See `plan/strategy/architecture.md` for component diagrams and data flows.

---

## Step 7: Implementation Plan Created

See `plan/strategy/implementation_plan.md` for integration contracts and build order.

---

## Step 8: Task Breakdown (Phase 2)

**Completed**: 2026-02-07

### Activities
1. Read and analyzed all Phase 1 context: implementation_plan.md, architecture.md, decision-log.md, user-stories.md, feature-spec.md, edge-case-resolutions.md, control-flows/
2. Decomposed into 28 tasks following 2-hour rule, organized by user story phases
3. Mapped all integration contracts (API endpoints, WebSocket messages, data models) to specific tasks
4. Created TDD specifications with RED phase tests and assertion requirements for all tasks
5. Declared implementation strategy per task group with anti-pattern avoidance
6. Ran pre-implementation validation: coverage, assertion depth, anti-pattern signals

### Output Artifacts
- `plan/tasks/tasks.md` - 28 JIRA-format tasks with acceptance criteria
- `plan/tasks/tasks_details.md` - TDD specs, assertion requirements, implementation strategy
- `plan/tasks/task_groups.md` - 8 phases organized by user story

### Validation Results
- Spec-to-task coverage: 100% (all Phase 1 FRs and US covered)
- Assertion quality: All contract fields have explicit assertions
- Anti-pattern signals: None detected
- Strategy declarations: Complete for all 5 task groups
- Validation status: PASS

### Phase 1 User Stories Covered
| Story | Priority | Phase | Tasks | Checkpoint |
|-------|----------|-------|-------|------------|
| US-001 | P1 | Phase 3 | 9 tasks (backend+frontend) | Yes |
| US-002 | P1 | Phase 4 | 3 tasks (frontend) | Yes |
| US-003 | P1 | Phase 4 | Included in TASK-023 | Yes |
| US-004 | P1 | Phase 5 | 2 tasks | Yes |
| US-005 | P1 | Phase 4 | Included in TASK-024 | Yes |
| US-006 | P2 | Phase 6 | 2 tasks | Yes |
| US-007 | P2 | Phase 7 | 2 tasks | Yes |

---

*End of Status Log*
