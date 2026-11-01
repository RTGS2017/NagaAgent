import { globalShortcut } from 'electron'
import { collapseFloatingWindow, expandFloatingWindow, getFloatingState, getMainWindow, showMainWindow } from './window'

export function registerHotkeys(): void {
  // Ctrl+Shift+N (Cmd+Shift+N on macOS) toggles window visibility
  globalShortcut.register('CommandOrControl+Shift+N', () => {
    const win = getMainWindow()
    if (!win)
      return

    const state = getFloatingState()

    if (state === 'classic') {
      // 经典模式：切换显示/隐藏
      if (win.isVisible()) {
        win.hide()
      }
      else {
        showMainWindow()
      }
    }
    else if (state === 'ball') {
      // 球态：如果可见则展开，如果隐藏则显示
      if (win.isVisible()) {
        expandFloatingWindow()
        win.focus()
      }
      else {
        showMainWindow()
      }
    }
    else if (state === 'compact' || state === 'full') {
      // 紧凑态/完整态：收起为球态
      collapseFloatingWindow()
    }
  })
}

export function unregisterHotkeys(): void {
  globalShortcut.unregisterAll()
}
