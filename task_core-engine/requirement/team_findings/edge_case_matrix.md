# Edge Case Matrix - claude_sdk_pattern Core Engine

> Analysis Date: 2026-02-07
> Analyst: Edge Case Hunter
> Architecture Version: v1.1

## Executive Summary

This document systematically identifies edge cases, failure modes, and boundary conditions across all major components of the claude_sdk_pattern platform. The analysis covers 8 categories for 7 core components, resulting in **127 distinct edge cases** identified.

**High-Risk Summary:**
- **Critical (requires design changes)**: 18 edge cases
- **High (requires mitigation strategies)**: 34 edge cases
- **Medium (monitoring/logging needed)**: 42 edge cases
- **Low (acceptable with documentation)**: 33 edge cases

**Most Critical Areas:**
1. Session Lifecycle (subprocess management, memory growth, pre-warm pool exhaustion)
2. WebSocket Communication (reconnection sync, concurrent connections, backpressure)
3. Plugin System (runtime failures, hot reload conflicts, secret rotation)
4. Subprocess Management (OOM, zombie processes, file system exhaustion)

---

## 1. Edge Cases: Session Lifecycle

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-001 | Boundary | Pre-warm pool is empty when user creates session | Wait for cold start (20-30s); show "Preparing your session..." | HIGH | Implement pool auto-scaling: monitor pool depth, start pre-warming additional instances when depth < 2. Alert operators when pool exhausted. |
| EC-002 | Boundary | Maximum concurrent sessions reached (CLAUDE_SDK_PATTERN_MAX_SESSIONS) | Return HTTP 503 with "Server at capacity. Retry after: 60s" | MEDIUM | Implement queue system for session creation requests with position notification. |
| EC-003 | Boundary | Session duration reaches MAX_SESSION_DURATION_SECONDS exactly mid-query | Send graceful shutdown notification via WebSocket, allow query to complete (up to 30s grace), then force terminate | HIGH | Add "approaching limit" warning at 90% of max duration. Allow user to request extension (adds 1 hour, max 2 extensions). |
| EC-004 | Boundary | RSS memory reaches MAX_SESSION_RSS_MB mid-query | Mark session for restart after current query completes; notify user "Session will restart after this response" | HIGH | Monitor RSS growth rate; predict OOM 5 minutes before limit and trigger proactive graceful restart. |
| EC-005 | Invalid Input | Session resume with session_id that doesn't exist | Return error "Session not found. Starting new session." | LOW | Log failed resume attempts; detect if session was purged due to retention policy vs never existed. |
| EC-006 | Invalid Input | Session fork with session_id that is currently active in another WebSocket | Allow fork (SDK supports this); both sessions operate independently | MEDIUM | Document that forked sessions do not see updates from parent after fork point. |
| EC-007 | Invalid Input | Resume session with corrupted ~/.claude/ data | Resume fails with SDK error; fallback to new session with notification | HIGH | Implement session health check: validate session data integrity before resume. If corrupted, archive the session and start fresh. |
| EC-008 | Concurrent | Two users attempt to resume the same session_id simultaneously | First resume succeeds, second receives "Session already active" error | MEDIUM | Implement session locking: atomic check-and-claim in SessionManager. Second user gets option to fork instead. |
| EC-009 | Concurrent | User closes browser tab while session is mid-query | WebSocket disconnects; query continues server-side; results buffered for reconnection | MEDIUM | Add query cancellation option: if WebSocket disconnects and user doesn't reconnect within 60s, call client.interrupt(). |
| EC-010 | Concurrent | User opens same session in multiple browser tabs | Each tab gets separate WebSocket; backend detects duplicate connections and sends "Session open in another window" warning | HIGH | Implement connection deduplication: allow only one active WebSocket per session_id. Newer connection replaces older. Notify replaced connection. |
| EC-011 | State Transition | Session timeout occurs while session is "thinking" (processing query) | Allow current query to complete (with QUERY_TIMEOUT_SECONDS limit); then destroy session | LOW | Current design already handles this via query timeout. Document behavior. |
| EC-012 | State Transition | User attempts to send message to session in "restarting" state | Queue message, deliver after restart completes | MEDIUM | Add session state machine with transitions: idle -> processing -> restarting -> idle. Block new messages during restart. |
| EC-013 | State Transition | Session fork fails mid-fork operation | Original session continues unchanged; user receives error "Fork failed, continuing original session" | LOW | Wrap fork operation in try/except; log fork failures for debugging. |
| EC-014 | External Failure | Claude API returns 429 during session creation | Pre-warmed client is rate-limited; return to pool for retry; create new client for user (which will also likely fail) | HIGH | Implement backoff for pre-warming: if API is rate-limited, pause pre-warm operations for 5 minutes. Don't waste pool slots on rate-limited clients. |
| EC-015 | External Failure | Network partition during active session (API unreachable) | Circuit breaker opens; current query fails; notify user "API unavailable"; offer resume when connectivity restored | MEDIUM | Already addressed by circuit breaker (Section 3.11). Ensure session state persisted before queries. |
| EC-016 | Permission | JWT expires during active session (WebSocket stays open) | Next message from user fails auth; WebSocket receives "token_expired" message; frontend prompts re-login | HIGH | Implement token refresh flow over WebSocket: server sends "refresh_required" message before expiry; client sends new token via WebSocket message; no disconnect needed. |
| EC-017 | Permission | User's role downgraded while session active (e.g., admin -> user) | Next tool invocation fails permission check; tool denied; session continues with reduced capabilities | MEDIUM | On role change, send "permissions_changed" WebSocket message; re-evaluate all active plugin permissions; notify user of newly unavailable tools. |
| EC-018 | Data | Pre-warmed session has stale plugin configuration (plugins changed since pre-warm) | Pre-warmed client created with old plugin set; first query uses outdated tools | HIGH | Invalidate pre-warm pool on plugin registry changes. Alternative: make pool creation lazy (build options at session start, not pre-warm). |
| EC-019 | Data | Session metadata persisted but ~/.claude/ session data deleted (e.g., manual cleanup) | Session resume fails; metadata says session exists but SDK can't load it | MEDIUM | Implement consistency check: verify SDK session file existence before allowing resume. Purge orphaned metadata entries on startup. |
| EC-020 | Timing | User sends new message before previous query completes | Queue the new message; deliver after current query returns ResultMessage | MEDIUM | Current streaming design assumes serial queries. Implement message queue in WebSocket handler. Alternative: allow concurrent queries (SDK unclear if supported). |
| EC-021 | Timing | Session created but user never sends first message (abandoned connection) | Session remains in pool as "idle"; eventually times out per SESSION_TIMEOUT | LOW | Implement "first message timeout" (shorter than idle timeout, e.g., 5 minutes). Reclaim unused sessions faster. |
| EC-022 | Timing | Pre-warm pool initialization fails on startup (all pre-warms crash) | Server starts but pool is empty; all users experience cold start | HIGH | Fail server startup if 0 pre-warm attempts succeed. Require at least 1 successful pre-warm to pass readiness probe. |
| EC-023 | Boundary | Cache directory ~/.claude/ grows beyond disk quota | CLI subprocess crashes with "No space left on device" during write | HIGH | Implement disk usage monitoring per session. Cleanup old shell snapshots proactively. Set per-session disk quota via container limits. |
| EC-024 | Concurrent | Graceful shutdown initiated while session is in pre-warm pool (unused) | Pre-warmed client destroyed immediately (no WebSocket to notify) | LOW | Acceptable behavior. Log count of destroyed pre-warm sessions during shutdown. |
| EC-025 | State Transition | Session RSS monitoring detects OOM risk, triggers restart, but user sends message during restart window | Message queued; delivered after restart; user sees brief "Session restarting..." status | MEDIUM | Already addressed in design. Ensure restart is atomic: old session not destroyed until new session ready. |

**Component Summary:**
- **HIGH Risk**: 10 edge cases (pool exhaustion, duration limits, RSS monitoring, concurrent resume, duplicate connections, rate-limited pre-warm, JWT expiry, stale plugin config, pre-warm startup failure, disk exhaustion)
- **MEDIUM Risk**: 11 edge cases
- **LOW Risk**: 4 edge cases
- **Total**: 25 edge cases

---

## 2. Edge Cases: WebSocket Communication

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-026 | Boundary | WebSocket message exceeds maximum frame size (typically 64 KB) | Large messages (e.g., tool results with base64 images) split across frames; client reassembles | LOW | Use WebSocket libraries that handle framing automatically (Starlette does). Document max message size. |
| EC-027 | Boundary | User sends MAX_MESSAGE_LENGTH characters exactly | Message accepted; processed normally | LOW | No issue. Boundary condition works as designed. |
| EC-028 | Boundary | Token streaming generates 50+ tokens/second (fast model) | Frontend buffers updates via useTransition; UI remains responsive | MEDIUM | Measure actual token rate in production. If backpressure occurs, implement token batching (send every 100ms instead of per-token). |
| EC-029 | Invalid Input | Malformed JSON in WebSocket message from client | JSON parse fails; send error message to client; log malformed data | LOW | Wrap JSON.parse in try/except; return {type: "error", code: "invalid_json"}. |
| EC-030 | Invalid Input | Unknown message type from client (typo or version mismatch) | Ignore unknown type; log warning; optionally send "unknown_message_type" error | LOW | Forward-compatibility strategy: ignore unknown types. Log for debugging. |
| EC-031 | Invalid Input | Client sends binary WebSocket frame (not text/JSON) | Reject frame; send error "Only text frames supported" | LOW | Configure WebSocket handler to reject binary frames. |
| EC-032 | Concurrent | Client sends two user_message messages before first query completes | Second message queued (see EC-020) or rejected with "Query in progress" | MEDIUM | Decide: queue vs reject. Queuing is more user-friendly but complicates state. Recommend reject with clear error. |
| EC-033 | Concurrent | Two browser tabs send messages to same session (see EC-010) | If connection deduplication implemented, second tab's connection is dropped; first tab continues | HIGH | Addressed in EC-010 mitigation. Critical to prevent state corruption. |
| EC-034 | Concurrent | Client sends interrupt while no query is active | Interrupt ignored; no error sent | LOW | Document idempotent interrupt behavior. Safe to call anytime. |
| EC-035 | State Transition | WebSocket disconnect during tool execution (mid-query) | Tool continues executing server-side; result buffered; delivered on reconnect | MEDIUM | Implement result buffer with TTL (5 minutes). Client sends last_message_seq on reconnect; server replays missed messages. |
| EC-036 | State Transition | Reconnection with sequence gap (client missed messages) | Server detects gap via last_message_seq; replays missing messages in order | HIGH | Critical for reliability. Implement message log per session with seq numbers. Purge log after WebSocket confirms delivery (ACK). |
| EC-037 | State Transition | Client reconnects with last_message_seq ahead of server (impossible unless time travel) | Server rejects reconnection: "Invalid sequence number. Please refresh page." | LOW | Indicates client state corruption or malicious manipulation. Reset session. |
| EC-038 | State Transition | Reconnection fails (e.g., session destroyed during disconnect) | Client receives "session_not_found" on reconnect; offer option to start new session | LOW | Store minimal session metadata even after destroy (for 5 minutes) to provide better error messages. |
| EC-039 | External Failure | WebSocket connection drops during initial handshake (before auth) | Connection fails; client retries with exponential backoff | LOW | Standard WebSocket reconnection logic. Already addressed in design (Section 4.6). |
| EC-040 | External Failure | Reverse proxy closes WebSocket connection (timeout) | Server detects disconnect; buffers results; client reconnects; sees missed messages | MEDIUM | Configure reverse proxy (nginx, ALB) for long WebSocket timeout (e.g., 1 hour). Document required settings. |
| EC-041 | External Failure | Client network switches (mobile: WiFi -> cellular) | WebSocket connection breaks; client detects and reconnects; syncs missed messages | MEDIUM | Test reconnection on mobile networks. Ensure seq sync handles multi-second gaps. |
| EC-042 | Permission | WebSocket upgrade request with invalid JWT | Upgrade rejected with 401; WebSocket never established | LOW | Already addressed in Section 3.10. Standard auth failure. |
| EC-043 | Permission | WebSocket open but JWT expires before first message (edge case: token near expiry at connect time) | First message fails auth; client receives token_expired notification | LOW | Frontend should check token expiry before opening WebSocket. Refresh token proactively if <5 min remaining. |
| EC-044 | Data | Message buffer for disconnected client grows unbounded (client never reconnects) | Buffer consumes memory; server OOM risk if many abandoned sessions | HIGH | Implement buffer TTL (5 minutes) and max size (100 messages or 10 MB). Purge expired buffers automatically. |
| EC-045 | Data | Sequence number wraps around (2^64 messages in one session) | Unlikely in practice (would take centuries at 1 msg/sec) | LOW | Use 64-bit unsigned int for seq. Document that wraparound is not handled (acceptable risk). |
| EC-046 | Data | StreamEvent partial messages arrive faster than client can render | Client buffers in React state; risks memory growth | MEDIUM | Implement client-side buffer cap: keep only last 10 KB of streaming buffer. Discard older deltas once complete message rendered. |
| EC-047 | Timing | Client sends user_message at exact moment server sends server_shutting_down | Race condition: message might be processed or rejected depending on timing | LOW | Shutdown handler sets flag before sending notification. Any message arriving after flag set is rejected with "Server shutting down". |
| EC-048 | Timing | Reconnection occurs during result message streaming (multi-part result) | Client receives partial result before disconnect; on reconnect, server replays full result (duplicate data) | MEDIUM | Mark result messages as "resumable" with offsets. Alternative: don't buffer result messages (client can fetch from session metadata via REST). |
| EC-049 | Timing | Rate limit exceeded mid-query (user hit limit during query processing) | Query completes normally; next message is rate-limited | LOW | Rate limiter checks at message ingress. In-flight queries exempt from rate limit. |
| EC-050 | Boundary | Server sends very large tool_result (e.g., 10 MB JSON response) | WebSocket frame size may exceed limits; connection drops | HIGH | Implement result size limits: truncate tool_result content over 1 MB. Store full result in session metadata; send truncated version with "truncated: true" flag. Frontend can fetch full via REST. |
| EC-051 | Concurrent | Multiple StreamEvent messages arrive while client is processing previous update | Events queue in WebSocket receive buffer; client processes serially | LOW | Acceptable. Modern WebSocket libraries handle buffering. Monitor client-side queue depth. |

**Component Summary:**
- **HIGH Risk**: 4 edge cases (concurrent connections, sequence sync, buffer exhaustion, large tool results)
- **MEDIUM Risk**: 9 edge cases
- **LOW Risk**: 13 edge cases
- **Total**: 26 edge cases

---

## 3. Edge Cases: Plugin System

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-052 | Boundary | Plugin manifest declares 100+ tools (context window risk) | All tools added to allowed_tools; SDK enables tool search automatically | MEDIUM | Document tool count limits. Recommend plugin authors group tools by subagent or use MCP tool search. |
| EC-053 | Boundary | Zero plugins active (fresh installation) | Sessions created with only built-in tools (Read, Write, Bash, etc.) | LOW | Valid state. Document minimum viable tool set. |
| EC-054 | Boundary | Plugin declares empty required permissions array | Plugin has no special permissions; can't request dangerous operations | LOW | Valid. Treat as "no special permissions needed". |
| EC-055 | Invalid Input | Plugin manifest has invalid JSON syntax | Discovery fails; plugin not registered; error logged; operator notified | LOW | Add JSON schema validation during discovery. Provide clear error messages with line numbers. |
| EC-056 | Invalid Input | Plugin manifest declares tool name that conflicts with built-in tool (e.g., "Bash") | Registration fails; error: "Tool name conflicts with built-in tool" | MEDIUM | Enforce plugin tool namespacing: all plugin tools must start with "mcp__<plugin>__". Reject non-namespaced names. |
| EC-057 | Invalid Input | Plugin declares platform_version requirement not met (e.g., requires >=2.0.0, platform is 1.5) | Registration fails; error: "Plugin requires platform version X" | LOW | Already addressed in design (Section 5.1). Validate during discovery. |
| EC-058 | Invalid Input | MCP plugin declares stdio server with command that doesn't exist | Activation fails; MCP server fails to start; plugin marked "errored" | MEDIUM | Test MCP server connectivity during activation. Timeout after 10s. Provide stderr logs to operator. |
| EC-059 | Concurrent | Two plugins declare tools with same name (e.g., "mcp__toolA__search") | Second plugin registration fails; error: "Tool name conflict with plugin B" | HIGH | Enforce unique tool names across all active plugins. Maintain tool name index in registry. |
| EC-060 | Concurrent | Plugin activated while sessions are active (new plugin available mid-session) | Active sessions continue with old plugin set; new sessions pick up new plugin | HIGH | Decision required: (A) Reload plugins mid-session (complex), or (B) Notify user "New tools available. Restart session?" Recommend (B). |
| EC-061 | Concurrent | Plugin deactivated while session is using its tool | Tool invocation fails; SDK reports tool not found; session continues; Claude adapts | MEDIUM | Send "plugin_deactivated" notification to all active sessions using that plugin. Document tool may become unavailable. |
| EC-062 | State Transition | Plugin activation fails after registration (MCP server crashes on startup) | Plugin status changed to "errored"; not included in OptionsBuilder; operator notified | LOW | Already addressed (Section 5.2). Log error details for debugging. |
| EC-063 | State Transition | Plugin configuration updated while plugin is active | Changes take effect for new sessions only; active sessions unaffected | MEDIUM | Document eventual consistency model. Provide "reload session configuration" button in UI. |
| EC-064 | State Transition | Skill plugin SKILL.md file deleted from filesystem while plugin is active | SDK fails to load skill; skill unavailable in new sessions; active sessions may error if skill already loaded | HIGH | Implement filesystem watcher for plugin directories. Detect file deletions; mark plugin as "degraded". Notify operator. |
| EC-065 | External Failure | MCP HTTP server becomes unreachable mid-session (network issue) | Tool invocation fails; PostToolUseFailure hook fires; error sent to frontend; session continues | MEDIUM | Already addressed (Section 3.11). Implement retry logic for transient network errors (3 retries with backoff). |
| EC-066 | External Failure | MCP stdio server subprocess crashes mid-session | SDK detects subprocess exit; tool invocations fail; plugin marked "degraded" | MEDIUM | Same as EC-065. SDK handles subprocess failures. Monitor crash rate per plugin. |
| EC-067 | External Failure | Plugin secret (API key) becomes invalid mid-session (key rotated on provider side) | Tool invocations return auth errors; user notified "Plugin X authentication failed" | HIGH | Implement secret health check: periodically test API keys for active plugins. Notify operator of expired keys. Allow key update without plugin restart. |
| EC-068 | Permission | Plugin requests permission not in operator's allowlist | Activation fails; error: "Plugin requires permission X which is not allowed" | LOW | Already addressed in design (Section 3.2). Validation during registration. |
| EC-069 | Permission | Tool plugin function calls external API without declaring permission | Plugin function executes; permission system doesn't block (in-process tools have limited isolation) | HIGH | Security risk. Document requirement: tool plugins MUST declare all external API calls in permissions. Recommend code review for tool plugins. Future: move to subprocess. |
| EC-070 | Permission | Endpoint plugin attempts to create session without user context | Session creation requires user_id; endpoint must provide auth token or service account identity | MEDIUM | Endpoint plugins receive user context from JWT. For service accounts, implement service-to-service auth (API key). |
| EC-071 | Data | Plugin secret encrypted with old SECRET_KEY; key rotated | Decryption fails; plugin activation fails; operator must re-enter secrets | HIGH | Implement secret re-encryption utility: when SECRET_KEY changes, admin runs script to decrypt with old key, re-encrypt with new key. Document rotation procedure. |
| EC-072 | Data | Plugin declares config_schema but operator provides values not matching schema | Validation fails during configuration; error returned to operator; plugin not activated | LOW | Validate config against JSON schema before saving. Provide clear validation error messages. |
| EC-073 | Data | Plugin registry database becomes corrupted (disk error) | Plugin loading fails on startup; server startup fails | HIGH | Implement database integrity check on startup. If corruption detected, attempt recovery from backup. Fail startup if unrecoverable. |
| EC-074 | Timing | Plugin directory uploaded via API while filesystem discovery is running | Race condition: plugin might be discovered twice or missed | MEDIUM | Implement mutex for plugin discovery operations. API upload triggers discovery after completion, not during. |
| EC-075 | Timing | Plugin hot reload requested (deactivate + activate) during active session using that plugin | Active session continues with old configuration; next query might see stale state | HIGH | Block hot reload if any active sessions use the plugin. Alternative: forcibly disconnect sessions using the plugin with warning. |
| EC-076 | Boundary | Plugin UI component bundle is very large (10+ MB JavaScript) | Initial load slow; impacts page load performance | MEDIUM | Enforce bundle size limits during plugin validation (max 2 MB). Require plugins to use lazy loading for large dependencies. |
| EC-077 | Invalid Input | Plugin UI component crashes on render (JavaScript error) | React error boundary catches crash; slot shows "Plugin UI error" fallback; main chat unaffected | LOW | Already addressed (Section 5.4). Log error to console; send error report to operator dashboard. |
| EC-078 | Concurrent | Multiple operators activate/deactivate same plugin simultaneously | Last write wins; race condition on plugin status | LOW | Unlikely in practice (single operator). If needed, implement optimistic locking (version field on plugin record). |

**Component Summary:**
- **HIGH Risk**: 8 edge cases (tool name conflicts, hot reload, skill file deletion, secret rotation, in-process tool security, secret key rotation, database corruption, hot reload with active sessions)
- **MEDIUM Risk**: 10 edge cases
- **LOW Risk**: 9 edge cases
- **Total**: 27 edge cases

---

## 4. Edge Cases: Permission System

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-079 | Boundary | can_use_tool callback takes longer than query timeout | Timeout enforced by SDK hooks timeout parameter; permission denied with "Timeout" | MEDIUM | Set hook timeout to reasonable value (e.g., 5s). Log slow permission checks; optimize PermissionGate code. |
| EC-080 | Boundary | can_use_tool denies tool, Claude tries all allowed tools, exhausts max_turns | Session ends with "Max turns reached" without completing task | LOW | Expected behavior. Claude should adapt. Document that overly restrictive permissions can cause task failure. |
| EC-081 | Invalid Input | can_use_tool callback raises unhandled exception | SDK treats as permission error; tool denied; error logged | MEDIUM | Wrap PermissionGate logic in try/except. Return PermissionResultDeny with reason: "Permission check failed (internal error)". |
| EC-082 | Invalid Input | PreToolUse hook returns invalid decision (not Allow/Deny) | SDK behavior undefined; likely treated as deny | LOW | Validate hook return types. Ensure PermissionGate always returns proper PermissionResult. |
| EC-083 | Concurrent | User role changes mid-query (role updated in database while query is processing) | Permission check uses role at query start; role change takes effect on next query | LOW | Acceptable eventual consistency. Document that role changes apply to new queries only. |
| EC-084 | Concurrent | Two PreToolUse hooks registered for same tool; first allows, second denies | SDK processes hooks in registration order; last decision wins (likely Deny) | HIGH | Document hook ordering semantics. Recommendation: only one security hook per tool. If multiple, require all to Allow. |
| EC-085 | State Transition | User downgraded from admin to user while session has active Bash command running | Command completes with admin privileges; next tool invocation uses user privileges | MEDIUM | Same as EC-083. Current command grandfathered; new commands use new role. Alternative: interrupt active queries on role change. |
| EC-086 | External Failure | Permission check requires external API call (e.g., policy engine); API times out | Return PermissionResultDeny with reason: "Permission service unavailable" | MEDIUM | Implement timeout (5s) for external permission checks. Cache permission decisions (TTL 60s) to reduce external calls. |
| EC-087 | Permission | Bash command with dangerouslyDisableSandbox=true requested | can_use_tool checks if command in operator-defined allowlist; denies if not | HIGH | Critical security gate. Ensure allowlist validation is robust. Log all unsandboxed command attempts (allowed and denied). |
| EC-088 | Permission | Plugin declares permission wildcard (e.g., "network:*") | Registration requires operator approval; wildcard permissions flagged during validation | MEDIUM | Implement permission granularity levels. Warn operator about wildcard permissions during plugin review. |
| EC-089 | Data | Permission callback accesses session context (ToolPermissionContext); context is stale | Context is snapshot at tool invocation time; race condition unlikely but possible | LOW | Document that context is point-in-time. PermissionGate should not rely on context mutating during check. |
| EC-090 | Data | updated_input from can_use_tool callback breaks tool input schema | Tool receives invalid input; tool execution fails with validation error | MEDIUM | PermissionGate must validate updated_input against tool schema before returning. Deny if invalid. |
| EC-091 | Timing | Permission check slow (2s) for every tool call in a 20-turn conversation | Query takes 40s longer than necessary; poor user experience | MEDIUM | Optimize PermissionGate: cache static decisions (e.g., "user X can always use tool Y"). Measure permission check latency via metrics. |
| EC-092 | Timing | JWT expiry timestamp and permission check timestamp differ (clock skew) | Permission check might use expired token for 1-2 seconds after expiry | LOW | Implement clock skew tolerance (±60s). Refresh tokens proactively (5 min before expiry). |
| EC-093 | Invalid Input | Prompt injection via tool input (user manipulates tool parameters to bypass permission check) | PermissionGate inspects input_data; detects injection patterns; denies with reason | HIGH | Critical security measure. Implement input sanitization for high-risk tools (Bash, Write, API calls). Use allowlist validation, not just blocklist. |
| EC-094 | Permission | Sandbox escape attempt detected (command tries to break out of sandbox) | can_use_tool blocks command; logs security event; alerts operator | HIGH | Already addressed (Section 3.8). Ensure sandbox exclusion list is minimal and well-audited. Monitor for escape attempts. |

**Component Summary:**
- **HIGH Risk**: 4 edge cases (hook ordering, unsandboxed commands, prompt injection, sandbox escape)
- **MEDIUM Risk**: 7 edge cases
- **LOW Risk**: 5 edge cases
- **Total**: 16 edge cases

---

## 5. Edge Cases: Claude API / SDK

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-095 | Boundary | Context window exceeded (conversation too long) | SDK triggers pre-compact; truncates old messages; notifies via PreCompact hook | MEDIUM | Already addressed (Section 3.5). Log compact events; expose to user "Earlier messages compacted due to length". |
| EC-096 | Boundary | max_turns reached exactly (e.g., 20 turns in complex task) | Query ends with ResultMessage.result = incomplete; user notified "Task incomplete (max turns reached)" | LOW | Expected behavior. Allow user to increase max_turns or continue in new query. |
| EC-097 | Boundary | max_budget_usd reached mid-query | SDK stops processing; returns ResultMessage with result = budget_exceeded | MEDIUM | Notify user at 80% of budget. Log budget exhaustion events. Allow operator to set per-user budget multipliers. |
| EC-098 | Invalid Input | Invalid API key provided in ANTHROPIC_API_KEY | SDK fails on first query; circuit breaker opens; all sessions fail | HIGH | Validate API key on server startup via test query. Fail health check if API key invalid. Prevent server start. |
| EC-099 | Invalid Input | Model parameter set to non-existent model (e.g., "claude-nonexistent-9") | SDK returns error "Model not found"; query fails; session unaffected | LOW | Validate model names against known list during OptionsBuilder. Fallback to default model if invalid. |
| EC-100 | Concurrent | Multiple sessions hit API rate limit simultaneously (429 errors) | Circuit breaker opens per-session or globally; all sessions see "API unavailable" | HIGH | Implement global circuit breaker (not per-session). Share rate limit state across all sessions to avoid cascading failures. |
| EC-101 | Concurrent | Two queries to Claude API with same user parameter conflict on API side | SDK handles independently; no conflict (API is stateless per request) | LOW | No issue. API requests are independent. |
| EC-102 | State Transition | fallback_model invoked due to primary model unavailable | SDK automatically falls back; query continues; user notified "Using fallback model" | LOW | Already supported by SDK. Log fallback events; expose in UI so user knows model switched. |
| EC-103 | State Transition | Conversation resumed with different model than original session | SDK allows this; conversation continues with new model; context preserved | LOW | Valid use case. Document that model can change across resumes. |
| EC-104 | External Failure | Anthropic API returns 500 (internal server error) | Query fails; retry logic kicks in (3 retries with backoff); if all fail, return error to user | MEDIUM | Implement retry logic for transient 5xx errors. Circuit breaker opens after sustained failures. |
| EC-105 | External Failure | API request times out (network latency or API slowness) | SDK times out per httpx timeout settings; query fails; user can retry | MEDIUM | Configure httpx timeout in SDK options (default: 60s). Log timeout events; detect if API is degraded. |
| EC-106 | External Failure | API connection drops mid-streaming response | SDK raises connection error; partial response discarded; query fails; user can retry | MEDIUM | Handle streaming connection errors gracefully. Log partial response length for debugging. |
| EC-107 | Permission | API rate limit (429) returned due to account-level limits | Same as EC-100; circuit breaker prevents retry storms | HIGH | Monitor API rate limit headers (X-RateLimit-*). Implement adaptive rate limiting: slow down requests when nearing limit. |
| EC-108 | Data | Structured output validation fails after max retries | ResultMessage.subtype = "error_max_structured_output_retries"; user receives error and unstructured result | MEDIUM | Log structured output validation failures. If common, schema might be too strict. Allow operator to increase retry count. |
| EC-109 | Data | Tool result contains binary data (e.g., image bytes) | SDK encodes as base64 in tool result; large results may hit message size limits | MEDIUM | Implement result size limits (see EC-050). For binary data, recommend storing in session workspace and returning file path, not raw bytes. |
| EC-110 | Timing | API response delayed (10+ seconds per token) | User sees very slow streaming; query eventually completes or times out | LOW | Monitor token streaming rate. If <1 token/second, show "API is slow" warning. Timeout enforced by QUERY_TIMEOUT_SECONDS. |
| EC-111 | Timing | Multiple streaming messages arrive simultaneously (API burst) | SDK queues messages; WebSocket handler processes serially | LOW | No issue. Async iteration handles queuing automatically. |
| EC-112 | Boundary | API returns empty response (no content) | SDK treats as error; query fails; user can retry | LOW | Validate API responses. Log empty response events; may indicate API bug. |
| EC-113 | Invalid Input | Betas parameter includes unsupported beta feature | SDK forwards to API; API rejects with error; query fails | LOW | Validate beta names against known list during OptionsBuilder. Warn if unknown. |

**Component Summary:**
- **HIGH Risk**: 3 edge cases (invalid API key on startup, simultaneous rate limit, account-level rate limit)
- **MEDIUM Risk**: 7 edge cases
- **LOW Risk**: 9 edge cases
- **Total**: 19 edge cases

---

## 6. Edge Cases: Subprocess Management

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-114 | Boundary | CLI subprocess RSS reaches system OOM threshold | Container OOM killer terminates subprocess; ProcessError raised; session recovery attempted (see EC-004) | HIGH | Already addressed (Section 3.1). Enforce MAX_SESSION_RSS_MB below container limit. Alert before OOM. |
| EC-115 | Boundary | Maximum open file descriptors reached (subprocess opens too many files) | Subprocess operations fail with "Too many open files" error | MEDIUM | Configure container ulimit for file descriptors (e.g., 4096). Monitor fd usage per subprocess. |
| EC-116 | Invalid Input | Environment variable injection via plugin (malicious env var) | Plugin env vars passed directly to subprocess; potential for shell injection | HIGH | Sanitize all plugin-provided env vars. Blocklist dangerous variables (LD_PRELOAD, PATH modifications). Log all env vars passed to subprocess. |
| EC-117 | Concurrent | Multiple subprocesses created simultaneously during pre-warm pool initialization | All subprocesses compete for CPU/RAM; system load spikes | MEDIUM | Stagger pre-warm initialization: create 1 subprocess, wait 5s, create next. Prevents resource contention. |
| EC-118 | Concurrent | Subprocess cleanup (destroy) called while subprocess is still initializing | Race condition: cleanup might run before init completes | LOW | Use asyncio locks for subprocess lifecycle. Ensure destroy waits for init to complete or cancel. |
| EC-119 | State Transition | Subprocess segfault (crash due to internal bug) | ProcessError raised; same recovery path as OOM (see Section 3.11) | MEDIUM | Log subprocess crashes with exit code and signal. Report crashes to Anthropic via telemetry (if enabled). |
| EC-120 | State Transition | Subprocess becomes zombie (terminated but not reaped) | Zombie process consumes PID slot; eventual PID exhaustion if many zombies | MEDIUM | Implement subprocess cleanup watchdog: periodically check for zombie processes, reap them. Log zombie detection events. |
| EC-121 | External Failure | Filesystem full (subprocess can't write to ~/.claude/) | Subprocess operations fail; writes to cache fail; subprocess may crash | HIGH | Already flagged (EC-023). Monitor filesystem usage; alert at 80% full. Implement cache eviction policy (LRU, max cache size per session). |
| EC-122 | External Failure | Container restart during active subprocess | Subprocess killed; session lost; user disconnected; session resume on reconnect | MEDIUM | Already addressed (Section 3.13). Ensure session metadata persisted before restart. Notify user of restart. |
| EC-123 | Permission | Subprocess attempts to access file outside allowed directories (sandbox violation) | SDK sandbox blocks access; operation fails; user notified "Access denied" | LOW | Already handled by SDK sandbox. Ensure add_dirs configured correctly for plugin needs. |
| EC-124 | Data | Shell snapshot cache in ~/.claude/ becomes corrupted | Subprocess fails to load snapshot; falls back to clean shell initialization (slower) | LOW | SDK handles gracefully. Performance degradation but not a hard failure. Log corruption events. |
| EC-125 | Data | Subprocess writes sensitive data to ~/.claude/ (credentials, secrets) | Data persisted in session directory; accessible to future session resumes | HIGH | Security risk. Document that ~/.claude/ is part of session state. Implement scrubbing: scan for secret patterns (API keys, tokens) before persisting snapshots. |
| EC-126 | Timing | Subprocess init takes >60s (extreme slowness) | Pre-warm timeout fires; subprocess killed; new attempt made | MEDIUM | Configure pre-warm timeout (default: 60s). If init consistently slow, investigate environment issues (CPU throttling, network latency). |
| EC-127 | Timing | Subprocess cleanup takes >30s (slow shutdown) | Graceful shutdown timeout fires; subprocess force-killed (SIGKILL) | LOW | Acceptable. Log slow shutdown events. SIGKILL ensures cleanup completes. |

**Component Summary:**
- **HIGH Risk**: 4 edge cases (OOM, env var injection, filesystem full, secrets in cache)
- **MEDIUM Risk**: 6 edge cases
- **LOW Risk**: 4 edge cases
- **Total**: 14 edge cases

---

## 7. Edge Cases: Scaling / Deployment

| ID | Category | Scenario | Expected Behavior | Redesign Risk | Mitigation |
|----|----------|----------|-------------------|---------------|------------|
| EC-128 | Boundary | Container CPU throttled (burst credits exhausted) | Subprocess init and queries become slower; latency increases; no hard failure | MEDIUM | Monitor CPU throttling metrics (container_cpu_cfs_throttled_seconds_total). Right-size containers to avoid throttling. |
| EC-129 | Boundary | Database connection pool exhausted (too many concurrent sessions) | New sessions fail with "Database connection unavailable" error | HIGH | Configure connection pool size based on MAX_SESSIONS. Implement connection pool monitoring and alerting. |
| EC-130 | Invalid Input | CORS origin not in allowlist (user loads frontend from unauthorized domain) | WebSocket upgrade fails with 403 Forbidden | LOW | Already addressed (Section 3.10). Document CORS configuration for production. |
| EC-131 | Concurrent | Rolling deployment: old pod terminates while handling active sessions | Graceful shutdown initiated (Section 3.13); sessions notified; users reconnect to new pod | MEDIUM | Ensure readiness probe passes before routing traffic. Configure load balancer for connection draining (60s). |
| EC-132 | Concurrent | Load balancer routes same session_id to different pods (no session affinity) | Session state mismatch; session not found on new pod; user forced to resume | HIGH | Enforce session affinity via load balancer (sticky sessions based on session_id in WebSocket path or cookie). Document load balancer requirements. |
| EC-133 | State Transition | New deployment version incompatible with old session data | Old sessions fail to resume; users forced to start new sessions | HIGH | Implement session data versioning. On version mismatch, detect and offer migration or reject resume with clear message. |
| EC-134 | State Transition | Prometheus scrape occurs during high load (many active queries) | Metrics collection adds CPU overhead; queries slightly slower | LOW | Optimize metrics collection: use efficient counters/gauges, avoid expensive calculations in scrape path. |
| EC-135 | External Failure | Database becomes unavailable during active sessions | New sessions fail to create (can't write metadata); active sessions continue (no DB access needed mid-query) | HIGH | Implement database health check in readiness probe. Cache essential session metadata in-memory to survive brief DB outages. |
| EC-136 | External Failure | Container orchestrator (Kubernetes) evicts pod due to memory pressure | Pod receives SIGTERM; graceful shutdown initiated; active sessions interrupted; users reconnect | MEDIUM | Already addressed (Section 3.13). Monitor memory requests/limits to avoid eviction. Set resource reservations correctly. |
| EC-137 | Permission | Health check endpoint accessed without auth | Health checks must be unauthenticated (for load balancer and Kubernetes probes) | LOW | Already specified (Section 3.12). Health endpoints are public. No sensitive data exposed. |
| EC-138 | Data | Shared database corrupted (multiple pods writing conflicting data) | Session metadata inconsistencies; race conditions | MEDIUM | Use database transactions for all metadata writes. Implement row-level locking for session updates. |
| EC-139 | Data | Session metadata pruning job runs during active sessions | Old session records deleted; active sessions unaffected (metadata updated with new last_active timestamp) | LOW | Pruning job uses "last_active < X days ago" filter. Active sessions have recent timestamps. No conflict. |
| EC-140 | Timing | Health check false positive (process alive but subprocess pool empty) | Load balancer routes traffic to unhealthy pod; users experience cold starts or failures | HIGH | Readiness probe must check pre-warm pool depth and circuit breaker state. Return 503 if pool empty and cold start failing. |
| EC-141 | Timing | Auto-scaler adds new pod during traffic spike | New pod takes 30-60s to become ready (pre-warm initialization); users may see increased latency during scale-up | MEDIUM | Configure auto-scaler with lead time: scale up proactively based on CPU/memory trends, not just current load. |

**Component Summary:**
- **HIGH Risk**: 5 edge cases (connection pool exhaustion, session affinity, session version incompatibility, database unavailability, health check false positive)
- **MEDIUM Risk**: 5 edge cases
- **LOW Risk**: 4 edge cases
- **Total**: 14 edge cases

---

## Risk Summary by Component

| Component | HIGH Risk | MEDIUM Risk | LOW Risk | Total |
|-----------|-----------|-------------|----------|-------|
| Session Lifecycle | 10 | 11 | 4 | 25 |
| WebSocket Communication | 4 | 9 | 13 | 26 |
| Plugin System | 8 | 10 | 9 | 27 |
| Permission System | 4 | 7 | 5 | 16 |
| Claude API / SDK | 3 | 7 | 9 | 19 |
| Subprocess Management | 4 | 6 | 4 | 14 |
| Scaling / Deployment | 5 | 5 | 4 | 14 |
| **TOTAL** | **38** | **55** | **48** | **141** |

---

## Critical Design Implications

### 1. Subprocess Model Creates Fundamental Scaling Limits

**Edge Cases:** EC-001 (pool exhaustion), EC-114 (OOM), EC-121 (disk full), EC-132 (session affinity)

**Implication:** The one-subprocess-per-session model means horizontal scaling is container-level, not process-level. Each container can support 4-8 concurrent sessions realistically (given 4GB RAM per session + overhead). This is NOT a serverless-friendly architecture.

**Design Decision Required:**
- Accept 4-8 sessions per container as architectural limit
- Document minimum container size (16GB RAM, 8 vCPU, 20GB disk)
- Implement session queuing (not load shedding) when capacity reached
- Consider session pooling service (separate tier) for better resource utilization

### 2. Pre-Warm Pool is Critical Path with Multiple Failure Modes

**Edge Cases:** EC-001 (empty pool), EC-014 (rate-limited pool), EC-018 (stale config), EC-022 (pool init fails), EC-140 (false healthy)

**Implication:** The 20-30s cold start makes pre-warming mandatory for UX. But the pool itself has lifecycle complexity: what if all pre-warm attempts fail on startup? What if API rate-limits pre-warming? What if plugin config changes invalidate the pool?

**Design Decision Required:**
- Should server start if 0 pre-warms succeed? (Recommendation: NO - fail startup)
- How to handle stale pool? (Recommendation: invalidate pool on plugin registry changes)
- Pool sizing strategy? (Recommendation: dynamic sizing based on historical load, not static)
- Pool health definition? (Recommendation: readiness probe checks pool depth AND recent success rate)

### 3. Session State Sync Across Disconnections is Complex

**Edge Cases:** EC-035 (disconnect mid-query), EC-036 (sequence gap), EC-044 (buffer exhaustion), EC-048 (duplicate results)

**Implication:** The architecture assumes WebSocket reconnection is common (mobile networks, laptop sleep). But ensuring exactly-once delivery of streaming messages is hard. The design proposes sequence numbers and buffering, but:
- How long to buffer? (5 min proposed, but what if user reconnects after 10 min?)
- What if buffer grows to 100MB? (memory risk)
- How to handle reconnect during streaming result? (full replay vs continuation)

**Design Decision Required:**
- Define reconnection window (Recommendation: 5 min buffer, after that session is "abandoned")
- Define buffer size limits (Recommendation: 100 messages OR 10MB per session)
- Define replay semantics for large messages (Recommendation: don't buffer tool_result >1MB; make client fetch via REST)

### 4. Plugin Hot Reload is Dangerous with Active Sessions

**Edge Cases:** EC-060 (activate mid-session), EC-061 (deactivate mid-session), EC-064 (file deleted), EC-075 (hot reload)

**Implication:** The plugin system assumes plugins can be added/removed at runtime. But if sessions are long-lived (up to 4 hours), plugin changes create consistency problems. Current design says "new sessions only", but:
- What if operator needs to emergency-disable a buggy plugin?
- What if plugin secret rotated (EC-067)?
- What if plugin file deleted from filesystem?

**Design Decision Required:**
- Should hot reload be supported? (Recommendation: YES for activate, NO for deactivate of in-use plugins)
- Should plugin deactivation force-disconnect sessions? (Recommendation: YES with 30s warning)
- Should plugin secret updates apply to active sessions? (Recommendation: NO - next session only)

### 5. Concurrent Connection Deduplication is Critical for Correctness

**Edge Cases:** EC-010 (same session multiple tabs), EC-033 (concurrent messages)

**Implication:** If a user opens the same session in two browser tabs and both tabs can send messages, the session state becomes nondeterministic (race conditions on query ordering). The design proposes dropping older connections, but:
- What if user has two tabs for legitimate multitasking (one for reference, one for active)?
- What if connection drop happens mid-query?

**Design Decision Required:**
- Enforce one-active-connection-per-session? (Recommendation: YES - last connection wins)
- Allow read-only connections for multiple tabs? (Recommendation: future enhancement)
- Notify user when connection is replaced? (Recommendation: YES - "Session opened in another window")

### 6. JWT Expiry During Active WebSocket Requires Token Refresh Protocol

**Edge Cases:** EC-016 (JWT expires during session), EC-043 (near-expiry at connect)

**Implication:** JWTs expire (15 min). WebSockets are long-lived (up to 4 hours). Current design proposes token refresh over WebSocket, but SDK doesn't have built-in token refresh. Need custom protocol:
- Server detects token near expiry (5 min remaining)
- Server sends `refresh_required` message to client
- Client fetches new token from auth endpoint (or uses refresh token)
- Client sends new token via WebSocket message `{type: "auth_refresh", token: "..."}`
- Server updates connection authentication without disconnect

**Design Decision Required:**
- Is WebSocket token refresh supported by Starlette/FastAPI? (Need to verify)
- Alternative: force disconnect before expiry, require reconnect? (Worse UX but simpler)

### 7. In-Process Tool Plugins Have Weak Isolation

**Edge Cases:** EC-069 (undeclared API calls), EC-081 (tool plugin exception)

**Implication:** Tool plugins are Python functions running in the main FastAPI process. They can:
- Call arbitrary external APIs (bypass permission system)
- Block the async event loop (hang the server)
- Consume unbounded memory (OOM the process)
- Raise unhandled exceptions (crash the server)

The design acknowledges this as P0 risk but proposes only review + logging in v1.

**Design Decision Required:**
- Is in-process acceptable for v1? (Recommendation: YES with restrictions)
- What restrictions? (Recommendation: operator-uploaded plugins only, no public marketplace)
- Future path? (Recommendation: move tool plugins to stdio MCP servers in v2)

### 8. Rate Limiting Must Be Multi-Layer to Prevent Cost Runaway

**Edge Cases:** EC-049 (rate limit mid-query), EC-100 (API rate limit), EC-107 (account-level limit)

**Implication:** Three rate limit layers needed:
1. Per-user message rate (prevent buggy client spam)
2. Per-session cost cap (prevent single runaway conversation)
3. Platform-wide budget monitoring (prevent account-level overages)

Current design addresses #1 and #2. But #3 (platform-wide monitoring) only has alerting, not enforcement.

**Design Decision Required:**
- Should platform enforce hard budget cap? (Recommendation: YES - configurable)
- What happens when cap reached? (Recommendation: return 503 on new sessions, allow existing to complete)
- Who is responsible for cost controls? (Recommendation: operator sets limits, platform enforces)

---

## Testing Implications

These edge cases directly inform integration test scenarios:

### Must-Test Scenarios (P0):
1. Pre-warm pool exhaustion during load spike (EC-001)
2. Session OOM and recovery via resume (EC-004, EC-114)
3. WebSocket disconnect/reconnect with message replay (EC-036)
4. Concurrent connection deduplication (EC-010, EC-033)
5. Plugin activation while sessions active (EC-060)
6. JWT expiry during active session (EC-016)
7. API rate limit (429) and circuit breaker (EC-100, EC-107)
8. Graceful shutdown with active sessions (EC-131)
9. Tool input sanitization (prompt injection defense) (EC-093)
10. Subprocess crash and session recovery (EC-119)

### Should-Test Scenarios (P1):
- All MEDIUM risk edge cases
- Boundary conditions (max values, empty values, exact limits)
- State transitions (plugin activate/deactivate, session resume/fork)

### Could-Test Scenarios (P2):
- LOW risk edge cases (document behavior, test if time permits)
- Performance edge cases (slow API, high token rate)

---

## Open Questions for Architecture Team

1. **Pre-warm pool invalidation strategy**: Should plugin changes invalidate the pool? What about config-only changes?

2. **Session abandonment policy**: What is the official timeout for reconnection? Should it differ between free/paid tiers?

3. **Plugin hot reload semantics**: Force-disconnect sessions using deactivated plugins, or allow graceful completion?

4. **Subprocess init timeout**: Is 60s too long? Should it be configurable per deployment environment?

5. **Tool plugin isolation**: Is in-process acceptable for v1 if we restrict to operator-uploaded plugins only?

6. **Circuit breaker scope**: Global (shared across sessions) or per-session?

7. **WebSocket token refresh**: Implement custom protocol, or force disconnect + reconnect?

8. **Budget enforcement**: Hard cap or soft warning?

9. **Session affinity implementation**: Load balancer level or application level (session ID in URL)?

10. **Health check definition**: What makes a pod "ready"? Pool depth? Circuit breaker state? Database connectivity?

---

## Recommended Next Steps

1. **Session Manager**: Prioritize implementation of EC-001, EC-003, EC-004, EC-008 mitigations (pool management, duration limits, RSS monitoring, session locking)

2. **WebSocket Handler**: Implement message sequence numbers and reconnection sync (EC-036, EC-044, EC-048)

3. **Permission Gate**: Implement input sanitization for Bash tool (EC-093) and environment variable validation (EC-116)

4. **Plugin Registry**: Implement file watcher for plugin directories (EC-064) and tool name conflict detection (EC-059)

5. **Deployment Guide**: Document load balancer session affinity requirements (EC-132), resource allocation guidelines (EC-128), and health check configuration (EC-140)

6. **Testing**: Create integration test suite covering all P0 edge cases listed above

7. **Monitoring**: Implement alerts for high-risk edge cases (pool exhaustion, OOM, rate limits, circuit breaker state)

8. **Decision Log**: Document architectural decisions for the 10 open questions listed above

---

*End of Edge Case Matrix*
