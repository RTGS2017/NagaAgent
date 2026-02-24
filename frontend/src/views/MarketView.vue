<script setup lang="ts">
import { h, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const tabs = [
  { id: 'album', label: '专辑' },
  { id: 'mcp', label: 'mcp' },
  { id: 'skill', label: '技能' },
  { id: 'skin', label: '角色皮肤' },
  { id: 'memory-skin', label: '记忆海皮肤' },
  { id: 'memory-trade', label: '记忆交易' },
  { id: 'recharge', label: '氪金' },
] as const

const svgIcon = (...paths: string[]) => h('svg', { 'viewBox': '0 0 24 24', 'fill': 'none', 'stroke': 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'class': 'tab-icon-svg' }, paths.map(d => h('path', { d })))

const tabIcons: Record<string, { render: () => ReturnType<typeof h> }> = {
  'album': { render: () => svgIcon('M9 18V5l12-2v13', 'M9 18a3 3 0 1 0 6 0 9 9 0 0 0 6 0') },
  'mcp': { render: () => svgIcon('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z') },
  'skill': { render: () => svgIcon('M13 2L3 14h9l-1 8 10-12h-9l1-8z') },
  'skin': { render: () => svgIcon('M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2', 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z') },
  'memory-skin': { render: () => svgIcon('M2 10c3 0 5 2 8 0s5-2 8 0', 'M2 14c3 0 5 2 8 0s5-2 8 0') },
  'memory-trade': { render: () => svgIcon('M7 16V4m0 0L3 8m4-4l4 4', 'M17 8v12m0 0l4-4m-4 4l-4-4') },
  'recharge': { render: () => svgIcon('M12 2L3 9l4 12h10l4-12-9-7z') },
}

type TabId = typeof tabs[number]['id']
const activeTab = ref<TabId>('album')

// 专辑示例数据
const albumItems = [
  { id: 1, title: '向日葵之约', subtitle: '夏日微风', daysLeft: 16, price: 18, image: '/assets/just.png' },
  { id: 2, title: '半甜草莓', subtitle: '测试', daysLeft: 6, price: 24, image: '/assets/just.png' },
  { id: 3, title: '红丝带之约', subtitle: '测试', daysLeft: 12, price: 21, image: '/assets/just.png' },
  { id: 4, title: '测试文本', subtitle: '测试', daysLeft: 30, price: 18, image: '/assets/just.png' },
  { id: 5, title: '测试文本', subtitle: '测试', daysLeft: 8, price: 22, image: '/assets/just.png' },
]

// ── 拖动横向滚动 ──
const albumSection = ref<HTMLElement | null>(null)

let dragActive = false
let dragStartX = 0
let dragScrollLeft = 0

function onPointerMove(e: MouseEvent) {
  if (!dragActive || !albumSection.value)
    return
  const x = e.pageX - albumSection.value.getBoundingClientRect().left
  const delta = x - dragStartX
  albumSection.value.scrollLeft = dragScrollLeft - delta
}

function onPointerUp() {
  dragActive = false
  document.removeEventListener('mousemove', onPointerMove)
  document.removeEventListener('mouseup', onPointerUp)
  if (albumSection.value)
    albumSection.value.style.cursor = 'grab'
  document.body.style.cursor = ''
}

function onWheel(e: WheelEvent) {
  if (!albumSection.value)
    return
  albumSection.value.scrollLeft += e.deltaY
}

function onDragStart(e: MouseEvent) {
  if (!albumSection.value)
    return
  dragActive = true
  dragStartX = e.pageX - albumSection.value.getBoundingClientRect().left
  dragScrollLeft = albumSection.value.scrollLeft
  albumSection.value.style.cursor = 'grabbing'
  document.body.style.cursor = 'grabbing'
  document.addEventListener('mousemove', onPointerMove)
  document.addEventListener('mouseup', onPointerUp)
}
</script>

<template>
  <div class="market-page">
    <!-- 顶部栏：返回 + 标题 -->
    <header class="market-header">
      <div class="header-left">
        <button type="button" class="back-btn" title="返回" @click="router.back">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <h1 class="market-title">
          枢机集市
        </h1>
      </div>
    </header>

    <!-- 标签导航 -->
    <nav class="market-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        type="button"
        class="tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <component :is="tabIcons[tab.id]" />
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </nav>

    <!-- 内容区 -->
    <main class="market-content">
      <!-- 专辑 -->
      <section
        v-show="activeTab === 'album'"
        ref="albumSection"
        class="album-section"
        @mousedown="onDragStart"
        @wheel.prevent="onWheel"
      >
        <div class="album-grid">
          <div
            v-for="item in albumItems"
            :key="item.id"
            class="album-card"
          >
            <div class="card-illust">
              <img :src="item.image" :alt="item.title" class="card-img">
              <div class="card-illust-gradient" />
              <div class="card-watermark">NagaAgent</div>
              <div class="card-banner">
                剩余{{ item.daysLeft }}天
              </div>
            </div>
            <div class="card-info">
              <div class="card-title-main">{{ item.title }}</div>
              <div class="card-title-sub">{{ item.subtitle }}</div>
            </div>
            <div class="card-price-bar">
              <span class="price-icon">◆</span>
              <span class="price-num">{{ item.price }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 其他标签占位 -->
      <section v-show="activeTab !== 'album'" class="placeholder-section">
        <div class="placeholder-text">
          {{ tabs.find(t => t.id === activeTab)?.label }} — 敬请期待
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* ── 面板容器：窗口宽度 × 3/4 高度，垂直居中 ── */
.market-page {
  position: fixed;
  top: 12.5vh;         /* (100 - 75) / 2 = 12.5 → 垂直居中 */
  left: 0;
  right: 0;
  height: 75vh;
  z-index: 200;
  display: flex;
  flex-direction: column;
  background: rgba(15, 17, 21, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 16px;
  border: 1px solid rgba(212, 175, 55, 0.3);
  overflow: hidden;
  /* 不设自定义 animation，由 Vue Router Transition (slide-in / slide-out) 接管 */
}

.market-page::before {
  content: '';
  position: absolute;
  top: 0;
  left: 10%;
  right: 10%;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(251, 191, 36, 0.9) 50%,
    transparent 100%
  );
  z-index: 1;
  pointer-events: none;
}

/* ── 顶部 Header ── */
.market-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px 8px;
  background: rgba(20, 22, 28, 0.5);
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  flex-shrink: 0;
  min-height: 48px;
  position: relative;
  z-index: 1;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(248, 250, 252, 0.75);
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.13);
  border-color: rgba(212, 175, 55, 0.45);
  color: #fff;
}

.market-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
}

/* ── Tab 栏 ── */
.market-tabs {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  width: 100%;
  flex-shrink: 0;
  background: rgba(12, 14, 18, 0.8);
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  min-height: 56px;
}

.tab-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  padding: 8px 4px 10px;
  border: none;
  border-radius: 0;
  border-right: 1px solid rgba(148, 163, 184, 0.1);
  background: transparent;
  color: rgba(248, 250, 252, 0.45);
  font-size: 11px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
  white-space: nowrap;
  position: relative;
  overflow: hidden;
}

.tab-btn:last-child {
  border-right: none;
}

.tab-btn:hover {
  color: rgba(248, 250, 252, 0.85);
  background: rgba(255, 255, 255, 0.05);
}

.tab-btn.active {
  color: rgba(251, 191, 36, 0.98);
  background: rgba(251, 191, 36, 0.08);
}

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 10%,
    rgba(251, 191, 36, 0.9) 50%,
    transparent 90%
  );
  border-radius: 1px 1px 0 0;
}

.tab-btn.active .tab-icon-svg {
  color: rgba(251, 191, 36, 0.98);
}

.tab-icon-svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  color: inherit;
}

.tab-label {
  white-space: nowrap;
  line-height: 1;
}

/* ── 内容区 ── */
.market-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.album-section {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 14px 16px;
  cursor: grab;
  user-select: none;
}

.album-section::-webkit-scrollbar {
  height: 4px;
}

.album-section::-webkit-scrollbar-track {
  background: transparent;
}

.album-section::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.25);
  border-radius: 2px;
}

.album-section::-webkit-scrollbar-thumb:hover {
  background: rgba(212, 175, 55, 0.45);
}

.album-grid {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 12px;
  height: 100%;
  align-items: stretch;
  min-width: min-content;
}

/* ── 卡片 ── */
.album-card {
  position: relative;
  flex-shrink: 0;
  width: calc(75vh - 218px);
  min-width: 100px;
  height: 100%;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.12);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.album-card:hover {
  transform: translateY(-4px) scale(1.02);
  border-color: rgba(251, 191, 36, 0.5);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.5),
    0 0 20px rgba(251, 191, 36, 0.18);
}

/* 图片区域 */
.card-illust {
  position: relative;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.card-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* 底部渐变蒙版 */
.card-illust-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    transparent 50%,
    rgba(0, 0, 0, 0.75) 100%
  );
  pointer-events: none;
  z-index: 1;
}

/* 水印文字 */
.card-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-30deg);
  font-size: 18px;
  font-weight: 900;
  font-family: 'Noto Serif SC', serif;
  color: rgba(255, 255, 255, 0.12);
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
  z-index: 2;
  letter-spacing: 0.05em;
}

/* 剩余天数徽章 */
.card-banner {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 3px 8px;
  background: linear-gradient(
    135deg,
    rgba(220, 38, 38, 0.92),
    rgba(234, 88, 12, 0.88)
  );
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  letter-spacing: 0.03em;
  z-index: 3;
  line-height: 1.4;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.4);
}

/* 卡片信息区 */
.card-info {
  padding: 8px 10px 6px;
  flex-shrink: 0;
}

.card-title-main {
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.95);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-title-sub {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.65);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 价格栏 */
.card-price-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 12px;
  background: linear-gradient(
    135deg,
    rgba(234, 179, 8, 0.95),
    rgba(217, 119, 6, 0.9)
  );
  flex-shrink: 0;
}

.price-icon {
  font-size: 11px;
  color: rgba(30, 41, 59, 0.85);
}

.price-num {
  font-size: 15px;
  font-weight: 800;
  color: #1e293b;
  letter-spacing: 0.02em;
}

/* ── 占位区 ── */
.placeholder-section {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.placeholder-text {
  font-size: 14px;
  color: rgba(148, 163, 184, 0.5);
}
</style>
