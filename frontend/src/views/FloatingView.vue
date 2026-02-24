<script setup lang="ts">
import type { CaptureSource, FloatingState } from '@/electron.d'
import { useEventListener } from '@vueuse/core'
import ScrollPanel from 'primevue/scrollpanel'
import { computed, nextTick, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import API from '@/api/core'
import MessageItem from '@/components/MessageItem.vue'
import { startToolPolling, stopToolPolling, toolMessage } from '@/composables/useToolStatus'
import { CONFIG } from '@/utils/config'
import { CURRENT_SESSION_ID, formatRelativeTime, IS_TEMPORARY_SESSION, loadCurrentSession, MESSAGES, newSession, newTemporarySession, switchSession } from '@/utils/session'
import { chatStream } from '@/views/MessageView.vue'

// 悬浮球状态
const floatingState = ref<FloatingState>('ball')
const isPinned = ref(false)
const input = ref('')
const showContent = ref(false) // 控制内容入场动画
const inputRef = useTemplateRef('inputRef')
const scrollPanelRef = useTemplateRef<{ scrollTop: (v: number) => void }>('scrollPanelRef')
const messageContentRef = useTemplateRef<HTMLElement>('messageContentRef')
const sessionPanelRef = useTemplateRef<HTMLElement>('sessionPanelRef')

// 窗口截屏
const showCapturePanel = ref(false)
const captureSources = ref<CaptureSource[]>([])
const loadingCapture = ref(false)
const capturePanelRef = useTemplateRef<HTMLElement>('capturePanelRef')
const pendingImages = ref<string[]>([]) // 待发送的截图 dataURL 列表

// 文件上传
const fileInputRef = useTemplateRef<HTMLInputElement>('fileInputRef')
let suppressBlur = false // 文件选择器打开期间抑制失焦收缩

// 右键菜单（通过 Electron 原生菜单实现，避免小窗口裁剪）
function showBallContextMenu(e: MouseEvent) {
  e.preventDefault()
  window.electronAPI?.showContextMenu()
}

// 是否有消息历史（用于决定展开到 compact 还是 full）
const hasMessages = computed(() => MESSAGES.value.length > 0)

// 判断当前是否处于展开状态（compact 或 full）
const isExpanded = computed(() =>
  floatingState.value === 'compact' || floatingState.value === 'full',
)

// 是否正在生成回复（用于光晕脉冲特效）
const isGenerating = computed(() => MESSAGES.value[MESSAGES.value.length - 1]?.generating === true)

// 序列帧动画（球态）
const frameIndex = ref(1) // 默认显示帧1（睁眼）
const framePath = (i: number) => `./assets/悬浮球序列帧/${i}.png`
let blinkTimer: ReturnType<typeof setTimeout> | null = null
let blinkStopped = false // 用于终止正在进行的眨眼序列

// 眨眼动画序列：睁眼->半闭->闭眼->半闭->睁眼
const BLINK_SEQUENCE = [1, 2, 3, 4, 5, 4, 3, 2, 1]
const BLINK_FRAME_MS = 70

function playBlink() {
  let step = 0
  const next = () => {
    if (blinkStopped)
      return
    if (step >= BLINK_SEQUENCE.length) {
      // 眨眼结束，随机 2~5 秒后再次眨眼
      scheduleNextBlink()
      return
    }
    frameIndex.value = BLINK_SEQUENCE[step]!
    step++
    setTimeout(next, BLINK_FRAME_MS)
  }
  next()
}

function scheduleNextBlink() {
  const delay = 2000 + Math.random() * 3000
  blinkTimer = setTimeout(playBlink, delay)
}

function startFrameAnimation() {
  blinkStopped = false
  frameIndex.value = 1
  scheduleNextBlink()
}

function stopFrameAnimation() {
  blinkStopped = true
  if (blinkTimer) {
    clearTimeout(blinkTimer)
    blinkTimer = null
  }
}

// 生成完成通知（灯泡覆盖层独立闪烁，不影响底层眨眼动画）
let notifyTimer: ReturnType<typeof setInterval> | null = null
const isNotifying = ref(false)
const showLightbulb = ref(false)

function startNotification() {
  isNotifying.value = true
  showLightbulb.value = true
  notifyTimer = setInterval(() => {
    showLightbulb.value = !showLightbulb.value
  }, 400)
}

function stopNotification() {
  if (notifyTimer) {
    clearInterval(notifyTimer)
    notifyTimer = null
  }
  isNotifying.value = false
  showLightbulb.value = false
}

// 监听生成完成：generating 从 true 变为 undefined 时，球态下触发灯泡闪烁
watch(
  () => MESSAGES.value[MESSAGES.value.length - 1]?.generating,
  (curr, prev) => {
    if (prev && !curr && floatingState.value === 'ball') {
      startNotification()
    }
  },
)

// 监听 Electron 状态变化
let unsubStateChange: (() => void) | undefined
let unsubBlur: (() => void) | undefined
let resizeObserver: ResizeObserver | null = null
let fitRAF = 0

// ─── 会话历史（声明前置，fitWindowHeight 需要引用） ──────
const showHistory = ref(false)

// 根据消息内容自适应窗口高度
function fitWindowHeight() {
  if (floatingState.value !== 'full')
    return
  const el = messageContentRef.value
  if (!el)
    return
  const HEADER_HEIGHT = 100
  const BORDER = 2
  const toolH = toolMessage.value ? 24 : 0
  // 使用 showHistory 守卫：Transition leave 期间 DOM 元素仍在但 showHistory 已为 false，避免误计
  const sessionH = showHistory.value ? (sessionPanelRef.value?.offsetHeight ?? 0) : 0
  const captureH = showCapturePanel.value ? (capturePanelRef.value?.offsetHeight ?? 0) : 0
  const contentH = el.scrollHeight
  const desired = HEADER_HEIGHT + sessionH + captureH + contentH + toolH + BORDER
  window.electronAPI?.floating.fitHeight(desired)
}

function requestFitHeight() {
  if (fitRAF)
    return
  fitRAF = requestAnimationFrame(() => {
    fitRAF = 0
    fitWindowHeight()
  })
}

function setupResizeObserver() {
  resizeObserver?.disconnect()
  if (messageContentRef.value) {
    resizeObserver = new ResizeObserver(requestFitHeight)
    resizeObserver.observe(messageContentRef.value)
  }
}

onMounted(() => {
  const api = window.electronAPI
  if (!api)
    return

  // 启动序列帧动画
  startFrameAnimation()

  // 加载会话和工具状态
  loadCurrentSession()
  startToolPolling()

  // 获取初始状态
  api.floating.getState().then((state) => {
    floatingState.value = state
  })

  // 监听状态变化
  unsubStateChange = api.floating.onStateChange((state) => {
    floatingState.value = state
    if (state === 'compact' || state === 'full') {
      // 延迟触发内容入场动画（等窗口动画结束）
      showContent.value = false
      nextTick().then(() => {
        showContent.value = true
        if (state === 'full') {
          nextTick().then(() => {
            scrollToBottom()
            setupResizeObserver()
            requestFitHeight()
          })
        }
        // 自动聚焦输入框
        setTimeout(() => {
          inputRef.value?.focus()
        }, 100)
      })
    }
    else {
      showContent.value = false
      resizeObserver?.disconnect()
      resizeObserver = null
    }
  })

  // 监听窗口失焦
  unsubBlur = api.floating.onWindowBlur(() => {
    if (isExpanded.value && !isPinned.value && !suppressBlur) {
      api.floating.collapse()
    }
  })
})

// 球态下让 Electron 透明窗口无方形背景，展开态恢复不透明
watch(floatingState, (state) => {
  const bg = state === 'ball' ? 'transparent' : '#110901'
  document.documentElement.style.backgroundColor = bg
}, { immediate: true })

onUnmounted(() => {
  // 恢复经典模式背景
  document.documentElement.style.backgroundColor = '#110901'
  unsubStateChange?.()
  unsubBlur?.()
  stopToolPolling()
  stopFrameAnimation()
  stopNotification()
  resizeObserver?.disconnect()
  if (fitRAF) {
    cancelAnimationFrame(fitRAF)
    fitRAF = 0
  }
})

// 悬浮球操作：根据消息历史决定展开目标
function handleBallClick() {
  if (isNotifying.value) {
    stopNotification()
  }
  window.electronAPI?.floating.expand(hasMessages.value)
}

// 手动拖拽实现（-webkit-app-region: drag 会吞掉点击事件，因此所有状态统一用 JS 实现）
const DRAG_THRESHOLD = 4
let dragState: { screenX: number, screenY: number, winX: number, winY: number } | null = null
let hasDragged = false

function onDragPointerDown(e: PointerEvent) {
  dragState = {
    screenX: e.screenX,
    screenY: e.screenY,
    winX: e.screenX - e.clientX,
    winY: e.screenY - e.clientY,
  }
  hasDragged = false
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}

function onDragPointerMove(e: PointerEvent) {
  if (!dragState)
    return
  const dx = e.screenX - dragState.screenX
  const dy = e.screenY - dragState.screenY
  if (!hasDragged && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD)
    return
  hasDragged = true
  window.electronAPI?.floating.setPosition(dragState.winX + dx, dragState.winY + dy)
}

function onDragPointerUp(e: PointerEvent) {
  if (!dragState) {
    return
  }
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  dragState = null
}

// 球态：拖拽 + 点击展开（pointerup 需要区分拖拽和点击）
function onBallPointerUp(e: PointerEvent) {
  if (!dragState) {
    return
  }
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  if (!hasDragged) {
    handleBallClick()
  }
  dragState = null
}

// 紧凑态/完整态球：拖拽 + 点击收起
function onCompactBallPointerDown(e: PointerEvent) {
  e.stopPropagation()
  onDragPointerDown(e)
}

function onCompactBallPointerUp(e: PointerEvent) {
  if (!dragState) {
    return
  }
  ;(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId)
  if (!hasDragged) {
    handleCollapse()
  }
  dragState = null
}

function handleCollapse() {
  window.electronAPI?.floating.collapse()
}

function handleExitFloating() {
  CONFIG.value.floating.enabled = false
  window.electronAPI?.floating.exit()
}

function togglePin() {
  isPinned.value = !isPinned.value
  window.electronAPI?.floating.pin(isPinned.value)
}

// 聊天功能
function scrollToBottom() {
  scrollPanelRef.value?.scrollTop(Infinity)
}

// 快捷技能按钮定义（name 对应 skills/ 目录下的技能名称）
const QUICK_SKILLS = [
  { label: '帮我翻译', name: 'translate' },
  { label: '帮我概括', name: 'summarize' },
  { label: '真假鉴别', name: 'verify-authenticity' },
  { label: '帮我想想', name: 'solve' },
]

// 当前选中的技能索引，-1 表示未选中
const activeSkillIndex = ref(-1)

function handleQuickSkill(index: number) {
  // 切换选中状态：再次点击取消选中
  activeSkillIndex.value = activeSkillIndex.value === index ? -1 : index
  nextTick(() => {
    inputRef.value?.focus()
  })
}

// 窗口截屏功能
const capturePermissionDenied = ref(false)

async function handleCapture() {
  if (showCapturePanel.value) {
    closeCapturePanel()
    return
  }
  // 如果是紧凑态，先展开到完整态
  if (floatingState.value === 'compact') {
    window.electronAPI?.floating.expandToFull()
  }
  loadingCapture.value = true
  showCapturePanel.value = true
  capturePermissionDenied.value = false
  try {
    const result = await window.electronAPI?.capture.getSources()
    if (result && 'permission' in result) {
      // macOS 屏幕录制权限未授予
      capturePermissionDenied.value = true
      captureSources.value = []
    }
    else {
      const sources = (result as Array<{ id: string, name: string, thumbnail: string, appIcon: string | null }>) ?? []
      captureSources.value = sources.filter(s => !s.name.includes('NagaAgent'))
    }
  }
  catch {
    captureSources.value = []
  }
  loadingCapture.value = false
  await nextTick()
  fitWindowHeight()
}

async function closeCapturePanel() {
  showCapturePanel.value = false
  await nextTick()
  await nextTick()
  fitWindowHeight()
}

function openScreenSettings() {
  window.electronAPI?.capture.openScreenSettings()
}

async function selectCaptureSource(source: CaptureSource) {
  showCapturePanel.value = false
  // 以高分辨率重新截取选中窗口，追加到待发送列表
  const imageData = await window.electronAPI?.capture.captureWindow(source.id)
  if (!imageData)
    return
  pendingImages.value.push(imageData)
  await nextTick()
  inputRef.value?.focus()
  fitWindowHeight()
}

function removePendingImage(index: number) {
  pendingImages.value.splice(index, 1)
  nextTick().then(fitWindowHeight)
}

function sendMessage() {
  if (!input.value.trim() && pendingImages.value.length === 0)
    return

  // 如果当前是紧凑态，先请求扩展到完整态
  if (floatingState.value === 'compact') {
    window.electronAPI?.floating.expandToFull()
  }

  // 如果选中了技能，通过 skill 参数传给后端，由后端注入完整指令
  let skillName: string | undefined
  if (activeSkillIndex.value >= 0) {
    skillName = QUICK_SKILLS[activeSkillIndex.value]?.name
    activeSkillIndex.value = -1
  }

  const images = pendingImages.value.length > 0 ? [...pendingImages.value] : undefined
  chatStream(input.value || '请分析这些截图中的内容', { skill: skillName, images })
  input.value = ''
  pendingImages.value = []
  nextTick().then(scrollToBottom)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    sendMessage()
  }
}

function triggerFileUpload() {
  suppressBlur = true
  // 用户取消文件选择器时 change 事件可能不触发，通过 focus 兜底恢复
  const onFocus = () => {
    setTimeout(() => {
      suppressBlur = false
    }, 300)
    window.removeEventListener('focus', onFocus)
  }
  window.addEventListener('focus', onFocus)
  fileInputRef.value?.click()
}

async function handleFileUpload(event: Event) {
  suppressBlur = false
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file)
    return

  // 如果是紧凑态，先展开到完整态
  if (floatingState.value === 'compact') {
    window.electronAPI?.floating.expandToFull()
  }

  const ext = file.name.split('.').pop()?.toLowerCase()
  const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
  const parseableExts = ['docx', 'xlsx', 'txt', 'csv', 'md']

  if (ext && imageExts.includes(ext)) {
    // 图片文件：读取为 dataURL 加入 pendingImages，走 VLM
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        pendingImages.value.push(reader.result)
        nextTick().then(() => {
          inputRef.value?.focus()
          fitWindowHeight()
        })
      }
    }
    reader.readAsDataURL(file)
  }
  else if (ext && parseableExts.includes(ext)) {
    // 可解析文件：解析后发送内容到对话
    MESSAGES.value.push({ role: 'system', content: `正在解析文件: ${file.name}...` })
    try {
      const result = await API.parseDocument(file)
      const msg = MESSAGES.value[MESSAGES.value.length - 1]!
      const truncNote = result.truncated ? '（内容过长，已截断）' : ''
      msg.content = `文件解析完成: ${file.name}${truncNote}`
      chatStream(`以下是文件「${file.name}」的内容：\n\n${result.content}\n\n请分析这个文件的内容。`)
      nextTick().then(scrollToBottom)
    }
    catch (err: any) {
      const msg = MESSAGES.value[MESSAGES.value.length - 1]!
      msg.content = `文件解析失败: ${err?.response?.data?.detail || err.message}`
    }
  }
  else {
    // 其他格式：二进制上传
    MESSAGES.value.push({ role: 'system', content: `正在上传文件: ${file.name}...` })
    try {
      const result = await API.uploadDocument(file)
      const msg = MESSAGES.value[MESSAGES.value.length - 1]!
      msg.content = `文件上传成功: ${file.name}`
      if (result.filePath) {
        chatStream(`请分析我刚上传的文件「${file.name}」，文件完整路径: ${result.filePath}`)
      }
    }
    catch (err: any) {
      const msg = MESSAGES.value[MESSAGES.value.length - 1]!
      msg.content = `文件上传失败: ${err.message}`
    }
  }
  target.value = ''
}

async function handleNewSession() {
  newSession()
  await nextTick()
  await nextTick()
  fitWindowHeight()
}

async function handleNewTemporarySession() {
  newTemporarySession()
  await nextTick()
  await nextTick()
  fitWindowHeight()
}

// ─── 会话历史 ──────────────────────────
const sessions = ref<Array<{
  sessionId: string
  createdAt: string
  lastActiveAt: string
  conversationRounds: number
  temporary: boolean
}>>([])
const loadingSessions = ref(false)

async function fetchSessions() {
  loadingSessions.value = true
  try {
    const res = await API.getSessions()
    sessions.value = res.sessions ?? []
  }
  catch {
    sessions.value = []
  }
  loadingSessions.value = false
  // 会话列表加载完成后刷新窗口高度（列表条目数量影响面板高度）
  await nextTick()
  fitWindowHeight()
}

// 记录是否因打开历史面板而从紧凑态展开到完整态，关闭时需要收回
let _expandedForHistory = false

function toggleHistory() {
  if (!showHistory.value) {
    // 打开历史面板
    if (floatingState.value === 'compact') {
      _expandedForHistory = true
      window.electronAPI?.floating.expandToFull()
    }
    showHistory.value = true
    fetchSessions() // fetchSessions 内部加载完成后统一调用 fitWindowHeight
  }
  else {
    closeHistory()
  }
}

// 关闭历史面板，通过 fitHeight 自适应窗口高度
async function closeHistory() {
  showHistory.value = false
  _expandedForHistory = false
  await nextTick()
  await nextTick()
  fitWindowHeight()
}

async function handleSwitchSession(id: string) {
  await switchSession(id)
  showHistory.value = false
  // 等待 Vue 渲染完消息 DOM 后再计算高度
  await nextTick()
  await nextTick()
  scrollToBottom()
  setupResizeObserver()
  fitWindowHeight()
}

async function handleDeleteSession(id: string) {
  try {
    await API.deleteSession(id)
    sessions.value = sessions.value.filter(s => s.sessionId !== id)
    if (CURRENT_SESSION_ID.value === id) {
      newSession()
    }
    await nextTick()
    fitWindowHeight()
  }
  catch { /* ignore */ }
}

// Esc 键：收起窗口
useEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isExpanded.value) {
    handleCollapse()
  }
})

// 监听新消息到达时的自动滚动和高度调整
useEventListener('token', () => {
  scrollToBottom()
  requestFitHeight()
})
</script>

<template>
  <!-- 球态：序列帧动画悬浮球 -->
  <div
    v-if="floatingState === 'ball'"
    class="floating-ball"
    @pointerdown="onDragPointerDown"
    @pointermove="onDragPointerMove"
    @pointerup="onBallPointerUp"
    @contextmenu.prevent="showBallContextMenu"
    @dragstart.prevent
  >
    <div class="ball-glow" :class="{ 'glow-pulse': isGenerating }" />
    <div class="ball-content">
      <img :src="framePath(frameIndex)" class="ball-frame" draggable="false">
      <img v-if="isNotifying" :src="framePath(0)" class="ball-frame lightbulb-overlay" :class="{ visible: showLightbulb }" draggable="false">
    </div>
    <div class="ball-ring" />
  </div>

  <!-- 紧凑态：方块头像 + 标语 + 输入框（Everywhere 风格） -->
  <div
    v-else-if="floatingState === 'compact'"
    class="floating-compact"
    @pointerdown="onDragPointerDown"
    @pointermove="onDragPointerMove"
    @pointerup="onDragPointerUp"
  >
    <!-- 左侧方块：与球态视觉一致，拖拽移动/点击收起 -->
    <div class="compact-ball" @pointerdown="onCompactBallPointerDown" @pointermove="onDragPointerMove" @pointerup="onCompactBallPointerUp" @dragstart.prevent>
      <div class="ball-content">
        <img :src="framePath(frameIndex)" class="ball-frame" draggable="false">
      </div>
      <div class="ball-ring" />
    </div>
    <!-- 右侧内容（带入场动画） -->
    <div
      class="flex-1 flex flex-col justify-center gap-1 min-w-0 px-4"
      :class="{ 'enter-anim': showContent }"
    >
      <div class="flex items-center gap-1">
        <span class="flex-1 text-white/40 text-xs truncate select-none">有什么可以帮你的吗？</span>
        <div class="flex items-center shrink-0" @pointerdown.stop>
          <button class="action-btn" :class="{ active: IS_TEMPORARY_SESSION }" title="临时聊天" @click="handleNewTemporarySession">🕶</button>
          <button class="action-btn" title="对话历史" @click="toggleHistory">📋</button>
          <button class="action-btn" :class="{ active: isPinned }" :title="isPinned ? '取消固定' : '固定窗口'" @click="togglePin">📌</button>
          <button class="action-btn" title="打开主界面" @click="handleExitFloating"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
          <button class="action-btn" title="退出悬浮球" @click="handleCollapse">✕</button>
        </div>
      </div>
      <div class="flex items-center gap-1 overflow-x-auto" @pointerdown.stop>
        <button
          v-for="skill, idx in QUICK_SKILLS" :key="skill.label"
          class="skill-tag" :class="{ active: activeSkillIndex === idx }"
          @click="handleQuickSkill(idx)"
        >
          {{ skill.label }}
        </button>
      </div>
      <div v-if="pendingImages.length" class="pending-image-bar" @pointerdown.stop>
        <div v-for="img, idx in pendingImages" :key="idx" class="pending-image-item">
          <img :src="img" class="pending-image-thumb" draggable="false">
          <button class="pending-image-remove" @click="removePendingImage(idx)">&#x2715;</button>
        </div>
        <span class="text-white/40 text-xs shrink-0">{{ pendingImages.length }}张截图</span>
      </div>
      <div class="flex items-center gap-1" @pointerdown.stop>
        <input
          ref="inputRef"
          v-model="input"
          class="flex-1 text-sm text-white bg-transparent border-none outline-none p-0"
          type="text"
          :placeholder="pendingImages.length ? '输入提示词后回车发送...' : '输入消息...'"
          @keydown="handleKeydown"
        >
        <button class="action-btn" :class="{ active: showCapturePanel }" title="截屏" @click="handleCapture">📷</button>
        <button class="action-btn" title="上传文件" @click="triggerFileUpload">📎</button>
        <button
          v-if="hasMessages || IS_TEMPORARY_SESSION"
          class="action-btn"
          title="新建对话"
          @click="handleNewSession"
        >
          ➕
        </button>
      </div>
    </div>
  </div>

  <!-- 完整态：输入框在上 + 消息在下（自适应高度） -->
  <div v-else-if="floatingState === 'full'" class="floating-full">
    <!-- 顶部栏：与紧凑态相同的头像+输入区 -->
    <div
      class="compact-header"
      @pointerdown="onDragPointerDown"
      @pointermove="onDragPointerMove"
      @pointerup="onDragPointerUp"
    >
      <div class="compact-ball" @pointerdown="onCompactBallPointerDown" @pointermove="onDragPointerMove" @pointerup="onCompactBallPointerUp" @dragstart.prevent>
        <div class="ball-content">
          <img :src="framePath(frameIndex)" class="ball-frame" draggable="false">
        </div>
        <div class="ball-ring" />
      </div>
      <div class="flex-1 flex flex-col justify-center gap-1 min-w-0 px-4">
        <div class="flex items-center gap-1">
          <span class="flex-1 text-white/40 text-xs truncate select-none">{{ CONFIG.system.ai_name }}</span>
          <div class="flex items-center shrink-0" @pointerdown.stop>
            <button class="action-btn" :class="{ active: IS_TEMPORARY_SESSION }" title="临时聊天" @click="handleNewTemporarySession">🕶</button>
            <button class="action-btn" :class="{ active: showHistory }" title="对话历史" @click="toggleHistory">📋</button>
            <button class="action-btn" :class="{ active: isPinned }" :title="isPinned ? '取消固定' : '固定窗口'" @click="togglePin">📌</button>
            <button class="action-btn" title="打开主界面" @click="handleExitFloating"><svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
            <button class="action-btn" title="收起" @click="handleCollapse">✕</button>
          </div>
        </div>
        <div class="flex items-center gap-1 overflow-x-auto" @pointerdown.stop>
          <button
            v-for="skill, idx in QUICK_SKILLS" :key="skill.label"
            class="skill-tag" :class="{ active: activeSkillIndex === idx }"
            @click="handleQuickSkill(idx)"
          >
            {{ skill.label }}
          </button>
        </div>
        <div v-if="pendingImages.length" class="pending-image-bar" @pointerdown.stop>
          <div v-for="img, idx in pendingImages" :key="idx" class="pending-image-item">
            <img :src="img" class="pending-image-thumb" draggable="false">
            <button class="pending-image-remove" @click="removePendingImage(idx)">&#x2715;</button>
          </div>
          <span class="text-white/40 text-xs shrink-0">{{ pendingImages.length }}张截图</span>
        </div>
        <div class="flex items-center gap-1" @pointerdown.stop>
          <input
            ref="inputRef"
            v-model="input"
            class="flex-1 text-sm text-white bg-transparent border-none outline-none p-0"
            type="text"
            :placeholder="pendingImages.length ? '输入提示词后回车发送...' : '输入消息...'"
            @pointerdown.stop
            @keydown="handleKeydown"
          >
          <button class="action-btn" :class="{ active: showCapturePanel }" title="截屏" @click="handleCapture">📷</button>
          <button class="action-btn" title="上传文件" @click="triggerFileUpload">📎</button>
          <button
            v-if="hasMessages || IS_TEMPORARY_SESSION"
            class="shrink-0 text-white/40 hover:text-white bg-transparent border-none cursor-pointer text-sm"
            title="新建对话"
            @pointerdown.stop
            @click="handleNewSession"
          >
            ➕
          </button>
        </div>
      </div>
    </div>

    <!-- 会话历史面板（使用 opacity-only 过渡，不影响 offsetHeight 测量） -->
    <Transition name="session-fade">
      <div v-if="showHistory" ref="sessionPanelRef" class="session-panel" @pointerdown.stop>
        <div class="flex items-center justify-between px-3 py-1.5 border-b border-white/10">
          <span class="text-white/70 text-xs font-bold">对话历史</span>
          <button
            class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
            @click="closeHistory"
          >
            关闭
          </button>
        </div>
        <div class="session-list">
          <div v-if="loadingSessions" class="text-white/40 text-xs text-center py-3">
            加载中...
          </div>
          <div v-else-if="sessions.length === 0" class="text-white/40 text-xs text-center py-3">
            暂无历史对话
          </div>
          <div
            v-for="s in sessions" :key="s.sessionId"
            class="session-item"
            :class="{ 'bg-white/10': s.sessionId === CURRENT_SESSION_ID }"
            @click="handleSwitchSession(s.sessionId)"
          >
            <div class="flex-1 min-w-0">
              <div class="text-white/80 text-xs truncate">
                <span v-if="s.temporary" class="temporary-tag">临时</span>
                {{ s.sessionId.slice(0, 8) }}...
              </div>
              <div class="text-white/40 text-xs">
                {{ formatRelativeTime(s.lastActiveAt) }} · {{ s.conversationRounds }} 轮
              </div>
            </div>
            <button
              class="text-white/30 hover:text-red-400 bg-transparent border-none cursor-pointer text-xs shrink-0 ml-2"
              title="删除"
              @click.stop="handleDeleteSession(s.sessionId)"
            >
              🗑
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 窗口截屏选择面板 -->
    <Transition name="session-fade">
      <div v-if="showCapturePanel" ref="capturePanelRef" class="capture-panel" @pointerdown.stop>
        <div class="flex items-center justify-between px-3 py-1.5 border-b border-white/10">
          <span class="text-white/70 text-xs font-bold">选择要截取的窗口</span>
          <button
            class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
            @click="closeCapturePanel"
          >
            关闭
          </button>
        </div>
        <div class="capture-grid">
          <div v-if="loadingCapture" class="text-white/40 text-xs text-center py-3 col-span-2">
            加载中...
          </div>
          <div v-else-if="capturePermissionDenied" class="text-white/40 text-xs text-center py-3 col-span-2">
            需要屏幕录制权限，请前往<br>系统设置 &gt; 隐私与安全性 &gt; 屏幕录制<br>中授权 NagaAgent
            <button class="mt-2 px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 text-xs border-none cursor-pointer transition-colors" @click="openScreenSettings">
              打开系统设置
            </button>
          </div>
          <div v-else-if="captureSources.length === 0" class="text-white/40 text-xs text-center py-3 col-span-2">
            未检测到可截取的窗口<br>
            <span class="text-white/30">可能是屏幕录制权限未授予，请检查<br>系统设置 &gt; 隐私与安全性 &gt; 屏幕录制</span>
            <br>
            <button class="mt-2 px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white/60 hover:text-white/80 text-xs border-none cursor-pointer transition-colors" @click="openScreenSettings">
              打开系统设置
            </button>
          </div>
          <div
            v-for="src in captureSources" :key="src.id"
            class="capture-item"
            @click="selectCaptureSource(src)"
          >
            <img :src="src.thumbnail" class="capture-thumb" draggable="false">
            <span class="capture-name">{{ src.name }}</span>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 消息区域 -->
    <ScrollPanel
      ref="scrollPanelRef"
      class="w-full flex-1 min-h-0 border-t border-white/6"
      :class="{ 'enter-anim': showContent }"
      :pt="{ barY: { class: 'w-2! rounded! bg-#373737! transition!' } }"
    >
      <div ref="messageContentRef" class="p-3 grid gap-3">
        <MessageItem
          v-for="item, index in MESSAGES" :key="index"
          :role="item.role" :content="item.content"
          :reasoning="item.reasoning" :sender="item.sender"
          :class="(item.generating && index === MESSAGES.length - 1) || 'border-b border-white/6'"
        />
      </div>
    </ScrollPanel>

    <!-- 工具状态提示 -->
    <Transition name="session-fade">
      <div v-if="toolMessage" class="text-white/50 text-xs px-3 py-1 shrink-0 border-t border-white/6">
        {{ toolMessage }}
      </div>
    </Transition>
  </div>

  <!-- 隐藏的文件上传 input -->
  <input
    ref="fileInputRef"
    type="file"
    accept=".docx,.xlsx,.txt,.csv,.md,.pdf,.png,.jpg,.jpeg,.gif,.webp"
    class="hidden"
    @change="handleFileUpload"
  >
</template>

<style scoped>
/* ========== 球态 ========== */
.floating-ball {
  position: relative;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  cursor: pointer;
  touch-action: none;
  transition: filter 0.2s ease;
}

/* 彩色光环（保持在窗口 100x100 内，避免方形裁切） */
.ball-glow {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, #ac45f1, #7a7ef4, #3dc6f8, #55a9f6, #ac45f1);
  opacity: 0.7;
  z-index: 0;
  animation: glow-spin 6s linear infinite;
}

@keyframes glow-spin {
  to { transform: rotate(360deg); }
}

/* 生成中：旋转加速 + 透明度脉冲 */
.ball-glow.glow-pulse {
  animation: glow-spin 3s linear infinite, glow-pulse 1.5s ease-in-out infinite;
}

@keyframes glow-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}

.ball-content {
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  overflow: hidden;
  z-index: 1;
  background: radial-gradient(circle at 40% 35%, #2a1810, #110901);
}

.ball-frame {
  width: 100%;
  height: 100%;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
  -webkit-user-drag: none;
}

/* 灯泡通知覆盖层：绝对定位叠在眨眼帧上方，独立闪烁 */
.lightbulb-overlay {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.lightbulb-overlay.visible {
  opacity: 1;
}

/* 边框环 */
.ball-ring {
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  border: 1.5px solid rgba(255, 255, 255, 0.12);
  z-index: 2;
  pointer-events: none;
  transition: border-color 0.3s;
}

.floating-ball:hover {
  filter: brightness(1.08);
}

.floating-ball:hover .ball-ring {
  border-color: rgba(255, 255, 255, 0.4);
}

.floating-ball:hover .ball-glow {
  opacity: 0.8;
}

/* ========== 紧凑态（Everywhere 风格） ========== */
.floating-compact {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: stretch;
  background: #110901;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.compact-ball {
  width: 100px;
  height: 100px;
  flex-shrink: 0;
  cursor: pointer;
  position: relative;
  background: radial-gradient(circle at 40% 35%, #2a1810, #110901);
  transition: filter 0.2s ease;
}

.compact-ball:hover {
  filter: brightness(1.08);
}

/* 紧凑/完整态的球无光环，内容占满 */
.compact-ball .ball-content {
  inset: 0;
  background: none;
}

.compact-ball .ball-ring {
  inset: 0;
}

.compact-ball:hover .ball-ring {
  border-color: rgba(255, 255, 255, 0.4);
}

/* ========== 操作按钮 ========== */
.action-btn {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.2s, background-color 0.2s;
  white-space: nowrap;
}

.action-btn:hover {
  color: rgba(255, 255, 255, 0.8);
  background-color: rgba(255, 255, 255, 0.08);
}

.action-btn.active {
  color: rgba(255, 255, 255, 0.8);
}

/* ========== 快捷技能标签 ========== */
.skill-tag {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 10px;
  transition: color 0.2s, background-color 0.2s, border-color 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.skill-tag:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.25);
}

.skill-tag.active {
  color: rgba(255, 255, 255, 0.95);
  background: rgba(172, 69, 241, 0.25);
  border-color: rgba(172, 69, 241, 0.5);
}

/* ========== 完整态 ========== */
.floating-full {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #110901;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.compact-header {
  display: flex;
  align-items: stretch;
  flex-shrink: 0;
  height: 100px;
  max-height: 100px;
  overflow: hidden;
}

/* ========== 内容入场动画 ========== */
@keyframes enter-fade-up {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.enter-anim {
  animation: enter-fade-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

/* ========== 会话历史面板 ========== */
.session-panel {
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.4);
}

.session-list {
  overflow-y: auto;
  max-height: 12rem;
}

.session-list::-webkit-scrollbar {
  width: 6px;
}

.session-list::-webkit-scrollbar-track {
  background: transparent;
}

.session-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.session-list::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.session-item {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  cursor: pointer;
  transition: background-color 0.15s;
}

.session-item:hover {
  background-color: rgba(255, 255, 255, 0.06);
}

/* ========== 临时会话标记 ========== */
.temporary-tag {
  display: inline-block;
  font-size: 9px;
  padding: 0 4px;
  margin-right: 4px;
  border-radius: 3px;
  background: rgba(255, 165, 0, 0.2);
  color: rgba(255, 165, 0, 0.9);
  border: 1px solid rgba(255, 165, 0, 0.3);
  vertical-align: middle;
  line-height: 14px;
}

/* ========== 会话面板过渡（仅 opacity，不影响布局测量） ========== */
.session-fade-enter-active {
  transition: opacity 0.15s ease;
}

.session-fade-leave-active {
  transition: opacity 0.1s ease;
}

.session-fade-enter-from,
.session-fade-leave-to {
  opacity: 0;
}

/* ========== 窗口截屏面板 ========== */
.capture-panel {
  flex-shrink: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.4);
}

/* ========== 待发送截图指示条 ========== */
.pending-image-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
}

.pending-image-thumb {
  width: 32px;
  height: 18px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  pointer-events: none;
  flex-shrink: 0;
}

.pending-image-remove {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  font-size: 10px;
  padding: 0 4px;
  flex-shrink: 0;
  transition: color 0.15s;
}

.pending-image-remove:hover {
  color: rgba(255, 100, 100, 0.8);
}

.capture-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  padding: 8px;
  overflow-y: auto;
  max-height: 14rem;
}

.capture-grid::-webkit-scrollbar {
  width: 6px;
}

.capture-grid::-webkit-scrollbar-track {
  background: transparent;
}

.capture-grid::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}

.capture-item {
  cursor: pointer;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: border-color 0.15s;
}

.capture-item:hover {
  border-color: rgba(172, 69, 241, 0.5);
}

.capture-thumb {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  pointer-events: none;
  user-select: none;
}

.capture-name {
  display: block;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.6);
  padding: 2px 6px 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
