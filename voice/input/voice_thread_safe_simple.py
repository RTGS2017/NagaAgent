# -*- coding: utf-8 -*-
"""
线程安全的语音客户端封装 - 最简化版本
直接使用原始实现，仅添加必要的线程保护
"""

try:
    from nagaagent_core.vendors.PyQt5.QtCore import QObject, pyqtSignal
    HAS_QT = True
except ImportError:
    QObject = object
    HAS_QT = False
    pyqtSignal = lambda *a, **kw: None
import threading


class ThreadSafeVoiceIntegration(QObject):
    """线程安全的语音集成管理器 - 最简化版本"""

    # 定义信号用于跨线程通信
    update_ui_signal = pyqtSignal(str, str)  # (action, data)

    def __init__(self, parent_widget):
        """
        初始化
        :param parent_widget: 父窗口（ChatWindow）
        """
        super().__init__()
        self.parent = parent_widget
        self.voice_client = None
        self._lock = threading.Lock()

        # 用于保存对话记录
        self._current_user_text = ""
        self._current_ai_text = ""
        self._ai_response_buffer = []  # 用于累积AI的流式响应

        # 连接信号到处理函数
        self.update_ui_signal.connect(self._handle_ui_update)

    def start_voice(self, config_params: dict):
        """
        启动语音功能 - 在主线程中执行，与原版类似
        :param config_params: 语音配置参数
        """
        try:
            # 清理可能存在的超时断开标记
            if hasattr(self.parent, '_is_timeout_disconnect'):
                self.parent._is_timeout_disconnect = False

            # 导入语音模块
            from voice.input.voice_realtime import create_voice_client

            # 确保配置中包含使用语音提示词的设置
            if 'use_voice_prompt' not in config_params:
                config_params['use_voice_prompt'] = True  # 默认启用语音提示词

            # 创建客户端（在主线程中）
            self.voice_client = create_voice_client(**config_params)

            if not self.voice_client:
                self.parent.chat_tool.add_user_message("系统", "❌ 语音服务创建失败")
                return False

            # 设置回调函数 - 使用线程安全的包装器
            self.voice_client.set_callbacks(
                on_user_text=self._on_user_text_safe,
                on_text=self._on_ai_text_safe,
                on_response_complete=self._on_response_complete_safe,
                on_status=self._on_status_safe,
                on_error=self._on_error_safe
            )

            # 连接服务
            if self.voice_client.connect():
                self.parent.voice_realtime_active = True
                self.parent.voice_realtime_state = "listening"
                self.parent.update_voice_button_state("listening")
                self.parent.chat_tool.add_user_message("系统", "✅ 实时语音模式已启动，请开始说话...")
                return True
            else:
                self.parent.chat_tool.add_user_message("系统", "❌ 语音服务连接失败，请检查API密钥和网络连接")
                self.voice_client = None
                return False

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.parent.chat_tool.add_user_message("系统", f"❌ 启动语音服务失败: {str(e)}")
            return False

    def stop_voice(self):
        """停止语音功能"""
        try:
            # 设置主动停止标记，防止误判为超时断开
            self.parent._is_manual_stop = True

            with self._lock:
                if self.voice_client:
                    # 先清除所有回调，防止断开时触发状态回调
                    self.voice_client.set_callbacks(
                        on_user_text=None,
                        on_text=None,
                        on_response_complete=None,
                        on_status=None,
                        on_error=None
                    )
                    self.voice_client.disconnect()
                    self.voice_client = None

            self.parent.voice_realtime_active = False
            self.parent.voice_realtime_state = "idle"
            self.parent.update_voice_button_state("idle")

            # 只有不是超时断开时才显示停止消息
            if not getattr(self.parent, '_is_timeout_disconnect', False):
                self.parent.chat_tool.add_user_message("系统", "🔇 实时语音模式已停止")

            # 清理超时标记（在判断后清理）
            if hasattr(self.parent, '_is_timeout_disconnect'):
                self.parent._is_timeout_disconnect = False

            # 清理主动停止标记
            if hasattr(self.parent, '_is_manual_stop'):
                self.parent._is_manual_stop = False

            return True

        except Exception as e:
            self.parent.chat_tool.add_user_message("系统", f"❌ 停止语音服务失败: {str(e)}")
            return False

    def is_active(self):
        """检查是否活跃"""
        with self._lock:
            return self.voice_client is not None

    # 线程安全的回调包装器
    def _on_user_text_safe(self, text):
        """用户文本回调 - 线程安全"""
        # 保存用户文本用于日志记录
        self._current_user_text = text
        self._ai_response_buffer = []  # 清空AI响应缓冲区
        # 总是使用信号确保UI更新
        self.update_ui_signal.emit("user_text", text)

    def _on_ai_text_safe(self, text):
        """AI文本回调 - 线程安全"""
        # 累积AI响应用于日志记录
        self._ai_response_buffer.append(text)
        # 总是使用信号确保UI更新
        self.update_ui_signal.emit("ai_text", text)

    def _on_response_complete_safe(self):
        """响应完成回调 - 线程安全"""
        # 保存完整的对话到日志
        if self._current_user_text and self._ai_response_buffer:
            try:
                from apiserver.message_manager import message_manager
                complete_ai_response = "".join(self._ai_response_buffer)
                # 保存对话日志
                message_manager.save_conversation_log(
                    self._current_user_text,
                    complete_ai_response,
                    dev_mode=False
                )
                # 清空缓冲区
                self._current_user_text = ""
                self._ai_response_buffer = []
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"保存语音对话日志失败: {e}")

        # 总是使用信号确保UI更新
        self.update_ui_signal.emit("response_complete", "")

    def _on_status_safe(self, status):
        """状态变化回调 - 线程安全"""
        # 如果是主动停止，忽略断开连接状态，避免误判为超时
        if status == "disconnected" and getattr(self.parent, '_is_manual_stop', False):
            return
        # 总是使用信号确保UI更新
        self.update_ui_signal.emit("status", status)

    def _on_error_safe(self, error):
        """错误回调 - 线程安全"""
        # 总是使用信号确保UI更新
        self.update_ui_signal.emit("error", error)

    def _handle_ui_update(self, action, data):
        """处理UI更新 - 在主线程中执行"""
        try:
            if action == "user_text":
                self.parent.on_voice_user_text(data)
            elif action == "ai_text":
                self.parent.on_voice_ai_text(data)
            elif action == "response_complete":
                self.parent.on_voice_response_complete()
            elif action == "status":
                self.parent.on_voice_status(data)
            elif action == "error":
                self.parent.on_voice_error(data)
        except Exception:
            import traceback
            traceback.print_exc()


# 向后兼容旧版本的导入
VoiceRealtimeThread = ThreadSafeVoiceIntegration
VoiceClientWorker = ThreadSafeVoiceIntegration