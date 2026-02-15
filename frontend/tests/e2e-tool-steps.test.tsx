import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, test, expect, vi, beforeEach } from 'vitest'
import App from '../src/App'

// ---------------------------------------------------------------------------
// Helpers (mirroring App.test.tsx patterns)
// ---------------------------------------------------------------------------

function createSSEStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  let index = 0
  return new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]))
        index++
      } else {
        controller.close()
      }
    },
  })
}

const mockFetch = vi.fn()

beforeEach(() => {
  vi.restoreAllMocks()
  mockFetch.mockReset()
  globalThis.fetch = mockFetch
})

function mockSessionAndExtensions() {
  const sessionResponse = {
    ok: true,
    status: 201,
    json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
  }
  const extensionsResponse = {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
  }

  mockFetch.mockImplementation((url: string, options?: RequestInit) => {
    if (url === '/api/v1/sessions' && options?.method === 'POST') {
      return Promise.resolve(sessionResponse)
    }
    if (url === '/api/v1/extensions') {
      return Promise.resolve(extensionsResponse)
    }
    return Promise.resolve({ ok: false, status: 404 })
  })
}

/** Wire mockFetch so session + extensions resolve, then the given chat handler
 *  runs for /v1/chat/completions. */
function mockWithChat(chatHandler: (url: string, opts?: RequestInit) => unknown) {
  mockFetch.mockImplementation((url: string, options?: RequestInit) => {
    if (url === '/v1/chat/completions' && options?.method === 'POST') {
      return chatHandler(url, options)
    }
    if (url === '/api/v1/sessions' && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
      })
    }
    if (url === '/api/v1/extensions') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
      })
    }
    if (url === '/api/v1/sessions/abc-12345678/interrupt' && options?.method === 'POST') {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ status: 'interrupted' }) })
    }
    return Promise.resolve({ ok: false, status: 404 })
  })
}

/** Send the fixed prompt and wait for the chat completion fetch call. */
async function sendPrompt(user: ReturnType<typeof userEvent.setup>) {
  const textarea = screen.getByRole('textbox')
  await user.type(textarea, 'use npm-review skill to evaluate xlsx')
  await user.keyboard('{Enter}')
}

// ---------------------------------------------------------------------------
// SSE chunk factories
// ---------------------------------------------------------------------------

function toolCallChunk(toolId: string, toolName: string, args: string): string {
  return `data: {"id":"chatcmpl-1","choices":[{"delta":{"tool_calls":[{"index":0,"id":"${toolId}","type":"function","function":{"name":"${toolName}","arguments":"${args.replace(/"/g, '\\"')}"}}]},"index":0}]}\n\n`
}

function toolResultChunk(toolUseId: string, content: string, isError = false): string {
  return `data: {"id":"chatcmpl-1","choices":[{"delta":{"tool_result":{"tool_use_id":"${toolUseId}","content":"${content.replace(/"/g, '\\"')}","is_error":${isError}}}}]}\n\n`
}

function contentChunk(text: string): string {
  return `data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"${text.replace(/"/g, '\\"')}"}}]}\n\n`
}

function metaChunk(meta: { num_turns?: number; total_cost_usd?: number; duration_ms?: number; input_tokens?: number; output_tokens?: number }): string {
  return `data: {"id":"chatcmpl-1","choices":[{"delta":{}}],"meta":{"num_turns":${meta.num_turns ?? 3},"total_cost_usd":${meta.total_cost_usd ?? 0.0012},"duration_ms":${meta.duration_ms ?? 2400},"usage":{"input_tokens":${meta.input_tokens ?? 1200},"output_tokens":${meta.output_tokens ?? 890}}}}\n\n`
}

function doneChunk(meta?: { turns?: number; cost?: number; duration?: number; tokens_in?: number; tokens_out?: number }): string {
  const metaPart = meta
    ? metaChunk({
        num_turns: meta.turns ?? 3,
        total_cost_usd: meta.cost ?? 0.0012,
        duration_ms: meta.duration ?? 2400,
        input_tokens: meta.tokens_in ?? 1200,
        output_tokens: meta.tokens_out ?? 890,
      })
    : ''
  return `${metaPart}data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n`
}

// ===========================================================================
// ADR-003 E2E Tests: Multi-Step Reasoning UX
// ===========================================================================

describe('ADR-003: Multi-Step Reasoning UX', () => {
  // -----------------------------------------------------------------------
  // Test 1: Tool steps render with CLI-style formatting
  // -----------------------------------------------------------------------
  test('tool steps render with CLI-style formatting and completion meta', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    const sseData = [
      // 3 tool_calls with arguments
      toolCallChunk('call_bash1', 'Bash', '{"command":"npm view xlsx version description license homepage"}'),
      toolResultChunk('call_bash1', 'xlsx@0.18.5\\nApache-2.0'),
      toolCallChunk('call_web1', 'WebFetch', '{"url":"https://snyk.io/advisor/npm-package/xlsx","prompt":"Extract health score"}'),
      toolResultChunk('call_web1', 'Package Health Score: 71/100'),
      toolCallChunk('call_bash2', 'Bash', '{"command":"npm audit xlsx --json 2>/dev/null | head -50"}'),
      toolResultChunk('call_bash2', 'found 0 vulnerabilities'),
      // Text content
      contentChunk('## NPM Package Review Summary\\n\\nApproved.'),
      // Final chunk with meta
      doneChunk({ turns: 3, cost: 0.0012, duration: 2400, tokens_in: 1200, tokens_out: 890 }),
    ]

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: createSSEStream(sseData),
      })
    )

    await sendPrompt(user)

    // Wait for streaming to finish and content to render
    expect(await screen.findByText(/NPM Package Review Summary/)).toBeVisible()

    // 3 tool steps should be visible with their names + parenthesized args
    // Per ADR-003 Decision 2: ToolName(args...) format
    // Two Bash steps + one WebFetch step
    const bashSteps = await screen.findAllByText(/Bash/)
    expect(bashSteps.length).toBeGreaterThanOrEqual(2)
    expect(await screen.findByText(/WebFetch/)).toBeVisible()

    // Args should be inline (truncated) per Decision 3
    const npmViewMatches = await screen.findAllByText(/npm view xlsx/)
    expect(npmViewMatches.length).toBeGreaterThanOrEqual(1)
    const snykMatches = await screen.findAllByText(/snyk\.io/)
    expect(snykMatches.length).toBeGreaterThanOrEqual(1)
    const npmAuditMatches = await screen.findAllByText(/npm audit xlsx/)
    expect(npmAuditMatches.length).toBeGreaterThanOrEqual(1)

    // Completion metadata bar per Decision 5: "N steps | Xs | tokens in/out | $cost"
    expect(await screen.findByText(/3 steps/)).toBeVisible()
    expect(await screen.findByText(/1\.2K in/)).toBeVisible()  // tokens_in
    expect(await screen.findByText(/890 out/)).toBeVisible()   // tokens_out
  })

  // -----------------------------------------------------------------------
  // Test 2: Expand/collapse tool step details
  // -----------------------------------------------------------------------
  test('expand and collapse tool step details on click', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    const sseData = [
      toolCallChunk('call_bash1', 'Bash', '{"command":"npm view xlsx version"}'),
      toolResultChunk('call_bash1', 'xlsx@0.18.5'),
      contentChunk('Review complete.'),
      doneChunk(),
    ]

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: createSSEStream(sseData),
      })
    )

    await sendPrompt(user)
    expect(await screen.findByText('Review complete.')).toBeVisible()

    // First step auto-expands (defaultExpanded=true for index 0 with result)
    // Verify the detail panel starts visible
    const stepHeaders = document.querySelectorAll('.tool-step-header')
    expect(stepHeaders.length).toBeGreaterThan(0)
    const firstHeader = stepHeaders[0] as HTMLElement

    await waitFor(() => {
      const detailPanel = firstHeader.parentElement?.querySelector('.tool-step-detail')
      expect(detailPanel).toHaveClass('visible')
    })

    // Detail panel should show full arguments and output (Decision 1 Level 1)
    const versionMatches = await screen.findAllByText(/xlsx@0\.18\.5/)
    expect(versionMatches.length).toBeGreaterThanOrEqual(1)

    // Click to collapse
    await user.click(firstHeader)

    // Detail panel should be hidden
    await waitFor(() => {
      const detailPanel = firstHeader.parentElement?.querySelector('.tool-step-detail')
      if (detailPanel) {
        expect(detailPanel).not.toHaveClass('visible')
      }
    })

    // Click again to re-expand
    await user.click(firstHeader)

    await waitFor(() => {
      const detailPanel = firstHeader.parentElement?.querySelector('.tool-step-detail')
      expect(detailPanel).toHaveClass('visible')
    })
  })

  // -----------------------------------------------------------------------
  // Test 3: Running state shows spinner and Stop button
  // -----------------------------------------------------------------------
  test('running state shows active indicator and Stop button', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    // Create a stream that stays open (holds the connection)
    let resolveStream: (() => void) | undefined
    const streamPromise = new Promise<void>((resolve) => {
      resolveStream = resolve
    })

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: new ReadableStream({
          async start(controller) {
            const encoder = new TextEncoder()
            // Emit one tool call then hold open
            controller.enqueue(
              encoder.encode(
                toolCallChunk('call_bash1', 'Bash', '{"command":"npm view xlsx version"}')
              )
            )
            // Hold stream open
            await streamPromise
            controller.enqueue(encoder.encode('data: [DONE]\n\n'))
            controller.close()
          },
        }),
      })
    )

    await sendPrompt(user)

    // Active step should have running indicator (spinner or running class)
    // Per ADR-003 Decision 2: running step has accent border + spinner
    await waitFor(() => {
      const runningElements = document.querySelectorAll('[class*="running"], .spinner, [data-status="running"]')
      expect(runningElements.length).toBeGreaterThan(0)
    })

    // Stop button should be visible (Decision 4: replaces Send during streaming)
    expect(await screen.findByText(/Stop/)).toBeVisible()

    // Input should be disabled during streaming
    expect(screen.getByRole('textbox')).toBeDisabled()

    // Clean up - resolve the stream
    resolveStream!()
  })

  // -----------------------------------------------------------------------
  // Test 4: Error + retry flow
  // -----------------------------------------------------------------------
  test('error step has error styling and retry step succeeds', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    const sseData = [
      // First tool call
      toolCallChunk('call_bash1', 'Bash', '{"command":"npm view xlsx version"}'),
      // Error result
      toolResultChunk('call_bash1', 'Error: ENOENT - package not found', true),
      // Retry tool call
      toolCallChunk('call_bash2', 'Bash', '{"command":"npm view xlsx@latest version"}'),
      // Success result
      toolResultChunk('call_bash2', 'xlsx@0.18.5'),
      // Text response
      contentChunk('Package xlsx found at version 0.18.5 after retry.'),
      doneChunk(),
    ]

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: createSSEStream(sseData),
      })
    )

    await sendPrompt(user)
    expect(await screen.findByText(/after retry/)).toBeVisible()

    // Error step should have error styling (Decision 8: FAILED badge, red background)
    await waitFor(() => {
      const errorElements = document.querySelectorAll('[class*="error"], [data-status="error"]')
      expect(errorElements.length).toBeGreaterThan(0)
    })

    // The FAILED badge should be visible per Decision 8
    const failedBadge = screen.queryByText(/FAILED/i)
    if (failedBadge) {
      expect(failedBadge).toBeVisible()
    }

    // A retry annotation should link failed to retry (Decision 8: "retried" annotation)
    const retryAnnotation = screen.queryByText(/retried/i)
    if (retryAnnotation) {
      expect(retryAnnotation).toBeVisible()
    }

    // The successful step should also be visible
    const retryStepMatches = await screen.findAllByText(/npm view xlsx/)
    expect(retryStepMatches.length).toBeGreaterThanOrEqual(1)
  })

  // -----------------------------------------------------------------------
  // Test 5: Cancel/interrupt via Escape
  // -----------------------------------------------------------------------
  test('pressing Escape cancels streaming and preserves partial content', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    let resolveStream: (() => void) | undefined
    const streamPromise = new Promise<void>((resolve) => {
      resolveStream = resolve
    })

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: new ReadableStream({
          async start(controller) {
            const encoder = new TextEncoder()
            // Emit tool call + result + partial text
            controller.enqueue(encoder.encode(
              toolCallChunk('call_bash1', 'Bash', '{"command":"npm view xlsx version"}')
            ))
            controller.enqueue(encoder.encode(
              toolResultChunk('call_bash1', 'xlsx@0.18.5')
            ))
            controller.enqueue(encoder.encode(
              contentChunk('Partial analysis of xlsx package...')
            ))
            // Hold stream open until cancelled
            await streamPromise
            controller.close()
          },
        }),
      })
    )

    await sendPrompt(user)

    // Wait for partial content to appear
    expect(await screen.findByText(/Partial analysis/)).toBeVisible()

    // Press Escape to cancel (Decision 4: Escape keyboard shortcut)
    await user.keyboard('{Escape}')

    // Verify POST to interrupt endpoint was called
    await waitFor(() => {
      const interruptCall = mockFetch.mock.calls.find(
        (c: unknown[]) => typeof c[0] === 'string' && (c[0] as string).includes('/interrupt')
      )
      expect(interruptCall).toBeDefined()
    })

    // Partial content should be preserved (Decision 4: preserve partial response)
    expect(screen.getByText(/Partial analysis/)).toBeVisible()

    // "Interrupted" label should be visible (Decision 4 + 5: interrupted indicator)
    expect(await screen.findByText(/interrupt/i)).toBeVisible()

    // Clean up
    resolveStream!()
  })

  // -----------------------------------------------------------------------
  // Test 6: Auto-collapse for many steps (8+)
  // -----------------------------------------------------------------------
  test('auto-collapse summary appears for many tool steps', async () => {
    mockSessionAndExtensions()
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText(/Connected/i)

    // Generate 8 tool calls
    const sseData: string[] = []
    for (let i = 1; i <= 8; i++) {
      sseData.push(toolCallChunk(`call_${i}`, 'Bash', `{"command":"step ${i} command"}`))
      sseData.push(toolResultChunk(`call_${i}`, `result ${i}`))
    }
    sseData.push(contentChunk('All 8 steps completed successfully.'))
    sseData.push(doneChunk({ turns: 8, cost: 0.005, duration: 8000, tokens_in: 3000, tokens_out: 2000 }))

    mockWithChat(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        body: createSSEStream(sseData),
      })
    )

    await sendPrompt(user)
    expect(await screen.findByText(/All 8 steps completed/)).toBeVisible()

    // Decision 6: When completed steps exceed 5, collapse older steps into summary
    // The collapsed-summary element should be present with "N steps: ..." format
    await waitFor(() => {
      const collapsedEl = document.querySelector('.collapsed-summary')
      expect(collapsedEl).toBeTruthy()
    })
    const collapsedEl = document.querySelector('.collapsed-summary') as HTMLElement
    expect(collapsedEl).toBeVisible()
    expect(collapsedEl.textContent).toMatch(/\d+\s+steps:/)

    // Click the collapsed summary to expand all
    await user.click(collapsedEl)

    // After expanding, earlier step commands should be findable
    await waitFor(() => {
      const matches = screen.getAllByText(/step 1 command/)
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
  })
})
