import { ref, watch } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import API from '@/api/core'
import { CONFIG } from '@/utils/config'

const audio = ref<HTMLAudioElement | null>(null)
export const isPlaying = ref(false)

const MAX_PLAYBACK_DURATION_MS = 30_000
const GATEWAY_TTS_MODEL = 'default'
const LOCAL_TTS_MODEL = 'tts-1'
const TTS_RESPONSE_FORMAT = 'mp3'

let maxDurationTimer: number | null = null
let abortController: AbortController | null = null
let currentObjectUrl: string | null = null

const queue: string[] = []
let processingQueue = false
let queueGeneration = 0

/** 移除 Markdown 代码块和行内代码，只保留适合朗读的自然语言。 */
function stripCodeBlocks(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`[^`]+`/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export async function speak(text: string): Promise<void> {
  _stopCurrent()

  const cleanText = stripCodeBlocks(text)
  if (!cleanText || !CONFIG.value.system.voice_enabled)
    return

  const useGateway = Boolean(ACCESS_TOKEN.value && CONFIG.value.api.use_gateway)
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (useGateway)
    headers.Authorization = `Bearer ${ACCESS_TOKEN.value}`

  const controller = new AbortController()
  abortController = controller

  try {
    const response = await fetch(`${API.endpoint}/tts/speech`, {
      method: 'POST',
      headers,
      signal: controller.signal,
      body: JSON.stringify({
        model: useGateway ? GATEWAY_TTS_MODEL : LOCAL_TTS_MODEL,
        input: cleanText,
        voice: useGateway ? CONFIG.value.voice_realtime.voice : CONFIG.value.tts.default_voice,
        speed: CONFIG.value.tts.default_speed,
        response_format: TTS_RESPONSE_FORMAT,
      }),
    })

    if (!response.ok)
      throw new Error(`TTS responded ${response.status}`)
    const refreshedAccessToken = response.headers.get('x-naga-access-token')
    if (refreshedAccessToken)
      ACCESS_TOKEN.value = refreshedAccessToken
    if (controller.signal.aborted)
      return

    // 代理会先完整接收上游音频，因此 MediaSource 不会降低首音延迟。
    // Blob 播放同时兼容 MP3 与代理包装后的 WAV，并可可靠等待播放结束。
    await playResponse(response, controller.signal)
  }
  catch (error) {
    if (controller.signal.aborted || isAbortError(error))
      return
    cleanup()
    console.error('[TTS] speak failed:', error)
    throw error
  }
  finally {
    if (abortController === controller)
      abortController = null
  }
}

async function playResponse(response: Response, signal: AbortSignal): Promise<void> {
  const blob = await response.blob()
  if (blob.size === 0)
    throw new Error('TTS returned empty audio')
  if (signal.aborted)
    return

  const responseType = response.headers.get('content-type')?.split(';', 1)[0]?.trim()
  const audioBlob = blob.type || !responseType
    ? blob
    : new Blob([blob], { type: responseType })
  const objectUrl = URL.createObjectURL(audioBlob)
  const element = new Audio(objectUrl)
  currentObjectUrl = objectUrl
  audio.value = element

  await new Promise<void>((resolve, reject) => {
    let settled = false
    let finish: (error?: Error) => void = () => {}
    const handleAbort = () => finish()

    finish = (error?: Error) => {
      if (settled)
        return
      settled = true
      signal.removeEventListener('abort', handleAbort)
      if (audio.value === element)
        cleanup()
      if (error)
        reject(error)
      else
        resolve()
    }

    signal.addEventListener('abort', handleAbort, { once: true })
    element.onplay = () => {
      isPlaying.value = true
    }
    element.onended = () => finish()
    element.onerror = () => finish(new Error('TTS audio playback failed'))

    maxDurationTimer = window.setTimeout(() => {
      finish(new Error('TTS audio playback timed out'))
    }, MAX_PLAYBACK_DURATION_MS)

    element.play().catch((error: unknown) => {
      finish(error instanceof Error ? error : new Error(String(error)))
    })
  })
}

function cleanup(): void {
  if (maxDurationTimer !== null) {
    clearTimeout(maxDurationTimer)
    maxDurationTimer = null
  }

  isPlaying.value = false
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl)
    currentObjectUrl = null
  }
  if (audio.value) {
    audio.value.onplay = null
    audio.value.onended = null
    audio.value.onerror = null
    audio.value.pause()
    audio.value.removeAttribute('src')
    audio.value.load()
  }
  audio.value = null
}

function _stopCurrent(): void {
  abortController?.abort()
  abortController = null
  cleanup()
}

/** 停止当前播放并清空所有待播句子。 */
export function stop(): void {
  queue.length = 0
  queueGeneration++
  processingQueue = false
  _stopCurrent()
}

/** 逐句入队并严格按顺序播放。 */
export function queueSpeak(text: string): void {
  if (!CONFIG.value.system.voice_enabled)
    return

  const cleanText = stripCodeBlocks(text)
  if (!cleanText)
    return

  queue.push(cleanText)
  if (processingQueue)
    return

  processingQueue = true
  void drainQueue(queueGeneration)
}

async function drainQueue(generation: number): Promise<void> {
  for (;;) {
    if (generation !== queueGeneration)
      break
    const text = queue.shift()
    if (!text)
      break

    try {
      await speak(text)
    }
    catch {
      // 单句失败不阻断后续句子。
    }
  }

  if (generation === queueGeneration)
    processingQueue = false
}

watch(
  () => CONFIG.value.system.voice_enabled,
  (enabled) => {
    if (!enabled)
      stop()
  },
)
