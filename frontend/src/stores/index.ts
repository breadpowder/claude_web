import { create } from 'zustand'
import { createSessionSlice, type SessionSlice } from './sessionStore.ts'
import { createExtensionSlice, type ExtensionSlice } from './extensionStore.ts'
import { createChatSlice, type ChatSlice } from './chatStore.ts'

export type StoreState = SessionSlice & ExtensionSlice & ChatSlice

export const useStore = create<StoreState>()((...a) => ({
  ...createSessionSlice(...a),
  ...createExtensionSlice(...a),
  ...createChatSlice(...a),
}))
