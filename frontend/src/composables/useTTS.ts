import { ref } from 'vue'
import { CONFIG } from '@/utils/config'

const audio = ref<HTMLAudioElement | null>(null)
export const isPlaying = ref(false)

export function speak(text: string) {
  stop()
  const tts = CONFIG.value.tts
  const url = `http://localhost:${tts.port}/v1/audio/speech`

  fetch(url, {
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
    if (!res.ok) return
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const el = new Audio(objectUrl)
    audio.value = el
    isPlaying.value = true
    el.onended = () => {
      isPlaying.value = false
      URL.revokeObjectURL(objectUrl)
      audio.value = null
    }
    el.play()
  }).catch(() => {
    isPlaying.value = false
  })
}

export function stop() {
  if (audio.value) {
    audio.value.pause()
    audio.value = null
    isPlaying.value = false
  }
}
