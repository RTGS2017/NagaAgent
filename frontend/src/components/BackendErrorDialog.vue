<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'

const props = defineProps<{
  visible: boolean
  logs: string
}>()

defineEmits<{ 'update:visible': [value: boolean] }>()

const toast = useToast()

async function copyLogs() {
  try {
    await navigator.clipboard.writeText(props.logs)
    toast.add({ severity: 'success', summary: '已复制到剪贴板', life: 2000 })
  }
  catch {
    toast.add({ severity: 'error', summary: '复制失败', detail: '请手动选中日志文本复制', life: 3000 })
  }
}
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    header="后端启动失败"
    :closable="false"
    :style="{ width: '640px' }"
    @update:visible="$emit('update:visible', $event)"
  >
    <p class="mb-3 text-sm op-70">
      后端进程异常退出，以下是最近的日志输出：
    </p>
    <div class="log-container">
      <pre class="log-content">{{ logs }}</pre>
    </div>

    <div class="mt-4 text-xs op-60">
      <p>如需帮助，可通过以下方式反馈：</p>
      <ul class="mt-1 ml-4 list-disc">
        <li>B站：<b>柏斯阔落</b></li>
        <li>QQ频道：<b>nagaagent1</b></li>
      </ul>
    </div>

    <template #footer>
      <Button label="复制全部日志" icon="pi pi-copy" severity="secondary" @click="copyLogs" />
      <Button label="关闭" icon="pi pi-times" @click="$emit('update:visible', false)" />
    </template>
  </Dialog>
</template>

<style scoped>
.log-container {
  max-height: 320px;
  overflow: auto;
  background: var(--p-surface-900, #111);
  border-radius: 8px;
  padding: 12px;
}

.log-content {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--p-surface-200, #ccc);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Fira Code', 'Cascadia Code', 'JetBrains Mono', monospace;
}
</style>
