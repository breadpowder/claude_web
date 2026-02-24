import { useState, useEffect, useRef, type KeyboardEvent, type ChangeEvent } from 'react'
import type { SlashCommand } from '../../types/index.ts'
import { useStore } from '../../stores/index.ts'
import './ChatInput.css'

export function ChatInput() {
  const input = useStore(s => s.input)
  const setInput = useStore(s => s.setInput)
  const isLoading = useStore(s => s.isLoading)
  const isConnected = useStore(s => s.isConnected)
  const extensions = useStore(s => s.extensions)
  const extensionError = useStore(s => s.extensionError)
  const sendMessage = useStore(s => s.sendMessage)
  const handleStop = useStore(s => s.handleStop)

  const [showAutocomplete, setShowAutocomplete] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Global Escape key handler for interrupt
  useEffect(() => {
    const handleGlobalKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && isLoading && !showAutocomplete) {
        handleStop()
      }
    }
    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [isLoading, showAutocomplete, handleStop])

  const handleSend = () => {
    setShowAutocomplete(false)
    sendMessage()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
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

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
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

  return (
    <div className="input-area">
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
          onClick={handleSend}
          disabled={!isConnected || !input.trim()}
        >
          Send
        </button>
      )}
    </div>
  )
}
