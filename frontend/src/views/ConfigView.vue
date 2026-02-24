<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Select, Slider, Textarea, ToggleSwitch } from 'primevue'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, useTemplateRef, watch } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { audioSettings, effectFileOptions, wakeVoiceOptions } from '@/composables/useAudio'
import { nagaUser } from '@/composables/useAuth'
import { CONFIG, DEFAULT_CONFIG, DEFAULT_MODEL, MODELS, SYSTEM_PROMPT } from '@/utils/config'
import { trackingCalibration } from '@/utils/live2dController'

// 当 active_character 有值时，AI昵称/Live2D模型/系统提示词由角色文件管理，不可手动修改
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

const accordionValue = useStorage('accordion-config', [])

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

// 开机自启动（仅 Electron）
const autoLaunchEnabled = ref(false)
const isElectron = !!window.electronAPI

onMounted(async () => {
  if (isElectron) {
    autoLaunchEnabled.value = await window.electronAPI!.autoLaunch.get()
  }
})

async function onAutoLaunchChange(value: boolean) {
  if (isElectron) {
    await window.electronAPI!.autoLaunch.set(value)
    autoLaunchEnabled.value = value
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
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" class="pb-8" multiple>
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
      <ConfigGroup value="character" header="角色档案">
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
      <ConfigGroup value="audio" header="音乐设置">
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
  </BoxContainer>
</template>
