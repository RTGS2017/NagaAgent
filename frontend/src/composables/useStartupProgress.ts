import { ref, watch } from 'vue'
import API from '@/api/core'
import { backendConnected } from '@/utils/config'
import { preloadAllViews } from '@/utils/viewPreloader'

/** 将 promise 限制在 ms 毫秒内完成，超时则 resolve(undefined) 而非 reject */
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T | undefined> {
  return Promise.race([
    promise,
    new Promise<undefined>((resolve) => {
      setTimeout(() => {
        console.warn(`[Startup] ${label} 超时 (${ms}ms)，跳过`)
        resolve(undefined)
      }, ms)
    }),
  ])
}

export function useStartupProgress() {
  const progress = ref(0)
  const phase = ref<string>('初始化...')
  const isReady = ref(false)
  const stallHint = ref(false)

  let targetProgress = 0
  let rafId = 0
  let modelReady = false
  let postConnectStarted = false
  let unsubProgress: (() => void) | undefined
  let lastProgressValue = 0
  let lastProgressChangeTime = Date.now()
  let healthPollTimer: ReturnType<typeof setInterval> | undefined

  // 停滞检测：进度 3 秒无变化 → 显示提示
  function checkStall() {
    const now = Date.now()
    if (progress.value !== lastProgressValue) {
      lastProgressValue = progress.value
      lastProgressChangeTime = now
      stallHint.value = false
    }
    else if (!stallHint.value && now - lastProgressChangeTime >= 3000 && progress.value < 100) {
      stallHint.value = true
      console.warn(`[Startup] 进度停滞在 ${progress.value.toFixed(1)}%，已超过 3 秒`)
    }
  }

  // requestAnimationFrame 驱动的丝滑插值
  function animateProgress() {
    const diff = targetProgress - progress.value
    if (diff > 0.5) {
      // 比例追赶 + 最低速度，避免接近目标时卡顿
      progress.value = Math.min(progress.value + Math.max(diff * 0.12, 0.5), targetProgress)
    }
    else if (diff > 0) {
      progress.value = targetProgress
    }

    if (progress.value >= 100) {
      progress.value = 100
      isReady.value = true
    }

    checkStall()

    if (!isReady.value || progress.value < 100) {
      rafId = requestAnimationFrame(animateProgress)
    }
  }

  function setTarget(value: number, newPhase: string) {
    if (value > targetProgress) {
      console.log(`[Startup] 进度 ${targetProgress.toFixed(0)}% → ${value.toFixed(0)}%  阶段: ${newPhase}`)
      targetProgress = value
      phase.value = newPhase
    }
  }

  // 外部通知：Live2D 模型加载完成
  function notifyModelReady() {
    modelReady = true
    console.log('[Startup] Live2D 模型就绪')
    setTarget(25, '连接后端...')
  }

  // 轮询后端健康检查，确保不会卡在 50%
  function startHealthPolling() {
    if (healthPollTimer)
      return
    let pollCount = 0
    console.log('[Startup] 开始轮询后端健康状态...')
    healthPollTimer = setInterval(async () => {
      pollCount++
      try {
        await API.health()
        // 健康检查成功 → 确保 backendConnected 置位（供 config sync 使用）
        if (!backendConnected.value) {
          console.log(`[Startup] 健康轮询成功 (第 ${pollCount} 次)，置位 backendConnected`)
          backendConnected.value = true
        }
        // 直接触发 postConnect（幂等，重复调用安全）
        runPostConnect()
      }
      catch {
        // 后端尚未就绪，继续轮询
        if (pollCount % 3 === 0) {
          console.log(`[Startup] 等待后端就绪... 已轮询 ${pollCount} 次`)
        }
      }
    }, 1000)
  }

  function stopHealthPolling() {
    if (healthPollTimer) {
      clearInterval(healthPollTimer)
      healthPollTimer = undefined
    }
  }

  async function runPostConnect() {
    // 幂等守卫：防止 watcher + 健康轮询重复触发
    if (postConnectStarted)
      return
    postConnectStarted = true

    // 全局安全超时：无论什么原因，15 秒后强制完成启动
    const safetyTimer = setTimeout(() => {
      console.warn('[Startup] runPostConnect 全局超时 (15s)，强制完成启动')
      setTarget(100, '准备就绪')
    }, 15000)

    try {
      // 取消后端进度监听和健康轮询
      unsubProgress?.()
      unsubProgress = undefined
      stopHealthPolling()

      // 阶段 25→50：后端已连接
      console.log('[Startup] 后端已连接，开始后连接任务')
      setTarget(50, '预加载视图...')

      // 阶段 50→70：预加载视图（8 秒超时，超时不阻塞启动）
      console.log('[Startup] 开始预加载 7 个视图组件...')
      await withTimeout(
        preloadAllViews((loaded, total) => {
          const viewProgress = 50 + (loaded / total) * 20
          console.log(`[Startup] 预加载视图 ${loaded}/${total} (${viewProgress.toFixed(0)}%)`)
          setTarget(viewProgress, `预加载视图 ${loaded}/${total}...`)
        }),
        8000,
        'preloadAllViews',
      )
      console.log('[Startup] 视图预加载完成')

      // 阶段 70→90：获取会话（5 秒超时）
      setTarget(70, '获取会话...')
      console.log('[Startup] 获取会话列表...')
      try {
        await withTimeout(API.getSessions(), 5000, 'getSessions')
        console.log('[Startup] 会话获取完成')
      }
      catch {
        console.warn('[Startup] 会话获取失败，不阻塞启动')
      }
      setTarget(90, '准备就绪')
      console.log('[Startup] 所有启动任务完成，进入主界面')

      // 阶段 90→100：完成
      setTimeout(() => setTarget(100, '准备就绪'), 300)
    }
    finally {
      clearTimeout(safetyTimer)
    }
  }

  async function startProgress() {
    // 阶段 0→10：初始化
    setTarget(10, modelReady ? '连接后端...' : '加载模型...')
    rafId = requestAnimationFrame(animateProgress)

    // 监听后端进度信号（Electron 环境）
    const api = window.electronAPI
    if (api?.backend) {
      unsubProgress = api.backend.onProgress((payload) => {
        // 后端 percent 0~50 映射到前端 10~50 区间
        const mapped = 10 + (payload.percent / 50) * 40
        setTarget(Math.min(mapped, 50), payload.phase)
      })
    }

    // 如果后端已连接（HMR/重复挂载），直接推进
    if (backendConnected.value) {
      runPostConnect()
      return
    }

    // 立即开始轮询后端健康状态（不再等待 progress >= 25，避免动画延迟导致卡死）
    startHealthPolling()

    // 监听后端连接（由 config.ts connectBackend 或健康轮询触发）
    const stopWatch = watch(backendConnected, (connected) => {
      if (!connected)
        return
      stopWatch()
      runPostConnect()
    })
  }

  function cleanup() {
    if (rafId)
      cancelAnimationFrame(rafId)
    unsubProgress?.()
    stopHealthPolling()
  }

  return {
    progress,
    phase,
    isReady,
    stallHint,
    startProgress,
    notifyModelReady,
    cleanup,
  }
}
