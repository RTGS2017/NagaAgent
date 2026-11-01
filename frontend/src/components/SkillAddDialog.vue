<script setup lang="ts">
import { Button, InputText, Select, Textarea } from 'primevue'
import { computed, ref, watch } from 'vue'

interface AgentOption {
  id: string
  name: string
  engine?: string
}

type SkillDialogConfirmPayload
  = | { mode: 'hub', name: string, source: string }
    | { mode: 'cache', name: string, sourceScope: 'cache' | 'public' | 'private', sourceAgentId?: string }
    | { mode: 'custom', name: string, content: string, scope: 'cache' | 'public' | 'private', agentId?: string }

const props = withDefaults(defineProps<{
  visible: boolean
  agents?: AgentOption[]
  initialScope?: 'cache' | 'public' | 'private'
  fixedScope?: 'cache' | 'public' | 'private'
  fixedAgentId?: string
  title?: string
  hubEnabled?: boolean
  cacheItems?: Array<{ name: string, description?: string, scope: 'cache' | 'public' | 'private', ownerAgentId?: string }>
}>(), {
  hubEnabled: false,
})

const emit = defineEmits<{
  confirm: [data: SkillDialogConfirmPayload]
  cancel: []
}>()

const importMode = ref<'cache' | 'hub' | 'custom'>('custom')
const name = ref('')
const cachedSkillKey = ref('')
const textContent = ref('')
const selectedFile = ref<File | null>(null)
const scope = ref<'cache' | 'public' | 'private'>('public')
const selectedAgentId = ref('')
const errorMsg = ref('')
const hubSource = ref('tencent-skillhub')

const scopeOptions: Array<{
  label: string
  value: 'public' | 'private'
  description: string
}> = [
  { label: '共享 Skill', value: 'public', description: '娜迦与多个干员可共用。' },
  { label: '私有 Skill', value: 'private', description: '只绑定单一干员，通常强依赖该干员的工具。' },
]

const hubSourceOptions = [
  {
    label: '腾讯 SkillHub',
    value: 'tencent-skillhub',
    description: '当前默认下载源。根据腾讯官方说明安装 SkillHub 商店时，只安装 CLI 即可。',
  },
  {
    label: 'ClawHub',
    value: 'clawhub',
    description: '通过 Naga 内置的 Node runtime 调用 npx clawhub@latest 进行安装。',
  },
]

const mode = computed<'text' | 'file' | null>(() => {
  if (textContent.value.trim())
    return 'text'
  if (selectedFile.value)
    return 'file'
  return null
})

const cacheModeAvailable = computed(() => props.fixedScope === 'private' && (props.cacheItems?.length ?? 0) > 0)
const showModeSwitch = computed(() => props.hubEnabled || cacheModeAvailable.value)
const canSubmit = computed(() => {
  if (importMode.value === 'cache')
    return !!cachedSkillKey.value
  if (!name.value.trim())
    return false
  if (importMode.value === 'hub')
    return true
  return !!mode.value
})

const cachedSkillOptions = computed(() => (props.cacheItems || []).map(item => ({
  label: item.description ? `${item.name} · ${item.description}` : item.name,
  value: `${item.scope}:${item.ownerAgentId || ''}:${item.name}`,
  item,
})))

const hubSourceGuide = computed(() => {
  if (hubSource.value === 'tencent-skillhub') {
    return {
      url: 'https://skillhub.tencent.com/#categories',
      text: '访问 https://skillhub.tencent.com/#categories 以获取详细技能清单',
    }
  }
  return {
    url: 'https://clawhub.ai/',
    text: '访问 https://clawhub.ai/ 以获取详细技能清单',
  }
})

watch(() => textContent.value, (v) => {
  if (v.trim())
    selectedFile.value = null
})

watch(() => props.visible, (visible) => {
  if (!visible)
    return
  name.value = ''
  cachedSkillKey.value = ''
  textContent.value = ''
  selectedFile.value = null
  scope.value = props.fixedScope ?? props.initialScope ?? 'public'
  selectedAgentId.value = props.fixedAgentId || ''
  importMode.value = cacheModeAvailable.value ? 'cache' : (showModeSwitch.value ? 'hub' : 'custom')
  hubSource.value = 'tencent-skillhub'
  errorMsg.value = ''
})

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file)
    return
  selectedFile.value = file
  textContent.value = ''
  const reader = new FileReader()
  reader.onload = () => {
    textContent.value = reader.result as string
    selectedFile.value = null
  }
  reader.readAsText(file)
}

function handleConfirm() {
  if (importMode.value === 'cache') {
    const selected = cachedSkillOptions.value.find(item => item.value === cachedSkillKey.value)?.item
    if (!selected) {
      errorMsg.value = '请选择一个已下载的 Skill'
      return
    }
    emit('confirm', {
      mode: 'cache',
      name: selected.name,
      sourceScope: selected.scope,
      sourceAgentId: selected.ownerAgentId,
    })
    errorMsg.value = ''
    return
  }
  if (!name.value.trim()) {
    errorMsg.value = '请输入 Skill 名称'
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
  if (!textContent.value.trim() && !selectedFile.value) {
    errorMsg.value = '请输入技能内容或选择文件'
    return
  }
  if (scope.value === 'private' && !selectedAgentId.value) {
    errorMsg.value = '私有 Skill 必须选择一个干员'
    return
  }
  emit('confirm', {
    mode: 'custom',
    name: name.value.trim(),
    content: textContent.value,
    scope: scope.value,
    agentId: scope.value === 'private' ? selectedAgentId.value : undefined,
  })
  errorMsg.value = ''
}

function handleCancel() {
  name.value = ''
  cachedSkillKey.value = ''
  textContent.value = ''
  selectedFile.value = null
  selectedAgentId.value = ''
  errorMsg.value = ''
  emit('cancel')
}
</script>

<template>
  <Transition name="dialog-fade">
    <div v-if="visible" class="dialog-overlay" @click.self="handleCancel">
      <div class="dialog-card">
        <h2 class="dialog-title">
          {{ title || '添加 Skill' }}
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
            <label class="dialog-label">
              选择已下载 Skill <span class="required">*</span>
            </label>
            <Select
              v-model="cachedSkillKey"
              :options="cachedSkillOptions"
              option-label="label"
              option-value="value"
              class="dialog-input"
              placeholder="选择一个已下载的 Skill"
            />
            <div class="dialog-hint-block">
              会把已下载的 Skill 复制到当前干员的专有 Skill 目录。
            </div>
          </template>

          <label v-if="importMode !== 'cache'" class="dialog-label">
            Skill 名称 <span class="required">*</span>
          </label>
          <InputText
            v-if="importMode !== 'cache'"
            v-model="name"
            :placeholder="importMode === 'hub' ? '例如：search' : '技能名称（将作为目录名）'"
            class="dialog-input"
          />

          <div v-if="importMode === 'hub'" class="dialog-hint-block">
            输入 Hub 中的 Skill 名称后，会直接安装到当前可用的 Skill 列表。
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
            <div class="dialog-hint-block">
              {{ hubSourceOptions.find(item => item.value === hubSource)?.description }}
            </div>
            <a
              class="dialog-link"
              :href="hubSourceGuide.url"
              target="_blank"
              rel="noreferrer"
            >
              {{ hubSourceGuide.text }}
            </a>
          </template>

          <template v-else>
            <template v-if="!fixedScope">
              <label class="dialog-label">
                Skill 范围 <span class="required">*</span>
              </label>
              <Select
                v-model="scope"
                :options="scopeOptions"
                option-label="label"
                option-value="value"
                class="dialog-input"
              />
              <div class="dialog-hint-block">
                {{ scopeOptions.find(item => item.value === scope)?.description }}
              </div>
            </template>
            <div v-else class="dialog-hint-block">
              {{ scope === 'private' ? '这个 Skill 只绑定当前干员。' : '这个 Skill 会加入共享列表。' }}
            </div>

            <template v-if="scope === 'private' && !fixedAgentId">
              <label class="dialog-label">
                绑定干员 <span class="required">*</span>
              </label>
              <Select
                v-model="selectedAgentId"
                :options="agents || []"
                option-label="name"
                option-value="id"
                class="dialog-input"
                placeholder="选择一个干员"
              />
            </template>

            <div class="content-section">
              <label class="dialog-label">
                技能内容 <span class="required">*</span>
                <span class="dialog-hint">（以下两种方式任选其一）</span>
              </label>

              <label class="dialog-label-inner">直接输入描述</label>
              <Textarea
                v-model="textContent"
                rows="6"
                placeholder="在此输入技能描述内容..."
                class="dialog-input resize-none text-xs!"
              />

              <div class="divider-row">
                <span class="divider-line" />
                <span class="divider-text">或</span>
                <span class="divider-line" />
              </div>

              <label class="dialog-label-inner">选择文件（.md / .txt）</label>
              <div class="file-row">
                <label class="file-btn" :class="{ disabled: mode === 'text' }">
                  选择文件
                  <input
                    type="file"
                    accept=".md,.txt,.markdown"
                    class="hidden"
                    :disabled="mode === 'text'"
                    @change="onFileSelect"
                  >
                </label>
                <span v-if="selectedFile" class="file-name">{{ selectedFile.name }}</span>
              </div>
            </div>
          </template>

          <div v-if="errorMsg" class="dialog-error">
            {{ errorMsg }}
          </div>
          <Button
            :label="importMode === 'hub' ? '下载并添加' : '确认导入'"
            :disabled="!canSubmit"
            class="dialog-btn"
            @click="handleConfirm"
          />
        </div>
        <div class="dialog-skip" @click="handleCancel">
          取消
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(6px);
}

.dialog-card {
  position: relative;
  z-index: 10000;
  width: 400px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 2rem 2.5rem;
  border: 1px solid rgba(212, 175, 55, 0.5);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.98);
  box-shadow: 0 0 60px rgba(0, 0, 0, 0.5), 0 0 40px rgba(212, 175, 55, 0.1);
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
  gap: 0.7rem;
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

.dialog-label-inner {
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.46);
}

.dialog-input {
  width: 100%;
}

.dialog-hint {
  margin-left: 0.2rem;
  font-size: 0.68rem;
  color: rgba(255, 255, 255, 0.35);
}

.dialog-hint-block {
  font-size: 0.74rem;
  color: rgba(255, 255, 255, 0.42);
  line-height: 1.55;
}

.dialog-link {
  font-size: 0.74rem;
  line-height: 1.55;
  color: rgba(212, 175, 55, 0.88);
  text-decoration: none;
}

.dialog-link:hover {
  color: rgba(248, 222, 159, 0.96);
  text-decoration: underline;
}

.content-section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 0.75rem;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.03);
}

.divider-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
}

.divider-text {
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.4);
}

.file-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.file-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.45rem 0.8rem;
  border-radius: 8px;
  border: 1px dashed rgba(212, 175, 55, 0.35);
  color: rgba(212, 175, 55, 0.84);
  cursor: pointer;
}

.file-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.file-name {
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.5);
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

.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.3s ease;
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
</style>
