import type { StateCreator } from 'zustand'
import type { StoreState } from './index.ts'

export interface SessionSlice {
  sessionId: string | null
  isConnected: boolean
  error: string | null
  createSession: () => Promise<void>
}

export const createSessionSlice: StateCreator<StoreState, [], [], SessionSlice> = (set, get) => ({
  sessionId: null,
  isConnected: false,
  error: null,

  createSession: async () => {
    try {
      const res = await fetch('/api/v1/sessions', { method: 'POST' })
      if (!res.ok) {
        set({ error: `Failed to create session: ${res.status}`, isConnected: false })
        return
      }
      const data = await res.json()
      set({ sessionId: data.session_id, isConnected: true, error: null })

      get().fetchExtensions()
    } catch {
      set({ error: 'Failed to connect to server', isConnected: false })
    }
  },
})
