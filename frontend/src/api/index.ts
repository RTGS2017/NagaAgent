import type { AxiosError, AxiosInstance } from 'axios'
import type { MaybeRef } from 'vue'
import { useStorage } from '@vueuse/core'
import axios from 'axios'
import camelcaseKeys from 'camelcase-keys'
import snakecaseKeys from 'snakecase-keys'
import { ref, unref, watch } from 'vue'

export const ACCESS_TOKEN = useStorage('naga-access-token', '')

/** 当 CAS 会话失效（refresh 也失败）时触发，由 App.vue 监听弹窗 */
export const authExpired = ref(false)

/** 重新登录期间抑制 authExpired 触发（避免清空 token 后在途请求再次触发弹窗） */
// eslint-disable-next-line import/no-mutable-exports
export let suppressAuthExpired = false
export function setAuthExpiredSuppressed(value: boolean) {
  suppressAuthExpired = value
}

let isRefreshing = false
let refreshSubscribers: Array<(newToken: string) => void> = []

export class ApiClient {
  instance: AxiosInstance

  get endpoint() {
    return `http://localhost:${unref(this.port)}`
  }

  constructor(readonly port: MaybeRef<number>) {
    this.instance = axios.create({
      baseURL: this.endpoint,
      timeout: 30 * 1000,
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
      transformResponse(data) {
        return camelcaseKeys(JSON.parse(data), { deep: true })
      },
    })

    watch(() => this.endpoint, (endpoint) => {
      this.instance.defaults.baseURL = endpoint
    })

    this.instance.interceptors.request.use((config) => {
      if (ACCESS_TOKEN.value) {
        config.headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`
      }
      return config
    })

    this.instance.interceptors.response.use(
      response => response.data,
      this.handleResponseError.bind(this),
    )
  }

  private async handleResponseError(error: AxiosError & { config: { _retry?: boolean } }): Promise<any> {
    if (!error.config) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401 && !error.config._retry) {
      if (error.config.url?.includes('/auth/refresh')) {
        this.clearAuthDataAndRedirect()
        return Promise.reject(error)
      }

      if (error.config.url?.includes('/auth/login')) {
        return Promise.reject(error)
      }

      if (isRefreshing) {
        return new Promise((resolve) => {
          refreshSubscribers.push((newToken: string) => {
            error.config.headers.Authorization = `Bearer ${newToken}`
            resolve(this.instance(error.config))
          })
        })
      }

      error.config._retry = true
      isRefreshing = true

      // 未登录时（无 access_token）不尝试刷新
      if (!ACCESS_TOKEN.value) {
        isRefreshing = false
        if (error.config.url?.includes('/auth/me')) {
          return Promise.reject(error)
        }
        this.clearAuthDataAndRedirect()
        return Promise.reject(new Error('Not authenticated'))
      }

      try {
        // refresh_token 由后端管理，前端只需发空请求
        // 迁移兼容：如果旧版 localStorage 中有 refresh_token，作为 fallback 发给后端
        const legacyToken = localStorage.getItem('naga-refresh-token')
        const refreshBody = legacyToken ? { refresh_token: legacyToken } : {}
        const response = await axios.post<{
          access_token: string
        }>(`${this.endpoint}/auth/refresh`, refreshBody)
        const { access_token } = response.data

        ACCESS_TOKEN.value = access_token
        // 刷新成功后清理旧 localStorage key（后端已持久化 refresh_token）
        localStorage.removeItem('naga-refresh-token')

        isRefreshing = false
        refreshSubscribers.forEach(callback => callback(access_token))
        refreshSubscribers = []

        error.config.headers.Authorization = `Bearer ${access_token}`
        return this.instance(error.config)
      }
      catch (refreshError) {
        isRefreshing = false
        refreshSubscribers.forEach(callback => callback(''))
        refreshSubscribers = []
        this.clearAuthDataAndRedirect()
        return Promise.reject(refreshError)
      }
    }

    console.error('API Error:', error)
    return Promise.reject(error)
  }

  private clearAuthDataAndRedirect(): void {
    // 重新登录期间不触发（避免清空 token 后在途请求的 401 再次弹窗）
    if (!authExpired.value && !suppressAuthExpired) {
      authExpired.value = true
    }
  }
}
