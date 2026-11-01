<script setup lang="ts">
import type { TravelProgressEvent, TravelSession } from '@/travel/types'
import { Button, ProgressBar, ToggleSwitch } from 'primevue'
import { computed } from 'vue'
import { formatMinutes } from '@/travel/composables/useTravel'
import TravelDiscoveryItem from './TravelDiscoveryItem.vue'

const props = defineProps<{
  session: TravelSession
  timeProgress: number
  creditProgress: number
  lastUpdatedLabel: string
}>()

const emit = defineEmits<{
  stop: []
  updateBrowserSettings: [payload: { browserVisible?: boolean, browserKeepOpen?: boolean }]
}>()

const browserVisible = computed({
  get: () => Boolean(props.session.browserVisible),
  set: value => emit('updateBrowserSettings', { browserVisible: value }),
})

const browserKeepOpen = computed({
  get: () => Boolean(props.session.browserKeepOpen),
  set: value => emit('updateBrowserSettings', { browserKeepOpen: value }),
})

const remainingMinutes = computed(() => Math.max(0, props.session.timeLimitMinutes - props.session.elapsedMinutes))
const remainingCredits = computed(() => Math.max(0, props.session.creditLimit - props.session.creditsUsed))
const creditBurnRate = computed(() => {
  if (!props.session.elapsedMinutes || props.session.elapsedMinutes <= 0)
    return null
  const rate = props.session.creditsUsed / props.session.elapsedMinutes
  return Number.isFinite(rate) && rate > 0 ? rate : null
})
const estimatedRemainingMinutes = computed(() => {
  const byTime = remainingMinutes.value
  const rate = creditBurnRate.value
  if (!rate)
    return byTime
  return Math.max(0, Math.min(byTime, remainingCredits.value / rate))
})
const timeWarning = computed(() => remainingMinutes.value <= Math.max(1, props.session.timeLimitMinutes * 0.1))
const creditWarning = computed(() => remainingCredits.value <= Math.max(1, props.session.creditLimit * 0.1))
const recentEvents = computed<TravelProgressEvent[]>(() => [...(props.session.progressEvents || [])].slice(-6).reverse())

function formatEta(minutes: number): string {
  if (!Number.isFinite(minutes))
    return '-'
  if (minutes >= 60)
    return `${(minutes / 60).toFixed(1)}h`
  return `${Math.max(0, Math.round(minutes))}m`
}

function eventToneClass(level?: string) {
  if (level === 'error')
    return 'border-red-400/15 bg-red-500/6 text-red-100/80'
  if (level === 'warn')
    return 'border-amber-400/15 bg-amber-500/6 text-amber-100/80'
  return 'border-white/8 bg-white/2 text-white/70'
}
</script>

<template>
  <div class="flex items-center gap-2 text-white/80 text-base font-bold">
    <span class="inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
    探索进行中
  </div>

  <div v-if="session.goalPrompt" class="text-white/35 text-[11px] leading-relaxed bg-white/2 rounded-lg p-3">
    探索方向：{{ session.goalPrompt }}
  </div>

  <div class="grid grid-cols-2 gap-2 text-[11px]">
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      执行干员
      <div class="mt-1 text-white/80 text-xs">
        {{ session.agentName || '自动分配' }}
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      最近刷新
      <div class="mt-1 text-white/80 text-xs">
        {{ lastUpdatedLabel }}
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      累计发现
      <div class="mt-1 text-white/80 text-xs">
        {{ session.discoveries.length }} 条
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      来源去重
      <div class="mt-1 text-white/80 text-xs">
        {{ session.uniqueSources || 0 }} 个
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55" :class="{ 'ring-1 ring-amber-300/20': timeWarning }">
      剩余时间
      <div class="mt-1 text-white/80 text-xs">
        {{ formatMinutes(remainingMinutes) }}
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55" :class="{ 'ring-1 ring-amber-300/20': creditWarning }">
      剩余积分
      <div class="mt-1 text-white/80 text-xs">
        {{ remainingCredits }}
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      预计还能跑
      <div class="mt-1 text-white/80 text-xs">
        {{ formatEta(estimatedRemainingMinutes) }}
      </div>
    </div>
    <div class="rounded-lg bg-white/3 px-3 py-2 text-white/55">
      积分速率
      <div class="mt-1 text-white/80 text-xs">
        {{ creditBurnRate ? `${creditBurnRate.toFixed(1)}/min` : '样本不足' }}
      </div>
    </div>
  </div>

  <div class="grid grid-cols-1 gap-2 rounded-lg border border-white/8 bg-white/2 px-3 py-3 text-[11px] text-white/55">
    <div class="text-white/75 text-xs">
      浏览器策略
    </div>
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-white/80">浏览器可见</div>
        <div class="mt-1 text-white/35">
          关闭时默认无头；切换后会影响后续浏览器动作
        </div>
      </div>
      <ToggleSwitch v-model="browserVisible" />
    </div>
    <div class="flex items-center justify-between gap-3">
      <div>
        <div class="text-white/80">页面保持打开</div>
        <div class="mt-1 text-white/35">
          关闭时空闲 300 秒自动关闭；打开后不自动回收
        </div>
      </div>
      <ToggleSwitch v-model="browserKeepOpen" />
    </div>
  </div>

  <div
    v-if="session.wrapUpSent"
    class="rounded-lg border border-blue-400/15 bg-blue-500/6 px-3 py-2 text-[11px] leading-relaxed text-blue-100/75"
  >
    已进入收束阶段，正在整理最终报告并准备回传。
  </div>

  <div
    v-else-if="(session.idlePolls || 0) >= 2 && !session.discoveries.length"
    class="rounded-lg border border-amber-400/15 bg-amber-500/6 px-3 py-2 text-[11px] leading-relaxed text-amber-100/75"
  >
    暂时还没有新的可保留发现，当前更像是在搜索或等待工具返回，不是已经停止。
  </div>

  <!-- 时间进度 -->
  <div class="flex flex-col gap-1">
    <div class="flex justify-between text-xs text-white/50">
      <span>已用时间</span>
      <span>{{ formatMinutes(session.elapsedMinutes) }} / {{ formatMinutes(session.timeLimitMinutes) }}</span>
    </div>
    <ProgressBar :value="timeProgress" :show-value="false" class="h-2!" />
  </div>

  <!-- 积分进度 -->
  <div class="flex flex-col gap-1">
    <div class="flex justify-between text-xs text-white/50">
      <span>已用积分</span>
      <span>{{ session.creditsUsed }} / {{ session.creditLimit }}</span>
    </div>
    <ProgressBar :value="creditProgress" :show-value="false" class="h-2!" />
  </div>

  <!-- 实时发现 -->
  <div v-if="session.discoveries.length" class="flex flex-col gap-2">
    <div class="text-white/40 text-xs">
      发现 ({{ session.discoveries.length }})
    </div>
    <div class="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
      <TravelDiscoveryItem
        v-for="(d, i) in session.discoveries.slice(-5)"
        :key="i"
        :discovery="d"
      />
    </div>
  </div>

  <div v-if="recentEvents.length" class="flex flex-col gap-2">
    <div class="text-white/40 text-xs">
      最近进展
    </div>
    <div class="flex max-h-48 flex-col gap-2 overflow-y-auto">
      <div
        v-for="(event, index) in recentEvents"
        :key="`${event.timestamp}-${event.type}-${index}`"
        class="rounded-lg border px-3 py-2 text-[11px] leading-relaxed"
        :class="eventToneClass(event.level)"
      >
        <div class="flex items-center justify-between gap-3 text-[10px] text-white/35">
          <span>{{ event.type }}</span>
          <span>{{ event.timestamp ? event.timestamp.slice(11, 19) : '--:--:--' }}</span>
        </div>
        <div class="mt-1 text-white/80">
          {{ event.message }}
        </div>
      </div>
    </div>
  </div>

  <!-- 停止按钮 -->
  <div class="flex justify-center mt-2">
    <Button
      label="停止探索"
      severity="danger"
      outlined
      class="px-8!"
      @click="emit('stop')"
    />
  </div>
</template>
