import { ref } from 'vue'
import { CONFIG } from '@/utils/config'

const audio = ref<HTMLAudioElement | null>(null)
export const isPlaying = ref(false)
let maxDurationTimer: number | null = null

const MAX_PLAYBACK_DURATION = 30000 // 30秒最大播放时长

export function speak(text: string): Promise<void> {
  stop()
  const tts = CONFIG.value.tts
  const url = `http://localhost:${tts.port}/v1/audio/speech`

  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'tts-1',
      input: text,
      voice: tts.default_voice,
      speed: tts.default_speed,
      response_format: tts.default_format,
    }),
  }).then(async (res) => {
    if (!res.ok)
      throw new Error(`TTS responded ${res.status}`)
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const el = new Audio(objectUrl)
    audio.value = el
    isPlaying.value = true

    // 设置30秒最大播放时长定时器
    maxDurationTimer = window.setTimeout(() => {
      if (audio.value) {
        stop()
      }
    }, MAX_PLAYBACK_DURATION)

    el.onended = () => {
      // 清除定时器
      if (maxDurationTimer) {
        clearTimeout(maxDurationTimer)
        maxDurationTimer = null
      }
      isPlaying.value = false
      URL.revokeObjectURL(objectUrl)
      audio.value = null
    }
    el.play()
  }).catch((err) => {
    // 清除定时器
    if (maxDurationTimer) {
      clearTimeout(maxDurationTimer)
      maxDurationTimer = null
    }
    isPlaying.value = false
    throw err
  })
}

export function stop() {
  // 清除定时器
  if (maxDurationTimer) {
    clearTimeout(maxDurationTimer)
    maxDurationTimer = null
  }

  if (audio.value) {
    audio.value.pause()
    audio.value = null
    isPlaying.value = false
  }
}
