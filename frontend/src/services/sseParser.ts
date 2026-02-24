import type { ToolCall, ToolStep, CompletionMeta } from '../types/index.ts'
import { formatToolName } from '../utils/formatters.ts'

export interface SSECallbacks {
  onMessageInit: () => void
  onContentUpdate: (content: string, toolCalls: ToolCall[], toolSteps: ToolStep[], meta: CompletionMeta | null) => void
  onToolCall: (toolCall: ToolCall, toolStep: ToolStep) => void
  onToolResult: (toolSteps: ToolStep[]) => void
  onMeta: (meta: CompletionMeta) => void
}

export async function parseSSEStream(
  body: ReadableStream<Uint8Array>,
  signal: AbortSignal,
  callbacks: SSECallbacks,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let assistantContent = ''
  const toolCalls: ToolCall[] = []
  const toolSteps: ToolStep[] = []
  let completionMeta: CompletionMeta | null = null

  callbacks.onMessageInit()

  const update = () => {
    callbacks.onContentUpdate(assistantContent, [...toolCalls], [...toolSteps], completionMeta)
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

          if (delta?.content) {
            assistantContent += delta.content
            update()
          }

          if (delta?.tool_calls) {
            for (const tc of delta.tool_calls) {
              if (tc.function?.name) {
                const toolCall: ToolCall = {
                  id: tc.id || `tool-${toolCalls.length}`,
                  name: tc.function.name,
                  displayName: formatToolName(tc.function.name),
                }
                toolCalls.push(toolCall)

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
                update()
              }
            }
          }

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
              update()
            }
          }

          if (parsed.meta) {
            const m = parsed.meta
            completionMeta = {
              numTurns: m.num_turns || 0,
              totalCostUsd: m.total_cost_usd || 0,
              durationMs: m.duration_ms || 0,
              inputTokens: m.usage?.input_tokens || 0,
              outputTokens: m.usage?.output_tokens || 0,
            }
            update()
          }
        } catch {
          // Skip malformed JSON lines
        }
      }
    }

    if (buffer.trim()) {
      const line = buffer.trim()
      if (line.startsWith('data: ') && line.slice(6).trim() !== '[DONE]') {
        try {
          const parsed = JSON.parse(line.slice(6).trim())
          const delta = parsed.choices?.[0]?.delta
          if (delta?.content) {
            assistantContent += delta.content
            update()
          }
        } catch {
          // Skip malformed remainder
        }
      }
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') return
    // Other stream read error - preserve what we have
  }
}
