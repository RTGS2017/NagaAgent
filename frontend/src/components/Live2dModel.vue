<script lang="ts">
import { Live2DModel } from 'pixi-live2d-display/cubism4'
import * as PIXI from 'pixi.js'
import { computed, nextTick, onMounted, onUnmounted, useTemplateRef, watch } from 'vue'

declare global {
  interface Window {
    PIXI: typeof PIXI
  }
}
window.PIXI = PIXI
</script>

<script setup lang="ts">
const { source, width, height, x, y, scale, ssaa } = defineProps<{
  source: string
  width: number
  height: number
  x: number
  y: number
  scale: number
  ssaa: number
}>()

let app: PIXI.Application

const computedScale = computed(() => scale * ssaa)
const computedWidth = computed(() => width * ssaa)
const computedHeight = computed(() => height * ssaa)

const canvas = useTemplateRef('canvas')

onMounted(async () => {
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

      app.stage.addChild(model)

      onCleanUp(() => {
        app.stage.removeChild(model)
        model.destroy()
        handles.forEach(handle => handle.stop())
      })
    }
    catch (error) {
      console.error('Failed to initialize Live2D:', error)
    }
  }, { immediate: true })
})

onUnmounted(() => app && app.destroy())
</script>

<template>
  <canvas ref="canvas" :width="computedWidth" :height="computedHeight" :style="{ zoom: 1 / ssaa }" />
</template>
