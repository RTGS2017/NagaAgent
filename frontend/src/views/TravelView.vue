<script setup lang="ts">
import { computed, ref } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import TravelConfigForm from '@/travel/components/TravelConfigForm.vue'
import TravelHistoryList from '@/travel/components/TravelHistoryList.vue'
import TravelResultPanel from '@/travel/components/TravelResultPanel.vue'
import TravelRunningPanel from '@/travel/components/TravelRunningPanel.vue'
import { useTravel } from '@/travel/composables/useTravel'

const {
  travelSession,
  activeSessions,
  isRunning,
  isCompleted,
  historyList,
  loading,
  timeProgress,
  creditProgress,
  lastUpdatedLabel,
  startTravel,
  stopTravel,
  updateTravelBrowserSettings,
  viewSession,
  clearSelection,
} = useTravel()

const agentFilter = ref('all')
const statusFilter = ref('all')
const timeRangeFilter = ref<'all' | '24h' | '7d' | '30d'>('all')

const allSessions = computed(() => [...activeSessions.value, ...historyList.value])
const agentOptions = computed(() => {
  const seen = new Map<string, string>()
  for (const session of allSessions.value) {
    if (!session.agentId)
      continue
    seen.set(session.agentId, session.agentName || session.agentId)
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label }))
})

function isWithinTimeRange(iso?: string) {
  if (timeRangeFilter.value === 'all')
    return true
  const ts = Date.parse(iso || '')
  if (!ts)
    return false
  const hours = timeRangeFilter.value === '24h' ? 24 : timeRangeFilter.value === '7d' ? 24 * 7 : 24 * 30
  return Date.now() - ts <= hours * 60 * 60 * 1000
}

function matchesFilters(session: { agentId?: string, status: string, completedAt?: string, startedAt?: string, createdAt: string }) {
  if (agentFilter.value !== 'all' && session.agentId !== agentFilter.value)
    return false
  if (statusFilter.value !== 'all' && session.status !== statusFilter.value)
    return false
  return isWithinTimeRange(session.completedAt || session.startedAt || session.createdAt)
}

const filteredActiveSessions = computed(() => activeSessions.value.filter(matchesFilters))
const filteredHistoryList = computed(() => historyList.value.filter(matchesFilters))
</script>

<template>
  <BoxContainer class="text-sm">
    <div class="grid gap-5 p-2 pb-8 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div class="flex flex-col gap-4">
        <div class="text-white/55 text-xs tracking-[0.18em] uppercase">
          新建探索
        </div>
        <TravelConfigForm :loading="loading" button-label="新建探索" @start="startTravel" />

        <div class="border-t border-white/8 my-1" />

        <div class="grid gap-2 rounded-lg border border-white/8 bg-white/2 p-3 text-xs text-white/60">
          <div class="text-white/75">
            任务筛选
          </div>
          <select v-model="agentFilter" class="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-white/80 outline-none">
            <option value="all">
              全部干员
            </option>
            <option v-for="option in agentOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <select v-model="statusFilter" class="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-white/80 outline-none">
            <option value="all">
              全部状态
            </option>
            <option value="pending">
              准备中
            </option>
            <option value="running">
              探索中
            </option>
            <option value="interrupted">
              已中断
            </option>
            <option value="completed">
              已完成
            </option>
            <option value="failed">
              失败
            </option>
            <option value="cancelled">
              已取消
            </option>
          </select>
          <select v-model="timeRangeFilter" class="rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-white/80 outline-none">
            <option value="all">
              全部时间
            </option>
            <option value="24h">
              最近 24 小时
            </option>
            <option value="7d">
              最近 7 天
            </option>
            <option value="30d">
              最近 30 天
            </option>
          </select>
        </div>

        <div class="flex flex-col gap-2">
          <div class="text-white/40 text-xs">
            进行中的探索
          </div>
          <div v-if="!filteredActiveSessions.length" class="flex items-center justify-center min-h-20 rounded-lg border border-white/6 bg-white/2 text-white/25 text-sm">
            暂无进行中的探索
          </div>
          <button
            v-for="session in filteredActiveSessions"
            :key="session.sessionId"
            class="flex w-full items-start justify-between gap-3 rounded-lg border border-white/8 bg-white/3 px-3 py-2 text-left text-xs text-white/65 transition hover:bg-white/6"
            :class="{ 'border-#d4af37/35 bg-#d4af37/6 text-white/80': travelSession?.sessionId === session.sessionId }"
            @click="viewSession(session)"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-white/85">
                {{ session.agentName || '默认干员' }}
              </div>
              <div class="mt-1 line-clamp-2 text-[11px] text-white/40">
                {{ session.goalPrompt || '自由探索最新热点' }}
              </div>
              <div class="mt-2 text-[10px] text-white/30">
                {{ session.discoveries.length }} 个发现 · {{ session.uniqueSources || 0 }} 个来源
              </div>
            </div>
            <span class="rounded-full bg-green-500/10 px-2 py-0.5 text-[10px] text-green-300/80">
              {{ session.status === 'pending' ? '准备中' : '探索中' }}
            </span>
          </button>
        </div>

        <div class="border-t border-white/8 my-1" />
        <TravelHistoryList :sessions="filteredHistoryList" @select="viewSession" />
      </div>

      <div class="flex min-h-[420px] flex-col gap-4">
        <template v-if="travelSession">
          <TravelRunningPanel
            v-if="isRunning && travelSession"
            :session="travelSession"
            :time-progress="timeProgress"
            :credit-progress="creditProgress"
            :last-updated-label="lastUpdatedLabel"
            @stop="stopTravel(travelSession.sessionId)"
            @update-browser-settings="updateTravelBrowserSettings(travelSession.sessionId, $event)"
          />

          <TravelResultPanel
            v-else-if="isCompleted && travelSession"
            :session="travelSession"
            @new-travel="clearSelection"
          />
        </template>

        <div v-else class="flex min-h-[320px] items-center justify-center rounded-xl border border-dashed border-white/10 bg-white/2 px-6 text-center text-white/30">
          选择一个探索任务查看详情，或者直接新建探索。
        </div>
      </div>
    </div>
  </BoxContainer>
</template>
