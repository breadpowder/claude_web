# ADR-003: Multi-Step Reasoning UX Enhancement

**Status:** Accepted
**Date:** 2026-02-14
**Decision Makers:** Core team (small team)
**Context Source:** `docs/mockups/enhanced-tool-steps-ux.html` (v3), design plan
**Depends on:** ADR-001 (Platform Strategy), ADR-002 (Technical Architecture)

---

## Context

The platform wraps Claude Agent SDK (on Claude Code CLI) in a Python backend serving a React frontend via SSE streaming (ADR-002). The CLI provides rich step-by-step tool execution visibility: tool names with arguments, animated spinners, result content, timing, Ctrl+C to cancel. The web UI currently shows only purple pill badges with tool names — no arguments, no results, no progress indication, no cancel mechanism.

This creates three concrete problems:

1. **User trust/confidence gap** — Users cannot tell what Claude is doing during multi-step tasks. They see opaque "Bash" / "WebFetch" pills but don't know if the approach is correct, leading to uncertainty and premature abandonment.
2. **Debugging/support burden** — When something goes wrong, neither users nor support can diagnose issues because tool arguments and results are hidden. The backend logs this data but it never reaches the UI.
3. **No abort mechanism** — Multi-step tasks can run for 30+ seconds across 10-20 tool calls. If a user detects the execution is going down the wrong path, there is no way to stop it — they must wait for all turns to complete, wasting time and tokens.

### Constraints

- Backend is Python with SSE streaming (OpenAI-compatible format) — ADR-002
- Claude Code SDK subprocess per session (~500MB-1GB RAM, 20-30s cold start) — ADR-002
- Tool results already flow through the pipeline but are actively suppressed in `sdk_event_to_chunk()`
- `SessionManager.interrupt()` exists but has no HTTP endpoint
- Target users are developers comfortable with information-dense displays
- Phase 1 scope — must ship incrementally, each decision independently deployable

---

## Decision 1: Progressive Depth Visual Pattern

**Decision:** Adopt a 3-level progressive disclosure hierarchy for tool step display.

| Level | Visibility | Content |
|-------|-----------|---------|
| Level 0 | Always visible | Tool name + truncated args + status icon + timing |
| Level 1 | Click to expand | Full arguments + result preview (500 chars) |
| Level 2 | Click "show full" | Full result text (scrollable, max-height 400px) |

**Rationale:** Tool results can be massive (10KB+). Showing everything inline would bury the assistant's actual response text and overwhelm users. The CLI uses the same mental model (collapsed by default, expand on demand), so users already understand this pattern. Additionally, rendering 10+ large results inline causes layout thrashing and scroll jank.

**Trade-offs:**
- Extra clicks for users who always want full details — every step requires a click to see arguments and results
- Risk of hiding critical information in collapsed state — users may miss important details
- Frontend state management complexity — tracking expanded/collapsed state per step, auto-expand on errors, auto-collapse at threshold

**Alternatives Considered:**
- **Tooltip/popover on pills**: Rejected — tooltips are ephemeral (vanish on touch devices), can't display large content (10KB results), and force context-switching away from the conversation flow
- **Side panel / drawer** (like DevTools): Rejected — requires responsive split-pane layout with breakpoints and resizing, high engineering cost for Phase 1. Also forces context-switching: user must look away from the conversation to see tool details

---

## Decision 2: CLI-Style Formatting

**Decision:** Mirror Claude Code CLI visual patterns: filled circle markers (●) colored by status, `ToolName(args...)` parenthesized format, `⎿` result connectors, monospace font throughout tool step elements.

**Rationale:** The CLI UX is already proven and well-received. Reusing validated patterns reduces design risk and avoids reinventing a visual language for tool execution display. The approach is: CLI-style as the baseline, iterate from there.

**Trade-offs:**
- May look too technical for non-developer audiences if the user base expands beyond developers in the future
- Anchors future design evolution to terminal aesthetics — transitioning to a more polished web-native design later would be a jarring change for existing users

**Alternatives Considered:**
- **Card-based UI (Material style)**: Rejected — cards with borders, padding, and headers consume 3-4x the vertical space per step. With 10 steps, cards would dominate the viewport, pushing the actual response off-screen
- **Enhanced purple pills**: Rejected — pills are fundamentally too small to display arguments, timing, and status. The pill format cannot fit the information density needed for meaningful tool execution visibility

---

## Decision 3: Inline Arguments at Level 0

**Decision:** Show truncated arguments directly in the collapsed tool step row (e.g., `Bash(npm view xlsx version desc...)`) using CSS `text-overflow: ellipsis`. Full arguments available on expand.

**Rationale:** Users should comprehend the full tool execution story at a glance without clicking anything. The collapsed view is the summary, not a teaser. Without inline args, users would expand every step just to understand what happened, defeating the purpose of having a collapsed view. This is especially critical when the same tool is called multiple times (e.g., 5 `Bash` calls — the args are the only differentiator).

**Trade-offs:**
- Long arguments (e.g., 500-char JSON body) truncate and may look messy at Level 0
- Adequate for Phase 1 with CSS ellipsis + "show full" on expand; may need per-tool-type special handling later (e.g., `Write` tool with file content as args)

**Alternatives Considered:**
- **Args hidden behind expand (Level 0 = name + timing only)**: Rejected — collapsed view becomes useless for understanding what happened. Users expand every step, adding interaction cost and negating the benefit of progressive disclosure

---

## Decision 4: Cancel/Interrupt Mechanism

**Decision:** Add a Stop button (replaces Send during streaming) and Escape keyboard shortcut that sends `POST /api/v1/sessions/{id}/interrupt` to the backend, aborts the client SSE connection, marks running steps as "cancelled", and preserves partial response content with a "[Response interrupted by user]" label.

**Rationale:** Users detect execution going down the wrong path and need to abort immediately rather than waiting through up to 30 turns. Multi-step tasks reviewing PRs, analyzing issues, or generating reports can take 30-60+ seconds — an escape hatch is essential.

**Trade-offs:**
- Adds backend interrupt endpoint complexity and requires coordinating client-side SSE abort with server-side CLI subprocess termination
- Escape key conflicts with autocomplete dismiss — resolved by priority: first Escape closes autocomplete, second Escape cancels stream

**Alternatives Considered:**
- **No cancel at all**: Rejected — wastes all remaining tokens/time on a known-wrong execution path. Unacceptable resource waste when the user already knows the approach is incorrect
- **Pause + resume**: Rejected — Claude Code SDK subprocess doesn't support pause/resume semantics. The CLI process is either running or interrupted; there is no middle state

---

## Decision 5: Completion Metadata Bar

**Decision:** Display "N steps | Xs | tokens in/out | $cost" after each assistant response completes. Left-aligned, monospace, subtle top border, fade-in animation. Cost omitted if zero; prefixed with "Interrupted:" if cancelled.

**Rationale:** Trust through transparency — users see the "receipt" of what happened for each response. Knowing the step count, duration, token usage, and cost lets users verify the response was reasonable and builds confidence in the system.

**Trade-offs:**
- Showing cost could cause sticker shock on expensive multi-step queries
- Adds visual noise to short single-step responses where metadata feels excessive

**Alternatives Considered:**
- **Hide metadata (current state)**: Rejected — data is already logged server-side but invisible to users, reducing trust and preventing cost awareness
- **Admin/settings panel only**: Rejected — lacks immediacy. Users want to see cost/time for the response they just received, not aggregate statistics later

---

## Decision 6: Auto-Collapse for 5+ Completed Steps

**Decision:** When completed steps exceed 5, collapse older steps into a descriptive summary line (e.g., "5 steps: list_pulls, get_pull x4 — 2.3s"). Keep the 2 most recent completed steps and the active running step always visible. Click to expand all. Re-collapsible.

**Rationale:** 10+ tool steps at ~30px each push the assistant's response text completely off-screen. Users must scroll past a wall of tool information to find the actual answer. Auto-collapse also reduces cognitive overload — seeing 10+ completed steps causes users to skip everything.

**Trade-offs:**
- Collapsed steps hide execution history by default — mitigated by the descriptive summary including tool names (e.g., "list_pulls, get_pull x4") so users can decide whether to expand

**Alternatives Considered:**
- **No collapsing (show all steps)**: Rejected — defeats progressive disclosure when workflows have 10-20 tool calls. The response text becomes buried

**Note:** Threshold of 5 is a pragmatic starting point, tunable based on real user feedback. Not over-optimized upfront.

---

## Decision 7: Backend — Forward Tool Results and Metadata via SSE

**Decision:** Stop suppressing `ToolResultBlock` content and `ResultMessage` metadata in the SSE pipeline. Forward `tool_use_id`, `content`, `is_error` for tool results, and `num_turns`, `total_cost_usd`, `duration_ms`, `usage` (token counts) for result metadata through the existing SSE stream as vendor extension fields.

**Rationale:** Downstream frontend requirement — Decisions 1-6 require tool results, arguments, and metadata to render. The data already flows through the pipeline (`_content_block_to_event()` receives it, `sdk_event_to_chunk()` actively discards it). The change is to stop discarding, not to add new data flow. Additionally, the backend should be a transparent pipe — let the frontend decide what to show/hide rather than the backend making display decisions.

**Trade-offs:**
- Increased SSE payload size — tool results can be 10KB+ per step. With 20 steps, a single response stream could be 200KB+
- Backward compatibility — existing frontends receive more data, mitigated by them ignoring unknown fields (OpenAI streaming format convention)

**Alternatives Considered:**
- **Separate fetch-on-demand API** (e.g., `GET /tool-results/{id}`): Rejected — adds latency on user expand click (user clicks, waits for network roundtrip), and requires backend result storage/caching that doesn't currently exist

---

## Decision 8: Error Recovery UX

**Decision:** Give error states special visual treatment: auto-expand error details, FAILED micro-badge, red background tint on the error step row, red-highlighted problematic argument fields (e.g., `"title": ""`), "Copy error" button with clipboard API, and "↩ retried" annotation linking failed step to its retry attempt.

**Rationale:** Three factors:
1. **Errors are common** — Claude frequently retries after validation errors, API failures, rate limits. Errors are a normal part of multi-step execution, not exceptional events
2. **Debugging was a pain point** — With suppressed tool results (Decision 7's "before" state), errors were invisible. Users had no way to understand what went wrong
3. **Self-healing narrative** — Showing error → retry → success demonstrates Claude's problem-solving ability. This builds trust rather than hiding mistakes behind a clean facade

**Trade-offs:**
- Error details add visual weight to the conversation flow
- "Copy error" button adds niche functionality most users won't use (but developers debugging integrations will value it)

**Alternatives Considered:**
- **Hide errors, show retry only**: Rejected — conceals important debugging information and misses the self-healing narrative that builds user trust
- **Generic error message** ("An error occurred"): Rejected — insufficient detail for users to understand what went wrong or whether the retry addressed the root cause

---

## Consequences

### Positive
- Users can see exactly what Claude is doing, building trust and reducing premature task abandonment
- Web experience matches CLI richness — no longer a degraded experience for browser users
- Users and support can diagnose issues by inspecting tool arguments, results, and errors directly in the UI
- Error → retry → success narrative demonstrates Claude's problem-solving capability
- Cancel mechanism prevents resource waste on wrong-path executions

### Negative
- Significant frontend complexity increase — 8 interrelated decisions touching state management, SSE parsing, animations, keyboard shortcuts
- CLI-style aesthetic limits appeal to non-developer audiences
- Increased SSE bandwidth from forwarding tool results

### Risks
- **Performance on many steps** — Rendering 20+ tool steps with args, results, and animations could cause React re-render thrashing and scroll jank (mitigated by: auto-collapse bounds visible DOM elements to ~7; benchmark first, optimize with virtualization only if real bottlenecks appear)

---

## References
- ADR-001: Platform Strategy
- ADR-002: Technical Architecture
- Design plan: `task_core-engine/` planning artifacts
- Interactive mockup: `docs/mockups/enhanced-tool-steps-ux.html` (v3)
- Claude Code CLI UX patterns (filled circles, parenthesized args, `⎿` connectors)
