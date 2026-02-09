<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { computed } from 'vue'
import Live2dModel from '@/components/Live2dModel.vue'
import TitleBar from '@/components/TitleBar.vue'
import { CONFIG } from '@/utils/config'

const { width, height } = useWindowSize()
const scale = computed(() => height.value / (10000 - CONFIG.value.web_live2d.model.size))

const isElectron = !!window.electronAPI
const titleBarPadding = isElectron ? '32px' : '0px'
</script>

<template>
  <TitleBar />
  <div class="h-full sunflower" :style="{ paddingTop: titleBarPadding }">
    <div class="absolute top-0 left-0 size-full -z-1">
      <img src="/assets/light.png" alt="" class="absolute right-0 bottom-0 w-80vw h-60vw op-40 -z-1">
      <Live2dModel
        v-bind="CONFIG.web_live2d.model"
        :width="width" :height="height"
        :scale="scale" :ssaa="CONFIG.web_live2d.ssaa"
      />
    </div>
    <div class="h-full px-1/8 py-1/12 grid-container">
      <RouterView v-slot="{ Component, route }">
        <Transition :name="route.path === '/' ? 'slide-out' : 'slide-in'">
          <component
            :is="Component"
            :key="route.fullPath"
            class="grid-item size-full"
          />
        </Transition>
      </RouterView>
    </div>
  </div>
</template>

<style scoped>
.sunflower {
  border-image-source: url('/assets/sunflower.9.png');
  border-image-slice: 50%;
  border-image-width: 10em;
}

.grid-container {
  display: grid;
  grid-template-columns: 1fr;
}

.grid-item {
  grid-column: 1;
  grid-row: 1;
}

.slide-in-enter-from {
  transform: translateX(-100%);
}
.slide-in-leave-to {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-in-leave-active,
.slide-in-enter-active,
.slide-out-leave-active,
.slide-out-enter-active {
  transition: all 1s ease;
}

.slide-out-enter-from {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-out-leave-to {
  opacity: 0;
  transform: translateX(-100%);
}
</style>
