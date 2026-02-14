import { useState, useEffect, useRef, type KeyboardEvent, type ChangeEvent } from 'react'
import './App.css'

interface Message {
  role: 'user' | 'assistant' | 'error'
  content: string
  toolCalls?: ToolCall[]
}

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

function formatToolName(name: string): string {
  // Parse mcp__server__tool format into "server > tool"
  const match = name.match(/^mcp__([^_]+)__(.+)$/)
  if (match) {
    return `${match[1]} > ${match[2]}`
  }
  return name
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Extension state (TASK-010a)
  const [extensions, setExtensions] = useState<ExtensionData | null>(null)
  const [extensionError, setExtensionError] = useState(false)
  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [showExtDropdown, setShowExtDropdown] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // Create session on mount
  useEffect(() => {
    const createSession = async () => {
      try {
        const res = await fetch('/api/v1/sessions', { method: 'POST' })
        const data = await res.json()
        setSessionId(data.session_id)
        setIsConnected(true)
        setError(null)

        // Fetch extensions after session creation
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

  const parseSSEStream = async (body: ReadableStream<Uint8Array>) => {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let assistantContent = ''
    const toolCalls: ToolCall[] = []

    // Add empty assistant message to accumulate into
    setMessages(prev => [...prev, { role: 'assistant', content: '', toolCalls: [] }])

    try {
      while (true) {
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

            if (!delta) continue

            // Handle content
            if (delta.content) {
              assistantContent += delta.content
              setMessages(prev => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last && last.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: assistantContent, toolCalls: [...toolCalls] }
                }
                return updated
              })
            }

            // Handle tool_calls (TASK-010a)
            if (delta.tool_calls) {
              for (const tc of delta.tool_calls) {
                if (tc.function?.name) {
                  const toolCall: ToolCall = {
                    id: tc.id || `tool-${toolCalls.length}`,
                    name: tc.function.name,
                    displayName: formatToolName(tc.function.name),
                  }
                  toolCalls.push(toolCall)
                  setMessages(prev => {
                    const updated = [...prev]
                    const last = updated[updated.length - 1]
                    if (last && last.role === 'assistant') {
                      updated[updated.length - 1] = { ...last, content: assistantContent, toolCalls: [...toolCalls] }
                    }
                    return updated
                  })
                }
              }
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    } catch {
      // Stream read error - preserve what we have
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
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ error: { message: 'Request failed' } }))
        setError(errData.error?.message || `Error: ${res.status}`)
        setMessages(prev => [...prev, { role: 'error', content: errData.error?.message || 'Request failed' }])
        return
      }

      if (res.body) {
        await parseSSEStream(res.body)
      }
    } catch {
      setError('Failed to send message')
      setMessages(prev => [...prev, { role: 'error', content: 'Failed to send message' }])
    } finally {
      setIsLoading(false)
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

    // Check for slash command autocomplete trigger
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

        {/* Extension badge (TASK-010a) */}
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
            {/* Tool indicators (TASK-010a) */}
            {msg.toolCalls && msg.toolCalls.length > 0 && (
              <div>
                {msg.toolCalls.map((tc) => (
                  <div key={tc.id} className="tool-indicator">
                    {tc.displayName}
                  </div>
                ))}
              </div>
            )}
            {msg.content}
          </div>
        ))}
        {isLoading && <div className="thinking">Thinking...</div>}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="input-area">
        {/* Autocomplete popup (TASK-010a) */}
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
          placeholder="Type a message..."
          disabled={!isConnected || isLoading}
          rows={1}
        />
        <button
          onClick={sendMessage}
          disabled={!isConnected || isLoading || !input.trim()}
        >
          {isLoading ? '...' : 'Send'}
        </button>
      </div>
    </div>
  )
}

export default App
