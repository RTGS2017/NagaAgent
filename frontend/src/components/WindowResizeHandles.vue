<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  visible: boolean
  titleBarHeight?: number
}>(), { titleBarHeight: 32 })

const MIN_WIDTH = 800
const MIN_HEIGHT = 600

type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw' | null

const resizing = ref<ResizeEdge>(null)
const startX = ref(0)
const startY = ref(0)
const startBounds = ref<{ x: number, y: number, width: number, height: number } | null>(null)

async function getBounds() {
  if (!window.electronAPI?.getBounds)
    return null
  return await window.electronAPI.getBounds()
}

function setBounds(bounds: { x?: number, y?: number, width?: number, height?: number }) {
  window.electronAPI?.setBounds(bounds)
}

async function onResizeStart(edge: ResizeEdge, e: MouseEvent) {
  if (!edge || !window.electronAPI || resizing.value)
    return
  e.preventDefault()
  e.stopPropagation()
  const bounds = await getBounds()
  if (!bounds)
    return
  resizing.value = edge
  startX.value = e.screenX
  startY.value = e.screenY
  startBounds.value = { ...bounds }
}

function onMouseMove(e: MouseEvent) {
  const edge = resizing.value
  if (!edge || !startBounds.value)
    return

  const dx = e.screenX - startX.value
  const dy = e.screenY - startY.value
  let { x, y, width, height } = startBounds.value

  if (edge.includes('e')) {
    width = Math.max(MIN_WIDTH, width + dx)
  }
  if (edge.includes('w')) {
    const newWidth = Math.max(MIN_WIDTH, width - dx)
    x += width - newWidth
    width = newWidth
  }
  if (edge.includes('s')) {
    height = Math.max(MIN_HEIGHT, height + dy)
  }
  if (edge.includes('n')) {
    const newHeight = Math.max(MIN_HEIGHT, height - dy)
    y += height - newHeight
    height = newHeight
  }

  setBounds({ x, y, width, height })
}

function onMouseUp() {
  if (resizing.value) {
    resizing.value = null
    startBounds.value = null
  }
}

onMounted(() => {
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', onMouseUp)
})
</script>

<template>
  <div
    v-if="visible"
    class="resize-handles"
    aria-hidden="true"
  >
    <!-- 四边 -->
    <div
      class="handle handle-n"
      @mousedown="onResizeStart('n', $event)"
    />
    <div
      class="handle handle-s"
      @mousedown="onResizeStart('s', $event)"
    />
    <div
      class="handle handle-e"
      @mousedown="onResizeStart('e', $event)"
    />
    <div
      class="handle handle-w"
      @mousedown="onResizeStart('w', $event)"
    />
    <!-- 四角 -->
    <div
      class="handle handle-ne"
      @mousedown="onResizeStart('ne', $event)"
    />
    <div
      class="handle handle-nw"
      @mousedown="onResizeStart('nw', $event)"
    />
    <div
      class="handle handle-se"
      @mousedown="onResizeStart('se', $event)"
    />
    <div
      class="handle handle-sw"
      @mousedown="onResizeStart('sw', $event)"
    />
  </div>
</template>

<style scoped>
.resize-handles {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9998;
}

.handle {
  position: absolute;
  pointer-events: auto;
  -webkit-app-region: no-drag;
}

/* 顶边 - 需在标题栏下方留出空间，避免与拖拽冲突 */
.handle-n {
  top: v-bind('`${props.titleBarHeight}px`');
  left: 12px;
  right: 12px;
  height: 6px;
  cursor: n-resize;
}

.handle-s {
  bottom: 0;
  left: 12px;
  right: 12px;
  height: 6px;
  cursor: s-resize;
}

.handle-e {
  top: 12px;
  right: 0;
  bottom: 12px;
  width: 6px;
  cursor: e-resize;
}

.handle-w {
  top: 12px;
  left: 0;
  bottom: 12px;
  width: 6px;
  cursor: w-resize;
}

.handle-ne {
  top: v-bind('`${props.titleBarHeight}px`');
  right: 0;
  width: 12px;
  height: 12px;
  cursor: ne-resize;
}

.handle-nw {
  top: 32px;
  left: 0;
  width: 12px;
  height: 12px;
  cursor: nw-resize;
}

.handle-se {
  bottom: 0;
  right: 0;
  width: 12px;
  height: 12px;
  cursor: se-resize;
}

.handle-sw {
  bottom: 0;
  left: 0;
  width: 12px;
  height: 12px;
  cursor: sw-resize;
}
</style>
