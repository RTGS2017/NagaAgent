<script setup lang="ts">
import { useStorage } from '@vueuse/core'
import { Button, Checkbox, InputText } from 'primevue'
import { useToast } from 'primevue/usetoast'
import { ref, watch } from 'vue'
import { useAuth } from '@/composables/useAuth'
import { backendConnected } from '@/utils/config'
import UserAgreement from './UserAgreement.vue'

const props = defineProps<{ visible: boolean }>()

const emit = defineEmits<{ success: [], skip: [] }>()

const toast = useToast()

const { login, register, sendVerification, getCaptcha } = useAuth()

// 'login' | 'register'
const mode = ref<'login' | 'register'>('login')

const username = useStorage('naga-login-username', '')
const email = ref('')
const password = ref('')
const verificationCode = ref('')
const errorMsg = ref('')
const successMsg = ref('')
const loading = ref(false)
const sendingCode = ref(false)
const codeSent = ref(false)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

// 协议勾选状态（持久化）
const agreementAccepted = useStorage('naga-agreement-accepted', false)
const showAgreement = ref(false)

// 验证码状态
const captchaId = ref('')
const captchaQuestion = ref('')
const captchaAnswer = ref('')
const captchaLoading = ref(false)

function resetForm() {
  // username 持久化在 localStorage，不清空
  email.value = ''
  password.value = ''
  verificationCode.value = ''
  errorMsg.value = ''
  successMsg.value = ''
  codeSent.value = false
  countdown.value = 0
  captchaAnswer.value = ''
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

async function fetchCaptcha() {
  captchaId.value = ''
  captchaQuestion.value = ''
  captchaAnswer.value = ''
  captchaLoading.value = true
  try {
    const res = await getCaptcha()
    captchaId.value = res.captchaId
    captchaQuestion.value = res.question
  }
  catch {
    // 验证码获取失败不阻塞，用户操作时再提示
  }
  finally {
    captchaLoading.value = false
  }
}

function switchToRegister() {
  resetForm()
  mode.value = 'register'
  fetchCaptcha()
}

function switchToLogin() {
  resetForm()
  mode.value = 'login'
  fetchCaptcha()
}

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  if (!captchaId.value) {
    errorMsg.value = '验证码未加载，请点击刷新'
    fetchCaptcha()
    return
  }
  if (!captchaAnswer.value) {
    errorMsg.value = '请输入验证码答案'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await login(username.value, password.value, captchaId.value, captchaAnswer.value)
    emit('success')
  }
  catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.response?.data?.message || '登录失败，请检查用户名和密码'
    // 验证码用完即失效，刷新
    fetchCaptcha()
  }
  finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!username.value || !email.value || !password.value || !verificationCode.value) {
    errorMsg.value = '请填写完整信息'
    return
  }
  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const res = await register(username.value, email.value, password.value, verificationCode.value)
    if (res.success) {
      // 注册成功且返回了 token，直接登录
      if (res.accessToken) {
        emit('success')
      }
      else {
        // 注册成功但没返回 token，切回登录页
        successMsg.value = '注册成功，请登录'
        const savedUsername = username.value
        switchToLogin()
        username.value = savedUsername
        successMsg.value = '注册成功，请登录'
      }
    }
  }
  catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '注册失败，请稍后重试'
  }
  finally {
    loading.value = false
  }
}

async function sendCode() {
  if (!username.value || !email.value) {
    errorMsg.value = '请先输入用户名和邮箱'
    return
  }
  if (!captchaId.value) {
    errorMsg.value = '验证码未加载，请点击刷新'
    fetchCaptcha()
    return
  }
  if (!captchaAnswer.value) {
    errorMsg.value = '请先输入验证码答案'
    return
  }
  sendingCode.value = true
  errorMsg.value = ''
  try {
    await sendVerification(email.value, username.value, captchaId.value, captchaAnswer.value)
    toast.add({ severity: 'success', summary: '验证码已发送', detail: '请查收邮箱', life: 3000 })
    codeSent.value = true
    countdown.value = 60
    countdownTimer = setInterval(() => {
      countdown.value -= 1
      if (countdown.value <= 0) {
        clearInterval(countdownTimer!)
        countdownTimer = null
        codeSent.value = false
      }
    }, 1000)
  }
  catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '发送验证码失败'
    // 验证码用完即失效，刷新
    fetchCaptcha()
  }
  finally {
    sendingCode.value = false
  }
}

function handleSkip() {
  emit('skip')
}

function openForgotPassword() {
  toast.add({ severity: 'info', summary: '功能开发中', detail: '密码找回功能尚未开放，请联系管理员', life: 3000 })
}

// 弹窗打开时重置到登录模式并加载验证码
watch(() => props.visible, (v) => {
  if (v) {
    mode.value = 'login'
    resetForm()
    if (backendConnected.value) {
      fetchCaptcha()
    }
  }
})

// 如果弹窗已显示但后端还没连上，等连接后再加载
const stopWatch = watch(backendConnected, (connected) => {
  if (connected && props.visible) {
    fetchCaptcha()
    stopWatch()
  }
})
</script>

<template>
  <Transition name="login-fade">
    <div v-if="visible" class="login-overlay">
      <div class="login-card">
        <!-- 登录模式 -->
        <template v-if="mode === 'login'">
          <h2 class="login-title">
            Naga 账号登录
          </h2>
          <div class="login-form">
            <InputText
              v-model="username"
              placeholder="用户名"
              class="login-input"
              @keyup.enter="handleLogin"
            />
            <InputText
              v-model="password"
              type="password"
              placeholder="密码"
              class="login-input"
              @keyup.enter="handleLogin"
            />
            <!-- 验证码 -->
            <div class="captcha-row">
              <span class="captcha-question">{{ captchaQuestion || '加载中...' }}</span>
              <InputText
                v-model="captchaAnswer"
                placeholder="答案"
                class="captcha-input"
                @keyup.enter="handleLogin"
              />
              <span class="captcha-refresh" title="换一题" @click="fetchCaptcha">&#x21bb;</span>
            </div>
            <div v-if="errorMsg" class="login-error">
              {{ errorMsg }}
            </div>
            <div v-if="successMsg" class="login-success">
              {{ successMsg }}
            </div>
            <div class="agreement-row">
              <Checkbox v-model="agreementAccepted" :binary="true" input-id="agree-login" />
              <label for="agree-login" class="agreement-label">
                我已阅读并同意
                <span class="agreement-link" @click.prevent="showAgreement = true">《用户使用协议》</span>
              </label>
            </div>
            <Button
              label="登 录"
              :loading="loading"
              :disabled="!agreementAccepted"
              class="login-btn"
              @click="handleLogin"
            />
          </div>
          <div class="login-links">
            <span class="login-link" @click="switchToRegister">注册账号</span>
            <span class="login-link" @click="openForgotPassword">忘记密码</span>
          </div>
          <div class="login-skip" @click="handleSkip">
            不登录，直接进入
          </div>
        </template>

        <!-- 注册模式 -->
        <template v-else>
          <h2 class="login-title">
            Naga 账号注册
          </h2>
          <div class="login-form">
            <InputText
              v-model="username"
              placeholder="用户名"
              class="login-input"
            />
            <InputText
              v-model="email"
              type="email"
              placeholder="邮箱"
              class="login-input"
            />
            <InputText
              v-model="password"
              type="password"
              placeholder="密码"
              class="login-input"
            />
            <!-- 验证码 -->
            <div class="captcha-row">
              <span class="captcha-question">{{ captchaQuestion || '加载中...' }}</span>
              <InputText
                v-model="captchaAnswer"
                placeholder="答案"
                class="captcha-input"
                @keyup.enter="sendCode"
              />
              <span class="captcha-refresh" title="换一题" @click="fetchCaptcha">&#x21bb;</span>
            </div>
            <div class="verification-row">
              <InputText
                v-model="verificationCode"
                placeholder="邮箱验证码"
                class="login-input flex-1"
                @keyup.enter="handleRegister"
              />
              <Button
                :label="codeSent ? `${countdown}s` : '发送验证码'"
                :loading="sendingCode"
                :disabled="codeSent"
                class="send-code-btn"
                size="small"
                @click="sendCode"
              />
            </div>
            <div v-if="errorMsg" class="login-error">
              {{ errorMsg }}
            </div>
            <div v-if="successMsg" class="login-success">
              {{ successMsg }}
            </div>
            <div class="agreement-row">
              <Checkbox v-model="agreementAccepted" :binary="true" input-id="agree-register" />
              <label for="agree-register" class="agreement-label">
                我已阅读并同意
                <span class="agreement-link" @click.prevent="showAgreement = true">《用户使用协议》</span>
              </label>
            </div>
            <Button
              label="注 册"
              :loading="loading"
              :disabled="!agreementAccepted"
              class="login-btn"
              @click="handleRegister"
            />
          </div>
          <div class="login-links">
            <span class="login-link" @click="switchToLogin">返回登录</span>
            <span class="login-link" @click="openForgotPassword">忘记密码</span>
          </div>
          <div class="login-skip" @click="handleSkip">
            不登录，直接进入
          </div>
        </template>
      </div>
    </div>
  </Transition>
  <UserAgreement v-model:visible="showAgreement" />
</template>

<style scoped>
.login-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.login-card {
  width: 360px;
  padding: 2rem 2.5rem;
  border: 1px solid rgba(212, 175, 55, 0.5);
  border-radius: 12px;
  background: rgba(20, 14, 6, 0.92);
  box-shadow: 0 0 40px rgba(212, 175, 55, 0.1);
}

.login-title {
  margin: 0 0 1.5rem;
  font-size: 1.25rem;
  font-weight: 600;
  text-align: center;
  color: rgba(212, 175, 55, 0.9);
  letter-spacing: 0.05em;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.login-input {
  width: 100%;
}

.captcha-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  background: rgba(212, 175, 55, 0.06);
  border: 1px solid rgba(212, 175, 55, 0.15);
}

.captcha-question {
  flex: 1;
  font-size: 0.9rem;
  color: rgba(212, 175, 55, 0.85);
  font-weight: 500;
  white-space: nowrap;
}

.captcha-input {
  width: 70px;
  text-align: center;
}

.captcha-refresh {
  font-size: 1.2rem;
  color: rgba(212, 175, 55, 0.5);
  cursor: pointer;
  transition: color 0.2s;
  user-select: none;
}

.captcha-refresh:hover {
  color: rgba(212, 175, 55, 0.9);
}

.verification-row {
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
}

.verification-row .flex-1 {
  flex: 1;
}

.send-code-btn {
  min-width: 100px;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.7), rgba(180, 140, 30, 0.7));
  border: none;
  color: #1a1206;
  font-weight: 500;
  font-size: 0.85rem;
}

.send-code-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.9), rgba(180, 140, 30, 0.9));
}

.send-code-btn:disabled {
  background: rgba(150, 150, 150, 0.3);
  color: rgba(255, 255, 255, 0.4);
  cursor: not-allowed;
}

.login-error {
  font-size: 0.8rem;
  color: #e85d5d;
  text-align: center;
}

.login-success {
  font-size: 0.8rem;
  color: rgba(120, 200, 120, 0.9);
  text-align: center;
}

.login-btn {
  width: 100%;
  margin-top: 0.25rem;
  background: linear-gradient(135deg, rgba(212, 175, 55, 0.8), rgba(180, 140, 30, 0.8));
  border: none;
  color: #1a1206;
  font-weight: 600;
}

.login-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(212, 175, 55, 1), rgba(180, 140, 30, 1));
}

.login-btn:disabled {
  background: rgba(150, 150, 150, 0.25);
  color: rgba(255, 255, 255, 0.35);
  cursor: not-allowed;
}

.agreement-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.25rem;
}

.agreement-label {
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  user-select: none;
}

.agreement-link {
  color: rgba(212, 175, 55, 0.85);
  cursor: pointer;
  transition: color 0.2s;
}

.agreement-link:hover {
  color: rgba(212, 175, 55, 1);
  text-decoration: underline;
}

.login-links {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 1rem;
}

.login-link {
  font-size: 0.8rem;
  color: rgba(212, 175, 55, 0.55);
  cursor: pointer;
  transition: color 0.2s;
}

.login-link:hover {
  color: rgba(212, 175, 55, 0.9);
}

.login-skip {
  margin-top: 0.6rem;
  font-size: 0.8rem;
  text-align: center;
  color: rgba(212, 175, 55, 0.35);
  cursor: pointer;
  transition: color 0.2s;
}

.login-skip:hover {
  color: rgba(212, 175, 55, 0.7);
}

.login-fade-enter-active {
  transition: opacity 0.3s ease;
}

.login-fade-enter-from {
  opacity: 0;
}

.login-fade-leave-active {
  transition: opacity 0.3s ease;
}

.login-fade-leave-to {
  opacity: 0;
}
</style>
