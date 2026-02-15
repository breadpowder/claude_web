# ADR-002: Technical Architecture

> **Status**: Accepted
> **Date**: 2026-02-14
> **Decision Makers**: Core team (small team)
> **Context Source**: `task_core-engine/` planning artifacts
> **Depends on**: ADR-001 (Platform Strategy)

---

## Context

With the platform strategy decided (ADR-001), the team must make technical architecture choices for the Phase 1 MVP. The system wraps Claude Agent SDK (on Claude Code CLI) in a Python backend, serving React frontends. Each SDK session spawns a CLI subprocess consuming ~500MB-1GB RAM with a 20-30s cold start.

---

## Decision 3: Three-Layer Communication Protocol

### Decision

Use three communication protocols, each serving a distinct layer:

| Layer | Protocol | Purpose |
|-------|----------|---------|
| Agent ↔ User (frontend) | **AG-UI** | Rich agent interaction for domain-specific UIs: streaming, tool calls, state sync, human-in-the-loop approval |
| Server ↔ Server (agentic) | **OpenAI-compliant streaming API** | Any backend can call the platform as a standard LLM endpoint |
| Server ↔ Server (data) | **REST** | Standard API calls for non-agentic data exchange |

### Rationale

1. **AG-UI** is purpose-built for agent-to-frontend communication. It handles tool call streaming, state management, cancel/resume, and human-in-the-loop -- all requirements for domain-specific UIs. It does NOT support server-to-server communication.
2. **OpenAI-compliant API** enables server-to-server agentic calls. Any service can consume the platform as if it were an LLM endpoint. This is the de facto standard for inter-service AI calls.
3. **REST** covers non-agentic data needs (session listing, user management, configuration).

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| WebSocket only (original architecture doc decision) | Custom protocol, harder for external services to integrate. Requires session affinity for load balancing. |
| AG-UI only | Does not support server-to-server communication |
| SSE + REST (two channels) | SSE is server-to-client only; adding REST for client-to-server creates two channels for one interaction |
| A2A protocol for server-to-server | Adds complexity. OpenAI-compliant API is simpler and more widely adopted for server-to-server agent calls. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| AG-UI Python server SDK is thin -- most integrations are via LangGraph/Pydantic AI adapters | Event stream can be implemented directly on FastAPI; protocol is lightweight JSON events over HTTP |
| Three protocols to maintain | Clear separation of concerns; each protocol has a distinct purpose and consumer |

---

## Decision 4: Pre-Warming Pool for SDK Sessions

### Decision

Maintain a pool of pre-initialized `ClaudeSDKClient` instances in an `asyncio.Queue` to eliminate cold start latency for users.

### Rationale

Claude Code CLI cold start is 20-30 seconds. This is unacceptable for a user-facing web product. The pre-warming pool keeps ready instances available for immediate assignment to incoming sessions.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Cold start only | 20-30s wait on every new session. Hostile UX. |
| Lazy initialization | Still slow on first use per user. |
| Persistent long-lived sessions | Memory growth over time; SDK sessions are designed for bounded lifetimes. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| Each idle pooled instance consumes ~500MB-1GB RAM | Pool depth is tunable. Start with pool size of 2-3 on 16GB host. Scale based on usage patterns. |
| Pre-warmed sessions may have stale config if plugins change | Invalidate pool when extension config changes (pool rebuild). |

---

## Decision 5: JSON File-Based Session Index (No Database)

### Decision

Use a single JSON index file for session metadata. No database for MVP.

### Rationale

Use a single JSON index file for session metadata. No database for MVP. With no authentication in Phase 1 (Decision 8), there is no user concept -- all sessions share one index. Phase 2 adds per-user partitioning when auth is introduced.

1. **Session content is already persisted by the CLI subprocess** as JSONL files at `~/.claude/projects/<mangled-cwd>/<session_id>.jsonl`. The backend does not need to duplicate this.
2. **The backend only needs a lightweight metadata index**: session ID mapping, session title, timestamps, status.
3. **JSON files have no dependency**, match the pattern used by both Claude CLI and OpenCode, and are sufficient for "a few people."

Session resume is handled entirely by the SDK: pass `resume=session_id` to `ClaudeAgentOptions`, and the CLI loads all conversation history from its own JSONL files.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| SQLite | Unnecessary dependency for a simple user-session index. Adds complexity without proportional benefit at this scale. |
| In-memory only | Loses user-session mapping on restart. Users cannot find their previous sessions after backend restart. |
| PostgreSQL | Infrastructure overkill for MVP with a few users. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| No query capability across users (e.g., "all active sessions") | Acceptable for a few users. Migrate to SQLite in Phase 2 if user count grows. |
| Concurrent writes from multiple requests | Use file locking or write-through-temp-file pattern. Low contention with few users. |

---

## Decision 6: Lightweight ExtensionLoader (Filesystem Scanner)

### Decision

Build a lightweight `ExtensionLoader` that scans the filesystem for MCP server configs (`mcp.json`), skills (`./skills/`), and commands (`./commands/`), then passes the config to the SDK. No plugin runtime, no lifecycle management.

### Rationale

The SDK/CLI already handles MCP server connections, skill execution, and tool dispatch. The platform only needs to discover what extensions are available and pass the configuration through. Extensions are re-scanned on each new session creation (FR-011c), so new MCP servers or skills added while the platform is running are picked up by the next session without requiring a restart. Building a full plugin framework would duplicate SDK functionality.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Full plugin framework with lifecycle management | Over-engineered for Phase 1. SDK handles execution. |
| Dynamic runtime loading | Complex, risky. Extensions change infrequently. |
| No extension support | Core requirement: platform must support MCP and skills. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| No hot-reload of extensions | Acceptable for MVP. Restart backend to pick up new extensions. Phase 2 adds filesystem watching. |
| No plugin isolation | Acceptable for MVP with operator-trusted extensions. Phase 2 adds subprocess isolation. |

---

## Decision 7: Zustand for Frontend State Management

### Decision

Use Zustand with slice pattern for frontend state management.

### Rationale

Zustand is simple, minimal boilerplate, and uses a slice pattern that keeps chat, session, and extension state isolated. The team values simplicity over feature richness.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Redux | Too much boilerplate for the team's needs. |
| React Context | Causes re-render cascades when state updates frequently. |
| Jotai / Valtio | Less established. Zustand has broader adoption and documentation. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| Smaller ecosystem than Redux | Zustand's API surface is small; less need for ecosystem plugins. |
| Less opinionated -- team needs conventions | Define slice conventions upfront in project docs. |

---

## Decision 8: No Authentication for MVP

### Decision

No authentication mechanism in Phase 1. The platform is accessible without login.

### Rationale

The MVP serves a small, known group of internal users. Adding auth (even a simple API key) adds scope to Phase 1 without proportional value. The priority is validating the core agent interaction loop.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| API key auth | Adds implementation scope. Not needed for small internal team. |
| JWT / OAuth | Significant scope creep for MVP. Deferred to Phase 2. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| No user isolation -- anyone can access any session | Acceptable for internal MVP with trusted users. Network-level access control (VPN/firewall) provides baseline security. |
| Must retrofit auth later | Auth boundary is clean: FastAPI middleware + AG-UI/REST headers. Designed to be addable without restructuring. |

---

## Decision 9: Single Container Deployment for MVP

### Decision

Deploy as a single container running FastAPI + pre-warm pool + all SDK sessions. No orchestration.

### Rationale

Simplest deployment model. One container, one process, no coordination. Appropriate for MVP with a small user base on a single host.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Microservices | Premature for MVP. Adds networking, service discovery, deployment complexity. |
| Sidecar pattern | Adds orchestration dependency (Kubernetes). Not needed at this scale. |
| Serverless | Incompatible with long-lived CLI subprocesses and pre-warming pool. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| Single point of failure | Acceptable for internal MVP. Add health monitoring and auto-restart via container runtime. |
| Cannot scale horizontally | Deferred to Phase 3. Single 16GB host handles 10 concurrent sessions (Decision 10). |

---

## Decision 10: 10 Concurrent Sessions on 16GB Host

### Decision

Target capacity of 10 concurrent SDK sessions on a single 16GB host.

### Rationale

Each CLI subprocess consumes ~500MB-1GB RSS. Pre-warmed pool instances (Decision 4, default size 2) count toward the 10-session limit. With pool size 2, a maximum of 8 user-assigned sessions can run concurrently. Total memory: 10 × ~1GB + ~750MB baseline ≈ 10.75GB on 16GB host. This is validated against capacity estimates in the architecture document.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Higher density (15-20 sessions) | OOM risk. No headroom for memory spikes during tool execution. |
| Lower density (5 sessions) | Underutilizes available hardware. 10 is the sweet spot for 16GB. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| Hard ceiling on concurrent users per host (8 user sessions + 2 pool slots = 10 total) | Sufficient for MVP with a few users. Horizontal scaling deferred to Phase 3. |
| Memory growth over session lifetime | SubprocessMonitor tracks RSS per session. Sessions exceeding threshold get graceful restart (edge case EC-004). |

---

## Note: Observability Strategy (Phase 2)

Phase 1 uses structured logging (timestamp - level - [module.function] - message) and health check endpoints (/api/v1/health/live and /api/v1/health/ready with pool_depth, active_sessions, max_sessions). Full observability (metrics export, distributed tracing, alerting) is deferred to Phase 2 when the platform moves beyond internal MVP.

---

## Overall Consequences

### Benefits
- Minimal infrastructure: single container, no database, filesystem-based storage
- SDK/CLI handles the hard parts: agent loop, session persistence, tool execution, MCP connections
- Clean protocol separation: AG-UI for frontend, OpenAI-compliant for server-to-server, REST for data
- Low operational overhead for a small team

### Risks
- Single container + no auth = limited to trusted internal use until Phase 2
- CLI subprocess memory model (~1GB each) limits density
- AG-UI is newer protocol -- fewer production references than WebSocket
- JSON file session index does not scale beyond a small user base

### Phase 2 Migration Path
- Add JWT/Keycloak authentication
- Migrate session index to SQLite or PostgreSQL if user count grows
- Add filesystem watching for extension hot-reload
- Add plugin isolation via subprocess model
- Multi-container deployment with session affinity
