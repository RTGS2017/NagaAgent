<script setup lang="ts">
import type { MemoryStats } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, Select, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { isNagaLoggedIn, nagaUser } from '@/composables/useAuth'
import { CONFIG } from '@/utils/config'

const accordionValue = useStorage('accordion-memory', [])

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

onMounted(() => {
  testConnection()
})
</script>

<template>
  <BoxContainer class="text-sm">
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
            已登录 <strong>{{ nagaUser?.username }}</strong>，所有模型请求通过 NagaModel 网关转发
          </template>
          <template v-else>
            未登录，需手动配置各模型的 API 地址和密钥
          </template>
        </div>
      </div>
    </div>

    <Accordion :value="accordionValue" class="pb-8" multiple>
      <!-- 大语言模型 -->
      <ConfigGroup value="llm" header="大语言模型">
        <div class="grid gap-4">
          <ConfigItem name="模型名称" description="用于对话的大语言模型">
            <InputText v-model="CONFIG.api.model" />
          </ConfigItem>
          <template v-if="isNagaLoggedIn">
            <ConfigItem name="连接状态" description="API 地址与密钥由网关自动管理">
              <span class="naga-authed">&#10003; NagaModel 网关已连接</span>
            </ConfigItem>
          </template>
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

      <!-- 云端记忆服务 / Neo4j -->
      <ConfigGroup value="neo4j" :header="isCloudMode ? '云端记忆服务' : 'Neo4j 数据库'">
        <div class="grid gap-4">
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
  </BoxContainer>
</template>

<style scoped>
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
</style>
