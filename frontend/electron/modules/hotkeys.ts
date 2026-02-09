import { globalShortcut } from 'electron'
import { getMainWindow } from './window'

export function registerHotkeys(): void {
  // Ctrl+Shift+N (Cmd+Shift+N on macOS) toggles window visibility
  globalShortcut.register('CommandOrControl+Shift+N', () => {
    const win = getMainWindow()
    if (!win) return

    if (win.isVisible()) {
      win.hide()
    } else {
      win.show()
      win.focus()
    }
  })
}

export function unregisterHotkeys(): void {
  globalShortcut.unregisterAll()
}
