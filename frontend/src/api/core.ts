import type { Config } from '@/utils/config'
import type { StreamChunk } from '@/utils/encoding'
import { aiter } from 'iterator-helper'
import snakecaseKeys from 'snakecase-keys'
import { decodeStreamChunk, readerToMessageStream } from '@/utils/encoding'
import { ACCESS_TOKEN, ApiClient } from './index'

export interface OpenClawStatus {
  found: boolean
  version?: string
  skills_dir: string
  config_path: string
  skills_error?: string
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
export class CoreApiClient extends ApiClient {
  health(): Promise<{
    status: 'healthy'
    agentReady: true
    timestamp: string
  }> {
    // 添加时间戳防止 Chromium HTTP 缓存返回旧响应（快速重启场景）
    return this.instance.get(`/health?_t=${Date.now()}`)
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

  chat(message: string, options?: {
    sessionId?: string
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
    services: Array<{
      name: string
      displayName: string
      description: string
      source: 'builtin' | 'mcporter'
      available: boolean
      enabled: boolean
      config?: Record<string, any>
    }>
  }> {
    return this.instance.get('/mcp/services', {
      params: { _t: Date.now() },
    })
  }

  importMcpConfig(name: string, config: Record<string, any>): Promise<{
    status: string
    message: string
  }> {
    return this.instance.post('/mcp/import', { name, config }, {
      transformRequest: [(data: any) => JSON.stringify(data)],
    })
  }

  updateMcpService(name: string, body: Record<string, any>): Promise<{
    status: string
    message: string
  }> {
    return this.instance.put(`/mcp/services/${encodeURIComponent(name)}`, body, {
      transformRequest: [(data: any) => JSON.stringify(data)],
    })
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

  // ── NagaCAS 认证 ──

  authLogin(username: string, password: string, captchaId?: string, captchaAnswer?: string): Promise<{
    success: boolean
    user: { username: string, sub?: string } | null
    accessToken: string
    memoryUrl?: string
  }> {
    return this.instance.post('/auth/login', { username, password, captcha_id: captchaId, captcha_answer: captchaAnswer })
  }

  authMe(): Promise<{ user: { username: string, sub?: string }, memoryUrl?: string }> {
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

  authGetCaptcha(): Promise<{
    captchaId: string
    question: string
  }> {
    return this.instance.get('/auth/captcha')
  }
}

export default new CoreApiClient(8000)
