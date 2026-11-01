<script setup lang="ts">
import { Button, InputText, Textarea } from 'primevue'
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'

interface AgentOption {
  id: string
  name: string
}

type McpDialogConfirmPayload
  = | { mode: 'hub', name: string, source: string }
    | {
      mode: 'cache'
      name: string
      displayName: string
      description: string
      config: Record<string, any>
    }
    | {
      mode: 'custom'
      name: string
      displayName: string
      description: string
      config: Record<string, any>
      scope: 'public' | 'private'
      agentId?: string
    }

const props = withDefaults(defineProps<{
  visible: boolean
  editData?: {
    name: string
    displayName: string
    description: string
    config: Record<string, any>
    scope?: 'public' | 'private'
    agentId?: string
  } | null
  agents?: AgentOption[]
  initialScope?: 'public' | 'private'
  fixedScope?: 'public' | 'private'
  fixedAgentId?: string
  title?: string
  hubEnabled?: boolean
  cacheItems?: Array<{ name: string, displayName?: string, description?: string, config?: Record<string, any> }>
}>(), {
  hubEnabled: false,
})

const emit = defineEmits<{
  confirm: [data: McpDialogConfirmPayload]
  cancel: []
}>()

const importMode = ref<'cache' | 'hub' | 'custom'>('custom')
const name = ref('')
const cachedMcpKey = ref('')
const displayName = ref('')
const description = ref('')
const jsonText = ref('')
const errorMsg = ref('')
const showExtra = ref(false)
const scope = ref<'public' | 'private'>('public')
const selectedAgentId = ref('')
const hubSource = ref('mcp.so')

const scopeOptions: Array<{ label: string, value: 'public' | 'private', description: string }> = [
  { label: '通用 MCP', value: 'public', description: '配置后会进入全局 MCP 列表，并做预热。' },
  { label: '专有 MCP', value: 'private', description: '只给单个干员使用，不会暴露给其他干员。' },
]

const hubSourceOptions = [
  {
    label: 'mcp.so',
    value: 'mcp.so',
    description: '访问 mcp.so 搜索你需要的 MCP 名称。这里会抓取对应详情页底部的 JSON 配置。',
  },
]

const isEdit = computed(() => !!props.editData)
const cacheModeAvailable = computed(() => props.fixedScope === 'private' && (props.cacheItems?.length ?? 0) > 0)
const showModeSwitch = computed(() => (props.hubEnabled || cacheModeAvailable.value) && !isEdit.value)
const canSubmit = computed(() => {
  if (importMode.value === 'cache')
    return !!cachedMcpKey.value
  if (!name.value.trim())
    return false
  if (importMode.value === 'hub')
    return true
  return !!jsonText.value.trim()
})

const cachedMcpOptions = computed(() => (props.cacheItems || []).map(item => ({
  label: item.description ? `${item.displayName || item.name} · ${item.description}` : (item.displayName || item.name),
  value: item.name,
  item,
})))

watch(() => props.visible, (visible) => {
  if (!visible)
    return
  if (props.editData) {
    importMode.value = 'custom'
    name.value = props.editData.name
    displayName.value = props.editData.displayName || props.editData.name
    description.value = props.editData.description || ''
    jsonText.value = JSON.stringify(props.editData.config || {}, null, 2)
    showExtra.value = !!props.editData.description
    scope.value = props.fixedScope || props.editData.scope || props.initialScope || 'public'
    selectedAgentId.value = props.fixedAgentId || props.editData.agentId || ''
  }
  else {
    importMode.value = cacheModeAvailable.value ? 'cache' : (showModeSwitch.value ? 'hub' : 'custom')
    name.value = ''
    cachedMcpKey.value = ''
    displayName.value = ''
    description.value = ''
    jsonText.value = ''
    showExtra.value = false
    scope.value = props.fixedScope || props.initialScope || 'public'
    selectedAgentId.value = props.fixedAgentId || ''
    hubSource.value = 'mcp.so'
  }
  errorMsg.value = ''
})

function handleConfirm() {
  if (importMode.value === 'cache') {
    const selected = cachedMcpOptions.value.find(item => item.value === cachedMcpKey.value)?.item
    if (!selected || !selected.config) {
      errorMsg.value = '请选择一个可复制的 MCP'
      return
    }
    emit('confirm', {
      mode: 'cache',
      name: selected.name,
      displayName: selected.displayName || selected.name,
      description: selected.description || '',
      config: selected.config,
    })
    errorMsg.value = ''
    return
  }
  if (!name.value.trim()) {
    errorMsg.value = importMode.value === 'hub' ? '请输入 MCP 名称' : '请输入 MCP 标题'
    return
  }
  if (importMode.value === 'hub') {
    emit('confirm', {
      mode: 'hub',
      name: name.value.trim(),
      source: hubSource.value,
    })
    errorMsg.value = ''
    return
  }
  if (!jsonText.value.trim()) {
    errorMsg.value = '请输入 JSON 配置'
    return
  }
  if (scope.value === 'private' && !selectedAgentId.value) {
    errorMsg.value = '专有 MCP 必须绑定一个干员'
    return
  }
  try {
    const config = JSON.parse(jsonText.value)
    emit('confirm', {
      mode: 'custom',
      name: name.value.trim(),
      displayName: displayName.value.trim() || name.value.trim(),
      description: description.value.trim(),
      config,
      scope: scope.value,
      agentId: scope.value === 'private' ? selectedAgentId.value : undefined,
    })
    errorMsg.value = ''
  }
  catch {
    errorMsg.value = 'JSON 格式无效'
  }
}

function handleCancel() {
  name.value = ''
  cachedMcpKey.value = ''
  displayName.value = ''
  description.value = ''
  jsonText.value = ''
  selectedAgentId.value = ''
  errorMsg.value = ''
  emit('cancel')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="dialog-overlay" @click.self="handleCancel">
        <div class="dialog-card">
          <h2 class="dialog-title">
            {{ title || (isEdit ? '编辑 MCP 服务' : '添加 MCP 服务') }}
          </h2>
          <div class="dialog-form">
            <div v-if="showModeSwitch" class="mode-switch">
              <button
                v-if="cacheModeAvailable"
                type="button"
                class="mode-switch-btn"
                :class="{ active: importMode === 'cache' }"
                @click="importMode = 'cache'"
              >
                缓存
              </button>
              <button
                v-if="props.hubEnabled"
                type="button"
                class="mode-switch-btn"
                :class="{ active: importMode === 'hub' }"
                @click="importMode = 'hub'"
              >
                从 Hub 下载
              </button>
              <button
                type="button"
                class="mode-switch-btn"
                :class="{ active: importMode === 'custom' }"
                @click="importMode = 'custom'"
              >
                自定义导入
              </button>
            </div>

            <template v-if="importMode === 'cache'">
              <label class="dialog-label">选择已下载 MCP</label>
              <Select
                v-model="cachedMcpKey"
                :options="cachedMcpOptions"
                option-label="label"
                option-value="value"
                class="dialog-input"
                placeholder="选择一个可复制的 MCP"
              />
              <div class="dialog-hint">
                会把已下载的 MCP 配置复制到当前干员的专有 MCP 列表。
              </div>
            </template>

            <label v-if="importMode !== 'cache'" class="dialog-label">
              {{ importMode === 'hub' ? 'MCP 名称' : 'MCP 标题（唯一标识）' }}
            </label>
            <InputText
              v-if="importMode !== 'cache'"
              v-model="name"
              :disabled="isEdit"
              :placeholder="importMode === 'hub' ? '例如 fetch，或直接贴 https://mcp.so/server/... 完整链接' : '如 firecrawl-mcp'"
              class="dialog-input"
              :class="{ 'op-50': isEdit }"
            />

            <div v-if="importMode === 'hub'" class="dialog-hint">
              输入 mcp.so 上搜到的 MCP 名称。系统会先按名称抓取；如果失败，请改传完整链接。
            </div>

            <template v-if="importMode === 'hub'">
              <label class="dialog-label">下载源</label>
              <Select
                v-model="hubSource"
                :options="hubSourceOptions"
                option-label="label"
                option-value="value"
                class="dialog-input"
              />
              <div class="dialog-hint">
                {{ hubSourceOptions.find(item => item.value === hubSource)?.description }}
              </div>
              <a
                class="dialog-link"
                href="https://mcp.so"
                target="_blank"
                rel="noreferrer"
              >
                访问 https://mcp.so 搜索自己需要的 MCP 名称
              </a>
            </template>

            <template v-else>
              <template v-if="!fixedScope">
                <label class="dialog-label">MCP 范围</label>
                <Select
                  v-model="scope"
                  :options="scopeOptions"
                  option-label="label"
                  option-value="value"
                  class="dialog-input"
                />
                <div class="dialog-hint">
                  {{ scopeOptions.find(item => item.value === scope)?.description }}
                </div>
              </template>
              <div v-else class="dialog-hint">
                {{ scopeOptions.find(item => item.value === scope)?.description }}
              </div>

              <template v-if="scope === 'private' && !fixedAgentId">
                <label class="dialog-label">绑定干员</label>
                <Select
                  v-model="selectedAgentId"
                  :options="agents || []"
                  option-label="name"
                  option-value="id"
                  class="dialog-input"
                  placeholder="选择一个干员"
                />
              </template>

              <div class="extra-toggle" @click="showExtra = !showExtra">
                <span class="extra-arrow">{{ showExtra ? '▾' : '▸' }}</span>
                <span>附加信息</span>
              </div>
              <div v-if="showExtra" class="extra-section">
                <label class="dialog-label">显示名称</label>
                <InputText
                  v-model="displayName"
                  placeholder="显示名称（可选）"
                  class="dialog-input"
                />
                <label class="dialog-label mt-2">描述</label>
                <InputText
                  v-model="description"
                  placeholder="简短描述（可选）"
                  class="dialog-input"
                />
              </div>

              <label class="dialog-label">JSON 配置</label>
              <Textarea
                v-model="jsonText"
                rows="8"
                placeholder="{\n  &quot;command&quot;: &quot;npx&quot;,\n  &quot;args&quot;: [&quot;-y&quot;, &quot;@mcp/server&quot;],\n  &quot;type&quot;: &quot;stdio&quot;\n}"
                class="dialog-input resize-none font-mono text-xs!"
              />
            </template>

            <div v-if="errorMsg" class="dialog-error">
              {{ errorMsg }}
            </div>
          </div>
          <Button
            :label="isEdit ? '保存' : (importMode === 'hub' ? '下载并添加' : '确认添加')"
            :disabled="!canSubmit"
            class="dialog-btn"
            @click="handleConfirm"
          />
        </div>
        <div class="dialog-skip" @click="handleCancel">
          取消
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
}

.dialog-card {
  position: relative;
  z-index: 10000;
  width: 420px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 2rem 2.5rem;
  border: 1px solid rgba(212, 175, 55, 0.5);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 60px rgba(0, 0, 0, 0.5), 0 0 40px rgba(212, 175, 55, 0.1);
}

.dialog-card::-webkit-scrollbar {
  width: 8px;
}

.dialog-card::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 4px;
}

.dialog-card::-webkit-scrollbar-thumb {
  background: rgba(212, 175, 55, 0.4);
  border-radius: 4px;
}

.dialog-card::-webkit-scrollbar-thumb:hover {
  background: rgba(212, 175, 55, 0.6);
}

.dialog-title {
  margin: 0 0 1.5rem;
  font-size: 1.25rem;
  font-weight: 600;
  text-align: center;
  color: rgba(212, 175, 55, 0.9);
  letter-spacing: 0.05em;
}

.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.mode-switch {
  display: inline-flex;
  gap: 0.35rem;
  padding: 0.3rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.mode-switch-btn {
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.78rem;
  font-weight: 700;
  padding: 0.42rem 0.85rem;
  border-radius: 999px;
  cursor: pointer;
}

.mode-switch-btn.active {
  background: rgba(212, 175, 55, 0.14);
  color: rgba(248, 222, 159, 0.96);
}

.dialog-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
}

.dialog-input {
  width: 100%;
}

.dialog-hint {
  font-size: 0.74rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.42);
}

.dialog-link {
  font-size: 0.74rem;
  line-height: 1.5;
  color: rgba(212, 175, 55, 0.88);
  text-decoration: none;
}

.dialog-link:hover {
  color: rgba(248, 222, 159, 0.96);
  text-decoration: underline;
}

.dialog-error {
  font-size: 0.8rem;
  color: #e85d5d;
  text-align: center;
}

.dialog-btn {
  width: 100%;
  margin-top: 0.25rem;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.8), rgba(180, 140, 30, 0.8));
  border: none;
  color: #1a1206;
  font-weight: 600;
}

.dialog-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(212, 175, 55, 1), rgba(180, 140, 30, 1));
}

.dialog-skip {
  margin-top: 1rem;
  font-size: 0.8rem;
  text-align: center;
  color: rgba(212, 175, 55, 0.45);
  cursor: pointer;
  transition: color 0.2s;
}

.dialog-skip:hover {
  color: rgba(212, 175, 55, 0.8);
}

.extra-toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  user-select: none;
  padding: 0.15rem 0;
}

.extra-toggle:hover {
  color: rgba(255, 255, 255, 0.7);
}

.extra-arrow {
  font-size: 0.6rem;
}

.extra-section {
  padding-left: 0.5rem;
  border-left: 1px solid rgba(255, 255, 255, 0.08);
}

.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.3s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
</style>
