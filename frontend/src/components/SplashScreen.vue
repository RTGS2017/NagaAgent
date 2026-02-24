<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef } from 'vue'
import NetworkCanvas from '@/components/NetworkCanvas.vue'
import { playWakeVoice } from '@/composables/useAudio'
import { CONFIG } from '@/utils/config'

const props = defineProps<{
  progress: number
  phase: string
  modelReady: boolean
  stallHint: boolean
}>()

const emit = defineEmits<{
  dismiss: []
  titleDone: []
}>()

// ─── 标题阶段 ───────────────────────────────
const titleOverlayVisible = ref(true)

onMounted(() => {
  // 标题图标出现时同时播放开机语音
  playWakeVoice()
})

function onTitleAnimEnd() {
  // 标题图片动画结束 → 淡出黑色遮罩
  titleOverlayVisible.value = false
}

function onOverlayAfterLeave() {
  // 黑色遮罩完全淡出 → 标题阶段结束，清理粒子
  stopParticles()
  emit('titleDone')
}

// ─── 标题粒子效果（从下往上飘） ──────────────────
const particleCanvas = useTemplateRef<HTMLCanvasElement>('particleCanvas')
let particleRaf = 0

interface Particle {
  x: number
  y: number
  vy: number // 上升速度
  vx: number // 微小水平漂移
  size: number
  alpha: number
  maxAlpha: number
  life: number // 剩余帧
  maxLife: number
}

function initParticles() {
  const canvas = particleCanvas.value
  if (!canvas)
    return

  const ctx = canvas.getContext('2d')!
  if (!ctx)
    return

  const dpr = window.devicePixelRatio || 1
  canvas.width = canvas.clientWidth * dpr
  canvas.height = canvas.clientHeight * dpr
  ctx.scale(dpr, dpr)

  const w = canvas.clientWidth
  const h = canvas.clientHeight
  const particles: Particle[] = []
  const PARTICLE_COUNT = 40

  function spawnParticle(): Particle {
    return {
      x: Math.random() * w,
      y: h + Math.random() * 20, // 从底部稍下方生成
      vy: -(0.3 + Math.random() * 0.8), // 上升速度
      vx: (Math.random() - 0.5) * 0.3, // 微小水平漂移
      size: 1 + Math.random() * 2.5,
      alpha: 0,
      maxAlpha: 0.2 + Math.random() * 0.5,
      life: 200 + Math.random() * 200,
      maxLife: 0, // 在生成后设置
    }
  }

  // 初始化粒子（分散在不同高度）
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const p = spawnParticle()
    p.y = Math.random() * h // 初始分散
    p.life = Math.random() * 300
    p.maxLife = p.life
    particles.push(p)
  }

  function animate() {
    ctx.clearRect(0, 0, w, h)

    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i]!
      p.x += p.vx
      p.y += p.vy
      p.life--

      // 淡入淡出
      const lifeRatio = p.maxLife > 0 ? p.life / p.maxLife : 0
      if (lifeRatio > 0.8) {
        // 前 20%: 淡入
        p.alpha = p.maxAlpha * ((1 - lifeRatio) / 0.2)
      }
      else if (lifeRatio < 0.3) {
        // 后 30%: 淡出
        p.alpha = p.maxAlpha * (lifeRatio / 0.3)
      }
      else {
        p.alpha = p.maxAlpha
      }

      // 绘制发光粒子
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(212, 175, 55, ${p.alpha})`
      ctx.fill()

      // 外发光
      if (p.size > 1.5) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(212, 175, 55, ${p.alpha * 0.15})`
        ctx.fill()
      }

      // 回收并重新生成
      if (p.life <= 0 || p.y < -10) {
        const np = spawnParticle()
        np.maxLife = np.life
        particles[i] = np
      }
    }

    particleRaf = requestAnimationFrame(animate)
  }

  particleRaf = requestAnimationFrame(animate)
}

function stopParticles() {
  if (particleRaf) {
    cancelAnimationFrame(particleRaf)
    particleRaf = 0
  }
}

onMounted(() => {
  initParticles()
})

onBeforeUnmount(() => {
  stopParticles()
})

// ─── 进度 ─────────────────────────────────
const canDismiss = computed(() => props.progress >= 100)
const displayProgress = computed(() => Math.min(100, Math.round(props.progress)))
</script>

<template>
  <div class="fixed inset-0 z-50 overflow-hidden select-none">
    <!-- 金色神经网络粒子动画（透明背景，Live2D 可从下层透出） -->
    <NetworkCanvas />

    <!-- clip-path evenodd 开洞遮罩：中间矩形区域透明，四周深色 -->
    <div class="frame-mask" />

    <!-- 矩形框金色边框 -->
    <div class="frame-border" />

    <!-- 底部进度区域 -->
    <div class="absolute bottom-12 left-1/2 -translate-x-1/2 w-60% flex flex-col items-center gap-2">
      <!-- 阶段文字 + 百分比 -->
      <div
        class="flex justify-between w-full px-1 text-xs tracking-widest"
        style="color: rgba(212, 175, 55, 0.7); font-family: 'Segoe UI', sans-serif;"
      >
        <span>{{ phase }}</span>
        <span>{{ displayProgress }}%</span>
      </div>
      <!-- 进度条轨道 -->
      <div class="w-full h-0.5 rounded-full" style="background: rgba(212, 175, 55, 0.15);">
        <div
          class="h-full rounded-full transition-all duration-300 ease-out"
          style="background: linear-gradient(90deg, rgba(212, 175, 55, 0.4), rgba(212, 175, 55, 0.9));"
          :style="{ width: `${displayProgress}%` }"
        />
      </div>
      <!-- 停滞提示 -->
      <Transition name="fade">
        <span v-if="stallHint" class="stall-hint">如果中途卡死，请重启应用</span>
      </Transition>
    </div>

    <!-- 左下角版本号 -->
    <div class="version-label">
      v{{ CONFIG.system.version }}
    </div>

    <!-- 点击进入提示 -->
    <Transition name="fade">
      <div
        v-if="canDismiss"
        class="absolute inset-0 flex items-end justify-center pb-28 cursor-pointer clickable"
        @click="emit('dismiss')"
      >
        <span class="click-hint text-sm tracking-[0.3em]" style="color: rgba(212, 175, 55, 0.8);">
          点 击 唤 醒
        </span>
      </div>
    </Transition>

    <!-- 标题阶段：纯黑遮罩 + 标题图片 + 上升粒子 -->
    <Transition name="title-overlay" @after-leave="onOverlayAfterLeave">
      <div v-if="titleOverlayVisible" class="title-overlay">
        <!-- 上升粒子 canvas -->
        <canvas ref="particleCanvas" class="absolute inset-0 w-full h-full" />
        <!-- 标题图片 -->
        <div class="title-content" @animationend="onTitleAnimEnd">
          <img src="/assets/title.png" alt="娜迦协议" class="title-img">
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.frame-mask {
  position: absolute;
  inset: 0;
  /* 居中矩形开洞 - 宽度约36vw, 高度约52vh, 稍偏上 */
  --frame-w: 36vw;
  --frame-h: 52vh;
  --frame-x: calc(50% - var(--frame-w) / 2);
  --frame-y: calc(38% - var(--frame-h) / 2);
  /* evenodd 填充规则：内外路径交叉区域镂空 */
  clip-path: polygon(
    evenodd,
    0% 0%, 100% 0%, 100% 100%, 0% 100%,
    var(--frame-x) var(--frame-y),
    var(--frame-x) calc(var(--frame-y) + var(--frame-h)),
    calc(var(--frame-x) + var(--frame-w)) calc(var(--frame-y) + var(--frame-h)),
    calc(var(--frame-x) + var(--frame-w)) var(--frame-y)
  );
  background: rgba(0, 0, 0, 0.85);
  pointer-events: none;
}

.frame-border {
  position: absolute;
  width: 36vw;
  height: 52vh;
  left: 50%;
  top: 38%;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(212, 175, 55, 0.4);
  box-shadow: 0 0 15px rgba(212, 175, 55, 0.15), inset 0 0 15px rgba(212, 175, 55, 0.05);
  pointer-events: none;
}

/* 停滞提示 */
.stall-hint {
  margin-top: 0.5rem;
  font-size: 0.65rem;
  color: rgba(212, 175, 55, 0.45);
  letter-spacing: 0.05em;
}

/* 左下角版本号 */
.version-label {
  position: absolute;
  bottom: 1.2rem;
  left: 1.5rem;
  font-size: 0.75rem;
  color: rgba(212, 175, 55, 0.35);
  letter-spacing: 0.08em;
  font-family: 'Segoe UI', sans-serif;
}

/* 点击进入脉冲动画 */
.click-hint {
  animation: pulse-gold 2s ease-in-out infinite;
}

@keyframes pulse-gold {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; text-shadow: 0 0 12px rgba(212, 175, 55, 0.5); }
}

/* 内部元素淡入 */
.fade-enter-active {
  transition: opacity 0.6s ease;
}
.fade-enter-from {
  opacity: 0;
}

/* ─── 标题阶段 ─────────────────────────────── */
.title-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.title-content {
  position: relative;
  z-index: 1;
  /* 0→0.6s 渐入, 0.6→1.6s 保持, 1.6→2.4s 渐出 */
  animation: title-sequence 2.4s ease-in-out forwards;
}

.title-img {
  width: min(60vw, 500px);
  height: auto;
  filter: drop-shadow(0 0 30px rgba(212, 175, 55, 0.25));
  image-rendering: -webkit-optimize-contrast;
}

@keyframes title-sequence {
  0%   { opacity: 0; transform: scale(0.96); }
  25%  { opacity: 1; transform: scale(1); }     /* 0.6s — 渐入完成 */
  67%  { opacity: 1; transform: scale(1); }     /* 1.6s — 保持至少 1 秒 */
  100% { opacity: 0; transform: scale(1.02); }  /* 2.4s — 渐出完成 */
}

/* 黑色遮罩淡出 */
.title-overlay-leave-active {
  transition: opacity 0.8s ease;
}
.title-overlay-leave-to {
  opacity: 0;
}
</style>
