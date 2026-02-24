import { computed, ref, watch } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import { getAffinity, getCredits } from '@/api/business'
import coreApi from '@/api/core'
import { backendConnected, CONFIG } from '@/utils/config'

export const nagaUser = ref<{ username: string, sub?: string, points?: number, affinity?: number, affinityLevel?: number } | null>(null)
export const isNagaLoggedIn = computed(() => !!nagaUser.value)
export const sessionRestored = ref(false)

// 防止多个组件调用 useAuth() 时重复 fetchMe
let _initFetched = false

/**
 * 同步 memory_server 配置：登录时设置 token/url，登出时清除
 */
function syncMemoryServer(loggedIn: boolean, memoryUrl?: string) {
  CONFIG.value.memory_server.token = loggedIn ? ACCESS_TOKEN.value : null
  if (loggedIn && memoryUrl) {
    CONFIG.value.memory_server.url = memoryUrl
  }
}

/**
 * 同步游戏攻略开关：仅登录态可用
 */
function syncGameEnabled(loggedIn: boolean) {
  CONFIG.value.game.enabled = loggedIn
}

/**
 * 拉取积分 + 熟悉度，更新 nagaUser
 */
async function fetchUserStats() {
  if (!ACCESS_TOKEN.value || !nagaUser.value)
    return
  try {
    const [credits, affinity] = await Promise.all([
      getCredits().catch(() => null),
      getAffinity().catch(() => null),
    ])
    if (!nagaUser.value)
      return
    if (credits)
      nagaUser.value.points = Number.parseFloat(credits.creditsAvailable) || 0
    if (affinity) {
      nagaUser.value.affinity = Number.parseFloat(affinity.affinityPoints) || 0
      nagaUser.value.affinityLevel = affinity.level ?? 0
    }
  }
  catch { /* 静默失败，不影响主流程 */ }
}

/** 供外部（如签到后）手动刷新 */
export const refreshUserStats = fetchUserStats

// Token 刷新时自动同步到 memory_server.token
watch(ACCESS_TOKEN, (newToken) => {
  if (nagaUser.value) {
    CONFIG.value.memory_server.token = newToken || null
  }
})

export function useAuth() {
  async function login(username: string, password: string, captchaId?: string, captchaAnswer?: string) {
    const res = await coreApi.authLogin(username, password, captchaId, captchaAnswer)
    if (res.success) {
      ACCESS_TOKEN.value = res.accessToken
      // refresh_token 由后端管理，前端不再存储
      nagaUser.value = res.user
      syncMemoryServer(true, res.memoryUrl)
      syncGameEnabled(true)
      fetchUserStats()
    }
    return res
  }

  async function register(username: string, email: string, password: string, verificationCode: string) {
    const res = await coreApi.authRegister(username, email, password, verificationCode)
    if (res.success && res.accessToken) {
      ACCESS_TOKEN.value = res.accessToken
      nagaUser.value = res.user || null
      syncMemoryServer(true)
      syncGameEnabled(true)
      fetchUserStats()
    }
    return res
  }

  async function sendVerification(email: string, username: string, captchaId?: string, captchaAnswer?: string) {
    return await coreApi.authSendVerification(email, username, captchaId, captchaAnswer)
  }

  async function getCaptcha() {
    return await coreApi.authGetCaptcha()
  }

  async function fetchMe() {
    try {
      const res = await coreApi.authMe()
      if (res.user) {
        nagaUser.value = res.user
        sessionRestored.value = true
        syncMemoryServer(true, res.memoryUrl)
        syncGameEnabled(true)
        fetchUserStats()

        // 防止 fetchMe 在 connectBackend 之前完成导致 CONFIG 被覆盖
        if (!backendConnected.value) {
          const stop = watch(backendConnected, (connected) => {
            if (connected) {
              syncMemoryServer(true, res.memoryUrl)
              syncGameEnabled(true)
              stop()
            }
          })
        }
      }
    }
    catch {
      nagaUser.value = null
    }
  }

  async function logout() {
    try {
      await coreApi.authLogout()
    }
    finally {
      ACCESS_TOKEN.value = ''
      nagaUser.value = null
      syncMemoryServer(false)
      syncGameEnabled(false)
    }
  }

  function skipLogin() {
    nagaUser.value = null
  }

  // 首次调用时自动恢复会话（仅在有 token 时才请求，避免无谓的 401）
  // 等后端就绪后再请求，避免后端还没启动就 fetchMe 失败导致登录态丢失
  if (!_initFetched) {
    _initFetched = true
    if (ACCESS_TOKEN.value) {
      if (backendConnected.value) {
        fetchMe()
      }
      else {
        const stop = watch(backendConnected, (connected) => {
          if (connected) {
            fetchMe()
            stop()
          }
        })
      }
    }
  }

  return { login, register, sendVerification, getCaptcha, fetchMe, logout, skipLogin, refreshUserStats }
}
