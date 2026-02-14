# User Stories: claude_sdk_pattern Core Engine

> **Document Version**: 1.0
> **Date**: 2026-02-07
> **Status**: Draft - Pending Review
> **Personas**: Plugin Developer (Alex), Platform Operator (Morgan), End User (Jordan), Platform Admin (Sam)

---

## Epic 1: Core Chat Experience (Phase 1 MVP)

### US-001: Pre-Warmed Session Start (Priority: P1)

**As an** end user, **I want** my chat session to start within 3 seconds, **so that** I can begin working immediately without losing my train of thought.

**Why this priority**: The 20-30 second cold start is the primary UX blocker identified in research. Without pre-warming, the platform is unusable for real-time interaction. This is the core differentiator from raw SDK usage.

**Independent Test**: Start the platform with a pre-warm pool of 1. Open the browser. Measure time from page load to "Ready" status. Verify it is under 3 seconds. This can be tested without any other feature being complete -- a minimal WebSocket connection and session assignment is sufficient.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the platform is running with a pre-warm pool size of 2 and both slots are filled,
   **When** a user opens the chat interface,
   **Then** the UI displays "Ready" status within 3 seconds and the session is assigned from the pool.

2. **Given** the pre-warm pool is empty (all slots in use),
   **When** a user opens the chat interface,
   **Then** the UI displays "Preparing your session (up to 30 seconds)..." with a progress indicator, and the session is created via cold start.

3. **Given** a pre-warmed session has been assigned to a user,
   **When** the pool detects an empty slot,
   **Then** a new session is pre-warmed in the background within 60 seconds without affecting active sessions.

4. **Given** the platform starts up with PREWARM_POOL_SIZE=2,
   **When** both pre-warm attempts fail (e.g., invalid API key),
   **Then** the readiness probe returns 503 and the platform does not accept traffic.

**Key Entities Involved**: Session, PreWarmPool, ClaudeSDKClient
**Key Fields**: session_id, pool_size, pool_depth, init_duration_seconds, session_status (pre-warmed|cold|active|idle|terminated)

---

### US-002: Streaming Chat Conversation (Priority: P1)

**As an** end user, **I want** to see Claude's response appear token by token as it streams, **so that** I know the system is working and can start reading before the full response is complete.

**Why this priority**: Streaming provides critical user feedback that prevents perceived hangs. Without streaming, users abandon sessions after 7 seconds (Microsoft attention span study). This is table-stakes for any chat interface.

**Independent Test**: Send a message to the chat interface. Verify that the first token appears within 2 seconds of a pre-warmed session. Verify that subsequent tokens render progressively. This can be tested with a hardcoded ClaudeAgentOptions (no plugin system needed).

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the user has an active session and types a message,
   **When** the user presses Enter,
   **Then** the message appears in the message list immediately, and Claude's response begins streaming within 2 seconds (pre-warmed) with tokens rendered as they arrive.

2. **Given** Claude is streaming a response,
   **When** the user observes the UI,
   **Then** a typing indicator (animated cursor) is visible on Claude's message bubble, and each token is appended without page flicker.

3. **Given** Claude completes the response,
   **When** the final ResultMessage is received,
   **Then** the typing indicator disappears, and the message displays cost information (e.g., "$0.02") in a subtle footer.

4. **Given** an error occurs mid-stream (e.g., API timeout),
   **When** the error is detected,
   **Then** the partial response is preserved, an error message appears below ("Response interrupted. You can retry."), and the user can send a new message.

**Key Entities Involved**: Session, WebSocketConnection, MessageStream, ChatMessage
**Key Fields**: message_id, message_type (user|assistant|tool_use|tool_result|error), content, timestamp, cost_usd, is_streaming, sequence_number

---

### US-003: Tool Use Transparency (Priority: P1)

**As an** end user, **I want** to see which tools Claude is using and their execution status, **so that** I understand what is happening and can trust the results.

**Why this priority**: "Opaque failures" is the #4 end-user pain point. Transparency builds trust and helps users learn what the system can do. This differentiates from ChatGPT's opaque tool use.

**Independent Test**: Send a message that triggers a tool invocation (e.g., a Bash command). Verify that the ToolUseCard appears showing the tool name, execution status, and result. No plugin system needed -- built-in SDK tools (Bash, Read, Write) suffice.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** Claude decides to invoke a tool during a response,
   **When** the ToolUseBlock event arrives via WebSocket,
   **Then** a ToolUseCard renders in the message list showing: tool name, "Executing..." status, and a collapse/expand toggle.

2. **Given** a ToolUseCard is showing "Executing..." status,
   **When** the ToolResultBlock event arrives,
   **Then** the card updates to show "Complete (X.Xs)" with the result summary, and the full result is available on expand.

3. **Given** a tool execution fails,
   **When** the failure event arrives,
   **Then** the ToolUseCard shows "Error" status in red with the error reason, and Claude's follow-up response explains the failure.

4. **Given** Claude invokes multiple tools in sequence,
   **When** each tool event arrives,
   **Then** each tool gets its own ToolUseCard, displayed in execution order within the message flow.

**Key Entities Involved**: ToolUseBlock, ToolResultBlock, ToolUseCard (UI component)
**Key Fields**: tool_name, tool_input (JSON), tool_result (JSON), execution_status (executing|complete|error), execution_duration_ms

---

### US-004: Session Memory Limits (Priority: P1)

**As a** platform operator, **I want** sessions to be automatically terminated when they exceed memory or duration limits, **so that** the server remains stable and does not crash from SDK memory leaks.

**Why this priority**: The SDK memory growth over extended sessions (~500MB-1GB baseline growing to 24GB+ per GitHub issue #4953, OPEN) is a critical operational risk. Without enforcement, a single session can OOM the entire server. This is mandatory for any production deployment.

**Independent Test**: Start a session and monitor its RSS via the /proc filesystem. Simulate memory growth by setting a low RSS threshold (e.g., 100MB for testing). Verify that the session receives a warning and is gracefully terminated. This test requires only SessionManager -- no plugins, RBAC, or frontend.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a session has been running for 3 hours and 36 minutes (90% of 4-hour default limit),
   **When** the duration monitor checks the session,
   **Then** the user receives a WebSocket notification "Session will end in 24 minutes. Save your work."

2. **Given** a session reaches the 4-hour duration limit,
   **When** no query is in flight,
   **Then** the session is terminated, subprocess is cleaned up, and the user sees "Session ended (duration limit). You can start a new session."

3. **Given** a session reaches the 4-hour duration limit,
   **When** a query IS in flight,
   **Then** the system waits up to 30 seconds for the query to complete, then terminates the session.

4. **Given** a session subprocess RSS exceeds 4GB,
   **When** the RSS monitor detects the threshold breach,
   **Then** the session is flagged for graceful restart: current query completes, user is notified "Session restarting due to resource limits," and a new session is created with resume capability.

5. **Given** a subprocess becomes a zombie (terminated but not reaped),
   **When** the periodic cleanup scan runs (every 60 seconds),
   **Then** the zombie process is detected and reaped, and an alert metric is incremented.

**Key Entities Involved**: Session, SubprocessMonitor, DurationMonitor
**Key Fields**: session_id, subprocess_pid, rss_bytes, created_at, last_active_at, max_duration_seconds, max_rss_bytes, session_state (active|warning|restarting|terminated)

---

### US-005: Chat Input and Controls (Priority: P1)

**As an** end user, **I want** a clean input bar with keyboard shortcuts for sending messages and interrupting Claude, **so that** I can interact efficiently without reaching for the mouse.

**Why this priority**: Power users send 20+ messages per session. Keyboard shortcuts and a responsive input bar are essential for flow state. This is basic UX hygiene for a chat interface.

**Independent Test**: Load the chat UI. Type a message and press Enter. Verify it sends. During a streaming response, press Ctrl+Shift+X. Verify the response is interrupted. This requires only the frontend and WebSocket -- no plugins or auth.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the user is focused on the input bar,
   **When** the user types a message and presses Enter,
   **Then** the message is sent via WebSocket and appears in the message list immediately.

2. **Given** Claude is streaming a response,
   **When** the user presses Ctrl+Shift+X,
   **Then** an interrupt command is sent, Claude's response stops, and a "[Response interrupted]" indicator appears.

3. **Given** the input bar is empty,
   **When** the user presses Enter,
   **Then** nothing is sent (no empty messages).

4. **Given** a query is in flight (Claude is processing),
   **When** the user types in the input bar,
   **Then** the input bar remains responsive (not blocked), and the message is queued to send after the current response completes.

**Key Entities Involved**: InputBar (UI), WebSocketConnection
**Key Fields**: message_text, is_sending, is_interrupted

---

### US-006: Session Resume (Priority: P2)

**As an** end user, **I want** to close my browser and return tomorrow to find my conversation intact, **so that** I don't lose context and don't have to re-explain my task.

**Why this priority**: Context loss is the #2 end-user pain point. Session persistence differentiates this platform from ephemeral chat tools. However, it is P2 because MVP can ship with ephemeral sessions first.

**Independent Test**: Start a session, send 3 messages, note the session_id. Close the browser. Reopen and navigate to the session. Verify all 3 messages are displayed and Claude retains context from the previous conversation. Requires SessionManager with resume support and session metadata storage.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a user has an active session with 5 messages exchanged,
   **When** the user closes the browser tab,
   **Then** the session remains on the server in "idle" state for up to 30 minutes (idle timeout), and the session metadata (including message history reference) is persisted to the database.

2. **Given** a user returns within 30 minutes of closing the browser,
   **When** the user opens the chat interface,
   **Then** the previous session is resumed automatically, all messages are displayed, and Claude retains context.

3. **Given** a user returns after the 30-minute idle timeout,
   **When** the user opens the chat interface,
   **Then** a new session is created with `resume=<session_id>`, SDK loads the session from disk, and the previous conversation history is available.

4. **Given** the SDK session data on disk is corrupted or deleted,
   **When** resume is attempted,
   **Then** the user sees "Previous session could not be restored. Starting a new session." and a fresh session is created.

**Key Entities Involved**: Session, SessionMetadata (database), SDKSessionStorage (disk)
**Key Fields**: session_id, user_id, created_at, last_active_at, message_count, resume_count, is_resumable

---

### US-007: Error Messages with Context (Priority: P2)

**As an** end user, **I want** error messages that tell me what happened and what I can do about it, **so that** I am not frustrated by opaque failures.

**Why this priority**: "Opaque failures" ranks as #4 end-user pain point. Actionable error messages reduce support tickets and improve user satisfaction. P2 because basic errors can be handled generically in MVP while polished messages come in iteration.

**Independent Test**: Trigger various error conditions (invalid API key, rate limit, tool failure, session timeout). Verify each produces an error message with: what happened, why, and what the user can do. Requires WebSocket error handling -- no plugins.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the Claude API returns a 429 (rate limit),
   **When** the error is propagated to the user,
   **Then** the message reads "The AI service is temporarily busy. Your message will be retried automatically in a few seconds." (not a raw HTTP error).

2. **Given** a tool invocation fails (e.g., database connection refused),
   **When** the error is displayed,
   **Then** the ToolUseCard shows the tool name, "Error: Connection refused", and Claude's follow-up explains the failure in natural language.

3. **Given** the user's session is terminated due to memory limits,
   **When** the termination notification is sent,
   **Then** the message reads "Your session has been restarted to maintain performance. Your conversation history is preserved. [Continue in new session]" with a clickable link.

4. **Given** the user attempts an action they lack permission for (Phase 2+),
   **When** the permission check fails,
   **Then** the message reads "This action requires [operator/admin] access. Contact your administrator." with the specific permission that was denied.

**Key Entities Involved**: ErrorHandler, WebSocketMessage (error type)
**Key Fields**: error_code, error_message (user-facing), error_detail (technical, logged only), suggested_action

---

## Epic 2: Plugin System (Phase 2)

### US-008: Plugin Registration via Manifest (Priority: P2)

**As a** plugin developer, **I want** to register my MCP server by creating a `plugin.json` file in the plugins directory, **so that** I can extend the platform without modifying core code.

**Why this priority**: Plugin extensibility is the core differentiation. However, MVP can ship without plugins (hardcoded options), so this is P2. The plugin system validates whether teams will actually extend the platform.

**Independent Test**: Create a directory `plugins/my-test-tool/` with a valid `plugin.json`. Start the platform. Verify the plugin appears in the admin API listing as "discovered." Create an invalid manifest (missing required field). Verify a validation error with line number is returned. Requires PluginRegistry -- no RBAC, no cost tracking.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a directory `plugins/slack-notify/` exists with a valid `plugin.json`,
   **When** the PluginRegistry scans the plugins directory on startup,
   **Then** the plugin is discovered, validated, and registered with status "needs_config" (if config_schema is defined) or "ready" (if no config needed).

2. **Given** a `plugin.json` has invalid JSON syntax (e.g., missing comma),
   **When** validation runs,
   **Then** the error message includes: file path, line number, and fix suggestion (e.g., "Line 12: Expected comma after 'version' field").

3. **Given** a `plugin.json` declares a tool name that conflicts with an existing plugin's tool,
   **When** registration is attempted,
   **Then** registration fails with error "Tool name 'mcp__slack__send_message' already registered by plugin 'slack-v1'. Use a unique tool name."

4. **Given** a new plugin directory is created while the platform is running,
   **When** the file watcher detects the change (or manual rescan is triggered),
   **Then** the new plugin is discovered and registered without requiring a platform restart.

**Key Entities Involved**: PluginRegistry, PluginManifest, Plugin
**Key Fields**: plugin_name, manifest_version, plugin_type (tool|mcp|skill|endpoint), capabilities.tools[], permissions.network[], config_schema, status (discovered|validated|registered|configured|activated|errored)

---

### US-009: RBAC with Three Roles (Priority: P2)

**As a** platform admin, **I want** to assign roles (admin, operator, user) to team members, **so that** I can enforce least-privilege access and meet compliance requirements.

**Why this priority**: Required for multi-user deployment. Without RBAC, any user can manage plugins, view other users' sessions, or bypass cost controls. P2 because single-user MVP does not need roles.

**Independent Test**: Create three users with different roles. Verify: admin can manage users and plugins; operator can manage sessions and view metrics; user can only chat. Attempt an admin action with a user token. Verify 403 Forbidden. Requires JWT auth and PermissionGate.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a user with role "user" is authenticated,
   **When** the user attempts to access `GET /api/v1/plugins`,
   **Then** the response is 403 Forbidden with message "Insufficient permissions. Required role: operator."

2. **Given** a user with role "operator" is authenticated,
   **When** the operator activates a plugin via `POST /api/v1/plugins/{name}/activate`,
   **Then** the plugin is activated and an audit log entry is created with the operator's user_id.

3. **Given** a user with role "admin" is authenticated,
   **When** the admin creates a new user via `POST /api/v1/users`,
   **Then** the user is created with the specified role, and the admin action is audit-logged.

4. **Given** a user's role is changed from "operator" to "user" while they have an active session,
   **When** the user's next tool invocation is checked by PermissionGate,
   **Then** the tool is denied if it requires operator access, and the user receives "Your permissions have changed. Some tools are no longer available."

**Key Entities Involved**: User, Role, PermissionGate, AuditLog
**Key Fields**: user_id, username, role (admin|operator|user), created_at, last_login_at, is_active

---

### US-010: Per-User Cost Caps (Priority: P2)

**As a** platform admin, **I want** to set a monthly cost cap per user, **so that** one user's experiment cannot run up a $2000 API bill.

**Why this priority**: "Opaque costs" is the #1 operator pain point and #1 admin pain point. Cost control is essential for enterprise adoption. P2 because MVP uses a single shared API key with manual cost monitoring.

**Independent Test**: Set a user's monthly cap to $10. Send messages until the cumulative cost approaches $10. Verify a warning at $8 (80%). Verify session creation is blocked at $10 with a clear message. Requires cost tracking from ResultMessage and user database.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a user has a monthly cost cap of $100 and has spent $79.50 this month,
   **When** a query completes with cost $1.50 (total now $81.00),
   **Then** the user receives an in-session notification "You have used 81% of your $100 monthly budget."

2. **Given** a user has reached 100% of their monthly cost cap,
   **When** the user attempts to send a new message,
   **Then** the message is rejected with "Monthly budget exceeded ($100.00/$100.00). Contact your administrator to increase your limit."

3. **Given** the admin increases a user's cost cap from $100 to $200,
   **When** the user (who was at $100/$100) sends a new message,
   **Then** the message is accepted and processed normally.

4. **Given** it is the first day of a new month,
   **When** the cost tracking resets,
   **Then** all users' monthly spend counters reset to $0.00, and previously blocked users can create sessions again.

**Key Entities Involved**: CostTracker, User, Session
**Key Fields**: user_id, monthly_cost_cap_usd, current_month_spend_usd, last_cost_update_at, cost_warning_sent (boolean)

---

### US-011: Audit Logging (Priority: P2)

**As a** platform admin, **I want** a complete audit trail of all tool invocations, **so that** I can demonstrate compliance during security reviews and investigate incidents.

**Why this priority**: Audit logging is a hard requirement for enterprise adoption (HIPAA, SOC2). Without it, the platform cannot be used in regulated environments. P2 because it requires the permission system and database.

**Independent Test**: Send a message that triggers a tool invocation. Query the audit log API. Verify the log entry contains: timestamp, user_id, session_id, tool_name, input (sanitized), result_status, cost. Requires AuditLogger and REST API endpoint.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** a user invokes the "postgres-query" tool,
   **When** the tool execution completes,
   **Then** an audit log entry is created with: timestamp, user_id, session_id, tool_name="mcp__postgres-query__execute_sql", sanitized_input (SQL query with credentials masked), result_status (success|error), execution_duration_ms, cost_usd.

2. **Given** an admin requests the audit log for a specific user,
   **When** the admin calls `GET /api/v1/admin/audit-log?user_id=123&start=2026-02-01&end=2026-02-07`,
   **Then** the response contains all tool invocations by that user in the date range, paginated (100 per page).

3. **Given** a tool invocation input contains sensitive data (e.g., API keys in a curl command),
   **When** the audit log entry is created,
   **Then** the input field has patterns matching secrets (API keys, tokens, passwords) replaced with "[REDACTED]".

**Key Entities Involved**: AuditLog, ToolInvocation
**Key Fields**: audit_id, timestamp, user_id, session_id, tool_name, sanitized_input, result_status (success|error|denied), execution_duration_ms, cost_usd

---

## Epic 3: Production Operations (Phase 3)

### US-012: Prometheus Metrics (Priority: P2)

**As a** platform operator, **I want** Prometheus-compatible metrics at a /metrics endpoint, **so that** I can build Grafana dashboards and configure alerts for production monitoring.

**Why this priority**: "Can't operate what you can't measure" -- observability is the #1 operator need. Without metrics, operators cannot detect or diagnose issues. P2 because MVP can launch with logs-only observability.

**Independent Test**: Start the platform. Scrape `GET /metrics`. Verify Prometheus text format with at least 10 custom metrics (session_count, pool_depth, rss_bytes, etc.). Import the provided Grafana dashboard JSON. Verify all panels render. Requires prometheus-fastapi-instrumentator and custom metric registration.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the platform is running,
   **When** Prometheus scrapes `GET /metrics`,
   **Then** the response contains Prometheus text format with metrics including: csp_active_sessions (gauge), csp_prewarm_pool_depth (gauge), csp_session_init_duration_seconds (histogram), csp_subprocess_rss_bytes (gauge per session), csp_api_cost_usd_total (counter), csp_query_error_total (counter), csp_circuit_breaker_state (gauge), csp_websocket_connections (gauge), csp_tool_execution_duration_seconds (histogram), csp_tool_execution_total (counter).

2. **Given** a Grafana dashboard JSON is provided,
   **When** imported into Grafana connected to the Prometheus instance,
   **Then** all panels render with real data from the running platform.

**Key Entities Involved**: MetricsRegistry, PrometheusExporter
**Key Fields**: metric_name, metric_type (gauge|counter|histogram), labels (session_id, tool_name, error_type)

---

### US-013: Graceful Shutdown (Priority: P2)

**As a** platform operator, **I want** the platform to shut down gracefully during deployments without losing any active sessions, **so that** rolling updates do not disrupt users.

**Why this priority**: Deployment without user disruption is a requirement for production. Without graceful shutdown, every deploy causes in-flight queries to fail and users to lose context. P2 because development/staging environments can tolerate hard stops.

**Independent Test**: Start the platform with an active session mid-query. Send SIGTERM. Verify: (1) the in-flight query completes, (2) the user receives a "Server shutting down" notification, (3) no new sessions are accepted, (4) the process exits cleanly after all sessions terminate. Requires SessionManager shutdown handler.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the platform receives SIGTERM with 2 active sessions (one mid-query, one idle),
   **When** the shutdown handler runs,
   **Then** the platform stops accepting new sessions immediately, sends "server_shutting_down" to all connected WebSockets, waits up to 30 seconds for the mid-query session to complete, terminates the idle session immediately, cleans up all subprocesses, and exits with code 0.

2. **Given** a rolling deployment is in progress in Kubernetes,
   **When** the old pod receives SIGTERM,
   **Then** the readiness probe immediately returns 503 (new traffic routes to new pod), active sessions complete their current queries, and the pod terminates within 60 seconds.

**Key Entities Involved**: ShutdownHandler, SessionManager, WebSocketConnection
**Key Fields**: shutdown_initiated_at, active_sessions_at_shutdown, shutdown_grace_period_seconds

---

### US-014: Health Check Endpoints (Priority: P2)

**As a** platform operator, **I want** Kubernetes-compatible health check endpoints, **so that** the orchestrator can route traffic correctly and restart unhealthy pods.

**Why this priority**: Health probes are required for any Kubernetes deployment. Without them, traffic can be routed to pods that are not ready (empty pre-warm pool) or unhealthy (crashed subprocess). P2 because development does not need probes.

**Independent Test**: Start the platform. Call each health endpoint. Verify: /live returns 200 when process is alive; /ready returns 200 when pool has capacity and DB is connected (503 otherwise); /startup returns 200 after initialization completes. Requires health route registration.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** the platform is fully initialized,
   **When** `GET /api/v1/health/live` is called,
   **Then** the response is 200 with body `{"status": "ok"}`.

2. **Given** the pre-warm pool is empty and all sessions are at capacity,
   **When** `GET /api/v1/health/ready` is called,
   **Then** the response is 503 with body `{"status": "not_ready", "reason": "pool_empty", "active_sessions": N, "max_sessions": M}`.

3. **Given** the platform is still initializing (pre-warm pool filling),
   **When** `GET /api/v1/health/startup` is called,
   **Then** the response is 503 until at least 1 pre-warm slot is filled, then 200 with `{"status": "started", "startup_duration_ms": X}`.

**Key Entities Involved**: HealthCheckRouter, SessionManager, DatabaseConnection
**Key Fields**: status, pool_depth, active_sessions, db_connected, circuit_breaker_state

---

### US-015: Circuit Breaker for API Outages (Priority: P3)

**As a** platform operator, **I want** the platform to detect Anthropic API outages and stop sending requests until the API recovers, **so that** users get fast error messages instead of hanging queries and I avoid retry storms.

**Why this priority**: Circuit breaking prevents cascading failures during API outages. P3 because basic error handling (try/catch with user-facing error) works for MVP; the circuit breaker adds resilience at scale.

**Independent Test**: Simulate API failures by mocking the SDK to return connection errors. After 5 failures in 60 seconds, verify the circuit opens. Verify new queries immediately return "API temporarily unavailable" without attempting a request. After 60 seconds, verify a probe query is sent. If it succeeds, verify the circuit closes and normal queries resume. Requires aiobreaker integration.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** 5 consecutive API requests have failed within 60 seconds,
   **When** a new user sends a message,
   **Then** the message is immediately rejected with "The AI service is temporarily unavailable. We are monitoring the situation." without sending a request to the API.

2. **Given** the circuit breaker is open,
   **When** 60 seconds have elapsed,
   **Then** a single probe query is sent to the API. If it succeeds, the circuit closes and normal operations resume.

3. **Given** the circuit breaker state changes (open, closed, half-open),
   **When** Prometheus scrapes metrics,
   **Then** the `csp_circuit_breaker_state` gauge reflects the current state (0=closed, 1=half_open, 2=open).

**Key Entities Involved**: CircuitBreaker, SessionManager
**Key Fields**: breaker_state (closed|half_open|open), failure_count, last_failure_at, last_probe_at

---

## Epic 4: Platform Security (Phase 2-3)

### US-016: Encrypted Secret Storage (Priority: P2)

**As a** platform operator, **I want** plugin secrets (API keys, database passwords) to be encrypted at rest, **so that** a database breach does not expose credentials.

**Why this priority**: Secret exposure is a top security risk. Storing plaintext API keys in the database is unacceptable for any production deployment. P2 because MVP has no plugins (no secrets to store).

**Independent Test**: Configure a plugin with a secret (e.g., Slack token). Query the database directly. Verify the stored value is encrypted (not plaintext). Call the plugin config API. Verify the secret is returned as "[REDACTED]" in the response. Requires cryptography.Fernet integration.

**Acceptance Scenarios** (Given/When/Then format):

1. **Given** an operator configures a plugin with a secret field (e.g., slack_token),
   **When** the configuration is saved to the database,
   **Then** the secret value is encrypted using Fernet (AES-128-CBC + HMAC-SHA256) before storage, and the plaintext is never written to disk or logs.

2. **Given** an operator retrieves plugin configuration via the API,
   **When** the response is returned,
   **Then** secret fields are replaced with "[REDACTED]" and the original encrypted value is never sent to the client.

3. **Given** the platform SECRET_KEY is rotated,
   **When** the admin runs the re-encryption utility,
   **Then** all stored secrets are decrypted with the old key and re-encrypted with the new key, and the utility reports how many secrets were re-encrypted.

**Key Entities Involved**: SecretStore, PluginConfig
**Key Fields**: plugin_name, config_key, encrypted_value, encryption_key_version

---

## Story Map Summary

| Priority | Story | Phase | Estimated Effort |
|----------|-------|-------|-----------------|
| P1 | US-001: Pre-Warmed Session Start | Phase 1 | 5 days |
| P1 | US-002: Streaming Chat Conversation | Phase 1 | 5 days |
| P1 | US-003: Tool Use Transparency | Phase 1 | 3 days |
| P1 | US-004: Session Memory Limits | Phase 1 | 5 days |
| P1 | US-005: Chat Input and Controls | Phase 1 | 3 days |
| P2 | US-006: Session Resume | Phase 1 | 3 days |
| P2 | US-007: Error Messages with Context | Phase 1 | 2 days |
| P2 | US-008: Plugin Registration via Manifest | Phase 2 | 5 days |
| P2 | US-009: RBAC with Three Roles | Phase 2 | 4 days |
| P2 | US-010: Per-User Cost Caps | Phase 2 | 3 days |
| P2 | US-011: Audit Logging | Phase 2 | 3 days |
| P2 | US-012: Prometheus Metrics | Phase 3 | 3 days |
| P2 | US-013: Graceful Shutdown | Phase 3 | 2 days |
| P2 | US-014: Health Check Endpoints | Phase 3 | 1 day |
| P3 | US-015: Circuit Breaker | Phase 3 | 2 days |
| P2 | US-016: Encrypted Secret Storage | Phase 2 | 2 days |

---

*End of User Stories*
