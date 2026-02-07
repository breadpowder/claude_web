# Architecture Review: enhanced_architecture.md

> Reviewer: Architecture Reviewer / Devil's Advocate
> Review Date: 2026-02-06
> Document Under Review: `enhanced_architecture.md` v1.0
> Research Sources: Claude Agent SDK v0.1.31 (PyPI), Context7 MCP, GitHub issues, official SDK docs

---

## Executive Summary

The enhanced architecture document is a substantial and well-structured design for wrapping Claude Agent SDK as a pluggable web platform. It demonstrates strong familiarity with the SDK surface area and makes sound foundational choices (ClaudeSDKClient over query(), hooks-based security, plugin manifest system). However, the document under-addresses several critical production concerns -- most importantly the **subprocess scaling bottleneck**, **security hardening**, **error recovery**, and **observability**. It also makes optimistic assumptions about SDK capabilities that conflict with known issues reported by the community. This review identifies 7 categories of concern and provides 15 prioritized recommendations.

---

## 1. Strengths

The architecture gets several important things right:

**Correct SDK interface selection.** Section 3.1 correctly identifies `ClaudeSDKClient` as the appropriate interface for a chat application, with accurate rationale about session state, hooks, and streaming support. The distinction from `query()` is well-articulated.

**Accurate SDK parameter mapping.** Section 8.4 correctly maps application settings to `ClaudeAgentOptions` fields. The `OptionsBuilder` concept of dynamically constructing options per session is sound and aligns with how the SDK expects to be configured. The permission_mode, setting_sources, and sandbox parameters are used appropriately.

**Hooks integration is well-designed.** Section 3.5 identifies the right hook events for the right purposes. Using `PreToolUse` for permission enforcement is the correct pattern per the SDK docs. The `HookDispatcher` aggregation concept is architecturally clean.

**Plugin type taxonomy is comprehensive.** Section 5.3 correctly maps the four plugin types to their SDK integration points: `@tool` functions bundled via `create_sdk_mcp_server()`, MCP server configs added to `mcp_servers`, skills via `add_dirs` and `setting_sources`, and endpoint plugins as FastAPI routers. This covers the full SDK capability surface.

**Honest about constraints.** Section 9 (Scaling Considerations) and Section 11 (Open Design Decisions) acknowledge real limitations rather than hand-waving them away. The subprocess constraint is called out explicitly.

**WebSocket protocol design is thorough.** Section 3.3 defines clear upstream and downstream message types that map to real SDK message types. The protocol is well-specified enough to implement from.

---

## 2. Missing Concerns

### 2.1 Security

The architecture mentions security in passing but lacks a comprehensive security design.

**Authentication and authorization.** Section 3.3 mentions the WebSocket connects "with authentication headers" but does not specify the authentication mechanism. Is this JWT-based? OAuth2? API key? The FastAPI gateway (Section 2) lists endpoints but does not describe an auth middleware, token validation, or user identity propagation. For a platform that gives users access to a shell-capable AI agent, authentication is not optional infrastructure -- it is a core security boundary.

**CORS configuration.** The frontend is described as a client-side SPA (Section 4.4) communicating via WebSocket. No CORS policy is defined for the REST endpoints or the WebSocket upgrade request. In a deployment where the frontend and backend are on different origins, missing CORS headers will prevent the application from working. In a deployment where they share an origin, overly permissive CORS creates attack surface.

**Rate limiting.** No rate limiting is mentioned anywhere. Each user message triggers an SDK query that spawns API calls costing real money. Without rate limiting, a single malicious or buggy client can exhaust the `max_budget_usd` or, if no budget is set, rack up unbounded API costs. Rate limiting should exist at both the WebSocket message level and the REST API level.

**Prompt injection defense.** The document does not address prompt injection. User messages pass directly to `client.query()` which sends them to Claude. If the platform is multi-tenant, one user's message could attempt to override system prompts, exfiltrate other users' data (if sessions share a container), or manipulate tool behavior. The `PreToolUse` hook guards tool execution but does not guard the prompt itself. The `UserPromptSubmit` hook event exists in the SDK (documented in the architecture_analysis.md, Section "Missing Patterns") but is not mentioned in the hooks table in Section 3.5.

**Secret management for plugins.** Section 5.2 mentions operators providing "API keys" and "environment variables" during plugin configuration. These secrets are passed via `PUT /api/plugins/{name}/config` (Section 7.2) and then merged into `ClaudeAgentOptions.env` (Section 8.4). There is no discussion of how secrets are stored, encrypted at rest, rotated, or scoped. Storing API keys in a SQLite database (the default per Section 8.1) without encryption is a security vulnerability.

### 2.2 Error Handling and Recovery

**SDK subprocess crash recovery.** Section 5.4 states "If an MCP server crashes, the SDK handles the error; it does not bring down the main process." This is true for external MCP servers. However, it does not address what happens when the **CLI subprocess itself** crashes -- which is the SDK's core process, not a plugin. GitHub issue anthropics/claude-code#13126 documents that the Claude Code CLI can be killed by the Linux OOM killer, with RSS memory growing from 2.5 GB to 24-26 GB in extended sessions. When this happens, the `ClaudeSDKClient` will raise a `ProcessError`. The architecture does not describe:
  - How the WebSocket handler catches and recovers from `ProcessError`
  - Whether the session can be resumed after a crash (via `resume=<session_id>`)
  - Whether the user is notified and offered recovery options
  - How to prevent OOM in the first place (cache cleanup, session duration limits)

**Circuit breakers.** If the Anthropic API is down or rate-limited, every `client.query()` call will fail. The architecture does not describe circuit breaker patterns to avoid cascading failures across all sessions. A single API outage will produce error storms through all active WebSocket connections.

**Graceful degradation.** If a specific plugin's MCP server is unreachable, should the session start without that plugin's tools? The architecture says the plugin moves to "errored" status (Section 5.4), but does not describe what happens to **in-flight sessions** that were already using that plugin's tools. Does Claude get notified that tools disappeared? Does the user see an explanation?

**Timeout handling.** Section 5.4 mentions hook timeouts, but what about the overall query timeout? If Claude enters a long tool-execution loop (e.g., a Bash command that hangs), what is the timeout? The SDK's `max_turns` setting limits conversation turns but not wall-clock time. The `client.interrupt()` method is referenced (Section 3.3 upstream messages) but the conditions under which the server auto-interrupts are not defined.

### 2.3 Scalability

**The 20-30 second initialization problem.** GitHub issue anthropics/claude-agent-sdk-python#333 reports that SDK instance initialization takes 20-30+ seconds because it spawns the Claude Code CLI, which bundles a full Node.js runtime and must initialize its V8 engine, load shell snapshots, and establish API connections. The architecture describes creating a `ClaudeSDKClient` when the user opens a chat (Section 3.1). This means users will wait 20-30 seconds before they can send their first message. This is not mentioned in the scaling section.

Section 11 lists "ClaudeSDKClient pooling" as an open design decision but understates the severity. Without pooling or pre-warming, the platform will have unacceptable first-message latency.

**Cache accumulation and memory growth.** The Claude Code CLI accumulates data in `~/.claude/` directories, particularly shell-snapshots (up to 1.5 GB per GitHub issue anthropics/claude-code#13126). In the ephemeral container model (Section 3.8), this is mitigated because containers are destroyed. But in the single-server model for low-scale deployments (Section 9), sessions sharing a `~/.claude/` directory will accumulate cache indefinitely. No cache management strategy is described.

**Concurrent session limits.** Section 9 estimates 8-16 concurrent sessions on a 16 GiB / 8 vCPU machine. This estimate appears optimistic given the evidence. The SDK recommends 1 GiB RAM per instance, but real-world reports show memory growing to 2.5+ GB per session. With overhead from FastAPI, the Plugin Registry, and MCP subprocesses, a more conservative estimate would be 4-8 sessions on that hardware. The document should present these figures as ranges with caveats rather than as definitive capacities.

**Connection pooling for MCP servers.** Multiple sessions may connect to the same external MCP server (e.g., a shared GitHub MCP). The architecture does not discuss whether MCP server connections are shared across sessions or duplicated per session. If each session spawns its own subprocess for the same MCP server, this creates unnecessary overhead. The SDK likely manages this per-client, meaning N sessions = N MCP subprocesses for the same server.

### 2.4 Observability

The architecture has no observability design. For a production platform that orchestrates subprocesses, manages user sessions, executes arbitrary tools, and streams results, this is a significant omission.

**Logging.** No structured logging is described. What format? What fields? Where do logs go? The SDK's CLI subprocess produces its own logs (stderr). How are those captured? The `PostToolUse` hook is mentioned for "result logging" (Section 3.5) but there is no logging framework, log aggregation, or correlation ID scheme.

**Metrics.** No metrics are defined. Key metrics for this platform would include: active sessions, session creation latency (the 20-30s problem), messages per session, tool execution counts, tool failure rates, API costs per session, WebSocket connection health, and plugin error rates.

**Distributed tracing.** When a user message flows through the WebSocket handler, to the Core Engine, to the SDK, to the CLI subprocess, to the Claude API, to a tool execution, and back -- how is this traced? No trace context propagation is described.

**Health checks.** The architecture lists `/api/admin` endpoints (Section 6) but does not describe health check endpoints. Container orchestrators (Kubernetes, ECS) need health and readiness probes. A health check should verify: the FastAPI process is running, the SDK can be initialized, the API key is valid, and the plugin registry is loaded.

### 2.5 Testing Strategy

Section 6 lists a test directory structure with unit, integration, and e2e folders. However, the testing strategy is not described.

**Testing plugins in isolation.** How does a plugin developer test their plugin without running the full platform? Is there a test harness, a mock registry, or a plugin development kit? Without this, plugin development will be slow and error-prone.

**Integration testing with the real SDK.** The SDK spawns a subprocess that calls the Claude API. Integration tests either need real API keys (expensive, slow, non-deterministic) or a mock SDK. The architecture does not address this tension. The `conftest.py` is listed but its fixtures are not described.

**E2E testing.** `test_chat_flow.py` is listed but there is no discussion of how to test the WebSocket flow end-to-end. This requires a running backend, a WebSocket client, and either real or mocked SDK responses.

### 2.6 Deployment

**Docker configuration.** Section 6 lists `docker/Dockerfile` and `docker-compose.yml` but does not describe the container strategy. Key questions: What base image? How is the Claude Code CLI (bundled with the SDK) handled in the container? The CLI includes a Node.js runtime -- does the container need both Python and Node.js? How large is the resulting image? How are secrets injected?

**Environment management.** Section 8.1 lists environment variables but does not distinguish between development, staging, and production configurations. No `.env.example` file is listed in the project structure.

**Secret injection for containers.** In Kubernetes deployments, secrets should come from Kubernetes Secrets or a vault service, not environment variables in the pod spec. The architecture does not describe a secret injection pattern compatible with container orchestration.

### 2.7 Database and Persistence

Section 3.4 mentions "the platform stores session metadata in its own database" and Section 8.1 defaults to SQLite. Beyond session metadata, what else needs persistence?

**Plugin state persistence.** Section 5.2 describes a registration lifecycle where plugins transition through states (registered, configured, active, errored). Is this state persisted across server restarts? If the Plugin Registry is purely in-memory (Section 3.2), all plugins must be re-discovered and re-activated on restart. Operator-provided configuration (API keys, settings from Section 5.2 step 4) would be lost.

**User preferences.** The architecture does not mention user preferences (e.g., preferred model, enabled plugins per user, theme). If these are needed, where are they stored?

**Audit trail.** For a platform executing tools on behalf of users, an audit trail (who requested what tool, when, with what input, what result) is often required. No audit persistence is described.

---

## 3. Design Challenges

### 3.1 Plugin System: Over-Engineered or Under-Engineered?

The plugin system is the architecture's most ambitious feature. For the stated use case (a pluggable Claude Code web platform), the four-type taxonomy with manifest-based registration is well-targeted. However, several tensions exist:

**The plugin UI injection model is under-specified.** Section 4.2 describes dynamically loading React components from plugin-provided JavaScript modules using `lazy()` and `Suspense`. This raises immediate questions: What is the build pipeline for plugin UI? Must plugins be pre-built as JavaScript bundles, or can they be TypeScript that the platform compiles? How are plugin dependencies managed (what if two plugins depend on different versions of a charting library)? Without a clear answer, plugin developers will struggle to create UI components.

**Plugin versioning and compatibility.** The manifest includes a `version` field (Section 5.1), but there is no discussion of compatibility ranges, breaking changes, or migration paths. When the platform upgrades and changes its manifest schema or API, how do existing plugins adapt?

**Plugin isolation is weak for tool plugins.** Section 5.4 acknowledges that tool plugins run in-process (as `@tool` functions). A malicious or buggy tool plugin can: crash the Python process, block the async event loop, consume unbounded memory, or access other plugins' state. There is no sandboxing for in-process Python code. The SDK sandbox (Section 3.8) only applies to commands executed by the CLI, not to the Python tool functions themselves.

### 3.2 Can a Bad MCP Server Crash the System?

Section 5.4 claims MCP server crashes are handled by the SDK. This is partially true -- the SDK will report the error -- but the architecture does not address:

- An MCP server that hangs indefinitely (consuming a subprocess slot without producing results)
- An MCP server that produces extremely large outputs (consuming memory in the CLI subprocess)
- An MCP server that responds slowly, degrading the user experience for all tools in the same session

The architecture relies on the SDK to manage MCP lifecycle, but the SDK does not provide per-server timeouts or circuit breakers. These would need to be implemented at the platform level.

### 3.3 State Synchronization Between Frontend and Backend

Section 4.5 states the frontend uses `useReducer` with a context provider. The reducer handles all WebSocket messages and maintains the chat state. But several synchronization challenges are unaddressed:

- **Reconnection state recovery.** When the WebSocket reconnects after a disconnect, how does the frontend recover its state? Does the backend replay missed messages? Is there a message sequence number or offset protocol? Section 4.5 mentions "buffering outgoing messages" during interruption but says nothing about recovering inbound state.

- **Optimistic updates.** When the user sends a message, does the frontend optimistically render it, or wait for server confirmation? Optimistic rendering creates better UX but introduces state divergence if the server rejects the message.

- **Multiple tabs.** If a user opens two browser tabs for the same session, both WebSocket connections will receive messages. The architecture does not address this conflict.

### 3.4 WebSocket vs SSE

Section 1 states "all communication uses WebSocket streaming." This is a reasonable choice for bidirectional communication (user messages + interrupt commands going upstream), but it is worth noting the tradeoffs:

**SSE advantages for this use case:** Simpler to implement, works through HTTP/2, better proxy compatibility, automatic reconnection built into the browser EventSource API, and the server-to-client direction is the high-volume path (streaming tokens). The upstream path (user messages, interrupt commands) could use standard REST endpoints.

**WebSocket advantages:** True bidirectional streaming, lower latency for upstream messages, single connection.

The architecture does not discuss why WebSocket was chosen over SSE, or whether a hybrid approach (SSE for streaming + REST for commands) was considered. Given that React 19 and the broader ecosystem have strong SSE support, this decision deserves explicit rationale.

### 3.5 Subprocess Memory and CPU Implications

Section 9 estimates 1 GiB RAM and 1 CPU per SDK instance based on "official docs." However, real-world evidence contradicts this optimistic estimate:

- GitHub issue anthropics/claude-code#13126 documents RSS growth to 24-26 GB in extended sessions
- GitHub issue anthropics/claude-code#5771 reports 100% CPU usage
- GitHub issue anthropics/claude-agent-sdk-python#333 reports 20-30s initialization time
- GitHub issue anthropics/claude-code#22968 reports memory leaks in long-running sessions

The 1 GiB figure may represent the minimum for a short, simple session. For a web platform where sessions may last hours and involve complex tool executions, the real resource requirement per session could be 2-4 GiB or more. The architecture should present these figures with appropriate caveats and recommend session duration limits as a mitigation.

---

## 4. SDK Reality Check

### 4.1 ClaudeAgentOptions Usage

The proposed `ClaudeAgentOptions` usage in Section 8.4 is largely correct. Verified against the SDK:

- `model`, `max_turns`, `max_budget_usd`, `sandbox`, `permission_mode`, `include_partial_messages`, `setting_sources`, `cwd`, `env` -- all valid parameters confirmed via Context7 MCP and PyPI docs.
- `can_use_tool` accepts an async callback of the correct signature.
- `mcp_servers` accepts both dict configs and `McpSdkServerConfig` instances.

**One concern:** The document states `permission_mode` is set to `"default"` (Section 8.4). The `"default"` mode prompts the user for permission on each tool use. In a web platform context, there is no interactive terminal to prompt. The `can_use_tool` callback should return the permission decision programmatically. However, the SDK documentation is unclear on whether `"default"` mode with a `can_use_tool` callback skips the terminal prompt. This needs testing. The safer choice may be `"acceptEdits"` combined with the `can_use_tool` callback for deny-only decisions, or relying entirely on the `PreToolUse` hook for permission logic.

### 4.2 Hooks and Subagents

**Hooks work as described.** The `HookMatcher`, hook events, and permission decision return format match the SDK documentation. The hook timeout parameter is real.

**Subagents work as described with one caveat.** The `AgentDefinition` parameters, the `Task` tool requirement, and the no-nested-subagents constraint are all accurate. The caveat: the document says subagent sessions can be "resumed independently" (Section 3.7). While `session_id` and `agentId` are exposed, the SDK's documentation on resuming subagent sessions specifically is sparse. This capability should be verified experimentally before being promised as a platform feature.

### 4.3 can_use_tool Callback

The proposed permission model (Section 3.9) uses `can_use_tool` as the second layer. The SDK documentation confirms this callback receives `(tool_name: str, input_data: dict, context: ToolPermissionContext)` and returns `PermissionResultAllow` or `PermissionResultDeny`. The architecture's description of the callback signature as `(tool: str, input: dict) -> bool` (Section 3.9, layer 2) appears to use a simplified signature. The actual SDK signature uses named types, not bare bool returns. The `PermissionResultAllow` can also return `updated_input` to modify the tool's input, which is a powerful capability not mentioned in the architecture.

### 4.4 Concurrent Session Handling

The SDK does not provide built-in concurrent session management. Each `ClaudeSDKClient` instance is independent. The architecture correctly places this responsibility on the `SessionManager` (Section 3.4). However, the SDK stores sessions on disk at `~/.claude/projects/`, which means multiple `ClaudeSDKClient` instances on the same server share the filesystem namespace. Session ID collisions are unlikely (they are UUIDs) but concurrent file access to the shared `.claude/` directory could cause contention or corruption, especially during the cache accumulation described in GitHub issue anthropics/claude-code#13126.

---

## 5. Frontend Gaps

### 5.1 React 19 Server Components

Section 4.4 correctly notes that server components are "not used in v1" because the frontend is a client-side SPA. This is a reasonable decision for a WebSocket-driven chat interface. Server components would add complexity without clear benefit for a real-time streaming UI. The mention of a potential future Next.js migration path is appropriate.

### 5.2 State Management Approach

Section 4.5 uses `useReducer` with a context provider. For a chat application receiving high-frequency streaming updates, this has performance implications:

- Context value changes trigger re-renders for all consumers. If the entire chat state is in one context, every token update re-renders the entire component tree.
- The architecture does not mention memoization or state slicing strategies.

A more scalable approach would be a dedicated state management library like Zustand, which supports state selectors (components only re-render when their selected slice changes). Alternatively, splitting the context into separate providers for different state domains (messages, session metadata, plugin state) would mitigate the re-render problem.

Section 4.3 mentions using `useTransition` for streaming updates, which is correct for deprioritizing non-urgent updates. But `useTransition` defers rendering -- it does not prevent re-renders. The state management architecture needs more thought for scenarios with rapid token streaming (potentially 30+ tokens per second).

### 5.3 Accessibility (WCAG Compliance)

The architecture does not mention accessibility at all. For a chat UI, key accessibility concerns include:

- Screen reader compatibility for the message list (ARIA live regions for new messages)
- Keyboard navigation through messages and tool cards
- Focus management when new messages arrive (should focus move? configurable?)
- Color contrast for status indicators (streaming, executing, error states)
- Reduced motion preferences for animations (tool card state transitions, streaming cursor)

### 5.4 Mobile Responsiveness

No mention of mobile support. The component hierarchy (Section 4.1) includes a collapsible `SidePanel`, suggesting awareness of space constraints, but responsive breakpoints, touch interactions, and mobile-specific layouts are not discussed.

### 5.5 Plugin UI Injection and React's Component Model

Section 4.2 describes loading plugin UI components via `lazy()` and `Suspense`. Several technical challenges are unaddressed:

- **Dependency isolation.** Plugin components loaded via dynamic import share the React instance. If a plugin imports React internally (bundled in its JS module), version mismatches can cause cryptic errors. The platform needs to externalize React from plugin bundles.

- **Style isolation.** Plugin components share the global CSS scope. A plugin that uses generic class names (e.g., `.container`, `.button`) can break the main UI or other plugins. CSS Modules, Shadow DOM, or a scoping convention is needed.

- **Plugin component API.** What props does the platform pass to plugin components? How do plugins access the WebSocket connection to send custom messages? This API surface is undefined.

---

## 6. Missing from Architecture

### 6.1 API Versioning Strategy

The REST endpoints (`/api/plugins`, `/api/sessions`, `/api/admin`) have no versioning. When the API evolves, existing clients will break. A versioning strategy (URL prefix like `/api/v1/`, header-based, or content negotiation) should be defined before the first release.

### 6.2 Plugin Migration and Upgrade Path

When the platform releases a new version that changes the plugin manifest schema, how do existing plugins adapt? There is no migration tooling, schema versioning for manifests, or backward compatibility policy described.

### 6.3 Rate Limiting and Quotas

As noted in Section 2.1 (Security), there is no rate limiting. Beyond security, rate limiting is also a cost control mechanism. The `max_budget_usd` parameter (Section 8.4) caps per-session costs, but there is no per-user or per-tenant budget. A user who opens many sessions can exhaust the platform's API budget.

### 6.4 Multi-Tenant Considerations

Section 11 mentions multi-tenancy as a future concern but provides no design guidance. For even a simple multi-user deployment, tenant isolation questions arise immediately:
- Can users see each other's sessions?
- Can users see each other's plugin configurations?
- Are API keys shared across users or per-user?
- What is the authorization model (RBAC, ABAC)?

### 6.5 Internationalization (i18n)

The frontend component hierarchy (Section 4.1) includes hardcoded UI elements (Header, SettingsDrawer, PluginManager) with no mention of i18n support. Even if v1 is English-only, the architecture should note whether strings are externalized for future translation.

### 6.6 Documentation Generation from Plugin Manifests

Plugin manifests (Section 5.1) contain structured metadata (name, description, capabilities, config_schema). This metadata could auto-generate plugin documentation pages. The architecture lists `docs/plugin-guide.md` but does not describe automated documentation generation from manifest schemas.

### 6.7 Graceful Shutdown

When the server shuts down (for deployment or maintenance), active sessions have open WebSocket connections and running SDK subprocesses. The architecture does not describe a graceful shutdown protocol: notifying connected users, completing in-flight queries, or draining sessions before termination.

### 6.8 Cost Tracking and Reporting

The `ResultMessage` includes `cost_usd` (Section 3.3). The architecture mentions capturing this (Section 7.1) but does not describe aggregation, reporting, or cost alerting. For a platform that could cost hundreds of dollars per day in API calls, cost visibility is operationally critical.

---

## 7. Prioritized Recommendations

The following recommendations are ranked by impact, considering both the severity of the gap and the difficulty of addressing it post-implementation.

1. **Define and implement a subprocess lifecycle management strategy.** The 20-30s initialization time (GitHub issue #333) and memory accumulation (GitHub issue #13126) are the highest-risk technical challenges. Implement pre-warming of SDK instances, session duration limits (auto-cleanup after N minutes of inactivity), cache cleanup between sessions, and memory monitoring with proactive restart. Without this, the platform will have unacceptable latency and reliability. (Sections 3.1, 9)

2. **Add a comprehensive security design.** Define authentication (JWT with refresh tokens recommended), authorization (RBAC for admin/operator/user roles), CORS policy, rate limiting at both WebSocket and REST layers, CSRF protection for REST endpoints, and input sanitization for user messages. Add the `UserPromptSubmit` hook to the hooks table for prompt-level guardrails. Encrypt plugin secrets at rest. (Sections 3.3, 3.5, 3.9, 5.2)

3. **Design the error recovery path for subprocess crashes.** Define exactly what happens when `ClaudeSDKClient` raises `ProcessError` or `CLIConnectionError`. Implement session resume after crash, user notification via WebSocket, automatic cache cleanup post-crash, and circuit breaker for API outages. Document the recovery flow as clearly as the happy path. (Section 3.1, 5.4)

4. **Add observability infrastructure.** Define structured logging (JSON format with correlation IDs), key platform metrics (session latency, tool execution counts, error rates, API costs), health check endpoints for container orchestration, and stderr capture from the CLI subprocess. Consider OpenTelemetry for distributed tracing through the WebSocket-to-SDK-to-API chain. (Not currently addressed)

5. **Fix the can_use_tool callback signature.** The architecture uses `(tool: str, input: dict) -> bool` but the SDK uses `(tool_name: str, input_data: dict, context: ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`. Adopt the correct signature and leverage `PermissionResultAllow(updated_input=...)` for input sanitization, not just allow/deny. (Section 3.9)

6. **Address frontend state management performance.** Replace or augment `useReducer` + context with a solution that supports state selectors (Zustand is the strongest candidate for this use case). The current approach will cause full-tree re-renders on every streaming token, degrading UI performance during active conversations. (Section 4.5)

7. **Define the plugin UI build pipeline.** Specify how plugin developers build, bundle, and test React components. Define the plugin component API (props, hooks, WebSocket access). Address dependency and style isolation. Without this, the plugin UI slot system described in Section 4.2 is unimplementable. (Section 4.2)

8. **Add API versioning.** Prefix all REST endpoints with `/api/v1/`. This is trivial to implement now and painful to retrofit later. (Section 6)

9. **Verify permission_mode behavior.** Test whether `permission_mode="default"` with a `can_use_tool` callback works correctly in a non-interactive (no TTY) environment. If it still attempts terminal prompts, switch to `"acceptEdits"` with hook-based enforcement. (Section 8.4)

10. **Add graceful shutdown protocol.** Implement SIGTERM handling that drains active WebSocket connections, completes or interrupts in-flight queries, and cleanly destroys SDK subprocesses. This is required for zero-downtime deployments in Kubernetes. (Not currently addressed)

11. **Add session duration limits and cache management.** Based on the memory growth evidence from GitHub issues, implement maximum session duration (e.g., 4 hours), automatic cache cleanup between sessions, and memory monitoring per subprocess. This is especially critical for the single-server deployment model in Section 9. (Section 9)

12. **Add accessibility requirements to the frontend design.** At minimum: ARIA live regions for the message list, keyboard navigation, focus management, and WCAG AA color contrast. This should be a design requirement, not an afterthought. (Section 4)

13. **Add cost tracking and alerting.** Aggregate per-session `cost_usd` into per-user and platform-wide totals. Provide a cost dashboard in the admin API. Alert when spend exceeds configurable thresholds. This prevents bill shock. (Section 3.3, 8.1)

14. **Describe the testing strategy.** Define how to test: plugins in isolation (mock registry), integration with the SDK (recorded responses or a test API key with budget cap), WebSocket flows (test client), and frontend components (React Testing Library). Without this, the test directory in Section 6 is structure without substance. (Section 6)

15. **Add plugin versioning and manifest migration.** Define a manifest schema version field, compatibility ranges for platform versions, and a migration tool or instructions for when the schema changes. This protects the plugin ecosystem from breaking changes. (Section 5.1)

---

## Research References

- [Claude Agent SDK - PyPI](https://pypi.org/project/claude-agent-sdk/) (v0.1.31, confirmed 2026-02-06)
- [Claude Agent SDK Python - GitHub](https://github.com/anthropics/claude-agent-sdk-python)
- [Performance Issues with Server-side Multi-instance Deployment - Issue #333](https://github.com/anthropics/claude-agent-sdk-python/issues/333) (20-30s init, no pooling)
- [Claude Code OOM Issue - Issue #13126](https://github.com/anthropics/claude-code/issues/13126) (2.5GB to 24-26GB RSS, cache accumulation)
- [High CPU and Memory in Long Sessions - Issue #22968](https://github.com/anthropics/claude-code/issues/22968)
- [100% CPU and Memory - Issue #5771](https://github.com/anthropics/claude-code/issues/5771)
- [Claude Agent SDK Docs - Python](https://platform.claude.com/docs/en/agent-sdk/python)
- [Claude Agent SDK Docs - Hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Claude Agent SDK Docs - Subagents](https://platform.claude.com/docs/en/agent-sdk/subagents)
- [Claude Agent SDK Docs - Structured Outputs](https://platform.claude.com/docs/en/agent-sdk/structured-outputs)
- [React 19 Release Blog](https://react.dev/blog/2024/12/05/react-19)
- [SSE vs WebSocket Comparison - Ably](https://ably.com/blog/websockets-vs-sse)
- Context7 MCP: `/anthropics/claude-agent-sdk-python` (40 snippets, High reputation)
- Context7 MCP: `/websites/platform_claude_en_agent-sdk` (624 snippets, High reputation)
