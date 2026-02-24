<script lang="ts">
import { onKeyStroke, useEventListener } from '@vueuse/core'
import { nextTick, onMounted, onUnmounted, ref, useTemplateRef, watch } from 'vue'
import { ACCESS_TOKEN, authExpired } from '@/api'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import MessageItem from '@/components/MessageItem.vue'
import { startToolPolling, stopToolPolling, toolMessage } from '@/composables/useToolStatus'
import { CONFIG } from '@/utils/config'
import { live2dState, setEmotion } from '@/utils/live2dController'
import { CURRENT_SESSION_ID, formatRelativeTime, IS_TEMPORARY_SESSION, loadCurrentSession, MESSAGES, newSession, switchSession } from '@/utils/session'
import { isPlaying, speak } from '@/utils/tts'

export function chatStream(content: string, options?: { skill?: string, images?: string[] }) {
  MESSAGES.value.push({ role: 'user', content: options?.images?.length ? `[截图x${options.images.length}] ${content}` : content })

  API.chatStream(content, {
    sessionId: CURRENT_SESSION_ID.value ?? undefined,
    disableTTS: true,
    skill: options?.skill,
    images: options?.images,
    temporary: IS_TEMPORARY_SESSION.value || undefined,
  }).then(async ({ sessionId, response }) => {
    if (sessionId) {
      CURRENT_SESSION_ID.value = sessionId
    }
    MESSAGES.value.push({ role: 'assistant', content: '', reasoning: '', generating: true })
    const message = MESSAGES.value[MESSAGES.value.length - 1]!
    // 追踪纯LLM内容（不含工具状态标记），用于TTS朗读
    let spokenContent = ''

    live2dState.value = 'thinking'
    let compressTimer: ReturnType<typeof setTimeout> | undefined

    // 情感解析函数
    function parseEmotionFromText(text: string): 'normal' | 'positive' | 'negative' | 'surprise' {
      if (text.includes('【正面情感】')) {
        return 'positive'
      }
      else if (text.includes('【负面情感】')) {
        return 'negative'
      }
      else if (text.includes('【惊讶情感】')) {
        return 'surprise'
      }
      return 'normal'
    }

    // 记录当前轮次 content 流的起始位置，content_clean 只替换当前轮的 LLM 输出
    let roundContentStart = 0

    for await (const chunk of response) {
      if (chunk.type === 'reasoning') {
        message.reasoning = (message.reasoning || '') + chunk.text
      }
      else if (chunk.type === 'content') {
        message.content += chunk.text
        spokenContent += chunk.text
        // 检测情感标记并设置表情
        const emotion = parseEmotionFromText(chunk.text || '')
        if (emotion !== 'normal') {
          void setEmotion(emotion)
        }
      }
      else if (chunk.type === 'content_clean') {
        // 仅替换当前轮次的 LLM 输出（从 roundContentStart 开始），保留之前轮次的工具通知
        message.content = message.content.substring(0, roundContentStart) + (chunk.text || '')
        spokenContent = chunk.text || ''
      }
      else if (chunk.type === 'tool_calls') {
        // 显示工具调用状态
        const calls = chunk.calls || []
        const callDesc = calls.map((c: any) => {
          const name = c.service_name || c.agentType || 'tool'
          return `🔧 ${name}`
        }).join(', ')
        message.content += `\n\n> 正在执行工具: ${callDesc}...\n`
        // OpenClaw 工具可能耗时较长，添加提示
        const hasOpenclaw = calls.some((c: any) => {
          const name = (c.service_name || c.agentType || '').toLowerCase()
          return name.includes('openclaw') || name.includes('agent')
        })
        if (hasOpenclaw) {
          message.content += '> ⏳ OpenClaw 工具处理可能会比较久，预计需要两分钟\n'
        }
      }
      else if (chunk.type === 'tool_results') {
        // 显示工具结果摘要
        const results = chunk.results || []
        for (const r of results) {
          const status = r.status === 'success' ? '✅' : '❌'
          const label = r.tool_name ? `${r.service_name}: ${r.tool_name}` : r.service_name
          message.content += `\n> ${status} ${label}\n`
        }
        message.content += '\n'
        // 工具结果追加完毕，更新下一轮 content 的起始位置
        roundContentStart = message.content.length
      }
      else if (chunk.type === 'round_start' && (chunk.round ?? 0) > 1) {
        // 多轮分隔
        message.content += '\n---\n\n'
        // 新一轮开始，更新 content 起始位置
        roundContentStart = message.content.length
      }
      else if (chunk.type === 'token_refreshed') {
        // 后端刷新了 token，同步到前端（防止后续轮询请求用旧 token 覆盖）
        if (chunk.text) {
          ACCESS_TOKEN.value = chunk.text
        }
      }
      else if (chunk.type === 'auth_expired') {
        // 后端 LLM 认证失败且刷新也失败，触发重新登录
        authExpired.value = true
        message.content += chunk.text || '登录已过期，请重新登录'
      }
      else if (chunk.type === 'compress_start' || chunk.type === 'compress_progress' || chunk.type === 'compress_end') {
        // 上下文压缩进度提示（覆盖式显示，compress_end 后非阻塞延迟清空）
        message.content = `> ${chunk.text}\n\n`
        if (chunk.type === 'compress_end') {
          compressTimer = setTimeout(() => {
            message.content = ''
          }, 1200)
        }
      }
      else if (chunk.type === 'compress_info') {
        // 运行时压缩完成，在当前 assistant 消息前插入 info 标记
        if (compressTimer) {
          clearTimeout(compressTimer)
          compressTimer = undefined
        }
        message.content = ''
        const idx = MESSAGES.value.indexOf(message)
        if (idx > 0) {
          MESSAGES.value.splice(idx, 0, { role: 'info', content: chunk.text || '【已压缩上下文】' })
        }
      }
      // round_end 不需要特殊处理
      window.dispatchEvent(new CustomEvent('token', { detail: chunk.text || '' }))
    }

    delete message.generating
    if (!message.reasoning) {
      delete message.reasoning
    }

    if (CONFIG.value.system.voice_enabled && spokenContent) {
      speak(spokenContent).catch(() => {
        live2dState.value = 'idle'
      })
    }
    else {
      live2dState.value = 'idle'
    }
  }).catch((err) => {
    live2dState.value = 'idle'
    MESSAGES.value.push({ role: 'system', content: `Error: ${err.message}` })
  })
}
</script>

<script setup lang="ts">
const input = defineModel<string>()
const containerRef = useTemplateRef('containerRef')
const fileInput = ref<HTMLInputElement | null>(null)

// TTS 播放状态驱动嘴部动画：开始播放→talking，结束→idle
watch(isPlaying, (playing) => {
  live2dState.value = playing ? 'talking' : 'idle'
})

function scrollToBottom() {
  containerRef.value?.scrollToBottom()
}

function sendMessage() {
  if (input.value) {
    chatStream(input.value)
    nextTick().then(scrollToBottom)
    input.value = ''
  }
}

onMounted(() => {
  loadCurrentSession()
  startToolPolling()
  scrollToBottom()
})
onUnmounted(() => {
  stopToolPolling()
})
useEventListener('token', scrollToBottom)
onKeyStroke('Enter', (e) => {
  if (e.isComposing)
    return
  sendMessage()
})

// Session history
const showHistory = ref(false)
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
}

function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) {
    fetchSessions()
  }
}

async function handleSwitchSession(id: string) {
  await switchSession(id)
  showHistory.value = false
  nextTick().then(scrollToBottom)
}

async function handleDeleteSession(id: string) {
  try {
    await API.deleteSession(id)
    sessions.value = sessions.value.filter(s => s.sessionId !== id)
    if (CURRENT_SESSION_ID.value === id) {
      newSession()
    }
  }
  catch { /* ignore */ }
}

function handleNewSession() {
  newSession()
  showHistory.value = false
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file)
    return

  const ext = file.name.split('.').pop()?.toLowerCase()
  const parseable = ['docx', 'xlsx', 'txt', 'csv', 'md']

  if (ext && parseable.includes(ext)) {
    // 解析文档内容后发送给文本模型
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
    // 其他格式走原有上传逻辑
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

// ── 语音输入 ──
const isRecording = ref(false)
let recognition: any = null

function toggleVoiceInput() {
  if (isRecording.value) {
    stopVoiceInput()
    return
  }

  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SpeechRecognition) {
    MESSAGES.value.push({ role: 'system', content: '当前浏览器不支持语音识别，请使用 Chrome 或 Edge' })
    return
  }

  recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = true
  recognition.continuous = false

  recognition.onresult = (event: any) => {
    let transcript = ''
    for (let i = 0; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript
    }
    input.value = transcript
  }

  recognition.onend = () => {
    isRecording.value = false
    recognition = null
  }

  recognition.onerror = (event: any) => {
    isRecording.value = false
    recognition = null
    if (event.error === 'network') {
      MESSAGES.value.push({ role: 'system', content: '语音识别网络错误：浏览器语音识别需要连接 Google 服务器，请检查网络连接或使用代理。' })
    }
    else if (event.error === 'not-allowed') {
      MESSAGES.value.push({ role: 'system', content: '语音识别权限被拒绝，请在浏览器设置中允许麦克风访问。' })
    }
    else if (event.error !== 'no-speech') {
      MESSAGES.value.push({ role: 'system', content: `语音识别错误: ${event.error}` })
    }
  }

  recognition.start()
  isRecording.value = true
}

function stopVoiceInput() {
  if (recognition) {
    recognition.stop()
  }
  isRecording.value = false
}
</script>

<template>
  <div class="flex flex-col gap-8 relative">
    <BoxContainer ref="containerRef" class="w-full grow">
      <div class="grid gap-4 pb-8">
        <MessageItem
          v-for="item, index in MESSAGES" :key="index"
          :role="item.role" :content="item.content"
          :reasoning="item.reasoning" :sender="item.sender"
          :class="(item.generating && index === MESSAGES.length - 1) || 'border-b'"
        />
      </div>
    </BoxContainer>

    <!-- Session History Panel -->
    <Transition name="slide-up">
      <div v-if="showHistory" class="session-panel">
        <div class="flex items-center justify-between px-3 py-2 border-b border-white/10">
          <span class="text-white/70 text-sm font-bold">对话历史</span>
          <button
            class="text-white/40 hover:text-white/80 bg-transparent border-none cursor-pointer text-xs"
            @click="showHistory = false"
          >
            关闭
          </button>
        </div>
        <div class="overflow-y-auto max-h-48">
          <div v-if="loadingSessions" class="text-white/40 text-xs text-center py-4">
            加载中...
          </div>
          <div v-else-if="sessions.length === 0" class="text-white/40 text-xs text-center py-4">
            暂无历史对话
          </div>
          <div
            v-for="s in sessions" :key="s.sessionId"
            class="session-item"
            :class="{ 'bg-white/10': s.sessionId === CURRENT_SESSION_ID }"
            @click="handleSwitchSession(s.sessionId)"
          >
            <div class="flex-1 min-w-0">
              <div class="text-white/80 text-sm truncate">
                {{ s.sessionId.slice(0, 8) }}...
              </div>
              <div class="text-white/40 text-xs">
                {{ formatRelativeTime(s.lastActiveAt) }} · {{ s.conversationRounds }} 轮对话
              </div>
            </div>
            <button
              class="text-white/30 hover:text-red-400 bg-transparent border-none cursor-pointer text-xs shrink-0 ml-2"
              title="删除"
              @click.stop="handleDeleteSession(s.sessionId)"
            >
              x
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <div v-if="toolMessage" class="mx-[var(--nav-back-width)] text-white/50 text-xs px-2 py-1">
      {{ toolMessage }}
    </div>
    <div class="mx-[var(--nav-back-width)]">
      <div class="box flex items-center gap-2">
        <button
          class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
          title="新建对话"
          @click="handleNewSession"
        >
          +
        </button>
        <button
          class="p-2 text-white/60 hover:text-white bg-transparent border-none cursor-pointer text-sm shrink-0"
          :class="{ 'text-white!': showHistory }"
          title="对话历史"
          @click="toggleHistory"
        >
          H
        </button>
        <input
          v-model="input"
          class="p-2 lh-none text-white w-full bg-transparent border-none outline-none"
          type="text"
          placeholder="Type a message..."
        >
        <button
          class="input-icon-btn shrink-0"
          :class="{ recording: isRecording }"
          :title="isRecording ? '停止录音' : '语音输入'"
          @click="toggleVoiceInput"
        >
          <svg v-if="!isRecording" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" /><path d="M19 10v2a7 7 0 0 1-14 0v-2" /><line x1="12" x2="12" y1="19" y2="22" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
        </button>
        <button
          class="input-icon-btn shrink-0"
          title="上传文件 (Word/Excel/文本)"
          @click="triggerUpload"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" /><path d="M14 2v4a2 2 0 0 0 2 2h4" /><path d="M12 18v-6" /><path d="m9 15 3-3 3 3" /></svg>
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".docx,.xlsx,.txt,.csv,.md,.pdf,.png,.jpg,.jpeg"
          class="hidden"
          @change="handleFileUpload"
        >
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-panel {
  position: absolute;
  left: var(--nav-back-width);
  right: 0;
  bottom: 5rem;
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  backdrop-filter: blur(12px);
  z-index: 10;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.2s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.input-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.input-icon-btn:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.08);
}

.input-icon-btn.recording {
  color: #e85d5d;
  animation: recording-pulse 1.2s ease-in-out infinite;
}

@keyframes recording-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
