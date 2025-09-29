# config.py - 简化配置系统
"""
NagaAgent 配置系统 - 基于Pydantic实现类型安全和验证
支持配置热更新和变更通知
"""
import os
import socket
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field, field_validator

# 配置变更监听器
_config_listeners: List[Callable] = []

def add_config_listener(callback: Callable):
    """添加配置变更监听器"""
    _config_listeners.append(callback)

def remove_config_listener(callback: Callable):
    """移除配置变更监听器"""
    if callback in _config_listeners:
        _config_listeners.remove(callback)

def notify_config_changed():
    """通知所有监听器配置已变更"""
    for listener in _config_listeners:
        try:
            listener()
        except Exception as e:
            print(f"配置监听器执行失败: {e}")

def setup_environment():
    """设置环境变量解决兼容性问题"""
    env_vars = {
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1", 
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "PYTORCH_MPS_HIGH_WATERMARK_RATIO": "0.0",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1"
    }
    for key, value in env_vars.items():
        os.environ.setdefault(key, value)

class SystemConfig(BaseModel):
    """系统基础配置"""
    version: str = Field(default="3.0", description="系统版本号")
    ai_name: str = Field(default="娜杰日达", description="AI助手名称")
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent, description="项目根目录")
    log_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "logs", description="日志目录")
    voice_enabled: bool = Field(default=True, description="是否启用语音功能")
    stream_mode: bool = Field(default=True, description="是否启用流式响应")
    debug: bool = Field(default=False, description="是否启用调试模式")
    log_level: str = Field(default="INFO", description="日志级别")
    save_prompts: bool = Field(default=True, description="是否保存提示词")

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'日志级别必须是以下之一: {valid_levels}')
        return v.upper()

class APIConfig(BaseModel):
    """API服务配置"""
    api_key: str = Field(default="sk-placeholder-key-not-set", description="API密钥")
    base_url: str = Field(default="https://api.deepseek.com/v1", description="API基础URL")
    model: str = Field(default="deepseek-chat", description="使用的模型名称")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=10000, ge=1, le=32768, description="最大token数")
    max_history_rounds: int = Field(default=100, ge=1, le=200, description="最大历史轮数")
    persistent_context: bool = Field(default=True, description="是否启用持久化上下文")
    context_load_days: int = Field(default=3, ge=1, le=30, description="加载历史上下文的天数")
    context_parse_logs: bool = Field(default=True, description="是否从日志文件解析上下文")

class APIServerConfig(BaseModel):
    """API服务器配置"""
    enabled: bool = Field(default=True, description="是否启用API服务器")
    host: str = Field(default="127.0.0.1", description="API服务器主机")
    port: int = Field(default=8000, ge=1, le=65535, description="API服务器端口")
    auto_start: bool = Field(default=True, description="启动时自动启动API服务器")
    docs_enabled: bool = Field(default=True, description="是否启用API文档")

class GRAGConfig(BaseModel):
    """GRAG知识图谱记忆系统配置"""
    enabled: bool = Field(default=False, description="是否启用GRAG记忆系统")
    auto_extract: bool = Field(default=False, description="是否自动提取对话中的五元组")
    context_length: int = Field(default=5, ge=1, le=20, description="记忆上下文长度")
    similarity_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="记忆检索相似度阈值")
    neo4j_uri: str = Field(default="neo4j://127.0.0.1:7687", description="Neo4j连接URI")
    neo4j_user: str = Field(default="neo4j", description="Neo4j用户名")
    neo4j_password: str = Field(default="your_password", description="Neo4j密码")
    neo4j_database: str = Field(default="neo4j", description="Neo4j数据库名")
    extraction_timeout: int = Field(default=12, ge=1, le=60, description="知识提取超时时间（秒）")
    extraction_retries: int = Field(default=2, ge=0, le=5, description="知识提取重试次数")
    base_timeout: int = Field(default=15, ge=5, le=120, description="基础操作超时时间（秒）")

class HandoffConfig(BaseModel):
    """工具调用循环配置"""
    max_loop_stream: int = Field(default=5, ge=1, le=20, description="流式模式最大工具调用循环次数")
    max_loop_non_stream: int = Field(default=5, ge=1, le=20, description="非流式模式最大工具调用循环次数")
    show_output: bool = Field(default=False, description="是否显示工具调用输出")

class BrowserConfig(BaseModel):
    """浏览器配置"""
    playwright_headless: bool = Field(default=False, description="Playwright浏览器是否无头模式")
    edge_lnk_path: str = Field(
        default=r'C:\Users\DREEM\Desktop\Microsoft Edge.lnk',
        description="Edge浏览器快捷方式路径"
    )
    edge_common_paths: List[str] = Field(
        default=[
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            os.path.expanduser(r'~\AppData\Local\Microsoft\Edge\Application\msedge.exe')
        ],
        description="Edge浏览器常见安装路径"
    )

class TTSConfig(BaseModel):
    """TTS服务配置"""
    api_key: str = Field(default="", description="TTS服务API密钥")
    port: int = Field(default=5048, ge=1, le=65535, description="TTS服务端口")
    default_voice: str = Field(default="zh-CN-XiaoxiaoNeural", description="默认语音")
    default_format: str = Field(default="mp3", description="默认音频格式")
    default_speed: float = Field(default=1.0, ge=0.1, le=3.0, description="默认语速")
    default_language: str = Field(default="zh-CN", description="默认语言")
    remove_filter: bool = Field(default=False, description="是否移除过滤")
    expand_api: bool = Field(default=True, description="是否扩展API")
    require_api_key: bool = Field(default=False, description="是否需要API密钥")

class ASRConfig(BaseModel):
    """ASR输入服务配置"""
    port: int = Field(default=5060, ge=1, le=65535, description="ASR服务端口")
    device_index: int | None = Field(default=None, description="麦克风设备序号")
    sample_rate_in: int = Field(default=48000, description="输入采样率")
    frame_ms: int = Field(default=30, description="分帧时长ms")
    resample_to: int = Field(default=16000, description="重采样目标采样率")
    vad_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="VAD阈值")
    silence_ms: int = Field(default=420, description="静音结束阈值ms")
    noise_reduce: bool = Field(default=True, description="是否降噪")
    engine: str = Field(default="local_funasr", description="ASR引擎，仅支持local_funasr")
    local_model_path: str = Field(default="./utilss/models/SenseVoiceSmall", description="本地FunASR模型路径")
    vad_model_path: str = Field(default="silero_vad.onnx", description="VAD模型路径")
    api_key_required: bool = Field(default=False, description="是否需要API密钥")
    callback_url: str | None = Field(default=None, description="识别结果回调地址")
    ws_broadcast: bool = Field(default=False, description="是否WS广播结果")

class FilterConfig(BaseModel):
    """输出过滤配置"""
    filter_think_tags: bool = Field(default=True, description="过滤思考标签内容")
    filter_patterns: List[str] = Field(
        default=[
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<reflection>.*?</reflection>',
            r'<internal>.*?</internal>',
        ],
        description="过滤正则表达式模式"
    )
    clean_output: bool = Field(default=True, description="清理多余空白字符")

class DifficultyConfig(BaseModel):
    """问题难度判断配置"""
    enabled: bool = Field(default=False, description="是否启用难度判断")
    use_small_model: bool = Field(default=False, description="使用小模型进行难度判断")
    pre_assessment: bool = Field(default=False, description="是否启用前置难度判断")
    assessment_timeout: float = Field(default=1.0, ge=0.1, le=5.0, description="难度判断超时时间（秒）")
    deep_thinking_threshold: int = Field(default=3, ge=1, le=5, description="启用深度思考的难度阈值")
    difficulty_levels: List[str] = Field(
        default=["简单", "中等", "困难", "极难"],
        description="难度级别"
    )
    factors: List[str] = Field(
        default=["概念复杂度", "推理深度", "知识广度", "计算复杂度", "创新要求"],
        description="难度评估因素"
    )
    threshold_simple: int = Field(default=2, ge=1, le=10, description="简单问题阈值")
    threshold_medium: int = Field(default=4, ge=1, le=10, description="中等问题阈值")
    threshold_hard: int = Field(default=6, ge=1, le=10, description="困难问题阈值")

class ScoringConfig(BaseModel):
    """黑白名单打分系统配置"""
    enabled: bool = Field(default=False, description="是否启用打分系统")
    score_range: List[int] = Field(default=[1, 5], description="评分范围")
    score_threshold: int = Field(default=2, ge=1, le=5, description="结果保留阈值")
    similarity_threshold: float = Field(default=0.85, ge=0.0, le=1.0, description="相似结果识别阈值")
    max_user_preferences: int = Field(default=3, ge=1, le=10, description="用户最多选择偏好数")
    default_preferences: List[str] = Field(
        default=["逻辑清晰准确", "实用性强", "创新思维"],
        description="默认偏好设置"
    )
    penalty_for_similar: int = Field(default=1, ge=0, le=3, description="相似结果的惩罚分数")
    min_results_required: int = Field(default=2, ge=1, le=10, description="最少保留结果数量")
    strict_filtering: bool = Field(default=True, description="严格过滤模式")

class ThinkingConfig(BaseModel):
    """思考完整性判断配置"""
    enabled: bool = Field(default=False, description="是否启用思考完整性判断")
    use_small_model: bool = Field(default=False, description="使用小模型判断思考完整性")
    completeness_criteria: List[str] = Field(
        default=["问题分析充分", "解决方案明确", "逻辑链条完整", "结论清晰合理"],
        description="完整性评估标准"
    )
    completeness_threshold: float = Field(default=0.8, ge=0.0, le=1.0, description="完整性阈值")
    max_thinking_depth: int = Field(default=5, ge=1, le=10, description="最大思考深度层级")
    next_question_generation: bool = Field(default=False, description="生成下一级问题")

# 天气服务使用免费API，无需配置

class MQTTConfig(BaseModel):
    """MQTT配置"""
    enabled: bool = Field(default=False, description="是否启用MQTT功能")
    broker: str = Field(default="localhost", description="MQTT代理服务器地址")
    port: int = Field(default=1883, ge=1, le=65535, description="MQTT代理服务器端口")
    topic: str = Field(default="/test/topic", description="MQTT主题")
    client_id: str = Field(default="naga_mqtt_client", description="MQTT客户端ID")
    username: str = Field(default="", description="MQTT用户名")
    password: str = Field(default="", description="MQTT密码")
    keepalive: int = Field(default=60, ge=1, le=3600, description="保持连接时间（秒）")
    qos: int = Field(default=1, ge=0, le=2, description="服务质量等级")

class UIConfig(BaseModel):
    """用户界面配置"""
    user_name: str = Field(default="用户", description="默认用户名")
    bg_alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="聊天背景透明度")
    window_bg_alpha: int = Field(default=110, ge=0, le=255, description="主窗口背景透明度")
    mac_btn_size: int = Field(default=36, ge=10, le=100, description="Mac按钮大小")
    mac_btn_margin: int = Field(default=16, ge=0, le=50, description="Mac按钮边距")
    mac_btn_gap: int = Field(default=12, ge=0, le=30, description="Mac按钮间距")
    animation_duration: int = Field(default=600, ge=100, le=2000, description="动画时长（毫秒）")

class Live2DConfig(BaseModel):
    """Live2D配置"""
    enabled: bool = Field(default=False, description="是否启用Live2D功能")
    model_path: str = Field(default="", description="Live2D模型文件路径")
    fallback_image: str = Field(default="ui/standby.png", description="回退图片路径")
    auto_switch: bool = Field(default=True, description="是否自动切换模式")
    animation_enabled: bool = Field(default=True, description="是否启用动画")
    touch_interaction: bool = Field(default=True, description="是否启用触摸交互")

class NagaPortalConfig(BaseModel):
    """娜迦官网账户配置"""
    portal_url: str = Field(default="https://naga.furina.chat/", description="娜迦官网地址")
    username: str = Field(default="", description="娜迦官网用户名")
    password: str = Field(default="", description="娜迦官网密码")
    request_timeout: int = Field(default=30, ge=5, le=120, description="请求超时时间（秒）")
    login_path: str = Field(default="/api/user/login", description="登录API路径")
    turnstile_param: str = Field(default="", description="Turnstile验证参数")
    login_username_key: str = Field(default="username", description="登录请求中用户名的键名")
    login_password_key: str = Field(default="password", description="登录请求中密码的键名")
    login_payload_mode: str = Field(default="json", description="登录请求载荷模式：json或form")
    default_headers: Dict[str, str] = Field(
        default={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/json"
        },
        description="默认HTTP请求头"
    )

class OnlineSearchConfig(BaseModel):
    """在线搜索配置"""
    searxng_url: str = Field(default="http://localhost:8080", description="SearXNG实例URL")
    engines: List[str] = Field(default=["google"], description="默认搜索引擎列表")
    num_results: int = Field(default=5, ge=1, le=20, description="搜索结果数量")

class SystemCheckConfig(BaseModel):
    """系统检测状态配置"""
    passed: bool = Field(default=False, description="系统检测是否通过")
    timestamp: str = Field(default="", description="检测时间戳")
    python_version: str = Field(default="", description="Python版本")
    project_path: str = Field(default="", description="项目路径")

# 提示词配置已迁移到 system/prompt_repository.py

class GameModuleConfig(BaseModel):
    """博弈论模块配置"""
    enabled: bool = Field(default=False, description="是否启用博弈论流程")
    skip_on_error: bool = Field(default=True, description="博弈论流程失败时是否回退到普通对话")

class NagaConfig(BaseModel):
    """NagaAgent主配置类"""
    system: SystemConfig = Field(default_factory=SystemConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    api_server: APIServerConfig = Field(default_factory=APIServerConfig)
    grag: GRAGConfig = Field(default_factory=GRAGConfig)
    handoff: HandoffConfig = Field(default_factory=HandoffConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)  # ASR输入服务配置 #
    filter: FilterConfig = Field(default_factory=FilterConfig)
    difficulty: DifficultyConfig = Field(default_factory=DifficultyConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    thinking: ThinkingConfig = Field(default_factory=ThinkingConfig)
    # prompts: 提示词配置已迁移到 system/prompt_repository.py
    game: GameModuleConfig = Field(default_factory=GameModuleConfig)
    # weather: 天气服务使用免费API，无需配置
    mqtt: MQTTConfig = Field(default_factory=MQTTConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    live2d: Live2DConfig = Field(default_factory=Live2DConfig)
    naga_portal: NagaPortalConfig = Field(default_factory=NagaPortalConfig)
    online_search: OnlineSearchConfig = Field(default_factory=OnlineSearchConfig)
    system_check: SystemCheckConfig = Field(default_factory=SystemCheckConfig)

    model_config = {"extra": "ignore"}

    def __init__(self, **kwargs):
        setup_environment()
        super().__init__(**kwargs)
        self.system.log_dir.mkdir(parents=True, exist_ok=True)  # 确保递归创建日志目录 #

# 全局配置实例
ENCF = 0  # 编码修复计数器

def load_config():
    """加载配置"""
    global ENCF
    config_path = str(Path(__file__).parent.parent / "config.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            return NagaConfig(**config_data)
        except Exception as e:
            print(f"警告：加载 {config_path} 失败: {e}")
            print("使用默认配置")
            
            if ENCF > 1:
                print(f"警告：加载 {config_path} 失败: {e}")
                print("使用默认配置")
                return NagaConfig()
            
            ENCF += 1
            try:
                # 尝试修复编码问题
                with open(config_path, 'r', encoding='ISO-8859-1') as f:
                    con = f.read()
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(con)
                print("已经修复编码")
                
                # 重新尝试加载配置
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                return NagaConfig(**config_data)
            except Exception as e2:
                print(f"警告：加载 {config_path} 失败: {e2}")
                print("使用默认配置")
                return NagaConfig()
    else:
        print(f"警告：配置文件 {config_path} 不存在，使用默认配置")
    
    return NagaConfig()

config = load_config()

def reload_config() -> NagaConfig:
    """重新加载配置"""
    global config
    config = load_config()
    notify_config_changed()
    return config

def hot_reload_config() -> NagaConfig:
    """热更新配置 - 重新加载配置并通知所有模块"""
    global config
    old_config = config
    config = load_config()
    notify_config_changed()
    print(f"配置已热更新: {old_config.system.version} -> {config.system.version}")
    return config

def get_config() -> NagaConfig:
    """获取当前配置"""
    return config

# 初始化时打印配置信息
if config.system.debug:
    print(f"NagaAgent {config.system.version} 配置已加载")
    print(f"API服务器: {'启用' if config.api_server.enabled else '禁用'} ({config.api_server.host}:{config.api_server.port})")
    print(f"GRAG记忆系统: {'启用' if config.grag.enabled else '禁用'}")

# 启动时设置用户显示名：优先config.json，其次系统用户名 #
try:
    # 检查 config.json 中的 user_name 是否为空白或未填写
    if not config.ui.user_name or not config.ui.user_name.strip():
        # 如果是，则尝试获取系统登录用户名并覆盖
        config.ui.user_name = os.getlogin()
except Exception:
    # 获取系统用户名失败时，将保留默认值 "用户" 或 config.json 中的空值
    pass

