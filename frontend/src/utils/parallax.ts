import { readonly, ref } from 'vue'

const parallaxX = ref(0)
const parallaxY = ref(0)

let targetX = 0
let targetY = 0
let rafId = 0
let lastTime = 0

const HALF_LIFE = 80 // ms — controls smoothing speed
const DECAY = Math.LN2 / HALF_LIFE

function onMouseMove(e: MouseEvent) {
  const cx = window.innerWidth / 2
  const cy = window.innerHeight / 2
  targetX = (e.clientX - cx) / cx // [-1, 1]
  targetY = (e.clientY - cy) / cy
}

function onMouseLeave() {
  targetX = 0
  targetY = 0
}

function tick(now: number) {
  if (lastTime) {
    const dt = now - lastTime
    const factor = 1 - Math.exp(-DECAY * dt)
    parallaxX.value += (targetX - parallaxX.value) * factor
    parallaxY.value += (targetY - parallaxY.value) * factor
  }
  lastTime = now
  rafId = requestAnimationFrame(tick)
}

export function initParallax() {
  if (rafId)
    return
  window.addEventListener('mousemove', onMouseMove, { passive: true })
  document.documentElement.addEventListener('mouseleave', onMouseLeave)
  rafId = requestAnimationFrame(tick)
}

export function destroyParallax() {
  window.removeEventListener('mousemove', onMouseMove)
  document.documentElement.removeEventListener('mouseleave', onMouseLeave)
  cancelAnimationFrame(rafId)
  rafId = 0
  lastTime = 0
}

export const pX = readonly(parallaxX)
export const pY = readonly(parallaxY)
