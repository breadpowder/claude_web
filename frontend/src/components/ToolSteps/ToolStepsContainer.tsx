import type { ToolStep } from '../../types/index.ts'
import { ToolStepRow } from './ToolStepRow.tsx'
import { CollapsedSteps } from './CollapsedSteps.tsx'

export function ToolStepsContainer({ steps }: { steps: ToolStep[] }) {
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
        {recentSteps.map(s => <ToolStepRow key={s.id} step={s} defaultExpanded={false} />)}
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
