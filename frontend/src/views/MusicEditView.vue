<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BoxContainer from '@/components/BoxContainer.vue'
import { useMusicPlayer } from '@/composables/useMusicPlayer'

interface Song {
  id: string
  filename: string
  displayName: string
  src: string
}

// 读取背景音乐文件
const bgmGlob = import.meta.glob('/public/voices/background/*.mp3', { query: '?url', import: 'default' })
const availableSongs = ref<Song[]>([])
const playlist = ref<Song[]>([])
const selectedSong = ref<Song | null>(null)
const selectedPlaylistIndex = ref<number | null>(null)
const firstSelectedIndex = ref<number | null>(null)

// 分页
const currentPage = ref(1)
const pageSize = 10
const totalPages = computed(() => Math.max(1, Math.ceil(availableSongs.value.length / pageSize)))
const paginatedSongs = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return availableSongs.value.slice(start, start + pageSize)
})

const router = useRouter()
const { reloadPlaylist } = useMusicPlayer() // 编辑保存后同步到全局播放器

// 解析文件名，生成显示名称
function parseDisplayName(filename: string): string {
  // 移除扩展名
  const name = filename.replace(/\.mp3$/i, '')
  // 如果有数字前缀（如 "8.日常的小曲"），提取中文部分
  const match = name.match(/^\d+\.(.+)$/)
  if (match) {
    return match[1]!
  }
  return name
}

// 初始化可用歌曲列表
onMounted(async () => {
  const songs: Song[] = []
  for (const [path, loader] of Object.entries(bgmGlob)) {
    const url = await loader() as string
    const filename = path.replace('/public/voices/background/', '')
    songs.push({
      id: filename,
      filename,
      displayName: parseDisplayName(filename),
      src: url,
    })
  }
  // 按文件名排序
  songs.sort((a, b) => a.filename.localeCompare(b.filename))
  availableSongs.value = songs

  // 从 localStorage 加载已保存的播放列表
  const saved = localStorage.getItem('music-playlist')
  if (saved) {
    try {
      const savedIds = JSON.parse(saved) as string[]
      playlist.value = savedIds
        .map(id => songs.find(s => s.id === id))
        .filter((s): s is Song => s !== undefined)
    }
    catch {
      // 忽略解析错误
    }
  }
})

// 添加歌曲到播放列表
function addToPlaylist(song: Song) {
  if (playlist.value.some(s => s.id === song.id))
    return
  playlist.value.push(song)
  savePlaylist()
}

// 从播放列表移除歌曲
function removeFromPlaylist(index: number) {
  playlist.value.splice(index, 1)
  selectedPlaylistIndex.value = null
  firstSelectedIndex.value = null
  savePlaylist()
}

// 交换播放列表中两首歌曲的位置
function swapSongs(index1: number, index2: number) {
  if (index1 === index2 || index1 < 0 || index2 < 0 || index1 >= playlist.value.length || index2 >= playlist.value.length)
    return
  const temp = playlist.value[index1]!
  playlist.value[index1] = playlist.value[index2]!
  playlist.value[index2] = temp
  firstSelectedIndex.value = null
  selectedPlaylistIndex.value = null
  savePlaylist()
}

// 点击播放列表项
function handlePlaylistClick(index: number, event: MouseEvent) {
  if (event.button === 2) {
    // 右键：移除
    event.preventDefault()
    removeFromPlaylist(index)
    return
  }

  // 左键：选择或交换
  if (firstSelectedIndex.value === null) {
    firstSelectedIndex.value = index
    selectedPlaylistIndex.value = index
  }
  else {
    // 交换两首歌曲
    swapSongs(firstSelectedIndex.value, index)
  }
}

// 保存播放列表到 localStorage，并通知全局播放器刷新歌单
function savePlaylist() {
  localStorage.setItem('music-playlist', JSON.stringify(playlist.value.map(s => s.id)))
  reloadPlaylist()
}

// 完成：仅更新播放列表
function confirm() {
  savePlaylist()
}

// 取消
function _cancel() {
  router.push('/music')
}
</script>

<template>
  <BoxContainer class="text-sm">
    <div class="flex flex-col gap-4 min-h-0">
      <!-- 顶部标题 -->
      <div class="flex items-baseline justify-between gap-4">
        <div>
          <div class="text-xs tracking-[0.3em] text-amber-300/70 uppercase">
            NAGA · AUDIO LAB
          </div>
          <div class="mt-1 text-2xl font-serif text-white">
            编辑歌单
          </div>
          <div class="mt-1 text-xs text-white/40">
            点击左侧的曲名来添加曲目。右键点击曲名可移除曲目，点击两首曲目可替换顺序。
          </div>
        </div>
      </div>

      <!-- 当前歌曲拓展包 -->
      <div class="edit-expansion-section">
        <span class="edit-expansion-label">当前歌曲拓展包</span>
        <span class="edit-expansion-value">拓展包一：Naga</span>
        <button type="button" class="switch-btn">切换</button>
      </div>

      <!-- 主要内容区域：左右两栏 -->
      <div class="edit-panel">
        <!-- 左侧：可用歌曲列表 -->
        <div class="edit-left">
          <div class="edit-section-title">
            可用歌曲
          </div>
          <div class="song-list">
            <div
              v-for="song in paginatedSongs"
              :key="song.id"
              class="song-item"
              :class="{ selected: selectedSong?.id === song.id }"
              @click="selectedSong = song; addToPlaylist(song)"
            >
              {{ song.displayName }}
            </div>
          </div>
          <!-- 分页控制 -->
          <div class="pagination">
            <button
              class="page-btn"
              :disabled="currentPage === 1"
              @click="currentPage = Math.max(1, currentPage - 1)"
            >
              ◀
            </button>
            <span class="page-info">{{ currentPage }}/{{ totalPages }}</span>
            <button
              class="page-btn"
              :disabled="currentPage >= totalPages"
              @click="currentPage = Math.min(totalPages, currentPage + 1)"
            >
              ▶
            </button>
          </div>
        </div>

        <!-- 右侧：当前播放列表 -->
        <div class="edit-right">
          <div class="edit-section-title">
            当前播放列表
          </div>
          <div class="playlist-list">
            <div
              v-for="(song, index) in playlist"
              :key="`${song.id}-${index}`"
              class="playlist-item"
              :class="{ selected: selectedPlaylistIndex === index, first: firstSelectedIndex === index }"
              @click="handlePlaylistClick(index, $event)"
              @contextmenu.prevent="removeFromPlaylist(index)"
            >
              <span class="playlist-number">{{ index + 1 }}</span>
              <span class="playlist-title">{{ song.displayName }}</span>
            </div>
            <div v-if="playlist.length === 0" class="playlist-empty">
              播放列表为空，点击左侧歌曲添加
            </div>
          </div>
          <div class="playlist-actions">
            <button class="ready-btn" @click="confirm">
              完成
            </button>
          </div>
        </div>
      </div>
    </div>
  </BoxContainer>
</template>

<style scoped>
.edit-expansion-section {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 8px;
}

.edit-expansion-label {
  font-size: 12px;
  color: rgba(248, 250, 252, 0.6);
}

.edit-expansion-value {
  font-size: 12px;
  color: rgba(251, 191, 36, 0.9);
}

.switch-btn {
  margin-left: auto;
  padding: 6px 16px;
  border: none;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.9);
  color: white;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.switch-btn:hover {
  background: rgba(239, 68, 68, 1);
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.6);
}

.edit-panel {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  min-height: 0;
  flex: 1;
}

.edit-left,
.edit-right {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.edit-section-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.9);
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.song-list,
.playlist-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.song-item {
  padding: 8px 12px;
  border: 1px solid rgba(59, 130, 246, 0.5);
  background: rgba(30, 58, 138, 0.3);
  color: rgba(248, 250, 252, 0.85);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  border-radius: 4px;
}

.song-item:hover {
  background: rgba(59, 130, 246, 0.4);
  border-color: rgba(96, 165, 250, 0.8);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.5);
}

.song-item.selected {
  background: rgba(251, 191, 36, 0.4);
  border-color: rgba(251, 191, 36, 0.9);
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.7);
}

.playlist-item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid rgba(239, 68, 68, 0.5);
  background: rgba(127, 29, 29, 0.3);
  color: rgba(248, 250, 252, 0.85);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  border-radius: 4px;
}

.playlist-item:hover {
  background: rgba(239, 68, 68, 0.4);
  border-color: rgba(248, 113, 113, 0.8);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
}

.playlist-item.selected {
  background: rgba(251, 191, 36, 0.4);
  border-color: rgba(251, 191, 36, 0.9);
  box-shadow: 0 0 12px rgba(251, 191, 36, 0.7);
}

.playlist-item.first {
  background: rgba(34, 197, 94, 0.3);
  border-color: rgba(34, 197, 94, 0.7);
}

.playlist-number {
  font-variant-numeric: tabular-nums;
  color: rgba(248, 250, 252, 0.6);
  font-size: 11px;
  min-width: 20px;
}

.playlist-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.playlist-empty {
  padding: 24px;
  text-align: center;
  color: rgba(148, 163, 184, 0.5);
  font-size: 12px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px;
}

.page-btn {
  border: 1px solid rgba(148, 163, 184, 0.3);
  background: rgba(15, 23, 42, 0.9);
  color: rgba(248, 250, 252, 0.8);
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}

.page-btn:hover:not(:disabled) {
  background: rgba(30, 64, 175, 0.9);
  border-color: rgba(96, 165, 250, 0.8);
}

.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-variant-numeric: tabular-nums;
  color: rgba(248, 250, 252, 0.7);
  font-size: 11px;
  min-width: 40px;
  text-align: center;
}

.playlist-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
}

.ready-btn {
  padding: 8px 24px;
  border: none;
  border-radius: 6px;
  background: rgba(239, 68, 68, 0.9);
  color: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.ready-btn:hover {
  background: rgba(239, 68, 68, 1);
  box-shadow: 0 0 12px rgba(239, 68, 68, 0.6);
}
</style>
