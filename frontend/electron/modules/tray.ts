import { Tray, Menu, nativeImage, app } from 'electron'
import { join } from 'path'
import { getMainWindow } from './window'

let tray: Tray | null = null

export function createTray(): Tray {
  // In dev: icon is at project_root/build/icon.png
  // In production: icon is at resources/build/icon.png
  const iconPath = app.isPackaged
    ? join(process.resourcesPath, 'build', 'icon.png')
    : join(app.getAppPath(), 'build', 'icon.png')
  let icon: Electron.NativeImage
  try {
    icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 })
  } catch {
    icon = nativeImage.createEmpty()
  }

  tray = new Tray(icon)
  tray.setToolTip('Naga Agent')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示窗口',
      click: () => {
        const win = getMainWindow()
        if (win) {
          win.show()
          win.focus()
        }
      },
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
    const win = getMainWindow()
    if (win) {
      if (win.isVisible()) {
        win.focus()
      } else {
        win.show()
      }
    }
  })

  return tray
}

export function destroyTray(): void {
  if (tray) {
    tray.destroy()
    tray = null
  }
}
