<script setup lang="ts">
import type { ModelPricing } from '@/api/business'
import type { MemoryStats } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, Select, Slider, Textarea, ToggleSwitch } from 'primevue'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getModels } from '@/api/business'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import NotificationSettingsPanel from '@/components/NotificationSettingsPanel.vue'
import { audioSettings, effectFileOptions, wakeVoiceOptions } from '@/composables/useAudio'
import { isNagaLoggedIn, nagaUser } from '@/composables/useAuth'
import { checkForUpdate } from '@/composables/useVersionCheck'
import { CONFIG, DEFAULT_CONFIG, DEFAULT_MODEL, MODELS, SYSTEM_PROMPT } from '@/utils/config'
import { trackingCalibration } from '@/utils/live2dController'

// ── Tab 切换 ──
type TabKey = 'model' | 'memory' | 'terminal' | 'notifications'
const route = useRoute()
const activeTab = ref<TabKey>((route.query.tab as TabKey) || 'terminal')

const tabs: { key: TabKey, label: string }[] = [
  { key: 'model', label: '模型连接' },
  { key: 'memory', label: '记忆连接' },
  { key: 'terminal', label: '音画配置' },
  { key: 'notifications', label: '通知设置' },
]

// ── 终端 Tab 逻辑（原 ConfigView） ──
const characterLocked = computed(() => !!CONFIG.value.system.active_character)
const characterLockedHint = computed(() =>
  characterLocked.value
    ? `由角色「${CONFIG.value.system.active_character}.json」管理，不可直接修改`
    : undefined,
)

const selectedModel = ref(Object.entries(MODELS).find(([_, model]) => {
  return model.source === CONFIG.value.web_live2d.model.source
})?.[0] ?? DEFAULT_MODEL)

const modelSelectRef = useTemplateRef<{
  updateModel: (event: null, value: string) => void
}>('modelSelectRef')

function onModelChange(value: keyof typeof MODELS) {
  CONFIG.value.web_live2d.model = { ...MODELS[value] }
}

const ssaaInputRef = useTemplateRef<{
  updateModel: (event: null, value: number) => void
}>('ssaaInputRef')

function recoverUiConfig() {
  if (!characterLocked.value) {
    CONFIG.value.system.ai_name = DEFAULT_CONFIG.system.ai_name
    modelSelectRef.value?.updateModel(null, DEFAULT_MODEL)
  }
  CONFIG.value.ui.user_name = DEFAULT_CONFIG.ui.user_name
  ssaaInputRef.value?.updateModel(null, DEFAULT_CONFIG.web_live2d.ssaa)
}

const configRouter = useRouter()

const accordionTerminal = useStorage('accordion-config', [])
const accordionModel = useStorage('accordion-config-model', [])
const accordionMemory = useStorage('accordion-config-memory', [])

const MODEL_OPTIONS = [
  { label: 'Default', value: 'default' },
  { label: 'Deepseek-V3.2', value: 'Deepseek-V3.2' },
  { label: 'Kimi-K2.5', value: 'Kimi-K2.5' },
]

// ── 模型定价（登录后从服务端拉取） ──
const modelPricingMap = ref<Record<string, ModelPricing>>({})

const selectedModelPricing = computed(() => {
  const model = CONFIG.value.api.model || 'default'
  return modelPricingMap.value[model] ?? modelPricingMap.value[model.toLowerCase()] ?? null
})

async function loadModelPricing() {
  if (!isNagaLoggedIn.value)
    return
  try {
    const res = await getModels()
    const map: Record<string, ModelPricing> = {}
    for (const m of res.data ?? []) {
      if (m.id)
        map[m.id] = m
    }
    modelPricingMap.value = map
  }
  catch {
    // 定价获取失败不影响使用
  }
}

const toast = useToast()

let _previousUserName = CONFIG.value.ui.user_name
watch(() => CONFIG.value.ui.user_name, (newVal) => {
  if (newVal.includes('柏斯阔落')) {
    toast.add({ severity: 'info', summary: '系统提示', detail: '此名词不可用', life: 3000 })
    CONFIG.value.ui.user_name = '用户'
  }
  else {
    _previousUserName = newVal
  }
})

const autoLaunchEnabled = ref(false)
const isElectron = !!window.electronAPI

onMounted(async () => {
  if (isElectron) {
    autoLaunchEnabled.value = await window.electronAPI!.autoLaunch.get()
  }
  testConnection()
  loadModelPricing()
})

async function onAutoLaunchChange(value: boolean) {
  if (isElectron) {
    await window.electronAPI!.autoLaunch.set(value)
    autoLaunchEnabled.value = value
  }
}

const checkingUpdate = ref(false)

async function handleCheckUpdate() {
  if (checkingUpdate.value)
    return
  checkingUpdate.value = true
  try {
    const hasUpdate = await checkForUpdate()
    if (!hasUpdate) {
      toast.add({ severity: 'info', summary: '已是最新版本', detail: `当前版本 v${CONFIG.value.system.version}`, life: 2500 })
    }
  }
  catch {
    toast.add({ severity: 'error', summary: '检查更新失败', detail: '请稍后重试', life: 3000 })
  }
  finally {
    checkingUpdate.value = false
  }
}

function toggleFloatingMode(enabled: boolean) {
  CONFIG.value.floating.enabled = enabled
  if (!isElectron)
    return
  if (enabled) {
    window.electronAPI?.floating.enter()
  }
  else {
    window.electronAPI?.floating.exit()
  }
}

// ── 记忆 Tab 逻辑（原 MemoryView） ──
const memoryStats = ref<MemoryStats>()
const testResult = ref<{
  severity: 'success' | 'error'
  message: string
}>()

const isCloudMode = computed(() => isNagaLoggedIn.value)

const similarityPercent = computed({
  get() {
    return CONFIG.value.grag.similarity_threshold * 100
  },
  set(value: number) {
    CONFIG.value.grag.similarity_threshold = value / 100
  },
})

// ── 模型 Tab 常量（原 MemoryView） ──
const ASR_PROVIDERS = {
  qwen: '通义千问',
  openai: 'OpenAI',
  local: 'FunASR',
}

const TTS_VOICES = {
  Cherry: '默认',
}

async function testConnection() {
  testResult.value = undefined
  try {
    const res = await API.getMemoryStats()
    const stats = res.memoryStats ?? res
    if (stats.enabled === false) {
      testResult.value = {
        severity: 'error',
        message: `未启用: ${stats.message || '请先启用知识图谱'}`,
      }
    }
    else {
      memoryStats.value = stats
      testResult.value = {
        severity: 'success',
        message: `连接成功：已加载 ${stats.totalQuintuples ?? 0} 个五元组`,
      }
    }
  }
  catch (error: any) {
    testResult.value = {
      severity: 'error',
      message: `连接失败: ${error.message}`,
    }
  }
}
</script>

<template>
  <BoxContainer class="text-sm">
    <!-- Tab 栏 -->
    <div class="flex gap-1 mb-4 px-1">
      <button
        v-for="tab in tabs" :key="tab.key"
        class="tab-btn" :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- 模型 Tab -->
    <div v-show="activeTab === 'model'">
      <!-- 配置模式指示器 -->
      <div class="config-mode-banner" :class="isNagaLoggedIn ? 'mode-gateway' : 'mode-local'">
        <div class="config-mode-icon">
          <span v-if="isNagaLoggedIn">&#9729;</span>
          <span v-else>&#9881;</span>
        </div>
        <div class="config-mode-info">
          <div class="config-mode-title">
            {{ isNagaLoggedIn ? '网关模式' : '本地模式' }}
          </div>
          <div class="config-mode-desc">
            <template v-if="isNagaLoggedIn">
              已登录 <strong>{{ nagaUser?.username }}</strong>，所有模型请求通过 NagaModel 网关转发，无需配置 API 密钥
            </template>
            <template v-else>
              未登录，需手动配置各模型的 API 地址和密钥
            </template>
          </div>
        </div>
      </div>

      <Accordion :value="accordionModel" class="pb-8" multiple>
        <!-- 大语言模型 -->
        <ConfigGroup value="llm" header="大语言模型">
          <div class="grid gap-4">
            <ConfigItem name="模型名称" description="用于对话的大语言模型">
              <div class="flex items-center gap-3">
                <Select
                  v-model="CONFIG.api.model"
                  :options="MODEL_OPTIONS"
                  option-label="label"
                  option-value="value"
                />
                <span v-if="selectedModelPricing" class="model-pricing">
                  <span title="输入价格">↑{{ selectedModelPricing.inputPrice ?? '-' }}</span>
                  <span class="text-white/15">/</span>
                  <span title="输出价格">↓{{ selectedModelPricing.outputPrice ?? '-' }}</span>
                </span>
              </div>
            </ConfigItem>
            <!-- 网关模式: 合并显示连接状态 -->
            <template v-if="isNagaLoggedIn">
              <ConfigItem name="连接状态" description="API 地址与密钥由网关自动管理">
                <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
              </ConfigItem>
            </template>
            <!-- 本地模式: 展开完整配置 -->
            <template v-else>
              <ConfigItem name="API 地址" description="兼容 OpenAI 格式的 API 地址">
                <InputText v-model="CONFIG.api.base_url" placeholder="https://api.deepseek.com/v1" />
              </ConfigItem>
              <ConfigItem name="API 密钥" description="大语言模型的 API 密钥">
                <InputText v-model="CONFIG.api.api_key" type="password" placeholder="sk-..." />
              </ConfigItem>
            </template>
            <Divider class="m-1!" />
            <ConfigItem name="最大令牌数" description="单次对话的最大长度限制">
              <InputNumber v-model="CONFIG.api.max_tokens" show-buttons />
            </ConfigItem>
            <ConfigItem name="历史轮数" description="使用最近几轮对话内容作为上下文">
              <InputNumber v-model="CONFIG.api.max_history_rounds" show-buttons />
            </ConfigItem>
            <ConfigItem name="加载天数" description="从最近几天的日志文件中加载历史对话">
              <InputNumber v-model="CONFIG.api.context_load_days" show-buttons />
            </ConfigItem>
          </div>
        </ConfigGroup>

        <!-- 电脑控制模型 -->
        <ConfigGroup value="control">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>电脑控制模型</span>
              <label class="flex items-center gap-4">
                启用
                <ToggleSwitch v-model="CONFIG.computer_control.enabled" size="small" @click.stop />
              </label>
            </div>
          </template>
          <div class="grid gap-4">
            <template v-if="isNagaLoggedIn">
              <ConfigItem name="连接状态" description="控制模型与定位模型均由网关管理">
                <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
              </ConfigItem>
            </template>
            <template v-else>
              <ConfigItem name="控制模型" description="用于电脑控制任务的主要模型">
                <InputText v-model="CONFIG.computer_control.model" />
              </ConfigItem>
              <ConfigItem name="控制模型 API 地址" description="控制模型的 API 地址">
                <InputText v-model="CONFIG.computer_control.model_url" placeholder="https://..." />
              </ConfigItem>
              <ConfigItem name="控制模型 API 密钥" description="控制模型的 API 密钥">
                <InputText v-model="CONFIG.computer_control.api_key" type="password" placeholder="sk-..." />
              </ConfigItem>
              <Divider class="m-1!" />
              <ConfigItem name="定位模型" description="用于元素定位和坐标识别的模型">
                <InputText v-model="CONFIG.computer_control.grounding_model" />
              </ConfigItem>
              <ConfigItem name="定位模型 API 地址" description="定位模型的 API 地址">
                <InputText v-model="CONFIG.computer_control.grounding_url" placeholder="https://..." />
              </ConfigItem>
              <ConfigItem name="定位模型 API 密钥" description="定位模型的 API 密钥">
                <InputText v-model="CONFIG.computer_control.grounding_api_key" type="password" placeholder="sk-..." />
              </ConfigItem>
            </template>
          </div>
        </ConfigGroup>

        <!-- 语音识别模型 -->
        <ConfigGroup value="asr">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>语音识别模型</span>
              <label class="flex items-center gap-4">
                启用
                <ToggleSwitch v-model="CONFIG.voice_realtime.enabled" size="small" @click.stop />
              </label>
            </div>
          </template>
          <div class="grid gap-4">
            <template v-if="isNagaLoggedIn">
              <ConfigItem name="连接状态" description="语音识别由网关管理">
                <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
              </ConfigItem>
            </template>
            <template v-else>
              <ConfigItem name="模型名称" description="用于语音识别的模型">
                <InputText v-model="CONFIG.voice_realtime.asr_model" />
              </ConfigItem>
              <ConfigItem name="模型提供者" description="语音识别模型的提供者">
                <Select v-model="CONFIG.voice_realtime.provider" :options="Object.keys(ASR_PROVIDERS)">
                  <template #option="{ option }">
                    {{ ASR_PROVIDERS[option as keyof typeof ASR_PROVIDERS] }}
                  </template>
                  <template #value="{ value }">
                    {{ ASR_PROVIDERS[value as keyof typeof ASR_PROVIDERS] }}
                  </template>
                </Select>
              </ConfigItem>
              <ConfigItem name="API 密钥" description="语音识别模型的 API 密钥">
                <InputText v-model="CONFIG.voice_realtime.api_key" type="password" />
              </ConfigItem>
            </template>
          </div>
        </ConfigGroup>

        <!-- 语音合成模型 -->
        <ConfigGroup value="tts">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>语音合成模型</span>
              <label class="flex items-center gap-4">
                启用
                <ToggleSwitch v-model="CONFIG.system.voice_enabled" size="small" @click.stop />
              </label>
            </div>
          </template>
          <div class="grid gap-4">
            <ConfigItem name="声线" description="语音合成模型的声线">
              <Select v-model="CONFIG.tts.default_voice" :options="Object.keys(TTS_VOICES)">
                <template #option="{ option }">
                  {{ TTS_VOICES[option as keyof typeof TTS_VOICES] }}
                </template>
                <template #value="{ value }">
                  {{ TTS_VOICES[value as keyof typeof TTS_VOICES] }}
                </template>
              </Select>
            </ConfigItem>
            <template v-if="isNagaLoggedIn">
              <ConfigItem name="连接状态" description="语音合成由网关管理">
                <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
              </ConfigItem>
            </template>
            <template v-else>
              <ConfigItem name="模型名称" description="用于语音合成的模型">
                <InputText v-model="CONFIG.voice_realtime.tts_model" />
              </ConfigItem>
              <ConfigItem name="服务端口" description="用于语音合成的本地服务端口">
                <InputNumber v-model="CONFIG.tts.port" :min="1000" :max="65535" show-buttons />
              </ConfigItem>
              <ConfigItem name="API 密钥" description="语音合成模型的 API 密钥">
                <InputText v-model="CONFIG.tts.api_key" type="password" />
              </ConfigItem>
            </template>
          </div>
        </ConfigGroup>

        <!-- 嵌入模型 -->
        <ConfigGroup value="embedding" header="嵌入模型">
          <div class="grid gap-4">
            <template v-if="isNagaLoggedIn">
              <ConfigItem name="连接状态" description="嵌入模型由网关管理">
                <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
              </ConfigItem>
            </template>
            <template v-else>
              <ConfigItem name="模型名称" description="用于向量嵌入的模型">
                <InputText v-model="CONFIG.embedding.model" />
              </ConfigItem>
              <ConfigItem name="API 地址" description="嵌入模型的 API 地址（留空使用主模型地址）">
                <InputText v-model="CONFIG.embedding.api_base" placeholder="留空使用主模型地址" />
              </ConfigItem>
              <ConfigItem name="API 密钥" description="嵌入模型的 API 密钥（留空使用主模型密钥）">
                <InputText v-model="CONFIG.embedding.api_key" type="password" placeholder="留空使用主模型密钥" />
              </ConfigItem>
            </template>
          </div>
        </ConfigGroup>
      </Accordion>
    </div>

    <!-- 记忆 Tab -->
    <div v-show="activeTab === 'memory'">
      <!-- 配置模式指示器 -->
      <div class="config-mode-banner" :class="isCloudMode ? 'mode-gateway' : 'mode-local'">
        <div class="config-mode-icon">
          <span v-if="isCloudMode">&#9729;</span>
          <span v-else>&#9881;</span>
        </div>
        <div class="config-mode-info">
          <div class="config-mode-title">
            {{ isCloudMode ? '云端记忆' : '本地记忆' }}
          </div>
          <div class="config-mode-desc">
            <template v-if="isCloudMode">
              使用夏园云端记忆微服务，数据自动同步
            </template>
            <template v-else>
              使用本地 Neo4j 图数据库存储记忆
            </template>
          </div>
        </div>
      </div>

      <Accordion :value="accordionMemory" class="pb-8" multiple>
        <ConfigGroup value="neo4j" :header="isCloudMode ? '云端记忆服务' : 'Neo4j 数据库'">
          <div class="grid gap-4">
            <!-- 云端模式 -->
            <template v-if="isCloudMode">
              <ConfigItem name="服务状态" description="夏园 云端记忆微服务">
                <span class="naga-authed">&#10003; 云端记忆已连接 ({{ nagaUser?.username }})</span>
              </ConfigItem>
              <ConfigItem
                v-if="memoryStats"
                name="五元组数量"
                description="云端存储的记忆五元组总数"
              >
                <span class="text-white/70">{{ memoryStats.totalQuintuples ?? 0 }}</span>
              </ConfigItem>
            </template>
            <!-- 本地模式 -->
            <template v-else>
              <ConfigItem name="连接地址" description="Neo4j 数据库连接 URI">
                <InputText v-model="CONFIG.grag.neo4j_uri" placeholder="neo4j://127.0.0.1:7687" />
              </ConfigItem>
              <ConfigItem name="用户名" description="Neo4j 数据库用户名">
                <InputText v-model="CONFIG.grag.neo4j_user" placeholder="neo4j" />
              </ConfigItem>
              <ConfigItem name="密码" description="Neo4j 数据库密码">
                <InputText v-model="CONFIG.grag.neo4j_password" type="password" placeholder="••••••••" />
              </ConfigItem>
            </template>
            <Divider class="m-1!" />
            <ConfigItem name="知识图谱">
              <label class="flex items-center gap-4">
                启用
                <ToggleSwitch v-model="CONFIG.grag.enabled" size="small" />
              </label>
            </ConfigItem>
            <ConfigItem name="自动提取" description="自动从对话中提取五元组知识">
              <ToggleSwitch v-model="CONFIG.grag.auto_extract" />
            </ConfigItem>
            <ConfigItem name="上下文长度" description="最近对话窗口大小">
              <InputNumber v-model="CONFIG.grag.context_length" :min="1" :max="20" show-buttons />
            </ConfigItem>
            <ConfigItem name="相似度阈值" description="RAG 知识检索匹配阈值">
              <InputNumber v-model="similarityPercent" :min="0" :max="100" suffix="%" show-buttons />
            </ConfigItem>
            <Divider class="m-1!" />
            <div class="flex flex-row-reverse justify-between gap-4">
              <Button
                :label="testResult ? (isCloudMode ? '检查连接' : '测试连接') : '测试中...'"
                size="small"
                :disabled="!testResult"
                @click="testConnection"
              />
              <Message
                v-if="testResult" :pt="{ content: { class: 'p-2.5!' } }"
                :severity="testResult.severity"
              >
                {{ testResult.message }}
              </Message>
            </div>
          </div>
        </ConfigGroup>
      </Accordion>
    </div>

    <!-- 终端 Tab -->
    <div v-show="activeTab === 'terminal'">
      <Accordion :value="accordionTerminal" class="pb-6" multiple>
        <ConfigGroup value="ui">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>显示设置</span>
              <Button size="small" label="恢复默认" @click.stop="recoverUiConfig" />
            </div>
          </template>
          <div class="grid gap-4">
            <ConfigItem name="用户昵称" description="聊天窗口显示的用户昵称">
              <InputText v-model="CONFIG.ui.user_name" />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem name="Live2D 模型位置">
              <div class="flex flex-col items-center justify-evenly">
                <label v-for="direction in ['x', 'y'] as const" :key="direction" class="w-full flex items-center">
                  <div class="capitalize w-0 -translate-x-4">{{ direction }}</div>
                  <Slider
                    v-model="CONFIG.web_live2d.model[direction]"
                    class="w-full" :min="-2" :max="2" :step="1e-3"
                  />
                </label>
              </div>
            </ConfigItem>
            <ConfigItem name="Live2D 模型缩放">
              <Slider v-model="CONFIG.web_live2d.model.size" :min="0" :max="9000" />
            </ConfigItem>
            <ConfigItem name="Live2D 模型超采样倍数">
              <InputNumber
                ref="ssaaInputRef"
                v-model="CONFIG.web_live2d.ssaa"
                :min="1" :max="4" show-buttons
              />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem name="视角校准" description="调整追踪参考点到模型面部位置，开启准星后拖动滑块使红色十字对准面部">
              <div class="flex items-center gap-3 w-full">
                <Slider
                  v-model="CONFIG.web_live2d.face_y_ratio"
                  class="flex-1" :min="0" :max="1" :step="0.01"
                />
                <Button
                  :label="trackingCalibration ? '关闭准星' : '显示准星'"
                  :severity="trackingCalibration ? 'danger' : 'secondary'"
                  size="small"
                  @click="trackingCalibration = !trackingCalibration"
                />
              </div>
            </ConfigItem>
            <ConfigItem name="视角追踪延迟" description="按住鼠标超过该时间(毫秒)后才开始视角追踪，0=点击即追踪">
              <InputNumber
                :model-value="CONFIG.web_live2d.tracking_hold_delay_ms ?? 100"
                :min="0" :max="5000" :step="100"
                show-buttons
                @update:model-value="(v: number | null) => { CONFIG.web_live2d.tracking_hold_delay_ms = v ?? 100 }"
              />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem v-if="isElectron" name="悬浮球模式" description="启用后窗口变为可拖拽的悬浮球，点击展开聊天面板">
              <ToggleSwitch
                :model-value="CONFIG.floating.enabled"
                @update:model-value="toggleFloatingMode"
              />
            </ConfigItem>
          </div>
        </ConfigGroup>
        <ConfigGroup value="character">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>角色档案</span>
              <Button size="small" label="切换角色" @click.stop="configRouter.push('/market?tab=memory-skin')" />
            </div>
          </template>
          <div class="grid gap-4">
            <ConfigItem name="角色名称" :description="characterLockedHint ?? '聊天窗口显示的 AI 昵称'">
              <InputText v-model="CONFIG.system.ai_name" :disabled="characterLocked" />
            </ConfigItem>
            <ConfigItem name="L2D 模型" :description="characterLocked ? characterLockedHint : undefined">
              <Select
                ref="modelSelectRef"
                :options="Object.keys(MODELS)"
                :model-value="selectedModel"
                :disabled="characterLocked"
                @change="(event) => onModelChange(event.value)"
              />
            </ConfigItem>
            <ConfigItem
              layout="column"
              name="系统提示词"
              :description="characterLocked ? characterLockedHint : '编辑对话风格提示词，影响AI的回复风格和语言特点'"
            >
              <div class="flex flex-col gap-1 mt-3">
                <Textarea v-model="SYSTEM_PROMPT" rows="10" class="resize-none" :disabled="characterLocked" />
              </div>
            </ConfigItem>
          </div>
        </ConfigGroup>
        <ConfigGroup value="audio">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>音乐设置</span>
              <Button size="small" label="音律坊" @click.stop="configRouter.push('/music')" />
            </div>
          </template>
          <div class="grid gap-4">
            <ConfigItem name="背景音乐" description="启用/关闭背景音乐">
              <ToggleSwitch v-model="audioSettings.bgmEnabled" />
            </ConfigItem>
            <ConfigItem name="音乐音量">
              <Slider v-model="audioSettings.bgmVolume" :min="0" :max="1" :step="0.01" />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem name="点击音效" description="启用/关闭UI交互音效">
              <ToggleSwitch v-model="audioSettings.effectEnabled" />
            </ConfigItem>
            <ConfigItem name="音效音量">
              <Slider v-model="audioSettings.effectVolume" :min="0" :max="1" :step="0.01" />
            </ConfigItem>
            <ConfigItem name="音效文件" description="选择点击音效">
              <Select v-model="audioSettings.clickEffect" :options="effectFileOptions" />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem name="唤醒语音" description="点击唤醒时播放的语音包">
              <Select v-model="audioSettings.wakeVoice" :options="wakeVoiceOptions" />
            </ConfigItem>
          </div>
        </ConfigGroup>
        <ConfigGroup value="system">
          <template #header>
            <div class="flex w-full justify-between">
              <span>系统设置</span>
              <span>v{{ CONFIG.system.version }}</span>
            </div>
          </template>
          <div class="grid gap-4">
            <ConfigItem name="当前账号">
              <div v-if="nagaUser" class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-amber-600/60 flex items-center justify-center text-white text-sm font-bold shrink-0">
                  {{ nagaUser.username.charAt(0).toUpperCase() }}
                </div>
                <span class="text-white/80">{{ nagaUser.username }}</span>
              </div>
              <span v-else class="text-white/40">未登录</span>
            </ConfigItem>
            <ConfigItem v-if="isElectron" name="开机自启动" description="系统启动时自动运行应用">
              <ToggleSwitch :model-value="autoLaunchEnabled" @update:model-value="onAutoLaunchChange" />
            </ConfigItem>
          </div>
        </ConfigGroup>
      </Accordion>
      <div class="terminal-footer">
        <div class="terminal-footer-version">
          当前版本 v{{ CONFIG.system.version }}
        </div>
        <Button
          size="small"
          outlined
          :loading="checkingUpdate"
          label="检查更新"
          @click="handleCheckUpdate"
        />
      </div>
    </div>

    <div v-show="activeTab === 'notifications'">
      <NotificationSettingsPanel />
    </div>
  </BoxContainer>
</template>

<style scoped>
.tab-btn {
  flex: 1;
  padding: 0.5rem 0;
  font-size: 0.875rem;
  font-weight: 600;
  text-align: center;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.5rem;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.6);
}

.tab-btn.active {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.9);
}

.config-mode-banner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  margin-bottom: 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid;
}

.config-mode-banner.mode-gateway {
  background: rgba(74, 222, 128, 0.06);
  border-color: rgba(74, 222, 128, 0.2);
}

.config-mode-banner.mode-local {
  background: rgba(251, 191, 36, 0.06);
  border-color: rgba(251, 191, 36, 0.2);
}

.config-mode-icon {
  font-size: 1.25rem;
  line-height: 1;
  flex-shrink: 0;
}

.mode-gateway .config-mode-icon { color: #4ade80; }
.mode-local .config-mode-icon { color: #fbbf24; }

.config-mode-title {
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.2;
}

.mode-gateway .config-mode-title { color: #4ade80; }
.mode-local .config-mode-title { color: #fbbf24; }

.config-mode-desc {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
  line-height: 1.4;
  margin-top: 0.125rem;
}

.config-mode-desc strong {
  color: rgba(255, 255, 255, 0.8);
}

.naga-authed {
  color: #4ade80;
  font-size: 0.875rem;
  font-weight: 500;
}

.model-pricing {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.terminal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 0.25rem;
  padding: 0.9rem 0.25rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.terminal-footer-version {
  color: rgba(255, 255, 255, 0.5);
  font-size: 12px;
}
</style>
