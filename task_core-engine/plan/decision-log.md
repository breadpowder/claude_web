# Decision Log: core-engine

> **Feature**: claude_sdk_pattern Core Engine (Phase 1 MVP)
> **Date**: 2026-02-07

---

## Decision 1: WebSocket vs SSE for Client-Server Communication

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: WebSocket** | Bidirectional: native interrupt support (Ctrl+Shift+X sends command over same connection); single connection per session; lower latency for high-frequency streaming | Proxy compatibility issues in some corporate environments; requires sticky sessions at LB; manual reconnection logic | Medium |
| **B: SSE + REST** | Simpler server implementation; automatic browser reconnection; works through all proxies; no sticky sessions | Interrupt requires separate REST POST; two connections per session (SSE + REST); higher overhead for user-to-server messages | Low |

### Selected Option
**Option A: WebSocket**

### Rationale
1. PRD explicitly specifies `/ws/v1/chat` endpoint (FR-002) and interrupt via Ctrl+Shift+X (FR-008, US-005)
2. Interrupt is a P0 requirement, not a nice-to-have. Separate REST endpoint for interrupt adds race conditions (interrupt must arrive before next streaming token)
3. Single connection simplifies per-session connection deduplication (G-003: one active connection per session_id)
4. The target deployment is self-hosted (not corporate proxy environments), reducing proxy risk
5. SSE fallback is planned for Phase 2 if corporate proxy issues surface (documented in Assumption A-005)

### Strategic Assessment
- **Current problem solved**: Bidirectional streaming + interrupt in single connection
- **Edge cases handled**: EC-010 (duplicate tabs), EC-033 (concurrent messages), EC-035 (disconnect mid-tool)
- **Future ready**: WebSocket token refresh (Phase 2, EC-016), message replay on reconnect (Phase 2, EC-036)
- **Extensibility**: Can add SSE fallback endpoint later without breaking WebSocket clients

---

## Decision 2: Pre-Warming Pool Strategy

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Mandatory pre-warm pool (size >= 1)** | Sub-3s session start; blocks readiness probe until ready; proven UX benefit | ~500MB-1GB per slot baseline cost; complexity (replenishment, invalidation, failure handling) | Medium |
| **B: No pre-warming (cold start only)** | Zero idle memory cost; simpler code; "Preparing..." UI is acceptable | 20-30s wait for every new session; violates NFR-001 (<3s target); user abandonment risk | High |
| **C: Lazy pre-warming (warm after first user)** | Lower idle cost than A; first user waits, subsequent users fast | First user always waits 30s; startup probe passes before pool is ready | Medium-High |

### Selected Option
**Option A: Mandatory pre-warm pool**

### Rationale
1. PRD specifies pre-warming as P0 (FR-001) with <3s target (NFR-001)
2. Devil's Advocate challenged this as "premature optimization." PRD response: "The 20-30 second cold start is the primary UX blocker identified in research" (US-001)
3. Pool blocks readiness probe until at least 1 slot filled (G-002), preventing traffic to unusable instances
4. Memory cost is acceptable: ~1-2GB for pool=2 on a 16GB server leaves ~14-15GB for active sessions
5. Edge cases are well-documented: EC-001 (empty pool fallback), EC-014 (rate-limited pre-warm), EC-022 (startup failure)

### Strategic Assessment
- **Current problem solved**: 20-30s cold start eliminated for normal flow
- **Edge cases handled**: EC-001, EC-014, EC-022, EC-098
- **Future ready**: Dynamic pool sizing based on load (Phase 2+)
- **Anti-pattern avoided**: Over-engineering avoided by starting with configurable static size (PREWARM_POOL_SIZE env var)

---

## Decision 3: Session Storage for MVP

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: SQLite (aiosqlite)** | Zero deployment overhead; embedded; ACID; validates data model before PostgreSQL | Not suitable for multi-server; file-based locking | Low |
| **B: PostgreSQL (asyncpg)** | Multi-server ready; rich queries; horizontal read scaling | Requires external service; overkill for single-user MVP; adds deployment complexity | Medium |
| **C: In-memory dict only** | Simplest; zero persistence | Session metadata lost on restart; no resume support | Low |

### Selected Option
**Option A: SQLite (aiosqlite)**

### Rationale
1. PRD specifies "SQLite storage -- no external dependencies" for Phase 1 (Section 3.1)
2. MVP is single-server, single-user. SQLite handles this trivially.
3. Data model validated in SQLite migrates cleanly to PostgreSQL in Phase 2 (FR-022)
4. Session metadata is small (~1KB per session) with infrequent writes
5. Conversation history is NOT stored in our DB (SDK manages on disk at `~/.claude/`)

### Strategic Assessment
- **Current problem solved**: Persist session metadata for resume, session list
- **Future ready**: PostgreSQL migration in Phase 2 with provided migration script
- **Extensibility**: Abstract DB access behind repository interface for clean swap

---

## Decision 4: Extension Loading Mechanism

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Direct pass-through to SDK** | Zero abstraction; matches Claude Code behavior exactly; minimal code | No validation layer; no dynamic management | Low |
| **B: Custom ExtensionLoader with validation** | Can validate mcp.json schema; can report errors to user; can support hot-detection | More code than A; slight overhead | Low-Medium |
| **C: Full PluginRegistry (Phase 2 design)** | Formal lifecycle, manifest validation, activation workflow | Massive over-engineering for Phase 1; violates PRD scope | High |

### Selected Option
**Option B: Custom ExtensionLoader (lightweight)**

### Rationale
1. PRD specifies "file-based extension model (mcp.json, ./skills/, ./commands/) -- mirrors Claude Code's extension handling" (Section 3.1)
2. Pure pass-through (A) misses validation: what if mcp.json has invalid JSON? User sees opaque SDK error.
3. ExtensionLoader adds: (a) validate mcp.json syntax, (b) scan ./skills/ and ./commands/ directories, (c) build ClaudeAgentOptions fields, (d) re-scan on new session creation (FR-011c)
4. This is NOT the Phase 2 PluginRegistry. No manifest schema, no lifecycle states, no activation workflow.
5. Guardrail G-003b requires extensions "MUST be loaded using the same mechanism as Claude Code"

### Strategic Assessment
- **Current problem solved**: Load extensions from filesystem, validate, pass to SDK
- **Edge cases handled**: Invalid mcp.json (clear error), missing skill files, commands directory
- **Future ready**: Phase 2 PluginRegistry wraps this and adds formal lifecycle on top
- **Anti-pattern avoided**: Not building full plugin system for unproven demand (Devil's Advocate Section 2.5)

---

## Decision 5: Frontend State Management

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Zustand with slices** | Selective re-renders during streaming; clean separation of message, session, and streaming state; well-tested for high-frequency updates | Extra dependency; learning curve | Low |
| **B: useReducer + Context** | Zero dependencies; built-in; familiar | Context triggers full subtree re-render; streaming at 10+ tokens/sec causes performance issues | Medium |
| **C: React 19 useTransition only** | Built-in; handles concurrent updates | Does not solve state subscription problem; still need centralized store for multi-component state | Medium |

### Selected Option
**Option A: Zustand with slices**

### Rationale
1. PRD requires streaming token display (FR-003) with <100ms per-token latency (NFR-003)
2. Multiple components need streaming state simultaneously: MessageList (append tokens), InputBar (disable during stream), ToolUseCard (update status), SessionList (update last-active)
3. Zustand's selector pattern ensures only the component subscribed to changing state re-renders
4. Devil's Advocate challenged this. Response: React 19 useTransition helps with batching but does NOT solve the "4 components watching different state slices" problem. Context would force all 4 to re-render on every token.
5. Zustand is a 1KB library with zero boilerplate. The overhead is minimal.

### Strategic Assessment
- **Current problem solved**: Efficient state management for streaming UI
- **Edge cases handled**: EC-028 (high token rate), EC-046 (buffer growth)
- **Future ready**: Plugin UI slots can create their own Zustand stores (Phase 2)
- **Anti-pattern avoided**: Over-engineering avoided by using 3 slices max (messages, sessions, streaming)

---

## Decision 6: Authentication for MVP

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Single API key** | Simplest; no user management; matches PRD scope | No per-user identity; no audit trail per user | Low |
| **B: JWT from day 1** | Per-user identity; audit trail; Phase 2 ready | Premature complexity; requires user database; token refresh protocol | Medium |

### Selected Option
**Option A: Single API key**

### Rationale
1. PRD explicitly scopes MVP to "API key auth only (no RBAC, no multi-user)" (Section 3.1)
2. Devil's Advocate confirmed: "API key auth is sufficient for v1" (Section 2.6)
3. Single operator/user model means per-user identity has no value in Phase 1
4. API key validated in middleware (REST) and WebSocket upgrade handler
5. Key stored in CLAUDE_SDK_PATTERN_API_KEY environment variable (never in code or logs, G-009)

### Strategic Assessment
- **Current problem solved**: Prevent unauthorized access to platform
- **Future ready**: JWT auth (Phase 2) replaces API key middleware without architectural change
- **Anti-pattern avoided**: Not building RBAC for users that do not exist yet

---

## Decision 7: Container Strategy for MVP

**Date**: 2026-02-07
**Status**: Approved

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Single container (backend + frontend)** | Simple deployment (`docker run`); matches FR-012 | All sessions share container resources; no session isolation | Low |
| **B: Container-per-session** | Full session isolation; memory limits per session; clean zombie cleanup | Complex orchestration; requires Kubernetes or similar | High |

### Selected Option
**Option A: Single container for MVP**

### Rationale
1. PRD specifies "Single Dockerfile builds complete platform" (FR-012)
2. Phase 1 targets up to 10 concurrent sessions on a single 16GB host (NFR-008, updated with corrected ~500MB-1GB baseline per subprocess)
3. Container-per-session requires orchestration that exceeds MVP scope
4. SubprocessMonitor handles memory and zombie concerns within the single container
5. Container-per-session is a Phase 3 optimization for isolation and horizontal scaling, not required for memory management at MVP scale

### Strategic Assessment
- **Current problem solved**: Simple `docker run` deployment
- **Future ready**: Architecture supports extraction to container-per-session without redesign
- **Risk mitigation**: RSS monitoring (2GB threshold) + 4h duration cap; 16GB host handles 10 sessions comfortably

---

## Decision 8: 10 Concurrent Sessions on Single Host for MVP

**Date**: 2026-02-07
**Status**: Approved

### Context

Previous capacity estimates were based on a ~2.5GB per subprocess baseline, which limited the platform to 2-3 concurrent sessions on a 16GB server. Corrected evidence from GitHub #4953 (OPEN) shows the actual baseline is ~500MB-1GB per subprocess. This fundamentally changes the capacity math and the container-per-session recommendation for MVP.

### Options Considered

| Option | Pros | Cons | Risk Level |
|--------|------|------|------------|
| **A: Single-host, 10 concurrent sessions** | Simple deployment; no orchestration; 10 x ~750MB = ~7.5GB fits in 16GB with headroom; matches MVP simplicity | No session isolation; shared memory space; requires RSS monitoring per session | Low-Medium |
| **B: Container-per-session (K8s orchestration)** | Full isolation; clean zombie cleanup; independent memory limits per session | Requires Kubernetes or Docker Swarm; massive deployment complexity for MVP; overkill at 10-session scale | High |
| **C: Hybrid (single-host MVP, container-per-session Phase 3)** | MVP simplicity now; production isolation later; incremental path | Must design SubprocessMonitor to work in both models | Low |

### Selected Option
**Option C: Hybrid (single-host MVP, container-per-session Phase 3)**

### Rationale

**Memory Budget Calculation (10 concurrent sessions)**:

| Component | Memory | Calculation |
|-----------|--------|-------------|
| 10 sessions baseline | ~7.5GB | 10 x ~750MB (midpoint of 500MB-1GB range) |
| 10 sessions with leak headroom | ~15GB | 10 x ~1.5GB (conservative 2x buffer for memory growth over session lifetime) |
| OS + FastAPI + React build serving | ~1-2GB | Platform overhead |
| **Minimum server RAM** | **16GB (tight)** | 7.5GB baseline + 1.5GB overhead + headroom |
| **Comfortable server RAM** | **32GB** | Full leak headroom + overhead |

**Key observations**:
1. With corrected ~500MB-1GB baseline (not 2.5GB), 10 sessions fit comfortably on a 16GB host
2. The RSS restart threshold of 2GB (~3x baseline) catches leaking sessions early, before they consume excessive memory
3. 4-hour session duration cap (mitigating GitHub #4953 unbounded growth) further limits per-session memory growth
4. Pre-warm pool of 2-3 is reasonable: covers burst creation at 20-30s cold start per slot
5. Container-per-session adds isolation benefits (zombie cleanup, crash isolation) but is not required for memory management at this scale

**Alternatives rejected**:
- Container-per-session for MVP: overkill at 10-session scale. The orchestration complexity (K8s/Docker Swarm, service discovery, session routing) far exceeds the isolation benefit when SubprocessMonitor + RSS monitoring + duration caps provide adequate safeguards.

**RSS threshold update**:
- Previous: MAX_SESSION_RSS_MB=4096 (4GB) -- based on incorrect 2.5GB baseline assumption
- Updated: MAX_SESSION_RSS_MB=2048 (2GB) -- ~3x the corrected ~750MB baseline. This catches sessions that have grown 3x their baseline, indicating a leak, while leaving headroom before the session becomes a memory problem for co-located sessions.

### Strategic Assessment
- **Current problem solved**: 10 concurrent sessions on MVP single host with adequate monitoring
- **Edge cases handled**: Memory leaks caught at 2GB via RSS monitoring; 4h duration cap prevents unbounded growth
- **Future ready**: Container-per-session in Phase 3 adds isolation for multi-tenant, horizontal scaling
- **Anti-pattern avoided**: Not over-engineering MVP with K8s orchestration for 10 sessions

---

## Decision Traceability Matrix

| Tech Decision | User Stories Affected | Edge Cases Handled | Future Scenarios |
|--------------|----------------------|-------------------|------------------|
| WebSocket | US-002, US-003, US-005 | EC-010, EC-033, EC-035 | SSE fallback, token refresh |
| Pre-warm pool | US-001 | EC-001, EC-014, EC-022, EC-098 | Dynamic sizing, auto-scale |
| SQLite | US-006 (resume metadata) | EC-007, EC-073 | PostgreSQL migration |
| ExtensionLoader | US-002 (tool use), FR-011/011a/011b/011c | Invalid mcp.json, missing skills | PluginRegistry wraps this |
| Zustand | US-002, US-003, US-005 | EC-028, EC-046 | Plugin UI stores |
| API key auth | US-002, FR-009 | WebSocket auth failure | JWT replacement |
| Single container | FR-012 | EC-114, EC-121 | Container-per-session |
| 10 sessions on single host | FR-010, NFR-008 | Memory leaks (RSS monitoring), duration limits | Container-per-session (Phase 3) |

---

*End of Decision Log*
