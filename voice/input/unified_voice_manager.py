# -*- coding: utf-8 -*-
"""
统一语音管理器
支持多种语音模式切换：
1. 本地模式（FunASR）
2. 端到端模式（通义千问）
3. 混合模式（通义千问ASR + API Server）
"""

try:
    from PyQt5.QtCore import QObject, pyqtSignal, QTimer
    HAS_QT = True
except ImportError:
    QObject = object
    HAS_QT = False
    pyqtSignal = lambda *a, **kw: None
    QTimer = None
import threading
import requests
import logging
from typing import Optional, Dict
from enum import Enum

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceMode(Enum):
    """语音模式枚举"""
    LOCAL = "local"           # 本地FunASR模式
    END_TO_END = "end2end"    # 端到端通义千问模式
    HYBRID = "hybrid"         # 混合模式（通义千问ASR + API）

class UnifiedVoiceManager(QObject):
    """统一语音管理器"""

    # 信号定义
    update_ui_signal = pyqtSignal(str, str)  # (action, data)

    def __init__(self, parent_widget):
        """
        初始化统一语音管理器
        :param parent_widget: 父窗口（ChatWindow）
        """
        super().__init__()
        self.parent = parent_widget
        self.current_mode = None
        self.voice_integration = None
        self._lock = threading.Lock()

        # 连接信号
        self.update_ui_signal.connect(self._handle_ui_update)

        logger.info("[统一语音] 管理器初始化完成")

    def detect_available_modes(self) -> Dict[VoiceMode, bool]:
        """
        检测可用的语音模式
        :return: 各模式的可用性
        """
        availability = {}

        # 检测本地FunASR
        try:
            response = requests.get("http://localhost:5000/health", timeout=1)
            availability[VoiceMode.LOCAL] = response.status_code == 200
            logger.info(f"[统一语音] 本地FunASR服务: {'可用' if availability[VoiceMode.LOCAL] else '不可用'}")
        except:
            availability[VoiceMode.LOCAL] = False
            logger.info("[统一语音] 本地FunASR服务: 不可用")

        # 检测通义千问配置
        from system.config import config
        has_qwen_key = bool(config.voice_realtime.api_key)
        availability[VoiceMode.END_TO_END] = has_qwen_key
        availability[VoiceMode.HYBRID] = has_qwen_key

        logger.info(f"[统一语音] 通义千问端到端: {'可用' if availability[VoiceMode.END_TO_END] else '不可用'}")
        logger.info(f"[统一语音] 混合模式: {'可用' if availability[VoiceMode.HYBRID] else '不可用'}")

        return availability

    def start_voice(self, mode: VoiceMode = None, config_params: Dict = None):
        """
        启动语音服务
        :param mode: 语音模式，None则根据配置自动选择
        :param config_params: 配置参数
        """
        try:
            from system.config import config

            # 确定使用的模式
            if mode is None:
                # 根据配置自动选择模式
                if config.voice_realtime.provider == "local":
                    mode = VoiceMode.LOCAL
                elif config.voice_realtime.use_api_server:
                    mode = VoiceMode.HYBRID
                else:
                    mode = VoiceMode.END_TO_END

            # 检测模式是否可用
            availability = self.detect_available_modes()
            if not availability.get(mode, False):
                # 降级到可用的模式
                for fallback_mode in [VoiceMode.HYBRID, VoiceMode.END_TO_END, VoiceMode.LOCAL]:
                    if availability.get(fallback_mode, False):
                        logger.warning(f"[统一语音] {mode.value}模式不可用，降级到{fallback_mode.value}模式")
                        mode = fallback_mode
                        break
                else:
                    logger.error("[统一语音] 没有可用的语音模式")
                    self.parent.chat_tool.add_user_message("系统", "❌ 没有可用的语音模式")
                    return False

            # 停止当前的语音服务
            if self.voice_integration:
                self.stop_voice()

            # 根据模式启动对应的集成
            logger.info(f"[统一语音] 启动{mode.value}模式")

            if mode == VoiceMode.END_TO_END:
                # 端到端模式
                from voice.input.voice_thread_safe_simple import ThreadSafeVoiceIntegration
                self.voice_integration = ThreadSafeVoiceIntegration(self.parent)
                mode_name = "端到端语音（通义千问）"
            else:
                # 其他模式已删除，统一使用端到端模式
                from voice.input.voice_thread_safe_simple import ThreadSafeVoiceIntegration
                self.voice_integration = ThreadSafeVoiceIntegration(self.parent)
                mode_name = "统一语音模式"

            # 启动语音服务
            if not config_params:
                config_params = {
                    'provider': config.voice_realtime.provider,
                    'api_key': config.voice_realtime.api_key,
                    'model': config.voice_realtime.model,
                    'voice': config.voice_realtime.voice,
                    'debug': config.voice_realtime.debug,
                    'input_sample_rate': config.voice_realtime.input_sample_rate,
                    'output_sample_rate': config.voice_realtime.output_sample_rate,
                    'chunk_size_ms': config.voice_realtime.chunk_size_ms,
                    'vad_threshold': config.voice_realtime.vad_threshold,
                    'echo_suppression': config.voice_realtime.echo_suppression
                }

            success = self.voice_integration.start_voice(config_params)

            if success:
                self.current_mode = mode
                logger.info(f"[统一语音] {mode_name}启动成功")
                return True
            else:
                logger.error(f"[统一语音] {mode_name}启动失败")
                self.voice_integration = None
                return False

        except Exception as e:
            logger.error(f"[统一语音] 启动失败: {e}")
            import traceback
            traceback.print_exc()
            self.parent.chat_tool.add_user_message("系统", f"❌ 启动语音服务失败: {str(e)}")
            return False

    def stop_voice(self):
        """停止语音服务"""
        try:
            if self.voice_integration:
                success = self.voice_integration.stop_voice()
                self.voice_integration = None
                self.current_mode = None
                return success
            return True
        except Exception as e:
            logger.error(f"[统一语音] 停止失败: {e}")
            return False

    def switch_mode(self, new_mode: VoiceMode):
        """
        切换语音模式
        :param new_mode: 新模式
        """
        logger.info(f"[统一语音] 切换到{new_mode.value}模式")

        # 停止当前模式
        self.stop_voice()

        # 启动新模式
        return self.start_voice(mode=new_mode)

    def is_active(self) -> bool:
        """检查语音服务是否活跃"""
        return self.voice_integration is not None and hasattr(self.voice_integration, 'is_active') and self.voice_integration.is_active()

    def get_current_mode(self) -> Optional[VoiceMode]:
        """获取当前模式"""
        return self.current_mode

    def _handle_ui_update(self, action, data):
        """处理UI更新"""
        # 转发给父窗口处理
        if hasattr(self.parent, f'on_voice_{action}'):
            getattr(self.parent, f'on_voice_{action}')(data)