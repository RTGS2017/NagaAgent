export interface ElectronAPI {
  minimize: () => void
  maximize: () => void
  close: () => void
  isMaximized: () => Promise<boolean>
  onMaximized: (callback: (maximized: boolean) => void) => () => void
  downloadUpdate: () => void
  installUpdate: () => void
  onUpdateAvailable: (callback: (info: { version: string; releaseNotes: string }) => void) => () => void
  onUpdateDownloaded: (callback: () => void) => () => void
  platform: string
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}

export {}
