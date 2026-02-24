<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import musicBox from '@/assets/icons/音乐盒.png'
import BoxContainer from '@/components/BoxContainer.vue'
import { useMusicPlayer } from '@/composables/useMusicPlayer'

const router = useRouter()
// 统一使用全局音乐盒，主界面 BGM 与音律坊同一实例，避免叠加；isPlaying 与全局播放器同步，图标会随 BGM 自动变为播放态
const {
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
  reloadPlaylist,
} = useMusicPlayer()

function selectTrack(index: number) {
  currentIndex.value = index
  play()
}

onMounted(() => {
  reloadPlaylist() // 从编辑页返回时同步歌单
})
</script>

<template>
  <BoxContainer class="text-sm">
    <div class="flex flex-col gap-5 min-h-0">
      <!-- 顶部标题 -->
      <div class="flex items-baseline justify-between gap-4">
        <div>
          <div class="text-xs tracking-[0.3em] text-amber-300/70 uppercase">
            NAGA · AUDIO LAB
          </div>
          <div class="mt-1 text-2xl font-serif text-white">
            音律坊
          </div>
          <div class="mt-1 text-xs text-white/40">
            为娜迦定制的专属曲包，在节奏中同步思绪。
          </div>
        </div>
        <div class="text-right text-xs text-white/40 flex flex-col items-end gap-1">
          <div>
            当前曲目集
          </div>
          <div class="text-amber-300/80">
            自定义包1
          </div>
          <div class="flex gap-2 mt-1">
            <button class="mode-btn" title="点击切换播放顺序" @click="togglePlayMode">
              {{ playModeLabel }}
            </button>
            <button class="edit-btn" title="编辑歌单" @click="router.push('/music/edit')">
              编辑歌单
            </button>
          </div>
        </div>
      </div>

      <!-- 中部信息卡，参考示例视觉 -->
      <div class="music-panel">
        <div class="music-panel-inner">
          <!-- 左侧：封面 + 参数 + 频谱 -->
          <div class="music-left">
            <div class="music-hero">
              <div class="music-hero-grid" />
              <img :src="musicBox" alt="music box" class="music-hero-icon">
            </div>
          </div>

          <!-- 右侧：播放列表 -->
          <div class="music-track-list">
            <div
              v-for="(track, index) in tracks"
              :key="track.id"
              class="track-row"
              :class="{ active: currentIndex === index }"
              @click="selectTrack(index)"
            >
              <div class="dot" />
              <div class="title line-clamp-1">
                {{ track.title }}
              </div>
              <div class="duration">
                {{ track.duration }}
              </div>
            </div>
            <div v-if="tracks.length === 0" class="music-track-empty">
              歌曲等待打捞
            </div>
          </div>
        </div>
      </div>

      <!-- 底部播放控制区 -->
      <div class="mt-auto pt-2 music-player">
        <!-- 控制与进度条 -->
        <div class="controls">
          <div class="buttons">
            <button class="round-btn" title="上一首" :disabled="!tracks.length" @click="prev">
              〈〈
            </button>
            <button class="play-btn" :class="{ playing: isPlaying }" :disabled="!tracks.length" @click="togglePlay">
              <span v-if="!isPlaying">▶</span>
              <span v-else>⏸</span>
            </button>
            <button class="round-btn" title="下一首" :disabled="!tracks.length" @click="next">
              〉〉
            </button>
          </div>

          <div class="progress-area">
            <div class="time left">
              {{ tracks.length ? new Date(currentTime * 1000).toISOString().substring(14, 19) : '00:00' }}
            </div>
            <div class="bar">
              <div class="bar-bg" />
              <div class="bar-fill" :style="{ width: `${progress}%` }" />
              <div class="bar-thumb" :style="{ left: `${progress}%` }" />
            </div>
            <div class="time right">
              {{ currentTrack?.duration ?? '00:00' }}
            </div>
          </div>
        </div>

        <div class="track-title">
          正在播放：
          <span class="name">{{ currentTrack?.title ?? (tracks.length ? '' : '暂无') }}</span>
        </div>
      </div>
    </div>
  </BoxContainer>
</template>

<style scoped>
.music-panel {
  border-radius: 18px;
  padding: 1px;
  background: radial-gradient(circle at 0 0, rgba(212, 175, 55, 0.45), transparent 55%),
    radial-gradient(circle at 100% 100%, rgba(122, 199, 255, 0.4), transparent 55%);
}

.music-panel-inner {
  border-radius: 16px;
  padding: 16px 18px 12px;
  background: rgba(5, 7, 10, 0.92);
  box-shadow: 0 0 24px rgba(0, 0, 0, 0.6);
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.1fr);
  gap: 14px;
  align-items: stretch;
}

.music-left {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.music-hero {
  position: relative;
  border-radius: 16px;
  padding: 18px;
  background: radial-gradient(circle at 20% 0%, rgba(255, 158, 234, 0.25), transparent 55%),
    radial-gradient(circle at 80% 100%, rgba(111, 202, 255, 0.25), transparent 55%),
    rgba(15, 18, 27, 0.95);
  overflow: hidden;
}

.music-hero-grid {
  position: absolute;
  inset: 10px 10px auto 10px;
  height: 120px;
  background-image: linear-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.08) 1px, transparent 1px);
  background-size: 16px 16px;
  opacity: 0.35;
}

.music-hero-icon {
  position: relative;
  display: block;
  width: 130px;
  margin: 40px auto 24px;
  filter: drop-shadow(0 0 10px rgba(255, 122, 244, 0.5));
}

.music-track-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  font-size: 11px;
  min-height: 100px;
}

.track-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.65);
  color: rgba(248, 250, 252, 0.7);
  cursor: pointer;
}

.track-row .dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.7);
}

.track-row .duration {
  font-variant-numeric: tabular-nums;
  color: rgba(148, 163, 184, 0.9);
}

.track-row.active {
  background: linear-gradient(90deg, rgba(234, 179, 8, 0.2), rgba(56, 189, 248, 0.18));
  box-shadow: 0 0 0 1px rgba(248, 250, 252, 0.1);
}

.track-row.active .dot {
  background: #facc15;
  box-shadow: 0 0 10px rgba(250, 204, 21, 0.9);
}

.track-row.active .title {
  color: #e5e7eb;
}

.music-track-empty {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  min-height: 80px;
  color: rgba(148, 163, 184, 0.6);
  font-size: 12px;
}

.buttons button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.music-player {
  border-top: 1px solid rgba(148, 163, 184, 0.35);
  padding-top: 10px;
}

.mode-btn,
.edit-btn {
  border-radius: 999px;
  border: 1px solid rgba(248, 250, 252, 0.25);
  background: rgba(15, 23, 42, 0.9);
  color: rgba(248, 250, 252, 0.85);
  font-size: 11px;
  padding: 4px 10px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s, border-color 0.15s;
}

.mode-btn:hover,
.edit-btn:hover {
  background: rgba(30, 64, 175, 0.9);
  border-color: rgba(191, 219, 254, 0.9);
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.7);
}

.controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}

.round-btn,
.play-btn {
  border-radius: 999px;
  border: none;
  cursor: pointer;
  background: rgba(15, 23, 42, 0.95);
  color: rgba(248, 250, 252, 0.9);
  font-size: 11px;
  padding: 6px 10px;
  transition: background 0.15s, transform 0.1s, box-shadow 0.15s;
}

.round-btn:hover,
.play-btn:hover {
  background: rgba(30, 64, 175, 0.9);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.6);
}

.play-btn {
  font-size: 13px;
  padding: 8px 14px;
  background: linear-gradient(135deg, rgba(234, 179, 8, 0.95), rgba(59, 130, 246, 0.9));
  color: #020617;
}

.play-btn.playing {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.9), rgba(34, 197, 94, 0.9));
}

.progress-area {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.time {
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: rgba(148, 163, 184, 0.9);
}

.bar {
  position: relative;
  height: 6px;
}

.bar-bg {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: rgba(30, 41, 59, 0.8);
}

.bar-fill {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: linear-gradient(90deg, #facc15, #22c55e);
}

.bar-thumb {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #e5e7eb;
  box-shadow: 0 0 6px rgba(248, 250, 252, 0.8);
  transform: translate(-50%, -50%);
}

.track-title {
  margin-top: 6px;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.9);
}

.track-title .name {
  color: #e5e7eb;
}
</style>
