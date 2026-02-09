import type { Config } from '@/utils/config'
import type { StreamChunk } from '@/utils/encoding'
import { aiter } from 'iterator-helper'
import { decodeStreamChunk, readerToMessageStream } from '@/utils/encoding'
import { ACCESS_TOKEN, ApiClient } from './index'

export class CoreApiClient extends ApiClient {
  health(): Promise<{
    status: 'healthy'
    agentReady: true
    timestamp: string
  }> {
    return this.instance.get('/health')
  }

  systemInfo(): Promise<{
    version: '4.0.0' | string
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
    return this.instance('/system/config')
  }

  setSystemConfig(config: Config): Promise<{
    status: 'success'
    message: string
  }> {
    return this.instance.post('/system/config', config)
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
      body: JSON.stringify({ message, ...options }),
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
    }>
    totalSessions: number
  }> {
    return this.instance.get('/sessions')
  }

  getSessionDetail(id: string): Promise<{
    status: string
    sessionId: string
    messages: Array<{ role: string; content: string }>
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

  getToolStatus(): Promise<{ message: string; visible: boolean }> {
    return this.instance.get('/tool_status')
  }

  getClawdbotReplies(): Promise<{ replies: string[] }> {
    return this.instance.get('/clawdbot/replies')
  }

  uploadDocument(file: File, description?: string) {
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

  getMemoryStats() {
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
    status: string
    openclaw: {
      found: boolean
      version: string | null
      skillsDir: string
      configPath: string
      skillsError: string | null
    }
    items: Array<{
      id: string
      title: string
      description: string
      skillName: string
      installed: boolean
      enabled: boolean
      installType: string
    }>
  }> {
    return this.instance.get('/openclaw/market/items')
  }

  installMarketItem(itemId: string, payload?: Record<string, any>): Promise<{
    status: string
    message: string
    item: Record<string, any>
  }> {
    return this.instance.post(`/openclaw/market/items/${itemId}/install`, payload ?? {})
  }

  getMcpStatus(): Promise<{
    server: string
    timestamp: string
    tasks: { total: number; active: number; completed: number; failed: number }
    scheduler?: Record<string, any>
  }> {
    return this.instance.get('/mcp/status')
  }

  getContextStats(days: number = 7) {
    return this.instance.get(`/logs/context/statistics?days=${days}`)
  }

  loadContext(days: number = 3) {
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
}

export default new CoreApiClient(8000)
