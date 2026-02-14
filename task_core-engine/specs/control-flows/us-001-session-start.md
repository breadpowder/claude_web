# Control Flow: US-001 - Pre-Warmed Session Start

## Success Path (Happy Path)

```
[User Opens Browser]
     |
     v
+-----------------------------------------------------------------+
| Step 1: Load Chat UI                                             |
| ---------------------------------------------------------------- |
| Input: Browser navigates to platform URL                         |
| Action: React app loads, establishes WebSocket connection         |
| Auth: API key sent in WebSocket upgrade header                   |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 2: WebSocket Authentication                                 |
| ---------------------------------------------------------------- |
| Input: API key (Phase 1) or JWT token (Phase 2)                 |
| Validation: Verify key/token validity                            |
| On success: WebSocket connection accepted                        |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 3: Session Assignment from Pre-Warm Pool                    |
| ---------------------------------------------------------------- |
| Action: SessionManager.get_or_create_session(user_id)            |
| Pool check: PreWarmPool.get() (non-blocking)                     |
| If pool has slot: assign pre-warmed ClaudeSDKClient              |
| Expected duration: < 100ms                                       |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 4: Session Ready Notification                               |
| ---------------------------------------------------------------- |
| WebSocket message: {type: "session_ready",                       |
|   session_id: "abc123", status: "ready",                         |
|   source: "pre-warmed"}                                          |
| UI shows: "Ready" status                                         |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 5: Pool Replenishment (Background)                          |
| ---------------------------------------------------------------- |
| Trigger: Pool depth dropped below target                         |
| Action: asyncio.create_task(prewarm_pool.replenish())            |
| Duration: 20-30s (background, no user impact)                    |
+-----------------------------------------------------------------+
     |
     v
[User Sends First Message --> US-002 Flow]

Total elapsed: < 3 seconds (user perceives instant start)
```

## Edge Case Branches

### EC-001: Pre-Warm Pool Empty (Step 3)

```
+-----------------------------------------------------------------+
| Trigger: PreWarmPool.get() returns None (pool exhausted)         |
| ---------------------------------------------------------------- |
| Action: Fall back to cold start                                  |
| WebSocket message: {type: "session_creating",                    |
|   status: "preparing",                                           |
|   estimated_seconds: 30}                                         |
| UI shows: "Preparing your session (up to 30 seconds)..."        |
|   with progress indicator                                        |
| Duration: 20-30 seconds                                          |
| Recovery: Session created via ClaudeSDKClient() cold init        |
|   --> continue to Step 4 with source: "cold-start"              |
+-----------------------------------------------------------------+
```

### EC-022: All Pre-Warm Attempts Fail on Startup (Before Step 1)

```
+-----------------------------------------------------------------+
| Trigger: Platform startup, 0/N pre-warm attempts succeeded       |
| ---------------------------------------------------------------- |
| Action: Readiness probe returns 503                              |
| Log: "CRITICAL: Pre-warm pool initialization failed.             |
|   Reason: [API key invalid | rate limited | network error]"      |
| Effect: Load balancer does not route traffic to this pod          |
| Recovery: Operator fixes root cause, restarts pod                |
| UI: User never reaches this pod (503 from load balancer)         |
+-----------------------------------------------------------------+
```

### EC-014: API Rate Limit During Pre-Warm (Step 5)

```
+-----------------------------------------------------------------+
| Trigger: Pre-warm SDK call returns 429 (rate limited)            |
| ---------------------------------------------------------------- |
| Action: Pause pre-warm operations for 5 minutes                  |
| Log: "WARNING: Pre-warm rate limited. Pausing for 300s."         |
| Metric: csp_prewarm_failures_total{reason="rate_limit"}++        |
| Effect: Pool not replenished during pause; cold starts if pool   |
|   depletes during this window                                    |
| Recovery: After 5 min, retry pre-warm. If still failing, extend  |
|   backoff to 10 min.                                             |
+-----------------------------------------------------------------+
```

### EC-098: Invalid API Key on Startup (Before Step 1)

```
+-----------------------------------------------------------------+
| Trigger: Platform startup, test query fails with auth error      |
| ---------------------------------------------------------------- |
| Action: Fail startup immediately                                 |
| Log: "CRITICAL: ANTHROPIC_API_KEY is invalid or expired.         |
|   Pre-warm failed. Server cannot start."                         |
| Exit: Process exits with code 1                                  |
| Recovery: Operator corrects API key, restarts pod                |
+-----------------------------------------------------------------+
```

### WebSocket Auth Failure (Step 2)

```
+-----------------------------------------------------------------+
| Trigger: Invalid API key or expired JWT                          |
| ---------------------------------------------------------------- |
| Action: Reject WebSocket upgrade with 401                        |
| Response: HTTP 401 Unauthorized                                  |
| UI: Shows login page (Phase 2) or "Invalid API key" error        |
| Recovery: User provides valid credentials                        |
+-----------------------------------------------------------------+
```

## Flow Summary Table

| Step | Success Outcome | Edge Cases | Design Decision |
|------|-----------------|------------|-----------------|
| 1 | Chat UI loads | None (static assets) | N/A |
| 2 | WebSocket authenticated | Auth failure | 401 rejection |
| 3 | Session assigned from pool | EC-001 (pool empty), EC-022 (startup fail), EC-098 (bad API key) | Cold start fallback with progress UI |
| 4 | User sees "Ready" | None | < 3s total |
| 5 | Pool replenished | EC-014 (rate limited) | 5-min backoff |

---

*End of Control Flow: US-001*
