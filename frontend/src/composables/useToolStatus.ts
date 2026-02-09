import { ref } from 'vue'
import API from '@/api/core'
import { MESSAGES } from '@/composables/useSession'

export const toolMessage = ref('')
export const openclawTasks = ref<Array<Record<string, any>>>([])
let timer: ReturnType<typeof setInterval> | null = null

async function poll() {
  try {
    const [status, clawdbot, tasks] = await Promise.allSettled([
      API.getToolStatus(),
      API.getClawdbotReplies(),
      API.getOpenclawTasks(),
    ])

    if (status.status === 'fulfilled') {
      toolMessage.value = status.value.visible ? status.value.message : ''
    }

    if (clawdbot.status === 'fulfilled' && clawdbot.value.replies?.length) {
      for (const reply of clawdbot.value.replies) {
        MESSAGES.value.push({
          role: 'assistant',
          content: reply,
          sender: 'OpenClaw',
        })
      }
    }

    if (tasks.status === 'fulfilled' && tasks.value.tasks) {
      openclawTasks.value = tasks.value.tasks
      const active = tasks.value.tasks.filter((t: any) => t.status === 'running' || t.status === 'pending')
      if (active.length > 0 && !toolMessage.value) {
        toolMessage.value = `OpenClaw: ${active.length} 个任务执行中...`
      }
    }
  } catch {
    // ignore polling errors
  }
}

export function startToolPolling() {
  if (timer) return
  poll()
  timer = setInterval(poll, 2000)
}

export function stopToolPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  toolMessage.value = ''
}
