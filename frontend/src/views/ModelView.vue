<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import { Accordion, Divider, InputNumber, InputText, Message, Select, ToggleSwitch } from 'primevue'
import { computed } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { CONFIG } from '@/utils/config'

const accordionValue = useStorage('accordion-model', ['asr'])

const vad_percent = computed({
  get() {
    return CONFIG.value.voice_realtime.vad_threshold * 100
  },
  set(value) {
    CONFIG.value.voice_realtime.vad_threshold = value / 100
  },
})

const ASR_PROVIDERS = {
  qwen: '通义千问',
  openai: 'OpenAI',
  local: 'FunASR',
}

const TTS_VOICES = {
  'zh-CN-XiaoyiNeural': '晓伊',
  'zh-CN-YunxiNeural': '云溪',
  'zh-CN-XiaoxiaoNeural': '小萱',
  'en-US-JennyNeural': 'Jenny',
  'en-US-GuyNeural': 'Guy',
}
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" multiple>
      <ConfigGroup value="llm" header="大语言模型">
        <div class="grid gap-4">
          <ConfigItem name="大语言模型" description="用于对话的大语言模型">
            <InputText v-model="CONFIG.api.model" />
          </ConfigItem>
          <ConfigItem name="大语言模型 API 地址" description="大语言模型的 API 地址">
            <InputText v-model="CONFIG.api.base_url" />
          </ConfigItem>
          <ConfigItem name="大语言模型 API 密钥" description="大语言模型的 API 的密钥">
            <InputText v-model="CONFIG.api.api_key" />
          </ConfigItem>
        </div>
      </ConfigGroup>
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
            <InputText v-model="CONFIG.computer_control.model" />
          </ConfigItem>
          <ConfigItem name="控制模型 API 地址" description="控制模型的 API 地址">
            <InputText v-model="CONFIG.computer_control.model_url" />
          </ConfigItem>
          <ConfigItem name="控制模型 API 密钥" description="控制模型的 API 密钥">
            <InputText v-model="CONFIG.computer_control.api_key" />
          </ConfigItem>
          <Divider class="m-1!" />
          <ConfigItem name="定位模型" description="用于元素定位和坐标识别的模型">
            <InputText v-model="CONFIG.computer_control.grounding_model" />
          </ConfigItem>
          <ConfigItem name="定位模型 API 地址" description="定位模型的 API 地址">
            <InputText v-model="CONFIG.computer_control.grounding_url" />
          </ConfigItem>
          <ConfigItem name="定位模型 API 密钥" description="定位模型的 API 密钥">
            <InputText v-model="CONFIG.computer_control.grounding_api_key" />
          </ConfigItem>
        </div>
      </ConfigGroup>
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
          <ConfigItem name="语音识别模型" description="用于语音识别的模型">
            <InputText v-model="CONFIG.voice_realtime.model" />
          </ConfigItem>
          <ConfigItem name="语音识别模型提供者" description="语音识别模型的提供者">
            <Select v-model="CONFIG.voice_realtime.provider" :options="Object.keys(ASR_PROVIDERS)">
              <template #option="{ option }">
                {{ ASR_PROVIDERS[option as keyof typeof ASR_PROVIDERS] }}
              </template>
              <template #value="{ value }">
                {{ ASR_PROVIDERS[value as keyof typeof ASR_PROVIDERS] }}
              </template>
            </Select>
          </ConfigItem>
          <ConfigItem
            v-if="CONFIG.voice_realtime.provider !== 'local'"
            name="语音识别模型 API 密钥" description="语音识别模型的 API 密钥"
          >
            <InputText v-model="CONFIG.voice_realtime.api_key" />
          </ConfigItem>
          <Message v-else severity="error">
            暂不支持 ASR 本地模型
          </Message>
          <ConfigItem name="静音检测阈值" description="VAD 静音检测灵敏度">
            <InputNumber v-model="vad_percent" :min="0" :max="100" suffix="%" show-buttons />
          </ConfigItem>
        </div>
      </ConfigGroup>
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
          <ConfigItem name="语音合成模型声线" description="语音合成模型的声线">
            <Select v-model="CONFIG.tts.default_voice" :options="Object.keys(TTS_VOICES)">
              <template #option="{ option }">
                {{ TTS_VOICES[option as keyof typeof TTS_VOICES] }}
              </template>
              <template #value="{ value }">
                {{ TTS_VOICES[value as keyof typeof TTS_VOICES] }}
              </template>
            </Select>
          </ConfigItem>
          <ConfigItem name="语音合成模型端口" description="用于语音合成的模型端口">
            <InputNumber v-model="CONFIG.tts.port" :min="1000" :max="65535" show-buttons />
          </ConfigItem>
          <ConfigItem name="语音合成模型 API 密钥" description="语音合成模型的 API 密钥">
            <InputText v-model="CONFIG.tts.api_key" />
          </ConfigItem>
        </div>
      </ConfigGroup>
    </Accordion>
  </BoxContainer>
</template>
