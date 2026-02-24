import { useEffect, useRef } from 'react'
import { useStore } from '../../stores/index.ts'
import { ToolStepsContainer } from '../ToolSteps/ToolStepsContainer.tsx'
import { CompletionMetaBar } from '../CompletionMeta/CompletionMetaBar.tsx'
import './MessageList.css'

export function MessageList() {
  const messages = useStore(s => s.messages)
  const isLoading = useStore(s => s.isLoading)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  return (
    <div className="messages">
      {messages.map((msg, i) => (
        <div key={i} className={`message ${msg.role}`}>
          {msg.toolSteps && msg.toolSteps.length > 0 && (
            <ToolStepsContainer steps={msg.toolSteps} />
          )}
          {msg.content}
          {msg.interrupted && (
            <div className="interrupted-bar">
              {'\u26A0'} Response interrupted by user
            </div>
          )}
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
  )
}
