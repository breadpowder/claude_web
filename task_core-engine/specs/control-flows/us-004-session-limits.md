# Control Flow: US-004 - Session Memory and Duration Limits

## Success Path: Duration Limit

```
[Session Running Normally]
     |
     v (every 60 seconds)
+-----------------------------------------------------------------+
| Step 1: Duration Monitor Check                                   |
| ---------------------------------------------------------------- |
| Action: Compare current time to session.created_at               |
| Threshold: MAX_SESSION_DURATION_SECONDS (default 14400 = 4h)    |
| If elapsed < 90% of max: no action                              |
+-----------------------------------------------------------------+
     |
     v (at 90% of max duration)
+-----------------------------------------------------------------+
| Step 2: Duration Warning                                         |
| ---------------------------------------------------------------- |
| Trigger: elapsed >= 12,960 seconds (90% of 4 hours)             |
| WebSocket: {type: "session_warning",                             |
|   reason: "duration",                                             |
|   remaining_seconds: 1440,                                        |
|   message: "Session will end in 24 minutes. Save your work."}   |
| UI: Warning banner at top of chat                                |
+-----------------------------------------------------------------+
     |
     v (at 100% of max duration)
+-----------------------------------------------------------------+
| Step 3: Duration Limit Reached                                   |
| ---------------------------------------------------------------- |
| Check: Is a query currently in flight?                           |
|   If NO: proceed to Step 4 immediately                           |
|   If YES: wait up to 30s grace period for query to complete      |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 4: Session Termination                                      |
| ---------------------------------------------------------------- |
| Action: Cleanup subprocess (SIGTERM, wait 5s, SIGKILL)           |
| WebSocket: {type: "session_terminated",                          |
|   reason: "duration_limit",                                       |
|   message: "Session ended (4-hour limit reached).",              |
|   resume_url: "/chat?resume=abc123"}                             |
| UI: Termination dialog with "Start New Session" button           |
|   and resume link                                                 |
+-----------------------------------------------------------------+
     |
     v
[Session Ended -- User Can Resume or Start New]
```

## Success Path: RSS Memory Limit

```
[Session Running Normally]
     |
     v (every 30 seconds)
+-----------------------------------------------------------------+
| Step 1: RSS Monitor Check                                        |
| ---------------------------------------------------------------- |
| Action: Read /proc/<pid>/status for VmRSS                       |
| Threshold: MAX_SESSION_RSS_MB (default 4096 = 4GB)              |
| If RSS < threshold: no action                                    |
| Metric: csp_subprocess_rss_bytes{session_id} = current RSS      |
+-----------------------------------------------------------------+
     |
     v (RSS exceeds threshold)
+-----------------------------------------------------------------+
| Step 2: Flag Session for Graceful Restart                        |
| ---------------------------------------------------------------- |
| Action: session.state = "restart_pending"                        |
| Log: "WARNING: Session abc123 RSS={rss_mb}MB exceeds            |
|   threshold={threshold_mb}MB. Flagged for restart."              |
| Check: Is a query currently in flight?                           |
|   If YES: wait for query to complete (up to 30s grace)           |
|   If NO: proceed to Step 3 immediately                           |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 3: User Notification                                        |
| ---------------------------------------------------------------- |
| WebSocket: {type: "session_restarting",                          |
|   reason: "memory_limit",                                         |
|   message: "Session restarting to maintain performance.          |
|   Your conversation will be preserved."}                         |
| UI: Toast notification (non-blocking)                            |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 4: Subprocess Cleanup                                       |
| ---------------------------------------------------------------- |
| Action: SIGTERM to subprocess PID                                |
| Wait: 5 seconds for graceful exit                                |
| If still alive: SIGKILL                                          |
| Cleanup: Remove session from active map                          |
| Cache cleanup: Delete stale shell snapshots from ~/.claude/      |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 5: New Session Creation with Resume                         |
| ---------------------------------------------------------------- |
| Action: Create new ClaudeSDKClient with resume=session_id        |
| Source: Pre-warm pool (if available) or cold start                |
| Result: New session with previous conversation context           |
| WebSocket: {type: "session_ready",                               |
|   session_id: "abc123",                                           |
|   status: "resumed",                                              |
|   message: "Session restored. You can continue."}               |
| UI: Chat continues seamlessly                                    |
+-----------------------------------------------------------------+
     |
     v
[User Continues Working in Resumed Session]
```

## Edge Case Branches

### EC-003: Duration Limit Reached Mid-Query (Step 3 Duration)

```
+-----------------------------------------------------------------+
| Trigger: MAX_DURATION reached while query is processing          |
| ---------------------------------------------------------------- |
| Action: Wait up to 30 seconds for query to complete              |
| If query completes within 30s: user sees response, then          |
|   termination dialog                                              |
| If query does NOT complete in 30s: interrupt query               |
|   (client.interrupt()), then terminate                           |
| WebSocket: {type: "session_terminated",                          |
|   reason: "duration_limit",                                       |
|   message: "Session ended. Your last response may be             |
|   incomplete.",                                                    |
|   resume_url: "/chat?resume=abc123"}                             |
+-----------------------------------------------------------------+
```

### EC-004: RSS Exceeds Threshold Mid-Query (Step 2 Memory)

```
+-----------------------------------------------------------------+
| Trigger: RSS > 4GB while query is processing                    |
| ---------------------------------------------------------------- |
| Action: Flag for restart AFTER current query completes           |
| DO NOT interrupt the in-flight query                             |
| Rationale: User is waiting for a response; interrupting is       |
|   worse UX than allowing memory to grow temporarily              |
| Grace limit: If RSS > 2x threshold (8GB), force-interrupt       |
|   to prevent container OOM                                       |
+-----------------------------------------------------------------+
```

### EC-007: Resume Fails Due to Corrupted Session Data (Step 5 Memory)

```
+-----------------------------------------------------------------+
| Trigger: ClaudeSDKClient(resume=session_id) raises exception     |
| ---------------------------------------------------------------- |
| Action: Log corruption details                                   |
| Archive: Move corrupted session metadata to "corrupted" table    |
| Fallback: Create fresh session (no resume)                       |
| WebSocket: {type: "session_ready",                               |
|   session_id: "new_id",                                           |
|   status: "new",                                                  |
|   message: "Previous session could not be restored.              |
|   Starting a new session."}                                      |
| UI: Info banner explaining the situation                         |
+-----------------------------------------------------------------+
```

### EC-023: Disk Space Exhausted (Step 1 Memory)

```
+-----------------------------------------------------------------+
| Trigger: ~/.claude/ directory exceeds disk quota                 |
| ---------------------------------------------------------------- |
| Detection: Periodic disk usage check (every 5 minutes)           |
| Warning: Alert at 80% of container disk limit                    |
| Action at 95%: Proactive cleanup of old shell snapshots          |
|   (delete snapshots older than 24 hours)                         |
| Action at 100%: Session flagged for restart (same as RSS flow)   |
| Log: "WARNING: Disk usage for session abc123 at {percent}%"     |
+-----------------------------------------------------------------+
```

### Zombie Process Detection (Ongoing)

```
+-----------------------------------------------------------------+
| Trigger: Periodic scan every 60 seconds                          |
| ---------------------------------------------------------------- |
| Action: List all child processes of the platform process         |
| Check: For each child PID, verify it maps to an active session   |
| If orphaned PID found:                                           |
|   1. Log: "WARNING: Orphaned subprocess PID={pid} detected"     |
|   2. Send SIGTERM, wait 5s, SIGKILL                             |
|   3. Increment metric: csp_zombie_processes_cleaned_total        |
| If zombie (defunct) process found:                               |
|   1. Reap via os.waitpid()                                      |
|   2. Log: "INFO: Reaped zombie process PID={pid}"               |
+-----------------------------------------------------------------+
```

## Flow Summary Table

| Monitor | Check Interval | Warning | Action | Recovery |
|---------|---------------|---------|--------|----------|
| Duration | 60s | 90% of max (banner) | Terminate after grace period | Resume in new session |
| RSS Memory | 30s | At threshold (notification) | Graceful restart | Resume in new session |
| Disk Usage | 300s | 80% of limit (operator alert) | Cleanup snapshots; restart at 100% | Automatic cleanup |
| Zombie Processes | 60s | N/A | Kill orphaned, reap zombies | Automatic |

---

*End of Control Flow: US-004*
