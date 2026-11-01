<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import { computed, h, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getCredits, getPurchaseLink, redeemCode } from '@/api/business'
import API from '@/api/core'
import { isNagaLoggedIn, nagaUser, refreshUserStats, sessionRestored } from '@/composables/useAuth'
import { useBackground } from '@/composables/useBackground'
import { CONFIG, SYSTEM_PROMPT } from '@/utils/config'
import { applyCustomLive2DModel, upsertCustomLive2DModel } from '@/utils/live2dModels'

const router = useRouter()
const route = useRoute()

const tabs = [
  { id: 'album', label: '音之巷' },
  { id: 'memory-skin', label: '角色注册' },
  { id: 'skin', label: '界面背景' },
  { id: 'recharge', label: '模型充值' },
] as const

const svgIcon = (...paths: string[]) => h('svg', { 'viewBox': '0 0 24 24', 'fill': 'none', 'stroke': 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'class': 'tab-icon-svg' }, paths.map(d => h('path', { d })))

const tabIcons: Record<string, { render: () => ReturnType<typeof h> }> = {
  'album': { render: () => svgIcon('M9 18V5l12-2v13', 'M9 18a3 3 0 1 0 6 0 9 9 0 0 0 6 0') },
  'skin': { render: () => svgIcon('M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z', 'M21 15l-5-5L5 21') },
  'memory-skin': { render: () => svgIcon('M2 10c3 0 5 2 8 0s5-2 8 0', 'M2 14c3 0 5 2 8 0s5-2 8 0') },
  'recharge': { render: () => svgIcon('M12 2L3 9l4 12h10l4-12-9-7z') },
}

type TabId = typeof tabs[number]['id']
const initTab = route.query.tab as string | undefined
const activeTab = ref<TabId>(
  tabs.some(t => t.id === initTab) ? initTab as TabId : 'skin',
)

// 专辑数据：仅保留沙之书，左上角角标为 NEW
const albumItems = [
  { id: 1, title: '沙之书', subtitle: '', daysLeft: 0, price: 0, image: '/assets/just.png', bannerLabel: 'NEW' as const },
]

// ── 拖动横向滚动（通用） ──
const albumSection = ref<HTMLElement | null>(null)
const characterSectionRef = ref<HTMLElement | null>(null)

let wasDragging = false
const DRAG_THRESHOLD = 4

function initDragScroll(container: HTMLElement) {
  container.addEventListener('mousedown', (e: MouseEvent) => {
    const startX = e.clientX
    const startScrollLeft = container.scrollLeft
    let moved = false

    container.style.cursor = 'grabbing'
    document.body.style.cursor = 'grabbing'

    function onMove(ev: MouseEvent) {
      const dx = ev.clientX - startX
      if (Math.abs(dx) > DRAG_THRESHOLD)
        moved = true
      container.scrollLeft = startScrollLeft - dx
    }

    function onUp() {
      wasDragging = moved
      container.style.cursor = 'grab'
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      // 在 click 事件触发后再重置标记
      setTimeout(() => {
        wasDragging = false
      }, 0)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  })

  container.addEventListener('wheel', (e: WheelEvent) => {
    e.preventDefault()
    container.scrollLeft += e.deltaY
  }, { passive: false })
}

// ── 界面背景（声明提前，供 onMounted 使用） ──
const toast = useToast()
const { backgroundList, activeBackground, isOwned, isActive, purchase, apply, resetToDefault, getBackgroundUrl, loadBackgrounds } = useBackground()

const skinGridRef = ref<HTMLElement | null>(null)
const bgConfirmTarget = ref<string | null>(null)
const bgPurchasing = ref(false)

onMounted(() => {
  if (albumSection.value)
    initDragScroll(albumSection.value)
  if (characterSectionRef.value)
    initDragScroll(characterSectionRef.value)
  loadBackgrounds()
  nextTick(() => {
    if (skinGridRef.value)
      initVerticalDragScroll(skinGridRef.value)
  })
  if (activeTab.value === 'recharge')
    loadRechargeData()
})

// ── 角色注册 ──
interface CharacterCard {
  id: string
  name: string
  bio: string
  portraitUrl: string
}

const expandedCard = ref<string | null>(null)
const charCardRefs: Record<string, HTMLElement> = {}

const characters: CharacterCard[] = [
  {
    id: 'nadezhda',
    name: '娜杰日达',
    bio: '由创造者柏斯阔落亲手创造的AI智能体，亦称娜迦。',
    portraitUrl: 'naga-char://娜杰日达/Naga.png',
  },
]

// 立绘统一比例 3:4（宽:高），直接显示完整画布
// 展开 = cardH × 3/4（原图宽高比）
// 收缩 = cardH × 2/5
function computeAllCardWidths() {
  for (const char of characters) {
    const el = charCardRefs[char.id]
    if (!el)
      continue
    const h = el.offsetHeight
    if (h <= 0)
      continue
    el.style.setProperty('--collapsed-w', `${Math.round(h * 2 / 5)}px`)
    el.style.setProperty('--expanded-w', `${Math.round(h * 3 / 4)}px`)
  }
  // custom card
  const customEl = charCardRefs.custom
  if (customEl) {
    const ch = customEl.offsetHeight
    if (ch > 0) {
      customEl.style.setProperty('--collapsed-w', `${Math.round(ch * 2 / 5)}px`)
      customEl.style.setProperty('--expanded-w', `${Math.round(ch * 3 / 4)}px`)
    }
  }
}

function setCardRef(charId: string, el: any) {
  if (el)
    charCardRefs[charId] = el as HTMLElement
}

function toggleCard(id: string) {
  if (wasDragging)
    return
  expandedCard.value = expandedCard.value === id ? null : id
}

function onSectionClick() {
  if (!wasDragging)
    expandedCard.value = null
}

function applyCharacter(name: string) {
  CONFIG.value.system.active_character = name
}

// ── 自定义角色 ──
const customChar = reactive({
  name: '',
  modelFiles: [] as File[],
  modelPath: '',
  prompt: '',
  uploading: false,
})
const customReady = computed(() =>
  customChar.name.trim() !== '' && customChar.modelFiles.length > 0 && customChar.prompt.trim() !== '',
)
const fileInputRef = ref<HTMLInputElement | null>(null)

function triggerFileInput() {
  fileInputRef.value?.click()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  customChar.modelFiles = files
  const modelFiles = files
    .map(file => file.webkitRelativePath || file.name)
    .filter(path => path.toLowerCase().endsWith('.model3.json'))
  customChar.modelPath = modelFiles.length === 1 ? modelFiles[0] ?? '' : ''
}

async function applyCustomCharacter() {
  if (!customReady.value || customChar.uploading)
    return
  customChar.uploading = true
  try {
    const res = await API.uploadCustomLive2DModel({
      name: customChar.name.trim(),
      files: customChar.modelFiles,
      modelPath: customChar.modelPath || undefined,
    })
    const savedModel = upsertCustomLive2DModel(res.model)
    applyCustomLive2DModel(savedModel)
    toast.add({ severity: 'success', summary: '角色已录入', detail: customChar.name.trim(), life: 2500 })
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: '录入失败', detail: e?.response?.data?.detail || e.message, life: 4000 })
    return
  }
  finally {
    customChar.uploading = false
  }
  CONFIG.value.system.ai_name = customChar.name
  CONFIG.value.system.active_character = ''
  SYSTEM_PROMPT.value = customChar.prompt
}

// 标签可见时执行初始化
watch(activeTab, (tab) => {
  if (tab === 'memory-skin') {
    nextTick(computeAllCardWidths)
  }
  if (tab === 'skin') {
    nextTick(() => {
      if (skinGridRef.value)
        initVerticalDragScroll(skinGridRef.value)
    })
  }
  if (tab === 'recharge')
    loadRechargeData()
})

function handleBgAction(bgId: string) {
  if (isActive(bgId))
    return
  if (isOwned(bgId)) {
    apply(bgId)
    toast.add({ severity: 'success', summary: '已应用', detail: '背景已切换', life: 2000 })
    return
  }
  bgConfirmTarget.value = bgId
}

async function confirmPurchase() {
  const bgId = bgConfirmTarget.value
  if (!bgId || bgPurchasing.value)
    return
  const bg = backgroundList.value.find(b => b.id === bgId)
  if (!bg)
    return

  if (!isNagaLoggedIn.value) {
    toast.add({ severity: 'warn', summary: '请先登录', detail: '登录后才能兑换背景', life: 3000 })
    bgConfirmTarget.value = null
    return
  }

  const userPoints = nagaUser.value?.points ?? 0
  if (userPoints < bg.price) {
    toast.add({ severity: 'error', summary: '积分不足', detail: `需要 ${bg.price} 积分，当前余额 ${userPoints}`, life: 3000 })
    bgConfirmTarget.value = null
    return
  }

  bgPurchasing.value = true
  try {
    purchase(bgId)
    if (nagaUser.value) {
      nagaUser.value.points = userPoints - bg.price
    }
    apply(bgId)
    toast.add({ severity: 'success', summary: '兑换成功', detail: `${bg.name} 已解锁并应用`, life: 3000 })
    refreshUserStats()
  }
  finally {
    bgPurchasing.value = false
    bgConfirmTarget.value = null
  }
}

function cancelPurchase() {
  bgConfirmTarget.value = null
}

function handleResetBg() {
  resetToDefault()
  toast.add({ severity: 'info', summary: '已重置', detail: '已恢复默认向日葵边框', life: 2000 })
}

const confirmBgItem = computed(() => {
  if (!bgConfirmTarget.value)
    return null
  return backgroundList.value.find(b => b.id === bgConfirmTarget.value) ?? null
})

// 背景网格垂直拖动滚动
function initVerticalDragScroll(container: HTMLElement) {
  let wasSkinDragging = false

  container.addEventListener('mousedown', (e: MouseEvent) => {
    const startY = e.clientY
    const startScrollTop = container.scrollTop
    let moved = false

    container.style.cursor = 'grabbing'
    document.body.style.cursor = 'grabbing'

    function onMove(ev: MouseEvent) {
      const dy = ev.clientY - startY
      if (Math.abs(dy) > DRAG_THRESHOLD)
        moved = true
      container.scrollTop = startScrollTop - dy
    }

    function onUp() {
      wasSkinDragging = moved
      container.style.cursor = ''
      document.body.style.cursor = ''
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      setTimeout(() => {
        wasSkinDragging = false
      }, 0)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  })

  // 拦截点击，拖动中不触发 handleBgAction
  container.addEventListener('click', (e: MouseEvent) => {
    if (wasSkinDragging) {
      e.stopPropagation()
      e.preventDefault()
    }
  }, true)
}

// ── 模型充值 ──
interface Product { name: string, price: number, credits: number, url: string }
const rechargeProducts = ref<Product[]>([])
const rechargeLoading = ref(false)
const rechargeError = ref('')
const rechargeLoaded = ref(false)
const currentCredits = ref<string | null>(null)
const redeemInput = ref('')
const redeemLoading = ref(false)

async function loadRechargeData() {
  if (rechargeLoaded.value)
    return

  // 等待会话恢复完成，避免 token 未同步时 businessClient 401
  if (!sessionRestored.value) {
    rechargeLoading.value = true
    rechargeError.value = ''
    const stop = watch(sessionRestored, (ready) => {
      if (ready) {
        stop()
        _doLoadRecharge()
      }
    })
    // 5秒超时兜底（未登录用户不会触发 sessionRestored）
    setTimeout(() => {
      stop()
      if (!rechargeLoaded.value)
        _doLoadRecharge()
    }, 5000)
    return
  }
  _doLoadRecharge()
}

async function _doLoadRecharge() {
  if (rechargeLoaded.value)
    return
  rechargeLoading.value = true
  rechargeError.value = ''
  try {
    const [purchaseData, creditsData] = await Promise.all([
      getPurchaseLink(),
      getCredits().catch(() => null),
    ])
    rechargeProducts.value = purchaseData.products || []
    if (creditsData)
      currentCredits.value = creditsData.creditsAvailable
    rechargeLoaded.value = true
  }
  catch (e: any) {
    rechargeError.value = e?.response?.status === 401
      ? '请先登录后使用充值功能'
      : `加载失败: ${e?.response?.data?.detail || e.message}`
  }
  rechargeLoading.value = false
}

function openPurchaseUrl(url: string) {
  window.open(url, '_blank')
}

async function handleRedeem() {
  const code = redeemInput.value.trim()
  if (!code)
    return
  redeemLoading.value = true
  try {
    const result = await redeemCode(code)
    toast.add({ severity: 'success', summary: '兑换成功', detail: `+${result.creditsAdded} 积分`, life: 3000 })
    currentCredits.value = result.creditsAvailable
    redeemInput.value = ''
    refreshUserStats()
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: '兑换失败', detail: e?.response?.data?.detail || e.message, life: 4000 })
  }
  redeemLoading.value = false
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
                {{ item.bannerLabel ?? `剩余${item.daysLeft}天` }}
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

      <!-- 角色注册 -->
      <section v-show="activeTab === 'memory-skin'" ref="characterSectionRef" class="character-section" @click="onSectionClick">
        <div class="character-grid">
          <div
            v-for="char in characters"
            :key="char.id"
            :ref="(el: any) => setCardRef(char.id, el)"
            class="char-card"
            :class="{ expanded: expandedCard === char.id }"
            @click.stop="toggleCard(char.id)"
          >
            <img
              :src="char.portraitUrl"
              :alt="char.name"
              class="char-portrait-img"
            >
            <!-- 底部渐变遮罩 -->
            <div class="char-portrait-gradient" />
            <!-- 收缩态角色名 -->
            <div class="char-name-tag">
              {{ char.name }}
            </div>
            <!-- 展开态简介面板：绝对定位覆盖在卡片底部 -->
            <div class="char-desc-panel">
              <h3 class="char-desc-title">
                {{ char.name }}
              </h3>
              <p class="char-desc-text">
                {{ char.bio }}
              </p>
              <button
                type="button"
                class="char-apply-btn"
                @click.stop="applyCharacter(char.name)"
              >
                录入角色
              </button>
            </div>
          </div>

          <!-- 自定义角色卡 -->
          <div
            :ref="(el: any) => setCardRef('custom', el)"
            class="char-card custom-card"
            :class="{ expanded: expandedCard === 'custom' }"
            @click.stop="toggleCard('custom')"
          >
            <!-- 收缩态：+ 图标 + 文字 -->
            <div v-if="expandedCard !== 'custom'" class="custom-collapsed">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span class="custom-label">自定义角色</span>
            </div>
            <!-- 展开态：表单 -->
            <div v-else class="custom-form" @click.stop>
              <label class="custom-field">
                <span class="custom-field-label">角色名称</span>
                <input
                  v-model="customChar.name"
                  type="text"
                  class="custom-input"
                  placeholder="输入角色名称"
                >
              </label>
              <div class="custom-field">
                <span class="custom-field-label">L2D 模型</span>
                <input
                  ref="fileInputRef"
                  type="file"
                  webkitdirectory
                  directory
                  multiple
                  style="display:none"
                  @change="onFileChange"
                >
                <button type="button" class="custom-file-btn" @click="triggerFileInput">
                  {{ customChar.modelFiles.length ? `${customChar.modelFiles.length} 个模型资源文件` : '选择 Live2D 模型目录' }}
                </button>
                <span v-if="customChar.modelPath" class="custom-file-hint">
                  {{ customChar.modelPath }}
                </span>
              </div>
              <label class="custom-field custom-field-grow">
                <span class="custom-field-label">系统提示词</span>
                <textarea
                  v-model="customChar.prompt"
                  class="custom-textarea"
                  placeholder="输入系统提示词"
                />
              </label>
              <button
                type="button"
                class="char-apply-btn"
                :class="{ disabled: !customReady }"
                :disabled="!customReady || customChar.uploading"
                @click.stop="customReady && applyCustomCharacter()"
              >
                {{ customChar.uploading ? '录入中...' : '录入角色' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 界面背景 -->
      <section v-show="activeTab === 'skin'" class="skin-section">
        <!-- 顶部信息栏：积分余额 + 重置按钮 -->
        <div class="skin-toolbar">
          <div class="skin-balance">
            <span class="balance-icon">◆</span>
            <span class="balance-num">{{ nagaUser?.points ?? '--' }}</span>
            <span class="balance-label">积分</span>
          </div>
          <button
            type="button"
            class="skin-reset-btn"
            :class="{ disabled: !activeBackground }"
            :disabled="!activeBackground"
            @click="handleResetBg"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            恢复默认
          </button>
        </div>

        <!-- 背景卡片网格（3列，垂直滚动 + 拖动） -->
        <div ref="skinGridRef" class="skin-grid">
          <div
            v-for="bg in backgroundList"
            :key="bg.id"
            class="skin-card"
            :class="{ active: isActive(bg.id), owned: isOwned(bg.id) }"
            @click="handleBgAction(bg.id)"
          >
            <div class="skin-thumb">
              <img :src="getBackgroundUrl(bg.id)" :alt="bg.name" class="skin-thumb-img" @error="($event.target as HTMLImageElement).style.display = 'none'">
              <div class="skin-thumb-placeholder">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <path d="M21 15l-5-5L5 21" />
                </svg>
              </div>
              <!-- 状态角标 -->
              <div v-if="isActive(bg.id)" class="skin-badge active-badge">使用中</div>
              <div v-else-if="isOwned(bg.id)" class="skin-badge owned-badge">已拥有</div>
            </div>
            <div class="skin-info">
              <div class="skin-name">{{ bg.name }}</div>
              <div class="skin-price-row">
                <template v-if="isActive(bg.id)">
                  <span class="skin-status-text active-text">当前背景</span>
                </template>
                <template v-else-if="isOwned(bg.id)">
                  <span class="skin-status-text owned-text">已拥有</span>
                </template>
                <template v-else>
                  <span class="skin-price">
                    <span class="price-icon">◆</span>
                    {{ bg.price }}
                  </span>
                </template>
              </div>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="backgroundList.length === 0" class="skin-empty">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
            <span>将图片放入 premium-assets/backgrounds 文件夹</span>
          </div>
        </div>

        <!-- 兑换确认弹窗 -->
        <Teleport to="body">
          <Transition name="popup-fade">
            <div v-if="bgConfirmTarget" class="bg-confirm-overlay" @click.self="cancelPurchase">
              <div class="bg-confirm-card">
                <h3 class="bg-confirm-title">确认兑换</h3>
                <div v-if="confirmBgItem" class="bg-confirm-body">
                  <div class="bg-confirm-name">{{ confirmBgItem.name }}</div>
                  <div class="bg-confirm-price">
                    <span class="price-icon">◆</span>
                    <span class="bg-confirm-price-num">{{ confirmBgItem.price }}</span>
                    <span class="bg-confirm-price-label">积分</span>
                  </div>
                  <div class="bg-confirm-balance">
                    当前余额：{{ nagaUser?.points ?? 0 }} 积分
                  </div>
                </div>
                <div class="bg-confirm-actions">
                  <button
                    type="button"
                    class="bg-confirm-btn primary"
                    :disabled="bgPurchasing"
                    @click="confirmPurchase"
                  >
                    {{ bgPurchasing ? '兑换中...' : '确认兑换' }}
                  </button>
                  <button type="button" class="bg-confirm-btn secondary" @click="cancelPurchase">
                    取消
                  </button>
                </div>
              </div>
            </div>
          </Transition>
        </Teleport>
      </section>

      <!-- 模型充值 -->
      <section v-show="activeTab === 'recharge'" class="recharge-section">
        <div v-if="currentCredits !== null" class="recharge-balance">
          当前余额: <span class="balance-value">{{ currentCredits }}</span> 积分
        </div>

        <div v-if="rechargeLoading" class="recharge-placeholder">加载中...</div>
        <div v-else-if="rechargeError" class="recharge-placeholder recharge-error">{{ rechargeError }}</div>

        <div v-else class="recharge-grid">
          <div
            v-for="product in rechargeProducts" :key="product.name"
            class="recharge-card"
            @click="openPurchaseUrl(product.url)"
          >
            <div class="card-credits">{{ product.credits }}</div>
            <div class="card-unit">积分</div>
            <div class="card-price">{{ product.price }}</div>
          </div>
        </div>

        <div class="recharge-redeem">
          <input
            v-model="redeemInput" class="redeem-input" type="text"
            placeholder="输入兑换码" @keyup.enter="handleRedeem"
          >
          <button class="redeem-btn" :disabled="redeemLoading || !redeemInput.trim()" @click="handleRedeem">
            {{ redeemLoading ? '兑换中...' : '兑换' }}
          </button>
        </div>

        <div class="recharge-tip">点击商品卡片跳转爱发电支付，支付完成后积分自动到账</div>
        <div class="recharge-notice">充值会在一个工作日内到账</div>
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

/* ── 角色注册 ── */
.character-section {
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 16px 24px;
  display: flex;
  align-items: stretch;
  min-height: 0;
  cursor: grab;
  user-select: none;
}

.character-section::-webkit-scrollbar {
  height: 4px;
}

.character-section::-webkit-scrollbar-track {
  background: transparent;
}

.character-section::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.25);
  border-radius: 2px;
}

.character-grid {
  display: flex;
  gap: 16px;
  height: 100%;
  align-items: stretch;
}

/* ── 角色卡：高度恒定，只变宽度，内部全部绝对定位 ── */
.char-card {
  position: relative;
  height: 100%;
  width: var(--collapsed-w, 130px);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.15);
  cursor: pointer;
  transition:
    width 0.5s cubic-bezier(0.33, 1, 0.68, 1),
    background 0.3s,
    border-color 0.3s,
    box-shadow 0.3s;
  flex-shrink: 0;
}

.char-card:hover {
  border-color: rgba(212, 175, 55, 0.4);
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.4),
    0 0 12px rgba(212, 175, 55, 0.1);
}

.char-card.expanded {
  width: var(--expanded-w, 300px);
  background: transparent;
  border-color: transparent;
  box-shadow: none;
}

.char-portrait-img {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  height: 100%;
  width: auto;
  z-index: 0;
}

/* 立绘底部渐变遮罩 */
.char-portrait-gradient {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 80px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.75));
  pointer-events: none;
  z-index: 1;
}

/* 收缩态角色名：绝对定位在底部 */
.char-name-tag {
  position: absolute;
  bottom: 10px;
  left: 10px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.8);
  z-index: 2;
  transition: opacity 0.3s;
}

.char-card.expanded .char-name-tag {
  opacity: 0;
}

/*
 * 展开态简介面板：绝对定位覆盖在卡片底部
 * 不占据任何布局空间，立绘区域高度始终不变
 */
.char-desc-panel {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 3;
  padding: 10px 12px 12px;
  background: linear-gradient(transparent, rgba(10, 12, 16, 0.92) 25%);
  display: flex;
  flex-direction: column;
  opacity: 0;
  transform: translateY(100%);
  transition:
    opacity 0.4s ease,
    transform 0.5s cubic-bezier(0.33, 1, 0.68, 1);
  pointer-events: none;
}

.char-card.expanded .char-desc-panel {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

.char-desc-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 700;
  color: rgba(251, 191, 36, 0.95);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.05em;
}

.char-desc-text {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(203, 213, 225, 0.85);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── "录入角色"按钮 ── */
.char-apply-btn {
  margin-top: 8px;
  padding: 4px 14px;
  font-size: 11px;
  font-weight: 600;
  color: rgba(251, 191, 36, 0.95);
  background: transparent;
  border: 1px solid rgba(251, 191, 36, 0.5);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  letter-spacing: 0.04em;
  align-self: center;
  flex-shrink: 0;
}

.char-apply-btn:hover {
  background: rgba(251, 191, 36, 0.12);
  border-color: rgba(251, 191, 36, 0.8);
}

.char-apply-btn.disabled {
  color: rgba(148, 163, 184, 0.45);
  border-color: rgba(148, 163, 184, 0.2);
  cursor: not-allowed;
}

.char-apply-btn.disabled:hover {
  background: transparent;
  border-color: rgba(148, 163, 184, 0.2);
}

/* ── 自定义角色卡 ── */
.custom-card {
  background: rgba(22, 26, 35, 0.95);
}

.custom-card.expanded {
  background: rgba(22, 26, 35, 0.95) !important;
  border-color: rgba(148, 163, 184, 0.15) !important;
  box-shadow: none !important;
}

.custom-collapsed {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: rgba(248, 250, 252, 0.45);
  transition: color 0.2s;
}

.custom-card:hover .custom-collapsed {
  color: rgba(251, 191, 36, 0.8);
}

.custom-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  writing-mode: vertical-rl;
  text-orientation: mixed;
}

.custom-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 12px;
  height: 100%;
  overflow-y: auto;
}

.custom-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.custom-field-grow {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.custom-field-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(251, 191, 36, 0.85);
  letter-spacing: 0.03em;
}

.custom-input {
  padding: 6px 8px;
  font-size: 12px;
  color: rgba(248, 250, 252, 0.9);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  outline: none;
  transition: border-color 0.2s;
}

.custom-input:focus {
  border-color: rgba(251, 191, 36, 0.5);
}

.custom-file-btn {
  padding: 6px 8px;
  font-size: 11px;
  color: rgba(248, 250, 252, 0.7);
  background: rgba(255, 255, 255, 0.06);
  border: 1px dashed rgba(148, 163, 184, 0.25);
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-file-btn:hover {
  border-color: rgba(251, 191, 36, 0.45);
  background: rgba(255, 255, 255, 0.08);
}

.custom-file-hint {
  color: rgba(248, 250, 252, 0.44);
  font-size: 10px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.custom-textarea {
  flex: 1;
  min-height: 60px;
  padding: 6px 8px;
  font-size: 12px;
  color: rgba(248, 250, 252, 0.9);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  outline: none;
  resize: none;
  font-family: inherit;
  transition: border-color 0.2s;
}

.custom-textarea:focus {
  border-color: rgba(251, 191, 36, 0.5);
}

/* ── 界面背景 ── */
.skin-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.skin-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.skin-toolbar-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.7);
  letter-spacing: 0.04em;
}

.skin-reset-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(248, 250, 252, 0.6);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.skin-reset-btn:hover:not(.disabled) {
  border-color: rgba(212, 175, 55, 0.4);
  color: rgba(212, 175, 55, 0.9);
  background: rgba(212, 175, 55, 0.08);
}

.skin-reset-btn.disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.skin-grid {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 20px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  align-content: start;
  cursor: grab;
  user-select: none;
}

.skin-grid::-webkit-scrollbar {
  width: 5px;
}

.skin-grid::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.03);
  border-radius: 3px;
}

.skin-grid::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.3);
  border-radius: 3px;
}

.skin-grid::-webkit-scrollbar-thumb:hover {
  background: rgba(212, 175, 55, 0.5);
}

.skin-card {
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(22, 26, 35, 0.9);
  border: 1px solid rgba(148, 163, 184, 0.1);
  cursor: pointer;
  transition: all 0.25s ease;
}

.skin-card:hover {
  border-color: rgba(212, 175, 55, 0.4);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3), 0 0 12px rgba(212, 175, 55, 0.08);
  transform: translateY(-2px);
}

.skin-card.active {
  border-color: rgba(212, 175, 55, 0.6);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.15);
}

.skin-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: rgba(15, 17, 21, 0.8);
}

.skin-thumb-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.skin-thumb-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(148, 163, 184, 0.2);
}

.skin-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  z-index: 2;
}

.active-badge {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.95), rgba(180, 140, 30, 0.9));
  color: #1a1206;
}

.skin-info {
  padding: 8px 10px;
}

.skin-name {
  font-size: 12px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.9);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.03em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skin-price-row {
  margin-top: 2px;
  display: flex;
  align-items: center;
}

.skin-status-text {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.active-text {
  color: rgba(212, 175, 55, 0.85);
}

.owned-text {
  color: rgba(148, 163, 184, 0.5);
}

.skin-price {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(234, 179, 8, 0.9);
}

.skin-price .price-icon {
  font-size: 9px;
}

.skin-empty {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  color: rgba(148, 163, 184, 0.35);
  font-size: 12px;
  text-align: center;
}

.skin-balance {
  display: flex;
  align-items: center;
  gap: 5px;
}

.balance-icon {
  font-size: 12px;
  color: rgba(212, 175, 55, 0.9);
}

.balance-num {
  font-size: 16px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.9);
  font-variant-numeric: tabular-nums;
}

.balance-label {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.5);
}

.skin-card.owned {
  border-color: rgba(148, 163, 184, 0.2);
}

.owned-badge {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(248, 250, 252, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

/* ── 兑换确认弹窗 ── */
.bg-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.bg-confirm-card {
  width: 320px;
  padding: 24px;
  border: 1px solid rgba(212, 175, 55, 0.35);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.4), 0 0 20px rgba(212, 175, 55, 0.08);
}

.bg-confirm-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.95);
  text-align: center;
  font-family: 'Noto Serif SC', serif;
}

.bg-confirm-body {
  text-align: center;
}

.bg-confirm-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.95);
  font-family: 'Noto Serif SC', serif;
}

.bg-confirm-price {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-top: 14px;
}

.bg-confirm-price .price-icon {
  font-size: 12px;
  color: rgba(234, 179, 8, 0.85);
}

.bg-confirm-price-num {
  font-size: 22px;
  font-weight: 800;
  color: rgba(234, 179, 8, 0.95);
  font-variant-numeric: tabular-nums;
}

.bg-confirm-price-label {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.5);
}

.bg-confirm-balance {
  font-size: 11px;
  color: rgba(148, 163, 184, 0.45);
  margin-top: 6px;
}

.bg-confirm-actions {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.bg-confirm-btn {
  flex: 1;
  padding: 8px 0;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.bg-confirm-btn.primary {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.9), rgba(180, 140, 30, 0.85));
  color: #1a1206;
}

.bg-confirm-btn.primary:hover {
  filter: brightness(1.1);
}

.bg-confirm-btn.primary:disabled {
  opacity: 0.5;
  cursor: wait;
}

.bg-confirm-btn.secondary {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.5);
}

.bg-confirm-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.1);
}

.popup-fade-enter-active,
.popup-fade-leave-active {
  transition: opacity 0.2s ease;
}

.popup-fade-enter-from,
.popup-fade-leave-to {
  opacity: 0;
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

/* ── 模型充值 ── */
.recharge-section {
  flex: 1; display: flex; flex-direction: column; gap: 1.2rem;
  padding: 1rem 0.5rem; overflow-y: auto;
}
.recharge-balance {
  text-align: center; color: rgba(255,255,255,0.6); font-size: 0.85rem;
}
.balance-value { color: #d4af37; font-weight: bold; font-size: 1.1rem; }

.recharge-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.8rem;
}
.recharge-card {
  display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
  padding: 1.2rem 0.8rem; border-radius: 12px;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  cursor: pointer; transition: all 0.2s;
}
.recharge-card:hover {
  background: rgba(212,175,55,0.08); border-color: rgba(212,175,55,0.3);
  transform: translateY(-2px);
}
.recharge-card .card-credits { font-size: 1.8rem; font-weight: bold; color: #d4af37; }
.recharge-card .card-unit { font-size: 0.7rem; color: rgba(255,255,255,0.4); margin-top: -0.2rem; }
.recharge-card .card-price { font-size: 1rem; font-weight: 600; color: rgba(255,255,255,0.9); margin-top: 0.2rem; }

.recharge-redeem { display: flex; gap: 0.5rem; max-width: 360px; margin: 0 auto; }
.redeem-input {
  flex: 1; padding: 0.5rem 0.8rem; border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04);
  color: white; font-size: 0.85rem; outline: none;
}
.redeem-input:focus { border-color: rgba(212,175,55,0.4); }
.redeem-btn {
  padding: 0.5rem 1rem; border-radius: 8px; border: none;
  background: rgba(212,175,55,0.2); color: #d4af37;
  font-size: 0.85rem; cursor: pointer; transition: background 0.2s; white-space: nowrap;
}
.redeem-btn:hover:not(:disabled) { background: rgba(212,175,55,0.35); }
.redeem-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.recharge-placeholder { text-align: center; color: rgba(255,255,255,0.4); padding: 2rem; }
.recharge-error { color: rgba(255,100,100,0.7); }
.recharge-tip { text-align: center; color: rgba(255,255,255,0.3); font-size: 0.75rem; }
.recharge-notice { text-align: center; color: rgba(255,255,255,0.2); font-size: 0.7rem; margin-top: 6px; }
</style>
