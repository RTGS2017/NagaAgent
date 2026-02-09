<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Select, Slider } from 'primevue'
import { ref, useTemplateRef } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { CONFIG, DEFAULT_CONFIG, DEFAULT_MODEL, MODELS } from '@/utils/config'

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
  CONFIG.value.system.ai_name = DEFAULT_CONFIG.system.ai_name
  CONFIG.value.ui.user_name = DEFAULT_CONFIG.ui.user_name
  modelSelectRef.value?.updateModel(null, DEFAULT_MODEL)
  ssaaInputRef.value?.updateModel(null, DEFAULT_CONFIG.web_live2d.ssaa)
}

const accordionValue = useStorage('accordion-config', [])
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" multiple>
      <ConfigGroup value="ui">
        <template #header>
          <div class="w-full flex justify-between items-center -my-1.5">
            <span>显示设置</span>
            <Button size="small" label="恢复默认" @click.stop="recoverUiConfig" />
          </div>
        </template>
        <div class="grid gap-4">
          <ConfigItem name="AI 昵称" description="聊天窗口显示的 AI 昵称">
            <InputText v-model="CONFIG.system.ai_name" />
          </ConfigItem>
          <ConfigItem name="用户昵称" description="聊天窗口显示的用户昵称">
            <InputText v-model="CONFIG.ui.user_name" />
          </ConfigItem>
          <Divider class="m-1!" />
          <ConfigItem name="Live2D 模型">
            <Select
              ref="modelSelectRef"
              :options="Object.keys(MODELS)"
              :model-value="selectedModel"
              @change="(event) => onModelChange(event.value)"
            />
          </ConfigItem>
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
        </div>
      </ConfigGroup>
      <ConfigGroup value="portal" header="账号设置">
        <div class="grid gap-4">
          <ConfigItem name="用户名">
            <InputText v-model="CONFIG.naga_portal.username" />
          </ConfigItem>
          <ConfigItem name="用户密码">
            <InputText v-model="CONFIG.naga_portal.password" />
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
    </Accordion>
  </BoxContainer>
</template>
