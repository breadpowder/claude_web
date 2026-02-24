import { useState, useEffect } from 'react'
import type { ToolStep } from '../../types/index.ts'
import { formatTiming, formatArgs } from '../../utils/formatters.ts'
import './ToolSteps.css'

export function ToolStepRow({ step, defaultExpanded }: { step: ToolStep; defaultExpanded: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded || step.isError)

  // Sync expanded state when defaultExpanded changes (e.g. step transitions from running to completed)
  useEffect(() => {
    if (defaultExpanded) setExpanded(true)
  }, [defaultExpanded])
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
