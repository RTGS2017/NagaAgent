import { ref } from 'vue'
import API from '@/api/core'
import { CONFIG } from '@/utils/config'

export interface UpdateInfo {
  hasUpdate: boolean
  latestVersion: string
  description: string
  forceUpdate: boolean
  /** null 表示当前平台无可用资源 */
  downloadUrl: string | null
  fileSize: number | null
}

function detectPlatform(): string {
  const p = window.electronAPI?.platform
  if (p === 'darwin')
    return 'macos'
  if (p === 'win32')
    return 'windows'
  if (p === 'linux')
    return 'linux'
  // web 环境做粗略猜测
  const ua = navigator.userAgent.toLowerCase()
  if (ua.includes('mac'))
    return 'macos'
  if (ua.includes('win'))
    return 'windows'
  return 'linux'
}

export const updateInfo = ref<UpdateInfo | null>(null)
export const showUpdateDialog = ref(false)

export async function checkForUpdate(): Promise<void> {
  try {
    const platform = detectPlatform()
    const res = await fetch(`${API.endpoint}/update/latest?platform=${platform}`, {
      signal: AbortSignal.timeout(10_000),
    })

    if (!res.ok)
      return

    const data = await res.json() as {
      version?: string
      description?: string
      force_update?: boolean
      download_url?: string | null
      file_size?: number | null
      has_update?: boolean
    }

    if (!data.version || data.has_update === false)
      return

    const currentVersion = CONFIG.value.system.version ?? '5.1.0'
    if (data.version === currentVersion)
      return

    updateInfo.value = {
      hasUpdate: true,
      latestVersion: data.version,
      description: data.description ?? '',
      forceUpdate: data.force_update ?? false,
      downloadUrl: data.download_url ?? null,
      fileSize: data.file_size ?? null,
    }
    showUpdateDialog.value = true
  }
  catch (err) {
    console.warn('[VersionCheck] Failed to check for updates:', err)
  }
}

export function dismissUpdate(): void {
  showUpdateDialog.value = false
}

export function openDownloadUrl(url: string): void {
  window.open(url, '_blank')
}
