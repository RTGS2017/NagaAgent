import { ref, watch } from 'vue'
import API from '@/api/core'

export interface Model {
  source: string
  x: number
  y: number
  size: number
}

export function defineModel(model: Model) {
  return model
}

export const MODELS = {
  NagaTest: defineModel({
    source: './models/naga-test/naga-test.model3.json',
    x: 0.5,
    y: 1.3,
    size: 6800,
  }),
  NagaTest2: defineModel({
    source: './models/NagaTest2/NagaTest2.model3.json',
    x: 0.5,
    y: 1.3,
    size: 6800,
  }),
} as const

export const DEFAULT_MODEL: keyof typeof MODELS = 'NagaTest2'

export const DEFAULT_CONFIG = {
  system: {
    version: '5.1.0', // 系统版本号
    ai_name: '娜杰日达', // AI助手名称
    active_character: '娜迦日达', // 当前活跃角色名称
    voice_enabled: true, // 是否启用语音功能
    stream_mode: true, // 是否启用流式响应
    debug: false, // 是否启用调试模式
    log_level: 'INFO', // 日志级别: DEBUG, INFO, WARNING, ERROR
    save_prompts: true, // 是否保存提示词到日志
  },
  api: {
    api_key: 'your-api-key-here', // LLM API密钥
    base_url: 'https://api.deepseek.com/v1', // API基础URL
    model: 'deepseek-v3.2', // 使用的模型名称
    temperature: 0.7, // 生成温度 (0.0-2.0)
    max_tokens: 8192, // 最大token数
    max_history_rounds: 10, // 最大历史对话轮数
    persistent_context: true, // 是否持久化上下文
    context_load_days: 3, // 上下文加载天数
    context_parse_logs: true, // 是否解析日志中的上下文
    applied_proxy: false, // 是否应用代理
  },
  api_server: {
    enabled: true, // 是否启用API服务器
    host: '127.0.0.1', // 服务器主机地址
    port: 8000, // 服务器端口
    auto_start: true, // 是否自动启动
    docs_enabled: true, // 是否启用API文档
  },
  agentserver: {
    enabled: true, // 是否启用代理服务器
    host: '127.0.0.1', // 代理服务器主机
    port: 8001, // 代理服务器端口
    auto_start: true, // 是否自动启动
  },
  mcpserver: {
    enabled: true, // 是否启用MCP服务器
    host: '127.0.0.1', // MCP服务器主机
    port: 8003, // MCP服务器端口
    auto_start: true, // 是否自动启动
    agent_discovery: true, // 是否启用代理发现
  },
  grag: {
    enabled: true, // 是否启用知识图谱
    auto_extract: true, // 是否自动提取
    context_length: 5, // 上下文长度
    similarity_threshold: 0.6, // 相似度阈值
    neo4j_uri: 'neo4j://127.0.0.1:7687', // Neo4j数据库URI
    neo4j_user: 'neo4j', // Neo4j用户名
    neo4j_password: 'your-neo4j-password', // Neo4j密码
    neo4j_database: 'neo4j', // Neo4j数据库名
    extraction_timeout: 12, // 提取超时时间(秒)
    extraction_retries: 2, // 提取重试次数
    base_timeout: 15, // 基础超时时间(秒)
  },
  handoff: {
    max_loop_stream: 5, // 流式模式最大循环次数
    max_loop_non_stream: 5, // 非流式模式最大循环次数
    show_output: false, // 是否显示输出
  },
  browser: {
    playwright_headless: false, // Playwright是否无头模式
  },
  tts: {
    api_key: '', // TTS API密钥
    port: 5048, // TTS服务端口
    default_voice: 'zh-CN-XiaoxiaoNeural', // 默认语音
    default_format: 'mp3', // 默认音频格式
    default_speed: 1.0, // 默认语速
    default_language: 'zh-CN', // 默认语言
    remove_filter: false, // 是否移除过滤器
    expand_api: true, // 是否扩展API
    require_api_key: false, // 是否需要API密钥
  },
  game: {
    enabled: false, // 是否启用游戏功能
    skip_on_error: true, // 出错时是否跳过
  },
  voice_realtime: {
    enabled: false, // 是否启用实时语音
    provider: 'qwen', // 语音提供商
    api_key: 'your-dashscope-api-key-here', // DashScope API密钥
    model: 'qwen3-asr-realtime', // 实时语音模型
    tts_model: 'qwen-tts-realtime', // TTS模型
    asr_model: 'qwen3-asr-realtime', // ASR模型
    voice: 'Cherry', // 语音名称
    voice_mode: 'auto', // 语音模式
    tts_voice: 'zh-CN-XiaoyiNeural', // TTS语音
    input_sample_rate: 16000, // 输入采样率
    output_sample_rate: 24000, // 输出采样率
    chunk_size_ms: 200, // 音频块大小(毫秒)
    vad_threshold: 0.02, // 语音活动检测阈值
    echo_suppression: true, // 是否启用回声抑制
    min_user_interval: 2.0, // 最小用户间隔(秒)
    cooldown_duration: 1.0, // 冷却持续时间(秒)
    max_user_speech: 30.0, // 最大用户语音时长(秒)
    debug: false, // 是否启用调试
    integrate_with_memory: true, // 是否与记忆集成
    show_in_chat: true, // 是否在聊天中显示
    use_api_server: true, // 是否使用API服务器
  },
  weather: {
    api_key: 'your-weather-api-key-or-leave-empty', // 天气API密钥
  },
  mqtt: {
    enabled: false, // 是否启用MQTT
    broker: 'mqtt-broker-address', // MQTT代理地址
    port: 1883, // MQTT端口
    topic: 'naga/agent/topic', // MQTT主题
    client_id: 'naga-agent-client', // MQTT客户端ID
    username: 'mqtt-username', // MQTT用户名
    password: 'mqtt-password', // MQTT密码
    keepalive: 60, // 保持连接时间(秒)
    qos: 1, // 服务质量等级
  },
  ui: {
    user_name: '用户', // 用户名称
    bg_alpha: 0.81, // 背景透明度
    window_bg_alpha: 128, // 窗口背景透明度
    mac_btn_size: 36, // Mac按钮大小
    mac_btn_margin: 16, // Mac按钮边距
    mac_btn_gap: 12, // Mac按钮间距
    animation_duration: 600, // 动画持续时间(毫秒)
  },
  naga_portal: {
    portal_url: 'https://naga.furina.chat/', // Naga门户URL
    username: 'your-portal-username', // 门户用户名
    password: 'your-portal-password', // 门户密码
  },
  online_search: {
    searxng_url: 'https://searxng.pylindex.top', // SearXNG搜索URL
    engines: [ // 搜索引擎列表
      'google',
    ],
    num_results: 5, // 搜索结果数量
  },
  computer_control: {
    enabled: true, // 是否启用计算机控制
    model: 'gemini-2.5-flash', // 视觉模型
    model_url: 'https://open.bigmodel.cn/api/paas/v4', // 模型API URL
    api_key: '', // 模型API密钥
    grounding_model: 'gemini-2.5-flash', // 基础模型
    grounding_url: 'https://open.bigmodel.cn/api/paas/v4', // 基础模型URL
    grounding_api_key: '', // 基础模型API密钥
    screen_width: 1920, // 屏幕宽度
    screen_height: 1080, // 屏幕高度
    max_dim_size: 1920, // 最大尺寸
    dpi_awareness: true, // 是否启用DPI感知
    safe_mode: true, // 是否启用安全模式
  },
  crawl4ai: {
    headless: true, // 是否无头模式
    timeout: 30000, // 超时时间(毫秒)
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', // 用户代理
    viewport_width: 1280, // 视口宽度
    viewport_height: 720, // 视口高度
  },
  live2d: {
    enabled: false, // 是否启用Live2D
    model_path: '', // Live2D模型路径
    fallback_image: 'ui/img/standby.png', // 备用图片
    auto_switch: true, // 是否自动切换
    animation_enabled: true, // 是否启用动画
    touch_interaction: true, // 是否启用触摸交互
  },
  floating: {
    enabled: false, // 是否启用悬浮球模式
  },
  memory_server: {
    url: 'http://localhost:8004', // NagaMemory 服务地址
    token: null as string | null, // 认证 Token
  },
  embedding: {
    model: 'tongyi-embedding', // 嵌入模型名称
    api_base: '', // 嵌入模型API地址（留空使用主模型地址）
    api_key: '', // 嵌入模型API密钥（留空使用主模型密钥）
  },
  web_live2d: {
    ssaa: 2,
    model: MODELS[DEFAULT_MODEL],
    face_y_ratio: 0.13, // 视角追踪面部Y轴位置比例（0=模型顶部, 1=底部）
    tracking_hold_delay_ms: 100, // 按住超过该毫秒数后才开始视角追踪，0=点击即追踪
  },
  system_check: {
    passed: false, // 系统检查是否通过
    timestamp: '', // 检查时间戳
    python_version: '', // Python版本
    project_path: '', // 项目路径
  },
  pypi: {
    token_name: 'RTGS', // PyPI令牌名称
    api: 'pypi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', // PyPI API令牌
  },
}

export const SYSTEM_PROMPT = ref('')

let promptWatchStop: (() => void) | null = null
const CONFIG_SYNC_DELAY_MS = 400

function loadSystemPrompt() {
  API.getSystemPrompt().then((res) => {
    SYSTEM_PROMPT.value = res.prompt
    if (!promptWatchStop) {
      promptWatchStop = watch(SYSTEM_PROMPT, (content) => {
        API.setSystemPrompt(content)
      })
    }
  }).catch(() => {
    // Retry after backend connects
    setTimeout(loadSystemPrompt, 3000)
  })
}

export type Config = typeof DEFAULT_CONFIG

export const CONFIG = ref<Config>(JSON.parse(JSON.stringify(DEFAULT_CONFIG)))
export const backendConnected = ref(false)

function deepMerge<T extends Record<string, any>>(target: T, source: Record<string, any>): T {
  const result = { ...target }
  for (const key of Object.keys(source)) {
    const tVal = result[key as keyof T]
    const sVal = source[key]
    if (
      tVal && sVal
      && typeof tVal === 'object' && !Array.isArray(tVal)
      && typeof sVal === 'object' && !Array.isArray(sVal)
    ) {
      ;(result as any)[key] = deepMerge(tVal, sVal)
    }
    else {
      ;(result as any)[key] = sVal
    }
  }
  return result
}

let configWatchStop: (() => void) | null = null
let configSyncTimer: ReturnType<typeof setTimeout> | null = null

function scheduleConfigSync(config: Config) {
  if (configSyncTimer) {
    clearTimeout(configSyncTimer)
  }

  // 避免在防抖窗口内被后续响应对象引用污染
  const payload: Config = JSON.parse(JSON.stringify(config))
  configSyncTimer = setTimeout(() => {
    API.setSystemConfig(payload).catch(() => {
      // 后端暂不可用时忽略，连接逻辑会自动重试
    })
  }, CONFIG_SYNC_DELAY_MS)
}

let connectRetryDelay = 300 // 指数退避起始值

function connectBackend() {
  API.systemConfig().then((res) => {
    CONFIG.value = deepMerge(JSON.parse(JSON.stringify(DEFAULT_CONFIG)), res.config)
    backendConnected.value = true
    connectRetryDelay = 300 // 重置
    loadSystemPrompt()
    // Only set up sync watch once connected
    if (!configWatchStop) {
      configWatchStop = watch(CONFIG, (nextConfig) => {
        if (!backendConnected.value) {
          return
        }
        scheduleConfigSync(nextConfig)
      }, { deep: true })
    }
  }).catch(() => {
    if (!backendConnected.value) {
      // 指数退避：300 → 600 → 1200 → 2400（上限 2.5s）
      setTimeout(connectBackend, connectRetryDelay)
      connectRetryDelay = Math.min(connectRetryDelay * 2, 2500)
    }
  })
}

connectBackend()
