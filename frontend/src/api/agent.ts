import { ApiClient } from './index'

export class AgentApiClient extends ApiClient {
  getTools(): Promise<{
    success: boolean
    tools: Array<{
      name: string
      description: string
      toolkit: string
      inputSchema?: Record<string, any>
    }>
    count: number
  }> {
    return this.instance.get('/tools')
  }

  getToolkits(): Promise<{
    success: boolean
    toolkits: string[]
    count: number
  }> {
    return this.instance.get('/toolkits')
  }

  getToolkitDetail(name: string) {
    return this.instance.get(`/toolkits/${name}`)
  }

  getSessions(): Promise<{
    success: boolean
    sessions: Array<Record<string, any>>
    totalSessions: number
  }> {
    return this.instance.get('/sessions')
  }

  getSessionMemory(sessionId: string) {
    return this.instance.get(`/sessions/${sessionId}/memory`)
  }

  getSessionKeyFacts(sessionId: string): Promise<{
    success: boolean
    sessionId: string
    keyFacts: Record<string, string>
    count: number
  }> {
    return this.instance.get(`/sessions/${sessionId}/key_facts`)
  }
}

export default new AgentApiClient(8001)
