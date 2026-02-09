<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { computed } from 'vue'
import { useLink } from 'vue-router'
import brain from '@/assets/icons/brain.png'
import chip from '@/assets/icons/chip.png'
import naga from '@/assets/icons/naga.png'
import toolkit from '@/assets/icons/toolkit.png'
import ArkButton from '@/components/ArkButton.vue'

const { height } = useWindowSize()
const scale = computed(() => height.value / 720)
</script>

<template>
  <div class="flex flex-col items-start justify-center px-1/16">
    <div
      class="grid grid-rows-3 gap-3 *:gap-3" :style="{
        transformOrigin: 'left',
        transform: `perspective(1000px) rotateY(8deg) scale(${scale})`,
      }"
    >
      <div class="relative size-full">
        <div class="absolute -left-12 right-1/2 top-2 bottom-2">
          <ArkButton class="size-full bg-#f00! z-1" disabled>
            <div class="size-full">
              娜迦EXE测试版
            </div>
          </ArkButton>
        </div>
        <ArkButton class="size-full" :icon="naga" @click="useLink({ to: '/chat' }).navigate">
          <div class="size-full flex items-center justify-end mr-4em">
            对话
          </div>
        </ArkButton>
      </div>
      <div class="grid grid-cols-2 -translate-x-1/5">
        <ArkButton :icon="brain" title="记忆<br>云海" disabled />
        <ArkButton :icon="toolkit" title="技能<br>工坊" @click="useLink({ to: '/skill' }).navigate" />
      </div>
      <div class="grid grid-cols-2">
        <div class="flex flex-col">
          <div class="bg-#363837 text-white p-2 text-sm">
            参数设置
          </div>
          <div class="grow grid grid-cols-2 font-serif font-bold lh-none">
            <ArkButton @click="useLink({ to: '/model' }).navigate">
              <div class="size-full text-lg">人格投影</div>
            </ArkButton>
            <ArkButton disabled>
              <div class="size-full text-lg">记忆链接</div>
            </ArkButton>
          </div>
        </div>
        <ArkButton :icon="chip" title="终端<br>设置" @click="useLink({ to: '/config' }).navigate" />
      </div>
    </div>
  </div>
</template>
