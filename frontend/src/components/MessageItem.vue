<script setup lang="ts">
import type { Message, ToolEvent } from '@/utils/session'
import { computed, onUnmounted, ref, watch } from 'vue'
import { CONFIG } from '@/utils/config'
import Markdown from './Markdown.vue'

const props = defineProps<Message>()

const GENERATING_PHRASES = [
  'Generating...',
  'Thinking...',
  'Composing...',
  'Crafting...',
  'Processing...',
  'Pondering...',
  'Formulating...',
  'Conjuring...',
  'Weaving...',
  'Brewing...',
]

const phraseIndex = ref(Math.floor(Math.random() * GENERATING_PHRASES.length))
let phraseTimer: ReturnType<typeof setInterval> | undefined

const generatingText = computed(() => {
  return GENERATING_PHRASES[phraseIndex.value % GENERATING_PHRASES.length] ?? 'Generating...'
})

const displaySource = computed(() => {
  if (props.content)
    return props.content
  if (props.reasoning)
    return ''
  if (props.generating)
    return generatingText.value
  return ''
})

const shouldAnimate = computed(() => props.generating && !props.content && !props.reasoning)

watch(shouldAnimate, (active) => {
  if (active && !phraseTimer) {
    phraseTimer = setInterval(() => {
      phraseIndex.value = Math.floor(Math.random() * GENERATING_PHRASES.length)
    }, 2000)
  }
  else if (!active && phraseTimer) {
    clearInterval(phraseTimer)
    phraseTimer = undefined
  }
}, { immediate: true })

onUnmounted(() => {
  if (phraseTimer) {
    clearInterval(phraseTimer)
    phraseTimer = undefined
  }
})

const COLOR_MAP = {
  system: 'bg-gray-500',
  user: 'bg-blue-500',
  assistant: 'bg-green-500',
  info: 'bg-yellow-600',
}

const ROLE_MAP = {
  system: '系统',
  user: CONFIG.value.ui.user_name,
  assistant: CONFIG.value.system.ai_name,
  info: '提示',
}

const reasoningExpanded = ref(true)

function formatToolPayload(value: unknown): string {
  if (value == null)
    return ''
  if (typeof value === 'string')
    return value
  try {
    return JSON.stringify(value, null, 2)
  }
  catch {
    return String(value)
  }
}

function toolSummary(event: ToolEvent): string {
  const name = event.name || '工具'
  if (event.type === 'tool_call') {
    return `🔧 ${name}`
  }
  return `${event.isError ? '❌' : '✅'} ${name}`
}

function toolBody(event: ToolEvent): string {
  if (event.type === 'tool_call') {
    return formatToolPayload(event.args)
  }
  return formatToolPayload(event.result)
}
</script>

<template>
  <!-- info 标记：居中分隔线样式 -->
  <div v-if="role === 'info'" class="info-divider">
    <span class="info-text">{{ content }}</span>
  </div>
  <!-- 普通消息 -->
  <div v-else>
    <div class="flex flex-row gap-2 items-center">
      <div class="w-4 h-4 rounded-full" :class="sender ? 'bg-orange-500' : COLOR_MAP[role]" />
      <div class="font-bold text-white">{{ sender ?? ROLE_MAP[role] }}</div>
    </div>
    <!-- 思考过程（reasoning）：生成中展开显示，生成完成后可折叠 -->
    <div v-if="reasoning" class="mx-2 mt-1 reasoning-block">
      <div
        class="reasoning-header"
        @click="reasoningExpanded = !reasoningExpanded"
      >
        <span v-if="generating" class="reasoning-spinner" />
        <span>{{ generating ? '思考中' : '思考过程' }}</span>
        <span v-if="!generating" class="reasoning-toggle">{{ reasoningExpanded ? '收起' : '展开' }}</span>
      </div>
      <div v-show="reasoningExpanded" class="reasoning-content">
        <Markdown :source="reasoning" />
      </div>
    </div>
    <div class="text-white mx-2 relative message-body">
      <div v-if="!content && !reasoning && generating && status" class="status-line">
        <span class="status-spinner" />
        <span class="status-text">{{ status }}</span>
      </div>
      <Markdown v-else :source="displaySource" />
      <div v-if="toolEvents?.length" class="tool-events">
        <details
          v-for="(event, index) in toolEvents"
          :key="`${event.type}-${event.toolCallId || event.name || 'tool'}-${index}`"
          class="tool-result"
        >
          <summary>{{ toolSummary(event) }}</summary>
          <pre v-if="toolBody(event)" class="tool-result-body">{{ toolBody(event) }}</pre>
        </details>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-body {
  overflow-wrap: break-word;
  word-break: break-word;
  min-width: 0;
  overflow: hidden;
}

/* :deep() 穿透 v-html 渲染的所有子元素 */
.message-body :deep(*) {
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: break-word;
}

.message-body :deep(pre) {
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.message-body :deep(table) {
  display: block;
  overflow-x: auto;
}

.message-body :deep(img) {
  max-width: 100%;
  height: auto;
}

/* 工具结果：可折叠区块 */
.message-body :deep(.tool-result) {
  margin: 0.3rem 0;
  border-left: 2px solid rgba(255, 255, 255, 0.15);
  border-radius: 0 4px 4px 0;
  background: rgba(255, 255, 255, 0.03);
  font-size: 0.85rem;
}
.message-body :deep(.tool-result summary) {
  padding: 0.3rem 0.6rem;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.6);
  user-select: none;
  list-style: none;
}
.message-body :deep(.tool-result summary::before) {
  content: '▶ ';
  font-size: 0.65rem;
  margin-right: 0.3rem;
  transition: transform 0.15s;
  display: inline-block;
}
.message-body :deep(.tool-result[open] summary::before) {
  transform: rotate(90deg);
}
.message-body :deep(.tool-result summary:hover) {
  color: rgba(255, 255, 255, 0.85);
}
.message-body :deep(.tool-result-body) {
  margin: 0;
  padding: 0.4rem 0.6rem;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.45);
  white-space: pre-wrap;
  word-break: break-word;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  max-height: min(420px, 45vh);
  overflow-y: auto;
}
.message-body :deep(.tool-result-line) {
  padding: 0.3rem 0.6rem;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85rem;
  border-left: 2px solid rgba(255, 255, 255, 0.15);
  margin: 0.3rem 0;
}

.tool-events {
  margin-top: 0.4rem;
}

/* 思考过程区块 */
.reasoning-block {
  border-left: 2px solid rgba(212, 175, 55, 0.4);
  margin-bottom: 0.5rem;
}

.reasoning-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.8rem;
  color: rgba(212, 175, 55, 0.7);
  cursor: pointer;
  user-select: none;
}

.reasoning-header:hover {
  color: rgba(212, 175, 55, 0.9);
}

.reasoning-spinner {
  width: 0.6rem;
  height: 0.6rem;
  border: 1.5px solid rgba(212, 175, 55, 0.3);
  border-top-color: rgba(212, 175, 55, 0.8);
  border-radius: 50%;
  animation: reasoning-spin 0.8s linear infinite;
}

@keyframes reasoning-spin {
  to { transform: rotate(360deg); }
}

.reasoning-toggle {
  margin-left: auto;
  font-size: 0.7rem;
  opacity: 0.6;
}

.reasoning-content {
  padding: 0.25rem 0.75rem;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.55);
  max-height: 300px;
  overflow-y: auto;
}

.reasoning-content :deep(*) {
  max-width: 100%;
  overflow-wrap: break-word;
  word-break: break-word;
}

/* 阶段状态行 */
.status-line {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
}

.status-spinner {
  width: 0.75rem;
  height: 0.75rem;
  border: 2px solid rgba(212, 175, 55, 0.2);
  border-top-color: rgba(212, 175, 55, 0.8);
  border-radius: 50%;
  animation: status-spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes status-spin {
  to { transform: rotate(360deg); }
}

.status-text {
  font-size: 0.85rem;
  color: rgba(212, 175, 55, 0.7);
}

/* info 标记分隔线 */
.info-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.25rem 0;
}

.info-divider::before,
.info-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
}

.info-text {
  padding: 0 0.75rem;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.35);
  white-space: nowrap;
}
</style>
