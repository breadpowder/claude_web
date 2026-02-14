# Technical Feasibility Assessment: claude_sdk_pattern Core Engine

> **Assessment Date**: 2026-02-07
> **Analyst**: Technical Feasibility Analyst
> **Target Platform**: claude_sdk_pattern v1.0 core engine
> **SDK Version**: claude-agent-sdk v0.1.30 (Python)

---

## Executive Summary

### Feasibility Rating: **MEDIUM-HIGH with significant caveats**

The core engine is technically feasible but carries substantial risks from SDK instability, memory management challenges, and architectural constraints. The Claude Agent SDK provides the necessary APIs but has known production issues that require careful mitigation strategies.

**Key Findings**:
- ✅ SDK APIs are stable and well-documented for core functionality
- ⚠️ **CRITICAL**: CLI subprocess has memory growth issues (~500MB-1GB baseline → 24GB+ over extended sessions)
- ⚠️ **CRITICAL**: Cold start latency is 20-30 seconds per session
- ⚠️ SDK is in rapid evolution (v0.1.30 released Feb 5, 2026)
- ✅ FastAPI + WebSocket integration is well-understood pattern
- ⚠️ One subprocess per session limits horizontal scaling options
- ⚠️ Process accumulation and zombie subprocess issues reported

**Recommendation**: Proceed with MVP but implement aggressive memory monitoring, pre-warming pool, and session duration limits from day one. Plan for container-per-session architecture to mitigate subprocess issues.

---

## 1. SDK Readiness Assessment

### 1.1 Version Stability

| Aspect | Status | Evidence |
|--------|--------|----------|
| **Package Version** | v0.1.30 (Feb 5, 2026) | Latest on PyPI, actively maintained |
| **Release Cadence** | Rapid (weekly/bi-weekly) | Indicates active development but also instability |
| **Breaking Changes** | Moderate risk | Package renamed from `claude-code-sdk` to `claude-agent-sdk` |
| **Python Support** | >= 3.10 | Compatible with target (Python 3.12) |
| **Production Readiness** | Beta/Early Production | Official but with known critical issues |

**Assessment**: The SDK is **usable but not production-hardened**. Rapid iteration suggests API churn risk. The package rename indicates the project is still finding its identity.

### 1.2 Known Critical Limitations

#### Memory Growth (SEVERITY: CRITICAL)

**Issue**: CLI subprocess RSS starts at ~500MB-1GB baseline and can grow to 24GB+ over extended sessions (30-60 min+) due to memory leaks.

**Evidence** (baseline verified from GitHub issues #22042 and #4953):
- GitHub Issue anthropics/claude-code#4953 (OPEN): Memory leak causes process to grow to 120GB+ over extended sessions; expected baseline 1-2GB
- GitHub Issue anthropics/claude-code#22042 (CLOSED/FIXED): v2.1.25 showed ~540-555MB stable baseline; v2.1.27 had regression (467MB start, leaked to 7.5GB), fixed in later patch
- GitHub Issue anthropics/claude-code#18280 (CLOSED/FIXED): CPU thrashing bug, not a memory baseline issue
- Shell snapshots in `~/.claude/` grow to 1.5GB

**Impact on Core Engine**:
- On 16GB server, can support more concurrent sessions at startup but memory growth over time constrains practical concurrency to ~3-5 sessions
- Session duration must be capped (recommend 4 hours max)
- Memory monitoring is mandatory, not optional
- Graceful restart/recovery must be built from start

**Mitigation Strategy**:
```
REQUIRED:
- CLAUDE_SDK_PATTERN_MAX_SESSION_DURATION_SECONDS=14400 (4 hours)
- CLAUDE_SDK_PATTERN_MAX_SESSION_RSS_MB=2048 (2GB threshold, ~3x baseline)
- Periodic RSS monitoring via /proc/<pid>/status
- Graceful session termination with user notification
- Cache cleanup between sessions (~/.claude/ snapshots)

CONTAINER STRATEGY:
- Run each session in ephemeral container
- Destroy container on session end (auto-cleanup)
- Allocate 4-8GB RAM per container (headroom for memory growth over session lifetime)
```

**References**:
- [Claude Code Memory Leak - 120GB RAM (Issue #4953, OPEN)](https://github.com/anthropics/claude-code/issues/4953)
- [Memory Allocation Thrashing (Issue #18280, CLOSED/FIXED)](https://github.com/anthropics/claude-code/issues/18280)
- [Critical Memory Regression 2.1.27 (Issue #22042, CLOSED/FIXED)](https://github.com/anthropics/claude-code/issues/22042)

#### Subprocess Initialization Latency (SEVERITY: HIGH)

**Issue**: Claude Code CLI subprocess takes 20-30 seconds to initialize.

**Root Cause**:
- CLI bundles Node.js runtime that must boot V8
- Shell snapshots must be loaded from disk
- API connection must be established
- Authentication handshake adds latency

**Evidence**:
- GitHub Issue anthropics/claude-agent-sdk-python#333: Performance issues with multi-instance deployment
- Agent SDK TypeScript Issue #34: query() has ~12s overhead per call due to no hot process reuse

**Impact on Core Engine**:
- New user waits 20-30s for first response (unacceptable UX)
- Session creation becomes expensive
- Cannot scale quickly to handle traffic spikes

**Mitigation Strategy**:
```
REQUIRED - PRE-WARMING POOL:
- Initialize CLAUDE_SDK_PATTERN_PREWARM_POOL_SIZE=2 clients on startup
- Assign pre-warmed client to new user immediately
- Replenish pool asynchronously in background
- Show "Preparing your session..." UI during cold start fallback

METRICS:
- Track csp_session_init_duration_seconds histogram
- Alert if pool exhaustion occurs frequently
- Auto-scale pool size based on demand patterns
```

**Trade-off**: Pre-warming consumes memory even when idle (~500MB-1GB per slot). For 2-client pool = ~1-2GB baseline memory.

**References**:
- [Performance Issues with Multi-instance Deployment](https://github.com/anthropics/claude-agent-sdk-python/issues/333)
- [TypeScript SDK query() 12s overhead](https://github.com/anthropics/claude-agent-sdk-typescript/issues/34)

#### Zombie Subprocess Accumulation (SEVERITY: MEDIUM-HIGH)

**Issue**: SDK-spawned subprocesses don't terminate properly, accumulating zombie processes.

**Evidence**:
- One report: 155 haiku subprocesses consuming 51GB RAM
- Processes remain after ClaudeSDKClient context manager exits

**Impact on Core Engine**:
- Memory leaks even with proper session cleanup
- Server OOM after dozens of sessions
- Requires manual process cleanup

**Mitigation Strategy**:
```
REQUIRED:
- Track CLI subprocess PID on session creation
- On session cleanup: kill -TERM <pid>, wait 5s, kill -KILL if still alive
- Periodic process audit: scan for orphaned claude-code processes
- Alert if subprocess count exceeds 2x active session count

CONTAINER STRATEGY (PREFERRED):
- Each session in separate container
- Container destruction kills all child processes
- No zombie accumulation possible
```

### 1.3 SDK Feature Readiness

| Feature | SDK Support | Status | Risk |
|---------|------------|--------|------|
| **Core query()** | Native | GA | Low |
| **ClaudeSDKClient** | Native | GA | Low |
| **MCP stdio transport** | Native | GA | Low |
| **MCP HTTP transport** | Native | GA | Low |
| **Custom tools (@tool)** | Native | GA | Low |
| **Skills (SKILL.md)** | Native | GA | Low |
| **Hooks system** | Native | GA (v0.1.20+) | Low-Medium |
| **Subagents (AgentDefinition)** | Native | GA (v0.1.15+) | Medium |
| **Structured outputs** | Native | GA (v0.1.25+) | Low |
| **Session resume/fork** | Native | GA | Low |
| **Permission callbacks (can_use_tool)** | Native | GA | Low |
| **Sandbox configuration** | Native | GA | Medium |
| **Streaming (include_partial_messages)** | Native | GA | Low |

**Assessment**: Core SDK features are **GA and stable**. Advanced features (hooks, subagents) are documented but less battle-tested in production.

### 1.4 Version Pinning Risks

**Risk**: Pinning to v0.1.30 means missing bug fixes and features, but upgrading risks breaking changes.

**Strategy**:
```toml
# pyproject.toml
[project.dependencies]
claude-agent-sdk = "~=0.1.30"  # Allow patch updates (0.1.31, 0.1.32)
# NOT: claude-agent-sdk = "^0.1.30"  # Would allow 0.2.0 (risky)
# NOT: claude-agent-sdk = ">=0.1.30"  # Would allow any version (dangerous)
```

**Monitoring**:
- Subscribe to GitHub releases
- Review changelog for each patch
- Test patch updates in staging before production
- Budget 1 day/month for SDK upgrade testing

---

## 2. Core Engine Components Gap Analysis

| Component | SDK Support | Custom Code Needed | Implementation Complexity | Risk Level |
|-----------|-------------|-------------------|--------------------------|------------|
| **SessionManager** | Partial (ClaudeSDKClient lifecycle) | Session-to-client mapping, timeout tracking, pre-warm pool, memory monitoring | Medium | Medium-High |
| **PluginRegistry** | None | Plugin discovery, validation, activation, persistence, config merging | High | Medium |
| **OptionsBuilder** | None | Build ClaudeAgentOptions from registry, merge configs, apply overrides | Medium | Low-Medium |
| **PermissionGate** | Partial (can_use_tool callback) | RBAC logic, input sanitization, audit logging | Medium | Medium |
| **HookDispatcher** | Partial (hooks parameter) | Aggregate hooks from core + plugins, register with SDK | Low-Medium | Low |
| **WebSocket Handler** | None | Accept connections, authenticate, route messages, stream SDK responses | Medium | Medium |
| **Pre-warming Pool** | None | Initialize clients on startup, assign to sessions, replenish background | Medium | Medium-High |
| **Circuit Breaker** | None | Track API failures, open/close circuit, probe health | Low-Medium | Low |

### 2.1 SessionManager

**SDK Provides**:
- `ClaudeSDKClient` async context manager
- `client.query()` and `client.receive_response()` methods
- Session ID capture from `ResultMessage`
- `resume=<session_id>` and `fork_session=True` parameters

**Must Build**:
- User ID → ClaudeSDKClient instance mapping
- Session metadata storage (session_id, user_id, created_at, last_active, plugin_set)
- Idle timeout tracking (default 30 minutes)
- Session duration limits (default 4 hours)
- Memory monitoring per subprocess (RSS threshold)
- Pre-warm pool management
- Graceful shutdown protocol
- Session resume coordination

**Complexity**: **MEDIUM** - Mostly state management and monitoring. The hard parts (subprocess lifecycle) are handled by SDK.

**Risk**: **MEDIUM-HIGH** - Memory monitoring and pre-warming are critical to UX/stability. Bugs here cause OOM or 30s wait times.

### 2.2 PluginRegistry

**SDK Provides**:
- Nothing - plugins are a platform concept, not SDK concept
- SDK accepts configs that plugins generate (mcp_servers, allowed_tools, hooks, agents)

**Must Build**:
- Filesystem plugin discovery (scan `plugins/` directory)
- Manifest schema validation (plugin.json)
- Plugin type system (tool, MCP, skill, endpoint)
- Plugin lifecycle (discover → validate → register → configure → activate)
- Plugin state persistence (database)
- Secret storage (encrypted)
- Filesystem reconciliation on startup (new plugins on disk, removed plugins)

**Complexity**: **HIGH** - Large surface area, many edge cases, persistence layer, crypto for secrets.

**Risk**: **MEDIUM** - Non-critical to MVP (can launch with zero plugins). Complexity can be managed incrementally.

### 2.3 OptionsBuilder

**SDK Provides**:
- `ClaudeAgentOptions` dataclass (30+ fields)
- Validation of option values

**Must Build**:
- Query PluginRegistry for active plugins
- Merge `mcp_servers` from all MCP + tool plugins
- Merge `allowed_tools` from all plugins + operator config
- Merge `hooks` from HookDispatcher
- Set `can_use_tool` callback to PermissionGate
- Apply session overrides (model, max_budget, resume, fork_session)
- Apply platform defaults (sandbox, max_turns, permission_mode)

**Complexity**: **MEDIUM** - Straightforward merge logic, but 30+ fields to handle.

**Risk**: **LOW-MEDIUM** - Incorrect merging breaks plugin functionality. High test coverage required.

### 2.4 PermissionGate

**SDK Provides**:
- `can_use_tool` callback signature: `(tool_name: str, input_data: dict, context: ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`
- `PermissionResultAllow` with `updated_input` field (for sanitization)
- `PermissionResultDeny` with `reason` field (Claude sees this)

**Must Build**:
- RBAC role system (admin, operator, user)
- Per-user authorization checks
- Plugin permission declarations
- Input sanitization logic (e.g., strip secrets from Bash commands)
- Audit logging (who used what tool, when)

**Complexity**: **MEDIUM** - Core logic is simple (allow/deny), but audit and sanitization add complexity.

**Risk**: **MEDIUM** - Security-critical. Bugs allow unauthorized tool access. Requires security review.

### 2.5 HookDispatcher

**SDK Provides**:
- `hooks` parameter on `ClaudeAgentOptions`
- `HookMatcher` type for registering hooks
- Hook event types (PreToolUse, PostToolUse, etc.)

**Must Build**:
- Aggregate hooks from platform core (PermissionGate, prompt_guard, cost_tracker)
- Aggregate hooks from active plugins
- Merge into hooks dict keyed by `HookEvent`
- Pass merged hooks to OptionsBuilder

**Complexity**: **LOW-MEDIUM** - Mostly list aggregation. Hook registration is plugin responsibility.

**Risk**: **LOW** - Straightforward. Main risk is hook ordering/conflict if multiple plugins register same hook.

### 2.6 WebSocket Handler

**SDK Provides**:
- Nothing - networking is not SDK concern
- SDK streams `AssistantMessage`, `ToolUseBlock`, `ToolResultBlock`, `StreamEvent`, `ResultMessage` via async iterator

**Must Build**:
- FastAPI WebSocket endpoint (`/ws/v1/chat`)
- Accept WebSocket connection + JWT authentication
- Map upstream WebSocket messages to `client.query()` calls
- Map downstream SDK messages to WebSocket JSON messages
- Handle reconnection with message sequence numbers
- Interrupt command handling (`client.interrupt()`)
- Session command handling (resume, fork)
- Error handling and recovery

**Complexity**: **MEDIUM** - WebSocket state management + bidirectional message translation. FastAPI WebSocket support is mature.

**Risk**: **MEDIUM** - Connection reliability issues common in WebSocket apps. Reconnection logic is tricky.

### 2.7 Pre-warming Pool

**SDK Provides**:
- Nothing - pre-warming is optimization strategy, not SDK feature

**Must Build**:
- Initialize N `ClaudeSDKClient` instances on startup (blocking)
- Hold clients in queue (asyncio.Queue)
- Assign client from queue when user creates session
- Replenish queue in background task (asyncio.create_task)
- Track pool size metrics (csp_prewarm_pool_size gauge)
- Handle pool exhaustion (fall back to cold start)

**Complexity**: **MEDIUM** - Queue management + async background tasks. Must handle startup failure (API key invalid, rate limit).

**Risk**: **MEDIUM-HIGH** - Critical to UX. If pool is empty, users wait 30s. If replenish fails silently, pool drains permanently.

### 2.8 Circuit Breaker

**SDK Provides**:
- Nothing - circuit breaker is resilience pattern, not SDK feature

**Must Build**:
- Track `client.query()` connection errors in sliding window
- Open circuit after N failures in M seconds (default: 5 failures in 60s)
- Short-circuit new queries while open (immediate error)
- Periodic probe query to test recovery
- Close circuit when probe succeeds
- Expose circuit state metric (csp_circuit_breaker_state gauge)

**Complexity**: **LOW-MEDIUM** - Well-understood pattern. Many libraries available (pybreaker, aiobreaker).

**Risk**: **LOW** - Non-critical. Improves stability but not required for MVP.

---

## 3. Integration Complexity Assessment

### 3.1 FastAPI + ClaudeSDKClient Integration

**Pattern**: ClaudeSDKClient as long-lived service object, held by SessionManager.

**Complexity**: **LOW-MEDIUM**

**Implementation**:
```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, ClaudeSDKClient] = {}

    async def create_session(self, user_id: str, options: ClaudeAgentOptions) -> str:
        # Option 1: Use pre-warmed client (instant)
        client = await self.prewarm_pool.get()
        # Option 2: Cold start (20-30s)
        # client = ClaudeSDKClient(options=options)
        # await client.__aenter__()

        session_id = generate_session_id()
        self.sessions[session_id] = client
        return session_id

    async def query(self, session_id: str, message: str) -> AsyncIterator:
        client = self.sessions[session_id]
        await client.query(message)
        async for msg in client.receive_response():
            yield msg

    async def cleanup_session(self, session_id: str):
        client = self.sessions.pop(session_id)
        await client.__aexit__(None, None, None)
```

**Challenges**:
- ClaudeSDKClient must be held as instance variable (not local variable)
- Async context manager lifecycle must be managed manually
- Subprocess PID must be tracked for memory monitoring
- Error recovery requires session metadata persistence

**Risk**: **MEDIUM** - Lifecycle bugs cause memory leaks or orphaned subprocesses.

### 3.2 WebSocket Streaming

**Pattern**: Iterate `client.receive_response()` async generator, forward to WebSocket.

**Complexity**: **MEDIUM**

**Implementation**:
```python
from fastapi import WebSocket

@app.websocket("/ws/v1/chat")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = await authenticate_websocket(websocket)

    while True:
        # Upstream: user message
        data = await websocket.receive_json()
        if data["type"] == "user_message":
            await session_manager.query(session_id, data["text"])
            # Downstream: stream SDK messages
            async for msg in session_manager.receive_response(session_id):
                await websocket.send_json(translate_sdk_message(msg))
        elif data["type"] == "interrupt":
            await session_manager.interrupt(session_id)
```

**Challenges**:
- Message type translation (SDK types → WebSocket JSON schema)
- Partial message buffering for `StreamEvent` messages
- Reconnection handling (missed messages, sequence numbers)
- Error propagation (SDK exceptions → WebSocket error frames)
- Concurrent message handling (user sends while streaming)

**Risk**: **MEDIUM** - Message ordering bugs, missed messages on reconnect, race conditions.

### 3.3 MCP Server Management

#### stdio MCP Servers

**SDK Behavior**: SDK spawns stdio MCP server as subprocess, manages lifecycle, kills on ClaudeSDKClient exit.

**Platform Responsibility**: Provide config in `ClaudeAgentOptions.mcp_servers`.

**Complexity**: **LOW** - SDK handles everything.

**Risk**: **LOW-MEDIUM** - Risk of zombie MCP subprocesses if SDK doesn't clean up properly (same issue as CLI subprocess).

#### HTTP MCP Servers

**SDK Behavior**: SDK sends HTTP requests to remote URL. No process management.

**Platform Responsibility**: Ensure MCP server is reachable, handle secrets (API keys), detect server unavailability.

**Complexity**: **LOW** - Config-only integration.

**Risk**: **LOW** - Network failures handled by SDK. Main risk is exposing secrets in config.

#### In-Process MCP Servers (Custom Tools)

**SDK Behavior**: Tools run in same Python process as SDK. No subprocess.

**Platform Responsibility**: Load tool modules, call `create_sdk_mcp_server()`, include in `mcp_servers` config.

**Complexity**: **MEDIUM** - Plugin loading, import safety, error isolation.

**Risk**: **MEDIUM-HIGH** - Malicious or buggy tool can crash Python process, block event loop, or consume unbounded memory. **No process isolation for tool plugins in MVP.**

**Mitigation**:
- Require operator review before activating tool plugins
- Log execution time per tool invocation
- Timeout enforcement (via SDK hooks)
- Future: Move tool plugins to stdio MCP servers for isolation

### 3.4 Plugin Isolation

| Plugin Type | Isolation Level | Risk |
|-------------|----------------|------|
| **MCP (stdio)** | Subprocess | Low - SDK kills subprocess on exit |
| **MCP (HTTP)** | Network | Low - Remote process, no lifecycle coupling |
| **Tool (@tool)** | None (in-process) | **HIGH** - Can crash Python process |
| **Skill (SKILL.md)** | None (SDK-managed) | Low - Read-only files |
| **Endpoint (FastAPI route)** | None (in-process) | **HIGH** - Can crash Python process |

**Critical Gap**: In-process plugins (tool, endpoint) have **zero isolation** in MVP. This is acceptable for trusted operators but unacceptable for multi-tenant deployments.

**Future Enhancement**: Run tool plugins as stdio MCP servers in separate processes.

---

## 4. Technical Constraints and Limitations

### 4.1 Memory Constraints

| Scenario | Memory Requirement | Risk |
|----------|-------------------|------|
| **Single idle session** | ~500MB-1GB RSS | Baseline (per GitHub issues #22042, #4953) |
| **Single active session (4 hours)** | 2-8GB RSS | Memory growth over extended sessions (#4953, OPEN) |
| **Extreme session (long-running)** | 24GB+ RSS | OOM crash from unresolved memory leak (#4953) |
| **Pre-warm pool (2 clients)** | ~1-2GB RSS | Startup cost |
| **FastAPI + Python overhead** | 500MB-1GB | Platform overhead |
| **MCP subprocesses (5 stdio servers)** | 500MB-2GB | Tool overhead |
| **Total for 3 concurrent sessions** | 6-16GB | Depends on session age and activity |

**Constraint (updated with corrected baseline)**: With the corrected ~500MB-1GB baseline per subprocess (not the previously assumed 2.5GB), a 16GB server can support **up to 10 concurrent sessions** at startup (~7.5GB for 10 sessions at ~750MB midpoint + ~1.5GB OS/platform overhead = ~9GB, leaving ~7GB headroom). Memory growth over extended sessions (GitHub #4953, OPEN) is mitigated by:
- RSS monitoring with 2GB threshold (~3x baseline) triggers graceful restart per session
- 4-hour session duration cap prevents unbounded growth
- Conservative sustained capacity: 10 sessions on 16GB (tight), 10 sessions on 32GB (comfortable with full leak headroom)

**Scaling Strategy**: Single-host multi-session for MVP (up to 10 sessions on 16GB). Container-per-session deferred to Phase 3 for isolation and horizontal scaling benefits, not for memory necessity.

### 4.2 Initialization Latency

| Operation | Latency | User Impact |
|-----------|---------|-------------|
| **Cold start (new ClaudeSDKClient)** | 20-30s | Unacceptable |
| **Pre-warmed client assignment** | <100ms | Acceptable |
| **Pool replenishment** | 20-30s | Background, no user impact |
| **Session resume** | 2-5s | Acceptable (loads from disk) |

**Constraint**: Pre-warm pool is **mandatory** for acceptable UX. Without it, every new user waits 30s for first response.

**Pool Sizing**: Pool must be sized for peak concurrent session creation rate. If 10 users join in 1 minute and pool size is 2, 8 users wait 30s.

### 4.3 Concurrency Limits

**Subprocess Model**: One Claude Code CLI subprocess per `ClaudeSDKClient` instance.

**Implications**:
- Cannot share subprocess across sessions (session state is in subprocess)
- Cannot scale vertically beyond memory limits
- Must scale horizontally (more containers)

**Session Affinity**: Once a session is bound to a container, it cannot migrate. Load balancer must use sticky sessions.

### 4.4 Sandbox Limitations

**SDK Sandbox**: Commands run inside SDK-managed sandbox (Linux containers on Linux, VM on macOS/Windows).

**Scope**:
- Applies to `Bash` tool only
- Does not apply to Python tool functions (@tool)
- Does not apply to MCP HTTP servers (remote)

**Risk**: Tool plugins and endpoint plugins have full access to Python process. Cannot be sandboxed without moving to subprocess model.

### 4.5 Networking Constraints

**WebSocket Reliability**:
- WebSocket connections can drop (network issues, proxy timeouts, client sleep)
- Platform must handle reconnection with state recovery

**Proxy Compatibility**:
- Some corporate proxies block WebSocket or have short timeouts
- Fallback to SSE or long-polling may be needed in future

---

## 5. Minimum Viable Core Engine

### Phase 1: MVP (What Can We Build FIRST)

**Goal**: Single-user, admin-only platform with core chat functionality.

**Scope**:
- FastAPI backend with single WebSocket endpoint (`/ws/v1/chat`)
- SessionManager with basic lifecycle (create, query, cleanup)
- Pre-warm pool (size=1)
- Memory monitoring with hard session duration limit (4 hours)
- Basic authentication (API key in header, no RBAC)
- React frontend with chat UI (MessageList, InputBar, ToolUseCard)
- Zero plugins (hardcoded ClaudeAgentOptions)
- SQLite database for session metadata

**Excluded**:
- PluginRegistry
- PermissionGate (all tools allowed)
- HookDispatcher
- Circuit breaker
- Cost tracking
- Health checks / metrics
- Graceful shutdown

**Deliverables**:
1. `src/claude_sdk_pattern/core/session_manager.py` (SessionManager with pre-warm pool)
2. `src/claude_sdk_pattern/api/websocket.py` (WebSocket handler)
3. `src/claude_sdk_pattern/main.py` (FastAPI app entry point)
4. `frontend/src/components/ChatApp.tsx` (React UI)
5. `docker/Dockerfile` (Container image)
6. `tests/integration/test_websocket_flow.py` (End-to-end test)

**Timeline Estimate**: 2-3 weeks (1 backend dev + 1 frontend dev)

**Risk**: **LOW-MEDIUM** - Narrow scope, well-understood patterns. Main risk is SDK subprocess issues.

### Phase 2: Extensions (What Adds Extension Capabilities)

**Goal**: Plugin system operational, multi-user support, RBAC.

**Scope**:
- PluginRegistry (discover, validate, register, activate)
- Plugin manifest schema (plugin.json)
- OptionsBuilder (merge plugin configs)
- PermissionGate (RBAC + can_use_tool callback)
- HookDispatcher
- JWT authentication + user/operator/admin roles
- REST API for plugin management (`/api/v1/plugins`)
- Secret storage (encrypted)
- PostgreSQL database (replace SQLite)

**Deliverables**:
1. `src/claude_sdk_pattern/plugins/registry.py` (PluginRegistry)
2. `src/claude_sdk_pattern/plugins/manifest.py` (Schema validation)
3. `src/claude_sdk_pattern/core/options_builder.py` (OptionsBuilder)
4. `src/claude_sdk_pattern/core/permission_gate.py` (PermissionGate)
5. `src/claude_sdk_pattern/api/plugins_api.py` (REST endpoints)
6. `src/claude_sdk_pattern/plugins/secret_store.py` (Secret encryption)
7. Plugin developer guide (docs/plugin-guide.md)
8. Example plugins (plugins/example-tool/, plugins/example-mcp/)

**Timeline Estimate**: 3-4 weeks

**Risk**: **MEDIUM** - Plugin loading is complex, security-critical. Requires thorough testing.

### Phase 3: Production Hardening (What Makes It Production-Ready)

**Goal**: Observability, resilience, scaling, security hardening.

**Scope**:
- Circuit breaker for API outages
- Prometheus metrics (10+ key metrics)
- Structured logging (structlog JSON)
- Health check endpoints (live, ready, startup)
- Cost tracking + alerting
- Graceful shutdown protocol
- Rate limiting (REST + WebSocket)
- CORS configuration
- Prompt injection defense (UserPromptSubmit hook)
- Subprocess crash recovery
- Auto-interrupt for hung queries
- Frontend error boundaries + accessibility (WCAG AA)

**Deliverables**:
1. `src/claude_sdk_pattern/core/circuit_breaker.py`
2. `src/claude_sdk_pattern/core/cost_tracker.py`
3. `src/claude_sdk_pattern/core/prompt_guard.py`
4. `src/claude_sdk_pattern/api/health.py`
5. `src/claude_sdk_pattern/config/logging.py`
6. Deployment guide (docs/deployment.md)
7. Load testing results
8. Security audit report

**Timeline Estimate**: 2-3 weeks

**Risk**: **MEDIUM** - Many moving parts. Requires production-like testing environment.

---

## 6. Technology Stack Validation

### 6.1 Backend: Python 3.12 + FastAPI + uvicorn

| Aspect | Status | Notes |
|--------|--------|-------|
| **Python 3.12** | ✅ Confirmed | SDK requires >=3.10, 3.12 is excellent choice |
| **FastAPI** | ✅ Confirmed | Mature WebSocket support, async-native, well-documented |
| **uvicorn** | ✅ Confirmed | ASGI server, WebSocket support, production-ready |
| **uv (package manager)** | ✅ Confirmed | Fast, modern, lockfile support |
| **SQLite → PostgreSQL** | ✅ Confirmed | SQLite for MVP, PostgreSQL for multi-server |
| **structlog** | ✅ Recommended | JSON logging, correlation IDs, async-safe |
| **prometheus-fastapi-instrumentator** | ✅ Recommended | Metrics for Prometheus |

**Assessment**: Technology stack is **well-suited** for the platform. No red flags.

**Alternatives Considered**:
- Starlette (lower-level, more control, but FastAPI is better DX)
- Flask (not async-native, poor WebSocket support)
- Django (too heavy for agent backend)

### 6.2 Frontend: React 19 + Vite + Zustand

| Aspect | Status | Notes |
|--------|--------|-------|
| **React 19** | ✅ Confirmed | Bleeding edge but stable, useTransition for streaming perf |
| **Vite** | ✅ Confirmed | Fast dev server, HMR, plugin system for UI slots |
| **Zustand** | ✅ Confirmed | Better than Context API for streaming (selective re-renders) |
| **TypeScript** | ✅ Recommended | Type safety for WebSocket messages, plugin API |
| **CommonMark** | ✅ Recommended | Markdown rendering for messages |

**Assessment**: Frontend stack is **modern and appropriate**. React 19 is cutting-edge but provides real value (useTransition for streaming).

**Risk**: React 19 is new (released Dec 2024). Some libraries may not be compatible. Test thoroughly.

### 6.3 Deployment: Docker + Kubernetes

| Aspect | Status | Notes |
|--------|--------|-------|
| **Docker** | ✅ Confirmed | Standard container format, SDK-compatible |
| **Kubernetes** | ✅ Recommended | For multi-container deployments, auto-scaling |
| **Container-per-session pattern** | ✅ Recommended | Mitigates subprocess issues, ephemeral isolation |
| **Resource limits** | ⚠️ Critical | Must set memory limits (16GB minimum for 10 sessions, 32GB recommended), CPU limits |
| **gVisor / Firecracker** | Optional | Extra isolation for untrusted plugins |

**Assessment**: Container deployment is **recommended and well-documented** by Anthropic.

**Evidence**:
- [Official Hosting Guide](https://docs.claude.com/en/docs/agent-sdk/hosting)
- [Container Deployment Examples (GitHub)](https://github.com/receipting/claude-agent-sdk-container)
- [AgCluster Container (Community Project)](https://github.com/whiteboardmonk/agcluster-container)

**Resource Requirements** (per Anthropic recommendations + corrected empirical data):
- **Per-session minimum**: ~500MB-1GB RAM baseline (corrected from previous 2.5GB)
- **Per-session recommended**: ~1.5GB RAM (with leak headroom buffer)
- **MVP platform (10 sessions)**: 16GB RAM minimum, 32GB recommended, 20GB disk, 4 CPU
- **RSS monitoring threshold**: 2GB per session (~3x baseline) triggers graceful restart

**Scaling Strategy**:
```
LOW SCALE (1-10 concurrent sessions):
- Single server, SessionManager with max_sessions=10
- Pre-warm pool size=2-3
- 16GB RAM (tight), 32GB RAM (comfortable), 4 CPU
- RSS monitoring at 2GB/session, 4h duration cap

MEDIUM SCALE (10-100 users):
- Kubernetes cluster with ephemeral container per session
- Central gateway routes WebSocket to correct container
- Shared PostgreSQL for session metadata
- Auto-scale based on session count

HIGH SCALE (100+ users):
- Multi-region Kubernetes
- Custom operator for container lifecycle
- Redis for session affinity
- Dedicated metrics/cost tracking services
```

---

## 7. SDK-Specific Challenges

### 7.1 The "Subprocess Model" Constraint

**What It Means**: The SDK spawns Claude Code CLI as a subprocess. This is not a lightweight API wrapper—it's a full Electron-like app (Node.js + V8 runtime) running as a child process.

**Implications**:
- Cannot share subprocess across sessions (stateful)
- Cannot quickly spawn new subprocess (20-30s cold start)
- Cannot easily recover from subprocess crash (state is in subprocess)
- Subprocess lifecycle is tied to Python process lifecycle

**Why Anthropic Did This**: The SDK reuses Claude Code CLI to avoid reimplementing the entire agent loop, tools, MCP clients, and UI state management in Python. It's a pragmatic choice but creates operational challenges.

**Platform Response**:
- Accept the constraint (cannot change SDK architecture)
- Design around it (pre-warm pool, container-per-session)
- Monitor aggressively (RSS, subprocess count, zombie processes)
- Plan for future SDK evolution (if Anthropic moves to API-based SDK)

### 7.2 API Key Management

**SDK Behavior**: SDK reads `ANTHROPIC_API_KEY` from environment variable or passes via config.

**Platform Requirement**: Multi-user platform needs per-user or per-tenant API keys (optional) or shared API key with cost tracking.

**Options**:
1. **Shared API Key** (MVP): Platform uses single key, tracks cost per user in database
2. **Per-User API Key** (Future): User provides their own key, stored encrypted
3. **Per-Tenant API Key** (Enterprise): Tenant admin configures key for all users

**Implementation**:
```python
options = ClaudeAgentOptions(
    # Option 1: Shared key (set globally via env var)
    # ANTHROPIC_API_KEY is read automatically

    # Option 2: Per-user key
    api_key=user.encrypted_api_key.decrypt()
)
```

**Risk**: **MEDIUM** - Secret management is security-critical. Shared key is easiest but complicates billing.

### 7.3 Session Storage Location

**SDK Behavior**: Sessions are stored on disk at `~/.claude/projects/<project_name>/<session_id>/`.

**Platform Implications**:
- Session data is local to container
- If container is destroyed, session data is lost (unless volume is mounted)
- Cannot migrate session to different container (data is on disk)

**Options**:
1. **Ephemeral Sessions** (Recommended for MVP): No persistence, session lost on container destruction
2. **Persistent Volume** (Future): Mount `~/.claude/` as Docker volume, survives container restart
3. **External Storage** (Future): If SDK adds S3/blob storage support

**Trade-off**: Ephemeral sessions simplify ops but user loses history on crash. Persistent volumes add complexity.

---

## 8. Open Questions and Unknowns

### 8.1 Subagent Session Resume (P3)

**Question**: Can subagent sessions be resumed by capturing `agentId` from Task tool result?

**Status**: SDK docs are sparse on this. Enhanced architecture marks it as "experimental behind feature flag."

**Action**: Experimental testing required before exposing as platform feature.

### 8.2 Hook Execution Ordering (P2)

**Question**: If multiple plugins register `PreToolUse` hooks, what is execution order?

**Status**: Not documented in SDK.

**Action**: Test empirically. Document behavior in plugin developer guide.

### 8.3 Tool Search Activation (P3)

**Question**: When does `ENABLE_TOOL_SEARCH` activate? What is "10% of context window" threshold?

**Status**: Documented in research report but not in official docs.

**Action**: Test with >50 MCP tools to observe behavior.

### 8.4 Structured Output Retry Behavior (P2)

**Question**: How many retries does SDK attempt before returning `error_max_structured_output_retries`?

**Status**: Not documented.

**Action**: Review SDK source code or test empirically.

### 8.5 ClaudeSDKClient Lifecycle Edge Cases (P1)

**Question**: What happens if SDK subprocess crashes mid-query? Does `receive_response()` raise exception or hang?

**Status**: Enhanced architecture mentions `ProcessError` and `CLIConnectionError` exceptions.

**Action**: Test subprocess kill scenarios in integration tests.

---

## 9. Risk Summary and Mitigations

| Risk | Severity | Probability | Impact | Mitigation |
|------|----------|------------|--------|------------|
| **Memory growth causes OOM** | CRITICAL | High | System crash, user data loss | Session duration limits, RSS monitoring, container destruction |
| **30s cold start hurts UX** | HIGH | Medium | User abandonment | Pre-warm pool (mandatory), cold start UI indicator |
| **Zombie subprocess accumulation** | HIGH | Medium | Memory leak, server crash | PID tracking, explicit kill on cleanup, container-per-session |
| **SDK version breaking change** | MEDIUM | Medium | Platform breaks on upgrade | Pin to ~0.1.30, test upgrades in staging |
| **Tool plugin crashes Python process** | MEDIUM | Low-Medium | Service outage | Review plugins before activation, log execution time, future: subprocess isolation |
| **WebSocket reconnection state loss** | MEDIUM | Medium | User loses context | Message sequence numbers, sync-on-reconnect protocol |
| **API rate limiting** | MEDIUM | Low | New sessions fail | Circuit breaker, exponential backoff, pre-warm pool reduces API calls |
| **Session affinity breaks on container restart** | LOW | Low | User gets new session | Document as known limitation, add session resume UI |
| **Horizontal scaling cost** | LOW | Medium | High infrastructure cost | Accept (API cost >> compute cost), monitor and optimize |

---

## 10. Recommendations

### 10.1 Go / No-Go Decision

**Recommendation**: **GO with aggressive risk management**

The core engine is **technically feasible** but carries **material risk** from SDK instability. The project should proceed but with the following requirements:

**MANDATORY** (Cannot launch without these):
1. Pre-warm pool (size >= 2)
2. Session duration limits (<= 4 hours)
3. Memory monitoring (RSS threshold 2GB, ~3x baseline)
4. Single-host support for up to 10 concurrent sessions on 16GB (container-per-session deferred to Phase 3)
5. Comprehensive integration tests covering subprocess failures

**HIGHLY RECOMMENDED** (Should have for MVP):
1. Circuit breaker for API outages
2. Graceful session termination UI
3. Cost tracking per session
4. Basic metrics (session count, init duration, memory usage)

**DEFERRED TO PHASE 2**:
1. Plugin system (can launch with zero plugins)
2. RBAC (can launch admin-only)
3. Advanced observability (Prometheus metrics, structured logs)

### 10.2 Architecture Decisions

**DECISION 1**: Single-host multi-session for MVP (up to 10 concurrent sessions on 16GB). Container-per-session deferred to Phase 3.
- **Rationale**: With corrected ~500MB-1GB baseline (not 2.5GB), 10 sessions fit comfortably on 16GB. Container-per-session adds isolation benefits but is not required for memory management at this scale.
- **Trade-off**: No session isolation in MVP; SubprocessMonitor + RSS monitoring + duration caps provide adequate safeguards.

**DECISION 2**: Pre-warm pool is mandatory, not optional.
- **Rationale**: 30s cold start is unacceptable UX.
- **Trade-off**: Consumes ~1.5-2.25GB baseline memory for pool of 2-3 (acceptable on 16GB+ servers). Pool slots count toward the 10-session max.

**DECISION 3**: Tool plugins run in-process in MVP, move to subprocess in Phase 2.
- **Rationale**: Simplifies MVP, acceptable for trusted operators.
- **Risk**: Malicious plugins can crash service (mitigated by operator review).

**DECISION 4**: Shared API key for MVP, per-user keys in Phase 2.
- **Rationale**: Reduces complexity for MVP.
- **Trade-off**: Cannot charge users directly (must track cost in platform).

### 10.3 Testing Strategy

**CRITICAL TESTS** (Must pass before launch):
1. Subprocess crash recovery (kill CLI mid-query, verify session can resume)
2. Memory growth measurement (run session for 4 hours, measure RSS growth)
3. Pre-warm pool exhaustion (create 10 sessions rapidly, verify cold start fallback)
4. WebSocket reconnection (drop connection mid-stream, verify state recovery)
5. Concurrent session isolation (2 sessions, verify no state leakage)

**PERFORMANCE TESTS**:
1. Cold start latency (10 samples, p50/p95/p99)
2. Pre-warmed start latency (10 samples, p50/p95/p99)
3. WebSocket message throughput (tokens/sec during streaming)
4. Memory baseline + growth rate (baseline → 1hr → 2hr → 4hr)

**LOAD TESTS**:
1. Concurrent sessions (max supported on 16GB server)
2. Session creation rate (can pre-warm pool keep up?)
3. Sustained operation (24 hour soak test, check for leaks)

---

## 11. Timeline and Effort Estimate

### Phase 1: MVP Core Engine

| Component | Effort (person-days) | Risk |
|-----------|---------------------|------|
| SessionManager + pre-warm pool | 5 days | Medium |
| WebSocket handler | 3 days | Medium |
| FastAPI app + auth | 2 days | Low |
| React chat UI | 5 days | Low |
| Docker container | 2 days | Low |
| Integration tests | 3 days | Medium |
| **Total** | **20 days (4 weeks)** | |

### Phase 2: Plugin System

| Component | Effort (person-days) | Risk |
|-----------|---------------------|------|
| PluginRegistry | 5 days | Medium |
| OptionsBuilder | 3 days | Low |
| PermissionGate | 4 days | Medium-High |
| Secret storage | 2 days | Medium |
| REST API for plugins | 3 days | Low |
| Plugin developer guide | 2 days | Low |
| Example plugins | 3 days | Low |
| **Total** | **22 days (4.5 weeks)** | |

### Phase 3: Production Hardening

| Component | Effort (person-days) | Risk |
|-----------|---------------------|------|
| Circuit breaker | 2 days | Low |
| Metrics + logging | 3 days | Low |
| Cost tracking | 3 days | Medium |
| Health checks | 1 day | Low |
| Rate limiting | 2 days | Low |
| Security hardening | 3 days | Medium |
| Load testing | 3 days | Medium |
| Deployment guide | 2 days | Low |
| **Total** | **19 days (4 weeks)** | |

**GRAND TOTAL**: ~12 weeks (3 months) from start to production-ready.

---

## 12. Conclusion

The core engine for `claude_sdk_pattern` is **technically feasible** using Claude Agent SDK v0.1.30. The SDK provides stable APIs for all required functionality. However, the project carries **significant operational risk** from known SDK issues:

**CRITICAL RISKS**:
- Memory growth (~500MB-1GB baseline → 24GB+ over extended sessions, #4953 OPEN) requires aggressive monitoring and session limits
- 30s cold start requires mandatory pre-warm pool
- Zombie subprocess accumulation requires PID tracking and periodic cleanup; container-per-session deferred to Phase 3

**SUCCESS FACTORS**:
- Accept subprocess model constraint (cannot change SDK)
- Design around limitations (pre-warm, monitor, container-per-session)
- Plan for SDK evolution (rapid release cadence, potential breaking changes)
- Start narrow (MVP with zero plugins, single-user)
- Expand incrementally (Phase 2 plugins, Phase 3 production hardening)

**GO DECISION**: Proceed with MVP development with the mandatory mitigations listed in Section 10.1.

---

## References

**SDK Documentation**:
- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Agent SDK Python API](https://platform.claude.com/docs/en/agent-sdk/python)
- [Hosting the Agent SDK](https://docs.claude.com/en/docs/agent-sdk/hosting)

**Known Issues**:
- [Memory Leak - 120GB RAM (Issue #4953, OPEN)](https://github.com/anthropics/claude-code/issues/4953)
- [Memory Allocation Thrashing (Issue #18280, CLOSED/FIXED)](https://github.com/anthropics/claude-code/issues/18280)
- [Critical Memory Regression 2.1.27 (Issue #22042, CLOSED/FIXED)](https://github.com/anthropics/claude-code/issues/22042)
- [Performance Issues Multi-instance (Issue #333)](https://github.com/anthropics/claude-agent-sdk-python/issues/333)
- [TypeScript SDK 12s Overhead (Issue #34)](https://github.com/anthropics/claude-agent-sdk-typescript/issues/34)

**Community Resources**:
- [Container Deployment Example](https://github.com/receipting/claude-agent-sdk-container)
- [AgCluster Container Platform](https://github.com/whiteboardmonk/agcluster-container)
- [Practical Guide to Python SDK (2025)](https://www.eesel.ai/blog/python-claude-code-sdk)
- [Claude Code Multiple Agents Guide](https://www.eesel.ai/blog/claude-code-multiple-agent-systems-complete-2026-guide)

**Technology Stack**:
- [FastAPI Production Best Practices](https://render.com/articles/fastapi-production-deployment-best-practices)
- [FastAPI Best Practices 2026](https://fastlaunchapi.dev/blog/fastapi-best-practices-production-2026)
