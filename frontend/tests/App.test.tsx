import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, test, expect, vi, beforeEach } from 'vitest'
import App from '../src/App'

// Helper to create a ReadableStream from SSE text
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

// Mock fetch globally
const mockFetch = vi.fn()

beforeEach(() => {
  vi.restoreAllMocks()
  mockFetch.mockReset()
  globalThis.fetch = mockFetch
})

// Helper: set up session + extensions mock
function mockSessionAndExtensions(
  extensions?: {
    mcp_servers?: Array<{ name: string; status: string; tool_count: number | null }>;
    skills?: Array<{ name: string; description: string; type: string; invoke_prefix: string }>;
    commands?: Array<{ name: string; description: string; type: string; invoke_prefix: string }>;
    all_slash_commands?: Array<{ name: string; description: string; type: string; invoke_prefix: string }>;
    total_count?: number;
  }
) {
  const defaultExtensions = {
    mcp_servers: [],
    skills: [],
    commands: [],
    all_slash_commands: [],
    total_count: 0,
    ...extensions,
  }

  mockFetch.mockImplementation((url: string, options?: RequestInit) => {
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
        json: () => Promise.resolve(defaultExtensions),
      })
    }
    return Promise.resolve({ ok: false, status: 404 })
  })
}

// ==========================================
// TASK-010: Basic React Chatbot Tests
// ==========================================

describe('TASK-010: Basic Chatbot', () => {
  test('creates session on mount and shows connected status', async () => {
    mockSessionAndExtensions()

    render(<App />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v1/sessions', expect.objectContaining({ method: 'POST' }))
    })

    expect(await screen.findByText(/Connected/i)).toBeVisible()
    expect(await screen.findByText(/abc-1234/)).toBeVisible()
  })

  test('displays connection error on session failure', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.reject(new Error('Network error'))
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    render(<App />)

    expect(await screen.findByText(/Failed to connect/i)).toBeVisible()
    expect(screen.getByText(/Disconnected/i)).toBeVisible()

    // Input should be disabled
    const textarea = screen.getByRole('textbox')
    expect(textarea).toBeDisabled()
  })

  test('sends message and displays streaming response', async () => {
    mockSessionAndExtensions()

    const user = userEvent.setup()
    render(<App />)

    // Wait for session to be created
    await screen.findByText(/Connected/i)

    // Set up SSE response for chat completions
    const sseData = [
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant","content":""},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hello"},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":" there"},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ]

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: createSSEStream(sseData),
        })
      }
      // Keep session mock working
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    // Type and send message
    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Hi there')
    await user.keyboard('{Enter}')

    // Verify user message visible
    expect(await screen.findByText('Hi there')).toBeVisible()

    // Verify fetch called with correct params
    await waitFor(() => {
      const chatCall = mockFetch.mock.calls.find(
        (c: unknown[]) => c[0] === '/v1/chat/completions'
      )
      expect(chatCall).toBeDefined()
      const body = JSON.parse((chatCall![1] as RequestInit).body as string)
      expect(body.stream).toBe(true)
      expect(body.messages).toContainEqual(expect.objectContaining({ role: 'user', content: 'Hi there' }))
    })

    // Verify assistant message appears
    expect(await screen.findByText('Hello there')).toBeVisible()
  })

  test('empty input does not send', async () => {
    mockSessionAndExtensions()

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox')
    await user.click(textarea)
    await user.keyboard('{Enter}')

    // No chat completion call should be made
    await waitFor(() => {
      const chatCalls = mockFetch.mock.calls.filter(
        (c: unknown[]) => c[0] === '/v1/chat/completions'
      )
      expect(chatCalls).toHaveLength(0)
    })
  })

  test('Shift+Enter inserts newline without sending', async () => {
    mockSessionAndExtensions()

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    await user.type(textarea, 'line 1')
    await user.keyboard('{Shift>}{Enter}{/Shift}')

    // No message sent
    const chatCalls = mockFetch.mock.calls.filter(
      (c: unknown[]) => c[0] === '/v1/chat/completions'
    )
    expect(chatCalls).toHaveLength(0)

    // Textarea has multiline content
    expect(textarea.value).toContain('line 1')
    expect(textarea.value).toContain('\n')
  })

  test('shows loading indicator during response', async () => {
    mockSessionAndExtensions()

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    // Create a never-resolving stream to keep loading state
    let resolveStream: (() => void) | undefined
    const streamPromise = new Promise<void>((resolve) => { resolveStream = resolve })

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: new ReadableStream({
            async start(controller) {
              const encoder = new TextEncoder()
              controller.enqueue(encoder.encode('data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant","content":""},"index":0}]}\n\n'))
              // Hold open until we resolve
              await streamPromise
              controller.enqueue(encoder.encode('data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n'))
              controller.enqueue(encoder.encode('data: [DONE]\n\n'))
              controller.close()
            },
          }),
        })
      }
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Hello')
    await user.keyboard('{Enter}')

    // Thinking indicator should appear
    expect(await screen.findByText(/Thinking/i)).toBeVisible()

    // Textarea should be disabled while loading
    expect(screen.getByRole('textbox')).toBeDisabled()

    // Resolve stream
    resolveStream!()

    // Thinking should disappear
    await waitFor(() => {
      expect(screen.queryByText(/Thinking/i)).not.toBeInTheDocument()
    })
  })

  test('API error shows error banner', async () => {
    mockSessionAndExtensions()

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ error: { message: 'Service unavailable' } }),
        })
      }
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Hello')
    await user.keyboard('{Enter}')

    // Error banner should appear
    expect(await screen.findByRole('alert')).toBeVisible()

    // Input should still be usable after error
    await waitFor(() => {
      expect(screen.getByRole('textbox')).not.toBeDisabled()
    })
  })

  test('zustand is a dependency; no ag-ui, no radix, no tailwind', async () => {
    const pkg = await import('../package.json')
    const allDeps = {
      ...pkg.dependencies,
      ...pkg.devDependencies,
    }
    const depNames = Object.keys(allDeps)

    expect(depNames).toContain('zustand')
    expect(depNames.some((d: string) => d.includes('ag-ui'))).toBe(false)
    expect(depNames.some((d: string) => d.includes('@radix-ui'))).toBe(false)
    expect(depNames).not.toContain('tailwindcss')
  })
})

// ==========================================
// TASK-010a: Extension UX Tests
// ==========================================

describe('TASK-010a: Extension UX', () => {
  const extensionsWithCommands = {
    mcp_servers: [
      { name: 'github', status: 'configured', tool_count: null },
      { name: 'slack', status: 'configured', tool_count: null },
    ],
    skills: [
      { name: 'code-review', description: 'Review code', type: 'skill', invoke_prefix: '/code-review' },
    ],
    commands: [
      { name: 'deploy', description: 'Deploy app', type: 'command', invoke_prefix: '/deploy' },
    ],
    all_slash_commands: [
      { name: 'code-review', description: 'Review code', type: 'skill', invoke_prefix: '/code-review' },
      { name: 'deploy', description: 'Deploy app', type: 'command', invoke_prefix: '/deploy' },
    ],
    total_count: 4,
  }

  test('slash autocomplete opens on / and shows commands', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '/')

    // Autocomplete popup should appear
    const popup = await screen.findByRole('listbox')
    expect(popup).toBeVisible()
    expect(screen.getByText('code-review')).toBeVisible()
    expect(screen.getByText('deploy')).toBeVisible()
  })

  test('slash autocomplete filters by input', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '/code')

    const popup = await screen.findByRole('listbox')
    expect(popup).toBeVisible()
    expect(screen.getByText('code-review')).toBeVisible()
    expect(screen.queryByText('deploy')).not.toBeInTheDocument()
  })

  test('slash autocomplete selects on click', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    await user.type(textarea, '/')

    await screen.findByRole('listbox')
    const option = screen.getByText('code-review')
    await user.click(option)

    // Textarea should have selected command with trailing space
    expect(textarea.value).toBe('/code-review ')

    // Popup should be closed
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  test('slash autocomplete keyboard navigation', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    await user.type(textarea, '/')

    await screen.findByRole('listbox')

    // Press Down to highlight first item, Enter to select
    await user.keyboard('{ArrowDown}{Enter}')

    expect(textarea.value).toBe('/code-review ')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  test('slash autocomplete escape dismisses', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    await user.type(textarea, '/')

    await screen.findByRole('listbox')

    await user.keyboard('{Escape}')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(textarea.value).toBe('/')
  })

  test('slash autocomplete shows message when no extensions available', async () => {
    mockSessionAndExtensions({
      all_slash_commands: [],
      total_count: 0,
    })

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '/')

    expect(await screen.findByText(/No extensions available/i)).toBeVisible()
  })

  test('slash autocomplete handles fetch error gracefully', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.reject(new Error('Network error'))
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, '/')

    expect(await screen.findByText(/Could not load extensions/i)).toBeVisible()

    // User can still type normally
    expect(textarea).not.toBeDisabled()
  })

  test('tool calls render inline indicator with server > tool format', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    // SSE stream with tool_calls delta
    const sseData = [
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant","content":""},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"mcp__github__list_issues","arguments":""}}]},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Here are the issues."},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ]

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: createSSEStream(sseData),
        })
      }
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve(extensionsWithCommands),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Show issues')
    await user.keyboard('{Enter}')

    // Tool indicator should show parsed name
    expect(await screen.findByText(/github > list_issues/)).toBeVisible()

    // Content should also appear
    expect(await screen.findByText('Here are the issues.')).toBeVisible()
  })

  test('non-MCP tool name shows raw name without crashing', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const sseData = [
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant","content":""},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"custom_tool","arguments":""}}]},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Done."},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ]

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: createSSEStream(sseData),
        })
      }
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve(extensionsWithCommands),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Do something')
    await user.keyboard('{Enter}')

    // Raw tool name should be shown
    expect(await screen.findByText('custom_tool')).toBeVisible()
    expect(await screen.findByText('Done.')).toBeVisible()
  })

  test('tool name with underscores in server name parsed correctly', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const sseData = [
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"role":"assistant","content":""},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"mcp__my_db__query_users","arguments":""}}]},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Results."},"index":0}]}\n\n',
      'data: {"id":"chatcmpl-1","choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ]

    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/v1/chat/completions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 200,
          headers: new Headers({ 'content-type': 'text/event-stream' }),
          body: createSSEStream(sseData),
        })
      }
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: true, status: 201,
          json: () => Promise.resolve({ session_id: 'abc-12345678', status: 'ready', source: 'pre-warm' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve(extensionsWithCommands),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    const textarea = screen.getByRole('textbox')
    await user.type(textarea, 'Query users')
    await user.keyboard('{Enter}')

    // Server name with underscores should parse correctly
    expect(await screen.findByText('my_db > query_users')).toBeVisible()
  })

  test('session creation failure shows error and disables input', async () => {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/v1/sessions' && options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ error: 'At capacity' }),
        })
      }
      if (url === '/api/v1/extensions') {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ mcp_servers: [], skills: [], commands: [], all_slash_commands: [], total_count: 0 }),
        })
      }
      return Promise.resolve({ ok: false, status: 404 })
    })

    render(<App />)

    expect(await screen.findByText(/Failed to create session/i)).toBeVisible()
    expect(screen.getByText(/Disconnected/i)).toBeVisible()
    expect(screen.getByRole('textbox')).toBeDisabled()
  })

  test('extension status badge shows count in header', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    render(<App />)

    await screen.findByText(/Connected/i)

    // Should show total count as badge
    expect(await screen.findByText(/4 extensions/i)).toBeVisible()
  })

  test('extension status dropdown opens on badge click', async () => {
    mockSessionAndExtensions(extensionsWithCommands)

    const user = userEvent.setup()
    render(<App />)

    await screen.findByText(/Connected/i)

    const badge = await screen.findByText(/4 extensions/i)
    await user.click(badge)

    // Dropdown should show categorized lists
    expect(await screen.findByText(/MCP Servers/i)).toBeVisible()
    expect(screen.getByText('github')).toBeVisible()
    expect(screen.getByText('slack')).toBeVisible()
    expect(screen.getByText(/Skills/i)).toBeVisible()
    expect(screen.getByText(/Commands/i)).toBeVisible()
  })
})
