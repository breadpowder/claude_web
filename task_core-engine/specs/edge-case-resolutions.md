# Edge Case Resolution Matrix: claude_sdk_pattern Core Engine

> **Document Version**: 1.0
> **Date**: 2026-02-07
> **Source**: 141 edge cases from `requirement/team_findings/edge_case_matrix.md`
> **Focus**: All HIGH risk edge cases with design decisions

---

## Resolution Summary

| Category | HIGH Risk Cases | Resolved | Pending Decision |
|----------|----------------|----------|------------------|
| Session Lifecycle | 10 | 10 | 0 |
| WebSocket Communication | 4 | 4 | 0 |
| Plugin System | 8 | 7 | 1 (EC-075) |
| Permission System | 4 | 4 | 0 |
| Claude API / SDK | 3 | 3 | 0 |
| Subprocess Management | 4 | 4 | 0 |
| Scaling / Deployment | 5 | 5 | 0 |
| **TOTAL** | **38** | **37** | **1** |

---

## Session Lifecycle (10 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-001 | Pre-warm pool empty when user creates session | Fall back to cold start with "Preparing your session (up to 30 seconds)..." progress indicator. Auto-scale pool: when depth < 1, start pre-warming immediately in background. | Cold start is acceptable as fallback; progress indicator sets user expectation. | Progress bar with estimated time remaining | Phase 1 |
| EC-003 | Session duration reaches max mid-query | Warning at 90% of limit (WebSocket notification). At limit: allow current query up to 30s grace, then terminate. Offer "Start new session" button with resume link. | Abrupt termination is hostile UX; grace period + warning gives user control. | Warning banner at 90%; termination dialog at 100% | Phase 1 |
| EC-004 | RSS memory exceeds threshold mid-query | Mark session for graceful restart. Allow current query to complete. Notify user: "Session restarting for performance." Create new session with resume=session_id. | Hard kill loses user's in-flight query; graceful restart preserves it. | Toast notification: "Session restarting..." | Phase 1 |
| EC-007 | Resume with corrupted SDK session data | Detect corruption via try/except on resume. Archive corrupted session metadata. Start fresh session. Notify user: "Previous session could not be restored." | Users should not be blocked by corrupted data; fresh start with clear message is acceptable. | Error banner with "Start new session" button | Phase 1 |
| EC-010 | Same session in multiple browser tabs | Enforce one-active-connection-per-session. New connection replaces old. Old connection receives: "Session opened in another window." | Prevents state corruption from concurrent message sends. Most natural behavior for users. | Modal dialog: "Session opened elsewhere. [Reconnect here]" | Phase 1 |
| EC-014 | API rate limit during pre-warm | Pause pre-warm operations for 5 minutes when rate-limited. Don't waste pool slots on rate-limited clients. Log rate limit events. | Pre-warming during rate limit wastes quota and fails anyway. Backoff is correct strategy. | No direct UI impact (background operation) | Phase 1 |
| EC-016 | JWT expires during active WebSocket session | Server detects token near expiry (5 min remaining). Sends "refresh_required" message via WebSocket. Client obtains new token via refresh endpoint. Client sends new token via WebSocket message. No disconnect needed. | Forcing disconnect + reconnect is poor UX and risks losing streaming data. In-band refresh is seamless. | Silent token refresh; no user-visible impact if refresh succeeds. "Please re-login" dialog if refresh fails. | Phase 2 |
| EC-018 | Pre-warmed session has stale plugin config | Invalidate pre-warm pool when PluginRegistry emits "plugin_changed" event. New pre-warm slots use current config. Active sessions unaffected (new sessions only). | Lazy config build (at session start) is simpler but adds latency. Pool invalidation is a clean trade-off. | No direct UI impact (new sessions get correct config) | Phase 2 |
| EC-022 | All pre-warm attempts fail on startup | Server startup fails (readiness probe returns 503). Require at least 1 successful pre-warm to pass readiness. Log failure reason (API key invalid, rate limit, network). | Routing traffic to a server with no working sessions is worse than failing startup. Fail-fast is the correct strategy. | No UI (server does not start) | Phase 1 |
| EC-023 | Cache directory exceeds disk quota | Monitor ~/.claude/ disk usage per session. Set per-session disk quota via container limits (20GB). Proactive cleanup: delete shell snapshots older than 24h. Alert operator at 80% disk. | Disk exhaustion is as dangerous as OOM. Proactive cleanup prevents it. | No direct UI impact (operational concern) | Phase 1 |

---

## WebSocket Communication (4 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-033 | Two tabs send messages to same session concurrently | Enforced by EC-010 resolution (one connection per session). Second tab's connection is dropped before it can send messages. | Connection deduplication eliminates the concurrent message problem entirely. | Handled by EC-010 modal dialog | Phase 1 |
| EC-036 | Reconnection with message sequence gap | Implement message log per session with sequence numbers. On reconnect, client sends last_message_seq. Server replays missing messages in order. Buffer TTL: 5 minutes, max size: 100 messages or 10MB. | Message replay is essential for reliability. Buffer limits prevent unbounded memory growth. | Automatic: user sees messages appear after reconnect. If gap exceeds buffer, show "Some messages may have been missed." | Phase 2 |
| EC-044 | Message buffer for disconnected client grows unbounded | Cap buffer: 100 messages or 10MB, whichever hit first. TTL: 5 minutes. After TTL, buffer is purged. If client reconnects after purge, session is treated as "stale" -- user starts fresh query. | Unbounded buffers risk server OOM. 5-minute window is generous for mobile network switches. After 5 min, user likely navigated away. | If buffer expired: "Connection was lost for too long. Your session is still available." | Phase 2 |
| EC-050 | Server sends very large tool_result (10MB+) | Truncate tool_result content over 1MB in WebSocket frame. Send truncated version with "truncated: true" flag. Store full result in session metadata. Frontend can fetch full result via REST endpoint on user request. | Large WebSocket frames can break connections and overwhelm the frontend. Truncation with on-demand fetch is the standard pattern. | ToolUseCard shows truncated result with "[Show full result]" button that fetches via REST | Phase 2 |

---

## Plugin System (8 HIGH Risk, 1 Pending)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-059 | Two plugins declare tools with same name | Enforce unique tool names across all active plugins. Maintain tool name index in PluginRegistry. Second plugin registration fails with specific error naming the conflict. | Name collisions cause unpredictable behavior. Fail-fast at registration is clear and debuggable. | Admin UI: error message naming both conflicting plugins | Phase 2 |
| EC-060 | Plugin activated while sessions are active | New plugin available to new sessions only. Active sessions continue with their original plugin set. Notify active users via WebSocket: "New tools available. Restart session to access them." | Mid-session plugin injection is complex and risky. "New sessions only" is simple and safe. | In-session notification: "New tools available. [Restart session]" | Phase 2 |
| EC-064 | SKILL.md file deleted from filesystem | Filesystem watcher detects deletion. Plugin status set to "degraded." Active sessions that loaded the skill before deletion continue working. New sessions cannot use the skill. Operator notified. | Graceful degradation is better than crash. Active sessions should not be disrupted by filesystem changes. | Admin dashboard: plugin status "degraded" with reason | Phase 2 |
| EC-067 | Plugin secret becomes invalid mid-session | Tool invocations return auth errors. Platform detects repeated auth failures from same plugin (3 in 60s). Plugin status set to "auth_failed." Operator notified. Allow secret update without deactivating plugin. | Automatic detection prevents user confusion. Allowing update without deactivation minimizes disruption. | User sees: "[Tool] authentication failed. Administrator has been notified." | Phase 2 |
| EC-069 | Tool plugin calls external API without declaring permission | Accept for v1 (in-process plugins have no isolation). Mitigate: operator-reviewed plugins only, no public marketplace. Log all outbound network calls from tool execution (via hooks). Phase 2: move tool plugins to subprocess for isolation. | Full isolation requires subprocess model (significant effort). Operator trust model is acceptable for v1. | No direct UI impact (operational/security concern) | Phase 2 (mitigation), Phase 4+ (isolation) |
| EC-071 | Plugin secret encrypted with rotated SECRET_KEY | Provide re-encryption CLI utility. On startup, detect decryption failures. Log which plugins are affected. Block activation of affected plugins until secrets are re-encrypted. | Transparent re-encryption on startup is risky (could corrupt data). Explicit utility with admin control is safer. | Admin dashboard: "N plugins require secret re-encryption" alert | Phase 2 |
| EC-073 | Plugin registry database corrupted | Integrity check on startup (SQLite: `PRAGMA integrity_check`, PostgreSQL: similar). If corruption detected, attempt auto-repair. If unrecoverable, fail startup with specific error. Operator runs backup restore. | Database corruption is unrecoverable without backup. Fail-fast prevents cascading data loss. | No UI (server does not start). Operator follows runbook. | Phase 2 |
| EC-075 | Plugin hot reload during active session using that plugin | **PENDING DECISION**. Options: (A) Block hot reload if any active session uses the plugin. (B) Force-disconnect affected sessions with 30s warning. (C) Allow reload, active sessions use old version. **Recommendation: Option C** -- active sessions continue with old version; new sessions get new version. This matches EC-060 behavior. | Need stakeholder input on whether "emergency disable" is needed (Option B). Option C is safest for user experience. | If Option C: no impact on active sessions. If Option B: "Plugin is being updated. Your session will restart in 30 seconds." | Phase 2 |

---

## Permission System (4 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-084 | Two PreToolUse hooks disagree (one Allow, one Deny) | Deny wins. If ANY hook denies, the tool is denied. Hooks execute in registration order (core hooks first, plugin hooks second). | "Deny by default" is the secure choice. Any single objection should block the action. | User sees: "Tool denied by [hook name]: [reason]" | Phase 2 |
| EC-087 | Bash command with dangerouslyDisableSandbox=true | PermissionGate checks command against operator-defined allowlist in config. If not in allowlist: deny with "Unsandboxed commands require operator approval." Log ALL unsandboxed attempts (allowed and denied). | Unsandboxed commands are the highest security risk. Explicit allowlist prevents unauthorized access. | User sees: "This command requires operator approval." | Phase 2 |
| EC-093 | Prompt injection via tool input | PermissionGate input sanitization: (1) reject inputs > 32k chars, (2) scan for common injection patterns, (3) for Bash tool: block path traversal (`../`), block env var manipulation, block pipe to external URLs. Use allowlist for high-risk tools, not just blocklist. | Input sanitization is defense-in-depth. SDK has built-in safety, but tool inputs bypass it. | User sees: "Message blocked: potentially unsafe content detected." (vague on purpose to not train attackers) | Phase 3 |
| EC-094 | Sandbox escape attempt detected | PermissionGate blocks command. Log security event with full details. Increment security alert metric. Operator notified via alert. User session continues (not terminated -- could be false positive). | Alerting without termination avoids false-positive disruption. Operator investigates. | User sees: "This command is not allowed." (generic, no detail about why) | Phase 3 |

---

## Claude API / SDK (3 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-098 | Invalid API key on startup | Validate API key on startup via test query. If invalid: fail startup (readiness probe returns 503). Log specific error: "ANTHROPIC_API_KEY is invalid or expired." | Starting a platform that cannot reach the API is pointless. Fail-fast with clear error saves debugging time. | No UI (server does not start). Operator reads logs. | Phase 1 |
| EC-100 | Multiple sessions hit API rate limit (429) simultaneously | Implement global circuit breaker (not per-session). When any session receives 429, open circuit for all sessions. Prevents retry storms. | Per-session circuit breakers allow other sessions to keep hammering the rate-limited API. Global circuit breaker protects the account. | All active sessions see: "AI service is temporarily busy. Retrying automatically..." | Phase 3 |
| EC-107 | Account-level API rate limit reached | Monitor X-RateLimit-* headers. When approaching limit (90%): slow down new requests (add 1s delay between queries). When exceeded: circuit breaker opens. | Adaptive rate limiting prevents hitting the hard limit. More graceful than hitting the wall and recovering. | Users see slightly slower responses when approaching limit; explicit error when exceeded. | Phase 3 |

---

## Subprocess Management (4 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-114 | CLI subprocess RSS reaches OOM threshold | Handled by EC-004 resolution (graceful restart). Container memory limit set to 2x expected RSS (8GB for 4GB threshold). OOM killer is last resort, not primary defense. | RSS monitoring and graceful restart (EC-004) prevents hitting OOM. Container limit is safety net. | Handled by EC-004 | Phase 1 |
| EC-116 | Environment variable injection via plugin | Sanitize all plugin-provided env vars. Blocklist: LD_PRELOAD, LD_LIBRARY_PATH, PATH, PYTHONPATH, NODE_PATH. Allowlist: only env vars declared in plugin manifest config_schema. Log all env vars passed to subprocess. | Env var injection is a privilege escalation vector. Strict allowlist prevents it. | No direct UI impact (security concern) | Phase 2 |
| EC-121 | Filesystem full in subprocess | Handled by EC-023 resolution (disk monitoring, proactive cleanup, container disk limits). | See EC-023. | See EC-023. | Phase 1 |
| EC-125 | Subprocess writes sensitive data to ~/.claude/ | Implement post-session scrubbing: scan session directory for patterns matching secrets (regex for API keys, tokens, passwords). Redact or delete matching content. Document that ~/.claude/ is part of session state and may contain tool outputs. | Secret leakage into session storage is a data exposure risk. Post-session scrubbing reduces exposure. | No direct UI impact (security concern) | Phase 3 |

---

## Scaling / Deployment (5 HIGH Risk)

| EC-ID | Scenario | Design Decision | Rationale | UI Impact | Phase |
|-------|----------|-----------------|-----------|-----------|-------|
| EC-129 | Database connection pool exhausted | Size connection pool based on MAX_SESSIONS + overhead (e.g., MAX_SESSIONS * 2 + 5). Monitor pool utilization. Alert at 80% utilization. If exhausted: return 503 for new sessions; active sessions unaffected (they have active connections). | Connection pool sizing should be aligned with session capacity. Monitoring prevents surprise exhaustion. | New users see: "Server at capacity. Please try again in a few minutes." | Phase 3 |
| EC-132 | Load balancer routes to wrong pod (no session affinity) | Enforce session affinity via load balancer. Use session_id in WebSocket URL path (`/ws/v1/chat/{session_id}`) for affinity routing. Document load balancer configuration requirements (Nginx, ALB, etc.). | Session state is bound to a specific pod. Incorrect routing causes "session not found" errors. | If affinity breaks: "Session not found on this server. Reconnecting..." (automatic redirect) | Phase 3 |
| EC-133 | New deployment version incompatible with old session data | Version session data: include platform version in session metadata. On resume: check version compatibility. If incompatible: offer "start fresh" with explanation. Maintain backward compatibility for 2 minor versions. | Forced session loss on every upgrade is hostile UX. Version checking with graceful fallback is better. | "Your previous session was created with an older version. [Start new session] or [Try to resume (may have issues)]" | Phase 3 |
| EC-135 | Database unavailable during active sessions | Active sessions continue (no DB access needed mid-query). New sessions fail (cannot persist metadata). Cache essential session metadata in-memory (last 30 minutes). Readiness probe returns 503 when DB unreachable. | Database should not be on the critical path for active conversations. In-memory cache provides brief resilience. | Active users: no impact. New users: "Server is temporarily unavailable." | Phase 3 |
| EC-140 | Health check false positive (alive but pool empty) | Readiness probe checks: (1) pre-warm pool depth > 0 OR cold start succeeded in last 60s, (2) circuit breaker is not open, (3) database is reachable. All three must pass for 200 OK. | Multi-factor readiness prevents routing to degraded pods. Pool depth alone is not sufficient (cold start may still work). | No direct UI impact (traffic routing concern) | Phase 3 |

---

## Pending Decisions

| EC-ID | Scenario | Options | Recommendation | Blocker |
|-------|----------|---------|----------------|---------|
| EC-075 | Plugin hot reload during active sessions | A: Block reload, B: Force-disconnect, C: Old version for active, new for new sessions | Option C (safest for users) | Need stakeholder confirmation: is emergency disable (Option B) ever needed? |

---

*End of Edge Case Resolution Matrix*
