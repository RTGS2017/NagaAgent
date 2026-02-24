<script setup lang="ts">
import type { MemoryStats } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { isNagaLoggedIn, nagaUser } from '@/composables/useAuth'
import { CONFIG } from '@/utils/config'

const accordionValue = useStorage('accordion-memory', ['grag'])

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
    <Accordion :value="accordionValue" class="pb-8" multiple>
      <ConfigGroup value="grag">
        <template #header>
          <div class="w-full flex justify-between items-center -my-1.5">
            <span>知识图谱</span>
            <label class="flex items-center gap-4">
              启用
              <ToggleSwitch v-model="CONFIG.grag.enabled" size="small" @click.stop />
            </label>
          </div>
        </template>
        <div class="grid gap-4">
          <ConfigItem name="自动提取" description="自动从对话中提取五元组知识">
            <ToggleSwitch v-model="CONFIG.grag.auto_extract" />
          </ConfigItem>
          <ConfigItem name="上下文长度" description="最近对话窗口大小">
            <InputNumber v-model="CONFIG.grag.context_length" :min="1" :max="20" show-buttons />
          </ConfigItem>
          <ConfigItem name="相似度阈值" description="RAG 知识检索匹配阈值">
            <InputNumber v-model="similarityPercent" :min="0" :max="100" suffix="%" show-buttons />
          </ConfigItem>
        </div>
      </ConfigGroup>
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
          <!-- 云端模式：显示连接状态 -->
          <template v-if="isCloudMode">
            <ConfigItem name="服务状态" description="NagaMemory 云端记忆微服务">
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
          <!-- 本地模式：显示 Neo4j 配置 -->
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
  </BoxContainer>
</template>
