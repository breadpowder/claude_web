# Task Details & TDD Specifications: core-engine (Phase 1 MVP)

**Generated From**: tasks.md
**Total Tasks**: 28
**TDD Coverage**: All tasks

---

## TASK-001: Initialize Python project - TDD Specification

### Contract Reference
- **Spec Section**: Architecture Section 7 (Project Structure)
- **Data Contract**: N/A (scaffold)
- **Acceptance Criteria**: AC1, AC2, AC3

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_uv_sync_installs_all_dependencies` | AC1 | fastapi, uvicorn, aiosqlite, structlog, pydantic, claude-agent-sdk | ImportError for missing packages |
| `test_package_structure_matches_architecture` | AC2 | core/, api/, db/, models/ directories | FileNotFoundError for missing dirs |
| `test_package_importable` | AC3 | claude_sdk_pattern module | ModuleNotFoundError |

### Assertion Requirements

**test_uv_sync_installs_all_dependencies**:
```
ASSERT: importlib.import_module("fastapi") does not raise
ASSERT: importlib.import_module("uvicorn") does not raise
ASSERT: importlib.import_module("aiosqlite") does not raise
ASSERT: importlib.import_module("structlog") does not raise
ASSERT: importlib.import_module("pydantic") does not raise
```

**test_package_structure_matches_architecture**:
```
ASSERT: Path("src/claude_sdk_pattern/__init__.py").exists() is True
ASSERT: Path("src/claude_sdk_pattern/core/__init__.py").exists() is True
ASSERT: Path("src/claude_sdk_pattern/api/__init__.py").exists() is True
ASSERT: Path("src/claude_sdk_pattern/db/__init__.py").exists() is True
ASSERT: Path("src/claude_sdk_pattern/models/__init__.py").exists() is True
```

### GREEN Phase Criteria
- All dependency imports succeed
- All directories exist with __init__.py

### REFACTOR Phase Criteria
- pyproject.toml uses proper dependency groups (dev, test)

---

## TASK-002: Initialize Vite + React 19 frontend - TDD Specification

### Contract Reference
- **Spec Section**: Architecture Section 7 (Frontend Structure)
- **Data Contract**: Section 4.2-4.3 (Message Types, Data Contracts)
- **Acceptance Criteria**: AC1, AC2, AC3

### Data Contract Fields (from Section 4.2-4.3)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| type (message) | string union | Yes | One of 18 defined message types | - |
| session_id | string | Varies | UUID format | - |
| text | string | Conditional | Non-empty, max 32k | - |
| seq | number | Conditional | Positive integer | - |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_npm_build_succeeds` | AC1 | N/A (build validation) | Build process exits non-zero |
| `test_message_types_cover_all_ws_messages` | AC2 | all 18 message type strings | TypeScript compilation error |
| `test_session_types_match_contract` | AC3 | SessionSummary 7 fields, ToolUseDisplay 7 fields | TypeScript compilation error |

### Assertion Requirements

**test_message_types_cover_all_ws_messages**:
```
ASSERT: messages.ts exports UserMessage type with fields: type="user_message", session_id:string, text:string, seq:number
ASSERT: messages.ts exports InterruptMessage type with fields: type="interrupt", session_id:string
ASSERT: messages.ts exports StreamDelta type with fields: type="stream_delta", session_id:string, delta:string, seq:number
ASSERT: messages.ts exports ToolUse type with fields: type="tool_use", session_id:string, tool_use_id:string, tool:string, input:object, seq:number
ASSERT: messages.ts exports ResponseComplete type with fields: type="response_complete", session_id:string, cost_usd:number, turn_count:number, seq:number
(... all 18 types covered)
```

### GREEN Phase Criteria
- TypeScript compiles with strict mode, all types match contracts

### REFACTOR Phase Criteria
- Types organized into client-to-server and server-to-client groups

---

## TASK-003: Configuration module and Pydantic models - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.1, 5.1-5.4
- **Data Contract**: 13 env vars (Section 3.1), Session models (Section 5), Message models (Section 4.2)
- **Acceptance Criteria**: AC1, AC2, AC3, AC4

### Acceptance Scenario Mapping

| Scenario | Given | When | Then | Fields Validated |
|----------|-------|------|------|------------------|
| AC1 | No env vars set except required | Config loaded | Defaults match table | All 13 config fields |
| AC2 | Valid client message JSON | Parsed into model | Correct Pydantic type | type, session_id, text, seq |
| AC3 | Server message created | Serialized to JSON | Matches contract shape | All 13 server message types |
| AC4 | Invalid input (empty text, 33k chars) | Validated | ValidationError raised | text, session_id |

### Data Contract Fields (Config - from Section 3.1)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| CLAUDE_SDK_PATTERN_API_KEY | str | Yes | Non-empty | (required) |
| ANTHROPIC_API_KEY | str | Yes | Non-empty | (required) |
| PREWARM_POOL_SIZE | int | No | >= 1 | 2 |
| MAX_SESSIONS | int | No | >= 1 | 10 |
| MAX_SESSION_DURATION_SECONDS | int | No | >= 60 | 14400 |
| MAX_SESSION_RSS_MB | int | No | >= 512 | 2048 |
| SESSION_IDLE_TIMEOUT_SECONDS | int | No | >= 60 | 1800 |
| PREWARM_TIMEOUT_SECONDS | int | No | >= 10 | 60 |
| DATABASE_URL | str | No | Valid path | sqlite:///data/sessions.db |
| HOST | str | No | Valid IP/hostname | 0.0.0.0 |
| PORT | int | No | 1-65535 | 8000 |
| LOG_LEVEL | str | No | DEBUG/INFO/WARNING/ERROR | INFO |
| PROJECT_DIR | str | No | Valid path | . |

### Data Contract Fields (SessionMetadata - from Section 5.1)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| session_id | str | Yes | UUID format (36 chars) | Generated |
| user_id | str | Yes | Non-empty | "default" |
| status | str | Yes | creating/active/idle/terminated | "creating" |
| created_at | str | Yes | ISO 8601 | now() |
| last_active_at | str | Yes | ISO 8601 | now() |
| subprocess_pid | int or None | No | Positive integer | None |
| message_count | int | Yes | >= 0 | 0 |
| total_cost_usd | float | Yes | >= 0.0 | 0.0 |
| is_resumable | bool | Yes | True/False | True |
| terminated_reason | str or None | No | Any string | None |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_config_defaults_match_spec` | AC1 | All 13 config fields | AttributeError or wrong value |
| `test_config_required_fields_raise_without_env` | AC1 | API keys | ValidationError not raised |
| `test_user_message_model_validates` | AC2 | type, session_id, text, seq | ValidationError not raised for invalid |
| `test_session_metadata_defaults` | AC2 | All 10 SessionMetadata fields | AttributeError |
| `test_server_message_serialization` | AC3 | All 13 server message types | KeyError or serialization error |
| `test_validation_rejects_empty_text` | AC4 | text field | ValidationError not raised |
| `test_validation_rejects_oversized_text` | AC4 | text field (32k limit) | ValidationError not raised |
| `test_validation_rejects_invalid_session_id` | AC4 | session_id (UUID format) | ValidationError not raised |

### Assertion Requirements

**test_config_defaults_match_spec**:
```
ASSERT: config.PREWARM_POOL_SIZE == 2
ASSERT: config.MAX_SESSIONS == 10
ASSERT: config.MAX_SESSION_DURATION_SECONDS == 14400
ASSERT: config.MAX_SESSION_RSS_MB == 2048
ASSERT: config.SESSION_IDLE_TIMEOUT_SECONDS == 1800
ASSERT: config.PREWARM_TIMEOUT_SECONDS == 60
ASSERT: config.DATABASE_URL == "sqlite:///data/sessions.db"
ASSERT: config.HOST == "0.0.0.0"
ASSERT: config.PORT == 8000
ASSERT: config.LOG_LEVEL == "INFO"
ASSERT: config.PROJECT_DIR == "."
```

**test_session_metadata_defaults**:
```
ASSERT: metadata.user_id == "default"
ASSERT: metadata.status == "creating"
ASSERT: metadata.message_count == 0
ASSERT: metadata.total_cost_usd == 0.0
ASSERT: metadata.is_resumable == True
ASSERT: metadata.terminated_reason is None
ASSERT: metadata.subprocess_pid is None
ASSERT: len(metadata.session_id) == 36
ASSERT: metadata.created_at matches ISO 8601 regex
```

**test_validation_rejects_empty_text**:
```
ASSERT: ValidationError raised when text=""
ASSERT: ValidationError raised when text="   " (whitespace only)
ASSERT: "empty" in str(error) (error message mentions empty)
```

**test_validation_rejects_oversized_text**:
```
ASSERT: ValidationError raised when text = "x" * 32001
ASSERT: "32,000" in str(error) (error message mentions limit)
```

### FORBIDDEN Assertion Patterns
```
assert config is not None                  # Proves nothing
assert hasattr(config, "PREWARM_POOL_SIZE")  # Doesn't check value
assert isinstance(metadata.session_id, str)  # Missing format check
```

### GREEN Phase Criteria
- All config defaults match Section 3.1 table exactly
- All model fields match Section 5 schemas exactly
- Validation rejects all invalid inputs per Section 4.4

### REFACTOR Phase Criteria
- Models use Pydantic v2 model_config for performance
- Enum values for SessionStatus, message types

---

## TASK-004: SQLite schema and SessionRepository - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.2, 5.1
- **Data Contract**: sessions table (10 columns)
- **Acceptance Criteria**: AC1, AC2, AC3

### Acceptance Scenario Mapping

| Scenario | Given | When | Then | Fields Validated |
|----------|-------|------|------|------------------|
| AC1 | Fresh database | initialize() called | Table with 10 columns exists | All column names and types |
| AC2 | SessionMetadata saved | get() called | All fields match | All 10 fields round-trip |
| AC3 | Mix of active/terminated | list_active() called | Only active returned | status field filtering |

### Data Contract Fields (sessions table)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| session_id | TEXT PK | Yes | UUID format | generated |
| user_id | TEXT | Yes | NOT NULL | "default" |
| status | TEXT | Yes | NOT NULL | "creating" |
| created_at | TEXT | Yes | NOT NULL, ISO 8601 | now() |
| last_active_at | TEXT | Yes | NOT NULL, ISO 8601 | now() |
| subprocess_pid | INTEGER | No | Nullable | NULL |
| message_count | INTEGER | Yes | NOT NULL | 0 |
| total_cost_usd | REAL | Yes | NOT NULL | 0.0 |
| is_resumable | BOOLEAN | Yes | NOT NULL | TRUE |
| terminated_reason | TEXT | No | Nullable | NULL |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_initialize_creates_sessions_table` | AC1 | All 10 columns | Table not created |
| `test_save_and_get_roundtrip` | AC2 | All 10 fields | NotImplementedError |
| `test_list_active_excludes_terminated` | AC3 | status field | Returns terminated sessions |
| `test_update_activity_increments_fields` | AC2 | message_count, total_cost_usd, last_active_at | Fields not updated |
| `test_mark_terminated_updates_status` | AC2 | status, terminated_reason | Status not changed |

### Assertion Requirements

**test_save_and_get_roundtrip**:
```
ASSERT: retrieved.session_id == saved.session_id
ASSERT: retrieved.user_id == saved.user_id
ASSERT: retrieved.status == saved.status
ASSERT: retrieved.created_at == saved.created_at
ASSERT: retrieved.last_active_at == saved.last_active_at
ASSERT: retrieved.subprocess_pid == saved.subprocess_pid
ASSERT: retrieved.message_count == saved.message_count
ASSERT: retrieved.total_cost_usd == saved.total_cost_usd
ASSERT: retrieved.is_resumable == saved.is_resumable
ASSERT: retrieved.terminated_reason == saved.terminated_reason
```

**test_list_active_excludes_terminated**:
```
ASSERT: len(active_list) == 2 (only "active" and "idle" sessions)
ASSERT: all(s.status in ("creating", "active", "idle") for s in active_list)
ASSERT: no session with status "terminated" in active_list
```

**test_update_activity_increments_fields**:
```
ASSERT: updated.message_count == original.message_count + 3
ASSERT: updated.total_cost_usd == original.total_cost_usd + 0.05
ASSERT: updated.last_active_at > original.last_active_at
```

### GREEN Phase Criteria
- Real aiosqlite database used (tmpdir, not mocked)
- All CRUD operations work correctly

### REFACTOR Phase Criteria
- Connection pooling or reuse pattern
- Parameterized queries (no string concatenation)

---

## TASK-005: API key authentication - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 4.1 (auth headers), Section 4.4 (API key validation)
- **Data Contract**: X-API-Key header, 401 error response
- **Acceptance Criteria**: AC1, AC2, AC3

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_valid_api_key_allows_access` | AC1 | X-API-Key header | 401 returned unexpectedly |
| `test_invalid_api_key_returns_401` | AC2 | error, message fields | Wrong status code |
| `test_missing_api_key_returns_401` | AC2 | error, message fields | Wrong status code |
| `test_api_key_not_in_logs` | AC3 | Log output | Key value found in logs |

### Assertion Requirements

**test_invalid_api_key_returns_401**:
```
ASSERT: response.status_code == 401
ASSERT: response.json()["error"] == "unauthorized"
ASSERT: response.json()["message"] == "Invalid API key"
ASSERT: "error" in response.json()
ASSERT: "message" in response.json()
```

**test_api_key_not_in_logs**:
```
ASSERT: actual_api_key_value not in captured_log_output
ASSERT: "REDACTED" in captured_log_output or key not present at all
```

### GREEN Phase Criteria
- Real FastAPI test client used
- Auth works for both REST and WebSocket

### REFACTOR Phase Criteria
- Auth dependency is reusable across all endpoints

---

## TASK-006: ExtensionLoader - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.3, Section 5.3-5.4
- **Data Contract**: ExtensionConfig, MCPServerConfig
- **Acceptance Criteria**: AC1, AC2, AC3, AC4

### Data Contract Fields (MCPServerConfig)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| command | str | Yes | Non-empty | - |
| args | list[str] | Yes | List of strings | [] |
| env | dict[str, str] or None | No | Key-value pairs | None |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_valid_mcp_json_parsed` | AC1 | command, args, env per server | NotImplementedError |
| `test_missing_mcp_json_returns_empty` | AC2 | mcp_servers empty dict | FileNotFoundError raised |
| `test_invalid_json_returns_empty_with_log` | AC3 | mcp_servers empty dict | JSONDecodeError raised |
| `test_skills_directory_discovered` | AC4 | skill_directories list | Empty list returned |
| `test_load_options_aggregates_all` | AC1 | ExtensionConfig all fields | AttributeError |

### Assertion Requirements

**test_valid_mcp_json_parsed**:
```
ASSERT: config.mcp_servers["github"]["command"] == "npx"
ASSERT: config.mcp_servers["github"]["args"] == ["-y", "@modelcontextprotocol/server-github"]
ASSERT: config.mcp_servers["postgres"]["command"] == "npx"
ASSERT: len(config.mcp_servers) == 2
```

**test_missing_mcp_json_returns_empty**:
```
ASSERT: config.mcp_servers == {}
ASSERT: no exception raised
```

**test_invalid_json_returns_empty_with_log**:
```
ASSERT: config.mcp_servers == {}
ASSERT: "error" in captured_log_output.lower() or "invalid" in captured_log_output.lower()
ASSERT: no exception propagated
```

**test_skills_directory_discovered**:
```
ASSERT: "code-review" in [os.path.basename(d) for d in config.skill_directories]
ASSERT: all(os.path.exists(d) for d in config.skill_directories)
```

### GREEN Phase Criteria
- Uses real filesystem (tmpdir with test fixtures)
- No mocking of file I/O

### REFACTOR Phase Criteria
- Consistent error handling pattern
- Config re-read on every call (hot-detection)

---

## TASK-007: PreWarmPool - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.4, Architecture Section 6.2
- **Data Contract**: Pool interface (get, replenish, invalidate, depth, startup_fill)
- **Acceptance Criteria**: AC1, AC2, AC3, AC4

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_startup_fill_returns_true_on_success` | AC1 | startup_fill return value | NotImplementedError |
| `test_startup_fill_returns_false_all_fail` | AC2 | startup_fill return value | Returns True unexpectedly |
| `test_get_returns_client_from_pool` | AC3 | get() return type | Returns None unexpectedly |
| `test_get_returns_none_when_empty` | AC4 | get() return type | Raises exception instead |
| `test_depth_matches_pool_contents` | AC3 | depth() value | Wrong count |
| `test_invalidate_drains_pool` | AC3 | depth() after invalidate | Pool not emptied |

### Assertion Requirements

**test_startup_fill_returns_true_on_success**:
```
ASSERT: result is True
ASSERT: pool.depth() >= 1
```

**test_startup_fill_returns_false_all_fail**:
```
ASSERT: result is False
ASSERT: pool.depth() == 0
```

**test_get_returns_client_from_pool**:
```
ASSERT: client is not None
ASSERT: hasattr(client, "query") (duck-type check for ClaudeSDKClient interface)
ASSERT: pool.depth() == initial_depth - 1
```

**test_get_returns_none_when_empty**:
```
ASSERT: client is None
ASSERT: pool.depth() == 0
```

### GREEN Phase Criteria
- asyncio.Queue used internally
- Background replenishment task launches correctly

### REFACTOR Phase Criteria
- Backoff logic for rate limit (EC-014) implemented
- Proper async cleanup on shutdown

---

## TASK-008: SubprocessMonitor - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.5, Architecture Section 6.5
- **Data Contract**: MonitorAction types
- **Acceptance Criteria**: AC1, AC2, AC3, AC4

### Data Contract Fields (MonitorAction)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| type | str | Yes | One of: warn_duration, terminate_duration, restart_memory, force_kill_memory, cleanup_zombie | - |
| session_id | str | Conditional | UUID format | - |
| remaining_seconds | int | Conditional | >= 0 | - |
| rss_mb | int | Conditional | >= 0 | - |
| pid | int | Conditional | Positive | - |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_get_rss_returns_bytes_for_valid_pid` | AC1 | RSS value in bytes | NotImplementedError |
| `test_get_rss_returns_none_for_invalid_pid` | AC1 | None return | Exception raised |
| `test_check_warns_at_90_percent_duration` | AC2 | type="warn_duration", remaining_seconds | No warning generated |
| `test_check_terminates_at_100_percent_duration` | AC3 | type="terminate_duration" | No termination generated |
| `test_check_restarts_on_memory_threshold` | AC4 | type="restart_memory", rss_mb | No restart generated |

### Assertion Requirements

**test_get_rss_returns_bytes_for_valid_pid**:
```
ASSERT: rss is not None
ASSERT: isinstance(rss, int)
ASSERT: rss > 0
```

**test_check_warns_at_90_percent_duration**:
```
ASSERT: len(actions) == 1
ASSERT: actions[0].type == "warn_duration"
ASSERT: actions[0].session_id == test_session_id
ASSERT: 0 < actions[0].remaining_seconds <= max_duration * 0.10
```

**test_check_terminates_at_100_percent_duration**:
```
ASSERT: len(actions) == 1
ASSERT: actions[0].type == "terminate_duration"
ASSERT: actions[0].session_id == test_session_id
```

**test_check_restarts_on_memory_threshold**:
```
ASSERT: len(actions) == 1
ASSERT: actions[0].type == "restart_memory"
ASSERT: actions[0].session_id == test_session_id
ASSERT: actions[0].rss_mb >= MAX_SESSION_RSS_MB
```

### GREEN Phase Criteria
- Platform-aware RSS reading (Linux /proc or macOS ps)
- Uses current process PID for self-test

### REFACTOR Phase Criteria
- Background tasks properly cancellable
- Configurable intervals

---

## TASK-009: WebSocket message type definitions - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 4.2
- **Data Contract**: 5 client messages, 13 server messages
- **Acceptance Criteria**: AC1, AC2, AC3

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_parse_user_message` | AC1 | type, session_id, text, seq | NotImplementedError |
| `test_parse_interrupt` | AC1 | type, session_id | NotImplementedError |
| `test_parse_create_session` | AC1 | type | NotImplementedError |
| `test_parse_invalid_json` | AC2 | error code | No error returned |
| `test_parse_unknown_type` | AC2 | error code | No error returned |
| `test_factory_stream_delta` | AC3 | type, session_id, delta, seq | KeyError |
| `test_factory_tool_use` | AC3 | type, session_id, tool_use_id, tool, input, seq | KeyError |
| `test_factory_response_complete` | AC3 | type, session_id, cost_usd, turn_count, seq | KeyError |

### Assertion Requirements

**test_parse_user_message**:
```
ASSERT: result.type == "user_message"
ASSERT: result.session_id == "abc123"
ASSERT: result.text == "Hello"
ASSERT: result.seq == 5
```

**test_parse_invalid_json**:
```
ASSERT: result.type == "error"
ASSERT: result.code == "invalid_json"
```

**test_factory_stream_delta**:
```
ASSERT: msg["type"] == "stream_delta"
ASSERT: msg["session_id"] == "abc123"
ASSERT: msg["delta"] == "Hello"
ASSERT: msg["seq"] == 6
ASSERT: set(msg.keys()) == {"type", "session_id", "delta", "seq"}
```

### GREEN Phase Criteria
- All 5 client message types parseable
- All 13 server message types constructable

### REFACTOR Phase Criteria
- Type-safe dispatch (no string matching)

---

## TASK-010: SessionManager - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.6, Architecture Section 6.1
- **Data Contract**: SessionState, SessionSummary
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5

### Acceptance Scenario Mapping (from US-001, US-002)

| Scenario | Given | When | Then | Fields Validated |
|----------|-------|------|------|------------------|
| AC1 | Pool has capacity | create_session() | SessionState returned | session_id, client, pid, status |
| AC2 | Pool has slot | create_session() | Source is "pre-warmed" | source field |
| AC3 | Session active | query(prompt) | Stream events yielded | stream_delta, tool_use, response_complete |
| AC4 | Session exists | destroy_session() | Subprocess cleaned | SIGTERM/SIGKILL, sessions dict |
| AC5 | At max capacity | create_session() | Capacity error | error code |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_create_session_returns_valid_state` | AC1 | session_id, status, pid | NotImplementedError |
| `test_create_session_uses_pool` | AC2 | source field | Pool not used |
| `test_query_yields_stream_events` | AC3 | Event types | NotImplementedError |
| `test_destroy_session_cleans_subprocess` | AC4 | sessions dict emptied | Process not killed |
| `test_create_rejects_at_max_capacity` | AC5 | error type | No error raised |
| `test_list_sessions_returns_summaries` | AC1 | SessionSummary fields | NotImplementedError |
| `test_interrupt_stops_active_query` | AC3 | is_query_active flag | Flag not reset |

### Assertion Requirements

**test_create_session_returns_valid_state**:
```
ASSERT: len(state.session_id) == 36
ASSERT: state.status == SessionStatus.ACTIVE
ASSERT: state.pid > 0
ASSERT: state.client is not None
ASSERT: state.is_query_active is False
```

**test_create_rejects_at_max_capacity**:
```
ASSERT: error raised or returned
ASSERT: error contains "capacity_exceeded"
```

**test_destroy_session_cleans_subprocess**:
```
ASSERT: session_id not in manager.sessions
ASSERT: process with pid is no longer running
```

### GREEN Phase Criteria
- Integrates with real PreWarmPool, ExtensionLoader, Repository
- Async iteration of SDK messages works

### REFACTOR Phase Criteria
- State machine for session status transitions
- Proper async context management

---

## TASK-011: SessionManager monitor integration - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.5-3.6, Control Flow us-004-session-limits.md
- **Data Contract**: MonitorAction processing
- **Acceptance Criteria**: AC1, AC2, AC3, AC4

### Acceptance Scenario Mapping (from US-004)

| Scenario | Given | When | Then | Fields Validated |
|----------|-------|------|------|------------------|
| AC1 | Session at 90% duration | Monitor checks | session_warning sent | remaining_seconds |
| AC2 | Session at 100% duration, query active | Monitor checks | Wait 30s grace, then terminate | grace period |
| AC3 | Session RSS > threshold | Monitor checks | Restart with resume | new session_id, resume |
| AC4 | Orphaned PID detected | Monitor checks | SIGTERM/SIGKILL | PID cleanup |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_duration_warning_sends_ws_message` | AC1 | session_warning type, remaining_seconds | No message sent |
| `test_duration_terminate_waits_for_query` | AC2 | Grace period timing | Immediate termination |
| `test_memory_restart_creates_resume_session` | AC3 | New session with resume | No resume attempted |
| `test_zombie_cleanup_kills_orphan` | AC4 | PID removal | Orphan still running |

### Assertion Requirements

**test_duration_warning_sends_ws_message**:
```
ASSERT: ws_message["type"] == "session_warning"
ASSERT: ws_message["reason"] == "duration"
ASSERT: 0 < ws_message["remaining_seconds"] <= 1440
ASSERT: "save your work" in ws_message["message"].lower()
```

**test_duration_terminate_waits_for_query**:
```
ASSERT: termination happened AFTER query completed (or after 30s)
ASSERT: session status == "terminated"
ASSERT: session_terminated message sent with reason "duration_limit"
```

**test_memory_restart_creates_resume_session**:
```
ASSERT: session_restarting message sent with reason "memory_limit"
ASSERT: old session destroyed
ASSERT: new session created with resume=old_session_id
```

### GREEN Phase Criteria
- Monitor actions correctly dispatched to session operations

### REFACTOR Phase Criteria
- Clean separation between monitoring and action execution

---

## TASK-012: Session resume - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.6, User Stories US-006
- **Data Contract**: resume parameter, session metadata
- **Acceptance Criteria**: AC1, AC2, AC3

### Acceptance Scenario Mapping (from US-006)

| Scenario | Given | When | Then | Fields Validated |
|----------|-------|------|------|------------------|
| AC1 | Previous session exists | resume_session(id) | Context preserved | conversation continuity |
| AC2 | Session not resumable | resume_session(id) | Error returned | error message |
| AC3 | SDK data corrupted | resume_session(id) | Fresh session created | notification message |

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_resume_creates_client_with_resume_param` | AC1 | resume parameter | Not passed to SDK |
| `test_resume_non_resumable_returns_error` | AC2 | error message | No error raised |
| `test_resume_corrupted_starts_fresh` | AC3 | new session, notification | Exception propagated |

### Assertion Requirements

**test_resume_creates_client_with_resume_param**:
```
ASSERT: new_state.session_id is not None
ASSERT: SDK client created with resume=original_session_id
ASSERT: new_state.status == SessionStatus.ACTIVE
```

**test_resume_non_resumable_returns_error**:
```
ASSERT: error message contains "not resumable" or "not found"
```

**test_resume_corrupted_starts_fresh**:
```
ASSERT: new session created (not the old one)
ASSERT: notification contains "could not be restored"
ASSERT: no exception propagated to caller
```

### GREEN Phase Criteria
- Resume parameter correctly passed to SDK
- Error handling covers all failure modes

### REFACTOR Phase Criteria
- Retry logic for transient resume failures

---

## TASK-013: WebSocket handler - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.7, Section 4.2
- **Data Contract**: WebSocket endpoint, all message types
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_ws_auth_valid_key_accepted` | AC1 | Connection accepted | Connection rejected |
| `test_ws_auth_invalid_key_closes_1008` | AC1 | Close code 1008 | Wrong close code |
| `test_ws_user_message_streams_response` | AC2 | stream_delta, response_complete | No messages received |
| `test_ws_interrupt_sends_interrupted` | AC3 | stream_interrupted type | No interrupted message |
| `test_ws_duplicate_session_closes_old` | AC4 | "session_opened_elsewhere" | Both connections kept |
| `test_ws_query_in_progress_rejected` | AC5 | error code "query_in_progress" | Message accepted |

### Assertion Requirements

**test_ws_auth_invalid_key_closes_1008**:
```
ASSERT: connection close code == 1008
ASSERT: close reason contains "Policy Violation" or "Invalid"
```

**test_ws_user_message_streams_response**:
```
ASSERT: first message received has type "message_received"
ASSERT: subsequent messages include type "stream_delta" with non-empty delta
ASSERT: final message has type "response_complete" with cost_usd >= 0
```

**test_ws_duplicate_session_closes_old**:
```
ASSERT: old_connection received message with "session_opened_elsewhere"
ASSERT: old_connection is closed
ASSERT: new_connection is still open
```

### GREEN Phase Criteria
- Real WebSocket test client (Starlette TestClient)
- Full message routing works

### REFACTOR Phase Criteria
- Clean separation of auth, routing, streaming concerns

---

## TASK-014: REST API endpoints - TDD Specification

### Contract Reference
- **Spec Section**: Implementation Plan Section 3.8, Section 4.1
- **Data Contract**: All REST endpoint contracts
- **Acceptance Criteria**: AC1, AC2, AC3, AC4, AC5

### RED Phase Tests

| Test Name | Tests Requirement | Contract Fields Validated | Expected Failure Reason |
|-----------|-------------------|---------------------------|-------------------------|
| `test_get_sessions_returns_list` | AC1 | sessions array, SessionSummary 7 fields | 404 or empty |
| `test_post_sessions_creates_session` | AC2 | session_id, status, source, created_at | 500 or wrong status |
| `test_post_sessions_503_at_capacity` | AC2 | error, message | 200 returned |
| `test_delete_session_returns_terminated` | AC3 | session_id, status, reason | 500 or wrong status |
| `test_delete_session_404_not_found` | AC3 | error, message | 200 returned |
| `test_health_live_returns_ok` | AC4 | status field | 500 |
| `test_health_ready_returns_503_when_full` | AC4 | status, reason, active_sessions, max_sessions | 200 returned |
| `test_sessions_require_auth` | AC5 | 401 status | 200 without auth |

### Assertion Requirements

**test_get_sessions_returns_list**:
```
ASSERT: response.status_code == 200
ASSERT: "sessions" in response.json()
ASSERT: isinstance(response.json()["sessions"], list)
For each session in response:
  ASSERT: "session_id" in session
  ASSERT: "status" in session
  ASSERT: "created_at" in session
  ASSERT: "last_active_at" in session
  ASSERT: "message_count" in session
  ASSERT: "total_cost_usd" in session
  ASSERT: "is_resumable" in session
```

**test_post_sessions_creates_session**:
```
ASSERT: response.status_code == 201
ASSERT: len(response.json()["session_id"]) == 36
ASSERT: response.json()["status"] == "active"
ASSERT: response.json()["source"] in ("pre-warmed", "cold-start")
ASSERT: "created_at" in response.json()
```

**test_health_ready_returns_503_when_full**:
```
ASSERT: response.status_code == 503
ASSERT: response.json()["status"] == "not_ready"
ASSERT: response.json()["reason"] in ("pool_empty", "at_capacity")
ASSERT: isinstance(response.json()["active_sessions"], int)
ASSERT: isinstance(response.json()["max_sessions"], int)
```

### GREEN Phase Criteria
- httpx async test client used
- All 7 endpoints respond correctly

### REFACTOR Phase Criteria
- Consistent error response format across all endpoints

---

## TASK-015 through TASK-028: TDD Specifications (Summary)

Due to the volume, the remaining tasks follow the same TDD pattern. Key highlights:

### TASK-015: Application Entry Point
- **Tests**: startup sequence completes, startup_fill failure exits(1), SIGTERM triggers graceful shutdown
- **Key Assertions**: Health/live returns 200 after startup; exit code 1 on pool failure

### TASK-016: Structlog Logging
- **Tests**: Log output is valid JSON, session_id bound in context, API keys filtered
- **Key Assertions**: json.loads(log_line) succeeds; "session_id" in log_entry; api_key_value not in any log

### TASK-017: Dockerfile
- **Tests**: docker build succeeds, health check passes, UI accessible
- **Key Assertions**: Build exit code 0; curl /api/v1/health/live returns 200

### TASK-018: Error Translation
- **Tests**: SDK timeout -> user message, rate limit -> user message, no raw errors
- **Key Assertions**: translated.suggested_action == "retry"; "raw sdk" not in translated.message

### TASK-019: Idle Timeout
- **Tests**: Session transitions to idle, subprocess terminated, idle timer resets on activity
- **Key Assertions**: session.status == "idle" after timeout; process not running; active query prevents idle

### TASK-020: Zustand Stores
- **Tests**: Message append/finalize, session switch preserves history, streaming flag toggles
- **Key Assertions**: store.messages[sessionId] contains appended tokens; streaming transitions correctly

### TASK-021: WebSocket Hook
- **Tests**: Connection established, messages dispatched, send functions formatted correctly
- **Key Assertions**: onmessage dispatches to correct store; sendMessage includes all required fields

### TASK-022: Layout Components
- **Tests**: Session list renders, click switches session, new session button works
- **Key Assertions**: Rendered session count matches store; active session changes on click

### TASK-023: Message Components
- **Tests**: Streaming tokens render, ToolUseCard status updates, auto-scroll
- **Key Assertions**: Token text visible in DOM; ToolUseCard shows "Complete" after result

### TASK-024: InputBar
- **Tests**: Enter sends, Ctrl+Shift+X interrupts, empty blocked, responsive during stream
- **Key Assertions**: WebSocket send called on Enter; interrupt sent on shortcut; empty message not sent

### TASK-025: StatusBar and AuthGate
- **Tests**: Connection status display, cost display, auth gate blocks without key
- **Key Assertions**: "Connected" visible when WS open; cost value visible; chat not accessible without key

### TASK-026: Error/System Messages
- **Tests**: Retry button on stream_error, warning banner, termination dialog
- **Key Assertions**: Retry button visible; warning text includes remaining time; resume link present

### TASK-027: App Integration
- **Tests**: Full user journey, session switching, responsive layout
- **Key Assertions**: All components compose correctly; 360px width renders without overflow

### TASK-028: E2E Integration Tests
- **Tests**: Full WebSocket flow, session lifecycle, extension loading, health endpoints
- **Key Assertions**: Complete message round-trip validated; all contract fields present

---

## Implementation Strategy Declaration

### Anti-Pattern Reference (FORBIDDEN Patterns)

| Pattern | Why Forbidden | Strategic Alternative |
|---------|---------------|----------------------|
| Regex for JSON parsing | Brittle, breaks on format changes | json.loads() + Pydantic validation |
| Hardcoded config values | Inflexible, requires code changes | Pydantic BaseSettings from env vars |
| Inline if/else for message routing | Unreadable, hard to maintain | Dictionary dispatch or match/case |
| Catch-all exceptions (except Exception) | Hides bugs, poor error handling | Domain-specific exception types |
| Global mutable state | Hard to test, hidden dependencies | Dependency injection via FastAPI Depends |
| String concatenation for SQL | SQL injection risk | Parameterized queries via aiosqlite |
| Mocking internal modules | Tests pass but code broken | Real dependencies (tmpdir DB, test fixtures) |
| Shallow component rendering | Misses integration issues | Full render with @testing-library/react |
| fireEvent for user interactions | Does not simulate real events | @testing-library/user-event |

### Strategy Declaration Per Task Group

#### Group 1: Setup (TASK-001, TASK-002)
| Decision Point | Anti-Pattern Avoided | Strategic Pattern Selected | Rationale |
|---------------|---------------------|---------------------------|-----------|
| Dependency Management | Manual pip install | uv + pyproject.toml | Reproducible builds |
| Frontend Build | Manual webpack config | Vite + React 19 | Fast HMR, modern defaults |
| Type Definitions | Any/unknown types | Strict TypeScript with contract types | Type safety catches bugs |

#### Group 2: Foundational Backend (TASK-003, TASK-004, TASK-005, TASK-009, TASK-016)
| Decision Point | Anti-Pattern Avoided | Strategic Pattern Selected | Rationale |
|---------------|---------------------|---------------------------|-----------|
| Configuration | Hardcoded values | Pydantic BaseSettings | Env-driven, validated |
| Data Validation | Manual if/else checks | Pydantic v2 models | Declarative, self-documenting |
| Database Access | String SQL concatenation | Parameterized aiosqlite queries | SQL injection prevention |
| Authentication | Global middleware state | FastAPI Depends injection | Testable, composable |
| Logging | print() or basic logging | structlog with JSON renderer | Structured, queryable |

#### Group 3: Core Engine (TASK-006, TASK-007, TASK-008, TASK-010, TASK-011)
| Decision Point | Anti-Pattern Avoided | Strategic Pattern Selected | Rationale |
|---------------|---------------------|---------------------------|-----------|
| Extension Loading | Regex for file parsing | json.loads() + Pydantic | Robust error handling |
| Pool Management | Global queue variable | Class-based with asyncio.Queue | Encapsulated, testable |
| Process Monitoring | subprocess.call() | Platform-specific /proc or ps | Accurate RSS reading |
| Session Orchestration | God class | Composition (pool + monitor + loader + repo) | Single responsibility |
| Error Propagation | except Exception | Custom exception hierarchy | Actionable errors |

#### Group 4: API Layer (TASK-013, TASK-014, TASK-015, TASK-018)
| Decision Point | Anti-Pattern Avoided | Strategic Pattern Selected | Rationale |
|---------------|---------------------|---------------------------|-----------|
| Message Routing | Nested if/else on type | Dictionary dispatch table | O(1) lookup, readable |
| Error Translation | Raw SDK errors to client | Error mapping module (G-008) | User-friendly messages |
| WebSocket Management | Global connection dict | Per-handler connection tracking | Clean lifecycle |
| Startup Sequence | Flat script | Factory pattern with lifecycle events | Testable, orderly |

#### Group 5: Frontend (TASK-020 through TASK-027)
| Decision Point | Anti-Pattern Avoided | Strategic Pattern Selected | Rationale |
|---------------|---------------------|---------------------------|-----------|
| State Management | React Context (re-render all) | Zustand with selectors | Efficient streaming |
| Component Testing | Shallow rendering | Full render + user-event | Integration confidence |
| WebSocket Client | Manual event handling | Custom hook with store dispatch | Separation of concerns |
| Error Display | Generic "Something went wrong" | Typed error messages with actions | User actionable (G-008) |

### Pre-Implementation Checklist (Per Group)

Before implementation agent starts each group, verify:

- [ ] Strategic patterns declared for all decision points
- [ ] Anti-patterns explicitly listed as avoided
- [ ] Rationale documented for each strategic choice
- [ ] User has reviewed and approved strategy

---

*End of Task Details & TDD Specifications*
