import type { StateCreator } from 'zustand'
import type { ExtensionData } from '../types/index.ts'
import type { StoreState } from './index.ts'

export interface ExtensionSlice {
  extensions: ExtensionData | null
  extensionError: boolean
  fetchExtensions: () => Promise<void>
}

export const createExtensionSlice: StateCreator<StoreState, [], [], ExtensionSlice> = (set) => ({
  extensions: null,
  extensionError: false,

  fetchExtensions: async () => {
    try {
      const res = await fetch('/api/v1/extensions')
      const data = await res.json()
      set({ extensions: data, extensionError: false })
    } catch {
      set({ extensionError: true })
    }
  },
})
