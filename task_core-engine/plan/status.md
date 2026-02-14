# Planning Status: Core Engine MVP

> **Feature**: core-engine
> **Phase**: Architecture & Strategy (sdlc-plan-first)
> **Started**: 2026-02-14
> **Authority**: ADR-001 (Platform Strategy), ADR-002 (Technical Architecture)

---

## Step 1: Understand Use Case and Goal

**Status**: COMPLETE

### Requirements Analysis

The core engine is the production operations layer for Claude Agent SDK. It wraps the SDK's CLI subprocess model in a Python/FastAPI backend, exposing three communication protocols:

1. **AG-UI** (frontend): Rich agent-to-frontend interaction with streaming events, tool calls, state sync, human-in-the-loop
2. **OpenAI-compliant streaming API** (server-to-server agentic): Any backend can call the platform as a standard LLM endpoint
3. **REST** (data): Non-agentic operations (session CRUD, health, extensions)

### Key Constraints (from ADRs)

- Python + FastAPI backend (company compliance blocks Node.js)
- Claude Agent SDK spawns CLI subprocess per session (~500MB-1GB baseline, 20-30s cold start)
- No database for MVP: JSON file-based session index
- No authentication for MVP: network-level access control only
- Single container deployment: no orchestration
- 10 concurrent sessions on 16GB host
- Pre-warming pool mandatory (asyncio.Queue)
- Lightweight ExtensionLoader (filesystem scanner, no plugin lifecycle)
- Zustand for frontend state (simplicity, full message rendering)

### Stakeholder Mapping

| Stakeholder | Key Concern |
|-------------|-------------|
| End User (Jordan) | Fast session start, reliable chat, tool transparency |
| Extension Developer (Alex) | Claude Code extension compatibility (mcp.json, skills, commands) |
| Platform Operator (Morgan) | Stability, resource monitoring, easy deployment |
| External Service Consumer | Standard OpenAI-compatible API integration |

### Scope Boundaries

**In scope (Phase 1 MVP)**: 11 user stories across 4 epics (Core Chat, Server-to-Server, Extensions, Human-in-the-Loop)
**Out of scope**: Authentication, database, plugin registry, RBAC, cost tracking, metrics, multi-container deployment

---

## Step 2: Gap Analysis

**Status**: COMPLETE

### Existing Codebase

The repository is currently documentation-only (`claudesdk_integration.md`). No production code exists. Everything must be built from scratch.

### Components to Build (Custom)

| Component | SDK Support | Custom Work |
|-----------|------------|-------------|
| SessionManager | Partial (ClaudeSDKClient lifecycle) | Session-to-client mapping, pre-warm pool, memory monitoring, duration limits |
| AG-UI Endpoint | None | AG-UI event translation from SDK stream events, FastAPI SSE endpoint |
| OpenAI-compliant API | None | Request/response format translation, SSE streaming |
| REST API | None | Session CRUD, health checks, extension listing |
| ExtensionLoader | None | Filesystem scanner for mcp.json, skills/, commands/ |
| SubprocessMonitor | None | RSS tracking via /proc, zombie cleanup, graceful restart |
| JSONSessionIndex | None | Atomic file I/O with locking, session metadata persistence |
| React Chat UI | None | MessageList, InputBar, ToolUseCard, Zustand stores |

### Reusable from SDK

- ClaudeSDKClient async context manager and query() method
- SDK session persistence (JSONL files at ~/.claude/projects/)
- MCP server connections and tool dispatch
- Skill execution
- Sandbox configuration
- Permission callbacks (can_use_tool)
- Session resume via `resume=session_id` parameter

---

## Step 3: Open Source Research

**Status**: COMPLETE

### Key Findings (from requirement/team_findings/open_source_research.md)

- **No existing solution** combines Claude SDK CLI runtime + unified Python backend + three-layer communication (confirms ADR-001 build decision)
- **claude-code-openai-wrapper** (394 stars): Closest reference for OpenAI-compliant API translation, but no license, covers only ~20% of scope
- **Langflow** (130k stars, MIT): Best tech stack alignment (Python, FastAPI, React), SSE streaming patterns
- **LibreChat** (33.6k stars, MIT): Best session management and auth patterns

### Phase 1 Library Selections (ADR-aligned)

| Need | Library | License | Rationale |
|------|---------|---------|-----------|
| Web framework | FastAPI + uvicorn | MIT / BSD-3 | ADR-001 Decision 2 |
| AG-UI events | ag-ui-protocol (ag_ui.core + ag_ui.encoder) | TBD (evaluate) | ADR-002 Decision 3 |
| SSE streaming | sse-starlette or custom | MIT/BSD | OpenAI-compliant API |
| File locking | filelock | Unlicense | JSON session index concurrent access |
| Frontend state | Zustand | MIT | ADR-002 Decision 7 |
| UI primitives | Radix UI | MIT | Accessible components |
| Styling | Tailwind CSS | MIT | Utility-first |

### Deferred Libraries (Phase 2+)

PyJWT (auth), aiobreaker (circuit breaker), slowapi (rate limiting), structlog (logging), prometheus-fastapi-instrumentator (metrics), cryptography (secrets)

---

## Step 4: Impact Assessment

**Status**: COMPLETE

### Components Modified

None -- greenfield project. All components are new.

### Performance Implications

- Pre-warm pool consumes ~1-2GB baseline for 2-3 idle sessions
- AG-UI event stream adds < 200ms latency per event (NFR-003)
- JSON file I/O < 10ms per read/write (NFR-014)
- 10 concurrent sessions at ~1GB each = ~10GB + ~2GB platform overhead fits in 16GB

### Security Considerations

- No auth in Phase 1 (ADR-002 Decision 8): network-level access control only
- Env var sanitization for extensions (blocklist: LD_PRELOAD, PATH, PYTHONPATH)
- Operator-trusted extensions only (no plugin isolation in Phase 1)
- Subprocess sandbox for Bash commands

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| SDK memory leak (OOM) | CRITICAL | 4h session limit, 2GB RSS threshold, graceful restart |
| 30s cold start | HIGH | Pre-warm pool (mandatory) |
| AG-UI protocol immaturity | HIGH | Lightweight JSON events on FastAPI; can adapt quickly |
| Zombie subprocess accumulation | MEDIUM | PID tracking, periodic cleanup, SIGTERM/SIGKILL |
| JSON session index corruption | MEDIUM | Atomic writes, file locking, backup recovery |

---

## Step 5: Options Analysis and Decision

**Status**: COMPLETE

See `decision-log.md` for detailed options analysis.

---

## Step 6: Architecture

**Status**: COMPLETE

See `strategy/architecture.md` for component diagrams, data flow, and control flow with edge cases.

---

## Step 7: Implementation Plan

**Status**: COMPLETE

See `strategy/implementation_plan.md` for integration contracts, API endpoints, data models, and feature planning.

---

*End of Planning Status*
