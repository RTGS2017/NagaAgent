<script setup lang="ts">
import type { AgentEngine, AgentSettings, CharacterTemplate, McpService, SkillCatalogItem } from '@/api/core'
import type { AgentContact } from '@/utils/session'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { computed, ref, watch } from 'vue'
import API from '@/api/core'
import McpAddDialog from '@/components/McpAddDialog.vue'
import SkillAddDialog from '@/components/SkillAddDialog.vue'

const props = defineProps<{
  visible: boolean
  agent: AgentContact | null
}>()

const emit = defineEmits<{
  close: []
  updated: [settings: AgentSettings]
}>()

const loading = ref(false)
const saving = ref(false)
const errorMsg = ref('')
const characterTemplates = ref<CharacterTemplate[]>([])
const form = ref<AgentSettings>({
  id: '',
  name: '',
  engine: 'openclaw',
  characterTemplate: '',
  soulContent: '',
})
const privateSkills = ref<SkillCatalogItem[]>([])
const privateMcps = ref<McpService[]>([])
const cachedSkills = ref<SkillCatalogItem[]>([])
const cachedMcps = ref<McpService[]>([])

const showSkillDialog = ref(false)
const showMcpDialog = ref(false)
const editingMcp = ref<{
  name: string
  displayName: string
  description: string
  config: Record<string, any>
  scope: 'public' | 'private'
  agentId?: string
} | null>(null)

const isBuiltin = computed(() => !!props.agent?.builtin)
const canEditAgent = computed(() => !!props.agent && !props.agent.builtin)
const engineOptions: Array<{ label: string, value: AgentEngine, description: string }> = [
  { label: 'OpenClaw', value: 'openclaw', description: '适合网页探索、浏览器任务和复杂工具链。' },
  { label: 'NagaCore', value: 'naga-core', description: '适合直接走娜迦主后端，使用统一对话与工具调度。' },
]

async function loadAgentData() {
  if (!props.visible || !props.agent) {
    return
  }

  loading.value = true
  errorMsg.value = ''
  privateSkills.value = []
  privateMcps.value = []
  cachedSkills.value = []
  cachedMcps.value = []

  try {
    const [charactersRes, skillCatalogRes, mcpServicesRes] = await Promise.all([
      API.listCharacterTemplates().catch(() => ({ characters: [] as CharacterTemplate[] })),
      API.getSkillCatalog().catch(() => null),
      API.getMcpServices().catch(() => null),
    ])

    characterTemplates.value = charactersRes.characters || []

    if (props.agent.builtin) {
      form.value = {
        id: props.agent.id,
        name: props.agent.name,
        engine: props.agent.engine || 'naga-core',
        characterTemplate: props.agent.characterTemplate || '',
        soulContent: '',
      }
      return
    }

    const settings = await API.getAgentSettings(props.agent.id)
    form.value = {
      id: settings.id,
      name: settings.name,
      engine: settings.engine,
      characterTemplate: settings.characterTemplate || '',
      soulContent: settings.soulContent || '',
    }

    privateSkills.value = skillCatalogRes?.catalog?.privateSkills?.skills?.filter(
      (item: SkillCatalogItem) => item.ownerAgentId === props.agent?.id,
    ) || []
    cachedSkills.value = skillCatalogRes?.catalog?.localCache?.skills || []
    privateMcps.value = mcpServicesRes?.services?.filter(
      (item: McpService) => item.scope === 'private' && item.ownerAgentId === props.agent?.id,
    ) || []
    cachedMcps.value = mcpServicesRes?.services?.filter(
      (item: McpService) => item.scope === 'public' && item.source !== 'builtin',
    ) || []
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '加载干员设置失败'
  }
  finally {
    loading.value = false
  }
}

watch(() => [props.visible, props.agent?.id], () => {
  if (props.visible && props.agent) {
    void loadAgentData()
  }
}, { immediate: true })

function closeDialog() {
  if (saving.value)
    return
  emit('close')
}

async function saveAgentSettings() {
  if (!props.agent || isBuiltin.value || saving.value)
    return

  if (!form.value.name.trim()) {
    errorMsg.value = '请输入干员名称'
    return
  }
  if (!form.value.characterTemplate?.trim()) {
    errorMsg.value = '请选择一个人格模板'
    return
  }

  saving.value = true
  errorMsg.value = ''
  try {
    const settings = await API.updateAgentSettings(props.agent.id, {
      name: form.value.name.trim(),
      engine: form.value.engine,
      characterTemplate: form.value.characterTemplate,
      soulContent: form.value.soulContent || '',
    })
    form.value = {
      id: settings.id,
      name: settings.name,
      engine: settings.engine,
      characterTemplate: settings.characterTemplate || '',
      soulContent: settings.soulContent || '',
    }
    emit('updated', settings)
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '保存失败'
  }
  finally {
    saving.value = false
  }
}

function openAddPrivateSkill() {
  showSkillDialog.value = true
}

async function handlePrivateSkillConfirm(data:
  | { mode: 'hub', name: string, source: string }
  | { mode: 'cache', name: string, sourceScope: 'cache' | 'public' | 'private', sourceAgentId?: string }
  | { mode: 'custom', name: string, content: string, scope: 'cache' | 'public' | 'private', agentId?: string }) {
  if (!props.agent)
    return
  try {
    if (data.mode === 'hub') {
      await API.installHubSkill({
        name: data.name,
        scope: 'private',
        agentId: props.agent.id,
        source: data.source,
      })
    }
    else if (data.mode === 'cache') {
      await API.cloneSkill({
        name: data.name,
        sourceScope: data.sourceScope,
        sourceAgentId: data.sourceAgentId,
        targetScope: 'private',
        targetAgentId: props.agent.id,
      })
    }
    else {
      await API.importScopedSkill({
        ...data,
        scope: 'private',
        agentId: props.agent.id,
      })
    }
    showSkillDialog.value = false
    await loadAgentData()
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '导入专有 Skill 失败'
  }
}

async function deletePrivateSkill(skill: SkillCatalogItem) {
  if (!props.agent)
    return
  try {
    await API.deleteSkill(skill.name, 'private', props.agent.id)
    await loadAgentData()
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '删除专有 Skill 失败'
  }
}

function openAddPrivateMcp() {
  editingMcp.value = null
  showMcpDialog.value = true
}

function openEditPrivateMcp(service: McpService) {
  editingMcp.value = {
    name: service.name,
    displayName: service.displayName || service.name,
    description: service.description || '',
    config: service.config || {},
    scope: 'private',
    agentId: props.agent?.id,
  }
  showMcpDialog.value = true
}

async function handlePrivateMcpConfirm(data: {
  mode: 'hub'
  name: string
  source: string
} | {
  mode: 'cache'
  name: string
  displayName: string
  description: string
  config: Record<string, any>
} | {
  mode: 'custom'
  name: string
  displayName: string
  description: string
  config: Record<string, any>
  scope: 'public' | 'private'
  agentId?: string
}) {
  if (!props.agent)
    return
  try {
    if (data.mode === 'hub') {
      await API.installHubMcp({
        name: data.name,
        scope: 'private',
        agentId: props.agent.id,
        source: data.source,
      })
    }
    else if (data.mode === 'cache') {
      await API.importMcpConfig({
        name: data.name,
        config: data.config,
        displayName: data.displayName,
        description: data.description,
        scope: 'private',
        agentId: props.agent.id,
      })
    }
    else if (editingMcp.value) {
      await API.updateMcpService(data.name, {
        config: data.config,
        displayName: data.displayName,
        description: data.description,
      })
    }
    else {
      await API.importMcpConfig({
        name: data.name,
        config: data.config,
        displayName: data.displayName,
        description: data.description,
        scope: 'private',
        agentId: props.agent.id,
      })
    }
    showMcpDialog.value = false
    await loadAgentData()
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '保存专有 MCP 失败'
  }
}

async function deletePrivateMcp(service: McpService) {
  try {
    await API.deleteMcpService(service.name)
    await loadAgentData()
  }
  catch (error: any) {
    errorMsg.value = error?.response?.data?.detail || error?.message || '删除专有 MCP 失败'
  }
}
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    :header="agent ? `干员设置 · ${agent.name}` : '干员设置'"
    :style="{ width: '860px', maxWidth: 'calc(100vw - 24px)' }"
    @update:visible="value => !value && closeDialog()"
  >
    <div class="agent-settings-shell">
      <div v-if="loading" class="agent-settings-loading">
        正在加载干员设置...
      </div>

      <template v-else-if="agent">
        <div v-if="isBuiltin" class="agent-settings-banner">
          默认角色娜迦的名字、人设和底层引擎由系统托管，当前不允许在通讯录里修改。
        </div>

        <div class="agent-settings-grid">
          <section class="settings-card">
            <div class="settings-card-title">
              基础信息
            </div>
            <div class="settings-form">
              <label class="settings-label">干员名称</label>
              <InputText v-model="form.name" :disabled="!canEditAgent" />

              <label class="settings-label">人格模板</label>
              <Select
                v-model="form.characterTemplate"
                :options="characterTemplates"
                option-label="name"
                option-value="name"
                :disabled="!canEditAgent"
                placeholder="选择一个人格模板"
              />
              <div class="settings-hint">
                {{ characterTemplates.find(item => item.name === form.characterTemplate)?.bio || '选择后会重写该干员的 IDENTITY.md。' }}
              </div>

              <label class="settings-label">底层引擎</label>
              <Select
                v-model="form.engine"
                :options="engineOptions"
                option-label="label"
                option-value="value"
                :disabled="!canEditAgent"
                placeholder="选择干员引擎"
              />
              <div class="settings-hint">
                {{ engineOptions.find(item => item.value === form.engine)?.description }}
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-title">
              灵魂文档
            </div>
            <div class="settings-form">
              <Textarea
                v-model="form.soulContent"
                rows="14"
                :disabled="!canEditAgent"
                class="soul-textarea"
                placeholder="这里对应干员目录下的 SOUL.md，用于长期偏好、成长轨迹和后天形成的风格。"
              />
              <div class="settings-hint">
                {{ canEditAgent ? '保存后会写入该干员自己的 SOUL.md。' : '默认娜迦没有独立通讯录实例目录，这里暂不提供编辑。' }}
              </div>
            </div>
          </section>
        </div>

        <div v-if="canEditAgent" class="agent-settings-grid">
          <section class="settings-card">
            <div class="settings-card-head">
              <div class="settings-card-title">
                专有 Skill
              </div>
              <Button label="新增" size="small" text @click="openAddPrivateSkill" />
            </div>
            <div class="resource-list">
              <div v-for="skill in privateSkills" :key="skill.path" class="resource-item">
                <div class="resource-main">
                  <div class="resource-name">
                    {{ skill.name }}
                  </div>
                  <div class="resource-desc">
                    {{ skill.description || '暂无描述' }}
                  </div>
                </div>
                <Button label="删除" size="small" text severity="danger" @click="deletePrivateSkill(skill)" />
              </div>
              <div v-if="!privateSkills.length" class="resource-empty">
                当前没有专有 Skill。新增后会写入该干员自己的 `skills/` 目录。
              </div>
            </div>
          </section>

          <section class="settings-card">
            <div class="settings-card-head">
              <div class="settings-card-title">
                专有 MCP
              </div>
              <Button label="新增" size="small" text @click="openAddPrivateMcp" />
            </div>
            <div class="resource-list">
              <div v-for="service in privateMcps" :key="service.name" class="resource-item">
                <div class="resource-main">
                  <div class="resource-name">
                    {{ service.displayName || service.name }}
                  </div>
                  <div class="resource-desc">
                    {{ service.description || service.name }}
                  </div>
                </div>
                <div class="resource-actions">
                  <Button label="编辑" size="small" text @click="openEditPrivateMcp(service)" />
                  <Button label="删除" size="small" text severity="danger" @click="deletePrivateMcp(service)" />
                </div>
              </div>
              <div v-if="!privateMcps.length" class="resource-empty">
                当前没有专有 MCP。专有 MCP 只会暴露给这个干员。
              </div>
            </div>
          </section>
        </div>

        <div v-if="errorMsg" class="settings-error">
          {{ errorMsg }}
        </div>
      </template>
    </div>

    <template #footer>
      <div class="settings-footer">
        <Button label="关闭" text @click="closeDialog" />
        <Button v-if="canEditAgent" label="保存设置" :loading="saving" @click="saveAgentSettings" />
      </div>
    </template>
  </Dialog>

  <SkillAddDialog
    :visible="showSkillDialog"
    fixed-scope="private"
    :fixed-agent-id="agent?.id"
    :cache-items="cachedSkills"
    hub-enabled
    title="新增专有 Skill"
    @confirm="handlePrivateSkillConfirm"
    @cancel="showSkillDialog = false"
  />

  <McpAddDialog
    :visible="showMcpDialog"
    :edit-data="editingMcp"
    fixed-scope="private"
    :fixed-agent-id="agent?.id"
    :cache-items="cachedMcps"
    hub-enabled
    :title="editingMcp ? '编辑专有 MCP' : '新增专有 MCP'"
    @confirm="handlePrivateMcpConfirm"
    @cancel="showMcpDialog = false"
  />
</template>

<style scoped>
.agent-settings-shell {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.agent-settings-loading {
  padding: 1rem 0;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.6);
}

.agent-settings-banner {
  padding: 0.8rem 0.95rem;
  border-radius: 12px;
  border: 1px solid rgba(212, 175, 55, 0.22);
  background: rgba(212, 175, 55, 0.06);
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.84rem;
  line-height: 1.65;
}

.agent-settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.settings-card {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  min-width: 0;
  padding: 1rem;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.settings-card-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
}

.settings-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.settings-label {
  font-size: 0.76rem;
  color: rgba(255, 255, 255, 0.55);
}

.settings-hint {
  font-size: 0.74rem;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.42);
}

.soul-textarea {
  width: 100%;
}

.resource-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.resource-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.7rem 0.8rem;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
}

.resource-main {
  min-width: 0;
  flex: 1;
}

.resource-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.88);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resource-desc {
  margin-top: 0.18rem;
  font-size: 0.76rem;
  color: rgba(255, 255, 255, 0.45);
  line-height: 1.5;
}

.resource-actions {
  display: flex;
  align-items: center;
  gap: 0.2rem;
}

.resource-empty {
  padding: 0.8rem;
  border-radius: 10px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.38);
  font-size: 0.78rem;
  line-height: 1.6;
}

.settings-error {
  color: #ff8d8d;
  font-size: 0.82rem;
}

.settings-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

@media (max-width: 920px) {
  .agent-settings-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
