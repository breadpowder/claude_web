import { useState, useEffect, useRef, useCallback, type KeyboardEvent, type ChangeEvent } from 'react'
import './App.css'

// ── Data model ──

type ToolStepStatus = 'running' | 'completed' | 'error' | 'cancelled'

interface ToolStep {
  id: string
  name: string
  displayName: string
  arguments: string
  status: ToolStepStatus
  result: string
  isError: boolean
  startedAt: number
  completedAt: number | null
}

interface CompletionMeta {
  numTurns: number
  totalCostUsd: number
  durationMs: number
  inputTokens: number
  outputTokens: number
}

interface Message {
  role: 'user' | 'assistant' | 'error'
  content: string
  toolCalls?: ToolCall[]
  toolSteps?: ToolStep[]
  completionMeta?: CompletionMeta | null
  interrupted?: boolean
}

// Keep for backwards compat with existing code paths
interface ToolCall {
  id: string
  name: string
  displayName: string
}

interface SlashCommand {
  name: string
  description: string
  type: string
  invoke_prefix: string
}

interface ExtensionData {
  mcp_servers: Array<{ name: string; status: string; tool_count: number | null }>
  skills: Array<{ name: string; description: string; type: string; invoke_prefix: string }>
  commands: Array<{ name: string; description: string; type: string; invoke_prefix: string }>
  all_slash_commands: SlashCommand[]
  total_count: number
}

// ── Helpers ──

function formatToolName(name: string): string {
  const match = name.match(/^mcp__(.+?)__(.+)$/)
  if (match) {
    return `${match[1]} > ${match[2]}`
  }
  return name
}

function formatArgs(argsJson: string): string {
  try {
    const obj = JSON.parse(argsJson)
    if (typeof obj === 'object' && obj !== null) {
      return Object.entries(obj)
        .map(([k, v]) => `${k}: ${typeof v === 'string' ? `"${v}"` : JSON.stringify(v)}`)
        .join(', ')
    }
    return argsJson
  } catch {
    return argsJson
  }
}

function formatTiming(step: ToolStep): string {
  if (step.status === 'running') return ''
  if (step.status === 'cancelled') return '\u2013'
  if (!step.completedAt) return ''
  const ms = step.completedAt - step.startedAt
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

// ── ToolStep component (CLI-style) ──

function ToolStepRow({ step, defaultExpanded }: { step: ToolStep; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded || step.isError)
  const timing = formatTiming(step)
  const inlineArgs = formatArgs(step.arguments)

  const isError = step.status === 'error'
  const isCancelled = step.status === 'cancelled'
  const isRunning = step.status === 'running'

  const headerClass = [
    'tool-step-header',
    isRunning ? 'running-row' : '',
    isError ? 'error-row' : '',
  ].filter(Boolean).join(' ')

  const handleCopyError = () => {
    navigator.clipboard.writeText(step.result)
  }

  return (
    <div className="tool-step">
      <div
        className={headerClass}
        onClick={() => !isRunning && setExpanded(e => !e)}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            if (!isRunning) setExpanded(ex => !ex)
          }
        }}
        style={isCancelled ? { opacity: 0.6 } : undefined}
      >
        <span className="expand-hint">{expanded ? '\u25BE' : '\u25B8'}</span>
        <span className="step-marker" data-status={step.status}>
          {isRunning ? <span className="spinner" /> : '\u25CF'}
        </span>
        <span className="tool-name" style={isError ? { color: 'var(--error)' } : isCancelled ? { color: 'var(--warning)' } : undefined}>
          {step.displayName}
        </span>
        <span className="tool-paren" style={isError ? { color: 'rgba(239,68,68,0.6)' } : isCancelled ? { color: 'rgba(245,158,11,0.6)' } : undefined}>(</span>
        <span
          className="tool-args-inline"
          style={
            isError ? { color: 'rgba(239,68,68,0.6)' }
            : isCancelled ? { color: 'rgba(245,158,11,0.5)', textDecoration: 'line-through' }
            : undefined
          }
        >
          {inlineArgs}
        </span>
        <span className="tool-paren-close" style={isError ? { color: 'rgba(239,68,68,0.6)' } : isCancelled ? { color: 'rgba(245,158,11,0.6)' } : undefined}>)</span>
        {isRunning && <span className="tool-timing pulse" />}
        {!isRunning && <span className="tool-timing" style={isCancelled ? { color: 'var(--warning)' } : undefined}>{timing}</span>}
        {isError && <span className="error-badge">FAILED</span>}
      </div>

      {/* Result preview for completed, non-expanded, first step */}
      {step.status === 'completed' && !expanded && step.result && (
        <div className="result-preview">
          <span className="result-connector">{'\u23BF'}</span>
          <span className="result-preview-text">{step.result.slice(0, 80)}</span>
        </div>
      )}

      {/* Expanded detail panel */}
      <div className={`tool-step-detail ${expanded ? 'visible' : ''}`} data-status={step.status}>
        <div className="detail-label">Full arguments</div>
        <div className="detail-content">{step.arguments}</div>
        {step.result && (
          <>
            <div className="detail-label">
              {isError ? 'Error' : 'Output'}
              {!isError && <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: '10px' }}> ({step.result.length > 1024 ? `${(step.result.length / 1024).toFixed(1)} KB` : `${step.result.length} chars`})</span>}
            </div>
            <div className={`detail-content ${isError ? 'error-content' : ''}`}>
              {step.result.slice(0, 2000)}
            </div>
            {step.result.length > 2000 && (
              <button className="show-full" onClick={(e) => { e.stopPropagation() }}>
                Show full result ({(step.result.length / 1024).toFixed(1)} KB)
              </button>
            )}
            {isError && (
              <button className="copy-error-btn" onClick={(e) => { e.stopPropagation(); handleCopyError() }}>
                Copy error
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Collapsed summary for 5+ steps ──

function CollapsedSteps({ steps }: { steps: ToolStep[] }) {
  const [expanded, setExpanded] = useState(false)

  // Build summary: "5 steps: list_pulls, get_pull x4"
  const nameCounts: Record<string, number> = {}
  let totalTime = 0
  for (const s of steps) {
    const short = s.displayName.split(' > ').pop() || s.displayName
    nameCounts[short] = (nameCounts[short] || 0) + 1
    if (s.completedAt && s.startedAt) totalTime += s.completedAt - s.startedAt
  }
  const parts = Object.entries(nameCounts).map(([n, c]) => c > 1 ? `${n} \u00D7${c}` : n)
  const summary = `${steps.length} steps: ${parts.join(', ')}`
  const timingStr = totalTime < 1000 ? `${totalTime}ms` : `${(totalTime / 1000).toFixed(1)}s`

  return (
    <>
      <div className={`collapsed-summary ${expanded ? 'expanded' : ''}`} onClick={() => setExpanded(e => !e)}>
        <span className="collapse-icon">{'\u25B8'}</span>
        <span className="step-marker" data-status="completed">{'\u25CF'}</span>
        <span>{summary}</span>
        <span className="tool-timing">{timingStr}</span>
      </div>
      <div className={`expanded-steps-wrap ${expanded ? 'visible' : ''}`}>
        {steps.map(s => <ToolStepRow key={s.id} step={s} defaultExpanded={false} />)}
      </div>
    </>
  )
}

// ── ToolSteps container with auto-collapse logic ──

function ToolStepsContainer({ steps }: { steps: ToolStep[] }) {
  if (steps.length === 0) return null

  const completedSteps = steps.filter(s => s.status !== 'running')
  const runningStep = steps.find(s => s.status === 'running')
  const AUTO_COLLAPSE_THRESHOLD = 5

  if (completedSteps.length > AUTO_COLLAPSE_THRESHOLD) {
    const collapsedSteps = completedSteps.slice(0, completedSteps.length - 2)
    const recentSteps = completedSteps.slice(completedSteps.length - 2)

    return (
      <div className="tool-steps">
        <CollapsedSteps steps={collapsedSteps} />
        {recentSteps.map((s, i) => <ToolStepRow key={s.id} step={s} defaultExpanded={false} />)}
        {runningStep && <ToolStepRow key={runningStep.id} step={runningStep} defaultExpanded={false} />}
      </div>
    )
  }

  return (
    <div className="tool-steps">
      {steps.map((s, i) => (
        <ToolStepRow key={s.id} step={s} defaultExpanded={i === 0 && s.status === 'completed' && !!s.result} />
      ))}
    </div>
  )
}

// ── CompletionMetaBar ──

function CompletionMetaBar({ meta, interrupted }: { meta: CompletionMeta; interrupted?: boolean }) {
  const parts: string[] = []

  if (interrupted) {
    parts.push('Interrupted')
    const stepCount = meta.numTurns
    if (stepCount > 0) parts.push(`${stepCount} steps completed`)
    if (meta.durationMs > 0) {
      parts.push(meta.durationMs < 1000 ? `${meta.durationMs}ms` : `${(meta.durationMs / 1000).toFixed(1)}s`)
    }
  } else {
    if (meta.numTurns > 0) parts.push(`${meta.numTurns} steps`)
    if (meta.durationMs > 0) {
      parts.push(meta.durationMs < 1000 ? `${meta.durationMs}ms` : `${(meta.durationMs / 1000).toFixed(1)}s`)
    }
    if (meta.inputTokens > 0 || meta.outputTokens > 0) {
      parts.push(`${formatTokens(meta.inputTokens)} in / ${formatTokens(meta.outputTokens)} out`)
    }
    if (meta.totalCostUsd > 0) {
      parts.push(`$${meta.totalCostUsd.toFixed(4)}`)
    }
  }

  if (parts.length === 0) return null

  return (
    <div className={`completion-meta ${interrupted ? 'interrupted' : ''}`}>
      {parts.join(' | ')}
    </div>
  )
}

// ── Main App ──

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Extension state
  const [extensions, setExtensions] = useState<ExtensionData | null>(null)
  const [extensionError, setExtensionError] = useState(false)
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [showExtDropdown, setShowExtDropdown] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Create session on mount
  useEffect(() => {
    const createSession = async () => {
      try {
        const res = await fetch('/api/v1/sessions', { method: 'POST' })
        if (!res.ok) {
          setError(`Failed to create session: ${res.status}`)
          setIsConnected(false)
          return
        }
        const data = await res.json()
        setSessionId(data.session_id)
        setIsConnected(true)
        setError(null)

        fetchExtensions()
      } catch {
        setError('Failed to connect to server')
        setIsConnected(false)
      }
    }

    createSession()
  }, [])

  const fetchExtensions = async () => {
    try {
      const res = await fetch('/api/v1/extensions')
      const data = await res.json()
      setExtensions(data)
      setExtensionError(false)
    } catch {
      setExtensionError(true)
    }
  }

  // ── Interrupt / Stop ──

  const handleStop = useCallback(async () => {
    // Abort the client-side SSE fetch
    abortControllerRef.current?.abort()

    // Send interrupt to backend
    if (sessionId) {
      try {
        await fetch(`/api/v1/sessions/${sessionId}/interrupt`, { method: 'POST' })
      } catch {
        // Best effort
      }
    }

    // Mark any running tool steps as cancelled
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (last && last.role === 'assistant') {
        const steps = (last.toolSteps || []).map(s =>
          s.status === 'running' ? { ...s, status: 'cancelled' as ToolStepStatus, completedAt: Date.now() } : s
        )
        updated[updated.length - 1] = { ...last, toolSteps: steps, interrupted: true }
      }
      return updated
    })

    setIsLoading(false)
  }, [sessionId])

  // Escape key handler (global)
  useEffect(() => {
    const handleGlobalKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && isLoading && !showAutocomplete) {
        handleStop()
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [isLoading, showAutocomplete, handleStop])

  // ── SSE Parser ──

  const parseSSEStream = async (body: ReadableStream<Uint8Array>, signal: AbortSignal) => {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let assistantContent = ''
    const toolCalls: ToolCall[] = []
    const toolSteps: ToolStep[] = []
    let completionMeta: CompletionMeta | null = null

    // Add empty assistant message to accumulate into
    setMessages(prev => [...prev, { role: 'assistant', content: '', toolCalls: [], toolSteps: [] }])

    const updateMessage = () => {
      setMessages(prev => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            content: assistantContent,
            toolCalls: [...toolCalls],
            toolSteps: [...toolSteps],
            completionMeta,
          }
        }
        return updated
      })
    }

    try {
      while (true) {
        if (signal.aborted) break

        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()

          if (data === '[DONE]') continue

          try {
            const parsed = JSON.parse(data)
            const delta = parsed.choices?.[0]?.delta

            if (!delta && !parsed.meta) continue

            // Handle content
            if (delta?.content) {
              assistantContent += delta.content
              updateMessage()
            }

            // Handle tool_calls
            if (delta?.tool_calls) {
              for (const tc of delta.tool_calls) {
                if (tc.function?.name) {
                  const toolCall: ToolCall = {
                    id: tc.id || `tool-${toolCalls.length}`,
                    name: tc.function.name,
                    displayName: formatToolName(tc.function.name),
                  }
                  toolCalls.push(toolCall)

                  // Create a running tool step
                  const toolStep: ToolStep = {
                    id: tc.id || `tool-${toolSteps.length}`,
                    name: tc.function.name,
                    displayName: formatToolName(tc.function.name),
                    arguments: tc.function.arguments || '{}',
                    status: 'running',
                    result: '',
                    isError: false,
                    startedAt: Date.now(),
                    completedAt: null,
                  }
                  toolSteps.push(toolStep)
                  updateMessage()
                }
              }
            }

            // Handle tool_result
            if (delta?.tool_result) {
              const tr = delta.tool_result
              const matchIdx = toolSteps.findIndex(s => s.id === tr.tool_use_id && s.status === 'running')
              if (matchIdx >= 0) {
                toolSteps[matchIdx] = {
                  ...toolSteps[matchIdx],
                  status: tr.is_error ? 'error' : 'completed',
                  result: tr.content || '',
                  isError: tr.is_error || false,
                  completedAt: Date.now(),
                }
                updateMessage()
              }
            }

            // Handle completion metadata
            if (parsed.meta) {
              const m = parsed.meta
              completionMeta = {
                numTurns: m.num_turns || 0,
                totalCostUsd: m.total_cost_usd || 0,
                durationMs: m.duration_ms || 0,
                inputTokens: m.usage?.input_tokens || 0,
                outputTokens: m.usage?.output_tokens || 0,
              }
              updateMessage()
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }

      // Process any remaining buffer content
      if (buffer.trim()) {
        const line = buffer.trim()
        if (line.startsWith('data: ') && line.slice(6).trim() !== '[DONE]') {
          try {
            const parsed = JSON.parse(line.slice(6).trim())
            const delta = parsed.choices?.[0]?.delta
            if (delta?.content) {
              assistantContent += delta.content
              updateMessage()
            }
          } catch {
            // Skip malformed remainder
          }
        }
      }
    } catch (err) {
      // AbortError is expected on cancel, ignore it
      if (err instanceof DOMException && err.name === 'AbortError') return
      // Other stream read error - preserve what we have
    }
  }

  const sendMessage = async () => {
    const trimmed = input.trim()
    if (!trimmed || isLoading || !sessionId) return

    const userMessage: Message = { role: 'user', content: trimmed }
    const allMessages = [...messages, userMessage]
    setMessages(allMessages)
    setInput('')
    setIsLoading(true)
    setError(null)
    setShowAutocomplete(false)

    const abortController = new AbortController()
    abortControllerRef.current = abortController

    try {
      const res = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          stream: true,
          messages: allMessages
            .filter(m => m.role !== 'error')
            .map(m => ({ role: m.role, content: m.content })),
        }),
        signal: abortController.signal,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ error: { message: 'Request failed' } }))
        setError(errData.error?.message || `Error: ${res.status}`)
        setMessages(prev => [...prev, { role: 'error', content: errData.error?.message || 'Request failed' }])
        return
      }

      if (res.body) {
        await parseSSEStream(res.body, abortController.signal)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError('Failed to send message')
      setMessages(prev => [...prev, { role: 'error', content: 'Failed to send message' }])
    } finally {
      setIsLoading(false)
      abortControllerRef.current = null
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Autocomplete keyboard navigation
    if (showAutocomplete) {
      const filtered = getFilteredCommands()
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightedIndex(prev => Math.min(prev + 1, filtered.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightedIndex(prev => Math.max(prev - 1, 0))
        return
      }
      if (e.key === 'Enter' && highlightedIndex >= 0 && filtered[highlightedIndex]) {
        e.preventDefault()
        selectAutocomplete(filtered[highlightedIndex])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setShowAutocomplete(false)
        return
      }
    }

    // Send on Enter (not Shift+Enter)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleInputChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setInput(val)

    if (val.startsWith('/') && !val.includes(' ')) {
      setShowAutocomplete(true)
      setHighlightedIndex(-1)
    } else {
      setShowAutocomplete(false)
    }
  }

  const getFilteredCommands = (): SlashCommand[] => {
    if (!extensions) return []
    const filter = input.slice(1).toLowerCase()
    return extensions.all_slash_commands.filter(cmd =>
      cmd.name.toLowerCase().startsWith(filter)
    )
  }

  const selectAutocomplete = (cmd: SlashCommand) => {
    setInput(`${cmd.invoke_prefix} `)
    setShowAutocomplete(false)
    setHighlightedIndex(-1)
    textareaRef.current?.focus()
  }

  const sessionPreview = sessionId ? sessionId.slice(0, 8) : ''

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1 className="header-title">Claude Chat</h1>
          <div className="connection-status">
            <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
          {sessionPreview && <span className="session-id">{sessionPreview}</span>}
        </div>

        {/* Extension badge */}
        {extensions && extensions.total_count > 0 && (
          <div className="extension-badge-wrapper">
            <button
              className="extension-badge"
              onClick={() => setShowExtDropdown(prev => !prev)}
            >
              {extensions.total_count} extensions
            </button>
            {showExtDropdown && (
              <div className="extension-dropdown">
                {extensions.mcp_servers.length > 0 && (
                  <>
                    <h4>MCP Servers</h4>
                    <ul>
                      {extensions.mcp_servers.map(s => (
                        <li key={s.name}>{s.name}</li>
                      ))}
                    </ul>
                  </>
                )}
                {extensions.skills.length > 0 && (
                  <>
                    <h4>Skills</h4>
                    <ul>
                      {extensions.skills.map(s => (
                        <li key={s.name}>{s.name}</li>
                      ))}
                    </ul>
                  </>
                )}
                {extensions.commands.length > 0 && (
                  <>
                    <h4>Commands</h4>
                    <ul>
                      {extensions.commands.map(c => (
                        <li key={c.name}>{c.name}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}
          </div>
        )}
      </header>

      {/* Error banner */}
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {/* Messages */}
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {/* Tool steps (new CLI-style rendering) */}
            {msg.toolSteps && msg.toolSteps.length > 0 && (
              <ToolStepsContainer steps={msg.toolSteps} />
            )}
            {msg.content}
            {msg.interrupted && (
              <div className="interrupted-bar">
                {'\u26A0'} Response interrupted by user
              </div>
            )}
            {/* Completion meta bar */}
            {msg.role === 'assistant' && msg.completionMeta && (
              <CompletionMetaBar meta={msg.completionMeta} interrupted={msg.interrupted} />
            )}
          </div>
        ))}
        {isLoading && (
          <div className="thinking-indicator">
            <span className="thinking-dots"><span></span><span></span><span></span></span>
            <span>Thinking...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="input-area">
        {/* Autocomplete popup */}
        {showAutocomplete && (
          <ul className="autocomplete-popup" role="listbox">
            {extensionError ? (
              <li className="autocomplete-empty">Could not load extensions</li>
            ) : !extensions || extensions.all_slash_commands.length === 0 ? (
              <li className="autocomplete-empty">No extensions available</li>
            ) : (
              (() => {
                const filtered = getFilteredCommands()
                if (filtered.length === 0) {
                  return <li className="autocomplete-empty">No matching commands</li>
                }
                return filtered.slice(0, 10).map((cmd, idx) => (
                  <li
                    key={cmd.name}
                    role="option"
                    className={idx === highlightedIndex ? 'highlighted' : ''}
                    onClick={() => selectAutocomplete(cmd)}
                  >
                    <span>
                      <span className="cmd-name">{cmd.name}</span>
                      <span className="cmd-desc">{cmd.description || '(no description)'}</span>
                    </span>
                    <span className="cmd-type">{cmd.type}</span>
                  </li>
                ))
              })()
            )}
          </ul>
        )}

        <textarea
          ref={textareaRef}
          role="textbox"
          value={input}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={isLoading ? 'Claude is working... press Esc or click Stop to cancel' : 'Type a message...'}
          disabled={!isConnected || isLoading}
          rows={1}
        />
        {isLoading ? (
          <button className="btn-stop" onClick={handleStop}>
            {'\u25A0'} Stop
          </button>
        ) : (
          <button
            onClick={sendMessage}
            disabled={!isConnected || !input.trim()}
          >
            Send
          </button>
        )}
      </div>
    </div>
  )
}

export default App
