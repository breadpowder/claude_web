# Architecture: Core Engine MVP

> **Feature**: core-engine
> **Date**: 2026-02-14
> **Authority**: ADR-001 (Platform Strategy), ADR-002 (Technical Architecture)

---

## 1. System Overview

The core engine is a Python/FastAPI backend that wraps Claude Agent SDK, exposing three communication layers to serve browser frontends, external services, and operators. Each SDK session spawns a CLI subprocess (~500MB-1GB RAM, 20-30s cold start). A pre-warming pool (asyncio.Queue) eliminates cold start for users. Session metadata persists in JSON files; conversation content persists in SDK's own JSONL files. The platform deploys as a single Docker container on a 16GB host supporting 10 concurrent sessions.

---

## 2. Component Diagram

```
                          +-----------------------+
                          |    Browser (React)    |
                          |  Zustand stores:      |
                          |  chatStore            |
                          |  sessionStore         |
                          |  toolStore            |
                          |  uiStore              |
                          +----------+------------+
                                     |
                         AG-UI (SSE over HTTP)
                                     |
+------------------+     +-----------v-----------+     +------------------+
| External Service |---->| FastAPI Application   |     | Operator / CLI   |
| (OpenAI client)  |     |                       |<----|                  |
+------------------+     | +-------------------+ |     +------------------+
         |               | | AG-UI Endpoint    | |            |
   POST /v1/chat/        | | POST /agent/run   | |      GET /api/v1/...
   completions           | +-------------------+ |
         |               | +-------------------+ |
         +-------------->| | OpenAI API        | |
                         | | POST /v1/chat/    | |
                         | | completions       | |
                         | +-------------------+ |
                         | +-------------------+ |
                         | | REST API          | |
                         | | /api/v1/sessions  | |
                         | | /api/v1/health    | |
                         | | /api/v1/extensions| |
                         | +-------------------+ |
                         +----------+------------+
                                    |
                  +-----------------+-----------------+
                  |                 |                 |
         +--------v------+  +------v-------+  +------v--------+
         | SessionManager|  | ExtensionLdr |  | JSONSession   |
         |               |  |              |  | Index         |
         | - create()    |  | - scan_mcp() |  |               |
         | - query()     |  | - scan_skl() |  | - read()      |
         | - interrupt() |  | - scan_cmd() |  | - write()     |
         | - destroy()   |  |              |  | - list()      |
         +--------+------+  +--------------+  | - atomic I/O  |
                  |                            +---------------+
         +--------v--------+
         |  PreWarmPool    |
         |  asyncio.Queue  |
         |                 |
         |  - get()        |
         |  - replenish()  |
         +--------+--------+
                  |
         +--------v--------------+
         | ClaudeSDKClient (x10) |
         | (CLI subprocess each) |
         +-----------+-----------+
                     |
         +-----------v-----------+
         | SubprocessMonitor     |
         |                       |
         | - check_rss()         |
         | - check_duration()    |
         | - cleanup_zombies()   |
         | - graceful_restart()  |
         +----------+------------+
                    |
         +----------v------------+
         | CLI Subprocess        |
         | (~500MB-1GB RSS each) |
         |                       |
         | Session data:         |
         | ~/.claude/projects/   |
         |   <cwd>/<session>.jsonl|
         +----------+------------+
                    |
         +----------v-----------+
         | MCP Servers (stdio)  |
         | Skills (SKILL.md)    |
         | Commands (./commands)|
         +-----------------------+
```

---

## 3. Data Flow Diagram

### 3.1 AG-UI Chat Flow (Frontend)

```
Browser                    FastAPI                   SessionManager        SDK Subprocess
  |                           |                           |                      |
  |-- POST /agent/run ------->|                           |                      |
  |   (AG-UI RunAgentInput)   |                           |                      |
  |                           |-- query(session_id, msg)->|                      |
  |                           |                           |-- client.query() --->|
  |                           |                           |                      |
  |<-- SSE: RunStartedEvent --|<-- yield event -----------|                      |
  |                           |                           |<-- StreamEvent ------|
  |<-- SSE: TextMsgStart -----|<-- yield event -----------|                      |
  |<-- SSE: TextMsgContent ---|<-- yield event -----------|                      |
  |<-- SSE: TextMsgContent ---|<-- yield event -----------|                      |
  |                           |                           |<-- ToolUseBlock -----|
  |<-- SSE: ToolCallStart ----|<-- yield event -----------|                      |
  |<-- SSE: ToolCallEnd ------|<-- yield event -----------|<-- ToolResultBlock --|
  |                           |                           |<-- StreamEvent ------|
  |<-- SSE: TextMsgEnd -------|<-- yield event -----------|                      |
  |<-- SSE: RunFinishedEvent -|<-- yield event -----------|<-- ResultMessage ----|
  |                           |                           |                      |
```

### 3.2 OpenAI-Compliant API Flow (Server-to-Server)

```
External Service           FastAPI                   SessionManager        SDK Subprocess
  |                           |                           |                      |
  |-- POST /v1/chat/ -------->|                           |                      |
  |   completions             |-- acquire_session() ----->|                      |
  |   {messages, stream:true} |                           |-- pool.get() ------->|
  |                           |<-- session_id ------------|                      |
  |                           |-- query(session_id) ----->|                      |
  |                           |                           |-- client.query() --->|
  |                           |                           |                      |
  |<-- SSE: {choices:[       -|<-- translate(event) ------|<-- StreamEvent ------|
  |     {delta:{content:..}}]}|                           |                      |
  |<-- SSE: {choices:[       -|<-- translate(event) ------|<-- StreamEvent ------|
  |     {delta:{content:..}}]}|                           |                      |
  |<-- SSE: {choices:[       -|<-- translate(event) ------|<-- ResultMessage ----|
  |     {finish_reason:stop}]}|                           |                      |
  |<-- SSE: [DONE] -----------|                           |                      |
  |                           |-- release_session() ----->|                      |
```

### 3.3 Session Lifecycle Data Flow

```
                    +------------------+
                    | Platform Startup |
                    +--------+---------+
                             |
              +--------------v--------------+
              | 1. Validate ANTHROPIC_API_KEY|
              |    (EC-098: fail if invalid) |
              +--------------+--------------+
                             |
              +--------------v--------------+
              | 2. ExtensionLoader.scan()   |
              |    Read mcp.json, skills/,  |
              |    commands/                |
              +--------------+--------------+
                             |
              +--------------v--------------+
              | 3. JSONSessionIndex.init()  |
              |    Create dir if missing    |
              |    (EC-NEW-001)             |
              +--------------+--------------+
                             |
              +--------------v--------------+
              | 4. PreWarmPool.fill()       |
              |    Init N ClaudeSDKClients  |
              |    (EC-022: fail if all     |
              |     attempts fail)          |
              +--------------+--------------+
                             |
              +--------------v--------------+
              | 5. Start SubprocessMonitor  |
              |    Background tasks:        |
              |    - RSS check (30s)        |
              |    - Duration check (60s)   |
              |    - Zombie cleanup (60s)   |
              |    - Disk usage (300s)      |
              +--------------+--------------+
                             |
              +--------------v--------------+
              | 6. Readiness probe: 200 OK  |
              |    (pool depth >= 1)        |
              +--------------+--------------+
                             |
                    [Accepting Traffic]
```

---

## 4. Control Flow with Edge Case Branches

### 4.1 Session Creation (US-001)

```
                    [Session Request]
                          |
                          v
         +-------------------------------+
         | SessionManager.create_session()|
         +---------------+---------------+
                         |
              +----------v----------+
              | PreWarmPool.get()   |
              +----------+----------+
                         |
              +----------+----------+
              |                     |
         [Has slot]           [Pool empty]
              |                     |
              v                     v
+-------------------+   +----------------------+
| Assign pre-warmed |   | EC-001: Cold start   |
| ClaudeSDKClient   |   | Return {status:      |
| Duration: < 100ms |   |   "creating",        |
+--------+----------+   |   estimated_s: 30}   |
         |              | Init new client      |
         |              | Duration: 20-30s     |
         |              +----------+-----------+
         |                         |
         +------------+------------+
                      |
         +------------v------------+
         | JSONSessionIndex.write()|
         | Atomic: temp + rename   |
         | File lock via filelock  |
         +------------+------------+
                      |
         +------------v--------------+
         | Return session_id, status |
         | Source: "pre-warm"|"cold"  |
         +------------+--------------+
                      |
         +------------v--------------+
         | PreWarmPool.replenish()   |
         | Background: asyncio.task  |
         | Duration: 20-30s          |
         |                           |
         | EC-014: If rate limited,  |
         |   pause 5 min, backoff    |
         +---------------------------+
```

### 4.2 Chat Message Processing (US-002)

```
                [User Message via AG-UI "start run"]
                          |
                          v
         +-------------------------------+
         | Validate: session exists,     |
         | no run in progress (G-003)    |
         +---------------+---------------+
                         |
              +----------+----------+
              |                     |
         [Valid]             [Run in progress]
              |                     |
              v                     v
+-------------------+   +----------------------+
| SessionManager    |   | EC-NEW-004: Reject   |
| .query(sid, msg)  |   | AG-UI error event:   |
|                   |   | "Query in progress"  |
+--------+----------+   +----------------------+
         |
         v
+----------------------------+
| SDK: client.query(prompt)  |
| Emit: RunStartedEvent      |
+------------+---------------+
             |
    +--------v--------+
    | Stream SDK events|
    +--------+--------+
             |
     +-------+-------+
     |               |
[Text events]   [Tool events]
     |               |
     v               v
+-----------+  +------------------+
| TextMsg   |  | ToolCallStart    |
| Start     |  | ToolCallArgs     |
| Content   |  | ToolCallEnd      |
| End       |  | (EC-NEW-003:     |
+-----------+  |  truncate >1MB)  |
     |         +------------------+
     |               |
     +-------+-------+
             |
             v
+----------------------------+
| SDK: ResultMessage         |
| Emit: RunFinishedEvent     |
| Update: JSONSessionIndex   |
|   (message_count, cost)    |
+----------------------------+
             |
     +-------+-------+
     |               |
[Success]      [Error]
     |               |
     v               v
+-----------+  +---------------------+
| Response  |  | Stream error:       |
| complete  |  |   AG-UI RunError    |
| Cost info |  |   Partial preserved |
+-----------+  | EC-NEW-002: Client  |
               |   disconnect: abort |
               |   run, user retries |
               +---------------------+
```

### 4.3 Resource Monitoring (US-004)

```
    [SubprocessMonitor Background Tasks]
                    |
         +----------+-----------+
         |          |           |
    [RSS check]  [Duration]  [Zombie]
    every 30s    every 60s   every 60s
         |          |           |
         v          v           v
+-------------+ +----------+ +----------------+
| Read /proc/ | | Compare  | | List children  |
| <pid>/status| | elapsed  | | of platform PID|
| for VmRSS   | | vs max   | |                |
+------+------+ +-----+----+ +-------+--------+
       |              |              |
  +----+----+    +----+----+   +----+----+
  |         |    |         |   |         |
[< 2GB]  [>=2GB] [<90%]  [>=90%] [Clean] [Orphan]
  |         |    |         |   |         |
  v         v    v         v   v         v
[no-op]  +------+ [no-op] +------+ [no-op] +-------+
         |EC-004|         |EC-003|         |SIGTERM |
         |Grace |         |Warn  |         |wait 5s |
         |rst   |         |via   |         |SIGKILL |
         |after |         |AG-UI |         +-------+
         |query |         |custom|
         |done  |         |event |
         +--+---+         +--+---+
            |                |
            v                v (at 100%)
  +-------------------+  +-----------------+
  | Notify via AG-UI  |  | Grace: wait 30s |
  | "Session restart" |  | for in-flight   |
  | Create new session|  | query           |
  | with resume=sid   |  | Then terminate  |
  +-------------------+  | Notify user     |
                         +-----------------+
```

### 4.4 OpenAI-Compliant API Processing (US-008)

```
         [POST /v1/chat/completions]
                    |
                    v
         +-------------------+
         | Parse request     |
         | Validate messages |
         | EC-NEW-008: Ignore|
         | unsupported params|
         +--------+----------+
                  |
         +--------v--------+
         | Acquire session  |
         | from pool        |
         +--------+--------+
                  |
         +--------+--------+
         |                 |
    [Available]       [No capacity]
         |                 |
         v                 v
+----------------+  +-------------------+
| Translate msg  |  | EC-NEW-007: 503   |
| to SDK prompt  |  | Retry-After: 30   |
| Send query     |  | OpenAI error fmt  |
+--------+-------+  +-------------------+
         |
    +----+----+
    |         |
[stream]  [no stream]
    |         |
    v         v
+--------+ +----------+
| SSE    | | Buffer   |
| chunks:| | entire   |
| delta  | | response |
| content| | Return   |
| + tools| | single   |
+---+----+ | JSON     |
    |      +----------+
    v
+-------------------+
| finish_reason +   |
| usage stats       |
| data: [DONE]      |
|                   |
| EC-NEW-009: If    |
| terminated mid-   |
| stream: error evt |
| + [DONE]          |
+-------------------+
    |
    v
+-------------------+
| Release session   |
| back to pool      |
+-------------------+
```

---

## 5. Error Handling Matrix

| Component | Error Type | Edge Case | Response | Recovery |
|-----------|------------|-----------|----------|----------|
| PreWarmPool | All init attempts fail | EC-022 | Readiness probe 503 | Operator fixes root cause, restarts |
| PreWarmPool | Rate limited during replenish | EC-014 | Pause 5 min, exponential backoff | Auto-retry after backoff |
| PreWarmPool | Pool empty on session request | EC-001 | Cold start fallback, "Preparing..." UI | Auto-replenish in background |
| SessionManager | API key invalid on startup | EC-098 | Exit code 1, log CRITICAL | Operator corrects key, restarts |
| SessionManager | Resume fails (corrupted data) | EC-007 | Fresh session, user notified | Automatic |
| SessionManager | Concurrent runs on same session | EC-010/NEW-004 | AG-UI error event, reject | User waits for current run |
| SubprocessMonitor | RSS exceeds 2GB | EC-004 | Flag for graceful restart | Resume in new session |
| SubprocessMonitor | Duration at 90% of max | EC-003 | AG-UI custom event warning | User saves work |
| SubprocessMonitor | Duration at 100%, query in flight | EC-003 | 30s grace, then terminate | Resume in new session |
| SubprocessMonitor | Zombie process detected | Ongoing | SIGTERM, wait 5s, SIGKILL | Automatic |
| SubprocessMonitor | Disk quota exceeded | EC-023 | Cleanup old snapshots, restart at 100% | Automatic |
| AG-UI Endpoint | Client disconnect mid-stream | EC-NEW-002 | Abort run | User retries |
| AG-UI Endpoint | Large tool result (>1MB) | EC-NEW-003 | Truncate + REST fallback | User fetches full via REST |
| AG-UI Endpoint | Cancel race (run already done) | EC-NEW-005 | Idempotent, ignore cancel | No action needed |
| OpenAI API | No capacity | EC-NEW-007 | 503 + Retry-After | Caller retries |
| OpenAI API | Session terminated mid-stream | EC-NEW-009 | SSE error + [DONE] | Caller retries |
| JSONSessionIndex | First startup (no file) | EC-NEW-001 | Create dir + empty JSON | Automatic |
| JSONSessionIndex | Concurrent write | EC-NEW-010 | File locking + atomic write | Automatic |
| JSONSessionIndex | Corrupted JSON | EC-NEW-011 | Recover from .bak or re-create | Sessions list lost but content preserved |
| JSONSessionIndex | Unbounded growth | EC-NEW-012 | Periodic cleanup (30-day retention) | Automatic |
| ExtensionLoader | mcp.json deleted | EC-NEW-013 | New sessions: no MCP; active: unaffected | Operator re-creates file |
| ExtensionLoader | MCP binary not found | EC-NEW-014 | That server unavailable; others work | Operator installs binary |
| ExtensionLoader | Malformed SKILL.md | EC-NEW-015 | Ignored, logged | Operator fixes file |
| ExtensionLoader | Env var injection attempt | EC-116 | Blocklist applied, logged | Automatic |

---

## 6. Component Interaction Summary

### Runtime Dependencies

```
FastAPI Application
  |
  +-- AG-UI Endpoint (POST /agent/run)
  |     +-- SessionManager.query()
  |     +-- AG-UI EventEncoder (ag_ui.encoder)
  |
  +-- OpenAI API Endpoint (POST /v1/chat/completions)
  |     +-- SessionManager.create_session() or reuse
  |     +-- SessionManager.query()
  |     +-- OpenAIAdapter.translate()
  |     +-- sse-starlette (SSE transport)
  |
  +-- REST API Endpoints (/api/v1/*)
  |     +-- SessionManager (session CRUD)
  |     +-- JSONSessionIndex (list/get)
  |     +-- PreWarmPool (health/ready)
  |     +-- ExtensionLoader (extension listing)
  |
  +-- Startup
  |     +-- ExtensionLoader.scan()
  |     +-- JSONSessionIndex.init()
  |     +-- PreWarmPool.fill()
  |     +-- SubprocessMonitor.start()
  |
  +-- Background Tasks
        +-- PreWarmPool.replenish() (on demand)
        +-- SubprocessMonitor.check_rss() (every 30s)
        +-- SubprocessMonitor.check_duration() (every 60s)
        +-- SubprocessMonitor.cleanup_zombies() (every 60s)
        +-- SubprocessMonitor.check_disk() (every 300s)
        +-- JSONSessionIndex.cleanup_old() (daily)
```

### Data Store Interactions

```
JSONSessionIndex (JSON files on disk)
  |-- Read/Write: SessionManager (create, update, destroy)
  |-- Read: REST API (list sessions)
  |-- Write: SubprocessMonitor (update status on termination)
  |
  Method: Atomic write (temp file + rename)
  Locking: filelock library
  Location: configurable, default ~/.claude-web/sessions/

SDK JSONL Files (managed by CLI subprocess)
  |-- Read/Write: CLI subprocess (automatic)
  |-- Read: SDK on resume (resume=session_id)
  |
  Location: ~/.claude/projects/<mangled-cwd>/<session_id>.jsonl
  Note: Platform does NOT read or write these directly

Extension Config Files (read-only by platform)
  |-- mcp.json (project root)
  |-- ./skills/<name>/SKILL.md
  |-- ./commands/<name>/
  |
  Read: ExtensionLoader on startup + each new session creation
```

---

*End of Architecture Document*
