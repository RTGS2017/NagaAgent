<script setup lang="ts">
import type { ModelPricing } from '@/api/business'
import type { CustomLive2DModel, MemoryStats } from '@/api/core'
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
import { backendConnected, CONFIG, DEFAULT_CONFIG, DEFAULT_MODEL, MODELS, SYSTEM_PROMPT } from '@/utils/config'
import { trackingCalibration } from '@/utils/live2dController'
import { applyCustomLive2DModel, applyLive2DModel, toCustomLive2DModelConfig, upsertCustomLive2DModel } from '@/utils/live2dModels'

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

const selectedModel = computed(() => Object.entries(MODELS).find(([_, model]) => {
  return model.source === CONFIG.value.web_live2d.model.source
})?.[0] ?? DEFAULT_MODEL)

function onModelChange(value: keyof typeof MODELS) {
  applyLive2DModel({ ...MODELS[value] })
  CONFIG.value.system.active_character = ''
}

const ssaaInputRef = useTemplateRef<{
  updateModel: (event: null, value: number) => void
}>('ssaaInputRef')

function recoverUiConfig() {
  if (!characterLocked.value) {
    CONFIG.value.system.ai_name = DEFAULT_CONFIG.system.ai_name
    onModelChange(DEFAULT_MODEL)
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
  { label: 'DeepSeek V3.2', value: 'deepseek-v3.2' },
  { label: 'Kimi K2.5', value: 'kimi-k2.5' },
  { label: 'GPT-5', value: 'gpt-5' },
  { label: 'Claude Sonnet 4.5', value: 'claude-sonnet-4-5' },
]

const PROVIDER_OPTIONS = [
  { label: '自动识别', value: 'auto', apiFormat: 'openai', baseUrl: '' },
  { label: 'DeepSeek', value: 'deepseek', apiFormat: 'openai', baseUrl: 'https://api.deepseek.com/v1' },
  { label: 'OpenAI 兼容', value: 'openai', apiFormat: 'openai', baseUrl: 'https://api.openai.com/v1' },
  { label: 'OpenRouter', value: 'openrouter', apiFormat: 'openai', baseUrl: 'https://openrouter.ai/api/v1' },
  { label: 'Anthropic', value: 'anthropic', apiFormat: 'anthropic', baseUrl: 'https://api.anthropic.com' },
  { label: 'Gemini', value: 'gemini', apiFormat: 'openai', baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { label: '自定义', value: 'custom', apiFormat: 'openai', baseUrl: '' },
]

const API_FORMAT_OPTIONS = [
  { label: 'OpenAI 兼容', value: 'openai' },
  { label: 'Anthropic 原生', value: 'anthropic' },
]

const useNagaGateway = computed({
  get() {
    return CONFIG.value.api.use_gateway
  },
  set(value: boolean) {
    CONFIG.value.api.use_gateway = value
  },
})

const llmUsesGateway = computed(() => isNagaLoggedIn.value && CONFIG.value.api.use_gateway)

function onProviderChange(value: string) {
  const provider = PROVIDER_OPTIONS.find(item => item.value === value)
  CONFIG.value.api.provider = value
  if (!provider)
    return
  CONFIG.value.api.api_format = provider.apiFormat
  if (provider.baseUrl)
    CONFIG.value.api.base_url = provider.baseUrl
}

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
const customLive2dModels = computed(() => CONFIG.value.web_live2d.custom_models)
const customLive2dName = ref('')
const customLive2dFiles = ref<File[]>([])
const customLive2dModelPath = ref('')
const customLive2dUploading = ref(false)
const customLive2dLoading = ref(false)
const customLive2dFileInputRef = ref<HTMLInputElement | null>(null)
const customLive2dReady = computed(() =>
  customLive2dName.value.trim() !== '' && customLive2dFiles.value.length > 0,
)

function formatFileSize(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0)
    return '0 KB'
  if (bytes < 1024 * 1024)
    return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function getFileRelativePath(file: File) {
  return file.webkitRelativePath || file.name
}

function pickCustomLive2dFolder() {
  customLive2dFileInputRef.value?.click()
}

function handleCustomLive2dFilesChange(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  customLive2dFiles.value = files
  const modelFiles = files
    .map(getFileRelativePath)
    .filter(path => path.toLowerCase().endsWith('.model3.json'))
  customLive2dModelPath.value = modelFiles.length === 1 ? modelFiles[0] ?? '' : ''
  if (!customLive2dName.value.trim() && customLive2dModelPath.value) {
    const parts = customLive2dModelPath.value.split('/')
    customLive2dName.value = parts.length > 1
      ? parts[parts.length - 2] ?? ''
      : parts[0]?.replace(/\.model3\.json$/i, '') ?? ''
  }
}

async function loadCustomLive2dModels() {
  if (!backendConnected.value || customLive2dLoading.value)
    return
  customLive2dLoading.value = true
  try {
    const res = await API.listCustomLive2DModels()
    CONFIG.value.web_live2d.custom_models = (res.models || []).map(toCustomLive2DModelConfig)
  }
  catch {
    // 后端旧版本或暂不可用时不影响其他设置
  }
  finally {
    customLive2dLoading.value = false
  }
}

watch(backendConnected, (connected) => {
  if (connected) {
    loadCustomLive2dModels()
  }
}, { immediate: true })

async function uploadCustomLive2dModel() {
  if (!customLive2dReady.value || customLive2dUploading.value)
    return
  customLive2dUploading.value = true
  try {
    const res = await API.uploadCustomLive2DModel({
      name: customLive2dName.value.trim(),
      files: customLive2dFiles.value,
      modelPath: customLive2dModelPath.value || undefined,
    })
    const savedModel = upsertCustomLive2DModel(res.model)
    applyCustomLive2DModel(savedModel)
    customLive2dName.value = ''
    customLive2dFiles.value = []
    customLive2dModelPath.value = ''
    if (customLive2dFileInputRef.value) {
      customLive2dFileInputRef.value.value = ''
    }
    toast.add({ severity: 'success', summary: 'Live2D 已应用', detail: res.model.name, life: 2500 })
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: '上传失败', detail: e?.response?.data?.detail || e.message, life: 4000 })
  }
  finally {
    customLive2dUploading.value = false
  }
}

async function deleteCustomLive2dModel(model: CustomLive2DModel | typeof CONFIG.value.web_live2d.custom_models[number]) {
  try {
    await API.deleteCustomLive2DModel(model.id)
    CONFIG.value.web_live2d.custom_models = CONFIG.value.web_live2d.custom_models.filter(item => item.id !== model.id)
    if (CONFIG.value.web_live2d.model.source === model.source) {
      applyLive2DModel({ ...MODELS[DEFAULT_MODEL] })
    }
    toast.add({ severity: 'info', summary: '已删除', detail: model.name, life: 2200 })
  }
  catch (e: any) {
    toast.add({ severity: 'error', summary: '删除失败', detail: e?.response?.data?.detail || e.message, life: 3000 })
  }
}

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
      <Accordion :value="accordionModel" class="pb-8" multiple>
        <!-- 大语言模型 -->
        <ConfigGroup value="llm" header="大语言模型">
          <div class="grid gap-4">
            <ConfigItem name="使用 NagaModel 网关" description="登录后可通过网关调用模型；关闭后使用下方自定义供应商配置">
              <div class="flex items-center gap-3">
                <ToggleSwitch v-model="useNagaGateway" :disabled="!isNagaLoggedIn" />
                <span v-if="isNagaLoggedIn" class="gateway-state" :class="{ active: llmUsesGateway }">
                  {{ llmUsesGateway ? '网关已启用' : '使用本地配置' }}
                </span>
                <span v-else class="gateway-state">未登录，使用本地配置</span>
              </div>
            </ConfigItem>
            <ConfigItem name="模型供应商" description="决定 API 格式与 LiteLLM 路由前缀">
              <Select
                v-model="CONFIG.api.provider"
                :options="PROVIDER_OPTIONS"
                option-label="label"
                option-value="value"
                @update:model-value="onProviderChange"
              />
            </ConfigItem>
            <ConfigItem name="API 格式" description="OpenAI 兼容接口或 Anthropic 原生 Messages API">
              <Select
                v-model="CONFIG.api.api_format"
                :options="API_FORMAT_OPTIONS"
                option-label="label"
                option-value="value"
                :disabled="CONFIG.api.provider === 'anthropic'"
              />
            </ConfigItem>
            <ConfigItem name="模型名称" description="用于对话的大语言模型">
              <div class="flex items-center gap-3">
                <Select
                  v-model="CONFIG.api.model"
                  editable
                  filter
                  :options="MODEL_OPTIONS"
                  option-label="label"
                  option-value="value"
                  placeholder="选择或输入模型名"
                />
                <span v-if="selectedModelPricing" class="model-pricing">
                  <span title="输入价格">↑{{ selectedModelPricing.inputPrice ?? '-' }}</span>
                  <span class="text-white/15">/</span>
                  <span title="输出价格">↓{{ selectedModelPricing.outputPrice ?? '-' }}</span>
                </span>
              </div>
            </ConfigItem>
            <ConfigItem name="API 地址" description="大语言模型的 API 地址">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录 ({{ nagaUser?.username }})，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.api.base_url" placeholder="https://api.example.com/v1" />
            </ConfigItem>
            <ConfigItem name="API 密钥" description="大语言模型的 API 密钥">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录 ({{ nagaUser?.username }})，无需输入</span>
              <InputText v-else v-model="CONFIG.api.api_key" type="password" />
            </ConfigItem>
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
            <ConfigItem name="控制模型" description="用于电脑控制任务的主要模型">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.computer_control.model" />
            </ConfigItem>
            <ConfigItem name="控制模型 API 地址" description="控制模型的 API 地址">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.computer_control.model_url" />
            </ConfigItem>
            <ConfigItem name="控制模型 API 密钥" description="控制模型的 API 密钥">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，无需输入</span>
              <InputText v-else v-model="CONFIG.computer_control.api_key" />
            </ConfigItem>
            <Divider class="m-1!" />
            <ConfigItem name="定位模型" description="用于元素定位和坐标识别的模型">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.computer_control.grounding_model" />
            </ConfigItem>
            <ConfigItem name="定位模型 API 地址" description="定位模型的 API 地址">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.computer_control.grounding_url" />
            </ConfigItem>
            <ConfigItem name="定位模型 API 密钥" description="定位模型的 API 密钥">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，无需输入</span>
              <InputText v-else v-model="CONFIG.computer_control.grounding_api_key" />
            </ConfigItem>
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
            <ConfigItem name="模型名称" description="用于语音识别的模型">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.voice_realtime.asr_model" />
            </ConfigItem>
            <template v-if="!llmUsesGateway">
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
                <InputText v-model="CONFIG.voice_realtime.api_key" />
              </ConfigItem>
            </template>
            <ConfigItem v-else name="API 密钥">
              <span class="naga-authed">&#10003; 已登录，无需输入</span>
            </ConfigItem>
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
            <ConfigItem name="模型名称" description="用于语音合成的模型">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.voice_realtime.tts_model" />
            </ConfigItem>
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
            <template v-if="!llmUsesGateway">
              <ConfigItem name="服务端口" description="用于语音合成的本地服务端口">
                <InputNumber v-model="CONFIG.tts.port" :min="1000" :max="65535" show-buttons />
              </ConfigItem>
              <ConfigItem name="API 密钥" description="语音合成模型的 API 密钥">
                <InputText v-model="CONFIG.tts.api_key" />
              </ConfigItem>
            </template>
            <ConfigItem v-else name="API 密钥">
              <span class="naga-authed">&#10003; 已登录，无需输入</span>
            </ConfigItem>
          </div>
        </ConfigGroup>

        <!-- 嵌入模型 -->
        <ConfigGroup value="embedding" header="嵌入模型">
          <div class="grid gap-4">
            <ConfigItem name="模型名称" description="用于向量嵌入的模型">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.embedding.model" />
            </ConfigItem>
            <ConfigItem name="API 地址" description="嵌入模型的 API 地址（留空使用主模型地址）">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，使用 NagaModel 网关</span>
              <InputText v-else v-model="CONFIG.embedding.api_base" />
            </ConfigItem>
            <ConfigItem name="API 密钥" description="嵌入模型的 API 密钥（留空使用主模型密钥）">
              <span v-if="llmUsesGateway" class="naga-authed">&#10003; 已登录，无需输入</span>
              <InputText v-else v-model="CONFIG.embedding.api_key" type="password" />
            </ConfigItem>
          </div>
        </ConfigGroup>
      </Accordion>
    </div>

    <!-- 记忆 Tab -->
    <div v-show="activeTab === 'memory'">
      <Accordion :value="accordionMemory" class="pb-8" multiple>
        <ConfigGroup value="neo4j">
          <template #header>
            <div class="w-full flex justify-between items-center -my-1.5">
              <span>{{ isCloudMode ? '云端记忆服务' : 'Neo4j 数据库' }}</span>
              <span v-if="isCloudMode" class="text-xs text-green-400 flex items-center gap-1">
                <span class="inline-block w-2 h-2 rounded-full bg-green-400" />
                已登录
              </span>
            </div>
          </template>
          <div class="grid gap-4">
            <!-- 云端模式 -->
            <template v-if="isCloudMode">
              <ConfigItem name="服务状态" description="夏园 云端记忆微服务">
                <div class="text-xs text-white/70">
                  <div>用户: {{ nagaUser?.username }}</div>
                  <div class="mt-1 text-white/40">
                    云端记忆服务已连接
                  </div>
                </div>
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
                <InputText v-model="CONFIG.grag.neo4j_password" placeholder="••••••••" />
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
            <ConfigItem layout="column" name="Live2D 模型" description="上传整套 Cubism 模型目录，或从已保存模型中切换">
              <div class="live2d-model-panel">
                <div class="builtin-live2d-row">
                  <Select
                    :options="Object.keys(MODELS)"
                    :model-value="selectedModel"
                    :disabled="characterLocked"
                    @change="(event) => onModelChange(event.value)"
                  />
                  <Button
                    size="small"
                    label="角色注册"
                    @click="configRouter.push('/market?tab=memory-skin')"
                  />
                </div>
                <div v-if="characterLocked" class="live2d-lock-hint">
                  {{ characterLockedHint }}
                </div>

                <div class="custom-live2d-uploader">
                  <input
                    ref="customLive2dFileInputRef"
                    type="file"
                    webkitdirectory
                    directory
                    multiple
                    hidden
                    @change="handleCustomLive2dFilesChange"
                  >
                  <InputText
                    v-model="customLive2dName"
                    class="min-w-0"
                    placeholder="自定义模型名称"
                  />
                  <Button
                    size="small"
                    outlined
                    :label="customLive2dFiles.length ? `${customLive2dFiles.length} 个文件` : '选择目录'"
                    @click="pickCustomLive2dFolder"
                  />
                  <Button
                    size="small"
                    label="上传并应用"
                    :disabled="!customLive2dReady"
                    :loading="customLive2dUploading"
                    @click="uploadCustomLive2dModel"
                  />
                </div>
                <div v-if="customLive2dModelPath" class="live2d-path-hint">
                  入口文件：{{ customLive2dModelPath }}
                </div>

                <div class="custom-live2d-list">
                  <div v-if="customLive2dLoading" class="custom-live2d-empty">
                    正在读取模型列表...
                  </div>
                  <div v-else-if="customLive2dModels.length === 0" class="custom-live2d-empty">
                    暂无自定义 Live2D 模型
                  </div>
                  <template v-else>
                    <div
                      v-for="model in customLive2dModels"
                      :key="model.id"
                      class="custom-live2d-item"
                      :class="{ active: CONFIG.web_live2d.model.source === model.source }"
                    >
                      <div class="custom-live2d-meta">
                        <div class="custom-live2d-name">{{ model.name }}</div>
                        <div class="custom-live2d-detail">
                          {{ model.file_count }} 个文件 · {{ formatFileSize(model.total_bytes) }}
                        </div>
                      </div>
                      <div class="custom-live2d-actions">
                        <Button
                          size="small"
                          :label="CONFIG.web_live2d.model.source === model.source ? '使用中' : '应用'"
                          :disabled="CONFIG.web_live2d.model.source === model.source"
                          @click="applyCustomLive2DModel(model)"
                        />
                        <Button
                          size="small"
                          severity="danger"
                          outlined
                          label="删除"
                          @click="deleteCustomLive2dModel(model)"
                        />
                      </div>
                    </div>
                  </template>
                </div>
              </div>
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
            <ConfigItem name="L2D 模型" :description="characterLocked ? characterLockedHint : '在上方 Live2D 模型入口切换内置或自定义模型'">
              <span class="live2d-source-preview">
                {{ CONFIG.web_live2d.model.source }}
              </span>
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

.naga-authed {
  color: #4ade80;
  font-size: 0.875rem;
  font-weight: 500;
}

.gateway-state {
  color: rgba(255, 255, 255, 0.48);
  font-size: 0.8rem;
  white-space: nowrap;
}

.gateway-state.active {
  color: #4ade80;
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

.live2d-model-panel {
  display: grid;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.builtin-live2d-row,
.custom-live2d-uploader,
.custom-live2d-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.custom-live2d-uploader {
  flex-wrap: wrap;
}

.live2d-lock-hint,
.live2d-path-hint,
.custom-live2d-empty,
.live2d-source-preview {
  color: rgba(255, 255, 255, 0.48);
  font-size: 12px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.custom-live2d-list {
  display: grid;
  gap: 0.5rem;
}

.custom-live2d-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-width: 0;
  padding: 0.65rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.custom-live2d-item.active {
  border-color: rgba(74, 222, 128, 0.42);
  background: rgba(74, 222, 128, 0.08);
}

.custom-live2d-meta {
  min-width: 0;
}

.custom-live2d-name {
  color: rgba(255, 255, 255, 0.88);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-live2d-detail {
  margin-top: 0.15rem;
  color: rgba(255, 255, 255, 0.42);
  font-size: 12px;
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
