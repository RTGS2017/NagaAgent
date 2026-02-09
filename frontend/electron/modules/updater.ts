import pkg from 'electron-updater'
import { BrowserWindow } from 'electron'

const { autoUpdater } = pkg

export function setupAutoUpdater(win: BrowserWindow): void {
  autoUpdater.autoDownload = false
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('update-available', (info) => {
    win.webContents.send('updater:update-available', {
      version: info.version,
      releaseNotes: info.releaseNotes,
    })
  })

  autoUpdater.on('update-not-available', () => {
    win.webContents.send('updater:update-not-available')
  })

  autoUpdater.on('download-progress', (progress) => {
    win.webContents.send('updater:download-progress', {
      percent: progress.percent,
      bytesPerSecond: progress.bytesPerSecond,
    })
  })

  autoUpdater.on('update-downloaded', () => {
    win.webContents.send('updater:update-downloaded')
  })

  autoUpdater.on('error', (err) => {
    win.webContents.send('updater:error', err.message)
  })

  // Check for updates after a short delay
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch(() => {
      // Silently fail if no update server is configured
    })
  }, 3000)
}

export function downloadUpdate(): void {
  autoUpdater.downloadUpdate()
}

export function installUpdate(): void {
  autoUpdater.quitAndInstall()
}
