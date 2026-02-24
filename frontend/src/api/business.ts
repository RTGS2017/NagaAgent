import axios from 'axios'
import camelcaseKeys from 'camelcase-keys'
import { ACCESS_TOKEN } from './index'

const businessClient = axios.create({
  baseURL: 'http://62.234.131.204:30031',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
  transformResponse: [(data: string) => {
    try {
      return camelcaseKeys(JSON.parse(data), { deep: true })
    }
    catch { return data }
  }],
})

businessClient.interceptors.request.use((config) => {
  if (ACCESS_TOKEN.value) {
    config.headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`
  }
  return config
})

// ── 积分 ──

export function getCredits(): Promise<{
  creditsTotal: string
  creditsUsed: string
  creditsFrozen: string
  creditsAvailable: string
  dailyRequests: number
  planId: number
}> {
  return businessClient.get('/api/quota/credits').then(r => r.data)
}

export function redeemCode(code: string): Promise<{
  message: string
  creditsAdded: string
  creditsAvailable: string
}> {
  return businessClient.post('/api/quota/redeem', { code }).then(r => r.data)
}

export function getCreditsLogs(page = 1, perPage = 20): Promise<{
  logs: Array<{
    id: number
    userId: string
    changeType: string
    creditsChange: string
    creditsBefore: string
    creditsAfter: string
    reason: string | null
    operatorId: string | null
    createdAt: string
  }>
  total: number
  page: number
  pages: number
}> {
  return businessClient.get('/api/quota/credits/logs', { params: { page, per_page: perPage } }).then(r => r.data)
}

export function getQuotaMe(): Promise<{
  planName: string
  planId: number
  creditsTotal: string
  creditsUsed: string
  creditsFrozen: string
  creditsAvailable: string
  dailyRequestsUsed: number
  dailyRequestsLimit: number
  monthlyRequestsUsed: number
  monthlyRequestsLimit: number
  allowedModels: string[]
  expiresAt: string | null
}> {
  return businessClient.get('/api/quota/me').then(r => r.data)
}

// ── 熟悉度 ──

export function getAffinity(): Promise<{
  level: number
  affinityPoints: string
  peakAffinityPoints: string
  nextLevel: number | null
  pointsNeeded: string | null
  progressPct: number
  streakDays: number
  recoveryMode: boolean
  lastCheckinDate: string
  lastActiveDate: string
}> {
  return businessClient.get('/api/affinity/me').then(r => r.data)
}

export function checkIn(): Promise<{
  alreadyCheckedIn: boolean
  affinityEarned: string
  creditsEarned: number
  streakDays: number
  bonusType: string | null
  bonusCredits: number
  recoveryMode: boolean
}> {
  return businessClient.post('/api/affinity/check-in').then(r => r.data)
}

export function getCheckInStatus(): Promise<{
  checkedInToday: boolean
  streakDays: number
  lastCheckinDate: string
}> {
  return businessClient.get('/api/affinity/check-in/status').then(r => r.data)
}

export function getAffinityTasks(): Promise<Array<{
  id: string
  title: string
  description: string
  affinityReward: string
  completed: boolean
}>> {
  return businessClient.get('/api/affinity/tasks').then(r => r.data)
}

export function completeTask(taskId: string): Promise<{
  alreadyCompleted: boolean
  affinityEarned?: string
  recoveryMode?: boolean
}> {
  return businessClient.post(`/api/affinity/tasks/${taskId}/complete`).then(r => r.data)
}
