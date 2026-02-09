<script setup lang="ts">
import { useElectron } from '../composables/useElectron'

const { isElectron, isMaximized, isMac, minimize, maximize, close } = useElectron()
</script>

<template>
  <div v-if="isElectron" class="title-bar">
    <!-- Mac: traffic lights on left, drag fills rest -->
    <div v-if="isMac" class="mac-controls">
      <button class="mac-btn mac-close" title="关闭" @click="close">
        <svg width="6" height="6" viewBox="0 0 6 6"><path d="M0 0l6 6M6 0L0 6" stroke="currentColor" stroke-width="1.2" /></svg>
      </button>
      <button class="mac-btn mac-minimize" title="最小化" @click="minimize">
        <svg width="8" height="2" viewBox="0 0 8 2"><rect width="8" height="1.5" rx="0.5" fill="currentColor" /></svg>
      </button>
      <button class="mac-btn mac-maximize" :title="isMaximized ? '还原' : '最大化'" @click="maximize">
        <svg width="6" height="6" viewBox="0 0 6 6"><path d="M0 1.5V6h4.5M6 4.5V0H1.5" stroke="currentColor" stroke-width="1.2" fill="none" /></svg>
      </button>
    </div>
    <div class="drag-region" />
    <!-- Windows/Linux: controls on right -->
    <div v-if="!isMac" class="window-controls">
      <button class="control-btn" title="最小化" @click="minimize">
        <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor" /></svg>
      </button>
      <button class="control-btn" :title="isMaximized ? '还原' : '最大化'" @click="maximize">
        <svg v-if="isMaximized" width="10" height="10" viewBox="0 0 10 10"><path d="M2 0v2H0v8h8V8h2V0H2zm6 8H1V3h7v5zM9 1v6h-1V2H3V1h6z" fill="currentColor" /></svg>
        <svg v-else width="10" height="10" viewBox="0 0 10 10"><rect x="0" y="0" width="10" height="10" stroke="currentColor" stroke-width="1" fill="none" /></svg>
      </button>
      <button class="control-btn close-btn" title="关闭" @click="close">
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 0L0 1l4 4-4 4 1 1 4-4 4 4 1-1-4-4 4-4-1-1-4 4z" fill="currentColor" /></svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.title-bar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 32px;
  display: flex;
  align-items: center;
  z-index: 9999;
  background: linear-gradient(to bottom, rgba(17, 9, 1, 0.85), rgba(17, 9, 1, 0.4));
}

.drag-region {
  flex: 1;
  height: 100%;
  -webkit-app-region: drag;
}

/* ── Mac traffic-light buttons ── */
.mac-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 12px;
  height: 100%;
  -webkit-app-region: no-drag;
}

.mac-btn {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: transparent;
  transition: color 0.15s;
}

.mac-close {
  background: #ff5f57;
}

.mac-minimize {
  background: #febc2e;
}

.mac-maximize {
  background: #28c840;
}

.title-bar:hover .mac-btn {
  color: rgba(0, 0, 0, 0.5);
}

/* ── Windows / Linux buttons ── */
.window-controls {
  display: flex;
  height: 100%;
  -webkit-app-region: no-drag;
}

.control-btn {
  width: 46px;
  height: 32px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.15s;
}

.control-btn:hover {
  background-color: rgba(255, 255, 255, 0.1);
  color: white;
}

.close-btn:hover {
  background-color: #e81123;
  color: white;
}
</style>
