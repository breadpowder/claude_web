# Claude Web

A web interface for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that brings the full CLI experience to the browser — multi-step tool execution visibility, real-time streaming, cancel/interrupt, and cost transparency.

## The Problem

Claude Code's CLI provides a rich, information-dense experience: you see every tool call with arguments, animated progress, results, timing, and Ctrl+C to cancel. But not everyone works in a terminal. Teams need a shared web interface — and existing web wrappers reduce Claude to a basic chatbot, hiding the multi-step reasoning that makes it powerful.

**What you lose without visibility:**

- **Trust gap** — Users can't tell what Claude is doing during 30-second multi-step tasks. Opaque "Bash" / "WebFetch" badges provide zero insight, leading to uncertainty and premature abandonment.
- **Debugging blind spots** — When something goes wrong, neither users nor support can diagnose issues. Tool arguments and results are logged server-side but never surface in the UI.
- **No escape hatch** — Multi-step tasks can span 10-20 tool calls. If execution goes down the wrong path, there's no way to stop it — you wait and waste tokens.

## What Claude Web Does

Claude Web wraps the Claude Code SDK in a Python backend (FastAPI + SSE streaming) serving a React frontend, preserving the CLI's information density in a web-native format.

### Key Features

**Progressive Disclosure Tool Steps**
Every tool call is visible with a 3-level depth hierarchy:
- Level 0 (always visible): Tool name + truncated arguments + status icon + timing
- Level 1 (click to expand): Full arguments + result preview (500 chars)
- Level 2 (click "show full"): Complete result text (scrollable)

**CLI-Style Formatting**
Mirrors Claude Code CLI patterns: filled circle markers colored by status, `ToolName(args...)` parenthesized format, `⎿` result connectors, monospace font throughout tool steps.

**Cancel / Interrupt**
Stop button replaces Send during streaming. Escape key support. Fires `POST /api/v1/sessions/{id}/interrupt` to abort the backend subprocess, preserves partial content with "[Response interrupted]" label.

**Completion Metadata**
After each response: `N turns | Xs | $X.XXXX` — step count, wall-clock duration, and cost (from Anthropic's metering). Prefixed with "Interrupted:" if cancelled.

**Error Recovery UX**
Errors auto-expand with FAILED badge, red highlighting, and "Copy error" support. Error-then-retry sequences show the self-healing narrative.

**Auto-Collapse**
When completed steps exceed 5, older steps collapse into a summary line (e.g., "8 completed steps — 3.1s total"). Running and error steps stay visible.

**MCP Server + Skills Integration**
Configure external tools (GitHub, Slack, databases) via MCP servers and reusable workflows via slash-command skills — all defined in configuration, no code changes.

**Dual Provider Support**
Run against AWS Bedrock (subprocess-based, with pre-warm pool) or any OpenAI-compatible endpoint via LiteLLM (in-process, no subprocess overhead).

## Architecture

```
Browser (React 19 + Vite + Zustand)
  │
  │  SSE stream (OpenAI-compatible format)
  ▼
FastAPI Backend (Python 3.12+)
  ├── OpenAI Adapter ── translates SDK events → SSE chunks
  ├── Session Manager ── acquire/release/interrupt sessions
  ├── Pre-Warm Pool ── pre-spawned SDK subprocesses (~20-30s cold start avoided)
  ├── Subprocess Monitor ── RSS/duration guardrails
  └── Extension Loader ── MCP servers, skills, commands from config
  │
  │  claude-code-sdk (subprocess per session)
  ▼
Claude Code CLI
  ├── MCP Servers (stdio/HTTP)
  ├── Skills (.md slash commands)
  └── Anthropic API / AWS Bedrock
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- Anthropic API key or AWS Bedrock access

### Docker (Recommended)

```bash
cp .env.example .env
# Edit .env with your credentials

docker compose up --build
```

The app is available at `http://localhost:8000` (backend serves the built frontend as static files).

The Docker image runs as a non-root `claude` user — required by the Claude Code SDK which rejects `--dangerously-skip-permissions` under root.

### Local Development

1. **Clone and install backend dependencies:**

```bash
git clone https://github.com/anthropics/claude-web.git
cd claude-web
pip install uv
uv sync
```

2. **Configure environment:**

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY or AWS Bedrock credentials
```

3. **Install and start frontend (dev server with hot reload):**

```bash
cd frontend
npm install
npm run dev  # Starts on http://localhost:5173, proxies /api and /v1 to backend
```

4. **Start backend (from project root):**

```bash
uv run uvicorn src.main:get_app --factory --host 0.0.0.0 --port 8000
```

5. **Open** `http://localhost:5173` in your browser.

## Configuration

Configuration is driven by `config.yaml` with `${ENV_VAR}` resolution from `.env`:

```yaml
provider: bedrock          # "bedrock" or "litellm"

bedrock:
  model: us.anthropic.claude-sonnet-4-5-20250929-v1:0
  region: ${AWS_REGION}
  access_key_id: ${AWS_ACCESS_KEY_ID}
  secret_access_key: ${AWS_SECRET_ACCESS_KEY}
  session_token: ${AWS_SESSION_TOKEN}

litellm:
  model: anthropic/claude-sonnet-4-5-20250929
  api_key: ${ANTHROPIC_API_KEY}

engine:
  prewarm_pool_size: 2
  max_sessions: 10
  cors_origins: "*"
  log_level: INFO
  project_cwd: .
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **Bedrock Auth** | | |
| `AWS_ACCESS_KEY_ID` | — | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret key |
| `AWS_SESSION_TOKEN` | — | AWS temporary session token (optional) |
| `AWS_REGION` | `us-east-1` | AWS region |
| `AWS_PROFILE` | — | AWS profile name (alternative to keys) |
| **LiteLLM Auth** | | |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| **Engine Settings** | | |
| `PREWARM_POOL_SIZE` | `2` | Pre-warmed SDK sessions (Bedrock only; LiteLLM forces 0) |
| `MAX_SESSIONS` | `10` | Maximum concurrent sessions |
| `MAX_SESSION_DURATION_SECONDS` | `3600` | Session timeout |
| `MAX_SESSION_RSS_MB` | `512` | Memory limit per session subprocess |
| `PROJECT_CWD` | `.` | Working directory for Claude Code |
| `LOG_LEVEL` | `INFO` | Logging level |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated) |

## API Reference

### OpenAI-Compatible Streaming

```
POST /v1/chat/completions
```

Standard OpenAI chat completions format with SSE streaming. Vendor extensions in the stream:
- `delta.tool_calls` — tool invocations with name and arguments
- `delta.tool_result` — tool results with content and error status
- `chunk.meta` — completion metadata (turns, cost, duration, token usage)

### Session Management

```
GET    /api/v1/sessions                    # List all sessions
POST   /api/v1/sessions                    # Create or resume a session
GET    /api/v1/sessions/{id}               # Get session details
POST   /api/v1/sessions/{id}/interrupt      # Interrupt active query
DELETE /api/v1/sessions/{id}               # Destroy session
```

### Health & Extensions

```
GET    /api/v1/health/live                 # Liveness probe
GET    /api/v1/health/ready                # Readiness probe (pool + session metrics)
GET    /api/v1/extensions                  # List MCP servers, skills, commands
```

## Testing

```bash
# Backend tests (unit + integration + e2e)
uv run pytest tests/

# Frontend tests (27 integration tests via Vitest + Testing Library)
cd frontend && npm test
```

## Project Structure

```
claude-web/
├── src/                                # Python backend
│   ├── main.py                         # App factory, lifespan startup/shutdown
│   ├── core/
│   │   ├── config.py                   # Pydantic config models, env resolution
│   │   ├── sdk_client.py               # Claude Code SDK wrapper
│   │   ├── session_manager.py          # Session lifecycle (create/query/interrupt/destroy)
│   │   ├── prewarm_pool.py             # Pre-warmed subprocess pool
│   │   ├── provider_factory.py         # Bedrock / LiteLLM factory
│   │   ├── llm_provider.py            # Abstract provider interface
│   │   ├── subprocess_monitor.py       # RSS + duration guardrails
│   │   ├── extension_loader.py         # MCP servers, skills, commands scanner
│   │   ├── prompt_expander.py          # Slash command expansion
│   │   └── providers/
│   │       ├── bedrock.py              # AWS Bedrock (subprocess)
│   │       └── litellm_provider.py     # LiteLLM (in-process)
│   └── api/
│       ├── openai/
│       │   ├── adapter.py              # SDK events → OpenAI SSE translation
│       │   └── endpoint.py             # POST /v1/chat/completions
│       └── service/
│           ├── sessions.py             # Session CRUD + interrupt
│           ├── health.py               # Liveness + readiness probes
│           └── extensions.py           # Extension listing
├── frontend/                           # React 19 frontend
│   ├── src/
│   │   ├── main.tsx                    # React entry point
│   │   ├── App.tsx                     # Root component
│   │   ├── components/
│   │   │   ├── Header/                 # Title, connection status, extensions
│   │   │   ├── MessageList/            # Chat message rendering
│   │   │   ├── ChatInput/              # Input field, send/stop, slash autocomplete
│   │   │   ├── ErrorBanner/            # Error display with copy
│   │   │   ├── ToolSteps/              # ToolStepsContainer, ToolStepRow, CollapsedSteps
│   │   │   └── CompletionMeta/         # Turns, cost, duration bar
│   │   ├── stores/                     # Zustand state management
│   │   │   ├── chatStore.ts            # Messages, streaming, send/stop
│   │   │   ├── sessionStore.ts         # Session creation, connection status
│   │   │   └── extensionStore.ts       # MCP servers, skills, commands
│   │   ├── services/
│   │   │   ├── api.ts                  # REST API client
│   │   │   └── sseParser.ts            # OpenAI SSE stream parser
│   │   ├── types/index.ts              # TypeScript interfaces
│   │   └── utils/formatters.ts         # Tool name formatting (MCP server > tool)
│   └── tests/                          # Vitest + Testing Library
│       ├── App.test.tsx                # App integration tests
│       └── e2e-tool-steps.test.tsx     # Tool step UX tests
├── tests/                              # Backend test suite
│   ├── unit/                           # Pool, session, adapter, provider tests
│   ├── integration/                    # Startup, REST API, health tests
│   ├── e2e/                            # Full workflow + edge case tests
│   └── qa/                             # API contract validation
├── docs/
│   ├── adr/                            # Architecture Decision Records
│   └── wireframes/                     # Architecture diagrams (HTML + SVG)
├── Dockerfile                          # Multi-stage build (Node + Python, non-root)
├── docker-compose.yml                  # Single service, port 8000
├── config.yaml                         # Runtime configuration
└── pyproject.toml                      # Python project metadata (uv/hatchling)
```

## Roadmap

- [ ] Thinking indicator (collapsible section showing Claude's reasoning)
- [ ] Conversation history persistence and search
- [ ] Multi-user session sharing
- [ ] Mobile-responsive optimizations
- [ ] Plugin marketplace for MCP servers and skills
- [ ] WebSocket transport (replacing SSE for bidirectional communication)

## Architecture Decisions

Key design decisions are documented as ADRs in [`docs/adr/`](docs/adr/):

- **ADR-001**: Platform Strategy
- **ADR-002**: Technical Architecture
- **ADR-003**: Multi-Step Reasoning UX Enhancement

## License

MIT
