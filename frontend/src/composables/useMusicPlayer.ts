/**
 * 全局音乐播放器 - 主界面 BGM 与音律坊共用同一实例
 * 避免重复播放，开机/主界面 BGM 均来自音律坊曲库
 */
import { computed, onMounted, ref, watch } from 'vue'
import { audioSettings, registerBgmDelegate } from './useAudio'

export interface Track {
  id: number
  title: string
  duration: string
  src: string
  /** 文件名，用于 playBgm('8.日常的小曲.mp3') 匹配 */
  file: string
}

const DEFAULT_TRACKS: Track[] = [
  { id: 1, title: '日常的小曲 · Everyday Tune', duration: '03:24', src: '/voices/background/8.日常的小曲.mp3', file: '8.日常的小曲.mp3' },
  { id: 2, title: '快乐的小曲 · Happy Tune', duration: '03:07', src: '/voices/background/9.快乐的小曲.mp3', file: '9.快乐的小曲.mp3' },
]

function parseDisplayName(filename: string): string {
  const name = filename.replace(/\.mp3$/i, '')
  const match = name.match(/^\d+\.(.+)$/)
  return match ? match[1]! : name
}

/** 从 localStorage 加载歌单，与音律坊编辑页一致 */
function loadTracksFromStorage(): Track[] {
  const saved = localStorage.getItem('music-playlist')
  if (saved != null && saved !== '') {
    try {
      const savedIds = JSON.parse(saved) as string[]
      return savedIds.map((filename, idx) => ({
        id: idx + 1,
        title: parseDisplayName(filename),
        duration: '00:00',
        src: `/voices/background/${filename}`,
        file: filename,
      }))
    }
    catch {
      /* 解析失败用默认 */
    }
  }
  return [...DEFAULT_TRACKS]
}

const tracks = ref<Track[]>(loadTracksFromStorage())
const currentIndex = ref(0)
const isPlaying = ref(false)
const playMode = ref<'list' | 'shuffle' | 'single'>('list')
const duration = ref(0)
const currentTime = ref(0)
let audio: HTMLAudioElement | null = null

const currentTrack = computed(() => tracks.value[currentIndex.value] ?? null)
const progress = computed(() => (duration.value > 0 ? (currentTime.value / duration.value) * 100 : 0))
const playModeLabel = computed(() => {
  if (playMode.value === 'shuffle')
    return '随机播放'
  if (playMode.value === 'single')
    return '单曲循环'
  return '列表循环'
})

function initAudio() {
  if (audio)
    return
  audio = new Audio()
  audio.addEventListener('play', () => {
    isPlaying.value = true
  })
  audio.addEventListener('pause', () => {
    isPlaying.value = false
  })
  audio.addEventListener('timeupdate', () => {
    if (!audio)
      return
    currentTime.value = audio.currentTime
    duration.value = audio.duration || duration.value
  })
  audio.addEventListener('loadedmetadata', () => {
    if (audio)
      duration.value = audio.duration
  })
  audio.addEventListener('ended', handleEnded)
}

function setupAudioForTrack() {
  if (!audio || !currentTrack.value)
    return
  audio.src = currentTrack.value.src
  audio.currentTime = 0
  duration.value = 0
  currentTime.value = 0
  audio.volume = audioSettings.value.bgmVolume
  if (isPlaying.value) {
    audio.play().catch(() => {
      isPlaying.value = false
    })
  }
}

function handleEnded() {
  if (playMode.value === 'single') {
    if (audio) {
      audio.currentTime = 0
      audio.play().catch(() => {
        isPlaying.value = false
      })
    }
  }
  else {
    next()
    // 播完会先触发 pause 使 isPlaying=false，setupAudioForTrack 内不会自动 play，这里显式续播下一首
    play()
  }
}

function play() {
  if (!audio)
    return
  if (!audioSettings.value.bgmEnabled)
    return
  audio.volume = audioSettings.value.bgmVolume
  audio.play().catch(() => {
    isPlaying.value = false
  })
}

function pause() {
  audio?.pause()
}

function togglePlay() {
  if (!audio)
    return
  if (audio.paused)
    play()
  else pause()
}

function prev() {
  if (!tracks.value.length)
    return
  currentIndex.value = (currentIndex.value - 1 + tracks.value.length) % tracks.value.length
  setupAudioForTrack()
}

function next() {
  if (!tracks.value.length)
    return
  if (playMode.value === 'shuffle') {
    if (tracks.value.length === 1)
      return
    let idx = currentIndex.value
    while (idx === currentIndex.value)
      idx = Math.floor(Math.random() * tracks.value.length)
    currentIndex.value = idx
  }
  else {
    currentIndex.value = (currentIndex.value + 1) % tracks.value.length
  }
  setupAudioForTrack()
}

function togglePlayMode() {
  if (playMode.value === 'list')
    playMode.value = 'shuffle'
  else if (playMode.value === 'shuffle')
    playMode.value = 'single'
  else playMode.value = 'list'
}

/** BGM 委托：按文件名切换曲目并播放（主界面/启动时调用） */
function playFile(file: string) {
  initAudio()
  const idx = tracks.value.findIndex(t => t.file === file || t.src.endsWith(file))
  if (idx >= 0) {
    currentIndex.value = idx
    setupAudioForTrack()
    isPlaying.value = true
    play()
  }
}

/** BGM 委托：暂停（悬浮球等场景） */
function pauseBgm() {
  pause()
}

export function useMusicPlayer() {
  onMounted(() => {
    tracks.value = loadTracksFromStorage()
    initAudio()
    registerBgmDelegate({ playFile, pause: pauseBgm })
    if (audio && !audio.src)
      setupAudioForTrack() // 仅首次初始化，后续由 playBgm→playFile 驱动
  })

  watch(currentTrack, setupAudioForTrack)
  watch(() => audioSettings.value.bgmVolume, (v) => {
    if (audio)
      audio.volume = v
  })

  /** 从 localStorage 重新加载歌单（编辑页保存后调用） */
  function reloadPlaylist() {
    tracks.value = loadTracksFromStorage()
    if (currentIndex.value >= tracks.value.length)
      currentIndex.value = Math.max(0, tracks.value.length - 1)
  }

  return {
    tracks,
    currentIndex,
    isPlaying,
    playMode,
    duration,
    currentTime,
    currentTrack,
    progress,
    playModeLabel,
    togglePlay,
    prev,
    next,
    togglePlayMode,
    play,
    pause,
    reloadPlaylist,
  }
}
