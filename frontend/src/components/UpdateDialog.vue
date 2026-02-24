<script setup lang="ts">
import type { UpdateInfo } from '@/composables/useVersionCheck'
import { Button } from 'primevue'
import { computed } from 'vue'
import { dismissUpdate, openDownloadUrl } from '@/composables/useVersionCheck'

const props = defineProps<{
  visible: boolean
  info: UpdateInfo | null
}>()

const isForced = computed(() => props.info?.forceUpdate ?? false)
const hasResource = computed(() => !!props.info?.downloadUrl)

const fileSizeText = computed(() => {
  const size = props.info?.fileSize
  if (!size)
    return ''
  if (size >= 1024 * 1024)
    return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024)
    return `${(size / 1024).toFixed(0)} KB`
  return `${size} B`
})

function handleDownload() {
  if (props.info?.downloadUrl) {
    openDownloadUrl(props.info.downloadUrl)
  }
}

function handleClose() {
  if (!isForced.value || !hasResource.value) {
    dismissUpdate()
  }
}
</script>

<template>
  <Transition name="update-fade">
    <div v-if="visible && info" class="update-overlay">
      <div class="update-card">
        <!-- 关闭按钮：非强制更新 或 无资源可下载 时显示 -->
        <button v-if="!isForced || !hasResource" class="update-close" @click="handleClose">
          &times;
        </button>

        <!-- 有资源：正常更新弹窗 -->
        <template v-if="hasResource">
          <h2 class="update-title">
            发现新版本
          </h2>
          <div class="update-version">
            v{{ info.latestVersion }}
          </div>
          <p class="update-desc">
            {{ info.description }}
          </p>
          <div v-if="fileSizeText" class="update-size">
            文件大小: {{ fileSizeText }}
          </div>
          <div v-if="isForced" class="update-forced-hint">
            此版本为强制更新，请下载后安装
          </div>
          <Button
            label="立即下载"
            class="update-btn"
            @click="handleDownload"
          />
          <div v-if="!isForced" class="update-skip" @click="handleClose">
            稍后提醒
          </div>
        </template>

        <!-- 无资源：错误提示 -->
        <template v-else>
          <h2 class="update-title update-title--error">
            更新提示
          </h2>
          <div class="update-version">
            v{{ info.latestVersion }}
          </div>
          <p class="update-desc">
            {{ info.description }}
          </p>
          <div class="update-error">
            当前平台暂无可用安装包，请前往官网获取最新版本。
          </div>
          <div class="update-skip" @click="handleClose">
            我知道了
          </div>
        </template>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.update-overlay {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.update-card {
  position: relative;
  width: 380px;
  padding: 2rem 2.5rem;
  border: 1px solid rgba(212, 175, 55, 0.5);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.92);
  box-shadow: 0 0 40px rgba(212, 175, 55, 0.1);
  text-align: center;
}

.update-close {
  position: absolute;
  top: 0.6rem;
  right: 0.8rem;
  border: none;
  background: none;
  color: rgba(212, 175, 55, 0.4);
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  transition: color 0.2s;
}

.update-close:hover {
  color: rgba(212, 175, 55, 0.9);
}

.update-title {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.9);
  letter-spacing: 0.05em;
}

.update-title--error {
  color: #e8a44d;
}

.update-version {
  margin-bottom: 1rem;
  font-size: 1.6rem;
  font-weight: 700;
  color: rgba(212, 175, 55, 1);
}

.update-desc {
  margin: 0 0 1rem;
  font-size: 0.85rem;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.7);
  white-space: pre-line;
}

.update-size {
  margin-bottom: 0.75rem;
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.4);
}

.update-forced-hint {
  margin-bottom: 1rem;
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  background: rgba(220, 80, 60, 0.15);
  font-size: 0.8rem;
  color: #e85d5d;
}

.update-error {
  margin-bottom: 1rem;
  padding: 0.6rem 0.8rem;
  border-radius: 6px;
  background: rgba(220, 160, 60, 0.12);
  font-size: 0.85rem;
  color: #e8a44d;
  line-height: 1.5;
}

.update-btn {
  width: 100%;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.8), rgba(180, 140, 30, 0.8));
  border: none;
  color: #1a1206;
  font-weight: 600;
}

.update-btn:hover {
  background: linear-gradient(135deg, rgba(212, 175, 55, 1), rgba(180, 140, 30, 1));
}

.update-skip {
  margin-top: 0.8rem;
  font-size: 0.8rem;
  color: rgba(212, 175, 55, 0.35);
  cursor: pointer;
  transition: color 0.2s;
}

.update-skip:hover {
  color: rgba(212, 175, 55, 0.7);
}

.update-fade-enter-active {
  transition: opacity 0.3s ease;
}

.update-fade-enter-from {
  opacity: 0;
}

.update-fade-leave-active {
  transition: opacity 0.3s ease;
}

.update-fade-leave-to {
  opacity: 0;
}
</style>
