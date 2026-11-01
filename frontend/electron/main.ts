import { readFileSync } from 'node:fs'
import { readdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import process from 'node:process'
import { domainToUnicode, fileURLToPath, pathToFileURL } from 'node:url'
import { app, BrowserWindow, desktopCapturer, ipcMain, Menu, nativeTheme, net, protocol, shell, systemPreferences } from 'electron'
import { getBackendLogs, startBackend, stopBackend } from './modules/backend'
import { registerHotkeys, unregisterHotkeys } from './modules/hotkeys'
import { createMenu } from './modules/menu'
import { createTray, destroyTray } from './modules/tray'
import { downloadUpdate, installUpdate, setupAutoUpdater } from './modules/updater'
import {
  collapseFloatingWindow,
  collapseFullToCompact,
  createWindow,
  enterFloatingMode,
  exitFloatingMode,
  expandCompactToFull,
  expandFloatingWindow,
  getFloatingState,
  getMainWindow,
  isMainWindowMaximized,
  setFloatingHeight,
  setWindowPosition,
  showMainWindow,
  toggleMainWindowMaximize,
  usesManualMainWindowMaximize,
} from './modules/window'

let isQuitting = false

// 防止 EPIPE 导致 Electron 崩溃（后端进程 stdout 管道断开时会触发）
process.stdout?.on('error', () => {})
process.stderr?.on('error', () => {})

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
}

// ── 自定义协议：naga-char:// 用于加载 characters 目录下的角色资源 ──
// 打包模式：extraResources/characters；开发模式：项目根/characters
const CHARACTERS_DIR = app.isPackaged
  ? resolve(process.resourcesPath, 'characters')
  : resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'characters')
// ── 自定义协议：naga-bg:// 用于加载 premium-assets/backgrounds 目录下的背景图片 ──
const BACKGROUNDS_DIR = app.isPackaged
  ? resolve(process.resourcesPath, 'premium-assets', 'backgrounds')
  : resolve(dirname(fileURLToPath(import.meta.url)), '..', 'premium-assets', 'backgrounds')
protocol.registerSchemesAsPrivileged([
  { scheme: 'naga-char', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
  { scheme: 'naga-bg', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
  { scheme: 'naga-app', privileges: { secure: true, supportFetchAPI: true, corsEnabled: true, standard: true, stream: true } },
])

app.on('second-instance', () => {
  showMainWindow()
})

app.whenReady().then(async () => {
  // MIME 映射（音频/视频等二进制媒体文件需要通过 fs.readFile 读取以兼容 asar）
  const MEDIA_MIME: Record<string, string> = {
    mp3: 'audio/mpeg',
    wav: 'audio/wav',
    ogg: 'audio/ogg',
    m4a: 'audio/mp4',
    flac: 'audio/flac',
    aac: 'audio/aac',
    webm: 'audio/webm',
    mp4: 'video/mp4',
    mkv: 'video/x-matroska',
  }
  const FILE_MIME: Record<string, string> = {
    ...MEDIA_MIME,
    json: 'application/json; charset=utf-8',
    txt: 'text/plain; charset=utf-8',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    moc3: 'application/octet-stream',
  }

  function resolveCustomProtocolPath(requestUrl: string, baseDir: string): string | null {
    try {
      const url = new URL(requestUrl)
      const host = domainToUnicode(url.hostname || '')
      const pathname = decodeURIComponent(url.pathname).replace(/^\/+/, '')
      const relativePath = [host, pathname].filter(Boolean).join('/')
      const filePath = resolve(baseDir, relativePath)
      if (!filePath.startsWith(baseDir)) {
        return null
      }
      return filePath
    }
    catch {
      return null
    }
  }

  function serveLocalFile(filePath: string, notFoundMessage = 'Not Found'): Response {
    try {
      const data = readFileSync(filePath)
      const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
      const mime = FILE_MIME[ext] || 'application/octet-stream'
      return new Response(data, {
        headers: {
          'Content-Type': mime,
          'Content-Length': data.length.toString(),
          'Cache-Control': 'no-cache',
        },
      })
    }
    catch {
      return new Response(notFoundMessage, { status: 404 })
    }
  }

  // naga-app://路径 → 加载 dist/ 目录文件
  // 仅打包模式生效，开发模式走 Vite dev server
  const appDistDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'dist')
  protocol.handle('naga-app', (request) => {
    const rawPath = decodeURIComponent(new URL(request.url).pathname).replace(/^\/+/, '')
    const relativePath = rawPath.startsWith('dist/') ? rawPath.slice(5) : rawPath

    const basePath = resolve(appDistDir, relativePath)
    if (!basePath.startsWith(appDistDir)) {
      return new Response('Forbidden', { status: 403 })
    }

    // 音频/视频文件通过 fs.readFileSync 读取（Node fs 天然兼容 asar），
    // 避免 net.fetch(file://) 在 asar 内对媒体文件不兼容的问题。
    // 注意：此处使用 readFileSync 而非 async readFile，因为构建工具（Rollup/Rolldown）
    // 的 tree-shaking 会将 async handler 中的 await readFile 分支整体移除，
    // 导致打包后音频无 Content-Type/Content-Length 头，播放约 6 秒后卡死。
    const ext = basePath.split('.').pop()?.toLowerCase() ?? ''
    const mime = MEDIA_MIME[ext]
    if (mime) {
      try {
        const data = readFileSync(basePath)
        return new Response(data, {
          headers: { 'Content-Type': mime, 'Content-Length': data.length.toString() },
        })
      }
      catch {
        return new Response('Not Found', { status: 404 })
      }
    }

    return net.fetch(pathToFileURL(basePath).toString())
  })

  // naga-char://角色名/文件名 → characters/角色名/文件名
  protocol.handle('naga-char', (request) => {
    const filePath = resolveCustomProtocolPath(request.url, CHARACTERS_DIR)
    if (!filePath) {
      return new Response('Forbidden', { status: 403 })
    }
    return serveLocalFile(filePath, 'Character Asset Not Found')
  })

  // naga-bg://文件名 → premium-assets/backgrounds/文件名
  protocol.handle('naga-bg', (request) => {
    const filePath = resolveCustomProtocolPath(request.url, BACKGROUNDS_DIR)
    if (!filePath) {
      return new Response('Forbidden', { status: 403 })
    }
    return serveLocalFile(filePath, 'Background Asset Not Found')
  })

  // 强制暗色主题（确保原生菜单等 UI 为深色）
  nativeTheme.themeSource = 'dark'

  // Create menu
  createMenu()

  // Create main window
  const win = createWindow()

  // Create system tray
  createTray()

  // Register global hotkeys
  registerHotkeys()

  // Setup auto-updater (checks GitHub Releases for new versions)
  void setupAutoUpdater(win)

  // --- IPC Handlers ---

  // Window controls
  ipcMain.on('window:minimize', () => getMainWindow()?.minimize())
  ipcMain.on('window:maximize', () => toggleMainWindowMaximize())
  ipcMain.on('window:close', () => {
    const state = getFloatingState()
    if (state === 'compact' || state === 'full') {
      // 悬浮球展开态：收起为球态
      collapseFloatingWindow()
    }
    else if (state === 'classic') {
      // 经典模式：关闭窗口 → 自动进入悬浮球
      enterFloatingMode()
    }
    else {
      // 已经是球态，隐藏到托盘
      getMainWindow()?.hide()
    }
  })

  ipcMain.handle('window:isMaximized', () => isMainWindowMaximized())
  ipcMain.handle('window:getBounds', () => getMainWindow()?.getBounds() ?? { x: 0, y: 0, width: 1280, height: 800 })
  ipcMain.on('window:setBounds', (_event, bounds: { x?: number, y?: number, width?: number, height?: number }) => {
    const win = getMainWindow()
    if (!win || isMainWindowMaximized())
      return
    const current = win.getBounds()
    const next = {
      x: bounds.x ?? current.x,
      y: bounds.y ?? current.y,
      width: Math.max(800, bounds.width ?? current.width),
      height: Math.max(600, bounds.height ?? current.height),
    }
    win.setBounds(next)
  })

  // 悬浮球模式控制
  ipcMain.handle('floating:enter', () => {
    enterFloatingMode()
  })
  ipcMain.handle('floating:exit', () => {
    exitFloatingMode()
  })
  ipcMain.handle('floating:expand', (_event, toFull?: boolean) => {
    expandFloatingWindow(toFull ?? false)
  })
  ipcMain.handle('floating:expandToFull', () => {
    expandCompactToFull()
  })
  ipcMain.handle('floating:collapse', () => {
    collapseFloatingWindow()
  })
  ipcMain.handle('floating:collapseToCompact', () => {
    collapseFullToCompact()
  })
  ipcMain.handle('floating:getState', () => getFloatingState())
  ipcMain.on('floating:pin', (_event, pinned: boolean) => {
    const w = getMainWindow()
    if (w) {
      // 固定时显示任务栏图标，取消固定时隐藏（悬浮球模式下 alwaysOnTop 始终为 true）
      w.setSkipTaskbar(!pinned)
    }
  })
  ipcMain.on('floating:setPosition', (_event, x: number, y: number) => {
    setWindowPosition(x, y)
  })
  ipcMain.on('floating:fitHeight', (_event, height: number) => {
    setFloatingHeight(height)
  })

  // Update controls
  ipcMain.on('updater:download', () => downloadUpdate())
  ipcMain.on('updater:install', () => installUpdate())

  // App quit
  ipcMain.on('app:quit', () => {
    isQuitting = true
    app.quit()
  })

  // 悬浮球右键菜单
  ipcMain.on('context-menu:show', () => {
    const menu = Menu.buildFromTemplate([
      {
        label: '打开主界面',
        click: () => exitFloatingMode(),
      },
      {
        label: '隐藏到托盘',
        click: () => getMainWindow()?.hide(),
      },
      { type: 'separator' },
      {
        label: '退出应用',
        click: () => {
          isQuitting = true
          app.quit()
        },
      },
    ])
    menu.popup()
  })

  // 窗口截屏功能
  ipcMain.handle('capture:getSources', async () => {
    // macOS 需要屏幕录制权限
    if (process.platform === 'darwin') {
      const status = systemPreferences.getMediaAccessStatus('screen')
      if (status !== 'granted') {
        return { permission: status }
      }
    }

    try {
      const sources = await desktopCapturer.getSources({
        types: ['window', 'screen'],
        thumbnailSize: { width: 320, height: 180 },
        fetchWindowIcons: true,
      })
      return sources.map(s => ({
        id: s.id,
        name: s.name,
        thumbnail: s.thumbnail.toDataURL(),
        appIcon: s.appIcon?.toDataURL() || null,
      }))
    }
    catch {
      // desktopCapturer 可能因权限问题抛出异常
      return { permission: 'denied' }
    }
  })

  ipcMain.handle('capture:captureWindow', async (_event, sourceId: string) => {
    const sources = await desktopCapturer.getSources({
      types: ['window', 'screen'],
      thumbnailSize: { width: 1920, height: 1080 },
    })
    const target = sources.find(s => s.id === sourceId)
    if (!target)
      return null
    return target.thumbnail.toDataURL()
  })

  // 打开 macOS 屏幕录制权限设置
  ipcMain.handle('capture:openScreenSettings', async () => {
    if (process.platform === 'darwin') {
      await shell.openExternal('x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture')
    }
  })

  // 扫描背景图片文件夹
  ipcMain.handle('backgrounds:scan', async () => {
    try {
      const files = await readdir(BACKGROUNDS_DIR)
      const imageExts = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif']
      return files.filter(f => imageExts.some(ext => f.toLowerCase().endsWith(ext)))
    }
    catch {
      return []
    }
  })

  // 开机自启动
  ipcMain.handle('autoLaunch:get', () => {
    return app.getLoginItemSettings().openAtLogin
  })
  ipcMain.handle('autoLaunch:set', (_event, enabled: boolean) => {
    app.setLoginItemSettings({ openAtLogin: enabled })
  })
  ipcMain.handle('backend:getLogs', () => getBackendLogs())

  // Minimize to tray on close instead of quitting
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault()
      win.hide()
    }
  })

  win.on('maximize', () => {
    if (!usesManualMainWindowMaximize())
      win.webContents.send('window:maximized', true)
  })
  win.on('unmaximize', () => {
    if (!usesManualMainWindowMaximize())
      win.webContents.send('window:maximized', false)
  })

  // 悬浮球展开态失焦时自动收起（由渲染进程控制是否启用）
  win.on('blur', () => {
    win.webContents.send('floating:windowBlur')
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
    else {
      showMainWindow()
    }
  })

  // Start backend services
  startBackend()
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
