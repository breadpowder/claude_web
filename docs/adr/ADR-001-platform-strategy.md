# ADR-001: Platform Strategy

> **Status**: Accepted
> **Date**: 2026-02-14
> **Decision Makers**: Core team (small team)
> **Context Source**: `task_core-engine/` planning artifacts

---

## Context

The team needs to deliver a web-based interface where users interact with Claude as if they were using the Claude CLI -- same tools, same MCP servers, same skills -- but through a browser. The target users are new users accessing via browser, not existing CLI users.

Key constraints:
- The Python backend must expose unified interfaces so any business-domain UI (client onboarding, reporting, billing) can plug in
- The core engine must extend to support MCP servers and Claude skills as first-class extension points
- The team is Python-based
- Company compliance blocks Node.js/TypeScript servers

---

## Decision 1: Build Custom Platform over Existing Solutions

### Decision

Build a custom platform wrapping Claude Agent SDK (on Claude Code CLI) with a unified Python backend and pluggable domain-specific React UIs.

### Rationale

1. **Domain-specific UIs require separate frontends.** Business lines (client onboarding, reporting, billing) each need different UI layouts and workflows consuming a shared backend. OpenWebUI, Dify, and LobeChat are single-UI chat platforms that cannot support this.
2. **Claude Code CLI has a battle-tested agent loop.** The CLI provides all extension points (MCP, skills, tools, hooks) out of the box. The SDK wraps this loop, giving the backend a robust foundation without building an agent runtime from scratch.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| OpenWebUI | Single-UI chat platform. No support for multiple domain-specific frontends. |
| OpenCode | Enterprise compliance did not approve it. |
| Dify / LobeChat | Same limitation as OpenWebUI -- single-UI, no pluggable domain UIs. |
| LangGraph / CrewAI | Would require building the agent loop from scratch. Loses CLI's extension points. |
| Direct Anthropic API | Loses all CLI extension points (MCP, skills, hooks). Must build agent loop. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| No pre-existing community ecosystem for the platform | AI tooling makes building UI fast; ecosystem is less critical than it was historically |
| Depends on Anthropic maintaining SDK and CLI | Both are robust, actively maintained projects with growing adoption. Fallback trigger: if SDK goes unmaintained for 6+ months or introduces breaking changes without migration path, evaluate direct Anthropic API + custom agent loop as replacement. The platform's thin wrapper design (OptionsBuilder + SessionManager) limits blast radius. |

---

## Decision 2: Python + FastAPI Backend

### Decision

Use Python as the backend language with FastAPI as the web server layer.

### Rationale

Three hard constraints all point to Python:

1. **Claude Agent SDK is Python-only.** The SDK that wraps Claude Code CLI is a Python package. No alternative language binding exists.
2. **Team is Python-based.** Other team members who will work in the codebase are Python developers.
3. **Company compliance blocks Node.js servers.** TypeScript/Node.js is not an option for server-side applications per company policy.

FastAPI is chosen as the web layer because it is simple, mature, async-native (required for WebSocket and streaming), and easily replaceable -- it is a thin routing layer, not a deep architectural commitment.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| TypeScript full-stack (Next.js / Express) | Company compliance blocks Node.js servers |
| Django | Heavier framework; async support is secondary. FastAPI is simpler for an API-only backend. |
| Flask | Less native async support. FastAPI's async-first design is a better fit for WebSocket and streaming workloads. |

### Trade-offs

| Concern | Mitigation |
|---------|------------|
| Frontend team works in TypeScript, backend in Python -- two language stacks | Clear boundary: React frontend communicates via AG-UI/REST/OpenAI-compliant API. No shared code needed. |

---

## Consequences

### Benefits
- Full control over domain-specific UI per business line
- Leverages battle-tested Claude Code CLI agent loop via SDK
- Python-only stack aligns with team skills and compliance
- FastAPI is thin and replaceable -- low lock-in

### Risks
- Platform success depends on SDK/CLI stability and continued Anthropic investment
- Custom platform requires more upfront build effort than adopting an existing solution
- Small team must maintain both frontend and backend

### Follow-up Actions
- Monitor Claude Agent SDK releases for breaking changes
- Evaluate SDK maturity at each phase gate before expanding scope
- Document backend API contracts so domain-specific UIs can be built independently
