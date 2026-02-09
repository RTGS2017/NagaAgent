<script setup lang="ts">
import { computed, ref } from 'vue'
import { CONFIG } from '@/utils/config'
import Markdown from './Markdown.vue'

const props = defineProps<{
  role: 'system' | 'user' | 'assistant'
  content: string
  reasoning?: string
  sender?: string
}>()

const showReasoning = ref(false)

const COLOR_MAP = {
  system: 'bg-gray-500',
  user: 'bg-blue-500',
  assistant: 'bg-green-500',
}

const displayName = computed(() => {
  if (props.sender) return props.sender
  if (props.role === 'user') return CONFIG.value.ui.user_name
  if (props.role === 'assistant') return CONFIG.value.system.ai_name
  return '系统'
})

const dotColor = computed(() => {
  if (props.sender) return 'bg-orange-500'
  return COLOR_MAP[props.role]
})
</script>

<template>
  <div>
    <div class="flex flex-row gap-2 items-center">
      <div class="w-4 h-4 rounded-full" :class="dotColor" />
      <div class="font-bold text-white">{{ displayName }}</div>
    </div>
    <div v-if="reasoning" class="mx-2 mt-1">
      <button
        class="text-xs text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer p-0"
        @click="showReasoning = !showReasoning"
      >
        {{ showReasoning ? '▼' : '▶' }} 思考过程
      </button>
      <div
        v-if="showReasoning"
        class="text-white/50 text-sm mt-1 pl-2 border-l-2 border-white/20"
      >
        <Markdown :source="reasoning" />
      </div>
    </div>
    <div class="text-white mx-2 relative">
      <Markdown :source="content || 'Generating...'" />
    </div>
  </div>
</template>
