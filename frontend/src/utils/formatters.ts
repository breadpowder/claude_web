import type { ToolStep } from '../types/index.ts'

export function formatToolName(name: string): string {
  const match = name.match(/^mcp__(.+?)__(.+)$/)
  if (match) {
    return `${match[1]} > ${match[2]}`
  }
  return name
}

export function formatArgs(argsJson: string): string {
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

export function formatTiming(step: ToolStep): string {
  if (step.status === 'running') return ''
  if (step.status === 'cancelled') return '\u2013'
  if (!step.completedAt) return ''
  const ms = step.completedAt - step.startedAt
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

export function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}
