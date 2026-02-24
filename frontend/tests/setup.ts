import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { useStore } from '../src/stores/index.ts'

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {}

afterEach(() => {
  cleanup()
  // Reset Zustand store to initial state between tests
  useStore.setState({
    sessionId: null,
    isConnected: false,
    error: null,
    messages: [],
    input: '',
    isLoading: false,
    extensions: null,
    extensionError: false,
  })
})
