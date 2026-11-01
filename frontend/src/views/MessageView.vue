<script lang="ts">
import type { ChatTab, Message } from '@/utils/session'
import { useEventListener } from '@vueuse/core'
import Dialog from 'primevue/dialog'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'
import { ACCESS_TOKEN, authExpired } from '@/api'
import API from '@/api/core'
import AgentContacts from '@/components/AgentContacts.vue'
import BoxContainer from '@/components/BoxContainer.vue'
import Markdown from '@/components/Markdown.vue'
import MessageItem from '@/components/MessageItem.vue'
import { toolMessage } from '@/composables/useToolStatus'
import { useTravel } from '@/travel/composables/useTravel'
import { CONFIG } from '@/utils/config'
import { live2dState } from '@/utils/live2dController'
import { activeTabId, agentContacts, CURRENT_SESSION_ID, formatRelativeTime, getActiveTab, IS_TEMPORARY_SESSION, isAgentLoading, loadAgentMessages, loadCurrentSession, MESSAGES, newSession, switchSession, tabs } from '@/utils/session'
import { isPlaying, queueSpeak, stop as stopTTS } from '@/utils/tts'
import { TtsSentenceBuffer } from '@/utils/ttsText'
import { setMessageViewExpanded } from '@/utils/uiState'

const isSending = ref(false)
const messageQueue: Array<{ content: string, options?: any }> = []
const ttsEnabled = computed(() => CONFIG.value.system.voice_enabled)

function appendTtsText(buffer: TtsSentenceBuffer, text: string): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }
  for (const sentence of buffer.append(text))
    queueSpeak(sentence)
}

function replaceTtsText(buffer: TtsSentenceBuffer, text: string): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }

  // 原始流可能已经包含文本式工具调用，先停止再使用服务端清理后的正文重建队列。
  stopTTS()
  buffer.replace(text)
}

function flushTtsText(buffer: TtsSentenceBuffer): void {
  if (!ttsEnabled.value) {
    buffer.clear()
    return
  }
  const remainder = buffer.flush()
  if (remainder)
    queueSpeak(remainder)
}

function toolEventName(item: Record<string, any>): string {
  const service = item.service_name || item.agentType || '工具'
  return item.tool_name ? `${service}: ${item.tool_name}` : service
}

async function processQueue() {
  if (messageQueue.length === 0 || isSending.value)
    return

  const { content, options } = messageQueue.shift()!
  await chatStreamInternal(content, options)
}

export function chatStream(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  // 用户发送新消息时，立即中止上一次的 TTS 播放
  stopTTS()

  // 立即显示用户消息
  MESSAGES.value.push({ role: 'user', content: options?.images?.length ? `[截图x${options.images.length}] ${content}` : content })

  // 将消息加入队列
  messageQueue.push({ content, options })
  processQueue()
}

async function chatStreamInternal(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  isSending.value = true

  // 预先推入 assistant 消息（立即显示，不等 API 响应）
  MESSAGES.value.push({
    role: 'assistant',
    content: '',
    reasoning: '',
    generating: true,
    status: options?.voiceInput ? '理解话语中' : undefined,
    toolEvents: [],
  })
  const message = MESSAGES.value[MESSAGES.value.length - 1]!
  // 开启语音时在流式输出中逐句送入 TTS 队列，文本始终实时显示。
  const ttsBuffer = new TtsSentenceBuffer()
  let contentBuf = ''
  const pushContent = (text: string) => {
    contentBuf += text
    message.content = contentBuf
  }

  live2dState.value = 'thinking'
  let compressTimer: ReturnType<typeof setTimeout> | undefined
  // 记录当前轮次 content 流的起始位置，content_clean 只替换当前轮的 LLM 输出
  let roundContentStart = 0

  API.chatStream(content, {
    sessionId: CURRENT_SESSION_ID.value ?? undefined,
    disableTTS: true,
    skill: options?.skill,
    images: options?.images,
    temporary: IS_TEMPORARY_SESSION.value || undefined,
  }).then(async ({ sessionId, response }) => {
    if (sessionId) {
      CURRENT_SESSION_ID.value = sessionId
    }

    for await (const chunk of response) {
      if (chunk.type === 'reasoning') {
        message.reasoning = (message.reasoning || '') + chunk.text
      }
      else if (chunk.type === 'content') {
        pushContent(chunk.text || '')
        appendTtsText(ttsBuffer, chunk.text || '')
      }
      else if (chunk.type === 'content_clean') {
        // 仅替换当前轮次的 LLM 输出（从 roundContentStart 开始），保留之前轮次的工具通知
        contentBuf = contentBuf.substring(0, roundContentStart) + (chunk.text || '')
        message.content = contentBuf
        replaceTtsText(ttsBuffer, chunk.text || '')
      }
      else if (chunk.type === 'tool_calls') {
        // 工具执行可能耗时，先朗读清理后的引导语。
        flushTtsText(ttsBuffer)
        // 显示工具调用状态
        const calls = chunk.calls || []
        const callDesc = calls.map((c: any) => toolEventName(c)).join(', ')
        message.status = callDesc ? `正在执行工具: ${callDesc}` : '正在执行工具'
        message.toolEvents = message.toolEvents || []
        for (const call of calls) {
          message.toolEvents.push({
            type: 'tool_call',
            name: toolEventName(call),
            args: call,
          })
        }
        // OpenClaw 工具可能耗时较长，添加提示
        const hasOpenclaw = calls.some((c: any) => {
          const name = (c.service_name || c.agentType || '').toLowerCase()
          return name.includes('openclaw') || name.includes('agent')
        })
        if (hasOpenclaw) {
          pushContent('> ⏳ OpenClaw 工具处理可能会比较久，预计需要两分钟\n')
        }
      }
      else if (chunk.type === 'tool_results') {
        message.toolEvents = message.toolEvents || []
        for (const result of chunk.results || []) {
          message.toolEvents.push({
            type: 'tool_result',
            name: toolEventName(result),
            isError: result.status !== 'success',
            result: result.result,
          })
        }
        // 工具结果追加完毕，更新下一轮 content 的起始位置
        roundContentStart = contentBuf.length
      }
      else if (chunk.type === 'round_start' && (chunk.round ?? 0) > 1) {
        // 多轮分隔
        pushContent('\n---\n\n')
        // 新一轮开始，更新 content 起始位置
        roundContentStart = contentBuf.length
      }
      else if (chunk.type === 'round_end') {
        flushTtsText(ttsBuffer)
      }
      else if (chunk.type === 'token_refreshed') {
        // 后端刷新了 token，同步到前端（防止后续轮询请求用旧 token 覆盖）
        if (chunk.text) {
          ACCESS_TOKEN.value = chunk.text
        }
      }
      else if (chunk.type === 'auth_expired') {
        // 后端 LLM 认证失败且刷新也失败，触发重新登录
        authExpired.value = true
        pushContent(chunk.text || '登录已过期，请重新登录')
      }
      else if (chunk.type === 'status') {
        message.status = chunk.text || ''
      }
      else if (chunk.type === 'intent_result') {
        const tools = (chunk as any).tools || []
        if (tools.length > 0) {
          message.status = `调度: ${tools.join(', ')}`
        }
      }
      else if (chunk.type === 'pre_search_start') {
        message.status = `搜索: ${chunk.text || ''}`
      }
      else if (chunk.type === 'pre_search_end') {
        message.status = chunk.text || '搜索完成'
      }
      else if (chunk.type === 'compress_start' || chunk.type === 'compress_progress' || chunk.type === 'compress_end') {
        // 上下文压缩进度提示（覆盖式显示，直接写 message.content 不走缓冲）
        message.content = `> ${chunk.text}\n\n`
        if (chunk.type === 'compress_end') {
          compressTimer = setTimeout(() => {
            message.content = ''
          }, 1200)
        }
      }
      else if (chunk.type === 'compress_info') {
        // 运行时压缩完成，在当前 assistant 消息前插入 info 标记
        if (compressTimer) {
          clearTimeout(compressTimer)
          compressTimer = undefined
        }
        message.content = ''
        const idx = MESSAGES.value.indexOf(message)
        if (idx > 0) {
          MESSAGES.value.splice(idx, 0, { role: 'info', content: chunk.text || '【已压缩上下文】' })
        }
      }
      window.dispatchEvent(new CustomEvent('token', { detail: chunk.text || '' }))
    }

    // 清理生成状态（文本已实时显示，无需等待 TTS）
    delete message.generating
    delete message.status
    if (!message.reasoning)
      delete message.reasoning

    flushTtsText(ttsBuffer)
    if (!isPlaying.value) {
      live2dState.value = 'idle'
    }
  }).catch((err) => {
    live2dState.value = 'idle'
    message.content = `Error: ${err.message}`
    delete message.generating
    delete message.status
    if (message.reasoning === '')
      delete message.reasoning
  }).finally(() => {
    isSending.value = false
    processQueue()
  })
}
</script>

<script setup lang="ts">
const input = defineModel<string>()
const normalContainerRef = useTemplateRef('normalContainerRef')
const expandedContainerRef = useTemplateRef('expandedContainerRef')
const composerRef = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const inputDockRef = ref<HTMLElement | null>(null)
const isExpanded = ref(false)
const expandedStyle = ref<Record<string, string>>({})
const expandedInputStyle = ref<Record<string, string>>({})
const expandedAnchorLeft = ref(8)

function isImeComposing(event: KeyboardEvent) {
  return event.isComposing || (event as any).keyCode === 229
}

function resizeComposer() {
  if (!composerRef.value) {
    return
  }
  composerRef.value.style.height = '0px'
  const nextHeight = Math.min(Math.max(composerRef.value.scrollHeight, 44), 160)
  composerRef.value.style.height = `${nextHeight}px`
}

function toggleExpanded() {
  if (!isExpanded.value) {
    const chatRect = (normalContainerRef.value as any)?.$el?.getBoundingClientRect?.()
    if (chatRect) {
      expandedAnchorLeft.value = Math.max(8, chatRect.left)
    }
  }
  isExpanded.value = !isExpanded.value
  nextTick(() => {
    resizeComposer()
    if (isExpanded.value) {
      updateExpandedLayout()
      nextTick().then(scrollToBottom)
    }
  })
}

function handleComposerEnter(event: KeyboardEvent) {
  if (isImeComposing(event) || event.shiftKey) {
    return
  }
  event.preventDefault()
  sendMessage()
}

function updateExpandedLayout() {
  if (!inputDockRef.value) {
    return
  }
  const chatRect = (normalContainerRef.value as any)?.$el?.getBoundingClientRect?.()
  const inputRect = inputDockRef.value.getBoundingClientRect()
  const left = isExpanded.value
    ? expandedAnchorLeft.value
    : Math.max(8, chatRect?.left ?? expandedAnchorLeft.value)
  const composerHeight = Math.max(56, Math.ceil(inputRect.height))
  expandedStyle.value = {
    left: `${left}px`,
    top: '8px',
    right: '8px',
    bottom: `${composerHeight + 16}px`,
  }
  expandedInputStyle.value = {
    left: `${left}px`,
    right: '8px',
    bottom: '8px',
  }
}

function toggleTTS() {
  CONFIG.value.system.voice_enabled = !CONFIG.value.system.voice_enabled
  if (!CONFIG.value.system.voice_enabled) {
    stopTTS() // 关闭时停止当前播放
  }
}

// TTS 播放状态驱动嘴部动画：开始播放→talking，结束→idle
watch(isPlaying, (playing) => {
  live2dState.value = playing ? 'talking' : 'idle'
})

watch(input, () => {
  nextTick(() => {
    resizeComposer()
    if (isExpanded.value) {
      updateExpandedLayout()
    }
  })
})

watch(isExpanded, (value) => {
  setMessageViewExpanded(value)
})

function scrollToBottom() {
  normalContainerRef.value?.scrollToBottom()
  expandedContainerRef.value?.scrollToBottom()
}

// ── Tab 管理 ──
const renamingTabId = ref<string | null>(null)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

/** 当前活跃 tab 的 messages（用于模板渲染） */
const activeMessages = computed(() => getActiveTab().messages)
const { getActiveTravelForAgent, getLatestTravelForAgent } = useTravel()
const activeAgentTravel = computed(() => {
  const tab = getActiveTab()
  return tab.type === 'agent' ? getActiveTravelForAgent(tab.instanceId) : null
})
const latestAgentTravel = computed(() => {
  const tab = getActiveTab()
  return tab.type === 'agent' ? getLatestTravelForAgent(tab.instanceId) : null
})
const completedAgentTravel = computed(() => {
  const travel = latestAgentTravel.value
  if (!travel || activeAgentTravel.value)
    return null
  return travel.status === 'completed' ? travel : null
})
const sendingTravelInstruction = ref(false)
const rawTravelHistoryVisible = ref(false)
const rawTravelHistoryLoading = ref(false)
const rawTravelHistoryMessages = ref<Array<Record<string, any>>>([])
const rawTravelHistoryError = ref('')
const loadingCompletedTravelReport = ref(false)
const completedTravelReport = ref<{
  sessionId: string
  exists: boolean
  path: string | null
  title?: string | null
  content: string | null
  missingReason?: 'not_generated' | 'missing'
} | null>(null)
const activeAgentTravelMeta = computed(() => {
  const travel = activeAgentTravel.value
  if (!travel)
    return ''
  const remainingMinutes = Math.max(0, Math.round(travel.timeLimitMinutes - travel.elapsedMinutes))
  const remainingCredits = Math.max(0, travel.creditLimit - travel.creditsUsed)
  return `${travel.discoveries.length} 个发现 · ${travel.uniqueSources || 0} 个来源 · 剩余 ${remainingMinutes} 分钟 / ${remainingCredits} 积分`
})

watch(completedAgentTravel, async (travel) => {
  if (!travel) {
    completedTravelReport.value = null
    return
  }
  loadingCompletedTravelReport.value = true
  try {
    const report = await API.getTravelSessionReport(travel.sessionId)
    completedTravelReport.value = {
      sessionId: travel.sessionId,
      exists: report.exists,
      path: report.path,
      title: report.title,
      content: report.content,
      missingReason: report.missingReason,
    }
  }
  catch {
    completedTravelReport.value = {
      sessionId: travel.sessionId,
      exists: false,
      path: travel.summaryReportPath || null,
      title: travel.summaryReportTitle || null,
      content: null,
      missingReason: 'missing',
    }
  }
  finally {
    loadingCompletedTravelReport.value = false
  }
}, { immediate: true })

async function openRawTravelHistory() {
  const travel = activeAgentTravel.value || completedAgentTravel.value
  if (!travel?.sessionId || rawTravelHistoryLoading.value)
    return
  rawTravelHistoryLoading.value = true
  rawTravelHistoryVisible.value = true
  rawTravelHistoryError.value = ''
  try {
    const history = await API.getTravelSessionHistory(travel.sessionId, 0, true)
    rawTravelHistoryMessages.value = history.messages || []
  }
  catch (e: any) {
    rawTravelHistoryMessages.value = []
    rawTravelHistoryError.value = e?.response?.data?.detail || e?.message || '读取原始探索记录失败'
  }
  finally {
    rawTravelHistoryLoading.value = false
  }
}

function stringifyRawHistoryValue(value: unknown) {
  if (value == null)
    return ''
  if (typeof value === 'string')
    return value
  try {
    return JSON.stringify(value, null, 2)
  }
  catch {
    return String(value)
  }
}

function rawHistoryEntryMessage(entry: Record<string, any>) {
  return entry?.message && typeof entry.message === 'object'
    ? entry.message as Record<string, any>
    : null
}

function extractRawHistoryPreview(content: unknown) {
  if (typeof content === 'string')
    return content.trim()
  if (!Array.isArray(content))
    return ''
  const parts = content.flatMap((item) => {
    if (!item || typeof item !== 'object')
      return []
    if (item.type === 'text' && typeof item.text === 'string')
      return [item.text.trim()]
    if (item.type === 'toolCall')
      return [`[tool call] ${String(item.name || 'unknown')}`]
    return []
  }).filter(Boolean)
  return parts.join(' ').trim()
}

function rawHistoryEntryTimestamp(entry: Record<string, any>) {
  const raw = entry?.timestamp
  if (typeof raw === 'number')
    return new Date(raw).toTimeString().slice(0, 8)
  const text = String(raw || '')
  if (text.includes('T'))
    return text.slice(11, 19)
  return text || '--:--:--'
}

function parsePossibleJson(text: string) {
  const trimmed = text.trim()
  const firstChar = trimmed.charAt(0)
  if (!trimmed || !['{', '['].includes(firstChar))
    return null
  try {
    return JSON.parse(trimmed)
  }
  catch {
    return null
  }
}

function truncateHistoryText(text: string, maxChars = 2400) {
  const normalized = text.trim()
  if (!normalized)
    return '无内容'
  if (normalized.length <= maxChars)
    return normalized
  return `${normalized.slice(0, maxChars)}\n\n...已截断 ${normalized.length - maxChars} 个字符`
}

function formatTravelToolResult(toolName: string, text: string) {
  const parsed = parsePossibleJson(text)
  if (toolName === 'travel_state' && parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const state = parsed as Record<string, any>
    return [
      `状态: ${state.status || '-'}`,
      `阶段: ${state.phase || '-'}`,
      `发现: ${Array.isArray(state.discoveries) ? state.discoveries.length : 0} 条`,
      `来源: ${state.uniqueSources ?? (Array.isArray(state.sources) ? state.sources.length : 0)} 个`,
      `积分: ${state.creditsUsed ?? 0} / ${state.creditLimit ?? 0}`,
      `时间: ${state.elapsedMinutes ?? 0} / ${state.timeLimitMinutes ?? 0} 分钟`,
    ].join('\n')
  }
  if (toolName === 'travel_summary' && parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const result = parsed as Record<string, any>
    return [
      `标题: ${result.title || '-'}`,
      `文件: ${result.file_path || result.path || '-'}`,
      `大小: ${result.bytes ?? '-'} bytes`,
    ].join('\n')
  }
  return truncateHistoryText(text)
}

const rawTravelHistoryTimeline = computed(() => {
  const items: Array<{
    id: string
    kind: 'assistant' | 'tool_call' | 'tool_result'
    title: string
    time: string
    text: string
  }> = []

  rawTravelHistoryMessages.value.forEach((entry, index) => {
    const message = rawHistoryEntryMessage(entry)
    if (!message)
      return

    const role = String(message.role || '').trim()
    const time = rawHistoryEntryTimestamp(entry)

    if (role === 'assistant') {
      const content = Array.isArray(message.content) ? message.content : []
      let textBuffer: string[] = []
      const flushAssistantText = () => {
        const text = textBuffer.join('\n\n').trim()
        textBuffer = []
        if (!text)
          return
        items.push({
          id: `${index}-assistant-${items.length}`,
          kind: 'assistant',
          title: 'AI 回复',
          time,
          text,
        })
      }

      for (const part of content) {
        if (!part || typeof part !== 'object')
          continue
        if (part.type === 'text' && typeof part.text === 'string' && part.text.trim()) {
          textBuffer.push(part.text.trim())
          continue
        }
        if (part.type === 'toolCall') {
          flushAssistantText()
          items.push({
            id: `${index}-toolcall-${String(part.id || items.length)}`,
            kind: 'tool_call',
            title: `调度工具 · ${String(part.name || 'unknown')}`,
            time,
            text: stringifyRawHistoryValue(part.arguments || {}),
          })
        }
      }

      if (!content.length && typeof message.content === 'string' && message.content.trim())
        textBuffer.push(message.content.trim())

      flushAssistantText()
      return
    }

    if (role === 'toolResult' || role === 'tool_result') {
      const toolName = String(message.toolName || 'tool')
      const text = extractRawHistoryPreview(message.content)
      items.push({
        id: `${index}-toolresult-${toolName}`,
        kind: 'tool_result',
        title: `工具结果 · ${toolName}`,
        time,
        text: formatTravelToolResult(toolName, text),
      })
    }
  })

  return items
})

/** 当前活跃 tab 是否正在加载干员历史 */
const agentLoadingActive = computed(() => {
  const tab = getActiveTab()
  return tab.type === 'agent' && tab.instanceId ? isAgentLoading(tab.instanceId) : false
})

/** 关闭 tab（不杀进程，只从 tabs 移除） */
function closeTab(tab: ChatTab) {
  const idx = tabs.value.findIndex(t => t.id === tab.id)
  if (idx > 0) {
    tabs.value.splice(idx, 1)
  }
  if (activeTabId.value === tab.id) {
    activeTabId.value = 'naga'
  }
}

function startRename(tab: ChatTab) {
  if (tab.type !== 'agent' || !tab.instanceId)
    return
  renamingTabId.value = tab.id
  renameValue.value = tab.name
  nextTick(() => renameInputRef.value?.focus())
}

function finishRename(tab: ChatTab) {
  if (tab.type !== 'agent' || !tab.instanceId) {
    renamingTabId.value = null
    return
  }
  const newName = renameValue.value.trim()
  if (newName && newName !== tab.name) {
    const oldName = tab.name
    tab.name = newName
    // 同步消息中的 sender
    for (const msg of tab.messages) {
      if (msg.sender === oldName)
        msg.sender = newName
    }
    // 同步到后端 + 通讯录
    API.renameAgent(tab.instanceId, newName).then(() => {
      const contact = agentContacts.value.find(a => a.id === tab.instanceId)
      if (contact)
        contact.name = newName
    }).catch(() => {})
  }
  renamingTabId.value = null
}

// 切换 tab 时清除未读 + 懒加载历史
watch(activeTabId, async (id) => {
  const tab = tabs.value.find(t => t.id === id)
  if (tab) {
    tab.unread = 0
    // 切换到干员 tab 时强制触发一次后端历史/唤醒，避免只命中本地缓存导致进程未拉起
    if (tab.type === 'agent' && tab.instanceId && !isAgentLoading(tab.instanceId)) {
      await loadAgentMessages(tab, { forceRefresh: true })
      nextTick().then(scrollToBottom)
    }
  }
})

// ── 发送分发 ──
function sendMessage() {
  const tab = getActiveTab()
  if (!input.value?.trim())
    return

  if (tab.type === 'agent') {
    sendToAgent(tab, input.value.trim())
    input.value = ''
    return
  }
  // 娜迦 tab → 原有 chatStream
  chatStream(input.value)
  nextTick().then(scrollToBottom)
  input.value = ''
}

async function sendTravelInstruction() {
  const travel = activeAgentTravel.value
  const message = input.value?.trim()
  if (!travel || !message || sendingTravelInstruction.value)
    return
  sendingTravelInstruction.value = true
  try {
    await API.sendTravelInstruction(travel.sessionId, message)
    pushSystemMessage(`已追加到探索任务：${message}`)
    input.value = ''
  }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '追加探索指令失败'
    pushSystemMessage(`追加探索指令失败：${detail}`)
  }
  finally {
    sendingTravelInstruction.value = false
  }
}

function saveAgentTabMessages(tab: ChatTab) {
  if (!tab.instanceId)
    return
  const storageKey = `agent_history_${tab.instanceId}`
  localStorage.setItem(storageKey, JSON.stringify(tab.messages))
}

function pushSystemMessage(content: string): Message {
  const message: Message = { role: 'system', content }
  const tab = getActiveTab()
  if (tab.type === 'agent') {
    tab.messages.push(message)
    saveAgentTabMessages(tab)
  }
  else {
    MESSAGES.value.push(message)
  }
  nextTick().then(scrollToBottom)
  return message
}

function dispatchToActiveTab(content: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  const tab = getActiveTab()
  if (tab.type === 'agent') {
    void sendToAgent(tab, content, options)
    return
  }
  chatStream(content, options)
  nextTick().then(scrollToBottom)
}

async function sendToAgent(tab: ChatTab, msg: string, options?: { skill?: string, images?: string[], voiceInput?: boolean }) {
  stopTTS()

  if (!tab.instanceId) {
    tab.messages.push({ role: 'system', content: '干员实例未就绪，请稍后再试' })
    return
  }
  if (tab.engine === 'naga-core') {
    tab.messages.push({ role: 'user', content: msg })
    nextTick().then(scrollToBottom)

    tab.messages.push({
      role: 'assistant',
      content: '',
      reasoning: '',
      generating: true,
      status: options?.voiceInput ? '理解话语中' : '思考中',
      sender: tab.name,
      toolEvents: [],
    })
    const assistantMsg = tab.messages[tab.messages.length - 1]!
    let contentBuf = ''
    let roundContentStart = 0
    const ttsBuffer = new TtsSentenceBuffer()

    try {
      const { sessionId, response } = await API.chatStream(msg, {
        sessionId: tab.sessionId,
        agentId: tab.instanceId,
        disableTTS: true,
        skill: options?.skill,
        images: options?.images,
        temporary: false,
      })

      if (sessionId) {
        tab.sessionId = sessionId
        localStorage.setItem(`agent_session_${tab.instanceId}`, sessionId)
      }

      for await (const chunk of response) {
        if (chunk.type === 'reasoning') {
          assistantMsg.reasoning = (assistantMsg.reasoning || '') + (chunk.text || '')
        }
        else if (chunk.type === 'content') {
          contentBuf += chunk.text || ''
          assistantMsg.content = contentBuf
          appendTtsText(ttsBuffer, chunk.text || '')
        }
        else if (chunk.type === 'content_clean') {
          contentBuf = contentBuf.substring(0, roundContentStart) + (chunk.text || '')
          assistantMsg.content = contentBuf
          replaceTtsText(ttsBuffer, chunk.text || '')
        }
        else if (chunk.type === 'round_start' && (chunk.round ?? 0) > 1) {
          contentBuf += '\n---\n\n'
          assistantMsg.content = contentBuf
          roundContentStart = contentBuf.length
        }
        else if (chunk.type === 'tool_calls') {
          flushTtsText(ttsBuffer)
          const calls = chunk.calls || []
          assistantMsg.status = calls.length > 0
            ? `调度工具: ${calls.map(c => toolEventName(c)).join(', ')}`
            : '调度工具中'
          assistantMsg.toolEvents = assistantMsg.toolEvents || []
          for (const call of calls) {
            assistantMsg.toolEvents.push({
              type: 'tool_call',
              name: toolEventName(call),
              args: call,
            })
          }
        }
        else if (chunk.type === 'tool_results') {
          assistantMsg.toolEvents = assistantMsg.toolEvents || []
          for (const result of chunk.results || []) {
            assistantMsg.toolEvents.push({
              type: 'tool_result',
              name: toolEventName(result),
              isError: result.status !== 'success',
              result: result.result,
            })
          }
          roundContentStart = contentBuf.length
        }
        else if (chunk.type === 'status') {
          assistantMsg.status = chunk.text || ''
        }
        else if (chunk.type === 'round_end') {
          flushTtsText(ttsBuffer)
        }
        else if (chunk.type === 'compress_info') {
          const idx = tab.messages.indexOf(assistantMsg)
          if (idx > 0) {
            tab.messages.splice(idx, 0, { role: 'info', content: chunk.text || '【已压缩上下文】' })
          }
        }
        else if (chunk.type === 'auth_expired') {
          assistantMsg.content = chunk.text || '登录已过期，请重新登录'
        }
        nextTick().then(scrollToBottom)
      }
      flushTtsText(ttsBuffer)
    }
    catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || e
      assistantMsg.content = `发送失败: ${detail}`
    }

    delete assistantMsg.generating
    delete assistantMsg.status
    if (!assistantMsg.reasoning) {
      delete assistantMsg.reasoning
    }
    saveAgentTabMessages(tab)
    if (activeTabId.value !== tab.id) {
      tab.unread++
    }
    nextTick().then(scrollToBottom)
    return
  }

  tab.messages.push({ role: 'user', content: msg })
  nextTick().then(scrollToBottom)

  tab.messages.push({ role: 'assistant', content: '', generating: true, status: '思考中', sender: tab.name, toolEvents: [] })
  const assistantMsg = tab.messages[tab.messages.length - 1]!
  const ttsBuffer = new TtsSentenceBuffer()
  let receivedContent = false

  try {
    // 流式接收回复（使用新 API，内部自动 ensure_running）
    for await (const chunk of API.streamToAgent(tab.instanceId, msg)) {
      if (chunk.type === 'status') {
        assistantMsg.status = chunk.text
      }
      else if (chunk.type === 'content') {
        receivedContent = true
        assistantMsg.content += chunk.text
        appendTtsText(ttsBuffer, chunk.text)
      }
      else if (chunk.type === 'done') {
        assistantMsg.content = chunk.text // 用完整文本覆盖，防止拼接偏差
        if (!receivedContent)
          ttsBuffer.replace(chunk.text)
        flushTtsText(ttsBuffer)
      }
      else if (chunk.type === 'error') {
        assistantMsg.content = `错误: ${chunk.text}`
      }
      else if (chunk.type === 'tool_call') {
        assistantMsg.status = `🔧 ${chunk.name || '工具调用中'}...`
        assistantMsg.toolEvents = assistantMsg.toolEvents || []
        assistantMsg.toolEvents.push({
          type: 'tool_call',
          name: chunk.name || '工具',
          toolCallId: chunk.toolCallId,
          args: chunk.args,
        })
      }
      else if (chunk.type === 'tool_result') {
        assistantMsg.status = `${chunk.isError ? '❌' : '✅'} ${chunk.name || '工具'} ${chunk.isError ? '失败' : '完成'}`
        assistantMsg.toolEvents = assistantMsg.toolEvents || []
        assistantMsg.toolEvents.push({
          type: 'tool_result',
          name: chunk.name || '工具',
          toolCallId: chunk.toolCallId,
          isError: chunk.isError,
          result: chunk.result ?? chunk.text,
        })
      }
      nextTick().then(scrollToBottom)
    }
    flushTtsText(ttsBuffer)
  }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e.message || e
    assistantMsg.content = `发送失败: ${detail}`
  }

  delete assistantMsg.generating
  delete assistantMsg.status

  // 保存干员对话历史到 localStorage
  saveAgentTabMessages(tab)

  // 非活跃 tab → 未读+1
  if (activeTabId.value !== tab.id) {
    tab.unread++
  }

  nextTick().then(scrollToBottom)
}

onMounted(async () => {
  loadCurrentSession()
  scrollToBottom()
  nextTick(resizeComposer)
})

onBeforeUnmount(() => {
  setMessageViewExpanded(false)
})

useEventListener('token', scrollToBottom)
useEventListener(window, 'resize', () => {
  if (isExpanded.value) {
    updateExpandedLayout()
  }
})

// Session history
const showHistory = ref(false)
const sessions = ref<Array<{
  sessionId: string
  createdAt: string
  lastActiveAt: string
  conversationRounds: number
  temporary: boolean
}>>([])
const loadingSessions = ref(false)

async function fetchSessions() {
  loadingSessions.value = true
  try {
    const res = await API.getSessions()
    sessions.value = res.sessions ?? []
  }
  catch {
    sessions.value = []
  }
  loadingSessions.value = false
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) {
    fetchSessions()
  }
}

async function handleSwitchSession(id: string) {
  await switchSession(id)
  showHistory.value = false
  nextTick().then(scrollToBottom)
}

async function handleDeleteSession(id: string) {
  try {
    await API.deleteSession(id)
    sessions.value = sessions.value.filter(s => s.sessionId !== id)
    if (CURRENT_SESSION_ID.value === id) {
      newSession()
    }
  }
  catch { /* ignore */ }
}

function handleNewSession() {
  newSession()
  showHistory.value = false
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file)
    return

  const ext = file.name.split('.').pop()?.toLowerCase()
  const parseable = ['docx', 'xlsx', 'txt', 'csv', 'md']

  if (ext && parseable.includes(ext)) {
    // 解析文档内容后发送给文本模型
    const msg = pushSystemMessage(`正在解析文件: ${file.name}...`)
    try {
      const result = await API.parseDocument(file)
      const truncNote = result.truncated ? '（内容过长，已截断）' : ''
      msg.content = `文件解析完成: ${file.name}${truncNote}`
      dispatchToActiveTab(`以下是文件「${file.name}」的内容：\n\n${result.content}\n\n请分析这个文件的内容。`)
    }
    catch (err: any) {
      msg.content = `文件解析失败: ${err?.response?.data?.detail || err.message}`
    }
  }
  else {
    // 其他格式走原有上传逻辑
    const msg = pushSystemMessage(`正在上传文件: ${file.name}...`)
    try {
      const result = await API.uploadDocument(file)
      msg.content = `文件上传成功: ${file.name}`
      if (result.filePath) {
        dispatchToActiveTab(`请分析我刚上传的文件「${file.name}」，文件完整路径: ${result.filePath}`)
      }
    }
    catch (err: any) {
      msg.content = `文件上传失败: ${err.message}`
    }
  }
  target.value = ''
}

// ── 语音输入（MediaRecorder + ASR API） ──
const isRecording = ref(false)
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []

async function toggleVoiceInput() {
  if (!CONFIG.value.voice_realtime.enabled)
    return

  if (isRecording.value) {
    stopVoiceInput()
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMimeType() })

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0)
        audioChunks.push(e.data)
    }

    mediaRecorder.onstop = async () => {
      // 停止所有音轨，释放麦克风
      stream.getTracks().forEach(t => t.stop())
      if (audioChunks.length === 0)
        return

      const audioBlob = new Blob(audioChunks, { type: mediaRecorder?.mimeType || 'audio/webm' })
      try {
        const { text } = await API.transcribeAudio(audioBlob, { language: 'zh' })
        if (text && typeof text === 'string' && text.trim()) {
          // 语音识别成功：直接发送（带语音标注前缀）
          dispatchToActiveTab(`以下是用户的语音输入：【${text.trim()}】`, { voiceInput: true })
        }
      }
      catch (err: any) {
        const status = err?.response?.status
        if (status === 401) {
          pushSystemMessage('语音识别需要登录后使用')
        }
        else if (status === 402) {
          pushSystemMessage('余额不足，无法使用语音识别')
        }
        else {
          pushSystemMessage(`语音识别失败: ${err.message || err}`)
        }
      }
    }

    mediaRecorder.start()
    isRecording.value = true
  }
  catch (err: any) {
    if (err.name === 'NotAllowedError') {
      pushSystemMessage('麦克风权限被拒绝，请在系统设置中允许麦克风访问')
    }
    else {
      pushSystemMessage(`无法启动录音: ${err.message || err}`)
    }
  }
}

function stopVoiceInput() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  mediaRecorder = null
  isRecording.value = false
}

function getSupportedMimeType(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t))
      return t
  }
  return ''
}
</script>

<template>
  <div class="flex flex-col gap-8 relative">
    <div class="flex min-h-0 grow">
      <!-- 左侧通讯录抽屉 -->
      <AgentContacts />

      <!-- 主内容区 -->
      <BoxContainer v-show="!isExpanded" ref="normalContainerRef" class="w-full grow" hide-back>
        <!-- Tab Bar：header slot -->
        <template #header>
          <div class="message-header px-1 pt-3 pb-2">
            <div class="tab-row">
              <button
                v-for="tab in tabs" :key="tab.id"
                class="tab-btn" :class="{ active: tab.id === activeTabId }"
                @click="activeTabId = tab.id"
                @dblclick="startRename(tab)"
              >
                <input
                  v-if="renamingTabId === tab.id"
                  ref="renameInputRef"
                  v-model="renameValue"
                  class="tab-rename-input"
                  @blur="finishRename(tab)"
                  @keydown.enter="finishRename(tab)"
                  @click.stop
                >
                <template v-else>
                  {{ tab.name }}
                  <span v-if="tab.type === 'agent'" class="tab-close" @click.stop="closeTab(tab)">×</span>
                </template>
                <span v-if="tab.unread && tab.id !== activeTabId" class="badge">{{ tab.unread }}</span>
              </button>
            </div>
            <div class="window-actions">
              <button
                v-if="!isExpanded"
                class="window-btn"
                title="放大对话窗口"
                @click="toggleExpanded"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M15 3h6v6" />
                  <path d="M9 21H3v-6" />
                  <path d="M21 3l-7 7" />
                  <path d="M3 21l7-7" />
                </svg>
              </button>
            </div>
          </div>
        </template>

        <!-- 干员加载中：转圈圈 -->
        <div v-if="agentLoadingActive" class="agent-loading-overlay">
          <div class="agent-loading-spinner" />
          <div class="agent-loading-text">干员加载中</div>
        </div>

        <!-- 消息列表（当前活跃 tab） -->
        <div v-else class="grid gap-4 pb-8">
          <div v-if="activeAgentTravel" class="travel-status-banner">
            <div class="travel-status-title">
              <span class="travel-status-spinner" />
              探索中
            </div>
            <div class="travel-status-summary">
              {{ activeAgentTravel.goalPrompt || '正在执行后台探索任务' }}
            </div>
            <div class="travel-status-meta">
              {{ activeAgentTravelMeta }}
            </div>
            <button class="travel-action-btn" @click="openRawTravelHistory">
              查看原始探索记录
            </button>
          </div>
          <div v-else-if="completedAgentTravel" class="travel-report-banner">
            <div class="travel-report-title">探索完成成果</div>
            <div class="travel-report-meta">
              {{ completedAgentTravel.goalPrompt || '最近一次探索已完成' }}
            </div>
            <div v-if="loadingCompletedTravelReport" class="travel-report-content">
              正在读取探索成果文件...
            </div>
            <template v-else-if="completedTravelReport?.exists">
              <div class="travel-report-file">
                {{ completedTravelReport.title || '探索成果文件' }}
                <span v-if="completedTravelReport.path"> · {{ completedTravelReport.path.split('/').pop() }}</span>
              </div>
              <div class="travel-report-content travel-report-markdown">
                <Markdown :source="completedTravelReport.content || ''" />
              </div>
            </template>
            <div v-else class="travel-report-content travel-report-missing">
              {{ completedTravelReport?.missingReason === 'missing' ? '找不到探索成果文件。' : '尚未生成探索成果文件。' }}
            </div>
            <button class="travel-action-btn" @click="openRawTravelHistory">
              查看原始探索记录
            </button>
          </div>
          <MessageItem
            v-for="item, index in activeMessages" :key="index"
            :role="item.role" :content="item.content"
            :reasoning="item.reasoning" :sender="item.sender"
            :generating="item.generating" :status="item.status"
            :tool-events="item.toolEvents"
            :class="(item.generating && index === activeMessages.length - 1) || 'border-b'"
          />
        </div>
      </BoxContainer>

      <Teleport to="body">
        <div v-if="isExpanded" class="expanded-chat-overlay" :style="expandedStyle">
          <BoxContainer
            ref="expandedContainerRef"
            class="message-shell size-full"
            box-class="w-full h-full"
            :parallax="false"
            hide-back
          >
            <!-- Tab Bar：header slot -->
            <template #header>
              <div class="message-header px-1 pt-3 pb-2">
                <div class="tab-row">
                  <button
                    v-for="tab in tabs" :key="tab.id"
                    class="tab-btn" :class="{ active: tab.id === activeTabId }"
                    @click="activeTabId = tab.id"
                    @dblclick="startRename(tab)"
                  >
                    <input
                      v-if="renamingTabId === tab.id"
                      ref="renameInputRef"
                      v-model="renameValue"
                      class="tab-rename-input"
                      @blur="finishRename(tab)"
                      @keydown.enter="finishRename(tab)"
                      @click.stop
                    >
                    <template v-else>
                      {{ tab.name }}
                      <span v-if="tab.type === 'agent'" class="tab-close" @click.stop="closeTab(tab)">×</span>
                    </template>
                    <span v-if="tab.unread && tab.id !== activeTabId" class="badge">{{ tab.unread }}</span>
                  </button>
                </div>
                <div class="window-actions">
                  <button
                    class="window-btn"
                    title="缩小对话窗口"
                    @click="toggleExpanded"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M14 10 21 3" />
                      <path d="M21 10V3h-7" />
                      <path d="M3 14l7 7" />
                      <path d="M3 21h7v-7" />
                    </svg>
                  </button>
                </div>
              </div>
            </template>

            <div v-if="agentLoadingActive" class="agent-loading-overlay">
              <div class="agent-loading-spinner" />
              <div class="agent-loading-text">干员加载中</div>
            </div>

            <div v-else class="grid gap-4 pb-8">
              <div v-if="activeAgentTravel" class="travel-status-banner">
                <div class="travel-status-title">
                  <span class="travel-status-spinner" />
                  探索中
                </div>
                <div class="travel-status-summary">
                  {{ activeAgentTravel.goalPrompt || '正在执行后台探索任务' }}
                </div>
                <div class="travel-status-meta">
                  {{ activeAgentTravelMeta }}
                </div>
                <button class="travel-action-btn" @click="openRawTravelHistory">
                  查看原始探索记录
                </button>
              </div>
              <div v-else-if="completedAgentTravel" class="travel-report-banner">
                <div class="travel-report-title">探索完成成果</div>
                <div class="travel-report-meta">
                  {{ completedAgentTravel.goalPrompt || '最近一次探索已完成' }}
                </div>
                <div v-if="loadingCompletedTravelReport" class="travel-report-content">
                  正在读取探索成果文件...
                </div>
                <template v-else-if="completedTravelReport?.exists">
                  <div class="travel-report-file">
                    {{ completedTravelReport.title || '探索成果文件' }}
                    <span v-if="completedTravelReport.path"> · {{ completedTravelReport.path.split('/').pop() }}</span>
                  </div>
                  <div class="travel-report-content travel-report-markdown">
                    <Markdown :source="completedTravelReport.content || ''" />
                  </div>
                </template>
                <div v-else class="travel-report-content travel-report-missing">
                  {{ completedTravelReport?.missingReason === 'missing' ? '找不到探索成果文件。' : '尚未生成探索成果文件。' }}
                </div>
                <button class="travel-action-btn" @click="openRawTravelHistory">
                  查看原始探索记录
                </button>
              </div>
              <MessageItem
                v-for="item, index in activeMessages" :key="`expanded-${index}`"
                :role="item.role" :content="item.content"
                :reasoning="item.reasoning" :sender="item.sender"
                :generating="item.generating" :status="item.status"
                :tool-events="item.toolEvents"
                :class="(item.generating && index === activeMessages.length - 1) || 'border-b'"
              />
            </div>
          </BoxContainer>
        </div>
      </Teleport>
    </div>

    <!-- Session History Panel（仅在娜迦 tab 可见） -->
    <Transition name="slide-up">
      <div v-if="showHistory && activeTabId === 'naga' && !isExpanded" class="session-panel">
        <div class="flex items-center justify-between px-3 py-2 border-b border-white/10">
          <span class="text-white/70 text-sm font-bold">对话历史</span>
          <button
            class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
            @click="showHistory = false"
          >
            关闭
          </button>
        </div>
        <div class="overflow-y-auto max-h-48">
          <div v-if="loadingSessions" class="text-white/40 text-xs text-center py-4">
            加载中...
          </div>
          <div v-else-if="sessions.length === 0" class="text-white/40 text-xs text-center py-4">
            暂无历史对话
          </div>
          <div
            v-for="s in sessions" :key="s.sessionId"
            class="session-item"
            :class="{ 'bg-white/10': s.sessionId === CURRENT_SESSION_ID }"
            @click="handleSwitchSession(s.sessionId)"
          >
            <div class="flex-1 min-w-0">
              <div class="text-white/80 text-sm truncate">
                {{ s.sessionId.slice(0, 8) }}...
              </div>
              <div class="text-white/40 text-xs">
                {{ formatRelativeTime(s.lastActiveAt) }} · {{ s.conversationRounds }} 轮对话
              </div>
            </div>
            <button
              class="text-white/30 hover:text-red-400 bg-transparent border-none cursor-pointer text-xs shrink-0 ml-2"
              title="删除"
              @click.stop="handleDeleteSession(s.sessionId)"
            >
              x
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <div v-if="toolMessage && !isExpanded" class="mx-[var(--nav-back-width)] text-white/50 text-xs px-2 py-1">
      {{ toolMessage }}
    </div>
    <div
      ref="inputDockRef"
      :class="isExpanded ? 'expanded-input-dock' : 'mx-[var(--nav-back-width)]'"
      :style="isExpanded ? expandedInputStyle : undefined"
    >
      <div class="box flex items-center gap-2 min-w-0">
        <button
          v-if="activeTabId === 'naga'"
          class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
          title="新建对话"
          @click="handleNewSession"
        >
          +
        </button>
        <button
          v-if="activeTabId === 'naga'"
          class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
          :class="{ 'text-white!': showHistory }"
          title="对话历史"
          @click="toggleHistory"
        >
          H
        </button>
        <span class="input-prefix shrink-0">&gt;</span>
        <textarea
          ref="composerRef"
          v-model="input"
          rows="1"
          class="composer-textarea flex-1 min-w-0 text-white bg-transparent border-none outline-none"
          :placeholder="activeTabId === 'naga' ? 'Type a message...' : `发送给 ${getActiveTab().name}...`"
          @keydown.enter.exact="handleComposerEnter"
          @input="resizeComposer"
        />
        <button
          v-if="CONFIG.voice_realtime.enabled"
          class="input-icon-btn shrink-0"
          :class="{ recording: isRecording }"
          :title="isRecording ? '停止录音' : '语音输入'"
          @click="toggleVoiceInput"
        >
          <svg v-if="!isRecording" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" x2="12" y1="19" y2="22" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
        </button>
        <button
          class="input-icon-btn shrink-0"
          :title="ttsEnabled ? '关闭语音播报' : '开启语音播报'"
          @click="toggleTTS"
        >
          <svg v-if="ttsEnabled" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.54 8.46a5 5 0 0 1 0 7.07" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><line x1="22" y1="9" x2="16" y2="15" /><line x1="16" y1="9" x2="22" y2="15" /></svg>
        </button>
        <button
          class="input-icon-btn shrink-0"
          title="上传文件 (Word/Excel/文本)"
          @click="triggerUpload"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M12 18v-6" /><path d="m9 15 3-3 3 3" /></svg>
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".docx,.xlsx,.txt,.csv,.md,.pdf,.png,.jpg,.jpeg"
          class="hidden"
          @change="handleFileUpload"
        >
        <button
          v-if="activeAgentTravel"
          class="input-icon-btn shrink-0"
          :disabled="!input?.trim() || sendingTravelInstruction"
          :title="sendingTravelInstruction ? '投喂中' : '将当前输入追加为探索指令'"
          @click="sendTravelInstruction"
        >
          <span class="text-[11px] font-semibold">
            {{ sendingTravelInstruction ? '...' : '探' }}
          </span>
        </button>
        <button
          class="send-btn shrink-0"
          :disabled="!input?.trim()"
          title="发送消息"
          @click="sendMessage"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 2 11 13" />
            <path d="m22 2-7 20-4-9-9-4Z" />
          </svg>
        </button>
      </div>
    </div>

    <Dialog
      v-model:visible="rawTravelHistoryVisible"
      modal
      header="原始探索记录"
      :style="{ width: 'min(860px, 94vw)' }"
      :content-style="{ height: '82vh', overflow: 'hidden' }"
    >
      <div class="raw-history-panel">
        <div v-if="rawTravelHistoryLoading" class="travel-report-content">
          正在读取原始探索记录...
        </div>
        <div v-else-if="rawTravelHistoryError" class="travel-report-content travel-report-missing">
          {{ rawTravelHistoryError }}
        </div>
        <div v-else-if="!rawTravelHistoryMessages.length" class="travel-report-content travel-report-missing">
          暂无原始探索记录。
        </div>
        <div v-else class="raw-history-list">
          <div class="raw-history-toolbar">
            共 {{ rawTravelHistoryTimeline.length }} 条调度记录
          </div>
          <div v-if="!rawTravelHistoryTimeline.length" class="travel-report-content travel-report-missing">
            暂无可展示的 AI 回复或工具调度记录。
          </div>
          <div
            v-for="item in rawTravelHistoryTimeline"
            v-else
            :key="item.id"
            class="history-timeline-item"
            :class="item.kind"
          >
            <div class="history-timeline-head">
              <span class="history-timeline-title">{{ item.title }}</span>
              <span class="history-timeline-time">{{ item.time }}</span>
            </div>
            <pre class="history-timeline-body">{{ item.text }}</pre>
          </div>
        </div>
      </div>
    </Dialog>
  </div>
</template>

<style scoped>
.expanded-chat-overlay {
  position: fixed;
  z-index: 80;
}

.expanded-input-dock {
  position: fixed;
  z-index: 81;
}

.expanded-chat-overlay :deep(.box) {
  width: 100%;
  height: 100%;
}

.composer-textarea {
  min-height: 44px;
  max-height: 160px;
  padding: 10px 0;
  line-height: 24px;
  resize: none;
  overflow-y: auto;
}

.composer-textarea::placeholder {
  color: rgba(255, 255, 255, 0.45);
}

.input-prefix {
  color: rgba(255, 255, 255, 0.42);
  font-size: 1rem;
  line-height: 1;
  padding-left: 0.15rem;
}

.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 999px;
  background: rgba(212, 175, 55, 0.22);
  color: rgba(255, 255, 255, 0.92);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
}

.send-btn:hover:not(:disabled) {
  background: rgba(212, 175, 55, 0.34);
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tab-row {
  display: flex;
  gap: 0.25rem;
  flex: 1;
  min-width: 0;
}

.window-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
}

.window-btn {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  transition: all 0.2s ease;
}

.window-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.95);
  border-color: rgba(255, 255, 255, 0.22);
}

/* ── Tab 栏（与 ConfigView 完全一致） ── */
.tab-btn {
  flex: 1;
  position: relative;
  padding: 0.5rem 0;
  font-size: 0.875rem;
  font-weight: 600;
  text-align: center;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
}

.tab-btn.active {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.9);
}

.tab-close {
  font-size: 0.7rem;
  opacity: 0;
  margin-left: 2px;
  transition: opacity 0.15s;
}

.tab-btn:hover .tab-close {
  opacity: 0.6;
}

.tab-close:hover {
  opacity: 1 !important;
  color: #e74c3c;
}

.tab-rename-input {
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.4);
  color: white;
  outline: none;
  width: 60px;
  font-size: inherit;
  font-weight: inherit;
  text-align: center;
}

.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #e74c3c;
  color: white;
  font-size: 10px;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* ── 以下为原有样式 ── */.session-panel {
  position: absolute;
  left: var(--nav-back-width);
  right: 0;
  bottom: 5rem;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  backdrop-filter: blur(12px);
  z-index: 10;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.input-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.input-icon-btn:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.08);
}

.input-icon-btn.recording {
  color: #e85d5d;
  animation: recording-pulse 1.2s ease-in-out infinite;
}

@keyframes recording-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.agent-loading-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 100%;
  min-height: 200px;
}

.agent-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(255, 255, 255, 0.15);
  border-top-color: rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: agent-spin 0.8s linear infinite;
}

.agent-loading-text {
  color: rgba(255, 255, 255, 0.5);
  font-size: 14px;
}

.travel-status-banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: min(760px, 100%);
  max-width: 100%;
  align-self: flex-start;
  padding: 10px 12px;
  border: 1px solid rgba(66, 185, 131, 0.22);
  border-radius: 12px;
  background: rgba(66, 185, 131, 0.08);
}

.travel-status-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgba(224, 255, 238, 0.92);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.travel-status-spinner {
  width: 10px;
  height: 10px;
  border: 2px solid rgba(224, 255, 238, 0.26);
  border-top-color: rgba(224, 255, 238, 0.92);
  border-radius: 50%;
  animation: travel-spin 0.9s linear infinite;
}

.travel-status-summary {
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-status-meta {
  color: rgba(224, 255, 238, 0.55);
  font-size: 11px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-action-btn {
  align-self: flex-start;
  padding: 4px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.66);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.travel-action-btn:hover {
  border-color: rgba(96, 165, 250, 0.28);
  background: rgba(96, 165, 250, 0.1);
  color: rgba(226, 238, 255, 0.92);
}

.travel-report-banner {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: min(760px, 100%);
  max-width: 100%;
  align-self: flex-start;
  padding: 10px 12px;
  border: 1px solid rgba(96, 165, 250, 0.22);
  border-radius: 12px;
  background: rgba(96, 165, 250, 0.08);
}

.travel-report-title {
  color: rgba(226, 238, 255, 0.92);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.travel-report-meta {
  color: rgba(226, 238, 255, 0.56);
  font-size: 11px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-file {
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
  font-weight: 600;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-content {
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.travel-report-markdown {
  white-space: normal;
}

.travel-report-markdown :deep(h1),
.travel-report-markdown :deep(h2),
.travel-report-markdown :deep(h3),
.travel-report-markdown :deep(h4) {
  color: rgba(255, 255, 255, 0.9);
  margin: 0.9em 0 0.45em;
}

.travel-report-markdown :deep(p),
.travel-report-markdown :deep(li) {
  color: rgba(255, 255, 255, 0.74);
  line-height: 1.7;
}

.travel-report-markdown :deep(strong) {
  color: rgba(255, 255, 255, 0.9);
}

.travel-report-missing {
  color: rgba(248, 113, 113, 0.9);
}

.raw-history-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.raw-history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: auto;
  padding-right: 4px;
}

.raw-history-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  position: sticky;
  top: 0;
  z-index: 1;
  padding-bottom: 2px;
  background: rgba(20, 20, 20, 0.92);
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  font-weight: 600;
}

.history-timeline-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
}

.history-timeline-item.assistant {
  border-color: rgba(96, 165, 250, 0.18);
  background: rgba(96, 165, 250, 0.06);
}

.history-timeline-item.tool_call {
  border-color: rgba(251, 191, 36, 0.18);
  background: rgba(251, 191, 36, 0.06);
}

.history-timeline-item.tool_result {
  border-color: rgba(74, 222, 128, 0.18);
  background: rgba(74, 222, 128, 0.06);
}

.history-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-timeline-title {
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
  font-weight: 700;
}

.history-timeline-time {
  color: rgba(255, 255, 255, 0.46);
  font-size: 11px;
  flex: 0 0 auto;
}

.history-timeline-body {
  margin: 0;
  min-height: 120px;
  max-height: 360px;
  overflow: auto;
  padding: 12px;
  color: #f5f5f5;
  background: #101214;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  box-sizing: border-box;
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

@keyframes agent-spin {
  to { transform: rotate(360deg); }
}

@keyframes travel-spin {
  to { transform: rotate(360deg); }
}
</style>
