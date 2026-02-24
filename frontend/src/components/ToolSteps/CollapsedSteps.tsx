import { useState } from 'react'
import type { ToolStep } from '../../types/index.ts'
import { ToolStepRow } from './ToolStepRow.tsx'

export function CollapsedSteps({ steps }: { steps: ToolStep[] }) {
  const [expanded, setExpanded] = useState(false)

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
