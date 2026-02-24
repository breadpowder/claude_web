import type { ExtensionData } from '../types/index.ts'

export async function createSessionApi(): Promise<{ session_id: string }> {
  const res = await fetch('/api/v1/sessions', { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.status}`)
  }
  return res.json()
}

export async function fetchExtensionsApi(): Promise<ExtensionData> {
  const res = await fetch('/api/v1/extensions')
  return res.json()
}

export async function sendInterrupt(sessionId: string): Promise<void> {
  await fetch(`/api/v1/sessions/${sessionId}/interrupt`, { method: 'POST' })
}
