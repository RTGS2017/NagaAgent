import { useStorage } from '@vueuse/core'
import { ref } from 'vue'
import API from '@/api/core'

export interface Message {
  role: 'system' | 'user' | 'assistant'
  content: string
  reasoning?: string
  generating?: boolean
  sender?: string
}

export const CURRENT_SESSION_ID = useStorage<string | null>('naga-session', null)
export const MESSAGES = ref<Message[]>([])

export async function loadCurrentSession() {
  if (CURRENT_SESSION_ID.value) {
    try {
      const detail = await API.getSessionDetail(CURRENT_SESSION_ID.value)
      MESSAGES.value = detail.messages.map(m => ({
        role: m.role as Message['role'],
        content: m.content,
      }))
      return
    } catch {
      CURRENT_SESSION_ID.value = null
    }
  }
  // No session — load persistent context history
  try {
    const ctx = await API.loadContext()
    if (ctx.messages?.length) {
      MESSAGES.value = ctx.messages.map((m: any) => ({
        role: m.role as Message['role'],
        content: m.content,
      }))
    }
  } catch {
    // Backend unavailable, start empty
    MESSAGES.value = []
  }
}

export function newSession() {
  CURRENT_SESSION_ID.value = null
  MESSAGES.value = []
}

export async function switchSession(id: string) {
  CURRENT_SESSION_ID.value = id
  await loadCurrentSession()
}
