<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'

// ── Types ──
interface Quintuple {
  subject: string
  subjectType: string
  predicate: string
  object: string
  objectType: string
}

interface SeaNode {
  id: string
  type: string
  weight: number
  px: number
  py: number
  pz: number
  vx: number
  vz: number
  swayA: number
  swayF: number
  swayAmp: number
  swayAx: number
  swayFx: number
  swayAmpX: number
}

interface SeaLink {
  src: SeaNode
  tgt: SeaNode
  relation: string
}

interface Particle {
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  size: number
  alpha: number
  hue: number
  layer: number
}

interface Ray {
  x: number
  z: number
  radius: number
  phase: number
  freq: number
  swayAmp: number
  alpha: number
}

interface FlowDot {
  link: SeaLink
  t: number
  speed: number
  size: number
}

interface Plankton {
  x: number
  y: number
  z: number
  pa: number
  pf1: number
  pf2: number
  pa2: number
  pf3: number
  amp1: number
  amp2: number
  amp3: number
  size: number
  hue: number
  life: number
  maxLife: number
  trail: { x: number, y: number, z: number }[]
}

// ── Constants ──
const MAX_NODES = 100
const FLOOR_Y = 0
const SURFACE_H = 200
const WEIGHT_MAX = 10

const COLORS = [
  '#4fc3f7',
  '#81c784',
  '#ffb74d',
  '#e57373',
  '#ba68c8',
  '#4dd0e1',
  '#aed581',
  '#ff8a65',
  '#f06292',
  '#9575cd',
  '#26c6da',
  '#dce775',
  '#ffa726',
  '#ef5350',
  '#ab47bc',
]

// ── Refs ──
const canvasRef = ref<HTMLCanvasElement>()
const loading = ref(true)
const errorMsg = ref('')
const searchQuery = ref('')
const nodeCount = ref(0)
const quintupleCount = ref(0)

// ── State ──
let W = 0
let H = 0
let dpr = 1
let cx: CanvasRenderingContext2D | null = null
let animId = 0
let t0 = 0

let nodes: SeaNode[] = []
let links: SeaLink[] = []
let particles: Particle[] = []
let rays: Ray[] = []
let flowParts: FlowDot[] = []
let plankton: Plankton[] = []

let cmap: Record<string, string> = {}
let cidx = 0
let camT = 0.5
let camP = 0.45
let camD = 550
let panX = 0
let panY = 0

const cfg = {
  hScale: 1.0,
  spread: 100,
  fontSize: 9,
  sway: 1.0,
  nodeSize: 5,
  particlesOn: true,
  raysOn: true,
  flowOn: true,
  planktonOn: true,
}

let rotating = false
let panning = false
let rsx = 0
let rsy = 0
let rst = 0
let rsp = 0
let panOX = 0
let panOY = 0
let dragging: SeaNode | null = null
let dragMoved = false
let prevMX = 0
let prevMY = 0
let hovered: SeaNode | null = null
let selected: SeaNode | null = null

const showInfo = ref(false)
const infoNode = ref<{ id: string, type: string, weight: number, outCount: number, inCount: number, relations: string[] }>()

// ── Helpers ──
function tc(t: string): string {
  t = t || '?'
  if (!cmap[t])
    cmap[t] = COLORS[cidx++ % COLORS.length]!
  return cmap[t]!
}

function proj(x: number, y: number, z: number) {
  const ct = Math.cos(camT)
  const st = Math.sin(camT)
  const cp = Math.cos(camP)
  const sp = Math.sin(camP)
  const rx = ct * x + st * z
  const ry = y
  const rz = -st * x + ct * z
  const ry2 = cp * ry - sp * rz
  let rz2 = sp * ry + cp * rz
  rz2 += camD
  if (rz2 < 30)
    rz2 = 30
  const s = 700 / rz2
  return { sx: W / 2 + panX + rx * s, sy: H / 2 + panY - ry2 * s, s, d: rz2 }
}

// ── Particle system ──
function initParticles() {
  particles = []
  for (let i = 0; i < 40; i++) {
    particles.push({
      x: (Math.random() - 0.5) * 500,
      y: Math.random() * SURFACE_H * 0.2,
      z: (Math.random() - 0.5) * 500,
      vx: (Math.random() - 0.5) * 0.08,
      vy: 0.01 + Math.random() * 0.03,
      vz: (Math.random() - 0.5) * 0.08,
      size: 0.4 + Math.random() * 0.6,
      alpha: 0.08 + Math.random() * 0.12,
      hue: 200 + Math.random() * 20,
      layer: 0,
    })
  }
  for (let i = 0; i < 60; i++) {
    const big = Math.random() < 0.08
    particles.push({
      x: (Math.random() - 0.5) * 500,
      y: SURFACE_H * 0.1 + Math.random() * SURFACE_H * 0.8,
      z: (Math.random() - 0.5) * 500,
      vx: (Math.random() - 0.5) * 0.12,
      vy: big ? 0.3 + Math.random() * 0.3 : 0.06 + Math.random() * 0.18,
      vz: (Math.random() - 0.5) * 0.12,
      size: big ? 1.8 + Math.random() * 1.5 : 0.5 + Math.random() * 1.2,
      alpha: big ? 0.35 + Math.random() * 0.2 : 0.12 + Math.random() * 0.25,
      hue: 190 + Math.random() * 40,
      layer: 1,
    })
  }
  for (let i = 0; i < 25; i++) {
    particles.push({
      x: (Math.random() - 0.5) * 400,
      y: SURFACE_H * 0.75 + Math.random() * SURFACE_H * 0.3,
      z: (Math.random() - 0.5) * 400,
      vx: (Math.random() - 0.5) * 0.06,
      vy: 0.03 + Math.random() * 0.08,
      vz: (Math.random() - 0.5) * 0.06,
      size: 1 + Math.random() * 2,
      alpha: 0.2 + Math.random() * 0.3,
      hue: 185 + Math.random() * 30,
      layer: 2,
    })
  }
}

function simParticles() {
  const surfY = SURFACE_H * cfg.hScale
  for (const p of particles) {
    p.x += p.vx
    p.y += p.vy
    p.z += p.vz
    if (p.layer === 0) {
      if (p.y > surfY * 0.25) {
        p.y = 0
        p.x = (Math.random() - 0.5) * 500
        p.z = (Math.random() - 0.5) * 500
      }
    }
    else if (p.layer === 1) {
      if (p.y > surfY + 15) {
        p.y = surfY * 0.05
        p.x = (Math.random() - 0.5) * 500
        p.z = (Math.random() - 0.5) * 500
      }
    }
    else {
      if (p.y > surfY + 30) {
        p.y = surfY * 0.7
        p.x = (Math.random() - 0.5) * 400
        p.z = (Math.random() - 0.5) * 400
      }
    }
    if (p.x > 260)
      p.x = -260
    if (p.x < -260)
      p.x = 260
    if (p.z > 260)
      p.z = -260
    if (p.z < -260)
      p.z = 260
  }
}

function drawParticles() {
  if (!cx)
    return
  for (const p of particles) {
    const pp = proj(p.x, p.y, p.z)
    if (pp.d < 50)
      continue
    const fog = Math.min(1, Math.max(0.05, 250 / pp.d))
    const sz = Math.max(0.4, p.size * pp.s)
    const brightMul = p.layer === 2 ? 1.6 : 1
    cx.globalAlpha = p.alpha * fog * brightMul
    cx.fillStyle = `hsl(${p.hue},60%,${p.layer === 2 ? '78' : '65'}%)`
    cx.beginPath()
    cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
    cx.fill()
    if (sz > 0.8) {
      const gr = sz * (p.layer === 2 ? 4 : 2.5)
      const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, gr)
      gg.addColorStop(0, `hsla(${p.hue},70%,75%,${p.alpha * fog * 0.3 * brightMul})`)
      gg.addColorStop(1, 'transparent')
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, gr, 0, Math.PI * 2)
      cx.fillStyle = gg
      cx.fill()
    }
  }
  cx.globalAlpha = 1
}

// ── God Rays ──
function initRays() {
  rays = []
  for (let i = 0; i < 3; i++) {
    rays.push({
      x: (Math.random() - 0.5) * 200,
      z: (Math.random() - 0.5) * 200,
      radius: 18 + Math.random() * 22,
      phase: Math.random() * Math.PI * 2,
      freq: 0.12 + Math.random() * 0.08,
      swayAmp: 25 + Math.random() * 15,
      alpha: 0.018 + Math.random() * 0.012,
    })
  }
}

function drawRays() {
  if (!cx)
    return
  const now = (performance.now() - t0) * 0.001
  const surfY = SURFACE_H * cfg.hScale
  const slices = 14
  const prev = cx.globalCompositeOperation
  cx.globalCompositeOperation = 'lighter'
  for (const r of rays) {
    const sway = Math.sin(now * r.freq + r.phase) * r.swayAmp
    const bx = r.x + sway
    for (let s = 0; s < slices; s++) {
      const t = s / (slices - 1)
      const y = surfY * (1 - t)
      const rad = r.radius * (1 - t * 0.3) * (1 + Math.sin(now * 0.5 + s) * 0.08)
      const pp = proj(bx, y, r.z)
      if (pp.d < 40)
        continue
      const screenR = Math.max(2, rad * pp.s)
      const intensity = r.alpha * (1 - t * 0.85)
      const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, screenR)
      gg.addColorStop(0, `rgba(100,180,255,${intensity})`)
      gg.addColorStop(0.4, `rgba(70,150,240,${intensity * 0.5})`)
      gg.addColorStop(1, 'rgba(50,120,200,0)')
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, screenR, 0, Math.PI * 2)
      cx.fillStyle = gg
      cx.fill()
    }
  }
  cx.globalCompositeOperation = prev
}

// ── Flow particles ──
function initFlow() {
  flowParts = []
  for (const l of links) {
    if (Math.random() < 0.35)
      flowParts.push({ link: l, t: Math.random(), speed: 0.0008 + Math.random() * 0.0012, size: 0.5 + Math.random() * 0.5 })
  }
}

function simFlow() {
  for (const f of flowParts) {
    f.t += f.speed
    if (f.t > 1)
      f.t -= 1
  }
}

function drawFlow() {
  if (!cx)
    return
  const now = (performance.now() - t0) * 0.001
  for (const f of flowParts) {
    const s = f.link.src
    const tg = f.link.tgt
    const fx = s.px + (tg.px - s.px) * f.t
    const fy = s.py + (tg.py - s.py) * f.t
    const fz = s.pz + (tg.pz - s.pz) * f.t
    const pp = proj(fx, fy, fz)
    if (pp.d < 50)
      continue
    const fog = Math.min(1, Math.max(0.1, 250 / pp.d))
    const sz = Math.max(0.4, f.size * pp.s)
    const flicker = 0.7 + 0.3 * Math.sin(now * 6 + f.t * 20)
    cx.globalAlpha = 0.5 * fog * flicker
    cx.fillStyle = 'rgba(255,210,100,1)'
    cx.beginPath()
    cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
    cx.fill()
    const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, sz * 3)
    gg.addColorStop(0, `rgba(255,200,80,${0.35 * fog * flicker})`)
    gg.addColorStop(0.5, `rgba(255,170,50,${0.1 * fog * flicker})`)
    gg.addColorStop(1, 'transparent')
    cx.beginPath()
    cx.arc(pp.sx, pp.sy, sz * 3, 0, Math.PI * 2)
    cx.fillStyle = gg
    cx.fill()
  }
  cx.globalAlpha = 1
}

// ── Plankton ──
function spawnPlankton(): Plankton {
  return {
    x: (Math.random() - 0.5) * 350,
    y: SURFACE_H * 0.1 + Math.random() * SURFACE_H * 0.8,
    z: (Math.random() - 0.5) * 350,
    pa: Math.random() * Math.PI * 2,
    pf1: 0.4 + Math.random() * 0.5,
    pf2: 0.7 + Math.random() * 0.6,
    pa2: Math.random() * Math.PI * 2,
    pf3: 0.3 + Math.random() * 0.3,
    amp1: 0.5 + Math.random() * 0.6,
    amp2: 0.3 + Math.random() * 0.4,
    amp3: 0.2 + Math.random() * 0.3,
    size: 0.4 + Math.random() * 0.5,
    hue: 160 + Math.random() * 50,
    life: 0,
    maxLife: 300 + Math.floor(Math.random() * 400),
    trail: [],
  }
}

function initPlankton() {
  plankton = []
  for (let i = 0; i < 10; i++) {
    const p = spawnPlankton()
    p.life = Math.floor(Math.random() * p.maxLife)
    plankton.push(p)
  }
}

function simPlankton() {
  const now = (performance.now() - t0) * 0.001
  const surfY = SURFACE_H * cfg.hScale
  for (let i = 0; i < plankton.length; i++) {
    const p = plankton[i]!
    p.life++
    if (p.life > p.maxLife) {
      plankton[i] = spawnPlankton()
      continue
    }
    p.x += Math.sin(now * p.pf1 + p.pa) * p.amp1 * 0.12 + Math.cos(now * p.pf3 + p.pa2) * p.amp3 * 0.06
    p.y += Math.sin(now * p.pf2 + p.pa + 1) * p.amp2 * 0.05
    p.z += Math.cos(now * p.pf1 + p.pa + 2) * p.amp1 * 0.10 + Math.sin(now * p.pf3 + p.pa2 + 1) * p.amp3 * 0.05
    if (p.y < FLOOR_Y + 5)
      p.y = FLOOR_Y + 5
    if (p.y > surfY - 5)
      p.y = surfY - 5
    if (p.x > 180)
      p.x = -180
    if (p.x < -180)
      p.x = 180
    if (p.z > 180)
      p.z = -180
    if (p.z < -180)
      p.z = 180
    p.trail.push({ x: p.x, y: p.y, z: p.z })
    if (p.trail.length > 35)
      p.trail.shift()
  }
}

function drawPlankton() {
  if (!cx)
    return
  for (const p of plankton) {
    const lifeRatio = p.life / p.maxLife
    let fade = 1
    if (lifeRatio < 0.15)
      fade = lifeRatio / 0.15
    else if (lifeRatio > 0.8)
      fade = 1 - (lifeRatio - 0.8) / 0.2
    if (fade < 0.01)
      continue
    for (let i = 0; i < p.trail.length - 1; i++) {
      const t = p.trail[i]!
      const pp = proj(t.x, t.y, t.z)
      if (pp.d < 50)
        continue
      const fog = Math.min(1, Math.max(0.05, 250 / pp.d))
      const a = (i / p.trail.length) * 0.18 * fog * fade
      const sz = Math.max(0.2, p.size * 0.4 * pp.s)
      cx.globalAlpha = a
      cx.fillStyle = `hsl(${p.hue},80%,70%)`
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
      cx.fill()
    }
    const pp = proj(p.x, p.y, p.z)
    if (pp.d < 50)
      continue
    const fog = Math.min(1, Math.max(0.1, 250 / pp.d))
    const sz = Math.max(0.3, p.size * pp.s)
    cx.globalAlpha = 0.5 * fog * fade
    cx.fillStyle = `hsl(${p.hue},80%,72%)`
    cx.beginPath()
    cx.arc(pp.sx, pp.sy, sz, 0, Math.PI * 2)
    cx.fill()
    if (sz > 0.4) {
      const gg = cx.createRadialGradient(pp.sx, pp.sy, 0, pp.sx, pp.sy, sz * 3)
      gg.addColorStop(0, `hsla(${p.hue},90%,75%,${0.2 * fog * fade})`)
      gg.addColorStop(1, 'transparent')
      cx.beginPath()
      cx.arc(pp.sx, pp.sy, sz * 3, 0, Math.PI * 2)
      cx.fillStyle = gg
      cx.fill()
    }
  }
  cx.globalAlpha = 1
}

// ── Force simulation ──
function initPositions() {
  const R = 120
  nodes.forEach((n, i) => {
    const a = (i / nodes.length) * Math.PI * 2
    n.px = Math.cos(a) * R * (0.4 + Math.random() * 0.6)
    n.pz = Math.sin(a) * R * (0.4 + Math.random() * 0.6)
    n.py = Math.min(n.weight, WEIGHT_MAX) / WEIGHT_MAX * SURFACE_H * cfg.hScale
    n.vx = 0
    n.vz = 0
    n.swayA = Math.random() * Math.PI * 2
    n.swayF = 0.3 + Math.random() * 0.4
    n.swayAmp = 1.5 + Math.random() * 2
    n.swayAx = Math.random() * Math.PI * 2
    n.swayFx = 0.2 + Math.random() * 0.3
    n.swayAmpX = 0.5 + Math.random()
  })
}

function simulate() {
  const alpha = 0.22
  const fric = 0.88
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const dx = nodes[j]!.px - nodes[i]!.px
      const dz = nodes[j]!.pz - nodes[i]!.pz
      let d2 = dx * dx + dz * dz
      if (d2 < 4)
        d2 = 4
      const d = Math.sqrt(d2)
      const f = cfg.spread * alpha / d2
      nodes[i]!.vx -= dx / d * f
      nodes[i]!.vz -= dz / d * f
      nodes[j]!.vx += dx / d * f
      nodes[j]!.vz += dz / d * f
    }
  }
  for (const l of links) {
    const dx = l.tgt.px - l.src.px
    const dz = l.tgt.pz - l.src.pz
    const d = Math.sqrt(dx * dx + dz * dz) || 1
    const f = (d - 80) * 0.004 * alpha
    l.src.vx += dx / d * f
    l.src.vz += dz / d * f
    l.tgt.vx -= dx / d * f
    l.tgt.vz -= dz / d * f
  }
  for (const n of nodes) {
    n.vx -= n.px * 0.0003
    n.vz -= n.pz * 0.0003
  }
  const now = (performance.now() - t0) * 0.001
  for (const n of nodes) {
    if (n === dragging) {
      n.vx = 0
      n.vz = 0
      continue
    }
    n.vx *= fric
    n.vz *= fric
    n.px += n.vx
    n.pz += n.vz
    const baseY = Math.min(n.weight, WEIGHT_MAX) / WEIGHT_MAX * SURFACE_H * cfg.hScale
    const sway = Math.sin(now * n.swayF + n.swayA) * n.swayAmp * cfg.sway
    n.py += (baseY + sway - n.py) * 0.06
    n.px += Math.sin(now * n.swayFx + n.swayAx) * n.swayAmpX * 0.03 * cfg.sway
    n.pz += Math.cos(now * n.swayFx + n.swayAx + 1) * n.swayAmpX * 0.03 * cfg.sway
  }
}

// ── Drawing ──
function drawFloor() {
  if (!cx)
    return
  const gridN = 10
  const gridS = 30
  const half = gridN * gridS
  cx.strokeStyle = 'rgba(30,60,120,0.18)'
  cx.lineWidth = 0.7
  for (let i = -gridN; i <= gridN; i++) {
    const p1 = proj(i * gridS, FLOOR_Y, -half)
    const p2 = proj(i * gridS, FLOOR_Y, half)
    const p3 = proj(-half, FLOOR_Y, i * gridS)
    const p4 = proj(half, FLOOR_Y, i * gridS)
    cx.beginPath()
    cx.moveTo(p1.sx, p1.sy)
    cx.lineTo(p2.sx, p2.sy)
    cx.stroke()
    cx.beginPath()
    cx.moveTo(p3.sx, p3.sy)
    cx.lineTo(p4.sx, p4.sy)
    cx.stroke()
  }
}

function drawSurface() {
  if (!cx)
    return
  const surfY = SURFACE_H * cfg.hScale
  const half = 300
  const corners = [[-half, surfY, -half], [half, surfY, -half], [half, surfY, half], [-half, surfY, half]] as const
  const pc = corners.map(c => proj(c[0], c[1], c[2]))
  cx.beginPath()
  cx.moveTo(pc[0]!.sx, pc[0]!.sy)
  for (let i = 1; i < 4; i++)
    cx.lineTo(pc[i]!.sx, pc[i]!.sy)
  cx.closePath()
  cx.fillStyle = 'rgba(20,80,180,0.06)'
  cx.fill()
  cx.strokeStyle = 'rgba(40,100,200,0.15)'
  cx.lineWidth = 1
  cx.stroke()
  cx.strokeStyle = 'rgba(50,120,220,0.08)'
  cx.lineWidth = 0.5
  const now = (performance.now() - t0) * 0.0005
  for (let i = 0; i < 6; i++) {
    const off = (i / 6 - 0.5) * half * 1.8
    const p1 = proj(-half, surfY, off + Math.sin(now + i) * 10)
    const p2 = proj(half, surfY, off + Math.sin(now + i + 2) * 10)
    cx.beginPath()
    cx.moveTo(p1.sx, p1.sy)
    cx.lineTo(p2.sx, p2.sy)
    cx.stroke()
  }
}

function drawCompass() {
  if (!cx)
    return
  const ox = W - 70
  const oy = H - 70
  const len = 40
  const ct = Math.cos(camT)
  const st = Math.sin(camT)
  const cp = Math.cos(camP)
  const sp = Math.sin(camP)
  function projAxis(x: number, y: number, z: number) {
    const rx = ct * x + st * z
    const ry2 = cp * y - sp * (-st * x + ct * z)
    return { sx: ox + rx * len, sy: oy - ry2 * len }
  }
  const axes = [
    { x: 1, y: 0, z: 0, label: 'X', color: '#e05555' },
    { x: 0, y: 1, z: 0, label: 'Y', color: '#55cc55' },
    { x: 0, y: 0, z: 1, label: 'Z', color: '#5577ee' },
  ]
  cx.beginPath()
  cx.arc(ox, oy, 52, 0, Math.PI * 2)
  cx.fillStyle = 'rgba(6,12,24,0.7)'
  cx.fill()
  cx.strokeStyle = 'rgba(50,90,160,0.3)'
  cx.lineWidth = 1
  cx.stroke()
  for (const a of axes) {
    const p = projAxis(a.x, a.y, a.z)
    cx.beginPath()
    cx.moveTo(ox, oy)
    cx.lineTo(p.sx, p.sy)
    cx.strokeStyle = a.color
    cx.lineWidth = 2
    cx.stroke()
    const ang = Math.atan2(p.sy - oy, p.sx - ox)
    cx.beginPath()
    cx.moveTo(p.sx, p.sy)
    cx.lineTo(p.sx - Math.cos(ang - 0.4) * 8, p.sy - Math.sin(ang - 0.4) * 8)
    cx.lineTo(p.sx - Math.cos(ang + 0.4) * 8, p.sy - Math.sin(ang + 0.4) * 8)
    cx.closePath()
    cx.fillStyle = a.color
    cx.fill()
    const lx = p.sx + Math.cos(ang) * 12
    const ly = p.sy + Math.sin(ang) * 12
    cx.font = 'bold 9px sans-serif'
    cx.fillStyle = a.color
    cx.textAlign = 'center'
    cx.textBaseline = 'middle'
    cx.fillText(a.label, lx, ly)
  }
}

function drawNodeGlow(sx: number, sy: number, r: number, col: string, fog: number, isHov: boolean) {
  if (!cx)
    return
  if (r > 2) {
    const gr = r * 4
    const gg = cx.createRadialGradient(sx, sy, r * 0.3, sx, sy, gr)
    gg.addColorStop(0, `${col}40`)
    gg.addColorStop(0.3, `${col}18`)
    gg.addColorStop(0.7, `${col}08`)
    gg.addColorStop(1, 'transparent')
    cx.beginPath()
    cx.arc(sx, sy, gr, 0, Math.PI * 2)
    cx.fillStyle = gg
    cx.fill()
  }
  cx.beginPath()
  cx.arc(sx, sy, Math.max(1.5, r), 0, Math.PI * 2)
  cx.globalAlpha = Math.max(0.3, fog)
  cx.fillStyle = isHov ? '#fff' : col
  cx.fill()
  if (r > 3) {
    const hx = sx - r * 0.28
    const hy = sy - r * 0.28
    const hr = r * 0.38
    const ig = cx.createRadialGradient(hx, hy, 0, hx, hy, hr)
    ig.addColorStop(0, `rgba(255,255,255,${isHov ? 0.6 : 0.3 * fog})`)
    ig.addColorStop(1, 'transparent')
    cx.beginPath()
    cx.arc(hx, hy, hr, 0, Math.PI * 2)
    cx.fillStyle = ig
    cx.fill()
  }
  cx.globalAlpha = 1
}

function draw() {
  if (!cx)
    return
  const bg = cx.createLinearGradient(0, 0, 0, H)
  bg.addColorStop(0, '#0a1525')
  bg.addColorStop(0.3, '#06101c')
  bg.addColorStop(0.7, '#040a14')
  bg.addColorStop(1, '#020608')
  cx.fillStyle = bg
  cx.fillRect(0, 0, W, H)

  drawFloor()
  drawSurface()
  if (cfg.raysOn)
    drawRays()
  if (cfg.particlesOn)
    drawParticles()
  if (cfg.planktonOn)
    drawPlankton()

  // Sort items far→near
  const items: Array<{ t: 'L', p1: ReturnType<typeof proj>, p2: ReturnType<typeof proj>, l: SeaLink, d: number } | { t: 'N', p: ReturnType<typeof proj>, n: SeaNode, d: number }> = []
  for (const l of links) {
    const p1 = proj(l.src.px, l.src.py, l.src.pz)
    const p2 = proj(l.tgt.px, l.tgt.py, l.tgt.pz)
    items.push({ t: 'L', p1, p2, l, d: (p1.d + p2.d) / 2 })
  }
  for (const n of nodes) {
    const p = proj(n.px, n.py, n.pz)
    items.push({ t: 'N', p, n, d: p.d })
  }
  items.sort((a, b) => b.d - a.d)

  for (const it of items) {
    if (it.t === 'L') {
      const { p1, p2, l } = it
      const fog = Math.min(1, Math.max(0.05, 300 / ((p1.d + p2.d) / 2)))
      cx.beginPath()
      cx.moveTo(p1.sx, p1.sy)
      cx.lineTo(p2.sx, p2.sy)
      cx.strokeStyle = `rgba(60,100,180,${fog * 0.35})`
      cx.lineWidth = Math.max(0.3, 1.2 * Math.min(p1.s, p2.s))
      cx.stroke()
      // Arrow
      const ang = Math.atan2(p2.sy - p1.sy, p2.sx - p1.sx)
      const tr = cfg.nodeSize * p2.s + 2
      const ax = p2.sx - Math.cos(ang) * tr
      const ay = p2.sy - Math.sin(ang) * tr
      const az = Math.max(2, 4 * p2.s)
      cx.beginPath()
      cx.moveTo(ax, ay)
      cx.lineTo(ax - Math.cos(ang - 0.35) * az, ay - Math.sin(ang - 0.35) * az)
      cx.lineTo(ax - Math.cos(ang + 0.35) * az, ay - Math.sin(ang + 0.35) * az)
      cx.closePath()
      cx.fillStyle = `rgba(60,100,180,${fog * 0.45})`
      cx.fill()
      // Edge label
      if (cfg.fontSize > 0 && Math.min(p1.s, p2.s) > 0.6) {
        const mx = (p1.sx + p2.sx) / 2
        const my = (p1.sy + p2.sy) / 2
        const ef = Math.max(5, cfg.fontSize * Math.min(p1.s, p2.s) * 0.9)
        cx.font = `${ef}px sans-serif`
        cx.fillStyle = `rgba(80,130,200,${fog * 0.35})`
        cx.textAlign = 'center'
        cx.textBaseline = 'middle'
        cx.fillText(l.relation, mx, my)
      }
    }
    else {
      const { p, n } = it
      const r = cfg.nodeSize * p.s
      const col = tc(n.type)
      const fog = Math.min(1, Math.max(0.15, 350 / p.d))
      const isH = n === hovered
      const isS = n === selected

      // Vertical tether
      const pfloor = proj(n.px, FLOOR_Y, n.pz)
      cx.beginPath()
      cx.moveTo(p.sx, p.sy)
      cx.lineTo(pfloor.sx, pfloor.sy)
      cx.strokeStyle = `rgba(60,100,180,${fog * 0.08})`
      cx.lineWidth = 0.5
      cx.setLineDash([2, 4])
      cx.stroke()
      cx.setLineDash([])

      drawNodeGlow(p.sx, p.sy, r, col, fog, isH || isS)

      if (isS) {
        cx.beginPath()
        cx.arc(p.sx, p.sy, r + 3 * p.s, 0, Math.PI * 2)
        cx.strokeStyle = `${col}88`
        cx.lineWidth = 1.2
        cx.stroke()
      }

      if (cfg.fontSize > 0 && r > 2) {
        const lf = Math.max(6, cfg.fontSize * p.s * 0.95)
        cx.font = `bold ${lf}px sans-serif`
        cx.fillStyle = `rgba(190,210,255,${fog * 0.8})`
        cx.textAlign = 'center'
        cx.textBaseline = 'top'
        cx.fillText(n.id, p.sx, p.sy + r + 2)
      }
    }
  }

  if (cfg.flowOn)
    drawFlow()

  // Hover tooltip
  if (hovered) {
    const hp = proj(hovered.px, hovered.py, hovered.pz)
    const hr = cfg.nodeSize * hp.s
    const txt = `${hovered.id} [${hovered.type}] w=${hovered.weight}`
    cx.font = '11px sans-serif'
    const tw = cx.measureText(txt).width
    const bx = hp.sx - tw / 2 - 7
    const by = hp.sy - hr - 26
    cx.fillStyle = 'rgba(4,8,16,0.92)'
    cx.strokeStyle = 'rgba(50,90,160,0.5)'
    cx.lineWidth = 1
    cx.beginPath()
    cx.roundRect(bx, by, tw + 14, 22, 4)
    cx.fill()
    cx.stroke()
    cx.fillStyle = '#aaccee'
    cx.textAlign = 'center'
    cx.textBaseline = 'middle'
    cx.fillText(txt, hp.sx, by + 11)
  }

  drawCompass()
}

function loop() {
  simulate()
  if (cfg.particlesOn)
    simParticles()
  if (cfg.flowOn)
    simFlow()
  if (cfg.planktonOn)
    simPlankton()
  draw()
  animId = requestAnimationFrame(loop)
}

// ── Hit test ──
function findNode(sx: number, sy: number): SeaNode | null {
  let best: SeaNode | null = null
  let bestD = 900
  for (const n of nodes) {
    const p = proj(n.px, n.py, n.pz)
    const r = cfg.nodeSize * p.s + 5
    const d2 = (p.sx - sx) ** 2 + (p.sy - sy) ** 2
    if (d2 < r * r && d2 < bestD) {
      best = n
      bestD = d2
    }
  }
  return best
}

function selectNode(n: SeaNode) {
  selected = n
  let outC = 0
  let inC = 0
  const rels: string[] = []
  for (const l of links) {
    if (l.src === n) {
      outC++
      rels.push(`${n.id} → ${l.relation} → ${l.tgt.id}`)
    }
    if (l.tgt === n) {
      inC++
      rels.push(`${l.src.id} → ${l.relation} → ${n.id}`)
    }
  }
  infoNode.value = { id: n.id, type: n.type, weight: n.weight, outCount: outC, inCount: inC, relations: rels }
  showInfo.value = true
}

// ── Data loading ──
function buildSeaData(quints: Quintuple[]) {
  const degreeMap = new Map<string, number>()
  const nodeMap = new Map<string, { type: string }>()

  for (const q of quints) {
    if (!nodeMap.has(q.subject))
      nodeMap.set(q.subject, { type: q.subjectType })
    if (!nodeMap.has(q.object))
      nodeMap.set(q.object, { type: q.objectType })
    degreeMap.set(q.subject, (degreeMap.get(q.subject) || 0) + 1)
    degreeMap.set(q.object, (degreeMap.get(q.object) || 0) + 1)
  }

  // Cap at MAX_NODES: keep highest-degree nodes
  let selectedIds: Set<string>
  if (nodeMap.size > MAX_NODES) {
    const sorted = [...degreeMap.entries()].sort((a, b) => b[1] - a[1])
    selectedIds = new Set(sorted.slice(0, MAX_NODES).map(e => e[0]))
  }
  else {
    selectedIds = new Set(nodeMap.keys())
  }

  // Reset color map
  cmap = {}
  cidx = 0

  const maxDegree = Math.max(...[...degreeMap.values()], 1)
  nodes = []
  const nm = new Map<string, SeaNode>()
  for (const id of selectedIds) {
    const info = nodeMap.get(id)!
    const degree = degreeMap.get(id) || 1
    const weight = Math.round((degree / maxDegree) * WEIGHT_MAX * 10) / 10
    const n: SeaNode = {
      id,
      type: info.type,
      weight: Math.max(0.3, weight),
      px: 0,
      py: 0,
      pz: 0,
      vx: 0,
      vz: 0,
      swayA: 0,
      swayF: 0,
      swayAmp: 0,
      swayAx: 0,
      swayFx: 0,
      swayAmpX: 0,
    }
    nodes.push(n)
    nm.set(id, n)
    tc(info.type)
  }

  links = []
  for (const q of quints) {
    const src = nm.get(q.subject)
    const tgt = nm.get(q.object)
    if (src && tgt)
      links.push({ src, tgt, relation: q.predicate })
  }

  nodeCount.value = nodes.length
  quintupleCount.value = quints.length

  initPositions()
  initParticles()
  initRays()
  initFlow()
  initPlankton()
}

async function loadData() {
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await API.getQuintuples()
    const quints: Quintuple[] = res.quintuples ?? []
    if (quints.length > 0) {
      buildSeaData(quints)
    }
    else {
      nodes = []
      links = []
    }
    quintupleCount.value = quints.length
  }
  catch (e: any) {
    errorMsg.value = e.message || '加载失败'
  }
  finally {
    loading.value = false
  }
}

async function search() {
  if (!searchQuery.value.trim()) {
    await loadData()
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await API.searchQuintuples(searchQuery.value)
    const quints: Quintuple[] = res.quintuples ?? []
    if (quints.length > 0) {
      buildSeaData(quints)
    }
    else {
      nodes = []
      links = []
    }
    quintupleCount.value = quints.length
  }
  catch (e: any) {
    errorMsg.value = e.message || '搜索失败'
  }
  finally {
    loading.value = false
  }
}

// ── Canvas setup ──
function resize() {
  const cv = canvasRef.value
  if (!cv)
    return
  const container = cv.parentElement
  if (!container)
    return
  dpr = devicePixelRatio || 1
  W = container.clientWidth
  H = container.clientHeight
  cv.width = W * dpr
  cv.height = H * dpr
  cv.style.width = `${W}px`
  cv.style.height = `${H}px`
  cx = cv.getContext('2d')
  if (cx)
    cx.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function setupEvents() {
  const cv = canvasRef.value
  if (!cv)
    return

  cv.addEventListener('contextmenu', e => e.preventDefault())

  cv.addEventListener('mousedown', (e) => {
    e.preventDefault()
    const n = findNode(e.clientX - cv.getBoundingClientRect().left, e.clientY - cv.getBoundingClientRect().top)
    if (e.button === 1 || (e.button === 0 && e.shiftKey) || e.button === 2) {
      panning = true
      rsx = e.clientX
      rsy = e.clientY
      panOX = panX
      panOY = panY
      cv.style.cursor = 'move'
    }
    else if (n) {
      dragging = n
      dragMoved = false
      prevMX = e.clientX
      prevMY = e.clientY
      cv.style.cursor = 'grabbing'
    }
    else {
      rotating = true
      rsx = e.clientX
      rsy = e.clientY
      rst = camT
      rsp = camP
      selected = null
      showInfo.value = false
      cv.style.cursor = 'grabbing'
    }
  })

  cv.addEventListener('mousemove', (e) => {
    const rect = cv.getBoundingClientRect()
    if (dragging) {
      const dp = proj(dragging.px, dragging.py, dragging.pz)
      const scale = dp.d / 700
      const dx = e.clientX - prevMX
      const dy = e.clientY - prevMY
      if (Math.abs(dx) + Math.abs(dy) > 2)
        dragMoved = true
      const ct = Math.cos(camT)
      const st = Math.sin(camT)
      const cp = Math.cos(camP)
      const sp = Math.sin(camP)
      dragging.px += dx * scale * ct - dy * scale * sp * st
      dragging.pz += dx * scale * st + dy * scale * sp * ct
      dragging.py -= dy * scale * cp
      prevMX = e.clientX
      prevMY = e.clientY
    }
    else if (panning) {
      panX = panOX + (e.clientX - rsx)
      panY = panOY + (e.clientY - rsy)
    }
    else if (rotating) {
      camT = rst - (e.clientX - rsx) * 0.005
      camP = rsp - (e.clientY - rsy) * 0.005
    }
    else {
      hovered = findNode(e.clientX - rect.left, e.clientY - rect.top)
      cv.style.cursor = hovered ? 'pointer' : 'grab'
    }
  })

  cv.addEventListener('mouseup', () => {
    if (dragging) {
      if (!dragMoved)
        selectNode(dragging)
      dragging = null
    }
    rotating = false
    panning = false
    cv.style.cursor = 'grab'
  })

  cv.addEventListener('mouseleave', () => {
    rotating = false
    panning = false
    dragging = null
    hovered = null
  })

  cv.addEventListener('wheel', (e) => {
    e.preventDefault()
    camD *= e.deltaY > 0 ? 1.07 : 0.93
    camD = Math.max(80, Math.min(3000, camD))
  }, { passive: false })

  // Touch support
  let td = 0
  let tpan = false
  cv.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      const rect = cv.getBoundingClientRect()
      const t0 = e.touches[0]!
      const n = findNode(t0.clientX - rect.left, t0.clientY - rect.top)
      if (n) {
        dragging = n
        dragMoved = false
        prevMX = t0.clientX
        prevMY = t0.clientY
      }
      else {
        rotating = true
        rsx = t0.clientX
        rsy = t0.clientY
        rst = camT
        rsp = camP
      }
    }
    else if (e.touches.length === 2) {
      const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
      const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
      td = Math.sqrt(dx * dx + dy * dy)
    }
    else if (e.touches.length === 3) {
      tpan = true
      rsx = e.touches[0]!.clientX
      rsy = e.touches[0]!.clientY
      panOX = panX
      panOY = panY
    }
  }, { passive: true })

  cv.addEventListener('touchmove', (e) => {
    e.preventDefault()
    if (dragging && e.touches.length === 1) {
      const t0 = e.touches[0]!
      const dp = proj(dragging.px, dragging.py, dragging.pz)
      const scale = dp.d / 700
      const dx = t0.clientX - prevMX
      const dy = t0.clientY - prevMY
      if (Math.abs(dx) + Math.abs(dy) > 2)
        dragMoved = true
      const ct = Math.cos(camT)
      const st = Math.sin(camT)
      const cp = Math.cos(camP)
      const sp = Math.sin(camP)
      dragging.px += dx * scale * ct - dy * scale * sp * st
      dragging.pz += dx * scale * st + dy * scale * sp * ct
      dragging.py -= dy * scale * cp
      prevMX = t0.clientX
      prevMY = t0.clientY
    }
    else if (e.touches.length === 1 && rotating) {
      camT = rst - (e.touches[0]!.clientX - rsx) * 0.005
      camP = rsp - (e.touches[0]!.clientY - rsy) * 0.005
    }
    else if (e.touches.length === 2) {
      const dx = e.touches[1]!.clientX - e.touches[0]!.clientX
      const dy = e.touches[1]!.clientY - e.touches[0]!.clientY
      const nd = Math.sqrt(dx * dx + dy * dy)
      camD *= td / nd
      camD = Math.max(80, Math.min(3000, camD))
      td = nd
    }
    else if (e.touches.length === 3 && tpan) {
      panX = panOX + (e.touches[0]!.clientX - rsx)
      panY = panOY + (e.touches[0]!.clientY - rsy)
    }
  }, { passive: false })

  cv.addEventListener('touchend', () => {
    if (dragging && !dragMoved)
      selectNode(dragging)
    rotating = false
    dragging = null
    tpan = false
  })
}

let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  t0 = performance.now()
  resize()
  setupEvents()

  // Watch for container resize
  const cv = canvasRef.value
  if (cv?.parentElement) {
    resizeObserver = new ResizeObserver(() => resize())
    resizeObserver.observe(cv.parentElement)
  }

  await loadData()

  if (!errorMsg.value)
    animId = requestAnimationFrame(loop)
})

onUnmounted(() => {
  if (animId)
    cancelAnimationFrame(animId)
  if (resizeObserver)
    resizeObserver.disconnect()
})

// Restart animation when data changes
watch(loading, (isLoading) => {
  if (!isLoading && !errorMsg.value && nodes.length > 0) {
    if (animId)
      cancelAnimationFrame(animId)
    animId = requestAnimationFrame(loop)
  }
})

// Legend
const legendTypes = ref<string[]>([])
watch(nodeCount, () => {
  legendTypes.value = [...new Set(nodes.map(n => n.type))]
})
</script>

<template>
  <BoxContainer class="text-sm" no-scroll>
    <div class="text-white flex flex-col flex-1 min-h-0">
      <!-- Header -->
      <div class="flex items-center gap-3 mb-3 shrink-0">
        <h2 class="text-lg font-bold">
          记忆云海
        </h2>
        <div class="flex-1 flex items-center gap-2">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索关键词..."
            class="flex-1 bg-white/10 border border-white/20 rounded px-3 py-1.5 text-sm text-white placeholder-white/40 outline-none focus:border-white/40"
            @keyup.enter="search"
          >
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="search"
          >
            搜索
          </button>
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="searchQuery = ''; loadData()"
          >
            刷新
          </button>
        </div>
      </div>

      <!-- Stats -->
      <div class="flex gap-4 text-xs text-white/50 mb-2 shrink-0">
        <span>五元组: {{ quintupleCount }}</span>
        <span>实体: {{ nodeCount }}</span>
      </div>

      <!-- 3D Canvas：在限定高度内占满剩余空间 -->
      <div class="flex-1 relative min-h-[360px] rounded-lg overflow-hidden">
        <!-- Loading overlay -->
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-[#030810] z-10">
          <span class="text-[#3366aa] text-base tracking-widest">Loading...</span>
        </div>
        <!-- Error -->
        <div v-else-if="errorMsg" class="absolute inset-0 flex items-center justify-center bg-[#030810]">
          <span class="text-red-400">{{ errorMsg }}</span>
        </div>
        <!-- Empty state -->
        <div
          v-else-if="nodeCount === 0"
          class="absolute inset-0 flex flex-col items-center justify-center bg-[#030810] text-white/40"
        >
          <p>暂无五元组数据</p>
          <p class="text-xs mt-1">
            请先进行对话以生成知识图谱，或前往「记忆链接」启用 GRAG
          </p>
        </div>

        <canvas ref="canvasRef" class="w-full h-full" style="cursor: grab" />

        <!-- Legend overlay -->
        <div
          v-if="legendTypes.length > 0 && !loading"
          class="absolute bottom-3 left-3 bg-[rgba(6,12,24,0.88)] border border-[rgba(50,90,160,0.3)] rounded-lg px-3 py-2 backdrop-blur-sm text-[10px]"
        >
          <div v-for="t in legendTypes" :key="t" class="flex items-center gap-1.5 my-0.5">
            <span class="inline-block w-2.5 h-2.5 rounded-full" :style="{ background: tc(t) }" />
            <span class="text-white/60">{{ t }}</span>
          </div>
        </div>

        <!-- Node info panel -->
        <div
          v-if="showInfo && infoNode"
          class="absolute top-3 right-3 bg-[rgba(6,12,24,0.92)] border border-[rgba(50,90,160,0.4)] rounded-lg px-4 py-3 backdrop-blur-sm text-[11px] min-w-[200px] max-w-[300px]"
        >
          <div class="flex justify-between items-start">
            <h4 class="text-[#5580bb] text-[13px] font-bold">
              {{ infoNode.id }}
            </h4>
            <button class="text-white/30 hover:text-white/60 text-xs ml-2" @click="showInfo = false; selected = null">
              ✕
            </button>
          </div>
          <div class="mt-1 text-[#6688aa]">
            Type: <span class="text-[#aaccff]">{{ infoNode.type }}</span>
          </div>
          <div class="text-[#6688aa]">
            Weight: <span class="text-[#7bf] text-sm">{{ infoNode.weight }}</span>
          </div>
          <div class="text-[#6688aa]">
            Out: <span class="text-[#aaccff]">{{ infoNode.outCount }}</span>
            &middot; In: <span class="text-[#aaccff]">{{ infoNode.inCount }}</span>
          </div>
          <hr class="border-[#152030] my-1.5">
          <div class="max-h-[150px] overflow-y-auto text-[9px] text-[#6688aa]">
            <div v-for="(r, i) in infoNode.relations" :key="i" class="my-0.5">
              {{ r }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </BoxContainer>
</template>
