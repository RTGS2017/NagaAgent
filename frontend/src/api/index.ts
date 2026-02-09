import type { AxiosError, AxiosInstance } from 'axios'
import type { MaybeRef } from 'vue'
import { useStorage } from '@vueuse/core'
import axios from 'axios'
import camelcaseKeys from 'camelcase-keys'
import snakecaseKeys from 'snakecase-keys'
import { unref, watch } from 'vue'

export const ACCESS_TOKEN = useStorage('naga-access-token', '')
export const REFRESH_TOKEN = useStorage('naga-refresh-token', '')

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
      timeout: 10 * 1000,
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
      if (!REFRESH_TOKEN.value) {
        isRefreshing = false
        this.clearAuthDataAndRedirect()
        return Promise.reject(new Error('No refresh token available'))
      }

      try {
        const response = await axios.post<{
          access_token: string
          refresh_token: string
        }>(`${this.endpoint}/auth/refresh`, {
          refresh_token: REFRESH_TOKEN.value,
        })
        const { access_token, refresh_token } = response.data

        ACCESS_TOKEN.value = access_token
        REFRESH_TOKEN.value = refresh_token

        isRefreshing = false
        refreshSubscribers.forEach(callback => callback(access_token))
        refreshSubscribers = []

        error.config.headers.Authorization = `Bearer ${access_token}`
        return this.instance(error.config)
      }
      catch (refreshError) {
        isRefreshing = false
        this.clearAuthDataAndRedirect()
        return Promise.reject(refreshError)
      }
    }

    console.error('API Error:', error)
    return Promise.reject(error)
  }

  private clearAuthDataAndRedirect(): void {
    ACCESS_TOKEN.value = undefined
    REFRESH_TOKEN.value = undefined
    window.location.href = '/login'
  }
}
