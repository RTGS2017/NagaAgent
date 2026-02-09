<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

const mcpStatus = ref<McpStatus | null>(null)
const mcpError = ref('')
const mcpOpen = ref(true)

const marketItems = ref<MarketItem[]>([])
const marketLoading = ref(true)
const marketError = ref('')
const marketOpen = ref(true)
const installing = ref<string | null>(null)

async function loadMcpStatus() {
  mcpError.value = ''
  try {
    mcpStatus.value = await API.getMcpStatus()
  } catch (e: any) {
    mcpError.value = e.message || 'MCP Server 不可达'
  }
}

async function loadMarketItems() {
  marketLoading.value = true
  marketError.value = ''
  try {
    const res = await API.getMarketItems()
    marketItems.value = res.items ?? []
  } catch (e: any) {
    marketError.value = e.message || '加载失败'
  } finally {
    marketLoading.value = false
  }
}

async function installItem(itemId: string) {
  installing.value = itemId
  try {
    await API.installMarketItem(itemId)
    await loadMarketItems()
  } catch (e: any) {
    alert(`安装失败: ${e.message}`)
  } finally {
    installing.value = null
  }
}

onMounted(() => {
  loadMcpStatus()
  loadMarketItems()
})
</script>

<template>
  <BoxContainer class="w-full h-full overflow-y-auto">
    <div class="text-white">
      <h2 class="text-lg font-bold mb-4">
        技能工坊
      </h2>

      <!-- MCP Section -->
      <div class="mb-4">
        <div
          class="flex items-center justify-between cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition"
          @click="mcpOpen = !mcpOpen"
        >
          <span class="font-bold text-sm">MCP 工具服务</span>
          <span class="text-white/30 text-xs">{{ mcpOpen ? '▼' : '▶' }}</span>
        </div>
        <div v-show="mcpOpen" class="mt-2 pl-2">
          <div v-if="mcpError" class="text-red-400 text-sm">
            {{ mcpError }}
          </div>
          <div v-else-if="mcpStatus" class="grid grid-cols-4 gap-2">
            <div class="box p-2 text-center">
              <div class="text-xs text-white/40">
                状态
              </div>
              <div class="text-sm font-bold text-green-400">
                {{ mcpStatus.server }}
              </div>
            </div>
            <div class="box p-2 text-center">
              <div class="text-xs text-white/40">
                总任务
              </div>
              <div class="text-sm font-bold">
                {{ mcpStatus.tasks.total }}
              </div>
            </div>
            <div class="box p-2 text-center">
              <div class="text-xs text-white/40">
                活跃
              </div>
              <div class="text-sm font-bold text-blue-400">
                {{ mcpStatus.tasks.active }}
              </div>
            </div>
            <div class="box p-2 text-center">
              <div class="text-xs text-white/40">
                已完成
              </div>
              <div class="text-sm font-bold">
                {{ mcpStatus.tasks.completed }}
              </div>
            </div>
          </div>
          <div v-else class="text-white/40 text-sm">
            加载中...
          </div>
        </div>
      </div>

      <!-- Skill Market Section -->
      <div>
        <div
          class="flex items-center justify-between cursor-pointer p-2 bg-white/5 rounded hover:bg-white/10 transition"
          @click="marketOpen = !marketOpen"
        >
          <span class="font-bold text-sm">技能仓库</span>
          <span class="text-white/30 text-xs">{{ marketOpen ? '▼' : '▶' }}</span>
        </div>
        <div v-show="marketOpen" class="mt-2">
          <div v-if="marketLoading" class="text-white/50 text-sm pl-2">
            加载中...
          </div>
          <div v-else-if="marketError" class="text-red-400 text-sm pl-2">
            {{ marketError }}
          </div>
          <div v-else class="grid gap-2">
            <div
              v-for="item in marketItems" :key="item.id"
              class="box p-3 flex items-center justify-between"
            >
              <div class="flex-1 min-w-0">
                <div class="font-bold text-sm">
                  {{ item.title }}
                </div>
                <div class="text-xs text-white/50 truncate">
                  {{ item.description }}
                </div>
              </div>
              <div class="ml-3 shrink-0">
                <span v-if="item.installed" class="text-green-400 text-sm font-bold">
                  已安装
                </span>
                <button
                  v-else-if="installing === item.id"
                  class="px-3 py-1 bg-white/10 rounded text-xs text-white/50 cursor-wait"
                  disabled
                >
                  安装中...
                </button>
                <button
                  v-else
                  class="px-3 py-1 bg-white/10 hover:bg-white/20 rounded text-xs transition"
                  :disabled="!item.enabled"
                  @click="installItem(item.id)"
                >
                  安装
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </BoxContainer>
</template>
