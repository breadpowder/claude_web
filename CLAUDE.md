# CLAUDE.md - AI Assistant Guide

> This file provides context for AI assistants working with the claude_web repository.

## Repository Overview

This is a **documentation repository** focused on Claude SDK integration patterns. It serves as an architectural reference guide for developers building services that integrate Claude agents with external systems, tools, and other AI agents.

**Purpose**: Comprehensive guide for integrating Claude Agent SDK with various systems
**Type**: Documentation and code examples (not an executable application)
**Primary Language**: Python (async/await patterns)

## Repository Structure

```
claude_web/
├── CLAUDE.md                      # This file - AI assistant guidance
├── claudesdk_integration.md       # Main documentation (6 integration patterns)
└── .git/                          # Git version control
```

### Key Files

| File | Purpose |
|------|---------|
| `claudesdk_integration.md` | Core documentation covering all integration patterns with code examples |

## Technologies Documented

### Core Framework
- **Claude Agent SDK** - Primary framework for building Claude agents
  - `ClaudeAgentOptions` - Configuration object
  - `query()` - Main query function with async streaming
  - `ClaudeSDKClient` - Client class with context manager support

### Integration Technologies
- **MCP (Model Context Protocol)** - External tool/data integration
  - Transport types: stdio, HTTP, SSE, In-Process
  - Tool naming: `mcp__<server>__<tool>`
- **A2A Protocol** - Agent-to-agent communication standard
- **FastAPI** - Service layer deployment framework
- **httpx** - Async HTTP client for external calls

### Supporting Frameworks Referenced
- LangGraph, CrewAI, AutoGen (external agent frameworks)
- WebSocket for real-time communication

## Integration Patterns Documented

The repository covers **6 integration patterns** (see `claudesdk_integration.md`):

1. **MCP Server Integration** - Connect to external tools via MCP protocol
2. **Custom Tools (@tool decorator)** - In-process tools with no subprocess overhead
3. **Skills Integration** - Markdown-based workflow extensions (slash commands)
4. **A2A REST Pattern** - Simple REST bridge to external agents
5. **A2A Protocol Pattern** - Standardized multi-turn agent communication
6. **Complete Service Architecture** - Production FastAPI deployment

## Code Conventions

### Python Style
- **Async-first**: All functions use `async/await` patterns
- **Streaming**: Results returned via `async for message in query(...)`
- **Context managers**: `async with ClaudeSDKClient(...) as client:`

### Naming Conventions
| Element | Convention | Example |
|---------|------------|---------|
| Tool functions | snake_case | `query_users`, `send_notification` |
| MCP servers | lowercase | `github`, `business`, `a2a` |
| MCP tool references | `mcp__<server>__<tool>` | `mcp__github__list_issues` |
| Skill directories | lowercase with hyphens | `.claude/skills/pdf-extract/` |

### Tool Definition Pattern
```python
@tool("tool_name", "Description of what tool does", {"param": type})
async def tool_name(args: dict) -> dict:
    # Implementation
    return {"content": [{"type": "text", "text": "result"}]}
```

### Tool Return Format
Always return content blocks:
```python
{"content": [{"type": "text", "text": "your result here"}]}
```

### Configuration Pattern
```python
options = ClaudeAgentOptions(
    mcp_servers={...},           # MCP server definitions
    allowed_tools=[...],         # Tool allowlist
    setting_sources=["user", "project"],  # Skill discovery
    permission_mode="acceptEdits",
    max_turns=20
)
```

## Environment Variables

The documentation references these environment variables:
- `GITHUB_TOKEN` - GitHub API authentication
- `API_KEY` - Generic API authentication
- `A2A_TOKEN` - A2A protocol authentication
- `A2A_REGISTRY_URL` - A2A agent registry URL

## Skills System

### Skill Locations
| Scope | Path |
|-------|------|
| Personal (all projects) | `~/.claude/skills/<name>/SKILL.md` |
| Project-specific | `.claude/skills/<name>/SKILL.md` |

### Skill File Structure
```
.claude/skills/<skill-name>/
├── SKILL.md          # Required - main definition
├── reference.md      # Optional - detailed docs
└── examples.md       # Optional - usage examples
```

## Working with This Repository

### Documentation Updates
When updating `claudesdk_integration.md`:
1. Maintain the existing section structure (numbered patterns)
2. Follow the established format: Pattern Description, Use Cases, Code Example
3. Use consistent code block formatting with language hints
4. Include ASCII diagrams where helpful for architecture
5. Update the Quick Reference table if adding new patterns

### Adding New Patterns
1. Add as a new numbered section following existing format
2. Include: Pattern Description, Common Use Cases, Code Example
3. Add entry to Quick Reference table at bottom
4. Link to relevant external documentation in Resources section

### Code Example Guidelines
- Use realistic, production-quality code
- Include proper imports at the top
- Show error handling for async operations
- Demonstrate proper session/task management
- Use environment variables for credentials (never hardcode)

## External Resources

Referenced documentation:
- [Claude Agent SDK Docs](https://platform.claude.com/docs/en/agent-sdk/overview)
- [MCP Protocol](https://modelcontextprotocol.io/)
- [A2A Protocol](https://a2a-protocol.org/latest/)
- [A2A-MCP Bridge](https://github.com/GongRzhe/A2A-MCP-Server)

## Git Workflow

**Current Branch**: `claude/claude-md-ml2jl5ov0fptxwbm-aIvno`
**Main Branch**: `main`

### Commit Message Format
Use semantic prefixes:
- `docs:` - Documentation changes
- `sdlc:` - Software development lifecycle documentation
- `feat:` - New features/patterns
- `fix:` - Corrections to existing content

Example: `docs: add MCP HTTP transport example`

## Key Architectural Concepts

### Service Layer Architecture
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

### Pattern Selection Guide
| Need | Recommended Pattern |
|------|---------------------|
| External tools (GitHub, Slack) | MCP Server (stdio/HTTP) |
| Custom business logic | Custom Tools (@tool) |
| Reusable workflows | Skills (.md files) |
| Simple agent calls | A2A REST |
| Multi-turn agent conversations | A2A Protocol |

## Notes for AI Assistants

1. **This is documentation-only**: No build, test, or lint commands exist
2. **Focus on accuracy**: Code examples should be syntactically correct Python
3. **Maintain consistency**: Follow existing formatting and structure
4. **Keep examples practical**: Production-quality patterns over toy examples
5. **Update comprehensively**: When adding patterns, update all related sections
