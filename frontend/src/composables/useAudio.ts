import { useStorage } from '@vueuse/core'
import { watch } from 'vue'

// ─── 持久化设置（纯前端 localStorage） ─────────────────
export const audioSettings = useStorage('naga-audio-settings', {
  bgmVolume: 0.3,
  effectVolume: 0.5,
  wakeVoice: 'Default',
  clickEffect: '翻书.mp3',
  bgmEnabled: true,
  effectEnabled: true,
})

// ─── 静态资源文件列表（构建时收集） ─────────────────────
const AUDIO_EXTENSIONS = /\.(?:mp3|m4a|ogg|wav|flac|aac|webm)$/i
const startVoiceGlob = import.meta.glob('/public/voices/start/**/*.*', { query: '?url', import: 'default' })
const effectGlob = import.meta.glob('/public/voices/effect/*.*', { query: '?url', import: 'default' })

// 解析 start/ 下的语音包列表: { folderName: [fileName, ...] }
function parseStartVoices() {
  const map: Record<string, string[]> = {}
  for (const key of Object.keys(startVoiceGlob)) {
    // key: /public/voices/start/Default/音频3.mp3
    const rel = key.replace('/public/voices/start/', '')
    const slashIdx = rel.indexOf('/')
    if (slashIdx === -1)
      continue
    const folder = rel.substring(0, slashIdx)
    const file = rel.substring(slashIdx + 1)
    // 过滤非音频文件（.DS_Store 等）
    if (!AUDIO_EXTENSIONS.test(file))
      continue
    if (!map[folder])
      map[folder] = []
    map[folder].push(file)
  }
  return map
}

function parseEffectFiles() {
  const files: string[] = []
  for (const key of Object.keys(effectGlob)) {
    // key: /public/voices/effect/做出选择.ogg
    const file = key.replace('/public/voices/effect/', '')
    if (!AUDIO_EXTENSIONS.test(file))
      continue
    files.push(file)
  }
  return files
}

export const wakeVoiceMap = parseStartVoices()
export const wakeVoiceOptions = Object.keys(wakeVoiceMap)
export const effectFileOptions = parseEffectFiles()

// ─── BGM 播放器（单例） ──────────────────────────────
// 当音律坊注册为委托时，BGM 由音律坊统一播放，避免重复
interface BgmDelegate { playFile: (file: string) => void, pause: () => void }
let bgmDelegate: BgmDelegate | null = null
let bgmAudio: HTMLAudioElement | null = null
let bgmCurrentFile = ''

export function registerBgmDelegate(d: BgmDelegate) {
  bgmDelegate = d
  // 委托注册后停掉兜底 BGM，避免与音乐盒双轨叠加
  if (bgmAudio) {
    bgmAudio.pause()
    bgmAudio.src = ''
    bgmAudio = null
    bgmCurrentFile = ''
  }
}

export function unregisterBgmDelegate() {
  bgmDelegate = null
}

function fadeTo(audio: HTMLAudioElement, targetVolume: number, duration = 800): Promise<void> {
  return new Promise((resolve) => {
    const startVolume = audio.volume
    const startTime = performance.now()
    function step() {
      const elapsed = performance.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      audio.volume = startVolume + (targetVolume - startVolume) * progress
      if (progress < 1) {
        requestAnimationFrame(step)
      }
      else {
        resolve()
      }
    }
    requestAnimationFrame(step)
  })
}

export async function playBgm(file: string) {
  if (!audioSettings.value.bgmEnabled)
    return
  if (bgmDelegate) {
    bgmDelegate.playFile(file)
    return
  }
  if (bgmAudio && bgmCurrentFile === file)
    return

  // 淡出旧 BGM（无委托时的兜底逻辑）
  if (bgmAudio) {
    await fadeTo(bgmAudio, 0, 600)
    bgmAudio.pause()
    bgmAudio.src = ''
    bgmAudio = null
  }

  const audio = new Audio(`/voices/background/${file}`)
  audio.loop = true
  audio.volume = 0
  bgmAudio = audio
  bgmCurrentFile = file

  try {
    await audio.play()
    await fadeTo(audio, audioSettings.value.bgmVolume, 800)
  }
  catch {
    // autoplay policy blocked — ignore
  }
}

export function stopBgm() {
  if (bgmDelegate) {
    bgmDelegate.pause()
    return
  }
  if (!bgmAudio)
    return
  fadeTo(bgmAudio, 0, 600).then(() => {
    bgmAudio?.pause()
    if (bgmAudio)
      bgmAudio.src = ''
    bgmAudio = null
    bgmCurrentFile = ''
  })
}

// ─── 唤醒语音 ──────────────────────────────────────
export function playWakeVoice() {
  const pack = audioSettings.value.wakeVoice
  const files = wakeVoiceMap[pack]
  if (!files || files.length === 0) {
    console.warn(`[Audio] 唤醒语音包 "${pack}" 无可用文件`)
    return
  }

  const file = files[Math.floor(Math.random() * files.length)]!
  const url = `/voices/start/${encodeURIComponent(pack)}/${encodeURIComponent(file)}`
  const audio = new Audio(url)
  audio.volume = audioSettings.value.effectVolume
  audio.play().catch((e) => {
    console.error(`[Audio] 唤醒语音播放失败: ${url}`, e)
  })
}

// ─── 点击音效 ──────────────────────────────────────
export function playClickEffect() {
  if (!audioSettings.value.effectEnabled)
    return
  const file = audioSettings.value.clickEffect
  const audio = new Audio(`/voices/effect/${encodeURIComponent(file)}`)
  audio.volume = audioSettings.value.effectVolume
  audio.play().catch((e) => {
    console.warn(`[Audio] 点击音效播放失败:`, e.message)
  })
}

// ─── 响应设置变化 ──────────────────────────────────
watch(() => audioSettings.value.bgmVolume, (vol) => {
  if (bgmAudio)
    bgmAudio.volume = vol
})

watch(() => audioSettings.value.bgmEnabled, (enabled) => {
  if (!enabled) {
    stopBgm()
  }
  else if (bgmCurrentFile === '') {
    playBgm('8.日常的小曲.mp3')
  }
})
