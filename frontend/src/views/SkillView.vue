<script setup lang="ts">
import type { MarketItem } from '@/api/core'
import { useStorage } from '@vueuse/core'
import { Accordion } from 'primevue'
import { computed, ref } from 'vue'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'
import ConfigGroup from '@/components/ConfigGroup.vue'
import McpAddDialog from '@/components/McpAddDialog.vue'
import SkillAddDialog from '@/components/SkillAddDialog.vue'

interface McpService {
  name: string
  displayName: string
  description: string
  source: 'builtin' | 'mcporter'
  available: boolean
  enabled: boolean
  config?: Record<string, any>
}

const accordionValue = useStorage('accordion-skill', ['mcp', 'skills'])

// ── MCP 服务 ──
const mcpServices = ref<McpService[]>([])
const mcpLoading = ref(true)
const showMcpDialog = ref(false)
const editingMcp = ref<{ name: string, displayName: string, description: string, config: Record<string, any> } | null>(null)

const mcpEnabledCount = computed(() => mcpServices.value.filter(s => s.enabled).length)
const mcpTotalCount = computed(() => mcpServices.value.length)

async function loadMcpServices() {
  mcpLoading.value = true
  try {
    const res = await API.getMcpServices()
    mcpServices.value = res.services ?? []
  }
  catch {
    mcpServices.value = []
  }
  finally {
    mcpLoading.value = false
  }
}
loadMcpServices()

function openAddMcp() {
  editingMcp.value = null
  showMcpDialog.value = true
}

function openEditMcp(svc: McpService) {
  if (svc.source === 'builtin')
    return
  editingMcp.value = {
    name: svc.name,
    displayName: svc.displayName,
    description: svc.description,
    config: svc.config || {},
  }
  showMcpDialog.value = true
}

async function onMcpConfirm(data: { name: string, displayName: string, description: string, config: Record<string, any> }) {
  try {
    if (editingMcp.value) {
      await API.updateMcpService(data.name, {
        config: data.config,
        displayName: data.displayName,
        description: data.description,
      })
    }
    else {
      await API.importMcpConfig(data.name, data.config)
      // 导入后立即设置 displayName / description
      if (data.displayName !== data.name || data.description) {
        await API.updateMcpService(data.name, {
          displayName: data.displayName,
          description: data.description,
        }).catch(() => {})
      }
    }
    showMcpDialog.value = false
    await loadMcpServices()
  }
  catch (e: any) {
    // eslint-disable-next-line no-alert
    alert(`操作失败: ${e.message}`)
  }
}

async function toggleMcpEnabled(svc: McpService) {
  if (svc.source === 'builtin')
    return
  const newEnabled = !svc.enabled
  svc.enabled = newEnabled
  try {
    await API.updateMcpService(svc.name, { enabled: newEnabled })
  }
  catch {
    svc.enabled = !newEnabled
  }
}

async function deleteMcp(svc: McpService) {
  if (svc.source === 'builtin')
    return
  try {
    await API.deleteMcpService(svc.name)
    mcpServices.value = mcpServices.value.filter(s => s.name !== svc.name)
  }
  catch (e: any) {
    // eslint-disable-next-line no-alert
    alert(`删除失败: ${e.message}`)
  }
}

// ── 技能仓库 ──
const skills = ref<MarketItem[]>([])
const skillsLoading = ref(true)
const installing = ref<string | null>(null)
const showSkillDialog = ref(false)

API.getMarketItems().then((res) => {
  skills.value = res.items ?? []
}).catch(() => {}).finally(() => {
  skillsLoading.value = false
})

async function installItem(item: MarketItem) {
  installing.value = item.id
  try {
    await API.installMarketItem(item.id)
    item.installed = true
  }
  catch (e: any) {
    // eslint-disable-next-line no-alert
    alert(`安装失败: ${e.message}`)
  }
  finally {
    installing.value = null
  }
}

async function onSkillConfirm(data: { name: string, content: string }) {
  try {
    await API.importCustomSkill(data.name, data.content)
    showSkillDialog.value = false
    skillsLoading.value = true
    API.getMarketItems().then((res) => {
      skills.value = res.items ?? []
    }).catch(() => {}).finally(() => {
      skillsLoading.value = false
    })
  }
  catch (e: any) {
    // eslint-disable-next-line no-alert
    alert(`导入失败: ${e.message}`)
  }
}
</script>

<template>
  <BoxContainer class="text-sm">
    <Accordion :value="accordionValue" class="pb-8" multiple>
      <!-- MCP 工具服务 -->
      <ConfigGroup value="mcp" header="MCP 工具服务">
        <div class="grid gap-2 min-w-0 overflow-hidden">
          <!-- 计数摘要 -->
          <div v-if="!mcpLoading && mcpServices.length > 0" class="mcp-summary">
            已配置 {{ mcpTotalCount }} 个 MCP 服务器 · 已启用 {{ mcpEnabledCount }} 个
          </div>

          <div v-if="mcpLoading" class="text-white/40 text-xs py-2">
            检查可用性...
          </div>
          <template v-else>
            <div v-for="svc in mcpServices" :key="svc.name" class="mcp-item min-w-0" :class="{ 'mcp-disabled': !svc.enabled }">
              <div class="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                <!-- 开关 -->
                <button
                  class="mcp-toggle"
                  :class="{ 'mcp-toggle-on': svc.enabled, 'mcp-toggle-builtin': svc.source === 'builtin' }"
                  :title="svc.source === 'builtin' ? '内置服务（始终启用）' : (svc.enabled ? '点击禁用' : '点击启用')"
                  @click="toggleMcpEnabled(svc)"
                >
                  <span class="mcp-toggle-dot" />
                </button>
                <div class="min-w-0 flex-1 overflow-hidden">
                  <div class="flex items-center gap-1.5">
                    <span class="font-bold text-sm text-white truncate">{{ svc.displayName }}</span>
                    <span v-if="svc.source === 'builtin'" class="mcp-badge builtin">内置</span>
                    <span v-else class="mcp-badge external">外部</span>
                  </div>
                  <div v-if="svc.description" class="text-xs op-40 truncate mt-0.5">{{ svc.description }}</div>
                </div>
              </div>
              <!-- 操作按钮（仅外部服务） -->
              <div v-if="svc.source !== 'builtin'" class="flex items-center gap-1 shrink-0 ml-2">
                <button class="mcp-action-btn" title="编辑" @click="openEditMcp(svc)">
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" /><path d="m15 5 4 4" /></svg>
                </button>
                <button class="mcp-action-btn mcp-action-delete" title="删除" @click="deleteMcp(svc)">
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" /><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" /></svg>
                </button>
              </div>
            </div>
            <div v-if="mcpServices.length === 0" class="text-white/40 text-xs py-2">
              暂无 MCP 服务
            </div>
          </template>
          <button class="add-btn" @click="openAddMcp">
            +
          </button>
        </div>
      </ConfigGroup>

      <!-- 技能仓库 -->
      <ConfigGroup value="skills" header="技能仓库">
        <div class="grid gap-3 min-w-0 overflow-hidden">
          <div v-if="skillsLoading" class="text-white/40 text-xs py-2">
            加载中...
          </div>
          <template v-else>
            <div v-for="item in skills" :key="item.id" class="skill-item min-w-0">
              <div class="flex-1 min-w-0 overflow-hidden">
                <div class="font-bold text-sm text-white truncate">{{ item.title }}</div>
                <div class="text-xs op-50 truncate">{{ item.description }}</div>
              </div>
              <div class="ml-3 shrink-0">
                <span v-if="item.installed" class="text-green-400 text-xs font-bold">已安装</span>
                <button
                  v-else-if="installing === item.id"
                  class="px-2 py-1 bg-white/10 rounded text-xs op-50 cursor-wait"
                  disabled
                >
                  安装中...
                </button>
                <button
                  v-else
                  class="px-2 py-1 bg-white/10 hover:bg-white/20 rounded text-xs transition"
                  @click="installItem(item)"
                >
                  安装
                </button>
              </div>
            </div>
          </template>
          <button class="add-btn" @click="showSkillDialog = true">
            +
          </button>
        </div>
      </ConfigGroup>
    </Accordion>

    <!-- Dialogs -->
    <McpAddDialog
      :visible="showMcpDialog"
      :edit-data="editingMcp"
      @confirm="onMcpConfirm"
      @cancel="showMcpDialog = false"
    />
    <SkillAddDialog
      :visible="showSkillDialog"
      @confirm="onSkillConfirm"
      @cancel="showSkillDialog = false"
    />
  </BoxContainer>
</template>

<style scoped>
.mcp-summary {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.35);
  padding: 0 0.25rem;
}

.mcp-item {
  display: flex;
  align-items: center;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.mcp-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.mcp-item.mcp-disabled {
  opacity: 0.45;
}

/* Toggle switch */
.mcp-toggle {
  position: relative;
  width: 28px;
  height: 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.15);
  border: none;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  padding: 0;
}

.mcp-toggle-on {
  background: rgba(212, 175, 55, 0.7);
}

.mcp-toggle-builtin {
  opacity: 0.5;
  cursor: default;
}

.mcp-toggle-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  transition: transform 0.2s;
}

.mcp-toggle-on .mcp-toggle-dot {
  transform: translateX(12px);
}

/* Badges */
.mcp-badge {
  font-size: 0.6rem;
  padding: 0 0.3rem;
  border-radius: 3px;
  line-height: 1.4;
  font-weight: 600;
  flex-shrink: 0;
}

.mcp-badge.builtin {
  color: rgba(74, 222, 128, 0.8);
  background: rgba(74, 222, 128, 0.1);
}

.mcp-badge.external {
  color: rgba(96, 165, 250, 0.8);
  background: rgba(96, 165, 250, 0.1);
}

/* Action buttons */
.mcp-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.mcp-action-btn:hover {
  color: rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.08);
}

.mcp-action-delete:hover {
  color: #e85d5d;
  background: rgba(232, 93, 93, 0.1);
}

.skill-item {
  display: flex;
  align-items: center;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  transition: background 0.2s;
}

.skill-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 0.5rem;
  border: 1px dashed rgba(212, 175, 55, 0.35);
  border-radius: 8px;
  background: transparent;
  color: rgba(212, 175, 55, 0.6);
  font-size: 1.25rem;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}

.add-btn:hover {
  border-color: rgba(212, 175, 55, 0.7);
  color: rgba(212, 175, 55, 1);
  background: rgba(212, 175, 55, 0.06);
}
</style>
