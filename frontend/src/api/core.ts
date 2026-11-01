import type { TravelSession } from '@/travel/types'
import type { Config } from '@/utils/config'
import type { StreamChunk } from '@/utils/encoding'
import axios from 'axios'
import camelcaseKeys from 'camelcase-keys'
import { aiter } from 'iterator-helper'
import snakecaseKeys from 'snakecase-keys'
import { decodeStreamChunk, readerToMessageStream } from '@/utils/encoding'
import { ACCESS_TOKEN, ApiClient } from './index'

// Agent Server (port 8001) 的 axios 实例
const agentAxios = (() => {
  const instance = axios.create({
    baseURL: 'http://localhost:8001',
    timeout: 180 * 1000, // 干员实例操作可能较慢
    headers: { 'Content-Type': 'application/json' },
    transformRequest(data) {
      if (
        data
        && typeof data === 'object'
        && !(data instanceof FormData)
        && !(data instanceof ArrayBuffer)
        && !(data instanceof Blob)
      ) {
        return JSON.stringify(snakecaseKeys(data, { deep: true }))
      }
      return data
    },
    transformResponse: [(data: string) => {
      try {
        return camelcaseKeys(JSON.parse(data), { deep: true })
      }
      catch {
        return data
      }
    }],
  })
  instance.interceptors.request.use((config) => {
    if (ACCESS_TOKEN.value) {
      config.headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`
    }
    return config
  })
  instance.interceptors.response.use(response => response.data)
  return instance
})()

export interface OpenClawStatus {
  found: boolean
  version?: string
  skills_dir: string
  config_path: string
  skills_error?: string
}

export interface CharacterTemplate {
  name: string
  aiName?: string
  bio?: string
  voice?: string
  promptFile?: string
  portrait?: string
  live2dModel?: string
  live2dModelUrl?: string
  active?: boolean
}

export interface CustomLive2DModel {
  id: string
  name: string
  modelPath: string
  source: string
  fileCount: number
  totalBytes: number
  createdAt: string
}

export type AgentEngine = 'openclaw' | 'naga-core'

export interface SkillCatalogItem {
  name: string
  description: string
  version?: string
  tags?: string[]
  scope: 'cache' | 'public' | 'private'
  source: string
  path: string
  ownerAgentId?: string
  ownerAgentName?: string
  ownerEngine?: AgentEngine
}

export interface SkillCatalogSection {
  skills: SkillCatalogItem[]
  baseDir?: string
  baseDirs?: string[]
}

export interface AgentSettings {
  id: string
  name: string
  engine: AgentEngine
  characterTemplate?: string
  soulContent?: string
}

export interface McpService {
  name: string
  displayName: string
  description: string
  source: 'builtin' | 'mcporter'
  scope: 'public' | 'private'
  ownerAgentId?: string | null
  ownerAgentName?: string | null
  available: boolean
  enabled: boolean
  config?: Record<string, any>
}

export interface MarketItem {
  id: string
  title: string
  description: string
  skill_name?: string
  enabled: boolean
  installed: boolean
  eligible?: boolean
  disabled?: boolean
  missing?: boolean
  skill_path: string
  openclaw_visible: boolean
  install_type: string
}

export interface MemoryStats {
  totalQuintuples: number
  contextLength: number
  cacheSize: number
  activeTasks: number
  taskManager: {
    enabled: boolean
    totalTasks: number
    pendingTasks: number
    runningTasks: number
    completedTasks: number
    failedTasks: number
    cancelledTasks: number
    maxWorkers: number
    maxQueueSize: number
    queueSize: number
    queueUsage: string
    taskTimeout: number
  }
}
export type { SocialInteraction, TravelDiscovery, TravelSession } from '@/travel/types'

export class CoreApiClient extends ApiClient {
  health(): Promise<{
    status: 'healthy'
    agentReady: true
    timestamp: string
  }> {
    // 添加时间戳防止 Chromium HTTP 缓存返回旧响应（快速重启场景）
    return this.instance.get(`/health?_t=${Date.now()}`)
  }

  agentServerHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/health?_t=${Date.now()}`)
  }

  agentServerFullHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/health/full?_t=${Date.now()}`)
  }

  agentServerOpenclawHealth(): Promise<Record<string, any>> {
    return agentAxios.get(`/openclaw/health?_t=${Date.now()}`)
  }

  systemInfo(): Promise<{
    version: string
    status: 'running'
    availableServices: []
    apiKeyConfigured: boolean
  }> {
    return this.instance.get('/system/info')
  }

  systemConfig(): Promise<{
    status: 'success'
    config: Config
  }> {
    // 配置对象使用 snake_case 键名，跳过自动 camelCase 转换以避免键名不匹配
    // 添加时间戳防止 HTTP 缓存（快速重启场景）
    return this.instance(`/system/config?_t=${Date.now()}`, {
      transformResponse: [(data: string) => JSON.parse(data)],
    })
  }

  setSystemConfig(config: Config): Promise<{
    status: 'success'
    message: string
  }> {
    // 配置对象已是 snake_case，跳过自动 snakeCase 转换避免双重处理
    return this.instance.post('/system/config', config, {
      transformRequest: [(data: any) => JSON.stringify(data)],
      transformResponse: [(data: string) => JSON.parse(data)],
    })
  }

  trackTelemetry(params: {
    event: string
    props?: Record<string, any>
    source?: string
    traceId?: string
    sessionId?: string
    agentId?: string
  }): Promise<{ status: 'accepted' }> {
    return this.instance.post('/telemetry/track', params)
  }

  flushTelemetry(): Promise<{
    status: 'ok'
    result: Record<string, any>
  }> {
    return this.instance.post('/telemetry/flush')
  }

  getTelemetryStatus(): Promise<{
    status: 'success'
    telemetry: Record<string, any>
  }> {
    return this.instance.get('/telemetry/status')
  }

  getSystemPrompt(): Promise<{
    status: 'success'
    prompt: string
  }> {
    return this.instance.get('/system/prompt')
  }

  setSystemPrompt(content: string): Promise<{
    status: 'success'
    message: string
  }> {
    return this.instance.post('/system/prompt', { content })
  }

  getActiveCharacter(): Promise<{
    status: 'success'
    character: {
      name: string
      aiName: string
      userName: string
      live2dModelUrl: string
      promptFile: string
    }
  }> {
    return this.instance.get('/system/character')
  }

  listCharacterTemplates(): Promise<{
    status: 'success'
    activeCharacter?: string
    characters: CharacterTemplate[]
  }> {
    return this.instance.get('/system/characters')
  }

  listCustomLive2DModels(): Promise<{
    status: 'success'
    models: CustomLive2DModel[]
  }> {
    return this.instance.get('/system/live2d/custom-models')
  }

  uploadCustomLive2DModel(params: {
    name: string
    files: File[]
    modelPath?: string
  }): Promise<{
    status: 'success'
    model: CustomLive2DModel
  }> {
    const formData = new FormData()
    formData.append('name', params.name)
    if (params.modelPath) {
      formData.append('model_path', params.modelPath)
    }
    for (const file of params.files) {
      const relativePath = file.webkitRelativePath || file.name
      formData.append('files', file, relativePath)
    }
    return this.instance.post('/system/live2d/custom-models', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  }

  deleteCustomLive2DModel(id: string): Promise<{
    status: 'success'
    message: string
  }> {
    return this.instance.delete(`/system/live2d/custom-models/${encodeURIComponent(id)}`)
  }

  chat(message: string, options?: {
    sessionId?: string
    agentId?: string
    useSelfGame?: boolean
    skipIntentAnalysis?: boolean
  }): Promise<{
    status: 'success'
    response: string
    sessionId?: string
  }> {
    return this.instance.post('/chat', { message, ...options })
  }

  async chatStream(message: string, options?: {
    sessionId?: string
    agentId?: string
    returnAudio?: boolean
    disableTTS?: boolean
    skipIntentAnalysis?: boolean
    skill?: string
    images?: string[]
    temporary?: boolean
  }): Promise<{
    sessionId?: string
    response: AsyncGenerator<StreamChunk>
  }> {
    const { body } = await fetch(`${this.endpoint}/chat/stream`, {
      method: 'POST',
      headers: {
        'Accept': 'text/event-stream',
        'Authorization': ACCESS_TOKEN.value ? `Bearer ${ACCESS_TOKEN.value}` : '',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(snakecaseKeys({ message, ...options }, { deep: true })),
    })

    const reader = await body?.getReader()
    if (!reader) {
      throw new Error('Failed to get reader')
    }
    const messageStream = readerToMessageStream(reader)
    const { value } = await messageStream.next()
    if (!value?.startsWith('session_id: ')) {
      throw new Error('Failed to get sessionId')
    }
    return {
      sessionId: value.slice(12),
      response: aiter(messageStream).map(decodeStreamChunk),
    }
  }

  getSessions(): Promise<{
    status: string
    sessions: Array<{
      sessionId: string
      createdAt: string
      lastActiveAt: string
      conversationRounds: number
      temporary: boolean
    }>
    totalSessions: number
  }> {
    return this.instance.get('/sessions')
  }

  getSessionDetail(id: string): Promise<{
    status: string
    sessionId: string
    messages: Array<{ role: string, content: string }>
    conversationRounds: number
  }> {
    return this.instance.get(`/sessions/${id}`)
  }

  deleteSession(id: string) {
    return this.instance.delete(`/sessions/${id}`)
  }

  clearAllSessions() {
    return this.instance.delete('/sessions')
  }

  getToolStatus(): Promise<{ message: string, visible: boolean }> {
    return this.instance.get('/tool_status')
  }

  getClawdbotReplies(): Promise<{ replies: string[] }> {
    return this.instance.get('/clawdbot/replies')
  }

  uploadDocument(file: File, description?: string): Promise<{
    status: 'success'
    message: string
    filename: string
    filePath: string
    fileSize: number
    fileType: string
    uploadTime: string
  }> {
    const formData = new FormData()
    formData.append('file', file)
    if (description) {
      formData.append('description', description)
    }
    return this.instance.post('/upload/document', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  }

  parseDocument(file: File): Promise<{
    status: 'success'
    filename: string
    content: string
    truncated: boolean
    charCount: number
  }> {
    const formData = new FormData()
    formData.append('file', file)
    return this.instance.post('/upload/parse', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    })
  }

  getMemoryStats(): Promise<{
    status: string
    memoryStats: { enabled: true } & MemoryStats
      | { enabled: false, message: string }
  }> {
    return this.instance.get('/memory/stats')
  }

  getQuintuples(): Promise<{
    status: string
    quintuples: Array<{
      subject: string
      subjectType: string
      predicate: string
      object: string
      objectType: string
    }>
    count: number
  }> {
    return this.instance.get('/memory/quintuples')
  }

  searchQuintuples(keywords: string): Promise<{
    status: string
    quintuples: Array<{
      subject: string
      subjectType: string
      predicate: string
      object: string
      objectType: string
    }>
    count: number
  }> {
    return this.instance.get(`/memory/quintuples/search?keywords=${encodeURIComponent(keywords)}`)
  }

  getMarketItems(): Promise<{
    status: 'success'
    openclaw: OpenClawStatus
    items: MarketItem[]
  }> {
    return this.instance.get('/openclaw/market/items')
  }

  installMarketItem(itemId: string): Promise<{
    status: 'success'
    message: string
    item: MarketItem
    openclaw: OpenClawStatus
  }> {
    return this.instance.post(`/openclaw/market/items/${itemId}/install`, {}, {
      timeout: 5 * 60 * 1000,
    })
  }

  getMcpStatus(): Promise<{
    server: string
    timestamp: string
    tasks: { total: number, active: number, completed: number, failed: number }
    scheduler?: Record<string, any>
  }> {
    return this.instance.get('/mcp/status')
  }

  getMcpServices(): Promise<{
    status: string
    services: McpService[]
  }> {
    return this.instance.get('/mcp/services', {
      params: { _t: Date.now() },
    })
  }

  importMcpConfig(params: {
    name: string
    config: Record<string, any>
    displayName?: string
    description?: string
    scope?: 'public' | 'private'
    agentId?: string
  }): Promise<{
    status: string
    message: string
  }> {
    return this.instance.post('/mcp/import', params)
  }

  updateMcpService(name: string, body: Record<string, any>): Promise<{
    status: string
    message: string
  }> {
    return this.instance.put(`/mcp/services/${encodeURIComponent(name)}`, body)
  }

  deleteMcpService(name: string): Promise<{
    status: string
    message: string
  }> {
    return this.instance.delete(`/mcp/services/${encodeURIComponent(name)}`)
  }

  importCustomSkill(name: string, content: string): Promise<{
    status: string
    message: string
  }> {
    return this.instance.post('/skills/import', { name, content })
  }

  getSkillCatalog(): Promise<{
    status: 'success'
    catalog: {
      remoteHub: {
        status: string
        message: string
        baseUrl?: string
        skillEndpointTemplate?: string
        mcpEndpointTemplate?: string
      }
      localCache: SkillCatalogSection
      publicSkills: SkillCatalogSection
      privateSkills: SkillCatalogSection
    }
  }> {
    return this.instance.get('/skills/catalog')
  }

  importScopedSkill(params: {
    name: string
    content: string
    scope: 'cache' | 'public' | 'private'
    agentId?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    path: string
  }> {
    return this.instance.post('/skills/import', params)
  }

  cloneSkill(params: {
    name: string
    sourceScope: 'cache' | 'public' | 'private'
    targetScope: 'cache' | 'public' | 'private'
    sourceAgentId?: string
    targetAgentId?: string
  }): Promise<{
    status: string
    message: string
    sourceScope: string
    targetScope: string
    path: string
  }> {
    return this.instance.post('/skills/clone', params)
  }

  deleteSkill(name: string, scope: 'cache' | 'public' | 'private', agentId?: string): Promise<{
    status: string
    message: string
    scope: string
    path: string
  }> {
    return this.instance.delete(`/skills/${encodeURIComponent(name)}`, {
      params: {
        scope,
        agent_id: agentId,
      },
    })
  }

  installHubSkill(params: {
    name: string
    scope: 'cache' | 'public' | 'private'
    agentId?: string
    source?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    path: string
    name: string
    source: string
  }> {
    return this.instance.post('/hub/skills/install', params)
  }

  installHubMcp(params: {
    name: string
    scope: 'public' | 'private'
    agentId?: string
    source?: string
  }): Promise<{
    status: string
    message: string
    scope: string
    name: string
    source: string
  }> {
    return this.instance.post('/hub/mcp/install', params)
  }

  getContextStats(days?: number) {
    return this.instance.get(`/logs/context/statistics?days=${days}`)
  }

  loadContext(days?: number): Promise<{
    status: 'success'
    messages: { role: 'user' | 'assistant', content: string }[]
    count: number
    days: number
  }> {
    return this.instance.get(`/logs/context/load?days=${days}`)
  }

  getOpenclawTasks(): Promise<{
    status: string
    tasks: Array<Record<string, any>>
  }> {
    return this.instance.get('/openclaw/tasks')
  }

  getOpenclawTaskDetail(taskId: string): Promise<Record<string, any>> {
    return this.instance.get(`/openclaw/tasks/${taskId}`)
  }

  getMcpTasks(status?: string): Promise<Record<string, any>> {
    const params = status ? `?status=${status}` : ''
    return this.instance.get(`/mcp/tasks${params}`)
  }

  getLive2dActions(): Promise<{ actions: string[] }> {
    return this.instance.get('/live2d/actions')
  }

  getMusicCommands(): Promise<{ commands: Array<{ action: string, track?: string }> }> {
    return this.instance.get('/music/commands')
  }

  // ── ASR 语音识别 ──

  transcribeAudio(file: Blob, options?: {
    language?: string
    model?: string
    prompt?: string
  }): Promise<{ text: string }> {
    const formData = new FormData()
    formData.append('file', file, 'recording.webm')
    if (options?.language)
      formData.append('language', options.language)
    if (options?.model)
      formData.append('model', options.model)
    if (options?.prompt)
      formData.append('prompt', options.prompt)
    return this.instance.post('/asr/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 30000,
    })
  }

  // ── NagaCAS 认证 ──

  authLogin(username: string, password: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    user: { username: string, sub?: string } | null
    accessToken: string
    memoryUrl?: string
  }> {
    return this.instance.post('/auth/login', { username, password, captcha_id: captchaId, captcha_answer: captchaAnswer })
  }

  authMe(): Promise<{ user: { username: string, sub?: string }, memoryUrl?: string, accessToken?: string }> {
    return this.instance.get('/auth/me')
  }

  authLogout(): Promise<{ success: boolean }> {
    return this.instance.post('/auth/logout')
  }

  authRegister(username: string, email: string, password: string, verificationCode: string): Promise<{
    success: boolean
    user?: { username: string, email: string, sub?: string }
    accessToken?: string
  }> {
    return this.instance.post('/auth/register', { username, email, password, verification_code: verificationCode })
  }

  authSendVerification(email: string, username: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    message: string
  }> {
    return this.instance.post('/auth/send-verification', { email, username, captcha_id: captchaId, captcha_answer: captchaAnswer })
  }

  authSendQqVerification(email: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    message: string
  }> {
    return this.instance.post('/auth/send-qq-verification', { email, captcha_id: captchaId, captcha_answer: captchaAnswer })
  }

  authBindQqEmail(qqEmail: string, verificationCode: string): Promise<{
    ok: boolean
    message: string
    binding?: {
      userId: string
      username: string
      qqEmail: string
      qqNumber: string
    }
  }> {
    return this.instance.post('/auth/qq-email', { qq_email: qqEmail, verification_code: verificationCode })
  }

  authGetQqEmailBinding(): Promise<{
    ok: boolean
    binding: null | {
      userId: string
      username: string
      qqEmail: string
      qqNumber: string
    }
    qqEmail: string | null
    qqNumber: string | null
    currentAccountQqEmail: string | null
    currentAccountQqNumber: string | null
    currentAccountEmailVerified: boolean
    directBindAvailable: boolean
  }> {
    return this.instance.get('/auth/qq-email')
  }

  testQqNotification(qqUserId: string, message?: string): Promise<{
    status: 'success'
    deliveryStatus: string
  }> {
    return this.instance.post('/system/notifications/qq/test', { qq_user_id: qqUserId, message })
  }

  authGetCaptcha(format?: 'image'): Promise<{
    captchaId: string
    question?: string
    imageData?: string
    mimeType?: string
    answerLength?: number
    type?: 'image' | 'math'
    legacyCompatible?: boolean
  }> {
    const params = format ? { format } : undefined
    return this.instance.get('/auth/captcha', { params })
  }

  // ── 旅行 ──

  startTravel(params: {
    agentId?: string
    timeLimitMinutes?: number
    creditLimit?: number
    wantFriends?: boolean
    friendDescription?: string
    goalPrompt?: string
    postToForum?: boolean
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', sessionId: string }> {
    return this.instance.post('/travel/start', params)
  }

  createTravelSession(params: {
    agentId?: string
    timeLimitMinutes?: number
    creditLimit?: number
    wantFriends?: boolean
    friendDescription?: string
    goalPrompt?: string
    postToForum?: boolean
    deliverFullReport?: boolean
    deliverChannel?: string
    deliverTo?: string
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', sessionId: string, session: TravelSession }> {
    return this.instance.post('/travel/sessions', params)
  }

  updateTravelSessionBrowser(sessionId: string, params: {
    browserVisible?: boolean
    browserKeepOpen?: boolean
    browserIdleTimeoutSeconds?: number
  }): Promise<{ status: 'success', session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/browser`, params)
  }

  sendTravelInstruction(sessionId: string, message: string): Promise<{ status: 'success', session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/instruction`, { message })
  }

  getTravelStatus(): Promise<{
    status: 'success'
    session: TravelSession | null
    active: boolean
  }> {
    return this.instance.get('/travel/status')
  }

  getTravelSessions(): Promise<{
    status: 'success'
    sessions: TravelSession[]
  }> {
    return this.instance.get('/travel/sessions')
  }

  getTravelSession(sessionId: string): Promise<{
    status: 'success'
    session: TravelSession
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}`)
  }

  getTravelSessionReport(sessionId: string): Promise<{
    status: 'success'
    exists: boolean
    path: string | null
    title?: string | null
    content: string | null
    missingReason?: 'not_generated' | 'missing'
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}/report`)
  }

  getTravelSessionHistory(sessionId: string, limit = 0, includeTools = true): Promise<{
    status: 'success'
    sessionId: string
    sessionKey: string | null
    messages: Array<Record<string, any>>
  }> {
    return this.instance.get(`/travel/sessions/${sessionId}/history`, {
      params: {
        limit,
        include_tools: includeTools,
      },
    })
  }

  stopTravel(sessionId?: string): Promise<{ status: 'success', sessionId: string }> {
    return this.instance.post('/travel/stop', sessionId ? { sessionId } : {})
  }

  stopTravelSession(sessionId: string): Promise<{ status: 'success', sessionId: string, session: TravelSession }> {
    return this.instance.post(`/travel/sessions/${sessionId}/stop`)
  }

  getTravelHistory(): Promise<{
    status: 'success'
    sessions: TravelSession[]
  }> {
    return this.instance.get('/travel/history')
  }

  // ── 干员通讯录 API（Agent Server 8001） ──

  /** 列出通讯录中所有干员 */
  listAgents(): Promise<{ agents: Array<{ id: string, name: string, running: boolean, createdAt?: number, created_at?: number, characterTemplate?: string, engine?: AgentEngine }> }> {
    return agentAxios.get('/openclaw/agents')
  }

  /** 新建干员（写 manifest + 创建目录，不启动进程） */
  createAgent(name?: string, characterTemplate?: string, engine: AgentEngine = 'openclaw'): Promise<{ id: string, name: string, running: boolean, characterTemplate?: string, engine?: AgentEngine }> {
    return agentAxios.post('/openclaw/agents', { name, characterTemplate, engine })
  }

  /** 从通讯录删除干员 */
  deleteAgent(id: string, deleteData = true): Promise<{ success: boolean }> {
    return agentAxios.delete(`/openclaw/agents/${id}?delete_data=${deleteData}`)
  }

  /** 重命名干员 */
  renameAgent(id: string, name: string): Promise<{ success: boolean, name: string }> {
    return agentAxios.put(`/openclaw/agents/${id}/name`, { name })
  }

  /** 查询/唤醒干员运行时 */
  getAgentRuntime(id: string, wake = false): Promise<{
    success: boolean
    runtime: {
      id: string
      name: string
      engine: AgentEngine
      running: boolean
      woken?: boolean
      port?: number | null
      gatewayUrl?: string | null
      primary?: boolean
    }
  }> {
    return agentAxios.get(`/openclaw/agents/${id}/runtime`, { params: { wake } })
  }

  /** 获取干员对话历史 */
  getAgentHistory(id: string, limit = 50): Promise<{ messages: Array<{ role: string, content: string, toolEvents?: any[] }> }> {
    return agentAxios.get(`/openclaw/agents/${id}/history`, { params: { limit } })
  }

  getAgentSettings(id: string): Promise<AgentSettings> {
    return agentAxios.get(`/openclaw/agents/${id}/settings`)
  }

  updateAgentSettings(id: string, body: {
    name?: string
    engine?: AgentEngine
    characterTemplate?: string
    soulContent?: string
  }): Promise<AgentSettings> {
    return agentAxios.put(`/openclaw/agents/${id}/settings`, body)
  }

  relayAgentMessage(params: {
    message: string
    targetAgentId?: string
    targetAgentName?: string
    sourceAgentId?: string
    sourceAgentName?: string
    purpose?: string
    context?: string
    timeoutSeconds?: number
    sessionId?: string
  }): Promise<{
    success: boolean
    status: string
    reply?: string
    error?: string
    session_id?: string
    session_key?: string
    target?: { id: string, name: string, engine: string, character_template?: string, builtin?: boolean }
  }> {
    return this.instance.post('/agents/relay', {
      message: params.message,
      target_agent_id: params.targetAgentId,
      target_agent_name: params.targetAgentName,
      source_agent_id: params.sourceAgentId,
      source_agent_name: params.sourceAgentName,
      purpose: params.purpose,
      context: params.context,
      timeout_seconds: params.timeoutSeconds,
      session_id: params.sessionId,
    })
  }

  /** 流式发送消息到干员（SSE，内部自动 ensure_running） */
  async* streamToAgent(id: string, message: string, timeoutSeconds = 120): AsyncGenerator<{
    type: string
    text: string
    name?: string
    toolCallId?: string
    args?: any
    result?: any
    isError?: boolean
  }> {
    const resp = await fetch(`http://localhost:8001/openclaw/agents/${id}/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify({ message, timeout_seconds: timeoutSeconds }),
    })

    if (!resp.ok || !resp.body)
      throw new Error(`Stream failed: ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done)
        break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            yield JSON.parse(line.slice(6))
          }
          catch { /* skip malformed */ }
        }
      }
    }
  }

  // ── 旧干员实例 API（兼容，逐步废弃） ──

  createAgentInstance(name?: string): Promise<{ id: string, name: string, port: number, primary: boolean }> {
    return agentAxios.post('/openclaw/instances', { name })
  }

  destroyAgentInstance(id: string): Promise<{ success: boolean }> {
    return agentAxios.delete(`/openclaw/instances/${id}`)
  }

  listAgentInstances(): Promise<{ instances: Array<{ id: string, name: string, port: number, primary: boolean }> }> {
    return agentAxios.get('/openclaw/instances')
  }

  sendToAgentInstance(id: string, message: string, timeoutSeconds = 120): Promise<{ success: boolean, reply?: string, replies?: string[], error?: string, retry?: boolean }> {
    return agentAxios.post(`/openclaw/instances/${id}/send`, {
      message,
      timeout_seconds: timeoutSeconds,
    })
  }

  async* streamToAgentInstance(id: string, message: string, timeoutSeconds = 120): AsyncGenerator<{ type: string, text: string }> {
    yield* this.streamToAgent(id, message, timeoutSeconds)
  }

  renameAgentInstance(id: string, name: string): Promise<{ success: boolean, name: string }> {
    return agentAxios.put(`/openclaw/agents/${id}/name`, { name })
  }

  getAgentInstanceHistory(id: string, limit = 50): Promise<{ messages: Array<{ role: string, content: string }> }> {
    return this.getAgentHistory(id, limit)
  }
}

export default new CoreApiClient(8000)
