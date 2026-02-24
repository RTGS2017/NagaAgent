<script setup lang="ts">
import { useToast } from 'primevue/usetoast'
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { checkIn, getAffinity, getCheckInStatus, getCredits } from '@/api/business'
import affinityIcon from '@/assets/icons/affinity.svg'
import pointsIcon from '@/assets/icons/points.svg'
import { isNagaLoggedIn, nagaUser, useAuth } from '@/composables/useAuth'

const toast = useToast()
const router = useRouter()
const { logout, refreshUserStats } = useAuth()
const menuOpen = ref(false)
const openLoginDialog = inject<() => void>('openLoginDialog')

// ── 签到 ──
const checkedInToday = ref(false)
const checkingIn = ref(false)

watch(isNagaLoggedIn, async (loggedIn) => {
  if (loggedIn) {
    try {
      const status = await getCheckInStatus()
      checkedInToday.value = status.checkedInToday
    }
    catch { /* ignore */ }
  }
  else {
    checkedInToday.value = false
  }
}, { immediate: true })

async function handleCheckIn() {
  if (checkedInToday.value || checkingIn.value)
    return
  checkingIn.value = true
  try {
    const res = await checkIn()
    if (res.alreadyCheckedIn) {
      checkedInToday.value = true
      toast.add({ severity: 'info', summary: '今日已签到', detail: '明天再来吧', life: 3000 })
      return
    }
    checkedInToday.value = true
    const earned = Number.parseFloat(res.affinityEarned) || 0
    const credits = res.creditsEarned ?? 0
    let detail = `熟悉度 +${earned}，积分 +${credits}`
    if (res.bonusCredits > 0) {
      detail += `（含连签奖励 +${res.bonusCredits}）`
    }
    toast.add({ severity: 'success', summary: '签到成功', detail, life: 3000 })
    refreshUserStats()
  }
  catch (e: any) {
    const msg = e?.response?.data?.message || e?.response?.data?.detail || '签到失败，请稍后再试'
    toast.add({ severity: 'error', summary: '签到失败', detail: msg, life: 3000 })
  }
  finally {
    checkingIn.value = false
  }
}

// ── 弹窗 ──
const statPopup = ref<'points' | 'affinity' | null>(null)
const popupLoading = ref(false)

// 积分详情
const creditsDetail = ref<{ available: number, total: number, used: number } | null>(null)

// 熟悉度详情
const affinityDetail = ref<{
  level: number
  affinityPoints: number
  pointsNeeded: number
  progressPct: number
  streakDays: number
  recoveryMode: boolean
  nextLevel: number
} | null>(null)

async function openStatPopup(type: 'points' | 'affinity') {
  statPopup.value = type
  popupLoading.value = true
  if (type === 'points')
    creditsDetail.value = null
  else affinityDetail.value = null
  try {
    if (type === 'points') {
      const data = await getCredits()
      creditsDetail.value = {
        available: Number.parseFloat(data.creditsAvailable) || 0,
        total: Number.parseFloat(data.creditsTotal) || 0,
        used: Number.parseFloat(data.creditsUsed) || 0,
      }
    }
    else {
      const data = await getAffinity()
      affinityDetail.value = {
        level: data.level ?? 0,
        affinityPoints: Number.parseFloat(data.affinityPoints) || 0,
        pointsNeeded: Number.parseFloat(data.pointsNeeded ?? '0') || 0,
        progressPct: data.progressPct ?? 0,
        streakDays: data.streakDays ?? 0,
        recoveryMode: data.recoveryMode ?? false,
        nextLevel: data.nextLevel ?? 0,
      }
    }
  }
  catch { /* 静默，显示已有数据 */ }
  finally {
    popupLoading.value = false
  }
}

function closeStatPopup() {
  statPopup.value = null
}

const affinityProgress = computed(() => {
  if (!affinityDetail.value)
    return 0
  return Math.min(100, Math.round(affinityDetail.value.progressPct))
})

function toggleMenu() {
  if (!isNagaLoggedIn.value) {
    openLoginDialog?.()
  }
  else {
    menuOpen.value = !menuOpen.value
  }
}

function closeMenu() {
  menuOpen.value = false
}

function goConfig() {
  closeMenu()
  router.push('/config')
}

function openModelPlaza() {
  closeMenu()
  toast.add({ severity: 'info', summary: '功能开发中', detail: '模型广场功能即将上线', life: 3000 })
}

async function handleLogout() {
  closeMenu()
  await logout()
}

const initial = computed(() => {
  if (!isNagaLoggedIn.value) {
    return '?'
  }
  const name = nagaUser.value?.username ?? ''
  return name.charAt(0).toUpperCase()
})

const displayName = computed(() => {
  return isNagaLoggedIn.value ? nagaUser.value?.username : '未登录'
})
</script>

<template>
  <div class="user-menu" @mouseleave="closeMenu">
    <template v-if="isNagaLoggedIn">
      <!-- 签到按钮 -->
      <button
        class="checkin-btn"
        :class="{ 'checked-in': checkedInToday }"
        :disabled="checkedInToday || checkingIn"
        @click="handleCheckIn"
      >
        {{ checkedInToday ? '已签到' : '签到' }}
      </button>

      <!-- 积分 -->
      <button class="stat-item" @click="openStatPopup('points')">
        <img :src="pointsIcon" class="stat-icon" alt="积分">
        <span class="stat-value">{{ nagaUser?.points != null && !isNaN(nagaUser.points) ? nagaUser.points : '--' }}</span>
        <span class="stat-tooltip">积分</span>
      </button>

      <!-- 熟悉度 -->
      <button class="stat-item" @click="openStatPopup('affinity')">
        <img :src="affinityIcon" class="stat-icon" alt="熟悉度">
        <span class="stat-value">{{ nagaUser?.affinityLevel != null ? `Lv.${nagaUser.affinityLevel}` : '--' }}</span>
        <span class="stat-tooltip">熟悉度</span>
      </button>
    </template>

    <button class="avatar-btn" @click="toggleMenu">
      <span class="avatar" :class="{ 'not-logged-in': !isNagaLoggedIn }">{{ initial }}</span>
      <span class="username">{{ displayName }}</span>
    </button>

    <Transition name="dropdown-fade">
      <div v-if="menuOpen && isNagaLoggedIn" class="dropdown">
        <div class="user-header">
          <div class="user-header-name">{{ nagaUser?.username }}</div>
          <div v-if="nagaUser?.sub" class="user-header-id">ID: {{ nagaUser.sub }}</div>
        </div>
        <div class="dropdown-divider gold" />
        <button class="dropdown-item" @click="goConfig">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3" /><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" /></svg>
          用户设置
        </button>
        <button class="dropdown-item" @click="openModelPlaza">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /></svg>
          模型广场
        </button>
        <div class="dropdown-divider" />
        <button class="dropdown-item logout" @click="handleLogout">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></svg>
          登出
        </button>
      </div>
    </Transition>
  </div>

  <!-- 积分/熟悉度 弹窗 -->
  <Teleport to="body">
    <Transition name="popup-fade">
      <div v-if="statPopup" class="stat-popup-overlay" @click.self="closeStatPopup">
        <div class="stat-popup-card">
          <button class="stat-popup-close" @click="closeStatPopup">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
          <div class="stat-popup-header">
            <img v-if="statPopup === 'points'" :src="pointsIcon" class="stat-popup-icon">
            <img v-else :src="affinityIcon" class="stat-popup-icon">
            <h3 class="stat-popup-title">{{ statPopup === 'points' ? '积分' : '熟悉度' }}</h3>
          </div>

          <!-- 积分详情 -->
          <template v-if="statPopup === 'points'">
            <div class="stat-popup-value">{{ creditsDetail?.available ?? nagaUser?.points ?? '--' }}</div>
            <div class="stat-popup-desc">
              <div v-if="creditsDetail" class="stat-detail-grid">
                <span class="stat-detail-label">可用积分</span>
                <span class="stat-detail-val">{{ creditsDetail.available }}</span>
                <span class="stat-detail-label">累计获得</span>
                <span class="stat-detail-val">{{ creditsDetail.total }}</span>
                <span class="stat-detail-label">已使用</span>
                <span class="stat-detail-val">{{ creditsDetail.used }}</span>
              </div>
              <p v-else-if="popupLoading" class="stat-loading">加载中...</p>
            </div>
          </template>

          <!-- 熟悉度详情 -->
          <template v-else>
            <div class="stat-popup-value">
              <span v-if="affinityDetail">Lv.{{ affinityDetail.level }}</span>
              <span v-else>{{ nagaUser?.affinityLevel != null ? `Lv.${nagaUser.affinityLevel}` : '--' }}</span>
            </div>
            <div class="stat-popup-desc">
              <template v-if="affinityDetail">
                <div class="affinity-progress-wrap">
                  <div class="affinity-progress-bar">
                    <div class="affinity-progress-fill" :style="{ width: `${affinityProgress}%` }" />
                  </div>
                  <span class="affinity-progress-text">{{ affinityDetail.affinityPoints }} / {{ affinityDetail.pointsNeeded }}</span>
                </div>
                <div class="stat-detail-grid" style="margin-top: 12px;">
                  <span class="stat-detail-label">下一等级</span>
                  <span class="stat-detail-val">Lv.{{ affinityDetail.nextLevel }}</span>
                  <span class="stat-detail-label">连续签到</span>
                  <span class="stat-detail-val">{{ affinityDetail.streakDays }} 天</span>
                  <template v-if="affinityDetail.recoveryMode">
                    <span class="stat-detail-label">状态</span>
                    <span class="stat-detail-val" style="color: #e8a33d;">恢复中</span>
                  </template>
                </div>
              </template>
              <p v-else-if="popupLoading" class="stat-loading">加载中...</p>
            </div>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.user-menu {
  position: relative;
  display: flex;
  align-items: center;
  height: 100%;
  gap: 2px;
  -webkit-app-region: no-drag;
}

/* ── 签到按钮 ── */
.checkin-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  padding: 0 10px;
  border: none;
  border-radius: 4px;
  background: linear-gradient(135deg, #f0d060, #d4af37);
  color: #1a1206;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: filter 0.15s;
  white-space: nowrap;
}

.checkin-btn:hover {
  filter: brightness(1.15);
}

.checkin-btn.checked-in {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.4);
  cursor: default;
  filter: none;
}

.checkin-btn:disabled:not(.checked-in) {
  opacity: 0.6;
  cursor: wait;
}

/* ── 积分 / 熟悉度 ── */
.stat-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 0 6px;
  height: 100%;
  border: none;
  background: transparent;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.stat-item:hover {
  color: rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.06);
}

.stat-icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
}

.stat-value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* 浮动标签 */
.stat-tooltip {
  position: absolute;
  bottom: -26px;
  left: 50%;
  transform: translateX(-50%);
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(30, 22, 10, 0.95);
  border: 1px solid rgba(212, 175, 55, 0.25);
  color: rgba(255, 255, 255, 0.8);
  font-size: 10px;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 200;
}

.stat-item:hover .stat-tooltip {
  opacity: 1;
}

/* ── 头像按钮 ── */
.avatar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  padding: 0 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.8);
  font-size: 12px;
  transition: background 0.15s;
}

.avatar-btn:hover {
  background: rgba(255, 255, 255, 0.08);
}

.avatar {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.9), rgba(180, 140, 30, 0.9));
  color: #1a1206;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar.not-logged-in {
  background: linear-gradient(135deg, rgba(150, 150, 150, 0.5), rgba(100, 100, 100, 0.5));
  color: rgba(255, 255, 255, 0.6);
}

.username {
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 下拉菜单 ── */
.dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  min-width: 180px;
  padding: 4px 0;
  background: rgba(30, 22, 10, 0.96);
  border: 1px solid rgba(212, 175, 55, 0.25);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  z-index: 100;
}

.user-header {
  padding: 10px 14px 8px;
}

.user-header-name {
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 600;
}

.user-header-id {
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
  margin-top: 2px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 14px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.dropdown-item:hover {
  background: rgba(212, 175, 55, 0.1);
  color: rgba(212, 175, 55, 0.9);
}

.dropdown-item.logout:hover {
  background: rgba(232, 93, 93, 0.1);
  color: #e85d5d;
}

.dropdown-divider {
  height: 1px;
  margin: 4px 10px;
  background: rgba(255, 255, 255, 0.08);
}

.dropdown-divider.gold {
  background: linear-gradient(90deg, transparent, rgba(212, 175, 55, 0.35), transparent);
}

.dropdown-fade-enter-active {
  transition: opacity 0.15s, transform 0.15s;
}

.dropdown-fade-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}

.dropdown-fade-leave-active {
  transition: opacity 0.1s;
}

.dropdown-fade-leave-to {
  opacity: 0;
}

/* ── 弹窗 ── */
.stat-popup-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.stat-popup-card {
  position: relative;
  width: 320px;
  padding: 2rem;
  border: 1px solid rgba(212, 175, 55, 0.4);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 40px rgba(0, 0, 0, 0.4), 0 0 20px rgba(212, 175, 55, 0.08);
}

.stat-popup-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.stat-popup-close:hover {
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.08);
}

.stat-popup-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stat-popup-icon {
  width: 24px;
  height: 24px;
}

.stat-popup-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.9);
}

.stat-popup-value {
  margin-top: 1rem;
  font-size: 2rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.stat-popup-desc {
  margin-top: 1rem;
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.45);
  line-height: 1.5;
  min-height: 40px;
}

.popup-fade-enter-active,
.popup-fade-leave-active {
  transition: opacity 0.2s ease;
}

.popup-fade-enter-from,
.popup-fade-leave-to {
  opacity: 0;
}

/* ── 弹窗详情 ── */
.stat-detail-grid {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px 12px;
}

.stat-detail-label {
  color: rgba(255, 255, 255, 0.45);
  font-size: 0.8rem;
}

.stat-detail-val {
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.8rem;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.stat-loading {
  text-align: center;
  color: rgba(255, 255, 255, 0.3);
  font-size: 0.8rem;
}

/* 熟悉度进度条 */
.affinity-progress-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.affinity-progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.affinity-progress-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #d4af37, #f0d060);
  transition: width 0.3s ease;
}

.affinity-progress-text {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.4);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
