import { ref, onMounted, onUnmounted } from 'vue'

export function useElectron() {
  const isElectron = ref(!!window.electronAPI)
  const isMaximized = ref(false)
  const isMac = ref(window.electronAPI?.platform === 'darwin')

  let cleanupMaximized: (() => void) | undefined

  onMounted(async () => {
    if (!window.electronAPI) return

    isMaximized.value = await window.electronAPI.isMaximized()

    cleanupMaximized = window.electronAPI.onMaximized((maximized) => {
      isMaximized.value = maximized
    })
  })

  onUnmounted(() => {
    cleanupMaximized?.()
  })

  function minimize() {
    window.electronAPI?.minimize()
  }

  function maximize() {
    window.electronAPI?.maximize()
  }

  function close() {
    window.electronAPI?.close()
  }

  return {
    isElectron,
    isMaximized,
    isMac,
    minimize,
    maximize,
    close,
  }
}
