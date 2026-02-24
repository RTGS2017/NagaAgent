<script setup lang="ts">
import { onMounted, onUnmounted, useTemplateRef } from 'vue'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}

const canvasRef = useTemplateRef('canvas')
let rafId = 0
let particles: Particle[] = []
// 当前 canvas 尺寸（由 handleResize 更新，tick 每帧读取）
let canvasW = 0
let canvasH = 0

const PARTICLE_COUNT = 40
const MAX_DISTANCE = 200
const NODE_COLOR = 'rgba(212, 175, 55, 0.6)'

function createParticles(w: number, h: number): Particle[] {
  return Array.from({ length: PARTICLE_COUNT }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.8 + (Math.random() > 0.5 ? 0.2 : -0.2),
    vy: (Math.random() - 0.5) * 0.8 + (Math.random() > 0.5 ? 0.2 : -0.2),
    radius: Math.random() * 1.5 + 1,
  }))
}

function tick(ctx: CanvasRenderingContext2D) {
  const w = canvasW
  const h = canvasH
  ctx.clearRect(0, 0, w, h)

  // 更新粒子位置
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy

    // 边界反弹
    if (p.x < 0 || p.x > w)
      p.vx *= -1
    if (p.y < 0 || p.y > h)
      p.vy *= -1
    p.x = Math.max(0, Math.min(w, p.x))
    p.y = Math.max(0, Math.min(h, p.y))
  }

  // 绘制连线
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const pi = particles[i]!
      const pj = particles[j]!
      const dx = pi.x - pj.x
      const dy = pi.y - pj.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < MAX_DISTANCE) {
        const alpha = (1 - dist / MAX_DISTANCE) * 0.3
        ctx.beginPath()
        ctx.strokeStyle = `rgba(212, 175, 55, ${alpha})`
        ctx.lineWidth = 0.5
        ctx.moveTo(pi.x, pi.y)
        ctx.lineTo(pj.x, pj.y)
        ctx.stroke()
      }
    }
  }

  // 绘制节点
  for (const p of particles) {
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx.fillStyle = NODE_COLOR
    ctx.fill()
  }

  rafId = requestAnimationFrame(() => tick(ctx))
}

function handleResize() {
  const cvs = canvasRef.value
  if (!cvs)
    return
  canvasW = window.innerWidth
  canvasH = window.innerHeight
  cvs.width = canvasW
  cvs.height = canvasH
  particles = createParticles(canvasW, canvasH)
}

onMounted(() => {
  const cvs = canvasRef.value
  if (!cvs)
    return
  const ctx = cvs.getContext('2d')
  if (!ctx)
    return

  handleResize()
  window.addEventListener('resize', handleResize)

  rafId = requestAnimationFrame(() => tick(ctx))
})

onUnmounted(() => {
  if (rafId)
    cancelAnimationFrame(rafId)
  window.removeEventListener('resize', handleResize)
})
</script>

<template>
  <canvas ref="canvas" class="absolute inset-0 size-full" />
</template>
