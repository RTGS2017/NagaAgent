import { app, BrowserWindow, ipcMain } from 'electron'
import { createWindow, getMainWindow } from './modules/window'
import { createTray, destroyTray } from './modules/tray'
import { createMenu } from './modules/menu'
import { registerHotkeys, unregisterHotkeys } from './modules/hotkeys'
import { setupAutoUpdater, downloadUpdate, installUpdate } from './modules/updater'
import { startBackend, stopBackend } from './modules/backend'

let isQuitting = false

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
}

app.on('second-instance', () => {
  const win = getMainWindow()
  if (win) {
    if (win.isMinimized()) win.restore()
    win.show()
    win.focus()
  }
})

app.whenReady().then(() => {
  // Start backend services
  startBackend()

  // Create menu
  createMenu()

  // Create main window
  const win = createWindow()

  // Create system tray
  createTray()

  // Register global hotkeys
  registerHotkeys()

  // Setup auto-updater
  setupAutoUpdater(win)

  // --- IPC Handlers ---

  // Window controls
  ipcMain.on('window:minimize', () => getMainWindow()?.minimize())
  ipcMain.on('window:maximize', () => {
    const w = getMainWindow()
    if (w) {
      w.isMaximized() ? w.unmaximize() : w.maximize()
    }
  })
  ipcMain.on('window:close', () => getMainWindow()?.hide())

  ipcMain.handle('window:isMaximized', () => getMainWindow()?.isMaximized() ?? false)

  // Update controls
  ipcMain.on('updater:download', () => downloadUpdate())
  ipcMain.on('updater:install', () => installUpdate())

  // Minimize to tray on close instead of quitting
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      win.hide()
    }
  })

  win.on('maximize', () => win.webContents.send('window:maximized', true))
  win.on('unmaximize', () => win.webContents.send('window:maximized', false))

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    } else {
      getMainWindow()?.show()
    }
  })
})

app.on('before-quit', () => {
  isQuitting = true
})

app.on('will-quit', () => {
  unregisterHotkeys()
  destroyTray()
  stopBackend()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
