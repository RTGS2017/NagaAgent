<script setup lang="ts">
import { Divider, InputText, Select, ToggleSwitch } from 'primevue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import API from '@/api/core'
import ConfigItem from '@/components/ConfigItem.vue'
import { backendConnected, CONFIG } from '@/utils/config'

import { parseQqBindingTarget } from '@/utils/qqNotification'

const FEISHU_TARGET_OPTIONS = [
  { label: '发给个人', value: 'open_id' },
  { label: '发到群聊', value: 'chat_id' },
]

const activeTutorial = ref<'feishu' | 'qq' | null>(null)
const toast = useToast()
const qqSendingVerification = ref(false)
const qqSubmittingBinding = ref(false)
const qqVerificationFeedback = ref('')
const qqTestingNotification = ref(false)
const qqTestFeedback = ref('')
const qqCaptchaId = ref('')
const qqCaptchaQuestion = ref('')
const qqCaptchaImageData = ref('')
const qqCaptchaType = ref<'image' | 'math'>('math')
const qqCaptchaAnswer = ref('')
const qqCaptchaLoading = ref(false)
const qqBindingEditorOpened = ref(false)
const qqVerificationCodeInput = ref('')

const feishuTargetValue = computed({
  get() {
    return CONFIG.value.notifications.feishu.recipient_type === 'chat_id'
      ? CONFIG.value.notifications.feishu.recipient_chat_id
      : CONFIG.value.notifications.feishu.recipient_open_id
  },
  set(value: string) {
    if (CONFIG.value.notifications.feishu.recipient_type === 'chat_id') {
      CONFIG.value.notifications.feishu.recipient_chat_id = value
    }
    else {
      CONFIG.value.notifications.feishu.recipient_open_id = value
    }
  },
})

const feishuReady = computed(() => {
  const channelEnabled = CONFIG.value.openclaw.feishu.enabled
  const notifyEnabled = CONFIG.value.notifications.feishu.enabled
  const hasApp = !!CONFIG.value.openclaw.feishu.app_id.trim() && !!CONFIG.value.openclaw.feishu.app_secret.trim()
  const hasTarget = !!feishuTargetValue.value.trim()
  return channelEnabled && notifyEnabled && hasApp && hasTarget
})

const feishuStatusText = computed(() => {
  if (feishuReady.value) {
    const targetLabel = CONFIG.value.notifications.feishu.recipient_type === 'chat_id'
      ? 'chat_id'
      : 'open_id'
    const reportMode = CONFIG.value.notifications.feishu.deliver_full_report ? '完整报告' : '完成摘要'
    return `探索完成后会通过 OpenClaw 飞书通道回传${reportMode}到 ${targetLabel}: ${feishuTargetValue.value.trim()}`
  }
  if (CONFIG.value.notifications.feishu.enabled) {
    return '飞书通知已开启，但还缺少 App ID / App Secret / 接收对象中的至少一项。'
  }
  return '关闭时仅在应用内保留探索结果，不会向飞书回传。'
})

const qqBindingTarget = computed({
  get() {
    return CONFIG.value.notifications.qq.binding_target
  },
  set(value: string) {
    CONFIG.value.notifications.qq.binding_target = value
  },
})
const qqBinding = computed(() => parseQqBindingTarget(qqBindingTarget.value))
const qqNumberValid = computed(() => qqBinding.value.isValid)
const qqVerificationVisible = computed(() => qqBindingEditorOpened.value && !qqBinding.value.isEmpty)
const qqVerificationReady = computed(() => {
  const qq = CONFIG.value.notifications.qq
  return qq.binding_verified && qq.binding_verified_email === qqBinding.value.normalizedEmail
})
const qqConfigured = computed(() => {
  return CONFIG.value.notifications.qq.enabled && qqNumberValid.value && qqVerificationReady.value
})
const qqVerificationHint = computed(() => {
  if (!qqBinding.value.isValid) {
    return '只有纯数字 QQ 号或纯数字@qq.com 才会通过客户端校验。'
  }
  return `将按 ${qqBinding.value.normalizedEmail} 验证 QQ 邮箱。`
})

const qqStatusText = computed(() => {
  const qq = CONFIG.value.notifications.qq
  if (!qq.enabled) {
    return '关闭时仅在应用内保留探索结果，不会向 QQ 机器人发送回调。'
  }
  if (qqBinding.value.isEmpty) {
    return '填好纯数字 QQ 号或纯数字@qq.com 后，再填写邮箱验证码，探索完成才会自动走 QQ 机器人回调。'
  }
  if (!qqNumberValid.value) {
    return qqBinding.value.errorMessage
  }
  if (!qqVerificationReady.value) {
    return `QQ 绑定目标已识别为 ${qqBinding.value.normalizedQq}，还需要填写 ${qqBinding.value.normalizedEmail} 收到的验证码。`
  }
  if (qqConfigured.value) {
    return `探索完成后会通过 Undefined QQ机器人在群里 @${qqBinding.value.normalizedQq}。当前已绑定 ${CONFIG.value.notifications.qq.binding_verified_email}。`
  }
  return '填好 QQ 绑定信息后，探索完成会自动走 QQ 机器人回调。'
})

const tutorialTitle = computed(() => {
  if (activeTutorial.value === 'feishu')
    return '飞书通知配置教程'
  if (activeTutorial.value === 'qq')
    return 'QQ 通知配置教程'
  return ''
})

function openTutorial(kind: 'feishu' | 'qq') {
  activeTutorial.value = kind
}

watch(() => CONFIG.value.notifications.feishu.enabled, (enabled) => {
  CONFIG.value.openclaw.feishu.enabled = enabled
}, { immediate: true })

watch(qqBinding, (next, prev) => {
  const qq = CONFIG.value.notifications.qq
  qq.user_qq = next.isValid ? next.normalizedQq : ''
  qq.qq_email = next.isValid ? next.normalizedEmail : ''
  qqCaptchaAnswer.value = ''

  if (next.isEmpty) {
    qqVerificationCodeInput.value = ''
    qqCaptchaId.value = ''
    qqCaptchaQuestion.value = ''
    qqCaptchaImageData.value = ''
    qqCaptchaType.value = 'math'
    return
  }

  if (!next.isValid) {
    qqVerificationCodeInput.value = ''
    qqCaptchaId.value = ''
    qqCaptchaQuestion.value = ''
    qqCaptchaImageData.value = ''
    qqCaptchaType.value = 'math'
    return
  }

  if (prev && prev.normalizedEmail !== next.normalizedEmail) {
    qqVerificationCodeInput.value = ''
  }
}, { immediate: true })

watch([qqVerificationVisible, backendConnected], ([visible, connected]) => {
  if (visible && connected && !qqCaptchaLoading.value && !qqCaptchaId.value) {
    void fetchQqCaptcha()
  }
}, { immediate: true })

watch([() => CONFIG.value.notifications.qq.enabled, backendConnected], ([enabled, connected]) => {
  if (enabled && connected) {
    void refreshQqBindingStatus()
  }
}, { immediate: true })

function openQqBindingEditor() {
  qqBindingEditorOpened.value = true
}

async function refreshQqBindingStatus() {
  try {
    const res = await API.authGetQqEmailBinding()
    const binding = res.binding
    CONFIG.value.notifications.qq.binding_verified = !!binding
    CONFIG.value.notifications.qq.binding_verified_email = binding?.qqEmail || ''
    if (!qqBindingTarget.value && binding?.qqEmail) {
      qqBindingTarget.value = binding.qqEmail
    }
  }
  catch {
    // ignore binding probe failures
  }
}

async function fetchQqCaptcha() {
  qqCaptchaLoading.value = true
  qqCaptchaId.value = ''
  qqCaptchaQuestion.value = ''
  qqCaptchaImageData.value = ''
  qqCaptchaType.value = 'math'
  qqCaptchaAnswer.value = ''
  try {
    const res = await API.authGetCaptcha('image')
    qqCaptchaId.value = res.captchaId
    qqCaptchaQuestion.value = res.question || ''
    qqCaptchaImageData.value = res.imageData || ''
    qqCaptchaType.value = res.imageData ? 'image' : 'math'
  }
  catch {
    qqVerificationFeedback.value = '验证码加载失败，请点击刷新后重试'
  }
  finally {
    qqCaptchaLoading.value = false
  }
}

async function sendQqVerificationCode() {
  if (qqSendingVerification.value || !qqBinding.value.isValid)
    return
  if (!qqCaptchaId.value) {
    qqVerificationFeedback.value = '验证码未加载，请刷新后重试'
    void fetchQqCaptcha()
    return
  }
  if (!qqCaptchaAnswer.value.trim()) {
    qqVerificationFeedback.value = '请先填写验证码答案'
    return
  }
  qqSendingVerification.value = true
  qqVerificationFeedback.value = ''
  try {
    const res = await API.authSendQqVerification(
      qqBinding.value.normalizedEmail,
      qqCaptchaId.value,
      qqCaptchaAnswer.value.trim(),
    )
    qqVerificationFeedback.value = res.message || `验证码已发送到 ${qqBinding.value.normalizedEmail}`
    toast.add({ severity: 'success', summary: '验证码已发送', detail: qqVerificationFeedback.value, life: 3000 })
    await fetchQqCaptcha()
  }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '发送验证码失败'
    qqVerificationFeedback.value = detail
    toast.add({ severity: 'error', summary: '发送失败', detail, life: 4000 })
    await fetchQqCaptcha()
  }
  finally {
    qqSendingVerification.value = false
  }
}

async function submitQqEmailBinding() {
  if (qqSubmittingBinding.value)
    return
  if (!qqBinding.value.isValid) {
    qqVerificationFeedback.value = '请先填写有效的 QQ 号或 QQ 邮箱'
    return
  }
  if (!qqVerificationCodeInput.value.trim()) {
    qqVerificationFeedback.value = '请先填写邮箱验证码'
    return
  }
  qqSubmittingBinding.value = true
  try {
    const res = await API.authBindQqEmail(
      qqBinding.value.normalizedEmail,
      qqVerificationCodeInput.value.trim(),
    )
    await refreshQqBindingStatus()
    CONFIG.value.notifications.qq.email_verification_code = ''
    qqVerificationCodeInput.value = ''
    qqVerificationFeedback.value = res.message || 'QQ 邮箱绑定成功'
    toast.add({ severity: 'success', summary: '绑定成功', detail: qqVerificationFeedback.value, life: 2500 })
  }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || '提交失败'
    qqVerificationFeedback.value = detail
    toast.add({ severity: 'error', summary: '提交失败', detail, life: 3500 })
  }
  finally {
    qqSubmittingBinding.value = false
  }
}

async function sendQqTestNotification() {
  if (qqTestingNotification.value || !qqBinding.value.isValid)
    return
  qqTestingNotification.value = true
  qqTestFeedback.value = ''
  try {
    const res = await API.testQqNotification(qqBinding.value.normalizedQq)
    qqTestFeedback.value = `测试消息已提交，状态：${res.deliveryStatus}`
    toast.add({ severity: 'success', summary: '测试已发送', detail: qqTestFeedback.value, life: 3000 })
  }
  catch (e: any) {
    const detail = e?.response?.data?.detail || e?.response?.data?.message || e?.message || 'QQ 通知测试失败'
    qqTestFeedback.value = detail
    toast.add({ severity: 'error', summary: '测试失败', detail, life: 4000 })
  }
  finally {
    qqTestingNotification.value = false
  }
}
</script>

<template>
  <div class="pb-8 flex flex-col gap-4">
    <section class="notification-card">
      <div class="notification-card-header">
        <div class="notification-title-row">
          <div class="notification-card-title">
            QQ 通知
          </div>
          <button class="help-button" type="button" @click="openTutorial('qq')">
            ?
          </button>
        </div>
        <div class="notification-card-subtitle">
          常用。探索完成后会通过 Undefined QQ机器人在群里 @ 你。
        </div>
      </div>
      <div class="grid gap-4">
        <div class="qq-group-card">
          <div class="qq-group-title">
            加入 QQ群
          </div>
          <div class="qq-group-line">
            粉丝一群群号 1067860266（已满）
          </div>
          <div class="qq-group-line">
            粉丝二群群号 172624190
          </div>
          <div class="qq-group-disclaimer">
            QQ 群由粉丝支持并自发维护，非官方答疑渠道，粉丝言论不代表官方。
          </div>
        </div>
        <ConfigItem name="启用 QQ 通知" description="开启后，加群后可收到通知">
          <ToggleSwitch v-model="CONFIG.notifications.qq.enabled" />
        </ConfigItem>
        <ConfigItem name="机器人类型" description="当前固定使用 Undefined QQ机器人">
          <div class="notification-fixed-value">
            Undefined QQ机器人
          </div>
        </ConfigItem>
        <ConfigItem name="你的 QQ 号 / QQ 邮箱" description="支持纯数字 QQ 号或纯数字@qq.com，别名邮箱不支持">
          <InputText
            v-model="qqBindingTarget"
            placeholder="填写纯数字 QQ 号或纯数字@qq.com"
            @focus="openQqBindingEditor"
          />
        </ConfigItem>
        <div v-if="qqVerificationVisible" class="qq-verification-block">
          <div class="qq-verification-head">
            <div class="qq-verification-meta">
              <div class="qq-verification-title">
                邮箱验证码
              </div>
              <div class="qq-verification-desc">
                {{ qqVerificationHint }}
              </div>
            </div>
            <div class="qq-captcha-row">
              <div class="notification-captcha-question">
                <img
                  v-if="qqCaptchaImageData"
                  :src="qqCaptchaImageData"
                  alt="验证码"
                  class="notification-captcha-image"
                >
                <span v-else>{{ qqCaptchaQuestion || (qqCaptchaLoading ? '加载中...' : '点击刷新验证码') }}</span>
              </div>
              <InputText
                v-model="qqCaptchaAnswer"
                :disabled="!qqNumberValid || qqCaptchaLoading"
                class="w-28"
                :placeholder="qqCaptchaType === 'image' ? '输入图中字符' : '答案'"
              />
              <Button
                label="刷新"
                :disabled="qqCaptchaLoading"
                size="small"
                text
                @click="fetchQqCaptcha"
              />
            </div>
          </div>
          <div class="qq-submit-row">
            <InputText
              v-model="qqVerificationCodeInput"
              :disabled="!qqNumberValid"
              class="qq-verification-input"
              placeholder="填写 QQ 邮箱收到的验证码"
            />
            <Button
              :label="qqSendingVerification ? '发送中...' : '发送验证码'"
              :disabled="!qqNumberValid || qqSendingVerification"
              class="qq-send-code-btn"
              outlined
              @click="sendQqVerificationCode"
            />
            <Button
              :label="qqSubmittingBinding ? '提交中...' : '提交'"
              :disabled="!qqNumberValid || qqSubmittingBinding"
              class="qq-save-code-btn"
              outlined
              @click="submitQqEmailBinding"
            />
          </div>
          <div v-if="qqVerificationFeedback" class="text-[11px] text-white/45">
            {{ qqVerificationFeedback }}
          </div>
        </div>
        <div v-if="qqBindingTarget && !qqNumberValid" class="notification-warning">
          {{ qqBinding.errorMessage }}
        </div>
        <div v-if="qqNumberValid" class="flex flex-col gap-2 rounded-lg border border-white/8 bg-white/2 p-3">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm text-white/75">
              测试 QQ 回调
            </div>
            <Button
              :label="qqTestingNotification ? '发送中...' : '测试发送'"
              :disabled="qqTestingNotification"
              size="small"
              outlined
              @click="sendQqTestNotification"
            />
          </div>
          <div class="text-[11px] text-white/40">
            直接向 {{ qqBinding.normalizedQq }} 发一条测试消息，用来验证 QQ 机器人回调链路。
          </div>
          <div v-if="qqTestFeedback" class="text-[11px] text-white/50">
            {{ qqTestFeedback }}
          </div>
        </div>
        <div class="notification-note">
          {{ qqStatusText }}
        </div>
      </div>
    </section>

    <section class="notification-card">
      <div class="notification-card-header">
        <div class="notification-title-row">
          <div class="notification-card-title">
            飞书通知
          </div>
          <button class="help-button" type="button" @click="openTutorial('feishu')">
            ?
          </button>
        </div>
        <div class="notification-card-subtitle">
          探索完成后通过 OpenClaw 的飞书通道回传摘要或完整报告。
        </div>
      </div>
      <div class="grid gap-4">
        <ConfigItem name="启用飞书通知" description="开启后，探索任务结束时会尝试向飞书发送结果">
          <ToggleSwitch v-model="CONFIG.notifications.feishu.enabled" />
        </ConfigItem>
        <ConfigItem name="App ID" description="复制自飞书开放平台应用详情页">
          <InputText v-model="CONFIG.openclaw.feishu.app_id" placeholder="从飞书开放平台复制 App ID" />
        </ConfigItem>
        <ConfigItem name="App Secret" description="复制自飞书开放平台凭证页">
          <InputText v-model="CONFIG.openclaw.feishu.app_secret" type="password" placeholder="从飞书开放平台复制 App Secret" />
        </ConfigItem>
        <Divider class="m-1!" />
        <ConfigItem name="发送到哪里" description="个人消息用 open_id，群消息用 chat_id">
          <Select
            v-model="CONFIG.notifications.feishu.recipient_type"
            :options="FEISHU_TARGET_OPTIONS"
            option-label="label"
            option-value="value"
          />
        </ConfigItem>
        <ConfigItem
          :name="CONFIG.notifications.feishu.recipient_type === 'chat_id' ? '群聊 chat_id' : '个人 open_id'"
          description="按教程里的页面拿到 ID 后粘贴到这里"
        >
          <InputText
            v-model="feishuTargetValue"
            :placeholder="CONFIG.notifications.feishu.recipient_type === 'chat_id' ? '粘贴 chat_id' : '粘贴 open_id'"
          />
        </ConfigItem>
        <ConfigItem name="完成后发送完整报告" description="关闭后只发送完成摘要，完整记录仍保存在应用内">
          <ToggleSwitch v-model="CONFIG.notifications.feishu.deliver_full_report" />
        </ConfigItem>
        <div class="notification-note">
          {{ feishuStatusText }}
        </div>
      </div>
    </section>

    <Dialog
      :visible="!!activeTutorial"
      modal
      :header="tutorialTitle"
      :style="{ width: '640px' }"
      @update:visible="value => !value && (activeTutorial = null)"
    >
      <div v-if="activeTutorial === 'feishu'" class="tutorial-content">
        <section>
          <h4>1. 打开飞书开放平台后台</h4>
          <p>先去飞书开放平台找到你的应用，下面两个链接是最常用的入口：</p>
          <ul>
            <li><a href="https://open.feishu.cn/app" target="_blank" rel="noreferrer">应用列表 / 打开现有应用</a></li>
            <li><a href="https://open.feishu.cn/" target="_blank" rel="noreferrer">飞书开放平台首页</a></li>
          </ul>
        </section>

        <section>
          <h4>2. 回到这里填三样东西</h4>
          <p>你只需要关注：</p>
          <ul>
            <li>`App ID`</li>
            <li>`App Secret`</li>
            <li>接收对象 ID</li>
          </ul>
        </section>

        <section>
          <h4>3. 发送到哪里怎么选</h4>
          <p>如果你想发给个人，就选“发给个人”，然后填写对方的 `open_id`。</p>
          <p>如果你想发到群里，就选“发到群聊”，然后填写目标群的 `chat_id`。</p>
          <p>这两个 ID 需要你从飞书侧现有工具或后台拿到，再粘贴回这里。</p>
        </section>

        <section>
          <h4>4. 发摘要还是发完整报告</h4>
          <p>打开“完成后发送完整报告”时，会把完整结果回传到飞书。</p>
          <p>关闭时，只会发一条较短的完成摘要。</p>
        </section>
      </div>

      <div v-else-if="activeTutorial === 'qq'" class="tutorial-content">
        <section>
          <h4>1. 先填 QQ 号或 QQ 邮箱</h4>
          <p>QQ 通知已经固定走 Undefined QQ机器人，本地不需要再填服务地址、群号、模板或 token。</p>
          <p>这里只支持两种格式：纯数字 QQ 号，或纯数字@qq.com。</p>
          <p>如果你的 QQ 邮箱开了别名，别名地址不能用，必须回到纯数字@qq.com。</p>
        </section>

        <section>
          <h4>2. 再填邮箱验证码</h4>
          <ul>
            <li>填入 QQ 号后，会按 `QQ号@qq.com` 做邮箱验证。</li>
            <li>填入 QQ 邮箱后，只接受纯数字@qq.com。</li>
            <li>验证码会跟绑定信息一起上传，客户端会先做一轮格式校验。</li>
          </ul>
        </section>

        <section>
          <h4>3. 服务器会处理群路由</h4>
          <ul>
            <li>你在设置里只要填自己的 QQ 绑定信息和验证码。</li>
            <li>探索完成后，服务器会根据绑定关系决定发到哪个群。</li>
            <li>群里的机器人会自动 `@` 你，不需要客户端自己处理群号。</li>
          </ul>
        </section>

        <section>
          <h4>4. 真正发送时会发生什么</h4>
          <p>Naga 本地只会上报“这个账号的探索完成了”和“目标 QQ 号”。</p>
          <p>剩下的分发、群内 @ 和机器人发送，全都由服务器和 Undefined QQ机器人完成。</p>
        </section>
      </div>

      <template #footer>
        <Button label="关闭" icon="pi pi-times" @click="activeTutorial = null" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.notification-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border: 1px solid rgb(255 255 255 / 0.08);
  background: rgb(255 255 255 / 0.03);
  border-radius: 1rem;
  padding: 1rem;
}

.notification-card-header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.notification-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.notification-card-title {
  color: rgb(255 255 255 / 0.88);
  font-size: 14px;
  font-weight: 600;
}

.notification-fixed-value {
  color: rgb(255 255 255 / 0.82);
  font-size: 13px;
  line-height: 1.6;
}

.help-button {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  border: 1px solid rgb(255 255 255 / 0.16);
  background: rgb(255 255 255 / 0.04);
  color: rgb(255 255 255 / 0.7);
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
}

.help-button:hover {
  background: rgb(255 255 255 / 0.1);
  border-color: rgb(255 255 255 / 0.28);
  color: rgb(255 255 255 / 0.92);
}

.notification-card-subtitle {
  color: rgb(255 255 255 / 0.4);
  font-size: 12px;
  line-height: 1.6;
}

.notification-note {
  color: rgb(255 255 255 / 0.5);
  font-size: 12px;
  line-height: 1.6;
  padding-left: 4px;
}

.notification-warning {
  color: rgb(255 196 125 / 0.95);
  font-size: 12px;
  line-height: 1.5;
  padding-left: 4px;
}

.qq-group-card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.85rem 1rem;
  border-radius: 0.9rem;
  border: 1px solid rgb(255 255 255 / 0.07);
  background: rgb(255 255 255 / 0.035);
}

.qq-group-title {
  color: rgb(255 255 255 / 0.86);
  font-size: 12px;
  font-weight: 600;
}

.qq-group-line {
  color: rgb(255 255 255 / 0.68);
  font-size: 12px;
  line-height: 1.6;
}

.qq-group-disclaimer {
  color: rgb(255 255 255 / 0.44);
  font-size: 11px;
  line-height: 1.7;
}

.qq-verification-block {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.qq-verification-head {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(0, 1fr);
  gap: 1rem;
  align-items: center;
}

.qq-verification-meta {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.qq-verification-title {
  font-weight: 700;
}

.qq-verification-desc {
  font-size: 0.875rem;
  color: rgb(107 114 128);
  line-height: 1.5;
}

.notification-captcha-question {
  min-height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-width: 0;
  border-radius: 10px;
  border: 1px solid rgb(255 255 255 / 0.08);
  background: rgb(255 255 255 / 0.04);
  font-size: 0.85rem;
  color: rgb(255 255 255 / 0.72);
  overflow: hidden;
}

.notification-captcha-image {
  display: block;
  width: 100%;
  max-width: 160px;
  height: auto;
  object-fit: contain;
  border-radius: 6px;
}

.qq-send-code-btn {
  width: 96px;
  white-space: nowrap;
  flex: 0 0 96px;
}

.qq-save-code-btn {
  width: 72px;
  white-space: nowrap;
  flex: 0 0 72px;
}

.qq-verification-panel {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  width: 100%;
  min-width: 0;
  overflow: hidden;
}

.qq-captcha-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px auto;
  gap: 0.5rem;
  align-items: center;
  width: 100%;
  min-width: 0;
}

.qq-submit-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px 72px;
  gap: 0.5rem;
  align-items: stretch;
  width: 100%;
  min-width: 0;
}

.qq-verification-input {
  flex: 1 1 0;
  min-width: 0;
  width: auto;
}

.tutorial-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  color: rgb(255 255 255 / 0.72);
  font-size: 13px;
  line-height: 1.7;
}

.tutorial-content h4 {
  margin: 0 0 0.35rem;
  color: rgb(255 255 255 / 0.92);
  font-size: 14px;
  font-weight: 600;
}

.tutorial-content p {
  margin: 0.2rem 0;
}

.tutorial-content a {
  color: rgb(255 255 255 / 0.88);
  text-decoration: underline;
}

.tutorial-content ul {
  margin: 0.35rem 0 0;
  padding-left: 1.1rem;
}

.tutorial-content li {
  margin: 0.15rem 0;
}
</style>
