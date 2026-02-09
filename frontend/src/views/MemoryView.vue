<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import { Accordion, Button, Divider, InputNumber, InputText, Message, Slider, ToggleSwitch } from 'primevue'
import { computed, onMounted, ref } from 'vue'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import ConfigItem from '@/components/ConfigItem.vue'
import { CONFIG } from '@/utils/config'
import API from '@/api/core'

const accordionValue = useStorage('accordion-memory', ['grag'])

const memoryStats = ref<Record<string, any> | null>(null)
const testResult = ref<string | null>(null)
const testing = ref(false)

const similarityPercent = computed({
  get() {
    return CONFIG.value.grag.similarity_threshold * 100
  },
  set(value: number) {
    CONFIG.value.grag.similarity_threshold = value / 100
  },
})

async function testConnection() {
  testing.value = true
  testResult.value = null
  try {
    const res = await API.getMemoryStats()
    const stats = res.memoryStats ?? res
    if (stats.enabled === false) {
      testResult.value = `未启用: ${stats.message || '请先启用知识图谱'}`
    } else {
      memoryStats.value = stats
      testResult.value = `连接成功 (五元组: ${stats.totalQuintuples ?? 0})`
    }
  } catch (e: any) {
    testResult.value = `连接失败: ${e.message}`
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  testConnection()
})
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" multiple>
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
          <Message v-if="testResult" :severity="testResult.startsWith('连接成功') ? 'success' : 'error'">
            {{ testResult }}
          </Message>
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
      <ConfigGroup value="neo4j" header="Neo4j 数据库">
        <div class="grid gap-4">
          <ConfigItem name="连接地址" description="Neo4j 数据库连接 URI">
            <InputText v-model="CONFIG.grag.neo4j_uri" placeholder="neo4j://127.0.0.1:7687" />
          </ConfigItem>
          <ConfigItem name="用户名" description="Neo4j 数据库用户名">
            <InputText v-model="CONFIG.grag.neo4j_user" placeholder="neo4j" />
          </ConfigItem>
          <ConfigItem name="密码" description="Neo4j 数据库密码">
            <InputText v-model="CONFIG.grag.neo4j_password" placeholder="••••••••" />
          </ConfigItem>
          <Divider class="m-1!" />
          <div class="flex justify-end">
            <Button
              :label="testing ? '测试中...' : '测试连接'"
              size="small"
              :disabled="testing"
              @click="testConnection"
            />
          </div>
        </div>
      </ConfigGroup>
    </Accordion>
  </BoxContainer>
</template>
