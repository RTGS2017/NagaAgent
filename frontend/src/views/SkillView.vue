<script lang="ts">
import { Listbox } from 'primevue'
import { ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'

interface MarketItem {
  id: string
  title: string
  description: string
  skillName: string
  installed: boolean
  enabled: boolean
  installType: string
}

interface McpStatus {
  server: string
  tasks: { total: number; active: number; completed: number; failed: number }
}

const skills = ref<MarketItem[]>([])
const mcpStatus = ref<McpStatus | null>(null)
const mcpError = ref('')
const installing = ref<string | null>(null)

API.getMarketItems().then((res) => {
  skills.value = res.items ?? []
}).catch(() => {})

API.getMcpStatus().then((res) => {
  mcpStatus.value = res
}).catch((e: any) => {
  mcpError.value = e.message || 'MCP 不可达'
})

async function installItem(item: MarketItem) {
  installing.value = item.id
  try {
    await API.installMarketItem(item.id)
    item.installed = true
  } catch (e: any) {
    alert(`安装失败: ${e.message}`)
  } finally {
    installing.value = null
  }
}
</script>

<script setup lang="ts">
</script>

<template>
  <BoxContainer>
    <div class="h-full flex flex-col gap-4">
      <div class="font-bold text-xl text-white">
        技能工坊
      </div>

      <!-- MCP Status -->
      <div class="text-white">
        <div class="text-sm font-bold text-white/70 mb-2">
          MCP 工具服务
        </div>
        <div v-if="mcpError" class="text-red-400 text-xs">
          {{ mcpError }}
        </div>
        <div v-else-if="mcpStatus" class="grid grid-cols-4 gap-2">
          <div class="box p-2 text-center">
            <div class="text-xs text-white/40">状态</div>
            <div class="text-sm font-bold text-green-400">{{ mcpStatus.server }}</div>
          </div>
          <div class="box p-2 text-center">
            <div class="text-xs text-white/40">总任务</div>
            <div class="text-sm font-bold">{{ mcpStatus.tasks.total }}</div>
          </div>
          <div class="box p-2 text-center">
            <div class="text-xs text-white/40">活跃</div>
            <div class="text-sm font-bold text-blue-400">{{ mcpStatus.tasks.active }}</div>
          </div>
          <div class="box p-2 text-center">
            <div class="text-xs text-white/40">已完成</div>
            <div class="text-sm font-bold">{{ mcpStatus.tasks.completed }}</div>
          </div>
        </div>
        <div v-else class="text-white/40 text-xs">加载中...</div>
      </div>

      <!-- Skill Market -->
      <div class="text-white flex-1 overflow-hidden flex flex-col">
        <div class="text-sm font-bold text-white/70 mb-2">
          技能仓库
        </div>
        <div class="overflow-hidden flex-1">
          <Listbox
            :options="skills"
            option-label="title"
            class="size-full flex! flex-col"
            scroll-height="100%"
            filter
          >
            <template #option="{ option }">
              <div class="flex items-center justify-between w-full">
                <div class="flex-1 min-w-0">
                  <div class="font-bold text-sm">{{ option.title }}</div>
                  <div class="text-xs op-50 truncate">{{ option.description }}</div>
                </div>
                <div class="ml-3 shrink-0">
                  <span v-if="option.installed" class="text-green-400 text-xs font-bold">已安装</span>
                  <button
                    v-else-if="installing === option.id"
                    class="px-2 py-1 bg-white/10 rounded text-xs op-50 cursor-wait"
                    disabled
                  >安装中...</button>
                  <button
                    v-else
                    class="px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs transition"
                    @click.stop="installItem(option)"
                  >安装</button>
                </div>
              </div>
            </template>
          </Listbox>
        </div>
      </div>
    </div>
  </BoxContainer>
</template>
