import type { StateCreator } from 'zustand'
import type { ToolStepStatus, Message } from '../types/index.ts'
import type { StoreState } from './index.ts'
import { parseSSEStream } from '../services/sseParser.ts'

let abortController: AbortController | null = null

export interface ChatSlice {
  messages: Message[]
  input: string
  isLoading: boolean
  setInput: (v: string) => void
  sendMessage: () => Promise<void>
  handleStop: () => Promise<void>
}

export const createChatSlice: StateCreator<StoreState, [], [], ChatSlice> = (set, get) => ({
  messages: [],
  input: '',
  isLoading: false,

  setInput: (v: string) => set({ input: v }),

  sendMessage: async () => {
    const { input, isLoading, messages } = get()
    const sessionId = get().sessionId
    const trimmed = input.trim()
    if (!trimmed || isLoading || !sessionId) return

    const userMessage: Message = { role: 'user', content: trimmed }
    const allMessages = [...messages, userMessage]
    set({ messages: allMessages, input: '', isLoading: true, error: null })

    const controller = new AbortController()
    abortController = controller

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
        signal: controller.signal,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ error: { message: 'Request failed' } }))
        const errMsg = errData.error?.message || `Error: ${res.status}`
        set(state => ({
          error: errMsg,
          messages: [...state.messages, { role: 'error' as const, content: errMsg }],
        }))
        return
      }

      if (res.body) {
        await parseSSEStream(res.body, controller.signal, {
          onMessageInit: () => {
            set(state => ({
              messages: [...state.messages, { role: 'assistant' as const, content: '', toolCalls: [], toolSteps: [] }],
            }))
          },
          onContentUpdate: (content, toolCalls, toolSteps, meta) => {
            set(state => {
              const updated = [...state.messages]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = { ...last, content, toolCalls, toolSteps, completionMeta: meta }
              }
              return { messages: updated }
            })
          },
          onToolCall: () => {},
          onToolResult: () => {},
          onMeta: () => {},
        })
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      set(state => ({
        error: 'Failed to send message',
        messages: [...state.messages, { role: 'error' as const, content: 'Failed to send message' }],
      }))
    } finally {
      set({ isLoading: false })
      abortController = null
    }
  },

  handleStop: async () => {
    abortController?.abort()

    const sessionId = get().sessionId
    if (sessionId) {
      try {
        await fetch(`/api/v1/sessions/${sessionId}/interrupt`, { method: 'POST' })
      } catch {
        // Best effort
      }
    }

    set(state => {
      const updated = [...state.messages]
      const last = updated[updated.length - 1]
      if (last && last.role === 'assistant') {
        const steps = (last.toolSteps || []).map(s =>
          s.status === 'running' ? { ...s, status: 'cancelled' as ToolStepStatus, completedAt: Date.now() } : s
        )
        updated[updated.length - 1] = { ...last, toolSteps: steps, interrupted: true }
      }
      return { messages: updated, isLoading: false }
    })
  },
})
