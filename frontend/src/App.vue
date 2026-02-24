<script lang="ts">
// 模块级标记，HMR 重挂载时不会重置
</script>

<script setup lang="ts">
import type { FloatingState } from '@/electron.d'
import { useWindowSize } from '@vueuse/core'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { ACCESS_TOKEN, authExpired, setAuthExpiredSuppressed } from '@/api'
import BackendErrorDialog from '@/components/BackendErrorDialog.vue'
import Live2dModel from '@/components/Live2dModel.vue'
import LoginDialog from '@/components/LoginDialog.vue'
import SplashScreen from '@/components/SplashScreen.vue'
import TitleBar from '@/components/TitleBar.vue'
import UpdateDialog from '@/components/UpdateDialog.vue'
import WindowResizeHandles from '@/components/WindowResizeHandles.vue'
import { playBgm, playClickEffect, stopBgm } from '@/composables/useAudio'
import { isNagaLoggedIn, nagaUser, sessionRestored, useAuth } from '@/composables/useAuth'
import { useElectron } from '@/composables/useElectron'
import { useMusicPlayer } from '@/composables/useMusicPlayer'
import { useParallax } from '@/composables/useParallax'
import { useStartupProgress } from '@/composables/useStartupProgress'
import { checkForUpdate, showUpdateDialog, updateInfo } from '@/composables/useVersionCheck'
import { backendConnected, CONFIG } from '@/utils/config'
import { clearExpression, setExpression } from '@/utils/live2dController'
import { destroyParallax, initParallax } from '@/utils/parallax'
import FloatingView from '@/views/FloatingView.vue'

let _splashDismissed = false

const isElectron = !!window.electronAPI
const { isMaximized } = useElectron()
const isMac = window.electronAPI?.platform === 'darwin'

const showResizeHandles = computed(() => isElectron && !isFloatingMode.value && !isMaximized.value)
// macOS hiddenInset title bar is 28px, Windows/Linux custom title bar is 32px
const titleBarPadding = isElectron ? (isMac ? '28px' : '32px') : '0px'

const toast = useToast()
useMusicPlayer() // 注册全局音乐播放器，主界面 BGM 与音律坊共用

const { width, height } = useWindowSize()
const scale = computed(() => height.value / (10000 - CONFIG.value.web_live2d.model.size))

// ─── 悬浮球模式状态 ──────────────────────────
const floatingState = ref<FloatingState>('classic')
const isFloatingMode = computed(() => floatingState.value !== 'classic')

let unsubStateChange: (() => void) | undefined

// ─── 伪3D 视差 ────────────────────────────
const { tx: lightTx, ty: lightTy } = useParallax({ translateX: 40, translateY: 30, invert: true })

// ─── 启动界面状态 ───────────────────────────
const { progress, phase, isReady: _isReady, stallHint, startProgress, notifyModelReady, cleanup } = useStartupProgress()
const splashVisible = ref(!_splashDismissed)
const showMainContent = ref(_splashDismissed)
const modelReady = ref(false)
const titlePhaseDone = ref(false)

// 悬浮球模式下停止 BGM，退出悬浮球时恢复
watch(isFloatingMode, (floating) => {
  if (floating) {
    stopBgm()
  }
  else if (showMainContent.value) {
    playBgm('8.日常的小曲.mp3')
  }
})

// Live2D 居中/过渡控制
const live2dTransform = ref('')
const live2dTransformOrigin = ref('')
const live2dTransition = ref(false)

// 记录首次 model-ready 是否已处理（避免 watch 重复触发时反复设置 transform）
let initialPositionSet = false

function onModelReady(pos: { faceX: number, faceY: number }) {
  if (!modelReady.value) {
    modelReady.value = true
    notifyModelReady()
  }

  // splash 阶段：将 Live2D 面部居中到矩形框中央
  if (splashVisible.value && !initialPositionSet) {
    initialPositionSet = true
    // frame-mask 中心: left 50%, top 38% (见 SplashScreen.vue --frame-y)
    const cx = window.innerWidth * 0.5
    const cy = window.innerHeight * 0.38
    // 以面部为缩放原点，保证 scale 后面部仍居中
    live2dTransformOrigin.value = `${pos.faceX}px ${pos.faceY}px`
    live2dTransform.value = `translate(${cx - pos.faceX}px, ${cy - pos.faceY}px) scale(2.2)`
    // 开屏闭眼 + 身体静止
    setExpression({ ParamEyeLOpen: 0, ParamEyeROpen: 0, ParamBodyAngleX: 0, ParamAngleZ: 0 })
  }
}

// progress >= 50 且标题阶段结束后渐入 Live2D
const live2dShouldShow = computed(() => progress.value >= 50 && splashVisible.value && titlePhaseDone.value)

function onTitleDone() {
  titlePhaseDone.value = true
}

// ─── 登录弹窗状态 ───────────────────────────
const showLoginDialog = ref(false)

// ─── 后端错误弹窗状态 ──────────────────────────
const backendErrorVisible = ref(false)
const backendErrorLogs = ref('')

// ─── CAS 会话失效弹窗 ──────────────────────────
const authExpiredVisible = ref(false)
const { logout: doLogout } = useAuth()

watch(authExpired, (expired) => {
  if (expired && !authExpiredVisible.value) {
    authExpiredVisible.value = true
  }
})

function onAuthExpiredRelogin() {
  authExpiredVisible.value = false
  authExpired.value = false
  // 抑制在途请求的 401 再次触发弹窗，直到登录成功
  setAuthExpiredSuppressed(true)
  ACCESS_TOKEN.value = ''
  doLogout()
  showLoginDialog.value = true
}

function onAuthExpiredDismiss() {
  authExpiredVisible.value = false
  authExpired.value = false
}

function openLoginDialog() {
  showLoginDialog.value = true
}

// 提供给子组件使用
provide('openLoginDialog', openLoginDialog)

function onSplashDismiss() {
  _splashDismissed = true
  // 开机语音已在 SplashScreen 标题出现时播放，此处不再播放
  // 已登录 → 直接进入主界面；未登录 → 显示登录弹窗
  if (isNagaLoggedIn.value) {
    enterMainContent()
  }
  else {
    showLoginDialog.value = true
  }
}

function onLoginSuccess() {
  showLoginDialog.value = false
  setAuthExpiredSuppressed(false)
  toast.add({ severity: 'success', summary: '欢迎回来', detail: nagaUser.value?.username, life: 3000 })
  enterMainContent()
}

function onLoginSkip() {
  showLoginDialog.value = false
  setAuthExpiredSuppressed(false)
  enterMainContent()
}

function enterMainContent() {
  // 切换为日常 BGM（淡入淡出）
  playBgm('8.日常的小曲.mp3')
  // 启用过渡动画
  live2dTransition.value = true
  // 回到正常位置
  live2dTransform.value = ''
  live2dTransformOrigin.value = ''
  // 触发 SplashScreen 淡出
  splashVisible.value = false
  // 睁眼（平滑过渡）
  clearExpression()

  setTimeout(() => {
    showMainContent.value = true
  }, 200)

  setTimeout(() => {
    live2dTransition.value = false
    initialPositionSet = false
  }, 1500)
}

// ─── 会话自动恢复提示 ─────────────────────────
watch(sessionRestored, (restored) => {
  if (restored) {
    toast.add({ severity: 'info', summary: '已恢复登录状态', detail: nagaUser.value?.username, life: 3000 })
    // 如果登录弹窗已显示（splash 结束时 fetchMe 尚未完成），自动关闭并进入主界面
    if (showLoginDialog.value) {
      showLoginDialog.value = false
      setAuthExpiredSuppressed(false)
      enterMainContent()
    }
  }
})

onMounted(() => {
  initParallax()
  startProgress()

  // 启动 BGM（非悬浮球模式时播放）
  if (!isFloatingMode.value) {
    playBgm('9.快乐的小曲.mp3')
  }

  // 全局点击音效
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement
    if (target.closest('button, a, [role="button"], .p-button, .p-toggleswitch, .clickable')) {
      playClickEffect()
    }
  })

  // 悬浮球模式监听
  const api = window.electronAPI
  if (api) {
    api.floating.getState().then((state) => {
      floatingState.value = state
    })
    unsubStateChange = api.floating.onStateChange((state) => {
      floatingState.value = state
    })

    // 后端连接成功后，根据持久化配置自动恢复悬浮球模式
    const stopConfigWatch = watch(backendConnected, (connected) => {
      if (connected && CONFIG.value.floating.enabled) {
        api.floating.enter()
      }
      if (connected)
        stopConfigWatch()
    })
  }

  // 后端连接成功后检查版本更新
  const stopVersionWatch = watch(backendConnected, (connected) => {
    if (!connected)
      return
    stopVersionWatch()
    checkForUpdate()
  })

  // 监听后端启动失败
  if (api?.backend) {
    api.backend.onError((payload) => {
      backendErrorLogs.value = payload.logs
      backendErrorVisible.value = true
    })
  }
})

onUnmounted(() => {
  destroyParallax()
  cleanup()
  unsubStateChange?.()
})
</script>

<template>
  <!-- 悬浮球模式 -->
  <FloatingView v-if="isFloatingMode" />

  <!-- 经典模式 -->
  <template v-else>
    <TitleBar />
    <WindowResizeHandles :visible="showResizeHandles" :title-bar-height="isMac ? 28 : 32" />
    <Toast position="top-center" />
    <div class="h-full sunflower" :style="{ paddingTop: titleBarPadding }">
      <!-- Live2D 层：启动时 z-10（在 SplashScreen 遮罩之间），之后降到 -z-1 -->
      <div
        class="absolute top-0 left-0 size-full"
        :class="splashVisible ? 'z-10' : '-z-1'"
        :style="{
          transform: live2dTransform,
          transformOrigin: live2dTransformOrigin || undefined,
          transition: live2dTransition ? 'transform 1.2s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.8s ease' : 'none',
          opacity: splashVisible ? (live2dShouldShow ? 1 : 0) : 1,
        }"
      >
        <img src="/assets/light.png" alt="" class="absolute right-0 bottom-0 w-80vw h-60vw op-40 -z-1 will-change-transform" :style="{ transform: `translate(${lightTx}px, ${lightTy}px)` }">
        <Live2dModel
          v-bind="CONFIG.web_live2d.model"
          :width="width" :height="height"
          :scale="scale" :ssaa="CONFIG.web_live2d.ssaa"
          @model-ready="onModelReady"
        />
      </div>

      <!-- 主内容区域 -->
      <Transition name="fade">
        <div v-if="showMainContent" class="h-full px-1/8 py-1/12 grid-container pointer-events-none">
          <RouterView v-slot="{ Component, route }">
            <Transition :name="route.path === '/' ? 'slide-out' : 'slide-in'">
              <component
                :is="Component"
                :key="route.fullPath"
                class="grid-item size-full pointer-events-auto"
              />
            </Transition>
          </RouterView>
        </div>
      </Transition>

      <!-- 启动界面遮罩（Transition 在父级控制淡出动画） -->
      <Transition name="splash-fade">
        <SplashScreen
          v-if="splashVisible"
          :progress="progress"
          :phase="phase"
          :model-ready="modelReady"
          :stall-hint="stallHint"
          @dismiss="onSplashDismiss"
          @title-done="onTitleDone"
        />
      </Transition>

      <!-- 登录弹窗（在 SplashScreen 之上） -->
      <LoginDialog
        :visible="showLoginDialog"
        @success="onLoginSuccess"
        @skip="onLoginSkip"
      />

      <!-- 版本更新弹窗 -->
      <UpdateDialog
        :visible="showUpdateDialog"
        :info="updateInfo"
      />

      <!-- 后端启动失败弹窗 -->
      <BackendErrorDialog
        :visible="backendErrorVisible"
        :logs="backendErrorLogs"
        @update:visible="backendErrorVisible = $event"
      />

      <!-- CAS 会话失效弹窗 -->
      <Teleport to="body">
        <Transition name="fade">
          <div v-if="authExpiredVisible" class="auth-expired-overlay">
            <div class="auth-expired-card">
              <div class="auth-expired-icon">
                &#x26A0;
              </div>
              <h3 class="auth-expired-title">
                账号验证失效
              </h3>
              <p class="auth-expired-desc">
                服务器账号资源验证失效，可能是网络波动或账号已在其他设备登录。是否重新登录？
              </p>
              <div class="auth-expired-actions">
                <button class="auth-expired-btn primary" @click="onAuthExpiredRelogin">
                  重新登录
                </button>
                <button class="auth-expired-btn secondary" @click="onAuthExpiredDismiss">
                  暂时忽略
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </Teleport>
    </div>
  </template>
</template>

<style scoped>
.sunflower {
  border-image-source: url('/assets/sunflower.9.png');
  border-image-slice: 50%;
  border-image-width: 10em;
}

.grid-container {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 1fr;
}

.grid-item {
  grid-column: 1;
  grid-row: 1;
  min-height: 0;
}

.slide-in-enter-from {
  transform: translateX(-100%);
}
.slide-in-leave-to {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-in-leave-active,
.slide-in-enter-active,
.slide-out-leave-active,
.slide-out-enter-active {
  transition: all 1s ease;
}

.slide-out-enter-from {
  opacity: 0;
  transform: translate(-3%, -5%);
}

.slide-out-leave-to {
  opacity: 0;
  transform: translateX(-100%);
}

/* 主内容淡入 */
.fade-enter-active {
  transition: opacity 0.8s ease;
}
.fade-enter-from {
  opacity: 0;
}

/* SplashScreen 淡出 */
.splash-fade-leave-active {
  transition: opacity 1s ease;
}
.splash-fade-leave-to {
  opacity: 0;
}
</style>

<style>
/* Teleport 到 body 的弹窗样式（不能 scoped） */
.auth-expired-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
}

.auth-expired-card {
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  padding: 32px;
  max-width: 380px;
  text-align: center;
}

.auth-expired-icon {
  font-size: 36px;
  margin-bottom: 8px;
}

.auth-expired-title {
  color: #fff;
  font-size: 18px;
  margin: 0 0 12px;
}

.auth-expired-desc {
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 24px;
}

.auth-expired-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.auth-expired-btn {
  padding: 8px 24px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  transition: opacity 0.2s;
}

.auth-expired-btn:hover {
  opacity: 0.85;
}

.auth-expired-btn.primary {
  background: rgba(212, 175, 55, 0.9);
  color: #000;
}

.auth-expired-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
}
</style>
