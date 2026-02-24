<script lang="ts">
import * as PIXI from 'pixi.js'

declare global {
  interface Window {
    PIXI: typeof PIXI
  }
}
</script>

<script setup lang="ts">
import { Live2DModel } from 'pixi-live2d-display/cubism4'
import { computed, nextTick, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import { CONFIG } from '@/utils/config'
import { destroyController, initController, startTracking, stopTracking, trackingCalibration, updateTracking } from '@/utils/live2dController'
const { source, width, height, x, y, scale, ssaa } = defineProps<{
  source: string
  width: number
  height: number
  x: number
  y: number
  scale: number
  ssaa: number
}>()

const emit = defineEmits<{
  modelReady: [pos: { faceX: number, faceY: number }]
}>()

window.PIXI = PIXI

let app: PIXI.Application

const computedScale = computed(() => scale * ssaa)
const computedWidth = computed(() => width * ssaa)
const computedHeight = computed(() => height * ssaa)

const canvas = useTemplateRef('canvas')
let isDragging = false
// 按住超过 delay 后才开启追踪；0 表示点击即追踪
let trackingHoldTimer: ReturnType<typeof setTimeout> | null = null
let trackingActive = false // 是否已过延迟、正在追踪

// 模型面部在屏幕上的位置（由 recalcModelCenter 更新）
let modelFaceScreenX = 0
let modelFaceScreenY = 0
// 准星位置（响应式，供模板绑定）
const markerPos = ref({ left: '0px', top: '0px' })

// ─── Window 级别事件监听（绕过 CSS 层叠遮挡） ───────
const INTERACTIVE_SELECTOR = 'button, input, textarea, select, a, [contenteditable], label, [role="button"]'

function isInteractiveTarget(el: EventTarget | null): boolean {
  if (!(el instanceof Element))
    return false
  if (el.closest(INTERACTIVE_SELECTOR))
    return true
  if (el.closest('.box, .session-panel, .p-scrollpanel'))
    return true
  return false
}

function clearHoldTimer() {
  if (trackingHoldTimer !== null) {
    clearTimeout(trackingHoldTimer)
    trackingHoldTimer = null
  }
}

function onWindowPointerDown(e: PointerEvent) {
  if (isInteractiveTarget(e.target))
    return
  isDragging = true
  trackingActive = false
  clearHoldTimer()
  const delay = CONFIG.value.web_live2d?.tracking_hold_delay_ms ?? 1000
  if (delay <= 0) {
    trackingActive = true
    startTracking()
    updateTrackingFromPointer(e)
    return
  }
  trackingHoldTimer = setTimeout(() => {
    trackingHoldTimer = null
    if (isDragging) {
      trackingActive = true
      startTracking()
      // 位置由后续 pointermove 更新
    }
  }, delay)
}

function onWindowPointerMove(e: PointerEvent) {
  if (!isDragging)
    return
  if (trackingActive)
    updateTrackingFromPointer(e)
}

function onWindowPointerUp(_e: PointerEvent) {
  if (!isDragging)
    return
  clearHoldTimer()
  isDragging = false
  if (trackingActive) {
    trackingActive = false
    stopTracking()
  }
}

function clamp(v: number, min: number, max: number) {
  return Math.max(min, Math.min(max, v))
}

function updateTrackingFromPointer(e: PointerEvent) {
  // 从模型面部位置到鼠标的方向，归一化到 [-1, 1]
  const range = Math.min(window.innerWidth, window.innerHeight) * 0.4
  const normalizedX = clamp((e.clientX - modelFaceScreenX) / range, -1, 1)
  // 屏幕 Y 向下，Live2D Y 向上 → 取反
  const normalizedY = clamp(-(e.clientY - modelFaceScreenY) / range, -1, 1)
  updateTracking(normalizedX, normalizedY)
}

onMounted(async () => {
  window.addEventListener('pointerdown', onWindowPointerDown)
  window.addEventListener('pointermove', onWindowPointerMove)
  window.addEventListener('pointerup', onWindowPointerUp)

  if (!canvas.value)
    return

  app = new PIXI.Application({
    view: canvas.value,
    width: computedWidth.value,
    height: computedHeight.value,
    antialias: true,
    backgroundAlpha: 0,
    resizeTo: canvas.value,
  })

  watch(() => [width, height, ssaa], () => nextTick().then(() => app.resize()))

  watch(() => source, async (source, _, onCleanUp) => {
    try {
      const rawModel = await Live2DModel.from(source)
      const model = Object.assign(rawModel, {
        rawWidth: rawModel.width,
        rawHeight: rawModel.height,
      })

      const computedX = computed(() => width * ssaa * (1 + x) - model.rawWidth * computedScale.value)
      const computedY = computed(() => height * ssaa * (1 + y) - model.rawHeight * computedScale.value)

      const handles = [
        watch(computedScale, scale => model.scale.set(scale), { immediate: true }),
        watch(computedX, x => model.x = x / 2, { immediate: true }),
        watch(computedY, y => model.y = y / 2, { immediate: true }),
      ]

      // 计算模型面部在屏幕上的位置（PIXI坐标 / ssaa = 屏幕坐标）
      function recalcModelCenter() {
        const s = computedScale.value
        const faceY = CONFIG.value.web_live2d.face_y_ratio ?? 0.25
        modelFaceScreenX = (model.x + model.rawWidth * s * 0.5) / ssaa
        modelFaceScreenY = (model.y + model.rawHeight * s * faceY) / ssaa
        markerPos.value = { left: `${modelFaceScreenX}px`, top: `${modelFaceScreenY}px` }
        emit('modelReady', { faceX: modelFaceScreenX, faceY: modelFaceScreenY })
      }
      // 响应 face_y_ratio 配置变化（设置界面滑块调节时实时更新）
      const centerHandle = watch(
        [computedScale, computedX, computedY, () => CONFIG.value.web_live2d.face_y_ratio],
        recalcModelCenter,
        { immediate: true },
      )

      model.autoInteract = false
      app.stage.addChild(model)
      await initController(rawModel, source)

      onCleanUp(() => {
        destroyController()
        app.stage.removeChild(model)
        model.destroy()
        handles.forEach(handle => handle.stop())
        centerHandle.stop()
      })
    }
    catch (error) {
      console.error('Failed to initialize Live2D:', error)
    }
  }, { immediate: true })
})

onUnmounted(() => {
  window.removeEventListener('pointerdown', onWindowPointerDown)
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerUp)
  if (app)
    app.destroy()
})
</script>

<template>
  <canvas
    ref="canvas"
    :width="computedWidth" :height="computedHeight"
    :style="{ transform: `scale(${1 / ssaa})`, transformOrigin: '0 0', touchAction: 'none' }"
  />
  <!-- 视角校准准星 -->
  <div
    v-if="trackingCalibration"
    class="fixed pointer-events-none z-9999"
    :style="{ ...markerPos, transform: 'translate(-50%, -50%)' }"
  >
    <div class="w-6 h-6 border-2 border-red rounded-full" />
    <div class="absolute left-1/2 top-0 w-0.5 h-full bg-red -translate-x-1/2" />
    <div class="absolute top-1/2 left-0 h-0.5 w-full bg-red -translate-y-1/2" />
  </div>
</template>
