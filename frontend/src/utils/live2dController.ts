import type { Live2DModel } from 'pixi-live2d-display/cubism4'
import { ref } from 'vue'

// ─── 类型 ───────────────────────────────────────────
interface Keyframe {
  t: number
  params: Record<string, number>
}

interface StateConfig {
  loop: boolean
  duration?: number
  keyframes?: Keyframe[]
  params?: Record<string, number>
  mouth?: { param: string, speed: number, min: number, max: number }
}

interface ActionConfig {
  duration: number
  repeat: number
  keyframes: Keyframe[]
}

interface ActionsData {
  states: Record<string, StateConfig>
  actions: Record<string, ActionConfig>
}

/** .exp3.json 中单个参数定义 */
interface Exp3Param {
  Id: string
  Value: number
  Blend: 'Add' | 'Multiply' | 'Overwrite'
}

/** 加载后的表情定义 */
interface ExpressionDef {
  name: string
  fadeInTime: number
  params: Exp3Param[]
}

export type Live2dState = 'idle' | 'thinking' | 'talking'
export type EmotionCategory = 'normal' | 'positive' | 'negative' | 'surprise'

// ─── 全局响应式状态 ──────────────────────────────────
export const live2dState = ref<Live2dState>('idle')
export const trackingCalibration = ref(false)

// ─── 内部变量 ────────────────────────────────────────
let model: Live2DModel | null = null
let actionsData: ActionsData | null = null
let stateStartTime = 0
let currentStateName: Live2dState = 'idle'
let originalUpdate: ((dt: number) => void) | null = null
let lastTickTime = 0

// 通道 1: 身体摇摆（由状态 idle/thinking/talking 控制）
// → ParamBodyAngleX, ParamAngleZ 等

// 通道 2: 头部动作（由动作队列 nod/shake 控制，正交于身体通道）
// → ParamAngleX, ParamAngleY, ParamEyeBallX, ParamEyeBallY
let actionQueue: string[] = []
let activeAction: { config: ActionConfig, startTime: number } | null = null

// 通道 3: Emotion 表情（独立通道，从 .exp3.json 文件加载）
// 与身体/头部通道完全正交，使用 .exp3.json 的 Blend 模式合成
const expressionDefs: Map<string, ExpressionDef> = new Map()
let currentEmotionName: string | null = null
let emotionCurrentValues: Record<string, number> = {}
let _emotionFadeStartTime = 0

// 手动参数覆盖（由 setExpression 驱动，用于开屏闭眼等，优先级最高）
let expressionTarget: Record<string, number> = {}
let expressionCurrent: Record<string, number> = {}
let expressionActive = false

// 嘴巴状态（身体通道附属）
let mouthTarget = 0
let mouthCurrent = 0
let mouthNextChangeTime = 0

// ─── 手动覆盖通道 ──────────────────────────────────

/** 表情参数的默认值（清除表情时回归的目标） */
const EXPRESSION_DEFAULTS: Record<string, number> = {
  ParamEyeLOpen: 1,
  ParamEyeROpen: 1,
  ParamEyeLSmile: 0,
  ParamEyeRSmile: 0,
  ParamBrowLY: 0,
  ParamBrowRY: 0,
  ParamMouthForm: 0,
}

function computeManualOverride(dt: number): Record<string, number> {
  if (!expressionActive && Object.keys(expressionCurrent).length === 0)
    return {}

  const allParams = new Set([...Object.keys(expressionTarget), ...Object.keys(expressionCurrent)])
  const halfLife = 100 // 100ms 平滑过渡
  const sf = smoothFactor(halfLife, dt)
  const result: Record<string, number> = {}
  const toDelete: string[] = []

  for (const param of allParams) {
    const target = expressionActive
      ? (expressionTarget[param] ?? EXPRESSION_DEFAULTS[param] ?? 0)
      : (EXPRESSION_DEFAULTS[param] ?? 0)
    const current = expressionCurrent[param] ?? EXPRESSION_DEFAULTS[param] ?? 0
    const newVal = lerp(current, target, sf)
    expressionCurrent[param] = newVal
    result[param] = newVal

    // 参数已回归默认且不再激活，清理
    if (!expressionActive) {
      const defaultVal = EXPRESSION_DEFAULTS[param] ?? 0
      if (Math.abs(newVal - defaultVal) < 0.001) {
        toDelete.push(param)
      }
    }
  }

  for (const k of toDelete) {
    delete expressionCurrent[k]
  }

  return result
}

// ─── 视觉追踪（独立叠加层） ─────────────────────────
let isTracking = false
let trackTargetX = 0
let trackTargetY = 0
let trackCurrentX = 0
let trackCurrentY = 0
let trackBlend = 0

// ─── 工具函数 ────────────────────────────────────────

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.min(1, Math.max(0, t))
}

function smoothFactor(halfLife: number, dt: number): number {
  if (halfLife <= 0)
    return 1
  return 1 - Math.exp((-0.693 / halfLife) * dt)
}

function interpolateKeyframes(keyframes: Keyframe[], progress: number): Record<string, number> {
  const result: Record<string, number> = {}
  const p = Math.max(0, Math.min(1, progress))

  let left = keyframes[0]!
  let right = keyframes[keyframes.length - 1]!
  for (let i = 0; i < keyframes.length - 1; i++) {
    if (p >= keyframes[i]!.t && p <= keyframes[i + 1]!.t) {
      left = keyframes[i]!
      right = keyframes[i + 1]!
      break
    }
  }

  const segLen = right.t - left.t
  const localT = segLen > 0 ? (p - left.t) / segLen : 0
  const smooth = localT * localT * (3 - 2 * localT)

  const allParams = new Set([...Object.keys(left.params), ...Object.keys(right.params)])
  for (const param of allParams) {
    const a = left.params[param] ?? 0
    const b = right.params[param] ?? 0
    result[param] = lerp(a, b, smooth)
  }
  return result
}

function setParam(paramId: string, value: number) {
  if (!model)
    return
  try {
    const core = (model.internalModel as any).coreModel
    if (core?.setParameterValueById) {
      core.setParameterValueById(paramId, value)
    }
  }
  catch {
  }
}

// ─── 表情加载（从 .exp3.json 文件） ─────────────────

async function loadExpressions(modelBasePath: string, modelSource: string) {
  try {
    const modelRes = await fetch(modelSource)
    const modelJson = await modelRes.json()
    const expressions = modelJson?.FileReferences?.Expressions ?? []

    for (const entry of expressions) {
      const fileName: string = entry.File
      // 从文件名提取表情名称（如 happy.exp3.json → happy）
      const expName = fileName.replace('.exp3.json', '')

      try {
        const expRes = await fetch(`${modelBasePath}/${fileName}`)
        const expJson = await expRes.json()

        const def: ExpressionDef = {
          name: expName,
          fadeInTime: expJson.FadeInTime ?? 0.5,
          params: (expJson.Parameters ?? []).map((p: any) => ({
            Id: p.Id as string,
            Value: p.Value as number,
            Blend: (p.Blend ?? 'Add') as 'Add' | 'Multiply' | 'Overwrite',
          })),
        }
        expressionDefs.set(expName, def)
      }
      catch (e) {
        console.warn(`[Live2D] Failed to load expression: ${fileName}`, e)
      }
    }
    console.log('[Live2D] Loaded expressions:', Array.from(expressionDefs.keys()))
  }
  catch (e) {
    console.warn('[Live2D] Failed to load model3.json for expressions:', e)
  }
}

// ─── 通道计算（只计算不写入） ─────────────────────────

function computeStateParams(now: number): Record<string, number> {
  if (!actionsData)
    return {}
  const stateCfg = actionsData.states[currentStateName]
  if (!stateCfg)
    return {}

  const result: Record<string, number> = {}

  if (stateCfg.keyframes && stateCfg.duration) {
    const elapsed = now - stateStartTime
    const progress = stateCfg.loop
      ? (elapsed % stateCfg.duration) / stateCfg.duration
      : Math.min(elapsed / stateCfg.duration, 1)
    Object.assign(result, interpolateKeyframes(stateCfg.keyframes, progress))
  }
  else if (stateCfg.params) {
    Object.assign(result, stateCfg.params)
  }

  return result
}

function computeMouth(now: number, dt: number): Record<string, number> {
  if (!actionsData)
    return {}
  const stateCfg = actionsData.states[currentStateName]
  if (!stateCfg?.mouth)
    return {}

  const cfg = stateCfg.mouth
  if (now >= mouthNextChangeTime) {
    mouthTarget = cfg.min + Math.random() * (cfg.max - cfg.min)
    mouthNextChangeTime = now + 80 + Math.random() * 170
  }
  const halfLife = cfg.speed / 3
  mouthCurrent = lerp(mouthCurrent, mouthTarget, smoothFactor(halfLife, dt))

  return { [cfg.param]: mouthCurrent }
}

function computeActionParams(now: number): Record<string, number> {
  if (!actionsData)
    return {}

  if (!activeAction && actionQueue.length > 0) {
    const actionName = actionQueue.shift()!
    console.log('[Live2D] Starting action:', actionName)
    const cfg = actionsData.actions[actionName]
    if (cfg) {
      activeAction = { config: cfg, startTime: now }
    }
    else {
      console.warn('[Live2D] Action not found:', actionName)
    }
  }

  if (!activeAction)
    return {}

  const { config, startTime } = activeAction
  const totalDuration = config.duration * config.repeat
  const elapsed = now - startTime

  if (elapsed >= totalDuration) {
    const result: Record<string, number> = {}
    if (config.keyframes.length > 0) {
      const lastFrame = config.keyframes[config.keyframes.length - 1]!
      for (const k of Object.keys(lastFrame.params)) {
        result[k] = lastFrame.params[k] ?? 0
      }
    }
    console.log('[Live2D] Action completed, keeping last frame')
    activeAction = null
    return result
  }

  const repeatElapsed = elapsed % config.duration
  const progress = repeatElapsed / config.duration
  return interpolateKeyframes(config.keyframes, progress)
}

/**
 * 通道 3: Emotion 表情计算
 * 从 .exp3.json 加载的表情定义，平滑过渡到目标表情。
 * 返回 { paramId → { value, blend } } 用于与其他通道正确合成。
 */
function computeEmotionParams(dt: number): Record<string, { value: number, blend: 'Add' | 'Multiply' | 'Overwrite' }> {
  const result: Record<string, { value: number, blend: 'Add' | 'Multiply' | 'Overwrite' }> = {}

  // 获取目标表情参数
  const targetDef = currentEmotionName ? expressionDefs.get(currentEmotionName) : null
  const targetParams: Record<string, { value: number, blend: 'Add' | 'Multiply' | 'Overwrite' }> = {}

  if (targetDef) {
    for (const p of targetDef.params) {
      targetParams[p.Id] = { value: p.Value, blend: p.Blend }
    }
  }

  // 计算过渡（用 fadeInTime 或固定 halfLife）
  const fadeInTime = targetDef?.fadeInTime ?? 0.5
  const halfLife = Math.max(fadeInTime * 300, 80) // 转换为 ms 级别的半衰期
  const sf = smoothFactor(halfLife, dt)

  // 合并所有参与过渡的参数
  const allParamIds = new Set([
    ...Object.keys(targetParams),
    ...Object.keys(emotionCurrentValues),
  ])

  const toDelete: string[] = []

  for (const paramId of allParamIds) {
    const target = targetParams[paramId]
    const targetValue = target?.value ?? 0 // 不在新表情中的参数归零
    const blend = target?.blend ?? 'Add'
    const current = emotionCurrentValues[paramId] ?? 0

    const newVal = lerp(current, targetValue, sf)
    emotionCurrentValues[paramId] = newVal

    // 足够接近零且不是目标参数的，清理掉
    if (!targetParams[paramId] && Math.abs(newVal) < 0.001) {
      toDelete.push(paramId)
    }
    else {
      result[paramId] = { value: newVal, blend }
    }
  }

  for (const k of toDelete) {
    delete emotionCurrentValues[k]
  }

  return result
}

// ─── 视觉追踪计算 ────────────────────────────────────

const TRACK_PARAMS: Record<string, (x: number, y: number) => number> = {
  ParamAngleX: (x, _y) => x * 30,
  ParamAngleY: (_x, y) => y * 30,
  ParamEyeBallX: (x, _y) => x,
  ParamEyeBallY: (_x, y) => y,
  ParamBodyAngleX: (x, _y) => x * 10,
}

function computeTracking(dt: number): Record<string, number> {
  const blendTarget = isTracking ? 1 : 0
  const blendHalfLife = isTracking ? 60 : 120
  trackBlend = lerp(trackBlend, blendTarget, smoothFactor(blendHalfLife, dt))

  if (trackBlend < 0.001) {
    trackBlend = 0
    trackCurrentX = 0
    trackCurrentY = 0
    return {}
  }

  const followHalfLife = isTracking ? 40 : 80
  const sf = smoothFactor(followHalfLife, dt)
  const targetX = isTracking ? trackTargetX : 0
  const targetY = isTracking ? trackTargetY : 0
  trackCurrentX = lerp(trackCurrentX, targetX, sf)
  trackCurrentY = lerp(trackCurrentY, targetY, sf)

  const result: Record<string, number> = {}
  for (const [param, fn] of Object.entries(TRACK_PARAMS)) {
    result[param] = fn(trackCurrentX, trackCurrentY)
  }
  return result
}

// ─── 主 tick ─────────────────────────────────────────

function tick(now: number) {
  if (!actionsData)
    return

  const dt = lastTickTime > 0 ? Math.min(now - lastTickTime, 100) : 16
  lastTickTime = now

  if (currentStateName !== live2dState.value) {
    currentStateName = live2dState.value
    stateStartTime = now
    if (currentStateName !== 'talking') {
      mouthCurrent = 0
      mouthTarget = 0
    }
  }

  // ── 计算各正交通道 ──
  const stateParams = computeStateParams(now) // 通道1: 身体摇摆
  const mouthParams = computeMouth(now, dt) // 附属: 嘴巴
  const actionParams = computeActionParams(now) // 通道2: 头部动作
  const emotionParams = computeEmotionParams(dt) // 通道3: Emotion 表情（从 .exp3.json）
  const overrideParams = computeManualOverride(dt) // 手动覆盖（setExpression）

  // 合并基础通道（身体 + 嘴巴 + 头部 + 手动覆盖）
  const merged: Record<string, number> = { ...stateParams, ...mouthParams, ...actionParams, ...overrideParams }

  // 应用 Emotion 表情通道（使用 .exp3.json 的 Blend 模式）
  for (const [param, { value, blend }] of Object.entries(emotionParams)) {
    switch (blend) {
      case 'Add':
        merged[param] = (merged[param] ?? 0) + value
        break
      case 'Multiply':
        merged[param] = (merged[param] ?? 1) * value
        break
      case 'Overwrite':
        merged[param] = value
        break
    }
  }

  // 视觉追踪叠加
  const trackParams = computeTracking(dt)
  if (trackBlend > 0) {
    for (const [param, trackValue] of Object.entries(trackParams)) {
      const base = merged[param] ?? 0
      merged[param] = lerp(base, trackValue, trackBlend)
    }
  }

  for (const [param, value] of Object.entries(merged)) {
    setParam(param, value)
  }
}

// ─── 公共 API ────────────────────────────────────────

/**
 * 设置情绪表情。
 * 根据情绪类别选择对应的 .exp3.json 表情，平滑过渡。
 * - 'normal' → normal 表情
 * - 'positive' → 随机选择 happy 或 enjoy
 * - 'negative' → sad 表情
 * - 'surprise' → surprise 表情
 */
export async function setEmotion(emotion: EmotionCategory) {
  const positiveExpressions = ['happy', 'enjoy'] as const
  let targetName: string

  switch (emotion) {
    case 'normal':
      targetName = 'normal'
      break
    case 'positive':
      targetName = positiveExpressions[Math.floor(Math.random() * positiveExpressions.length)]!
      break
    case 'negative':
      targetName = 'sad'
      break
    case 'surprise':
      targetName = 'surprise'
      break
    default:
      targetName = 'normal'
  }

  // 只有在已加载对应表情时才切换
  if (expressionDefs.has(targetName)) {
    console.log('[Live2D] Set emotion:', emotion, '→', targetName)
    currentEmotionName = targetName
    _emotionFadeStartTime = performance.now()
  }
  else {
    console.warn('[Live2D] Emotion expression not loaded:', targetName, 'available:', Array.from(expressionDefs.keys()))
  }
}

/** 清除情绪表情，平滑回归中性 */
export function clearEmotion() {
  currentEmotionName = null
}

export function triggerAction(name: string) {
  console.log('[Live2D] Trigger action:', name)
  actionQueue = [name]
  activeAction = null
}

/** 设置手动参数覆盖（如闭眼：{ ParamEyeLOpen: 0, ParamEyeROpen: 0 }） */
export function setExpression(params: Record<string, number>) {
  expressionTarget = { ...params }
  expressionActive = true
}

/** 清除手动覆盖，参数平滑回归默认值 */
export function clearExpression() {
  expressionActive = false
  expressionTarget = {}
}

/** 获取所有已加载的表情名称 */
export function getAvailableExpressions(): string[] {
  return Array.from(expressionDefs.keys())
}

export function startTracking() {
  isTracking = true
}

export function stopTracking() {
  isTracking = false
}

export function updateTracking(x: number, y: number) {
  trackTargetX = x
  trackTargetY = y
}

export async function initController(modelInstance: Live2DModel, modelSource: string) {
  model = modelInstance

  // Derive base path from model3.json URL
  // e.g. './models/NagaTest2/NagaTest2.model3.json' → './models/NagaTest2'
  const basePath = modelSource.replace(/\/[^/]+$/, '')

  try {
    // 加载身体/头部动作数据
    const response = await fetch(`${basePath}/naga-actions.json`)
    actionsData = await response.json() as ActionsData

    // 加载 .exp3.json 表情文件
    await loadExpressions(basePath, modelSource)

    originalUpdate = model.update.bind(model)
    model.update = function (dt: number) {
      const now = performance.now()
      originalUpdate!(dt)
      tick(now)
    }
    console.log('[Live2D] Controller initialized for:', modelSource)
  }
  catch (e) {
    console.error('[Live2D] Controller initialization failed:', e)
  }
}

export function destroyController() {
  if (model && originalUpdate) {
    model.update = originalUpdate
  }
  model = null
  actionsData = null
  originalUpdate = null
  actionQueue = []
  activeAction = null
  // Emotion 通道
  expressionDefs.clear()
  currentEmotionName = null
  emotionCurrentValues = {}
  _emotionFadeStartTime = 0
  // 手动覆盖通道
  expressionTarget = {}
  expressionCurrent = {}
  expressionActive = false
  // 嘴巴
  mouthCurrent = 0
  mouthTarget = 0
  // 追踪
  lastTickTime = 0
  isTracking = false
  trackTargetX = 0
  trackTargetY = 0
  trackCurrentX = 0
  trackCurrentY = 0
  trackBlend = 0
}
