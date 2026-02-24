import type { CompletionMeta } from '../../types/index.ts'
import { formatTokens } from '../../utils/formatters.ts'
import './CompletionMetaBar.css'

export function CompletionMetaBar({ meta, interrupted }: { meta: CompletionMeta; interrupted?: boolean }) {
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
