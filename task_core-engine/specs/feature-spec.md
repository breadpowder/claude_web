# Feature Specification: claude_sdk_pattern Core Engine

> **Document Version**: 1.0
> **Date**: 2026-02-07
> **Status**: Draft - Pending Review
> **Owner**: Product Team
> **DRI**: Platform Lead

---

## 1. Problem Statement

### 1.1 The Problem

Teams that have invested in building Claude Agent SDK workflows (MCP servers, custom tools, skills) have no production-grade path to expose those capabilities as a shared web service. Today, each developer runs the SDK locally via CLI, and there is no way to:

- Share agent capabilities with non-technical team members
- Enforce cost controls, permissions, or audit logging
- Operate the SDK in production (observability, error recovery, session management)
- Deploy with acceptable startup latency (the SDK's 20-30 second cold start is a blocker)

### 1.2 Why Build vs. Contribute to Existing Platforms

The Devil's Advocate research (Section 1) raised the critical question: why not contribute to OpenWebUI, Dify, or LobeChat instead of building a new platform?

**Answer -- Three structural gaps in existing platforms that cannot be closed by contribution:**

1. **Subprocess Lifecycle Management**: The Claude Agent SDK spawns a full Node.js CLI subprocess per session (~500MB-1GB baseline, 20-30s cold start, potential unbounded memory growth over extended sessions per GitHub #4953). No existing platform is designed for this model. OpenWebUI, Dify, and LobeChat treat LLMs as stateless API calls. Retrofitting subprocess lifecycle management into these platforms would require rewriting their core session layer.

2. **Native MCP Integration Without Abstraction**: Existing platforms use abstraction layers (LangChain, custom action formats) that are 6+ months behind the SDK. Our platform passes `ClaudeAgentOptions` directly to the SDK with zero translation. Teams reuse MCP servers, custom tools, and skills they already built for Claude Code CLI without any rewrite.

3. **SDK-Specific Operational Concerns**: Memory growth monitoring (~500MB-1GB baseline with potential unbounded growth), zombie subprocess cleanup, pre-warming pools, RSS-based restart thresholds -- these are SDK-specific problems that no general-purpose chat platform addresses. Contributing these as plugins to OpenWebUI would be fighting the platform, not extending it.

**The value proposition is**: "The production operations layer for Claude Agent SDK" -- not "another chat UI."

### 1.3 Goals

| Goal | Measurable Target | Timeline |
|------|-------------------|----------|
| Enable users to access Claude agent capabilities via web browser with up to 10 concurrent sessions | Task completion rate > 90%; user can maintain and switch between up to 10 independent conversations on a single 16GB host | MVP (Phase 1) |
| Eliminate 20-30s cold start via pre-warming pool | Time to first response < 3 seconds (pre-warmed) | MVP (Phase 1) |
| Prevent cost surprises from runaway API usage | Cost within 10% of budget per month | Phase 2 |
| Provide production-grade observability | MTTR < 5 minutes for session issues | Phase 3 |
| Allow dev to add MCP servers, skills, and commands via file-based config (same as Claude Code) | Drop mcp.json or ./skills/ directory, new session picks it up | MVP (Phase 1) |

### 1.4 Non-Goals (Out of Scope for v1)

Based on Devil's Advocate feedback and technical feasibility constraints:

| Explicitly Out of Scope | Rationale |
|-------------------------|-----------|
| Multi-LLM support (GPT, Gemini) | Claude-native platform; multi-LLM dilutes the value proposition |
| Plugin UI slots (frontend injection) | No validated demand; 99% of plugins will be backend-only tools (Devil's Advocate Section 2.5) |
| Plugin marketplace | Requires ecosystem that does not exist yet; defer until 10+ community plugins |
| Multi-tenant SaaS | Unit economics require $50+/user/month at ~750MB-1.5GB/session (Devil's Advocate Section 2.1); target self-hosted teams |
| Mobile-native app | Mobile-responsive web is sufficient for Phase 1-3; native app requires separate team |
| SAML/SCIM SSO | Enterprise feature; defer until enterprise customer validation |
| Session branching visualizer | UX innovation opportunity, but not required for core value |
| Natural language plugin configuration | High complexity, low initial demand |
| Collaborative multi-user sessions | Requires WebSocket broadcast and presence; Phase 4+ |

---

## 2. Stakeholders

| Stakeholder | Role | Key Concern | Involvement |
|-------------|------|-------------|-------------|
| Plugin Developer (Alex) | Builds custom tools and MCP integrations | "Can I build a plugin in 30 minutes?" | Feature validation, plugin API design |
| Platform Operator (Morgan) | Deploys and monitors the platform | "Will this wake me up at 3am?" | NFR validation, deployment testing |
| End User (Jordan) | Uses the chat interface for daily tasks | "Does it just work?" | Usability testing, acceptance criteria |
| Platform Admin (Sam) | Manages users, costs, and compliance | "Can I trust this with production data?" | Security review, RBAC design |
| Enterprise Evaluator (Casey) | Evaluates platform for 5000-user rollout | "Does this meet our architecture standards?" | Architecture review, load testing |

---

## 3. Functional Requirements

### 3.1 Phase 1: MVP Core Engine (Weeks 1-4)

**Goal**: Single-user platform with core chat functionality, multiple concurrent sessions, and acceptable startup latency.

**Scope decisions that address Devil's Advocate concerns**:
- File-based extension model (mcp.json, ./skills/, ./commands/) -- mirrors Claude Code's extension handling; no plugin registry UI or activation workflow needed
- API key auth only (no RBAC, no multi-user) -- single operator/user; multi-user deferred to Phase 2
- Multiple sessions per user -- user can create and switch between independent conversations
- SQLite storage -- no external dependencies; validates data model before PostgreSQL migration
- WebSocket for streaming (not SSE) -- SDK streaming model maps naturally to WebSocket; SSE fallback deferred

| FR-ID | Requirement | Priority | Acceptance Criteria |
|-------|------------|----------|---------------------|
| FR-001 | **Session creation with pre-warming pool** | P0 | Pre-warmed session assigned in < 100ms; cold start fallback shows "Preparing..." UI; pool size configurable via env var |
| FR-002 | **WebSocket chat endpoint** | P0 | Client connects via `/ws/v1/chat`; sends JSON messages; receives streaming SDK responses as JSON frames |
| FR-003 | **Streaming token display** | P0 | Tokens render in browser as they arrive from SDK (not buffered); first token visible within 2s of pre-warmed session start |
| FR-004 | **Tool use transparency** | P0 | When Claude invokes a tool, UI shows tool name, execution status (running/complete/error), and result summary |
| FR-005 | **Session duration limits** | P0 | Sessions auto-terminate after configurable max duration (default 4 hours); user notified at 90% of limit; grace period for in-flight query |
| FR-006 | **Memory monitoring (RSS)** | P0 | Subprocess RSS tracked via /proc; session flagged for restart when RSS exceeds threshold (default 2GB, ~3x the ~750MB baseline); graceful restart after current query completes |
| FR-007 | **Subprocess cleanup** | P0 | On session end: SIGTERM to subprocess, wait 5s, SIGKILL if still alive; periodic scan for zombie processes; alert if orphaned process count > 0 |
| FR-008 | **React chat UI** | P0 | MessageList, InputBar, ToolUseCard components; Enter to send, Ctrl+Shift+X to interrupt; responsive layout (min 360px width) |
| FR-009 | **API key authentication** | P0 | Single API key in env var; all endpoints and WebSocket connections require valid key in header; 401 on invalid key |
| FR-010 | **Multiple concurrent sessions** | P0 | User can create multiple independent sessions; session list UI shows all sessions with last-active timestamp; user can switch between sessions or start new one |
| FR-010a | **Session resume** | P1 | User can resume any previous session by session_id; conversation history loaded from SDK session storage |
| FR-011 | **MCP server integration via mcp.json** | P0 | Platform reads `mcp.json` from project root on startup; each entry defines an MCP server (command, args, env); servers are passed to `ClaudeAgentOptions.mcp_servers`; tools available as `mcp__<server>__<tool>` in chat; matches Claude Code's MCP config format |
| FR-011a | **Skills integration via ./skills/** | P0 | Platform scans `./skills/<name>/SKILL.md` directories on startup; discovered skills are available to the agent via `setting_sources`; developer adds a skill by creating a directory with SKILL.md; matches Claude Code's skill discovery |
| FR-011b | **Custom commands via ./commands/** | P1 | Platform scans `./commands/` for command definitions; commands exposed as slash commands in chat UI (e.g., `/deploy`, `/review`); developer adds a command by creating a file in the directory |
| FR-011c | **Extension hot-detection on session creation** | P1 | MCP servers, skills, and commands are re-scanned when a new session is created; changes to mcp.json, ./skills/, or ./commands/ are picked up by new sessions without platform restart |
| FR-012 | **Docker containerization** | P1 | Single Dockerfile builds complete platform (backend + frontend); `docker run` starts working instance; health check at /api/v1/health/live |
| FR-013a | **Error messages with context** | P1 | All errors include: what happened, why, what user can do next; no generic "Something went wrong" messages |

### 3.2 Phase 2: Advanced Plugin System and Multi-User (Weeks 5-8)

**Goal**: Formal plugin system with manifest-based registry (beyond file-based mcp.json/skills/commands from Phase 1), multi-user support with RBAC, cost tracking.

**Note**: Phase 1 already provides file-based MCP, skills, and commands integration. Phase 2 adds the managed plugin registry with validation, lifecycle, encrypted secrets, and admin UI for third-party plugin distribution.

| FR-ID | Requirement | Priority | Acceptance Criteria |
|-------|------------|----------|---------------------|
| FR-013 | **Plugin Registry** | P1 | Scan `plugins/` directory for `plugin.json` manifests; validate schema; register valid plugins; reject invalid with line-number errors; extends Phase 1 file-based model with formal lifecycle |
| FR-014 | **Plugin lifecycle management** | P1 | Plugins transition through: discovered -> validated -> registered -> configured -> activated; operator controls transitions via API |
| FR-015 | **OptionsBuilder** | P1 | Merge mcp_servers from mcp.json (Phase 1) + plugin registry (Phase 2) + allowed_tools + hooks into single ClaudeAgentOptions; validate merged config before session creation |
| FR-016 | **PermissionGate (RBAC)** | P1 | Three roles: admin, operator, user; admin manages users/plugins; operator manages sessions/config; user can chat with allowed tools only |
| FR-017 | **JWT authentication** | P1 | Access tokens (15 min) + refresh tokens (7 days); WebSocket token refresh protocol (server sends refresh_required, client sends new token) |
| FR-018 | **Per-user cost tracking** | P1 | Track API cost per user per session from ResultMessage; store in database; expose via admin API |
| FR-019 | **Per-user cost caps** | P1 | Admin sets monthly cost cap per user (default $100); user receives warning at 80%; session creation blocked at 100% with clear message |
| FR-020 | **Audit logging** | P1 | Log every tool invocation: timestamp, user_id, session_id, tool_name, input (sanitized), result_status; queryable via admin API |
| FR-021 | **Secret storage (encrypted)** | P1 | Plugin secrets encrypted with Fernet before database storage; decrypted only during OptionsBuilder; raw secrets never exposed via API |
| FR-022 | **PostgreSQL migration** | P2 | Replace SQLite with PostgreSQL for multi-server deployments; migration script provided; backward-compatible schema |
| FR-023 | **Plugin hot reload** | P2 | File change detected in plugins/ triggers re-scan; new/changed plugins re-validated; active sessions not affected (new sessions pick up changes) |

### 3.3 Phase 3: Production Hardening (Weeks 9-12)

**Goal**: Observability, resilience, security hardening for production deployment.

| FR-ID | Requirement | Priority | Acceptance Criteria |
|-------|------------|----------|---------------------|
| FR-024 | **Circuit breaker** | P2 | Opens after 5 API failures in 60s; short-circuits new queries while open; periodic probe; closes on probe success; state exposed as metric |
| FR-025 | **Prometheus metrics** | P2 | 10+ metrics at /metrics: session_count, init_duration, rss_bytes, api_cost_total, error_rate, circuit_breaker_state, pool_depth, query_duration, tool_execution_count, websocket_connections |
| FR-026 | **Structured JSON logging** | P2 | All logs as JSON with: timestamp, level, event, correlation_id, session_id, user_id; configurable via structlog processor chain |
| FR-027 | **Health check endpoints** | P2 | GET /api/v1/health/live (process alive), /ready (pool has capacity, DB connected), /startup (init complete); K8s-compatible response codes |
| FR-028 | **Graceful shutdown** | P2 | On SIGTERM: stop accepting new sessions, notify active users via WebSocket, wait for in-flight queries (up to 30s), clean up subprocesses, exit |
| FR-029 | **Rate limiting** | P2 | Per-IP REST rate limiting (60 req/min); per-session WebSocket message rate limiting (20 msg/min); configurable via env vars |
| FR-030 | **Prompt injection defense** | P2 | UserPromptSubmit hook: message length check (32k chars), common injection pattern scanning, session ID verification; log blocked attempts |
| FR-031 | **Cost alerting** | P2 | Alert when daily platform cost reaches 80% of configured threshold; alert delivered via webhook (configurable) |
| FR-032 | **Helm chart** | P3 | Kubernetes deployment via `helm install`; values.yaml for all configurable parameters; includes ServiceMonitor for Prometheus |
| FR-033 | **WebSocket reconnection sync** | P2 | Message sequence numbers; 5-minute buffer for disconnected clients; replay missed messages on reconnect; buffer size capped at 100 messages or 10MB |

---

## 4. Non-Functional Requirements

| NFR-ID | Category | Requirement | Target | Measurement Method |
|--------|----------|------------|--------|-------------------|
| NFR-001 | Performance | Time to first response (pre-warmed) | < 3 seconds | Measure session assignment + first SDK token |
| NFR-002 | Performance | Time to first response (cold start) | < 35 seconds | Measure subprocess init + first SDK token |
| NFR-003 | Performance | Streaming token latency | < 100ms per token | Measure SDK event to WebSocket frame |
| NFR-004 | Performance | WebSocket reconnection sync | < 2 seconds | Measure reconnect + replay |
| NFR-005 | Reliability | Session crash rate | < 0.1% | Crashed sessions / total sessions per day |
| NFR-006 | Reliability | Uptime (during business hours) | > 99.5% | Health check monitoring |
| NFR-007 | Reliability | Graceful shutdown success | 100% (no lost in-flight queries) | Monitor SIGTERM handling in integration tests |
| NFR-008 | Scalability | Concurrent sessions per 16GB host (across all users) | Up to 10 active sessions (~750MB baseline each, ~7.5GB + headroom for leaks + OS/platform overhead) | Load test with memory monitoring |
| NFR-009 | Scalability | Pre-warm pool replenishment | < 60 seconds per slot | Measure background pool fill time |
| NFR-010 | Security | API key exposure | Zero secrets in logs or API responses | Log audit + penetration test |
| NFR-011 | Security | Subprocess sandbox | All Bash commands sandboxed (except operator allowlist) | Sandbox escape testing |
| NFR-012 | Observability | MTTR (Mean Time to Recovery) | < 5 minutes | Measure from alert to resolution in runbook exercises |
| NFR-013 | Cost | Cost predictability | Within 10% of monthly budget | Compare actual API spend to configured threshold |
| NFR-014 | Deployment | Docker build time | < 5 minutes | Measure CI/CD pipeline |
| NFR-015 | Deployment | Time from `docker run` to first chat | < 90 seconds | Measure startup probe pass time |

---

## 5. Constraints

### 5.1 Technical Constraints (from SDK)

| Constraint | Source | Impact | Mitigation |
|------------|--------|--------|------------|
| One subprocess per session | SDK architecture | Cannot share sessions; horizontal scaling only via containers | Single-host multi-session for MVP (up to 10); container-per-session for Phase 3; pre-warming pool for latency |
| ~500MB-1GB baseline RAM per session | SDK CLI subprocess (corrected per GitHub #4953 evidence) | Up to 10 concurrent sessions on 16GB server (~7.5GB baseline + headroom) | Document minimum hardware (16GB recommended); horizontal scaling guide |
| 20-30s cold start | SDK CLI initialization | Unacceptable UX without pre-warming | Mandatory pre-warming pool (size >= 1) |
| Unbounded memory growth over extended sessions | SDK memory leak risk (GitHub #4953, OPEN) | Sessions must be time-limited; RSS monitoring mandatory | 4-hour session limit; RSS monitoring (2GB threshold); graceful restart |
| Zombie subprocess accumulation | SDK cleanup gaps | Server OOM after many sessions without cleanup | PID tracking; explicit SIGKILL; container-per-session |
| SDK v0.1.30 (rapid evolution) | Active development | API may change; breaking changes possible | Pin to ~0.1.30; budget 1 day/month for upgrade testing |

### 5.2 Operational Constraints

| Constraint | Impact |
|------------|--------|
| Self-hosted only (no SaaS offering) | Customer responsible for infrastructure; reduces support burden |
| Shared API key for MVP | Cannot charge per-user; cost attribution by platform tracking only |
| In-process tool plugins (no isolation in v1) | Operator-reviewed plugins only; no public plugin marketplace |
| Single-region deployment (v1) | No data residency controls; enterprise customers may require multi-region |

### 5.3 Agent Guardrails (Constraints for Downstream Implementation Agents)

| Guardrail | Rule | Rationale |
|-----------|------|-----------|
| G-001 | All session operations MUST include PID tracking for the subprocess | Zombie process prevention |
| G-002 | Pre-warm pool MUST block server readiness probe until at least 1 slot is filled | Prevents routing to unusable instance |
| G-003 | WebSocket handler MUST enforce one active connection per session_id | Prevents state corruption from duplicate tabs |
| G-003a | SessionManager MUST support multiple concurrent sessions, each with independent state | Multi-session: user manages parallel conversations |
| G-003b | mcp.json, ./skills/, and ./commands/ MUST be loaded using the same mechanism as Claude Code (pass to ClaudeAgentOptions.mcp_servers and setting_sources) | Extension compatibility: reuse existing Claude Code extensions without modification |
| G-004 | All plugin secrets MUST be encrypted before database storage | Security: secrets at rest |
| G-005 | All tool invocations MUST be audit-logged before execution | Compliance: audit trail |
| G-006 | Session duration MUST be capped (configurable, default 4 hours) | Memory leak mitigation |
| G-007 | RSS monitoring MUST trigger graceful restart, not hard kill | User experience: complete current query before restart |
| G-008 | Frontend MUST NOT display raw SDK error messages to end users | UX: translate errors to actionable messages |
| G-009 | API key MUST NOT appear in logs, error messages, or API responses | Security: secret exposure prevention |
| G-010 | Host/container MUST have sufficient memory for all sessions: 10 sessions x ~1.5GB (conservative with leak buffer) + ~2GB OS/platform overhead = 17GB minimum; 16GB host is tight, 32GB recommended for headroom | OOM prevention with headroom |

---

## 6. Assumption Register

| ID | Assumption | Status | Owner | Validation Method | Impact if Wrong |
|----|-----------|--------|-------|-------------------|-----------------|
| A-001 | SDK memory leak will not be fixed in next 6 months | Unconfirmed | Tech Lead | Monitor Anthropic issue #13126 | If fixed: can relax session limits and RSS monitoring |
| A-002 | Pre-warming pool of 2 is sufficient for MVP usage patterns | Unconfirmed | Operator | Production metrics on pool exhaustion rate | If wrong: increase pool size; add auto-scaling |
| A-003 | API key auth is sufficient for MVP (no RBAC needed initially) | Unconfirmed | Product Owner | User feedback in first 2 weeks | If wrong: accelerate Phase 2 RBAC |
| A-004 | SQLite is adequate for single-server MVP | Unconfirmed | Tech Lead | Load test with 10 concurrent sessions | If wrong: move PostgreSQL migration to Phase 1 |
| A-005 | WebSocket is better than SSE for this use case | Unconfirmed | Tech Lead | Compare proxy compatibility issues in production | If wrong: add SSE fallback endpoint |
| A-006 | Users will tolerate 4-hour session limit | Unconfirmed | Product Owner | Session duration analytics in production | If wrong: investigate SDK memory fix; increase limit |
| A-007 | Tool plugin isolation via operator review is sufficient for v1 | Unconfirmed | Security Lead | Security audit of submitted plugins | If wrong: accelerate subprocess isolation |
| A-008 | 141 edge cases identified are comprehensive | Unconfirmed | QA Lead | Production incident analysis | If wrong: add newly discovered edge cases |
| A-009 | Anthropic will not launch hosted Claude Code that makes this obsolete | Unconfirmed | Product Owner | Monitor Anthropic announcements | If wrong: pivot to niche (e.g., "Claude for ops teams") |
| A-010 | Target users (5-50 person teams) will self-host | Unconfirmed | Product Owner | User interviews during MVP testing | If wrong: consider hosted offering |

---

## 7. Success Metrics

### 7.1 Product Metrics

| Metric | Target | Phase | Measurement |
|--------|--------|-------|-------------|
| Time to first working session | < 90 seconds from `docker run` | Phase 1 | Startup probe to first chat message |
| Time to first response (pre-warmed) | < 3 seconds | Phase 1 | Session assignment + first token |
| Task completion rate | > 90% | Phase 1 | Successful tool executions / total attempts |
| Session abandonment rate | < 15% | Phase 1 | Sessions with < 2 messages / total sessions |
| Time to first working plugin | < 30 minutes | Phase 2 | From `docker-compose up` to first plugin tool invocation |
| User provisioning time | < 10 minutes | Phase 2 | From admin action to user login |
| Cost variance | Within 10% of budget | Phase 2 | Actual monthly API spend vs configured threshold |
| Deployment time (Helm) | < 4 hours | Phase 3 | Helm install to first production user session |
| MTTR | < 5 minutes | Phase 3 | Alert to incident resolution |
| Session crash rate | < 0.1% | Phase 3 | Crashed sessions / total sessions per day |

### 7.2 Operational Health Metrics

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Uptime | > 99.5% | < 99.0% |
| API Error Rate | < 0.5% | > 1.0% |
| Pre-warm Pool Depth | >= 1 at all times | = 0 (critical) |
| Subprocess RSS | < 2GB per session (~3x baseline) | > 2GB |
| Circuit Breaker State | Closed | Open (alert) |
| Cost per Active User per Month | < $50 | > $75 |

---

## 8. Risk Assessment

| Risk ID | Risk | Severity | Probability | Impact | Mitigation | Owner |
|---------|------|----------|-------------|--------|------------|-------|
| R-001 | SDK memory leak causes production OOM | CRITICAL | High | System crash, user data loss | Session duration limits (4h), RSS monitoring (2GB threshold, ~3x baseline), single-host with 16GB for MVP; container-per-session deferred to Phase 3 | Tech Lead |
| R-002 | Anthropic launches hosted Claude Code | CRITICAL | Medium (40%) | Platform becomes obsolete | Ship MVP fast (4 weeks); pivot to niche if needed; differentiate on plugin system | Product Owner |
| R-003 | SDK breaking changes in v0.2.0 | HIGH | High (80%) | Parts of platform break | Pin to ~0.1.30; test upgrades in staging; budget 1 day/month | Tech Lead |
| R-004 | Pre-warming pool exhaustion during traffic spike | HIGH | Medium | Users wait 30s; abandonment | Pool auto-scaling; dynamic sizing based on load; cold start UI | Tech Lead |
| R-005 | In-process tool plugin crashes FastAPI | HIGH | Low-Medium | Service outage for all users | Operator review before activation; Phase 2: move to subprocess isolation | Security Lead |
| R-006 | No one builds plugins (ecosystem fails to materialize) | HIGH | High (70%) | Platform has no differentiation | Ship with 5 built-in MCP integrations; defer plugin system until demand proven | Product Owner |
| R-007 | Unit economics unsustainable ($4.50-$9/user/month infra) | MEDIUM | Medium | Cannot scale beyond internal teams | Accept self-hosted model; document hardware requirements; target teams willing to self-host | Product Owner |
| R-008 | WebSocket reliability issues in corporate proxies | MEDIUM | Medium | Users cannot connect | Document proxy requirements; plan SSE fallback for Phase 2 | Tech Lead |
| R-009 | Zombie subprocess accumulation despite cleanup | MEDIUM | Medium | Server OOM after many sessions | PID tracking, periodic audit, container-per-session architecture | Tech Lead |
| R-010 | Users reject 4-hour session limit | MEDIUM | Low | User dissatisfaction | Monitor session duration; if SDK fixes memory leak, relax limit | Product Owner |

---

## 9. Open Questions

| ID | Question | Owner | Due Date | Status |
|----|----------|-------|----------|--------|
| OQ-001 | Should pre-warm pool invalidate when plugin config changes? | Tech Lead | Week 2 | Open |
| OQ-002 | Is 60s acceptable as subprocess init timeout? | Tech Lead | Week 1 | Open |
| OQ-003 | Should plugin deactivation force-disconnect active sessions? | Product Owner | Week 5 | Open |
| OQ-004 | Global or per-session circuit breaker? | Tech Lead | Week 9 | Open |
| OQ-005 | WebSocket token refresh vs. force disconnect/reconnect? | Tech Lead | Week 5 | Open |
| OQ-006 | Hard budget cap enforcement or soft warning only? | Product Owner | Week 5 | Open |
| OQ-007 | Session affinity at load balancer or application level? | Operator | Week 9 | Open |
| OQ-008 | What makes a pod "ready"? Pool depth, circuit breaker, DB? | Operator | Week 9 | Open |
| OQ-009 | Should we evaluate TypeScript full-stack as alternative? | Tech Lead | Week 1 | Open |
| OQ-010 | Hook execution ordering when multiple plugins register same hook? | Tech Lead | Week 5 | Open |

---

## 10. Dependencies

### 10.1 External Dependencies

| Dependency | Version | License | Risk |
|------------|---------|---------|------|
| claude-agent-sdk | ~0.1.30 | Anthropic License | HIGH: rapid evolution, potential breaking changes |
| FastAPI | Latest | MIT | LOW: stable, well-maintained |
| uvicorn | Latest | BSD-3 | LOW |
| React | 19 | MIT | LOW-MEDIUM: React 19 is new, some library incompatibility |
| Vite | Latest | MIT | LOW |
| Zustand | Latest | MIT | LOW |

### 10.2 Component Library Dependencies (from Open Source Research)

| Component | Library | Version | License |
|-----------|---------|---------|---------|
| WebSocket | Starlette (built-in) | Included | BSD-3 |
| Session Store (Dev) | aiosqlite | v0.20+ | MIT |
| Session Store (Prod) | asyncpg | v0.30+ | Apache 2.0 |
| Plugin Hooks | pluggy | v1.6+ | MIT |
| Circuit Breaker | aiobreaker | v1.1+ | BSD-3 |
| Rate Limiting | slowapi | v0.1.9+ | MIT |
| JWT Auth | PyJWT | v2.11+ | MIT |
| Logging | structlog | v25.5+ | MIT/Apache 2.0 |
| Metrics | prometheus-fastapi-instrumentator | v7.0+ | ISC |
| Secret Management | cryptography (Fernet) | v44.0+ | Apache 2.0/BSD-3 |
| UI Primitives | Radix UI | v1.0+ | MIT |

---

## 11. Definition of Ready Checklist

- [x] Problem and goals are unambiguous
- [x] In/out of scope defined with clear boundaries
- [x] Primary user stories and scenarios identified (see user-stories.md)
- [x] Acceptance criteria finalized and testable (Given/When/Then)
- [x] NFRs set with measurable targets
- [x] Risks and open questions logged with owners
- [x] Guardrails and assumption register complete
- [x] Control flows documented for all major user journeys
- [x] Edge cases mapped to control flow steps with resolutions
- [ ] Owner/DRI, timeline, and success metrics agreed (pending review)

---

## 12. Phased Delivery Timeline

| Phase | Duration | Key Deliverables | Exit Criteria |
|-------|----------|-----------------|---------------|
| **Phase 1: MVP Core Engine** | Weeks 1-4 | SessionManager, WebSocket handler, React chat UI, pre-warm pool, session list, mcp.json loading, skills discovery, commands support, Docker container | User can chat via web browser with < 3s response time; can create/switch multiple sessions; agent uses MCP servers from mcp.json, skills from ./skills/, and commands from ./commands/ |
| **Phase 2: Advanced Plugins & Multi-User** | Weeks 5-8 | PluginRegistry, OptionsBuilder, PermissionGate, JWT auth, RBAC, cost tracking, encrypted secrets | Formal plugin lifecycle with manifests; multiple users with RBAC; cost caps and audit logging |
| **Phase 3: Production Hardening** | Weeks 9-12 | Circuit breaker, Prometheus metrics, structured logging, health checks, Helm chart | Platform passes load test (10 concurrent users), monitoring operational |

---

*End of Feature Specification*
