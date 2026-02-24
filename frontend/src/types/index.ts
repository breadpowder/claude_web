export type ToolStepStatus = 'running' | 'completed' | 'error' | 'cancelled'

export interface ToolStep {
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

export interface CompletionMeta {
  numTurns: number
  totalCostUsd: number
  durationMs: number
  inputTokens: number
  outputTokens: number
}

export interface Message {
  role: 'user' | 'assistant' | 'error'
  content: string
  toolCalls?: ToolCall[]
  toolSteps?: ToolStep[]
  completionMeta?: CompletionMeta | null
  interrupted?: boolean
}

export interface ToolCall {
  id: string
  name: string
  displayName: string
}

export interface SlashCommand {
  name: string
  description: string
  type: string
  invoke_prefix: string
}

export interface ExtensionData {
  mcp_servers: Array<{ name: string; status: string; tool_count: number | null }>
  skills: Array<{ name: string; description: string; type: string; invoke_prefix: string }>
  commands: Array<{ name: string; description: string; type: string; invoke_prefix: string }>
  all_slash_commands: SlashCommand[]
  total_count: number
}
