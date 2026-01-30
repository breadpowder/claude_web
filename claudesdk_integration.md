# Claude SDK Integration Patterns

> **Architecture:** Claude SDK as main agent with service wrapper

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Your Service Layer                            │
├─────────────────────────────────────────────────────────────────┤
│                    Claude Agent SDK                              │
├────────────┬────────────┬────────────┬──────────────────────────┤
│    MCP     │   Tools    │   Skills   │   A2A (External Agents)  │
│  Servers   │  (@tool)   │  (.md)     │   REST / A2A Protocol    │
└────────────┴────────────┴────────────┴──────────────────────────┘
```

---

## 1. MCP Server Integration

### Pattern Description

MCP (Model Context Protocol) connects Claude to external tools and data sources via standardized servers.

### Transport Types

| Type | Use Case | Connection |
|------|----------|------------|
| **stdio** | Local processes | Subprocess on same machine |
| **HTTP** | Remote APIs | HTTPS endpoint |
| **SSE** | Streaming remote | Server-sent events |
| **In-Process** | Custom tools | No subprocess overhead |

### Common Use Cases

- **Database access**: Query PostgreSQL, MongoDB via MCP server
- **Third-party APIs**: GitHub, Slack, Jira integrations
- **File systems**: Remote file access, cloud storage
- **Enterprise systems**: Internal APIs, CRM, ERP

### Code Example: Multiple MCP Servers

```python
from claude_agent_sdk import query, ClaudeAgentOptions
import os

async def run_with_mcp():
    options = ClaudeAgentOptions(
        mcp_servers={
            # Local process (stdio)
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": os.environ["GITHUB_TOKEN"]}
            },
            # Remote HTTP API
            "analytics": {
                "type": "http",
                "url": "https://api.analytics.com/mcp",
                "headers": {"Authorization": f"Bearer {os.environ['API_KEY']}"}
            },
            # SSE streaming
            "realtime": {
                "type": "sse",
                "url": "https://stream.example.com/mcp/sse"
            }
        },
        allowed_tools=[
            "mcp__github__list_issues",
            "mcp__github__create_issue",
            "mcp__analytics__get_metrics",
            "mcp__realtime__subscribe"
        ]
    )

    async for message in query(prompt="List open GitHub issues", options=options):
        print(message)
```

---

## 2. Custom Tools Integration (@tool Decorator)

### Pattern Description

In-process MCP servers using `@tool` decorator. No subprocess overhead, direct access to application state.

### Common Use Cases

- **Business logic**: Custom operations specific to your domain
- **Database queries**: Direct DB access without external server
- **API integrations**: Wrap external APIs as tools
- **Computation**: Complex calculations, data processing

### Code Example: Custom Tools

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions
import httpx

@tool("query_users", "Query users from database", {"email": str, "limit": int})
async def query_users(args: dict) -> dict:
    results = await db.query(
        "SELECT * FROM users WHERE email LIKE ? LIMIT ?",
        [f"%{args['email']}%", args.get("limit", 10)]
    )
    return {"content": [{"type": "text", "text": json.dumps(results)}]}

@tool("send_notification", "Send push notification", {"user_id": str, "message": str})
async def send_notification(args: dict) -> dict:
    await push_service.send(args["user_id"], args["message"])
    return {"content": [{"type": "text", "text": "Notification sent"}]}

# Bundle tools into MCP server
custom_server = create_sdk_mcp_server(
    name="business-tools",
    version="1.0.0",
    tools=[query_users, send_notification]
)

async def run_with_custom_tools():
    options = ClaudeAgentOptions(
        mcp_servers={"business": custom_server},
        allowed_tools=["mcp__business__query_users", "mcp__business__send_notification"]
    )
    async for msg in query(prompt="Find users with gmail and notify them", options=options):
        print(msg)
```

---

## 3. Skills Integration

### Pattern Description

Skills are markdown-based extensions that add custom `/slash-commands` and reusable capabilities. **Note:** Skills are context-matched, not programmatically invoked.

### Common Use Cases

- **Workflow automation**: `/deploy`, `/release`, `/review`
- **Domain knowledge**: Code patterns, best practices
- **Recurring tasks**: PR descriptions, documentation generation
- **Team standards**: Coding guidelines, review checklists

### Skill File Structure

```
.claude/skills/my-skill/
├── SKILL.md          # Required
├── reference.md      # Optional detailed docs
└── examples.md       # Optional examples
```

### Code Example: Enable Skills in SDK

```python
from claude_agent_sdk import query, ClaudeAgentOptions

# Skills are NOT directly callable - Claude matches based on description
# You must enable skill discovery via setting_sources

async def run_with_skills():
    options = ClaudeAgentOptions(
        cwd="/path/to/project",
        setting_sources=["user", "project"],  # Load skills from filesystem
        allowed_tools=["Skill", "Read", "Write", "Bash"]  # Enable Skill tool
    )

    # Claude will auto-match to skills based on prompt context
    # If you have a skill with description "Extract text from PDFs"
    # this prompt may trigger it automatically
    async for message in query(
        prompt="Extract text from invoice.pdf and summarize",
        options=options
    ):
        print(message)

# Skill file example: .claude/skills/pdf-extract/SKILL.md
SKILL_EXAMPLE = """
---
name: pdf-extract
description: Extract text and tables from PDF documents
allowed-tools: Read, Bash
---

When extracting from PDFs:
1. Use pdftotext for text extraction
2. Use tabula for table extraction
3. Return structured JSON output
"""
```

### Skill Locations

| Location | Path | Scope |
|----------|------|-------|
| Personal | `~/.claude/skills/<name>/SKILL.md` | All projects |
| Project | `.claude/skills/<name>/SKILL.md` | This project |

---

## 4. A2A Integration: REST Pattern

### Pattern Description

Expose external agents (LangGraph, CrewAI) as REST endpoints. Claude SDK calls them via custom tools.

### Common Use Cases

- **Simple request/response**: Single-turn agent calls
- **Stateless operations**: No conversation history needed
- **Internal services**: Microservice architecture
- **Quick integration**: Minimal protocol overhead

### Limitations

- Manual session management for multi-turn
- Client must track conversation history
- Polling required for async tasks
- No standard discovery mechanism

### Code Example: REST Bridge to LangGraph

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions
import httpx

# Session store for multi-turn
sessions: dict[str, str] = {}

@tool("langgraph_chat", "Chat with LangGraph agent",
      {"agent": str, "message": str, "new_session": bool})
async def langgraph_chat(args: dict) -> dict:
    agent_url = AGENT_REGISTRY[args["agent"]]["url"]

    # Session management (manual)
    if args.get("new_session") or args["agent"] not in sessions:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{agent_url}/sessions")
            sessions[args["agent"]] = resp.json()["session_id"]

    session_id = sessions[args["agent"]]

    # Call agent
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{agent_url}/chat",
            json={"session_id": session_id, "message": args["message"]}
        )
        # Handle async tasks (polling)
        if resp.status_code == 202:
            task_id = resp.json()["task_id"]
            while True:
                status = await client.get(f"{agent_url}/status/{task_id}")
                if status.json()["status"] == "completed":
                    return {"content": [{"type": "text", "text": status.json()["result"]}]}
                await asyncio.sleep(1)

        return {"content": [{"type": "text", "text": resp.json()["response"]}]}

rest_server = create_sdk_mcp_server(name="rest-agents", version="1.0.0", tools=[langgraph_chat])
```

---

## 5. A2A Integration: A2A Protocol Pattern

### Pattern Description

Use A2A-MCP bridge to communicate with A2A-compatible agents. Standardized protocol for agent-to-agent communication.

### Common Use Cases

- **Multi-turn stateful conversations**: Task lifecycle managed by protocol
- **Cross-framework agents**: LangGraph, CrewAI, AutoGen interop
- **Long-running tasks**: SSE streaming, no polling
- **Enterprise multi-agent**: Discovery, cancellation, history

### Advantages over REST

| Feature | REST | A2A Protocol |
|---------|------|--------------|
| Session management | Manual | Protocol-managed |
| Async updates | Polling | SSE streaming |
| Task cancellation | Custom | Standard `tasks/cancel` |
| History | Client tracks | Server provides |
| Discovery | Manual docs | Agent Cards |

### Integration Options

#### Option A: A2A-MCP Bridge (Recommended)

Uses community A2A-MCP server to bridge protocols.

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async def run_with_a2a_bridge():
    options = ClaudeAgentOptions(
        mcp_servers={
            "a2a": {
                "command": "npx",
                "args": ["-y", "a2a-mcp-server"],
                "env": {
                    "A2A_REGISTRY_URL": "https://registry.example.com",
                    "A2A_AUTH_TOKEN": os.environ["A2A_TOKEN"]
                }
            }
        },
        allowed_tools=[
            "mcp__a2a__discover_agents",   # Find available agents
            "mcp__a2a__send_task",         # Send task to agent
            "mcp__a2a__get_task",          # Get task status/history
            "mcp__a2a__cancel_task"        # Cancel running task
        ]
    )

    async for message in query(
        prompt="Discover research agents and ask one to analyze market trends",
        options=options
    ):
        print(message)
```

#### Option B: Custom A2A Bridge Tool

Build your own A2A client as custom tool.

```python
from claude_agent_sdk import tool, create_sdk_mcp_server
from a2a_client import A2AClient  # A2A Python SDK

a2a = A2AClient()

@tool("a2a_discover", "Discover A2A agents by capability", {"capability": str})
async def a2a_discover(args: dict) -> dict:
    agents = await a2a.discover(capability=args["capability"])
    return {"content": [{"type": "text", "text": json.dumps([a.card for a in agents])}]}

@tool("a2a_task", "Send task to A2A agent",
      {"agent_url": str, "message": str, "task_id": str})
async def a2a_task(args: dict) -> dict:
    agent = await a2a.connect(args["agent_url"])

    # Create or continue task
    task_id = args.get("task_id")
    task = await agent.send_task(message=args["message"], task_id=task_id)

    # Stream results (A2A native)
    result = None
    async for event in agent.subscribe(task.id):
        if event.type == "artifact":
            result = event.content
            break

    return {"content": [{"type": "text", "text": f"[Task: {task.id}]\n{result}"}]}

@tool("a2a_history", "Get task conversation history", {"task_id": str})
async def a2a_history(args: dict) -> dict:
    task = await a2a.get_task(args["task_id"])
    return {"content": [{"type": "text", "text": json.dumps(task.history)}]}

a2a_server = create_sdk_mcp_server(name="a2a", version="1.0.0",
                                    tools=[a2a_discover, a2a_task, a2a_history])
```

---

## 6. Complete Service Architecture

### Production Setup

```python
from fastapi import FastAPI, WebSocket
from claude_agent_sdk import query, ClaudeSDKClient, ClaudeAgentOptions
from contextlib import asynccontextmanager

# Import all tool servers
from .tools.business import business_server
from .tools.a2a_bridge import a2a_server

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize connections
    yield
    # Shutdown: cleanup

app = FastAPI(lifespan=lifespan)

def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        mcp_servers={
            # External MCP
            "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]},
            # Custom tools
            "business": business_server,
            # A2A bridge
            "a2a": a2a_server
        },
        setting_sources=["project"],  # Enable skills
        allowed_tools=[
            "Read", "Edit", "Bash", "Glob", "Grep", "Skill",
            "mcp__github__*",
            "mcp__business__*",
            "mcp__a2a__*"
        ],
        permission_mode="acceptEdits",
        max_turns=20
    )

@app.post("/agent/task")
async def run_task(request: dict):
    results = []
    async for msg in query(prompt=request["prompt"], options=build_options()):
        results.append(str(msg))
    return {"results": results}

@app.websocket("/ws/agent")
async def agent_ws(websocket: WebSocket):
    await websocket.accept()
    async with ClaudeSDKClient(options=build_options()) as client:
        while True:
            data = await websocket.receive_json()
            await client.query(data["message"])
            async for msg in client.receive_response():
                await websocket.send_json({"type": str(msg.type), "content": str(msg)})
```

---

## Quick Reference

| Pattern | Best For | Complexity |
|---------|----------|------------|
| **MCP (stdio)** | Local third-party tools | Low |
| **MCP (HTTP)** | Remote APIs | Low |
| **Custom Tools** | Business logic, DB access | Medium |
| **Skills** | Workflows, domain knowledge | Low |
| **A2A (REST)** | Simple agent calls | Low |
| **A2A (Protocol)** | Multi-turn, cross-framework | Medium |

## Resources

- [Claude Agent SDK Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [A2A-MCP Bridge](https://github.com/GongRzhe/A2A-MCP-Server)
