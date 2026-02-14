# Control Flow: US-002 - Streaming Chat Conversation

## Success Path (Happy Path)

```
[User Types Message and Presses Enter]
     |
     v
+-----------------------------------------------------------------+
| Step 1: Client Sends Message                                     |
| ---------------------------------------------------------------- |
| Input: User text (validated: non-empty, < 32k chars)             |
| WebSocket message: {type: "user_message",                        |
|   text: "How many active users last month?",                     |
|   seq: 5}                                                        |
| UI: Message appears in MessageList immediately (optimistic)      |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 2: Server Processes Message                                 |
| ---------------------------------------------------------------- |
| Action: SessionManager.query(session_id, message.text)           |
| SDK call: client.query(prompt=message.text)                      |
| WebSocket ack: {type: "message_received", seq: 5}               |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 3: Streaming Response Begins                                |
| ---------------------------------------------------------------- |
| SDK event: StreamEvent with delta tokens                         |
| WebSocket messages: {type: "stream_delta",                       |
|   delta: "I'll", seq: 6}                                        |
|   {type: "stream_delta", delta: " query", seq: 7}               |
|   ... (token by token)                                           |
| UI: Tokens appended to Claude's message bubble progressively     |
| Typing indicator: animated cursor visible                        |
+-----------------------------------------------------------------+
     |
     v (if Claude invokes a tool)
+-----------------------------------------------------------------+
| Step 4: Tool Invocation (Optional)                               |
| ---------------------------------------------------------------- |
| SDK event: ToolUseBlock                                          |
| WebSocket: {type: "tool_use",                                    |
|   tool: "mcp__postgres__execute_sql",                            |
|   input: {query: "SELECT COUNT(*)..."},                          |
|   seq: 20}                                                       |
| UI: ToolUseCard renders (see US-003 flow)                        |
|                                                                   |
| ... tool executes ...                                            |
|                                                                   |
| SDK event: ToolResultBlock                                       |
| WebSocket: {type: "tool_result",                                 |
|   result: {count: 45231},                                        |
|   duration_ms: 1200, seq: 21}                                    |
| UI: ToolUseCard updates to "Complete (1.2s)"                     |
+-----------------------------------------------------------------+
     |
     v (Claude continues streaming after tool result)
+-----------------------------------------------------------------+
| Step 5: Response Continues After Tool                            |
| ---------------------------------------------------------------- |
| More stream_delta messages with Claude's interpretation           |
| "Last month you had 45,231 active users."                        |
+-----------------------------------------------------------------+
     |
     v
+-----------------------------------------------------------------+
| Step 6: Response Complete                                        |
| ---------------------------------------------------------------- |
| SDK event: ResultMessage                                         |
| WebSocket: {type: "response_complete",                           |
|   cost_usd: 0.024,                                               |
|   session_id: "abc123",                                           |
|   turn_count: 3, seq: 35}                                        |
| UI: Typing indicator disappears                                  |
| UI: Cost shown in subtle footer: "$0.02"                         |
| Input bar: re-enabled for next message                           |
+-----------------------------------------------------------------+
     |
     v
[User Can Send Next Message]

Total elapsed: 2-15 seconds depending on tool invocations
First token: < 2 seconds (pre-warmed session)
```

## Edge Case Branches

### EC-020: User Sends Message While Query In Flight (Step 1)

```
+-----------------------------------------------------------------+
| Trigger: User presses Enter while Claude is still streaming      |
| ---------------------------------------------------------------- |
| Action: Queue the message client-side                            |
| UI: Input bar shows "Waiting for current response..."            |
| Behavior: After response_complete, queued message is sent        |
|   automatically                                                  |
| Alternative: If user wants to override, Ctrl+Shift+X interrupts |
|   current response, then new message is sent                     |
+-----------------------------------------------------------------+
```

### Stream Error Mid-Response (Step 3/5)

```
+-----------------------------------------------------------------+
| Trigger: API timeout, connection error, or SDK exception         |
| ---------------------------------------------------------------- |
| WebSocket: {type: "stream_error",                                |
|   error: "Response interrupted",                                  |
|   partial_preserved: true, seq: 25}                               |
| UI: Partial response preserved in message bubble                 |
|   Error indicator: "Response interrupted. [Retry]"               |
| Recovery: User clicks Retry or sends new message                 |
| Partial text: remains visible (not deleted)                      |
+-----------------------------------------------------------------+
```

### EC-028: Token Rate Exceeds Frontend Capacity (Step 3)

```
+-----------------------------------------------------------------+
| Trigger: SDK streams 50+ tokens/second                           |
| ---------------------------------------------------------------- |
| Mitigation: React useTransition batches state updates            |
| Fallback: If backpressure detected, batch tokens client-side     |
|   (render every 100ms instead of per-token)                      |
| Metric: Monitor client-side render queue depth                   |
| Effect: Slight visual delay (100ms) but no dropped tokens        |
+-----------------------------------------------------------------+
```

### EC-032: User Sends Second Message Before First Completes (Step 1)

```
+-----------------------------------------------------------------+
| Trigger: Rapid typing, user sends two messages quickly           |
| ---------------------------------------------------------------- |
| Design Decision: Reject second message with clear error          |
| WebSocket: {type: "error",                                       |
|   code: "query_in_progress",                                     |
|   message: "Please wait for the current response to complete."}  |
| UI: Input bar shows brief warning, message not sent              |
| Recovery: After response_complete, user can send normally        |
+-----------------------------------------------------------------+
```

### EC-009: Browser Tab Closed Mid-Stream (Step 3/5)

```
+-----------------------------------------------------------------+
| Trigger: WebSocket disconnect detected by server                 |
| ---------------------------------------------------------------- |
| Action: Query continues server-side (no interruption)            |
| Buffer: Results buffered for reconnection (5 min TTL, 100 msgs) |
| Timer: If user reconnects within 5 min, buffer replayed          |
| Timer: If user does not reconnect within 60s, call               |
|   client.interrupt() to stop wasting API quota                   |
| Cost: Completed portion is billed normally                       |
+-----------------------------------------------------------------+
```

### EC-035: WebSocket Disconnects During Tool Execution (Step 4)

```
+-----------------------------------------------------------------+
| Trigger: Network drop while tool is executing                    |
| ---------------------------------------------------------------- |
| Action: Tool execution continues (server-side)                   |
| Buffer: Tool result buffered for reconnection                    |
| On reconnect: client sends last_message_seq                      |
| Server replays: all messages from last_message_seq onward        |
| UI: User sees tool execution complete after reconnect            |
+-----------------------------------------------------------------+
```

## Flow Summary Table

| Step | Success Outcome | Edge Cases | Design Decision |
|------|-----------------|------------|-----------------|
| 1 | Message sent via WebSocket | EC-020 (queued), EC-032 (rejected) | Reject duplicate, queue if interrupted |
| 2 | SDK processes message | None (internal) | N/A |
| 3 | Tokens stream to UI | Stream error, EC-028 (high rate) | Preserve partial; batch if needed |
| 4 | Tool executes and shows result | EC-035 (disconnect mid-tool) | Buffer results for reconnect |
| 5 | Response continues | Same as Step 3 | Same mitigations |
| 6 | Response complete with cost | None | Show cost footer |

---

*End of Control Flow: US-002*
