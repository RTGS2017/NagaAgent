import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { app, BrowserWindow, screen, shell } from 'electron'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

let mainWindow: BrowserWindow | null = null

// 悬浮球模式状态
export type FloatingState = 'classic' | 'ball' | 'compact' | 'full'
let floatingState: FloatingState = 'classic'
let classicBounds: Electron.Rectangle | null = null // 经典模式下记住窗口位置
let ballPosition: { x: number, y: number } | null = null // 球态位置

// 悬浮球默认尺寸配置
const BALL_SIZE = 100
const EXPANDED_WIDTH = 420
const MAX_FULL_HEIGHT = 640
const INITIAL_FULL_HEIGHT = 200 // 展开到完整态时的初始动画目标高度
const MIN_FIT_HEIGHT = BALL_SIZE // fitHeight 允许收缩到的最小高度（无消息时仅头部）
const COMPACT_HEIGHT = BALL_SIZE // 与球态同高，展开时仅宽度变化

// 窗口渐变动画参数
const ANIM_DURATION_MS = 160
const ANIM_FPS = 60
const ANIM_FRAMES = Math.round(ANIM_DURATION_MS / (1000 / ANIM_FPS))

// 当前动画取消句柄，防止并发动画竞争
let cancelCurrentAnimation: (() => void) | null = null

/**
 * 分步动画过渡窗口尺寸和位置
 * 自动取消上一个未完成的动画，避免并发竞争
 */
function animateBounds(
  win: BrowserWindow,
  from: Electron.Rectangle,
  to: Electron.Rectangle,
  onDone?: () => void,
): void {
  // 取消上一个动画
  cancelCurrentAnimation?.()

  let frame = 0
  const interval = setInterval(() => {
    frame++
    // easeOutCubic: 快起慢停
    const t = frame / ANIM_FRAMES
    const ease = 1 - (1 - t) ** 3

    const x = Math.round(from.x + (to.x - from.x) * ease)
    const y = Math.round(from.y + (to.y - from.y) * ease)
    const w = Math.round(from.width + (to.width - from.width) * ease)
    const h = Math.round(from.height + (to.height - from.height) * ease)

    win.setBounds({ x, y, width: w, height: h })

    if (frame >= ANIM_FRAMES) {
      clearInterval(interval)
      cancelCurrentAnimation = null
      win.setBounds(to)
      onDone?.()
    }
  }, 1000 / ANIM_FPS)

  cancelCurrentAnimation = () => {
    clearInterval(interval)
    cancelCurrentAnimation = null
  }
}

/**
 * 根据球的位置计算面板展开的位置
 * 水平方向：始终从球位置向右展开（球在面板左侧），超出屏幕时左移面板
 * 垂直方向：面板顶部与球顶部对齐，空间不足时上移面板
 */
function calcExpandPosition(ballX: number, ballY: number, targetHeight: number): { x: number, y: number } {
  const display = screen.getPrimaryDisplay()
  const { width: screenW, height: screenH } = display.workAreaSize

  // 水平方向：球在面板左边缘
  let expandX = ballX
  if (expandX + EXPANDED_WIDTH > screenW)
    expandX = screenW - EXPANDED_WIDTH
  if (expandX < 0)
    expandX = 0

  // 垂直方向：面板顶部与球顶部对齐，空间不足时上移
  let expandY = ballY
  if (expandY + targetHeight > screenH)
    expandY = screenH - targetHeight
  if (expandY < 0)
    expandY = 0

  return { x: expandX, y: expandY }
}

export function createWindow(): BrowserWindow {
  // Windows: 使用 .ico 确保任务栏图标清晰
  const isWin = process.platform === 'win32'
  const baseDir = app.isPackaged ? process.resourcesPath : app.getAppPath()
  const iconFile = isWin ? 'icon.ico' : 'icon.png'
  const iconPath = join(baseDir, 'build', iconFile)

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    resizable: true,
    hasShadow: true,
    transparent: true,
    show: false,
    icon: iconPath,
    webPreferences: {
      preload: join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      webgl: true,
    },
  })

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show()
  })

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // Load the app
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
  }
  else {
    // 打包模式：通过 naga-app:// 协议加载，支持热补丁覆盖
    mainWindow.loadURL('naga-app://dist/index.html')
  }

  return mainWindow
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

export function getFloatingState(): FloatingState {
  return floatingState
}

/**
 * 进入悬浮球模式：将窗口缩小为球态
 */
export function enterFloatingMode(): void {
  const win = mainWindow
  if (!win)
    return

  // 记住经典模式的窗口位置
  classicBounds = win.getBounds()
  floatingState = 'ball'

  // 计算球态初始位置（屏幕右下角偏移）
  if (!ballPosition) {
    const display = screen.getPrimaryDisplay()
    const { width, height } = display.workAreaSize
    ballPosition = {
      x: width - BALL_SIZE - 40,
      y: height - BALL_SIZE - 40,
    }
  }

  win.setAlwaysOnTop(true, 'modal-panel')
  win.setSkipTaskbar(true)
  win.setResizable(false)
  win.setHasShadow(false)
  win.setMinimumSize(BALL_SIZE, BALL_SIZE)
  win.setBounds({
    x: ballPosition.x,
    y: ballPosition.y,
    width: BALL_SIZE,
    height: BALL_SIZE,
  })

  win.webContents.send('floating:stateChanged', floatingState)
}

/**
 * 退出悬浮球模式：恢复经典窗口
 */
export function exitFloatingMode(): void {
  const win = mainWindow
  if (!win)
    return

  floatingState = 'classic'

  win.setAlwaysOnTop(false)
  win.setSkipTaskbar(false)
  win.setResizable(true)
  win.setHasShadow(true)
  win.setMinimumSize(800, 600)

  if (classicBounds) {
    win.setBounds(classicBounds)
  }
  else {
    win.setBounds({ width: 1280, height: 800 })
    win.center()
  }

  win.webContents.send('floating:stateChanged', floatingState)
}

/**
 * 球态 -> 紧凑态或完整态（带动画）
 * toFull=true 时直接展开到完整尺寸（有消息历史时），否则展开到紧凑尺寸
 * 始终从球位置向右展开，球保持在面板左侧
 */
export function expandFloatingWindow(toFull: boolean = false): void {
  const win = mainWindow
  if (!win || floatingState !== 'ball')
    return

  // 记住球的位置
  const fromBounds = win.getBounds()
  ballPosition = { x: fromBounds.x, y: fromBounds.y }

  // 完整态先展开到最小高度，由渲染进程通过 fitHeight 根据实际内容动态调整
  const targetHeight = toFull ? INITIAL_FULL_HEIGHT : COMPACT_HEIGHT
  floatingState = toFull ? 'full' : 'compact'

  const { x: expandX, y: expandY } = calcExpandPosition(ballPosition.x, ballPosition.y, targetHeight)
  const toBounds = { x: expandX, y: expandY, width: EXPANDED_WIDTH, height: targetHeight }

  win.setMinimumSize(BALL_SIZE, BALL_SIZE)
  win.setHasShadow(true)

  animateBounds(win, fromBounds, toBounds, () => {
    win.setMinimumSize(EXPANDED_WIDTH, targetHeight)
    win.webContents.send('floating:stateChanged', floatingState)
  })
}

/**
 * 紧凑态 -> 完整态（带动画）
 * 初始扩展到最小完整态高度，后续由渲染进程通过 fitHeight 动态调整
 */
export function expandCompactToFull(): void {
  const win = mainWindow
  if (!win || floatingState !== 'compact')
    return

  floatingState = 'full'

  // 先通知渲染进程切换到完整态模板，避免动画期间紧凑态模板被拉伸
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()
  const display = screen.getPrimaryDisplay()
  const { height: screenH } = display.workAreaSize

  // 优先向下扩展（保持顶部不动）
  let newY = fromBounds.y
  if (fromBounds.y + INITIAL_FULL_HEIGHT > screenH) {
    newY = screenH - INITIAL_FULL_HEIGHT
    if (newY < 0)
      newY = 0
  }

  const toBounds = {
    x: fromBounds.x,
    y: newY,
    width: EXPANDED_WIDTH,
    height: INITIAL_FULL_HEIGHT,
  }

  win.setMinimumSize(BALL_SIZE, BALL_SIZE)

  animateBounds(win, fromBounds, toBounds, () => {
    win.setMinimumSize(EXPANDED_WIDTH, MIN_FIT_HEIGHT)
  })
}

/**
 * 完整态 -> 紧凑态（带动画）
 * 保持顶部位置不变，窗口高度收缩到紧凑态高度
 */
export function collapseFullToCompact(): void {
  const win = mainWindow
  if (!win || floatingState !== 'full')
    return

  floatingState = 'compact'

  // 先通知渲染进程切换到紧凑态模板
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()
  const toBounds = {
    x: fromBounds.x,
    y: fromBounds.y,
    width: EXPANDED_WIDTH,
    height: COMPACT_HEIGHT,
  }

  win.setMinimumSize(BALL_SIZE, BALL_SIZE)

  animateBounds(win, fromBounds, toBounds, () => {
    win.setMinimumSize(EXPANDED_WIDTH, COMPACT_HEIGHT)
  })
}

/**
 * 紧凑态/完整态 -> 球态（带动画）
 * 球始终回到当前窗口左边缘的位置（球视觉上在面板左侧）
 */
export function collapseFloatingWindow(): void {
  const win = mainWindow
  if (!win || (floatingState !== 'compact' && floatingState !== 'full'))
    return

  floatingState = 'ball'

  // 先通知渲染进程切换视图，再开始窗口动画
  win.webContents.send('floating:stateChanged', floatingState)

  const fromBounds = win.getBounds()

  // 球收缩到当前窗口的左边缘位置，垂直居中于面板顶部（球高 = compact高 = 100px）
  const targetX = fromBounds.x
  const targetY = fromBounds.y

  // 更新 ballPosition 为收缩后的实际位置
  ballPosition = { x: targetX, y: targetY }

  const toBounds = {
    x: targetX,
    y: targetY,
    width: BALL_SIZE,
    height: BALL_SIZE,
  }

  win.setMinimumSize(BALL_SIZE, BALL_SIZE)
  win.setHasShadow(false)
  animateBounds(win, fromBounds, toBounds)
}

/**
 * 设置窗口位置（用于渲染进程手动拖拽）
 * 同时更新 ballPosition 以保持收缩时位置一致
 */
export function setWindowPosition(x: number, y: number): void {
  const win = mainWindow
  if (!win)
    return
  const rx = Math.round(x)
  const ry = Math.round(y)
  if (floatingState !== 'classic') {
    cancelCurrentAnimation?.()
  }
  win.setPosition(rx, ry)
  // 任何悬浮球相关状态拖拽时都同步位置（球态/展开态都需要）
  if (floatingState !== 'classic') {
    ballPosition = { x: rx, y: ry }
  }
}

/**
 * 设置完整态窗口高度（由渲染进程根据内容高度调用）
 * 高度限制在 [MIN_FIT_HEIGHT, MAX_FULL_HEIGHT] 范围内
 * 高度变化 > 50px 时使用短动画过渡（如打开/关闭面板），小变化直接设置（流式消息逐行增长）
 */
export function setFloatingHeight(height: number): void {
  const win = mainWindow
  if (!win || floatingState !== 'full')
    return

  // 取消可能正在进行的高度动画，避免与新目标冲突
  cancelCurrentAnimation?.()

  const clamped = Math.max(MIN_FIT_HEIGHT, Math.min(Math.round(height), MAX_FULL_HEIGHT))
  const bounds = win.getBounds()

  if (bounds.height === clamped)
    return

  const display = screen.getPrimaryDisplay()
  const { height: screenH } = display.workAreaSize

  // 保持顶部不动，向下扩展；超出屏幕时向上调整
  let newY = bounds.y
  if (bounds.y + clamped > screenH) {
    newY = screenH - clamped
    if (newY < 0)
      newY = 0
  }

  const toBounds = { x: bounds.x, y: newY, width: EXPANDED_WIDTH, height: clamped }
  const delta = Math.abs(clamped - bounds.height)

  win.setMinimumSize(EXPANDED_WIDTH, MIN_FIT_HEIGHT)

  if (delta > 50) {
    // 高度变化较大时使用动画过渡（如打开/关闭会话历史面板）
    animateBounds(win, bounds, toBounds)
  }
  else {
    // 小变化直接设置（如流式消息逐行增长）
    win.setBounds(toBounds)
  }
}
