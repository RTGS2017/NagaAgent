import { join } from 'node:path'
import process from 'node:process'
import { app, Menu, nativeImage, Tray } from 'electron'
import { showMainWindow } from './window'

let tray: Tray | null = null

export function createTray(): Tray {
  const isWin = process.platform === 'win32'
  const baseDir = app.isPackaged ? process.resourcesPath : app.getAppPath()

  let icon: Electron.NativeImage
  try {
    if (isWin) {
      // Windows: 使用多尺寸 .ico（内含 16/24/32/48/64/128/256），
      // 系统根据 DPI 自动选取最佳尺寸，避免手动 resize 导致裁切/失真。
      const icoPath = join(baseDir, 'build', 'icon.ico')
      icon = nativeImage.createFromPath(icoPath)
    }
    else {
      // macOS: 22x22 PNG（Retina 由系统自动 2x）
      const pngPath = join(baseDir, 'build', 'icon.png')
      icon = nativeImage.createFromPath(pngPath)
        .resize({ width: 64, height: 64 })
        .resize({ width: 22, height: 22 })
    }
  }
  catch {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('Naga Agent')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => showMainWindow(),
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.quit()
      },
    },
  ])

  tray.setContextMenu(contextMenu)

  // Click tray icon to show window
  tray.on('click', () => {
    showMainWindow()
  })

  return tray
}

export function destroyTray(): void {
  if (tray) {
    tray.destroy()
    tray = null
  }
}
