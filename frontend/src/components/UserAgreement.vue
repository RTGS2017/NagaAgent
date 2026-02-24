<script setup lang="ts">
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'

defineProps<{ visible: boolean }>()
defineEmits<{ 'update:visible': [value: boolean] }>()
</script>

<template>
  <Dialog
    :visible="visible"
    modal
    header="用户使用协议"
    :style="{ width: '640px' }"
    @update:visible="$emit('update:visible', $event)"
  >
    <div class="agreement-content">
      <h3>娜迦智能体用户使用协议</h3>
      <p class="update-date">更新日期：2025 年 2 月</p>

      <section>
        <h4>一、总则与接受条款</h4>
        <p>欢迎使用由娜迦智能体团队（以下简称"我们"）开发并运营的"娜迦智能体"软件及相关服务（以下简称"本服务"）。请您在使用本服务前仔细阅读本协议。一旦您注册、登录或以任何方式使用本服务，即视为您已充分理解并同意接受本协议的全部条款。</p>
        <p>我们有权根据法律法规变化及业务发展需要修订本协议，更新后的协议将在软件内公布，继续使用即视为同意修订后的条款。</p>
      </section>

      <section class="beta-notice">
        <h4>特别声明：内测版本</h4>
        <p><b>本软件当前处于内测阶段（Beta），仅供测试与体验使用，不进行任何形式的收费。</b></p>
        <p>内测期间，我们不对用户数据的完整性、持久性作任何保障。用户数据（包括但不限于账号信息、对话记录、知识图谱数据、上传文件等）可能因系统升级、架构调整或其他原因被部分或全部清除，届时恕不另行通知。</p>
        <p>请勿在本服务中存储重要或敏感数据。因数据清除造成的任何损失，我们不承担责任。</p>
      </section>

      <section>
        <h4>二、服务内容</h4>
        <p>本服务主要包括但不限于以下功能：</p>
        <ul>
          <li>AI 对话交互：基于大语言模型的智能对话服务；</li>
          <li>知识图谱记忆（GRAG）：对话内容的知识抽取、存储与检索；</li>
          <li>语音交互：语音识别（ASR）及语音合成（TTS）功能；</li>
          <li>工具调用：通过 MCP 协议集成的第三方工具与插件；</li>
          <li>多智能体协作：基于任务规划的多 Agent 协同处理。</li>
        </ul>
        <p>我们可能根据运营需要对服务内容进行调整、增减或优化。</p>
      </section>

      <section>
        <h4>三、用户注册与账号安全</h4>
        <p>您在注册时应提供真实、准确、完整的信息，并妥善保管您的账号和密码。因您个人原因导致的账号泄露、被盗等风险及后果，由您自行承担。</p>
        <p>如发现账号存在安全风险，请及时联系我们处理。</p>
      </section>

      <section>
        <h4>四、使用规范</h4>
        <p>您在使用本服务时应遵守中华人民共和国相关法律法规，不得利用本服务从事以下行为：</p>
        <ul>
          <li>发布、传播违法违规或有害信息；</li>
          <li>利用本服务从事任何侵害他人合法权益的活动；</li>
          <li>对本服务进行反向工程、反编译、反汇编或其他试图获取源代码的行为（开源部分除外）；</li>
          <li>恶意干扰、破坏本服务的正常运行；</li>
          <li>利用本服务生成虚假信息进行欺诈或误导他人；</li>
          <li>未经授权批量抓取或自动化访问本服务。</li>
        </ul>
      </section>

      <section>
        <h4>五、知识产权</h4>
        <p>本服务中涉及的软件代码、界面设计、图标、文档及其他内容的知识产权归娜迦智能体团队所有（开源组件遵循其各自许可协议）。</p>
        <p>您通过本服务生成的内容，其知识产权归属依照相关法律法规确定。</p>
      </section>

      <section>
        <h4>六、隐私保护</h4>
        <p>我们重视您的隐私保护。在使用本服务过程中，我们可能收集必要的信息用于提供和改善服务，包括但不限于：</p>
        <ul>
          <li>注册信息（用户名、邮箱）；</li>
          <li>对话内容（用于知识图谱构建，数据存储在您本地或您配置的数据库中）；</li>
          <li>使用日志（用于问题排查和服务优化）。</li>
        </ul>
        <p>我们不会将您的个人信息出售或提供给第三方，除非获得您的明确授权或法律法规要求。</p>
      </section>

      <section>
        <h4>七、免责声明</h4>
        <p>本服务基于人工智能技术提供，AI 生成的内容仅供参考，不构成任何专业建议（包括但不限于法律、医疗、金融建议）。您应对基于 AI 生成内容所作的决策自行承担责任。</p>
        <p>因不可抗力、第三方服务故障、网络问题等非我们可控因素导致的服务中断或数据损失，我们不承担责任。</p>
      </section>

      <section>
        <h4>八、服务变更与终止</h4>
        <p>我们保留随时修改、中断或终止部分或全部服务的权利。对于免费服务的变更或终止，我们无需另行通知。</p>
        <p>如您违反本协议条款，我们有权限制或终止您对本服务的使用。</p>
      </section>

      <section>
        <h4>九、争议解决</h4>
        <p>本协议的订立、执行、解释及争议解决均适用中华人民共和国法律。</p>
        <p>因本协议产生的争议，双方应友好协商解决；协商不成的，任何一方均可向有管辖权的人民法院提起诉讼。</p>
      </section>

      <section>
        <h4>十、联系方式</h4>
        <p>如您对本协议有任何疑问或建议，请通过以下方式联系我们：</p>
        <ul>
          <li>B 站：<b>柏斯阔落</b></li>
          <li>QQ 频道：<b>nagaagent1</b></li>
        </ul>
      </section>
    </div>

    <template #footer>
      <Button label="关闭" icon="pi pi-times" @click="$emit('update:visible', false)" />
    </template>
  </Dialog>
</template>

<style scoped>
.agreement-content {
  max-height: 420px;
  overflow-y: auto;
  padding-right: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--p-surface-200, #ccc);
}

.agreement-content h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  color: rgba(212, 175, 55, 0.9);
}

.update-date {
  text-align: center;
  font-size: 12px;
  color: var(--p-surface-400, #888);
  margin-bottom: 12px;
}

.agreement-content h4 {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: rgba(212, 175, 55, 0.8);
}

.agreement-content p {
  margin: 4px 0;
}

.agreement-content ul {
  margin: 4px 0 4px 20px;
  padding: 0;
  list-style: disc;
}

.agreement-content li {
  margin: 2px 0;
}

.agreement-content section {
  margin-bottom: 4px;
}

.beta-notice {
  background: rgba(212, 175, 55, 0.08);
  border: 1px solid rgba(212, 175, 55, 0.25);
  border-radius: 6px;
  padding: 8px 12px;
  margin: 10px 0;
}
</style>
