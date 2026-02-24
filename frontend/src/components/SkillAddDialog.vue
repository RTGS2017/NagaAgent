<script setup lang="ts">
import { Button, InputText, Textarea } from 'primevue'
import { computed, ref, watch } from 'vue'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ confirm: [data: { name: string, content: string }], cancel: [] }>()

const name = ref('')
const textContent = ref('')
const selectedFile = ref<File | null>(null)
const errorMsg = ref('')

const mode = computed<'text' | 'file' | null>(() => {
  if (textContent.value.trim())
    return 'text'
  if (selectedFile.value)
    return 'file'
  return null
})

const canSubmit = computed(() => name.value.trim() && mode.value)

watch(() => textContent.value, (v) => {
  if (v.trim())
    selectedFile.value = null
})

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    selectedFile.value = file
    textContent.value = ''
    // Read file content for preview
    const reader = new FileReader()
    reader.onload = () => {
      textContent.value = reader.result as string
      selectedFile.value = null // treat as text after reading
    }
    reader.readAsText(file)
  }
}

function handleConfirm() {
  if (!name.value.trim()) {
    errorMsg.value = '请输入技能名称'
    return
  }
  if (!textContent.value.trim() && !selectedFile.value) {
    errorMsg.value = '请输入技能内容或选择文件'
    return
  }
  emit('confirm', { name: name.value.trim(), content: textContent.value })
  errorMsg.value = ''
}

function handleCancel() {
  name.value = ''
  textContent.value = ''
  selectedFile.value = null
  errorMsg.value = ''
  emit('cancel')
}
</script>

<template>
  <Transition name="dialog-fade">
    <div v-if="visible" class="dialog-overlay" @click.self="handleCancel">
      <div class="dialog-card">
        <h2 class="dialog-title">
          导入自定义技能
        </h2>
        <div class="dialog-form">
          <!-- 名称 -->
          <label class="dialog-label">
            技能名称 <span class="required">*</span>
          </label>
          <InputText
            v-model="name"
            placeholder="技能名称（将作为目录名）"
            class="dialog-input"
          />

          <!-- 内容区：框起来 -->
          <div class="content-section">
            <label class="dialog-label">
              技能内容 <span class="required">*</span>
              <span class="dialog-hint">（以下两种方式任选其一）</span>
            </label>

            <!-- 描述内容在上 -->
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

            <!-- 选择文件在下 -->
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

          <div v-if="errorMsg" class="dialog-error">
            {{ errorMsg }}
          </div>
          <Button
            label="确认导入"
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
  gap: 0.6rem;
}

.dialog-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
}

.dialog-label-inner {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 0.15rem;
}

.dialog-hint {
  font-size: 0.65rem;
  color: rgba(255, 255, 255, 0.3);
  margin-left: 0.25rem;
}

.required {
  color: #e85d5d;
  margin-left: 2px;
}

.content-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.dialog-input {
  width: 100%;
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

.file-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.file-btn {
  display: inline-flex;
  align-items: center;
  padding: 0.35rem 0.75rem;
  border: 1px dashed rgba(212, 175, 55, 0.4);
  border-radius: 6px;
  font-size: 0.75rem;
  color: rgba(212, 175, 55, 0.7);
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}

.file-btn:hover:not(.disabled) {
  border-color: rgba(212, 175, 55, 0.8);
  color: rgba(212, 175, 55, 1);
}

.file-btn.disabled {
  opacity: 0.35;
  pointer-events: none;
}

.file-name {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.divider-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 0.15rem 0;
}

.divider-line {
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
}

.divider-text {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.3);
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
