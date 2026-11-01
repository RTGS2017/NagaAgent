<script setup lang="ts">
import { Button, Dialog, InputNumber, Select, Textarea, ToggleSwitch } from 'primevue'
import ScrollPanel from 'primevue/scrollpanel'
import { computed, onMounted, ref, watch } from 'vue'
import { ACCESS_TOKEN } from '@/api'
import API from '@/api/core'
import TravelDiscoveryItem from '@/travel/components/TravelDiscoveryItem.vue'
import TravelHistoryList from '@/travel/components/TravelHistoryList.vue'
import { useTravel } from '@/travel/composables/useTravel'
import { backendConnected } from '@/utils/config'
import { agentContacts, loadAgentContacts } from '@/utils/session'
import ForumSidebarLeft from './components/ForumSidebarLeft.vue'
import ForumSidebarRight from './components/ForumSidebarRight.vue'
import { useForumProfile } from './useAgentProfile'

const { profile, profileError, load, reload } = useForumProfile()
const {
  travelSession,
  activeSessions,
  activeSessionByAgentId,
  historyList,
  loading,
  timeProgress,
  creditProgress,
  lastUpdatedLabel,
  startTravel,
  stopTravel,
  updateTravelBrowserSettings,
  viewSession,
  refreshSessions,
} = useTravel()

const exploring = computed(() => activeSessions.value.length > 0)
const currentSession = computed(() => travelSession.value || activeSessions.value[0] || historyList.value[0] || null)
const createDialogVisible = ref(false)
const helpVisible = ref(false)
const rawHistoryVisible = ref(false)
const rawHistoryLoading = ref(false)
const rawHistoryMessages = ref<Array<Record<string, any>>>([])
const goalPrompt = ref('追踪 AI、技术与互联网的最新热点，优先关注仍在持续发酵的话题和一手来源')
const selectedAgentId = ref('')
const timeLimitMinutes = ref(120)
const creditLimit = ref(800)
const createBrowserVisible = ref(false)
const createBrowserKeepOpen = ref(false)

const realCredits = computed(() => profile.value?.creditsBalance ?? 0)
const effectiveDailyBudget = computed(() => profile.value?.quota?.dailyBudget ?? 1000)
const effectiveUsedToday = computed(() => profile.value?.quota?.usedToday ?? 0)
const currentFindings = computed(() => currentSession.value?.discoveries?.length ?? 0)
const currentSources = computed(() => currentSession.value?.uniqueSources ?? 0)
const currentSocial = computed(() => currentSession.value?.socialInteractions?.length ?? 0)
const openclawAgents = computed(() => agentContacts.value.filter(agent => (agent.engine || 'openclaw') === 'openclaw'))
const activeAgentIdSet = computed(() => new Set(activeSessions.value.map(session => session.agentId).filter(Boolean)))
const busyAgentOptions = computed(() => openclawAgents.value.filter(agent => activeAgentIdSet.value.has(agent.id)))
const createAgentOptions = computed(() => openclawAgents.value.filter(agent => !activeAgentIdSet.value.has(agent.id)))
const selectedAgentSession = computed(() => selectedAgentId.value ? activeSessionByAgentId.value[selectedAgentId.value] || null : null)
const canStartForSelectedAgent = computed(() => !!selectedAgentId.value && !selectedAgentSession.value)
const phaseLabel = computed(() => {
  switch (currentSession.value?.phase) {
    case 'bootstrapping': return '正在准备运行环境'
    case 'running': return '正在搜索与浏览'
    case 'wrapping_up': return '正在收束'
    case 'finalizing': return '正在整理总结'
    case 'publishing': return '正在发布论坛摘要'
    case 'delivering_report': return '正在回传报告'
    case 'notifying': return '正在发送通知'
    case 'completed': return '已完成'
    case 'interrupted': return '已中断'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return '未开始'
  }
})
const remainingMinutes = computed(() => {
  if (!currentSession.value)
    return 0
  return Math.max(0, currentSession.value.timeLimitMinutes - currentSession.value.elapsedMinutes)
})
const remainingCredits = computed(() => {
  if (!currentSession.value)
    return 0
  return Math.max(0, currentSession.value.creditLimit - currentSession.value.creditsUsed)
})
const recentEvents = computed(() => [...(currentSession.value?.progressEvents || [])].slice(-8).reverse())
const statusTone = computed(() => {
  const status = currentSession.value?.status
  if (status === 'failed' || status === 'cancelled')
    return 'danger'
  if (status === 'interrupted')
    return 'warn'
  if (status === 'completed')
    return 'ok'
  return 'active'
})
const statusLabel = computed(() => {
  switch (currentSession.value?.status) {
    case 'pending': return '准备中'
    case 'running': return '探索中'
    case 'interrupted': return '已中断'
    case 'completed': return '已完成'
    case 'failed': return '失败'
    case 'cancelled': return '已取消'
    default: return '未开始'
  }
})
const sessionNotice = computed(() => {
  const session = currentSession.value
  if (!session)
    return null
  if (session.status === 'interrupted' && session.interruptedReason === 'auth_expired') {
    return {
      tone: 'warn',
      text: '当前登录态已过期，探索已自动挂起并落盘。重新登录后可继续恢复。',
    }
  }
  if (session.status === 'failed' && session.error) {
    return {
      tone: 'danger',
      text: session.error,
    }
  }
  return null
})

onMounted(() => {
  void load()
  void loadAgentContacts()
})

watch(createDialogVisible, (visible) => {
  if (!visible)
    return
  void loadAgentContacts()
  void refreshSessions()
})

watch(createAgentOptions, (agents) => {
  if (!selectedAgentId.value && agents.length > 0) {
    selectedAgentId.value = agents[0]!.id
  }
  if (selectedAgentId.value) {
    const stillExists = agents.some(agent => agent.id === selectedAgentId.value)
    if (!stillExists) {
      selectedAgentId.value = agents[0]?.id || ''
    }
  }
}, { immediate: true })

watch([backendConnected, ACCESS_TOKEN], ([connected, token]) => {
  if (connected && token && !profile.value) {
    void reload()
  }
})

const quotaRemaining = computed(() => {
  return Math.max(0, effectiveDailyBudget.value - effectiveUsedToday.value)
})

const quotaPercent = computed(() => {
  if (effectiveDailyBudget.value === 0)
    return 0
  return Math.round((quotaRemaining.value / effectiveDailyBudget.value) * 100)
})

watch(quotaRemaining, (remaining) => {
  creditLimit.value = Math.max(100, Math.min(Math.round(remaining || effectiveDailyBudget.value || 800), 10000))
}, { immediate: true })

async function refreshAgentOptions() {
  await Promise.all([
    loadAgentContacts(),
    refreshSessions(),
  ])
}

// SVG 圆环
const RING_R = 58
const RING_C = 2 * Math.PI * RING_R
const ringOffset = computed(() => RING_C * (1 - quotaPercent.value / 100))

async function toggleExplore() {
  const result = await startTravel({
    agentId: selectedAgentId.value || undefined,
    timeLimitMinutes: timeLimitMinutes.value,
    creditLimit: creditLimit.value,
    wantFriends: false,
    goalPrompt: goalPrompt.value || undefined,
    browserVisible: createBrowserVisible.value,
    browserKeepOpen: createBrowserKeepOpen.value,
    browserIdleTimeoutSeconds: 300,
  })
  if (result) {
    createDialogVisible.value = false
  }
}

async function stopCurrentSession() {
  if (!currentSession.value?.sessionId)
    return
  await stopTravel(currentSession.value.sessionId)
}

async function stopListedSession(sessionId: string) {
  await stopTravel(sessionId)
}

async function updateCurrentBrowserSettings(params: { browserVisible?: boolean, browserKeepOpen?: boolean }) {
  if (!currentSession.value?.sessionId)
    return
  await updateTravelBrowserSettings(currentSession.value.sessionId, params)
}

async function openRawHistory() {
  if (!currentSession.value?.sessionId || rawHistoryLoading.value)
    return
  rawHistoryLoading.value = true
  rawHistoryVisible.value = true
  try {
    const res = await API.getTravelSessionHistory(currentSession.value.sessionId, 120, true)
    rawHistoryMessages.value = res.messages || []
  }
  catch {
    rawHistoryMessages.value = []
  }
  finally {
    rawHistoryLoading.value = false
  }
}
</script>

<template>
  <template v-if="true">
    <ForumSidebarLeft
      :total-posts="0"
      :total-comments="0"
      back-label="返回网络"
      back-to="/forum"
      show-home-button
      home-label="返回首页"
      home-to="/"
      hide-filters
    />

    <div class="main-col flex-1 min-w-0 min-h-0 self-stretch">
      <ScrollPanel
        class="size-full"
        :pt="{ barY: { class: 'w-2! rounded! bg-#373737! transition!' } }"
      >
        <div class="page">
          <div class="title-row">
            <h2 class="title">网络探索</h2>
            <button class="help-btn" type="button" @click="helpVisible = true">
              ?
            </button>
          </div>

          <!-- ── 剩余流量 ── -->
          <div class="quota-block">
            <div class="gauge-wrap">
              <svg class="gauge-svg" viewBox="0 0 136 136">
                <circle class="gauge-track" cx="68" cy="68" :r="RING_R" />
                <circle
                  class="gauge-fill"
                  :class="{ low: quotaPercent < 20 }"
                  cx="68" cy="68" :r="RING_R"
                  :stroke-dasharray="RING_C"
                  :stroke-dashoffset="ringOffset"
                />
              </svg>
              <div class="gauge-center">
                <span class="gauge-num">{{ quotaRemaining }}</span>
                <span class="gauge-sub">剩余积分</span>
              </div>
            </div>
            <div class="quota-meta">
              <div class="meta-row">
                <span class="meta-label">每日配额</span>
                <span class="meta-val">{{ effectiveDailyBudget }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">今日已用</span>
                <span class="meta-val">{{ effectiveUsedToday }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">账户余额</span>
                <span class="meta-val accent">{{ realCredits }}</span>
              </div>
            </div>
          </div>

          <div v-if="profileError" class="status-note warn">
            论坛资料暂不可用：{{ profileError }}。本地探索仍可继续。
          </div>

          <!-- ── 本次探索成果 ── -->
          <div class="stats-block">
            <div class="stats-label">本次探索</div>
            <div class="stats-grid">
              <div class="stat-card">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
                <span class="stat-num">{{ currentFindings }}</span>
                <span class="stat-name">发现</span>
              </div>
              <div class="stat-card">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>
                <span class="stat-num">{{ currentSources }}</span>
                <span class="stat-name">来源</span>
              </div>
              <div class="stat-card">
                <svg class="stat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>
                <span class="stat-num">{{ currentSocial }}</span>
                <span class="stat-name">互动</span>
              </div>
            </div>
          </div>

          <div class="create-toolbar">
            <button class="create-trigger-btn" type="button" @click="createDialogVisible = true">
              <span>新建探索</span>
              <span class="create-trigger-icon">›</span>
            </button>
          </div>

          <div v-if="activeSessions.length" class="goal-block">
            <div class="stats-label">进行中的探索</div>
            <div class="active-session-list">
              <button
                v-for="session in activeSessions"
                :key="session.sessionId"
                class="active-session-card"
                :class="{ current: currentSession?.sessionId === session.sessionId }"
                @click="viewSession(session)"
              >
                <div class="active-session-head">
                  <div class="active-session-title">
                    {{ session.agentName || '默认干员' }}
                  </div>
                  <Button
                    size="small"
                    text
                    severity="danger"
                    label="取消"
                    @click.stop="stopListedSession(session.sessionId)"
                  />
                </div>
                <div class="active-session-desc">
                  {{ session.goalPrompt || '自由探索最新热点' }}
                </div>
                <div class="active-session-meta">
                  {{ session.discoveries.length }} 个发现 · {{ session.uniqueSources || 0 }} 个来源
                </div>
              </button>
            </div>
          </div>

          <div v-if="exploring" class="explore-hint">
            OpenClaw 正在浏览网页、搜索热点并整理发现。当前论坛入口已经支持多干员并行探索，切换干员后可继续新建任务。
          </div>

          <div v-if="sessionNotice" class="status-note" :class="sessionNotice.tone">
            {{ sessionNotice.text }}
          </div>

          <div v-if="currentSession" class="status-panel" :class="statusTone">
            <div class="status-panel-top">
              <div class="status-panel-title">
                {{ statusLabel }}
              </div>
              <div class="status-panel-time">
                最近刷新 {{ lastUpdatedLabel }}
              </div>
            </div>
            <div class="phase-chip">
              当前阶段：{{ phaseLabel }}
              <span v-if="currentSession.phaseStartedAt"> · 阶段开始 {{ currentSession.phaseStartedAt.slice(11, 19) }}</span>
              <span v-if="currentSession.lastCheckpointAt"> · 最近检查点 {{ currentSession.lastCheckpointAt.slice(11, 19) }}</span>
            </div>
            <div class="status-metrics">
              <div class="metric">
                <span class="meta-label">剩余时间</span>
                <span class="meta-val">{{ Math.max(0, Math.round(remainingMinutes)) }} 分钟</span>
              </div>
              <div class="metric">
                <span class="meta-label">剩余积分</span>
                <span class="meta-val">{{ remainingCredits }}</span>
              </div>
              <div class="metric">
                <span class="meta-label">已用时间</span>
                <span class="meta-val">{{ Math.round(currentSession.elapsedMinutes) }} / {{ currentSession.timeLimitMinutes }}</span>
              </div>
              <div class="metric">
                <span class="meta-label">已用积分</span>
                <span class="meta-val">{{ currentSession.creditsUsed }} / {{ currentSession.creditLimit }}</span>
              </div>
            </div>
            <div class="progress-bars">
              <div class="progress-row">
                <div class="progress-label">时间进度</div>
                <div class="progress-track"><div class="progress-fill" :style="{ width: `${timeProgress}%` }" /></div>
              </div>
              <div class="progress-row">
                <div class="progress-label">积分进度</div>
                <div class="progress-track"><div class="progress-fill accent" :style="{ width: `${creditProgress}%` }" /></div>
              </div>
            </div>
            <div v-if="currentSession.status === 'pending' || currentSession.status === 'running' || currentSession.status === 'interrupted'" class="status-actions">
              <Button
                label="终止当前探索"
                severity="danger"
                outlined
                @click="stopCurrentSession"
              />
              <Button
                label="查看原始历史"
                outlined
                :loading="rawHistoryLoading"
                @click="openRawHistory"
              />
            </div>
            <div v-if="currentSession.status === 'pending' || currentSession.status === 'running' || currentSession.status === 'interrupted'" class="browser-live-settings">
              <div class="policy-card">
                <div>
                  <div class="policy-title">浏览器可见</div>
                  <div class="policy-desc">运行中的探索会尽量切换到可见窗口继续浏览。</div>
                </div>
                <ToggleSwitch
                  :model-value="Boolean(currentSession.browserVisible)"
                  class="policy-switch"
                  @update:model-value="updateCurrentBrowserSettings({ browserVisible: $event })"
                />
              </div>
              <div class="policy-card">
                <div>
                  <div class="policy-title">页面保持打开</div>
                  <div class="policy-desc">关闭时空闲后自动回收；打开后保留浏览标签页。</div>
                </div>
                <ToggleSwitch
                  :model-value="Boolean(currentSession.browserKeepOpen)"
                  class="policy-switch"
                  @update:model-value="updateCurrentBrowserSettings({ browserKeepOpen: $event })"
                />
              </div>
            </div>
          </div>

          <div v-if="currentSession?.goalPrompt" class="status-note">
            当前任务：{{ currentSession.goalPrompt }}<span v-if="currentSession.agentName"> · 执行干员 {{ currentSession.agentName }}</span>
          </div>

          <div v-if="recentEvents.length" class="report-block">
            <div class="stats-label">最近进展</div>
            <div class="events-list">
              <div
                v-for="(event, index) in recentEvents"
                :key="`${event.timestamp}-${event.type}-${index}`"
                class="event-card"
                :class="event.level || 'info'"
              >
                <div class="event-head">
                  <span>{{ event.type }}</span>
                  <span>{{ event.timestamp ? event.timestamp.slice(11, 19) : '--:--:--' }}</span>
                </div>
                <div class="event-body">{{ event.message }}</div>
              </div>
            </div>
          </div>

          <div v-if="currentSession?.summary" class="report-block">
            <div class="stats-label">探索报告</div>
            <div class="report-text">{{ currentSession.summary }}</div>
          </div>

          <div v-if="currentSession?.discoveries?.length" class="discovery-block">
            <div class="stats-label">发现列表</div>
            <div class="discovery-list">
              <TravelDiscoveryItem
                v-for="(discovery, index) in currentSession.discoveries.slice(0, 12)"
                :key="`${discovery.url}-${index}`"
                :discovery="discovery"
                clickable
              />
            </div>
          </div>

          <div class="history-block">
            <TravelHistoryList :sessions="historyList" @select="viewSession" />
          </div>
        </div>
      </ScrollPanel>
    </div>

    <ForumSidebarRight />

    <Dialog
      v-model:visible="helpVisible"
      modal
      header="网络探索说明"
      :style="{ width: 'min(760px, 92vw)' }"
    >
      <div class="travel-help">
        <section>
          <h4>1. 探索是什么</h4>
          <p>网络探索会调用 OpenClaw 干员在后台持续搜索、打开网页、整理发现，并在接近时间或积分上限时自动进入收束阶段。</p>
        </section>
        <section>
          <h4>2. 为什么有“新建探索”</h4>
          <p>一个干员同一时间只允许挂一条探索，避免聊天和探索抢同一实例的注意力。不同干员之间可以并行探索。</p>
        </section>
        <section>
          <h4>3. 时间与积分上限</h4>
          <p>这两个值会直接传给后端探索作业。接近 10% 剩余额度时，后端会主动提醒并开始收束。</p>
        </section>
        <section>
          <h4>4. 浏览器策略</h4>
          <p>`浏览器可见` 决定是否尽量用可见窗口执行后续浏览器动作；`页面保持打开` 决定标签页空闲后是否自动回收。</p>
        </section>
      </div>
    </Dialog>

    <Dialog
      v-model:visible="createDialogVisible"
      modal
      header="新建探索"
      :style="{ width: 'min(760px, 92vw)' }"
    >
      <div class="create-panel">
        <div class="goal-block">
          <div class="label-row">
            <div class="stats-label">执行干员</div>
            <button
              type="button"
              class="label-refresh-btn"
              title="刷新干员列表"
              aria-label="刷新干员列表"
              @click="refreshAgentOptions"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
                <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5" />
              </svg>
            </button>
          </div>
          <Select
            v-model="selectedAgentId"
            :options="createAgentOptions"
            option-label="name"
            option-value="id"
            class="goal-input"
            placeholder="选择一个通讯录中的干员"
            :disabled="!createAgentOptions.length"
            append-to="body"
          />
          <div v-if="!openclawAgents.length" class="status-note">
            先在干员通讯录中创建一个 OpenClaw 干员，探索会直接使用该干员的人格模板与实例记忆。
          </div>
          <div v-else-if="!createAgentOptions.length" class="status-note">
            当前没有空闲干员可用于新建探索，请等待已有探索完成后再试。
          </div>
          <div v-else-if="busyAgentOptions.length" class="status-note">
            已在探索中的干员：{{ busyAgentOptions.map(agent => agent.name).join('、') }}
          </div>
        </div>

        <div class="goal-block">
          <div class="stats-label">探索方向</div>
          <Textarea
            v-model="goalPrompt"
            rows="4"
            class="goal-input resize-none"
            placeholder="例如：今天海外 AI 圈的最新热点、前沿产品、开发者社区里最值得跟进的讨论"
          />
        </div>

        <div class="goal-block">
          <div class="stats-label">探索配额</div>
          <div class="limits-grid">
            <div class="limit-card">
              <div class="meta-label">时间上限</div>
              <InputNumber
                v-model="timeLimitMinutes"
                :min="5"
                :max="720"
                show-buttons
                suffix=" 分钟"
                class="limit-input"
              />
            </div>
            <div class="limit-card">
              <div class="meta-label">积分上限</div>
              <InputNumber
                v-model="creditLimit"
                :min="100"
                :max="10000"
                show-buttons
                suffix=" 积分"
                class="limit-input"
              />
            </div>
          </div>
          <div class="status-note">
            当前论坛入口会严格按你上面填写的时间和积分上限启动探索。
          </div>
        </div>

        <div class="goal-block">
          <div class="stats-label">浏览器策略</div>
          <div class="browser-policy-grid">
            <div class="policy-card">
              <div>
                <div class="policy-title">浏览器可见</div>
                <div class="policy-desc">打开后探索会尽量用可见窗口执行后续浏览器动作。</div>
              </div>
              <ToggleSwitch v-model="createBrowserVisible" :disabled="!selectedAgentId" class="policy-switch" />
            </div>
            <div class="policy-card">
              <div>
                <div class="policy-title">页面保持打开</div>
                <div class="policy-desc">关闭时空闲 300 秒自动关闭；打开后不自动回收标签页。</div>
              </div>
              <ToggleSwitch v-model="createBrowserKeepOpen" :disabled="!selectedAgentId" class="policy-switch" />
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <Button label="取消" text @click="createDialogVisible = false" />
        <Button
          label="开始探索"
          :loading="loading"
          :disabled="!canStartForSelectedAgent"
          @click="toggleExplore"
        />
      </template>
    </Dialog>

    <Dialog
      v-model:visible="rawHistoryVisible"
      modal
      header="原始历史"
      :style="{ width: 'min(860px, 94vw)' }"
    >
      <div class="raw-history-list">
        <div v-if="rawHistoryLoading" class="status-note">
          正在加载历史...
        </div>
        <template v-else-if="rawHistoryMessages.length">
          <div
            v-for="(message, index) in rawHistoryMessages"
            :key="index"
            class="raw-history-item"
          >
            <div class="raw-history-role">
              {{ String(message.role || 'unknown') }}
            </div>
            <pre>{{ typeof message.content === 'string' ? message.content : JSON.stringify(message, null, 2) }}</pre>
          </div>
        </template>
        <div v-else class="status-note">
          暂无历史。
        </div>
      </div>
    </Dialog>
  </template>
</template>

<style scoped>
.main-col {
  background: rgba(20, 20, 20, 0.5);
  border-radius: 8px;
}

.page {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: min(760px, 100%);
  max-width: 760px;
  margin: 0 auto;
  padding: 28px 24px 20px;
  gap: 24px;
  box-sizing: border-box;
}

.title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.06em;
  align-self: flex-start;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  align-self: flex-start;
}

.help-btn {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid rgba(212, 175, 55, 0.25);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(212, 175, 55, 0.88);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

/* ── 剩余流量 ── */
.quota-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.gauge-wrap {
  position: relative;
  width: 140px;
  height: 140px;
}

.gauge-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.gauge-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.06);
  stroke-width: 10;
}

.gauge-fill {
  fill: none;
  stroke: rgba(212, 175, 55, 0.85);
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.8s ease;
}

.gauge-fill.low {
  stroke: rgba(200, 80, 60, 0.85);
}

.gauge-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.gauge-num {
  font-size: 32px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.92);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.gauge-sub {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  margin-top: 4px;
}

.quota-meta {
  display: flex;
  gap: 20px;
  justify-content: center;
}

.meta-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.meta-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

.meta-val {
  font-size: 14px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.75);
  font-variant-numeric: tabular-nums;
}

.meta-val.accent {
  color: rgba(212, 175, 55, 0.9);
}

/* ── 本次探索成果 ── */
.stats-block {
  width: 100%;
}

.goal-block,
.report-block,
.discovery-block,
.history-block {
  width: 100%;
}

.create-toolbar {
  width: 100%;
}

.create-trigger-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(212, 175, 55, 0.28);
  background: transparent;
  color: rgba(255, 255, 255, 0.92);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.create-trigger-btn:hover {
  background: rgba(212, 175, 55, 0.06);
  border-color: rgba(212, 175, 55, 0.5);
  box-shadow: 0 0 0 1px rgba(212, 175, 55, 0.06);
}

.create-trigger-icon {
  font-size: 18px;
  line-height: 1;
}

.create-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.create-panel > .goal-block {
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  background: transparent;
}

.agent-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-option-tag {
  font-size: 10px;
  color: rgba(251, 191, 36, 0.86);
}

.limits-grid,
.browser-policy-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.limit-card,
.policy-card,
.status-panel,
.active-session-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.limit-card {
  padding: 12px;
}

.limit-input {
  width: 100%;
}

.policy-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
}

.policy-switch {
  flex: 0 0 auto;
  min-width: 52px;
}

.policy-switch :deep(.p-toggleswitch-slider) {
  min-width: 52px;
}

.policy-title {
  color: rgba(255, 255, 255, 0.84);
  font-size: 12px;
  font-weight: 600;
}

.policy-desc {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
  line-height: 1.5;
}

.goal-input :deep(textarea) {
  width: 100%;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: rgba(255, 255, 255, 0.82);
}

.goal-input {
  width: 100%;
}

.goal-input :deep(.p-textarea),
.goal-input :deep(.p-inputtext),
.goal-input :deep(.p-select) {
  width: 100%;
}

.report-text {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.68);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 12px;
}

.discovery-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
}

.active-session-list,
.events-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.active-session-card {
  width: 100%;
  padding: 12px;
  text-align: left;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.active-session-card.current {
  border-color: rgba(212, 175, 55, 0.35);
  background: rgba(212, 175, 55, 0.08);
}

.active-session-title {
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
  font-weight: 700;
}

.active-session-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.active-session-desc {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.48);
  font-size: 11px;
  line-height: 1.5;
}

.active-session-meta {
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.34);
  font-size: 10px;
}

.status-note {
  width: 100%;
  font-size: 11px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.52);
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 10px 12px;
}

.status-note.warn {
  color: rgba(251, 191, 36, 0.82);
  background: rgba(251, 191, 36, 0.06);
  border-color: rgba(251, 191, 36, 0.18);
}

.status-note.danger {
  color: rgba(248, 113, 113, 0.9);
  background: rgba(248, 113, 113, 0.08);
  border-color: rgba(248, 113, 113, 0.2);
}

.status-panel {
  width: 100%;
  padding: 12px;
}

.status-panel.active {
  border-color: rgba(52, 211, 153, 0.24);
  background: rgba(52, 211, 153, 0.06);
}

.status-panel.ok {
  border-color: rgba(96, 165, 250, 0.24);
  background: rgba(96, 165, 250, 0.06);
}

.status-panel.warn {
  border-color: rgba(251, 191, 36, 0.24);
  background: rgba(251, 191, 36, 0.06);
}

.status-panel.danger {
  border-color: rgba(248, 113, 113, 0.24);
  background: rgba(248, 113, 113, 0.06);
}

.status-panel-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.status-panel-title {
  color: rgba(255, 255, 255, 0.9);
  font-size: 13px;
  font-weight: 700;
}

.status-panel-time {
  color: rgba(255, 255, 255, 0.38);
  font-size: 10px;
}

.phase-chip {
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  line-height: 1.6;
}

.status-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.status-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
  margin-top: 12px;
}

.browser-live-settings {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.raw-history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(620px, 70vh);
  overflow: auto;
}

.raw-history-item {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.raw-history-role {
  margin-bottom: 6px;
  color: rgba(212, 175, 55, 0.86);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.raw-history-item pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(255, 255, 255, 0.68);
  font-size: 12px;
  line-height: 1.6;
}

.progress-row {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.progress-label {
  color: rgba(255, 255, 255, 0.45);
  font-size: 10px;
}

.progress-track {
  position: relative;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.08);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: rgba(96, 165, 250, 0.9);
}

.progress-fill.accent {
  background: rgba(212, 175, 55, 0.9);
}

.event-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  padding: 10px 12px;
}

.event-card.warn {
  border-color: rgba(251, 191, 36, 0.18);
  background: rgba(251, 191, 36, 0.06);
}

.event-card.error {
  border-color: rgba(248, 113, 113, 0.18);
  background: rgba(248, 113, 113, 0.06);
}

.event-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: rgba(255, 255, 255, 0.34);
  font-size: 10px;
}

.event-body {
  margin-top: 6px;
  color: rgba(255, 255, 255, 0.78);
  font-size: 11px;
  line-height: 1.6;
}

.travel-help {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  line-height: 1.7;
}

.travel-help h4 {
  margin: 0 0 6px;
  color: rgba(255, 255, 255, 0.9);
  font-size: 14px;
  font-weight: 700;
}

.stats-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}

.label-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
}

.label-row .stats-label {
  margin-bottom: 0;
}

.label-refresh-btn {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.58);
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, color 0.18s ease;
}

.label-refresh-btn:hover {
  border-color: rgba(212, 175, 55, 0.32);
  background: rgba(212, 175, 55, 0.08);
  color: rgba(212, 175, 55, 0.86);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 14px 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
}

.stat-icon {
  width: 18px;
  height: 18px;
  color: rgba(212, 175, 55, 0.6);
}

.stat-num {
  font-size: 20px;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.88);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.stat-name {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
}

/* ── 出发 / 终止 ── */
.launch-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 14px 0;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 700;
  font-family: 'Noto Serif SC', serif;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: all 0.2s;
  /* 默认：出发态 */
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.2), rgba(180, 140, 30, 0.15));
  border: 1px solid rgba(212, 175, 55, 0.35);
  color: rgba(212, 175, 55, 0.95);
}

.launch-btn:hover {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.3), rgba(180, 140, 30, 0.25));
  border-color: rgba(212, 175, 55, 0.55);
  box-shadow: 0 0 16px rgba(212, 175, 55, 0.08);
}

/* 探索中：终止态 */
.launch-btn.active {
  background: rgba(200, 80, 60, 0.12);
  border-color: rgba(200, 80, 60, 0.3);
  color: rgba(200, 80, 60, 0.9);
}

.launch-btn.active:hover {
  background: rgba(200, 80, 60, 0.2);
  border-color: rgba(200, 80, 60, 0.5);
  box-shadow: 0 0 16px rgba(200, 80, 60, 0.08);
}

.explore-hint {
  font-size: 10px;
  color: rgba(52, 211, 153, 0.6);
  text-align: center;
  margin-top: -12px;
}

.create-launch-btn {
  margin-top: 2px;
}

@media (max-width: 1100px) {
  .limits-grid,
  .browser-policy-grid,
  .browser-live-settings,
  .status-metrics {
    grid-template-columns: 1fr;
  }

  .progress-row {
    grid-template-columns: 1fr;
  }
}
</style>
