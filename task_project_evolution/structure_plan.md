# Project Structure Plan: claude_web Evolution

## Executive Summary

- **Current state**: Minimal repo with a single monolithic markdown file (`claudesdk_integration.md`) containing all 6 integration patterns, plus a `CLAUDE.md` for AI assistant guidance.
- **Target state**: A proper Python project with modular documentation (MkDocs Material), runnable code examples as a Python package, automated tests validating examples, and CI/CD pipeline.
- **Tooling**: `uv` for Python project/dependency management, MkDocs Material for documentation site, pytest for testing, GitHub Actions for CI/CD.
- **Migration approach**: Incremental -- initialize project skeleton first, split documentation second, extract code examples third, add tests and CI last.
- **Key principle**: Every code example in the documentation should be importable and testable, ensuring docs never go stale.

---

## Current State

### Files

| File | Size | Purpose |
|------|------|---------|
| `claudesdk_integration.md` | 449 lines | Monolithic documentation covering 6 integration patterns with embedded code examples |
| `CLAUDE.md` | 198 lines | AI assistant guidance, project conventions, architectural overview |
| `.git/` | -- | Git version control |

### Content Inventory (from `claudesdk_integration.md`)

| Section | Lines | Code Example? | Dependencies Referenced |
|---------|-------|---------------|------------------------|
| 1. MCP Server Integration | 20-79 | Yes (MCP config) | `claude_agent_sdk`, `os` |
| 2. Custom Tools (@tool) | 83-129 | Yes (tool decorator) | `claude_agent_sdk`, `httpx`, `json` |
| 3. Skills Integration | 133-200 | Yes (skills config) | `claude_agent_sdk` |
| 4. A2A REST Pattern | 203-263 | Yes (REST bridge) | `claude_agent_sdk`, `httpx`, `asyncio` |
| 5. A2A Protocol Pattern | 267-366 | Yes (A2A bridge + custom) | `claude_agent_sdk`, `a2a_client`, `json` |
| 6. Complete Service Architecture | 370-428 | Yes (FastAPI service) | `fastapi`, `claude_agent_sdk`, `contextlib` |
| Quick Reference + Resources | 432-449 | No | -- |

### Observations

- All content in a single file makes navigation difficult as the project grows.
- Code examples are embedded in markdown fences -- not importable, not testable.
- No `pyproject.toml`, no package structure, no dependency tracking.
- No `.gitignore` file.
- CLAUDE.md notes explicitly: "No build, test, or lint commands exist."

---

## Target Layout

```
claude_web/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # Lint, test, build docs
│       └── deploy-docs.yml           # Deploy docs to GitHub Pages
├── .claude/
│   └── skills/                       # Project-specific skills (future)
├── docs/
│   ├── index.md                      # Landing page / overview
│   ├── getting-started.md            # Quick start guide
│   ├── architecture.md               # Service layer architecture overview
│   ├── patterns/
│   │   ├── index.md                  # Pattern selection guide
│   │   ├── mcp-server.md             # Pattern 1: MCP Server Integration
│   │   ├── custom-tools.md           # Pattern 2: Custom Tools (@tool)
│   │   ├── skills.md                 # Pattern 3: Skills Integration
│   │   ├── a2a-rest.md               # Pattern 4: A2A REST Pattern
│   │   ├── a2a-protocol.md           # Pattern 5: A2A Protocol Pattern
│   │   └── service-architecture.md   # Pattern 6: Complete Service
│   ├── reference/
│   │   ├── configuration.md          # ClaudeAgentOptions reference
│   │   ├── environment-variables.md  # Env var reference
│   │   └── quick-reference.md        # Quick lookup table
│   └── contributing.md               # How to contribute
├── src/
│   └── claude_web/
│       ├── __init__.py
│       ├── py.typed
│       └── examples/
│           ├── __init__.py
│           ├── mcp_server.py         # Pattern 1 code
│           ├── custom_tools.py       # Pattern 2 code
│           ├── skills_config.py      # Pattern 3 code
│           ├── a2a_rest.py           # Pattern 4 code
│           ├── a2a_protocol.py       # Pattern 5 code
│           └── service.py            # Pattern 6 code
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Shared fixtures
│   ├── test_examples_syntax.py       # Verify all examples parse/import
│   ├── test_mcp_server.py            # Pattern 1 validation
│   ├── test_custom_tools.py          # Pattern 2 validation
│   ├── test_skills_config.py         # Pattern 3 validation
│   ├── test_a2a_rest.py              # Pattern 4 validation
│   ├── test_a2a_protocol.py          # Pattern 5 validation
│   └── test_service.py               # Pattern 6 validation
├── scripts/
│   └── validate_docs.py              # Script to check doc code blocks compile
├── .gitignore
├── .python-version
├── pyproject.toml                    # uv-managed project config
├── mkdocs.yml                        # MkDocs Material configuration
├── CLAUDE.md                         # AI assistant guidance (updated)
├── LICENSE                           # MIT license
└── README.md                         # Project README
```

### Directory Purposes

| Directory | Purpose |
|-----------|---------|
| `docs/` | MkDocs source files -- modular markdown, one file per pattern |
| `docs/patterns/` | Individual pattern documentation (split from monolith) |
| `docs/reference/` | Configuration and quick-reference material |
| `src/claude_web/examples/` | Runnable Python code extracted from doc examples |
| `tests/` | Pytest tests that import and validate example code |
| `scripts/` | Utility scripts (doc validation, etc.) |
| `.github/workflows/` | CI/CD pipeline definitions |

---

## File Mapping

### Documentation Split

| Source (current) | Target (new) | Content |
|------------------|--------------|---------|
| `claudesdk_integration.md` lines 1-16 | `docs/index.md` | Overview, architecture diagram |
| `claudesdk_integration.md` section 1 | `docs/patterns/mcp-server.md` | MCP Server pattern |
| `claudesdk_integration.md` section 2 | `docs/patterns/custom-tools.md` | Custom Tools pattern |
| `claudesdk_integration.md` section 3 | `docs/patterns/skills.md` | Skills pattern |
| `claudesdk_integration.md` section 4 | `docs/patterns/a2a-rest.md` | A2A REST pattern |
| `claudesdk_integration.md` section 5 | `docs/patterns/a2a-protocol.md` | A2A Protocol pattern |
| `claudesdk_integration.md` section 6 | `docs/patterns/service-architecture.md` | Service Architecture pattern |
| `claudesdk_integration.md` Quick Ref | `docs/reference/quick-reference.md` | Quick reference table |
| `claudesdk_integration.md` Resources | `docs/reference/quick-reference.md` (footer) | External links |
| `CLAUDE.md` env vars section | `docs/reference/environment-variables.md` | Env var documentation |
| `CLAUDE.md` config section | `docs/reference/configuration.md` | Configuration reference |

### Code Extraction

| Source (embedded in markdown) | Target (Python module) |
|-------------------------------|------------------------|
| Section 1 code fence | `src/claude_web/examples/mcp_server.py` |
| Section 2 code fence | `src/claude_web/examples/custom_tools.py` |
| Section 3 code fence | `src/claude_web/examples/skills_config.py` |
| Section 4 code fence | `src/claude_web/examples/a2a_rest.py` |
| Section 5 code fences (both options) | `src/claude_web/examples/a2a_protocol.py` |
| Section 6 code fence | `src/claude_web/examples/service.py` |

### Documentation Code References

After extraction, each `docs/patterns/*.md` file should reference the corresponding Python module using MkDocs code inclusion (e.g., `--8<-- "src/claude_web/examples/mcp_server.py"`) so that documentation and runnable code stay in sync.

---

## Migration Steps

### Phase 1: Project Skeleton (No content changes)

1. **Initialize uv project**: Run `uv init` to create `pyproject.toml` and `.python-version`.
2. **Create directory structure**: `docs/`, `docs/patterns/`, `docs/reference/`, `src/claude_web/`, `src/claude_web/examples/`, `tests/`, `scripts/`, `.github/workflows/`.
3. **Add `.gitignore`**: Python, MkDocs build, task directories, IDE files, `.env`.
4. **Add `LICENSE`**: MIT license.
5. **Add `README.md`**: Brief project description pointing to docs.
6. **Configure `pyproject.toml`**: Add dependencies (`mkdocs-material`, `pytest`, `httpx`, `fastapi`), dev dependencies, and project metadata.
7. **Configure `mkdocs.yml`**: MkDocs Material theme, navigation structure, code highlighting.

### Phase 2: Documentation Split

8. **Create `docs/index.md`**: Migrate overview and architecture diagram from monolith.
9. **Create `docs/getting-started.md`**: New content -- installation, first example.
10. **Split patterns**: Create one file per pattern in `docs/patterns/`, migrating content from `claudesdk_integration.md` sections 1-6.
11. **Create `docs/patterns/index.md`**: Pattern selection guide (from Quick Reference table).
12. **Create reference docs**: `configuration.md`, `environment-variables.md`, `quick-reference.md`.
13. **Create `docs/contributing.md`**: Guidelines for adding new patterns.
14. **Preserve original**: Keep `claudesdk_integration.md` temporarily as reference, remove later.

### Phase 3: Code Extraction

15. **Create `src/claude_web/__init__.py`**: Package init with version.
16. **Extract examples**: Pull code from each pattern's markdown code fence into corresponding `src/claude_web/examples/*.py` module.
17. **Ensure importability**: Each example module should define async functions that can be imported (not auto-execute).
18. **Update doc code blocks**: Replace inline code fences with `--8<-- "..."` includes or keep inline but ensure they match the extracted files exactly.

### Phase 4: Testing

19. **Create `tests/conftest.py`**: Shared fixtures, mock SDK client if needed.
20. **Write syntax validation tests**: `test_examples_syntax.py` that imports all example modules to verify they parse correctly.
21. **Write per-pattern tests**: Validate each example's structure (correct function signatures, proper return formats, etc.).
22. **Create `scripts/validate_docs.py`**: Script that extracts code blocks from markdown and verifies they compile.

### Phase 5: CI/CD

23. **Create `.github/workflows/ci.yml`**: Lint (ruff), test (pytest), build docs (mkdocs build) on every push/PR.
24. **Create `.github/workflows/deploy-docs.yml`**: Deploy docs to GitHub Pages on push to main.
25. **Update `CLAUDE.md`**: Reflect new structure, build commands, test commands.

### Phase 6: Cleanup

26. **Remove `claudesdk_integration.md`**: After all content is migrated and verified.
27. **Update `CLAUDE.md`**: New repository structure, available commands, testing instructions.
28. **Final review**: Verify docs build, tests pass, CI green.

---

## Tooling Recommendations

### Package Management

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **uv** | Python project/dependency management | Fast, modern, replaces pip/poetry. Aligns with user's CLAUDE.md conventions. |

### Documentation

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **MkDocs Material** | Documentation site generator | Best-in-class for Python docs. Built-in search, code highlighting, responsive. |
| **mkdocs-include-markdown-plugin** | Include external files in docs | Enables single-source code examples (import from `src/`). |
| **mkdocstrings[python]** | Auto-generate API docs from docstrings | Future use when the package has a public API. |

### Testing

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **pytest** | Test runner | Standard Python testing. Aligns with user conventions. |
| **pytest-asyncio** | Async test support | All examples use async/await patterns. |

### Code Quality

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **ruff** | Linter + formatter | Fast, replaces flake8/black/isort. Single tool. |
| **mypy** | Type checking | Optional, for future strict typing of examples. |

### CI/CD

| Tool | Purpose | Rationale |
|------|---------|-----------|
| **GitHub Actions** | CI/CD pipeline | Native to GitHub, free for public repos. |
| **uv** in CI | Dependency caching | Fast installs in CI with `astral-sh/setup-uv` action. |

### Proposed `pyproject.toml` Dependencies

```
[project]
dependencies = []  # No runtime deps -- this is a documentation/examples project

[project.optional-dependencies]
examples = [
    "httpx>=0.27",
    "fastapi>=0.115",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mkdocs-material>=9.5",
    "mkdocs-include-markdown-plugin>=7.0",
]
```

---

## Open Questions

These decisions need user input before proceeding:

1. **Documentation hosting**: Should docs be deployed to GitHub Pages, or is this purely a local reference project? This affects whether we need the deploy workflow.

2. **Python version target**: The examples reference `claude_agent_sdk` which may have specific Python version requirements. Should we target Python >= 3.11 or >= 3.12?

3. **Claude Agent SDK availability**: The SDK (`claude_agent_sdk`) is referenced extensively but may not be publicly available as a pip package yet. Should we:
   - Mock it in tests (test structure/syntax only)?
   - Add it as a dependency if available?
   - Create a stub package for import validation?

4. **Scope of runnable examples**: Should the extracted code examples be fully runnable (requiring real API keys/services), or should they remain illustrative with the tests only validating syntax and structure?

5. **Original file preservation**: Should `claudesdk_integration.md` be kept as a legacy single-page reference, or fully replaced by the modular docs?

6. **README scope**: Should `README.md` be a brief pointer to the docs site, or a comprehensive standalone document?

7. **Namespace**: Is `claude_web` the correct Python package name, or should it be something more descriptive like `claude_sdk_patterns` or `claude_integration_guide`?

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Code examples may not compile without real SDK | High | Test syntax/structure only; create SDK stubs for import tests |
| Documentation build breaks on code inclusion | Medium | CI validates docs build on every PR |
| Migration introduces broken links | Low | MkDocs strict mode catches missing links |
| Scope creep during migration | Medium | Strictly follow phased approach; each phase is a separate PR |
