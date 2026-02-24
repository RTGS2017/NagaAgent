<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { computed } from 'vue'
import { useLink } from 'vue-router'
import brain from '@/assets/icons/brain.png'
import chip from '@/assets/icons/chip.png'
import market from '@/assets/icons/market.svg'
import musicBoxIcon from '@/assets/icons/musicbox3.png'
import naga from '@/assets/icons/naga.png'
import toolkit from '@/assets/icons/toolkit.png'
import ArkButton from '@/components/ArkButton.vue'
import { useParallax } from '@/composables/useParallax'
import { CONFIG } from '@/utils/config'

const { height } = useWindowSize()
const scale = computed(() => height.value / 720)

const { rx, ry, tx, ty } = useParallax({ rotateX: 5, rotateY: 4, translateX: 15, translateY: 10, invertRotate: true })

function enterFloatingMode() {
  CONFIG.value.floating.enabled = true
  window.electronAPI?.floating.enter()
}
</script>

<template>
  <div class="flex flex-col items-start justify-center px-1/16">
    <div
      class="grid grid-rows-4 gap-3 *:gap-3 will-change-transform select-none" :style="{
        transformOrigin: 'left',
        transform: `perspective(1000px) rotateX(${rx}deg) rotateY(${8 + ry}deg) translate(${tx}px, ${ty}px) scale(${scale})`,
      }"
    >
      <div class="relative size-full">
        <div class="absolute -left-12 right-1/2 top-2 bottom-2">
          <ArkButton class="size-full bg-#f00! z-1" disabled>
            <div class="size-full">
              娜迦协议Demo
            </div>
          </ArkButton>
        </div>
        <ArkButton class="size-full" :icon="naga" @click="useLink({ to: '/chat' }).navigate">
          <div class="size-full flex items-center justify-end mr-4em text-4xl">
            对话
          </div>
        </ArkButton>
      </div>
      <div class="grid grid-cols-2 -translate-x-1/5">
        <ArkButton :icon="brain" title="记忆<br>云海" @click="useLink({ to: '/mind' }).navigate" />
        <ArkButton :icon="toolkit" title="技能<br>工坊" @click="useLink({ to: '/skill' }).navigate" />
      </div>
      <div class="grid grid-cols-2 min-w-0">
        <div class="flex flex-col min-w-0 relative">
          <!-- 悬浮按钮 -->
          <button class="float-btn absolute -left-16 top-0 bottom-0 w-12 flex flex-col items-center justify-center bg-white bg-op-90 border-none shadow backdrop-blur-md transition hover:brightness-105 hover:bg-op-100" @click="enterFloatingMode">
            <span class="text-lg font-serif font-bold text-black">悬浮</span>
            <svg class="w-8 h-8" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="12" cy="12" r="9" stroke="#B9B9B9" stroke-width="1.5" />
              <path d="M12 4C12 4 6 8 6 12C6 16 12 20 12 20" stroke="#B9B9B9" stroke-width="1.2" stroke-linecap="round" opacity="0.8" />
              <path d="M12 4C12 4 18 8 18 12C18 16 12 20 12 20" stroke="#B9B9B9" stroke-width="1.2" stroke-linecap="round" opacity="0.6" />
              <ellipse cx="9" cy="10" rx="1.5" ry="2" fill="#B9B9B9" opacity="0.6" />
            </svg>
          </button>

          <div class="bg-#363837 text-white p-2 text-sm">
            参数设置
          </div>
          <div class="grow grid grid-cols-2 font-serif font-bold lh-none min-w-0">
            <ArkButton class="min-w-0" @click="useLink({ to: '/model' }).navigate">
              <div class="size-full text-lg">模型链接</div>
            </ArkButton>
            <ArkButton class="min-w-0" @click="useLink({ to: '/memory' }).navigate">
              <div class="size-full text-lg">记忆链接</div>
            </ArkButton>
          </div>
        </div>
        <ArkButton class="min-w-0" :icon="chip" title="终端<br>设置" @click="useLink({ to: '/config' }).navigate" />
      </div>
      <div class="grid grid-cols-2 -translate-x-1/5">
        <ArkButton class="market-btn" :icon="market" title="枢机<br>集市" disabled />
        <ArkButton class="music-btn" :icon="musicBoxIcon" title="音律坊" @click="useLink({ to: '/music' }).navigate" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.market-btn :deep(img) {
  filter: grayscale(1) brightness(0.6) opacity(0.5);
}

.market-btn {
  background-color: #d9d9d9 !important;
  color: #a0a0a0 !important;
  cursor: not-allowed !important;
}

.music-btn :deep(img) {
  filter: brightness(1.3) opacity(0.2);
  width: 4.5rem;
  height: 4.5rem;
  object-fit: contain;
  right: 0.6rem;
}
</style>
