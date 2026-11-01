import type { AgentEngine } from '@/api/core'
import type { StreamChunk } from '@/utils/encoding'
import { useStorage } from '@vueuse/core'
import { ref } from 'vue'
import API from '@/api/core'

export const proactiveNotifier = ref<null | ((source: string, content: string) => void)>(null)

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'info'
  content: string
  reasoning?: string
  generating?: boolean
  status?: string
  sender?: string
  toolEvents?: ToolEvent[]
}

export interface ToolEvent {
  type: 'tool_call' | 'tool_result'
  name?: string
  toolCallId?: string
  args?: any
  result?: any
  isError?: boolean
}

// ── Tab 状态管理 ──

export interface ChatTab {
  id: string // 'naga' 或 uuid
  type: 'naga' | 'agent'
  name: string // '娜迦' | '干员1' | 自定义名
  instanceId?: string // 后端实例 ID（仅 agent tab）
  sessionId?: string
  engine?: AgentEngine
  characterTemplate?: string
  messages: Message[]
  unread: number
}

/** 所有 tab，第一个固定为娜迦 */
export const tabs = ref<ChatTab[]>([
  { id: 'naga', type: 'naga', name: '娜迦', messages: [], unread: 0 },
])

/** 当前活跃 tab（持久化到 localStorage） */
export const activeTabId = useStorage('naga-active-tab', 'naga')

// ── 娜迦 tab 的 MESSAGES 保持兼容 ──

export const CURRENT_SESSION_ID = useStorage<string | null>('naga-session', null)
export const MESSAGES = ref<Message[]>([])
export const IS_TEMPORARY_SESSION = ref(false)

// 娜迦 tab 的 messages 与 MESSAGES.value 保持同一引用
tabs.value[0]!.messages = MESSAGES.value

/** 干员编号计数器（只增不减，不复用编号，避免混淆） */
let agentCounter = 0
export function nextAgentNumber(): number {
  return ++agentCounter
}

export function getActiveTab(): ChatTab {
  return tabs.value.find(t => t.id === activeTabId.value) || tabs.value[0]!
}

export function getNagaTab(): ChatTab {
  return tabs.value[0]!
}

export function appendNagaMessage(message: Message) {
  MESSAGES.value.push(message)
  syncNagaMessages()
}

export async function reloadCurrentSessionMessages() {
  if (!CURRENT_SESSION_ID.value)
    return
  const detail = await API.getSessionDetail(CURRENT_SESSION_ID.value)
  MESSAGES.value = normalizeMessages(detail.messages)
  syncNagaMessages()
}

function normalizeToolEvent(input: any): ToolEvent | null {
  if (!input || typeof input !== 'object')
    return null
  const type = input.type === 'tool_result' ? 'tool_result' : input.type === 'tool_call' ? 'tool_call' : null
  if (!type)
    return null
  return {
    type,
    name: typeof input.name === 'string' ? input.name : undefined,
    toolCallId: typeof input.toolCallId === 'string'
      ? input.toolCallId
      : typeof input.tool_call_id === 'string'
        ? input.tool_call_id
        : undefined,
    args: input.args,
    result: input.result,
    isError: Boolean(input.isError ?? input.is_error),
  }
}

function extractStructuredToolBlocks(content: string): { content: string, toolEvents: ToolEvent[] } {
  if (!content.includes('```tool-'))
    return { content, toolEvents: [] }

  const toolEvents: ToolEvent[] = []
  let remaining = content
  let cleaned = ''

  while (remaining.length > 0) {
    const startCall = remaining.indexOf('```tool-call')
    const startResult = remaining.indexOf('```tool-result')
    const start = startCall === -1
      ? startResult
      : startResult === -1
        ? startCall
        : Math.min(startCall, startResult)
    if (start === -1) {
      cleaned += remaining
      break
    }

    cleaned += remaining.slice(0, start)
    const isToolCall = remaining.startsWith('```tool-call', start)
    const afterHeader = remaining.indexOf('\n', start)
    if (afterHeader === -1) {
      cleaned += remaining.slice(start)
      break
    }

    const end = remaining.indexOf('```', afterHeader + 1)
    if (end === -1) {
      cleaned += remaining.slice(start)
      break
    }

    const block = remaining.slice(afterHeader + 1, end).trim()
    if (block) {
      const lines = block.split('\n')
      const summary = (lines[0] || '').trim()
      const body = lines.slice(1).join('\n').trim()
      const isError = summary.startsWith('❌ ')
      const isSuccess = summary.startsWith('✅ ')
      const name = (isError || isSuccess) ? summary.slice(2).trim() : summary
      toolEvents.push({
        type: isToolCall ? 'tool_call' : 'tool_result',
        name: name || '工具',
        isError: isToolCall ? undefined : isError,
        args: isToolCall ? body : undefined,
        result: isToolCall ? undefined : body,
      })
    }

    remaining = remaining.slice(end + 3)
  }

  return {
    content: cleaned.replace(/\n{3,}/g, '\n\n').trim(),
    toolEvents,
  }
}

function buildMessageQueueKey(role: Message['role'], content: string): string {
  return `${role}\u0000${extractStructuredToolBlocks(content).content}`
}

function normalizeMessage(input: any, assistantName?: string): Message | null {
  if (!input || typeof input !== 'object')
    return null

  const role = input.role
  if (role !== 'system' && role !== 'user' && role !== 'assistant' && role !== 'info')
    return null

  const initialContent = typeof input.content === 'string' ? input.content : ''
  const extracted = extractStructuredToolBlocks(initialContent)
  const rawEvents = Array.isArray(input.toolEvents)
    ? input.toolEvents
    : Array.isArray(input.tool_events)
      ? input.tool_events
      : []
  const toolEvents = [
    ...((rawEvents.map(normalizeToolEvent).filter(Boolean)) as ToolEvent[]),
    ...extracted.toolEvents,
  ]

  return {
    role,
    content: extracted.content,
    reasoning: typeof input.reasoning === 'string' ? input.reasoning : undefined,
    generating: Boolean(input.generating),
    status: typeof input.status === 'string' ? input.status : undefined,
    sender: typeof input.sender === 'string' ? input.sender : role === 'assistant' ? assistantName : undefined,
    toolEvents: toolEvents.length ? toolEvents : undefined,
  }
}

function mergeAssistantMessages(base: Message, extra: Message) {
  if (extra.content) {
    base.content = base.content
      ? `${base.content}\n\n${extra.content}`.trim()
      : extra.content
  }
  if (extra.reasoning) {
    base.reasoning = base.reasoning
      ? `${base.reasoning}\n\n${extra.reasoning}`.trim()
      : extra.reasoning
  }
  if (extra.toolEvents?.length) {
    base.toolEvents = [...(base.toolEvents || []), ...extra.toolEvents]
  }
  if (!base.status && extra.status)
    base.status = extra.status
  if (!base.sender && extra.sender)
    base.sender = extra.sender
  base.generating = base.generating || extra.generating
}

export function normalizeMessages(messages: unknown, assistantName?: string): Message[] {
  if (!Array.isArray(messages))
    return []

  const normalized: Message[] = []
  for (const item of messages) {
    const message = normalizeMessage(item, assistantName)
    if (!message)
      continue

    const previous = normalized[normalized.length - 1]
    if (message.role === 'assistant' && previous?.role === 'assistant') {
      mergeAssistantMessages(previous, message)
      continue
    }
    normalized.push(message)
  }
  return normalized
}

function isInternalAgentArtifact(message: Message): boolean {
  const text = `${message.content || ''}\n${message.reasoning || ''}`.trim()
  if (!text)
    return false
  if (message.role === 'user' && isCronHookMessage(text))
    return true
  if (message.role === 'user' && text.includes('Your previous response was only an acknowledgement'))
    return true
  if (message.role === 'assistant' && /\bNO_REPLY\b/.test(text))
    return true
  if (text.includes('/crons/') && text.includes('task.md'))
    return true
  if (text.includes('<|tool_calls_section_begin|>'))
    return true
  return false
}

function isCronHookMessage(text: string): boolean {
  const prefix = '[cron:'
  if (!text.startsWith(prefix))
    return false

  const closeIndex = text.indexOf(']', prefix.length)
  if (closeIndex === -1)
    return false

  const label = text.slice(prefix.length, closeIndex).trimEnd()
  const hook = 'hook'
  if (label.length <= hook.length)
    return false

  const hookStart = label.length - hook.length
  return label.slice(hookStart).toLowerCase() === hook && isWhitespace(label[hookStart - 1])
}

function isWhitespace(char: string | undefined): boolean {
  return char === ' ' || char === '\t' || char === '\n' || char === '\r' || char === '\f'
}

function filterInternalAgentArtifacts(messages: Message[]): Message[] {
  return messages.filter(message => !isInternalAgentArtifact(message))
}

function buildToolEventQueue(messages: Message[]): Map<string, ToolEvent[][]> {
  const queue = new Map<string, ToolEvent[][]>()
  for (const message of messages) {
    if (!message.toolEvents?.length)
      continue
    const key = buildMessageQueueKey(message.role, message.content)
    const items = queue.get(key) || []
    items.push(message.toolEvents)
    queue.set(key, items)
  }
  return queue
}

function takeQueuedToolEvents(queue: Map<string, ToolEvent[][]>, role: Message['role'], content: string): ToolEvent[] | undefined {
  const key = buildMessageQueueKey(role, content)
  const items = queue.get(key)
  if (!items?.length)
    return undefined
  const next = items.shift()
  if (!items.length)
    queue.delete(key)
  return next
}

// ── 通讯录状态 ──

export interface AgentContact {
  id: string
  name: string
  running: boolean
  createdAt?: number
  created_at?: number
  characterTemplate?: string
  engine?: AgentEngine
  builtin?: boolean
}

/** 通讯录列表（从后端 GET /openclaw/agents 加载） */
export const agentContacts = ref<AgentContact[]>([])

/** 加载通讯录 */
export async function loadAgentContacts() {
  try {
    const [agentsRes, charactersRes] = await Promise.allSettled([
      API.listAgents(),
      API.listCharacterTemplates(),
    ])

    const activeCharacter = charactersRes.status === 'fulfilled'
      ? (charactersRes.value.activeCharacter || charactersRes.value.characters?.find(item => item.active)?.name || '')
      : ''

    const contacts: AgentContact[] = [{
      id: 'naga-default',
      name: '娜迦',
      running: true,
      engine: 'naga-core',
      characterTemplate: activeCharacter || undefined,
      builtin: true,
    }]

    if (agentsRes.status === 'fulfilled') {
      contacts.push(...(agentsRes.value.agents || []))
    }

    agentContacts.value = contacts

    // 更新 counter 避免编号冲突
    const maxNum = agentContacts.value.reduce((max, a) => {
      const m = a.name.match(/^干员(\d+)$/)
      return m ? Math.max(max, Number.parseInt(m[1] ?? '0')) : max
    }, 0)
    if (maxNum > agentCounter)
      agentCounter = maxNum
  }
  catch {
    // 后端未就绪
  }
}

/** 从通讯录打开干员 tab（如果 tab 已存在则切换，否则创建并立即加载历史） */
export function openAgentTab(contact: AgentContact) {
  if (contact.id === 'naga-default') {
    activeTabId.value = 'naga'
    return getNagaTab()
  }

  const persistedSessionId = contact.engine === 'naga-core'
    ? localStorage.getItem(`agent_session_${contact.id}`) || undefined
    : undefined

  const existing = tabs.value.find(t => t.instanceId === contact.id)
  if (existing) {
    activeTabId.value = existing.id
    existing.engine = contact.engine
    existing.characterTemplate = contact.characterTemplate
    if (persistedSessionId) {
      existing.sessionId = persistedSessionId
    }
    void loadAgentMessages(existing, { forceRefresh: true })
    return existing
  }

  const tab: ChatTab = {
    id: `agent-${contact.id}`,
    type: 'agent',
    name: contact.name,
    instanceId: contact.id,
    sessionId: persistedSessionId,
    engine: contact.engine || 'openclaw',
    characterTemplate: contact.characterTemplate,
    messages: [],
    unread: 0,
  }
  tabs.value.push(tab)
  activeTabId.value = tab.id

  // 立即触发加载（同步设置 loading 状态，避免首帧闪烁）
  void loadAgentMessages(tab, { forceRefresh: true })

  return tab
}

// ── 娜迦 tab 的 MESSAGES 保持兼容 ──

function syncNagaMessages() {
  tabs.value[0]!.messages = MESSAGES.value
}

export async function loadCurrentSession() {
  if (CURRENT_SESSION_ID.value) {
    try {
      const detail = await API.getSessionDetail(CURRENT_SESSION_ID.value)
      MESSAGES.value = normalizeMessages(detail.messages)
      syncNagaMessages()
      return
    }
    catch {
      CURRENT_SESSION_ID.value = null
    }
  }
  MESSAGES.value = []
  syncNagaMessages()
}

export function newSession() {
  CURRENT_SESSION_ID.value = null
  MESSAGES.value = []
  syncNagaMessages()
  IS_TEMPORARY_SESSION.value = false
}

export function newTemporarySession() {
  CURRENT_SESSION_ID.value = null
  MESSAGES.value = []
  syncNagaMessages()
  IS_TEMPORARY_SESSION.value = true
}

export async function switchSession(id: string) {
  CURRENT_SESSION_ID.value = id
  IS_TEMPORARY_SESSION.value = false
  await loadCurrentSession()
}

export function formatRelativeTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1)
    return '刚刚'
  if (diffMin < 60)
    return `${diffMin}分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24)
    return `${diffHour}小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 7)
    return `${diffDay}天前`
  return d.toLocaleDateString()
}

/**
 * 懒加载干员 tab 的对话历史（从 OpenClaw session 恢复）。
 * 后端会自动 ensure_running 启动进程（可能需要数秒）。
 */
const _loadingAgents = ref(new Set<string>())

export function isAgentLoading(instanceId: string) {
  return _loadingAgents.value.has(instanceId)
}

export async function loadAgentMessages(tab: ChatTab, options?: { forceRefresh?: boolean }) {
  if (!tab.instanceId)
    return
  if (tab.engine === 'naga-core') {
    const storageKey = `agent_history_${tab.instanceId}`
    const persistedSessionId = localStorage.getItem(`agent_session_${tab.instanceId}`) || tab.sessionId
    let storageMessages: Message[] = []
    const cached = localStorage.getItem(storageKey)
    if (cached) {
      try {
        const messages = normalizeMessages(JSON.parse(cached), tab.name)
        if (Array.isArray(messages) && messages.length > 0) {
          storageMessages = filterInternalAgentArtifacts(messages)
          tab.messages = storageMessages
        }
      }
      catch {}
    }

    if (persistedSessionId) {
      tab.sessionId = persistedSessionId
      try {
        const detail = await API.getSessionDetail(persistedSessionId)
        const cachedToolEvents = buildToolEventQueue(storageMessages)
        if (Array.isArray(detail.messages) && detail.messages.length > 0) {
          tab.messages = normalizeMessages(
            detail.messages.map((m) => {
              const role = m.role as Message['role']
              return {
                role,
                content: m.content,
                sender: role === 'assistant' ? tab.name : undefined,
                toolEvents: takeQueuedToolEvents(cachedToolEvents, role, m.content),
              }
            }),
            tab.name,
          )
          tab.messages = filterInternalAgentArtifacts(tab.messages)
          localStorage.setItem(storageKey, JSON.stringify(tab.messages))
          return
        }
      }
      catch {
        // 保留 localStorage 兜底
      }
    }

    if (!tab.messages.length && !storageMessages.length) {
      tab.messages = [{
        role: 'system',
        content: `NagaCore 干员「${tab.name}」已就绪。它会使用当前娜迦后端能力，并按该干员自己的 IDENTITY / SOUL / 私有技能目录装配上下文。`,
      }]
    }
    return
  }
  if (_loadingAgents.value.has(tab.instanceId))
    return
  const forceRefresh = options?.forceRefresh === true
  const cachedMessages = tab.messages.slice()
  let storageMessages: Message[] = []

  // 跳过已有真实消息的 tab
  if (!forceRefresh && tab.messages.length > 0)
    return
  _loadingAgents.value = new Set([..._loadingAgents.value, tab.instanceId])

  try {
    const storageKey = `agent_history_${tab.instanceId}`

    // 先尝试读取 localStorage。强制刷新时继续向后端取数，不在这里 return。
    const cached = localStorage.getItem(storageKey)
    if (cached) {
      try {
        const messages = normalizeMessages(JSON.parse(cached), tab.name)
        if (Array.isArray(messages) && messages.length > 0) {
          storageMessages = filterInternalAgentArtifacts(messages)
          tab.messages = storageMessages
          if (!forceRefresh) {
            return
          }
        }
      }
      catch {}
    }

    // 强制刷新时也走后端，以触发 ensure_running 唤醒 OpenClaw 进程。
    const res = await API.getAgentHistory(tab.instanceId)
    if (res.messages?.length) {
      tab.messages = normalizeMessages(
        res.messages.map(m => ({
          role: m.role,
          content: m.content,
          sender: m.role === 'assistant' ? tab.name : undefined,
          toolEvents: (m as any).toolEvents ?? (m as any).tool_events,
        })),
        tab.name,
      )
      tab.messages = filterInternalAgentArtifacts(tab.messages)
      localStorage.setItem(storageKey, JSON.stringify(tab.messages))
    }
    else if (storageMessages.length > 0) {
      // 后端暂无历史时，保留 localStorage 中的历史作为展示兜底。
      tab.messages = storageMessages
    }
    else if (forceRefresh && cachedMessages.length > 0) {
      // 唤醒成功但后端暂无历史且本地无缓存时，保留已打开 tab 中的消息。
      tab.messages = cachedMessages
    }
  }
  catch {
    // 强制刷新失败时优先保留 localStorage，其次保留已打开 tab 的消息
    if (storageMessages.length > 0) {
      tab.messages = storageMessages
    }
    else if (forceRefresh && cachedMessages.length > 0) {
      tab.messages = cachedMessages
    }
  }
  finally {
    _loadingAgents.value.delete(tab.instanceId)
    // 触发 ref 更新（Set 的 delete 不会自动触发）
    _loadingAgents.value = new Set(_loadingAgents.value)
  }
}

declare global {
  interface WindowEventMap {
    token: CustomEvent<StreamChunk>
  }
}
