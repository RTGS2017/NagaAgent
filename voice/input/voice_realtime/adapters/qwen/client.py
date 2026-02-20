#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
重构版通义千问实时语音客户端
基于模块化设计，彻底解决自问自答问题
"""

import base64
import time
import logging
import threading
import websocket
from typing import Optional, Callable, Dict, Any
from dashscope.audio.qwen_omni import (
    OmniRealtimeConversation,
    OmniRealtimeCallback,
    MultiModality,
    AudioFormat
)
import dashscope

from ...core.audio_manager import AudioManager
from ...core.state_manager import StateManager, ConversationState

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PatchedOmniRealtimeConversation(OmniRealtimeConversation):
    """
    Subclass of OmniRealtimeConversation to override the connect method
    with a customizable timeout, avoiding direct modification of site-packages.
    """
    def _cleanup_connection_resources(self, join_timeout: float = 1.0) -> None:
        """
        Best-effort teardown for timeout/failed connect path.
        """
        ws = getattr(self, "ws", None)
        if ws is not None:
            try:
                ws.close()
            except Exception as exc:
                logger.warning(f"failed to close websocket during timeout cleanup: {exc}")

        thread = getattr(self, "thread", None)
        if thread is not None and thread.is_alive():
            try:
                thread.join(timeout=join_timeout)
            except Exception as exc:
                logger.warning(f"failed to join websocket thread during timeout cleanup: {exc}")

        self.ws = None
        self.thread = None

    def connect(self, timeout: int = 15) -> None:
        """
        connect to server, create session and return default session configuration
        """
        self.ws = websocket.WebSocketApp(
            self.url,
            header=self._get_websocket_header(),
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.thread = threading.Thread(target=self.ws.run_forever)
        self.thread.daemon = True
        self.thread.start()
        start_time = time.time()
        while (
            not (self.ws.sock and self.ws.sock.connected)
            and (time.time() - start_time) < timeout
        ):
            time.sleep(0.1)  # 短暂休眠，避免密集轮询
        if not (self.ws.sock and self.ws.sock.connected):
            self._cleanup_connection_resources()
            raise TimeoutError(
                f"websocket connection could not established within {timeout}s. "
                "Please check your network connection, firewall settings, or server status."
            )
        self.callback.on_open()


class QwenVoiceClientRefactored:
    """
    重构版通义千问语音客户端
    使用模块化设计，实现可靠的音频隔离
    """

    def __init__(
        self,
        api_key: str,
        model: str = 'qwen3-omni-flash-realtime',
        voice: str = 'Cherry',
        debug: bool = False,
        use_voice_prompt: bool = True  # 添加是否使用语音专用提示词的参数
    ):
        """
        初始化客户端

        参数:
            api_key: DashScope API密钥
            model: 模型名称
            voice: 语音角色
            debug: 是否启用调试模式
        """
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.debug = debug
        self.use_voice_prompt = use_voice_prompt  # 保存是否使用语音提示词的设置

        # 设置API密钥
        dashscope.api_key = api_key

        # 核心组件
        self.audio_manager = AudioManager(
            input_sample_rate=16000,
            output_sample_rate=24000,
            chunk_size_ms=20,  # 🔧 关键修复：改为20ms（480样本，50FPS），接近EdgeTTS的400样本，RMS能量计算更准确
            vad_threshold=0.02,  # 提高阈值，减少误触发
            echo_suppression=True
        )

        # 🔧 首次播放优化：暂时不启用延迟
        # self.audio_manager.first_playback_delay_ms = 0
        # self.audio_manager.enable_timing_debug = True  # 已默认开启

        self.state_manager = StateManager(debug=debug)

        # DashScope会话
        self.conversation: Optional[OmniRealtimeConversation] = None

        # 回调函数
        self.on_text_callback: Optional[Callable[[str], None]] = None
        self.on_user_text_callback: Optional[Callable[[str], None]] = None
        self.on_response_complete_callback: Optional[Callable[[], None]] = None
        self.on_status_callback: Optional[Callable[[str], None]] = None

        # 统计信息
        self.stats = {
            'session_id': None,
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'start_time': 0
        }

        # 配置参数
        self.config = {
            'auto_reconnect': False,  # 默认关闭自动重连，由UI层控制
            'reconnect_interval': 5.0,
            'max_reconnect_attempts': 3,
            'allow_auto_interrupt': False,  # 是否允许自动打断AI说话
            'vad_sensitivity': 0.5  # VAD敏感度（0-1，值越高越不敏感）
        }

        # 打断控制
        self.manual_interrupt_flag = False  # 手动打断标志

        # 断开连接标志
        self.is_disconnecting = False  # 添加断开连接标志，防止播放结束后重连

        # AI响应状态标志
        self.ai_response_in_progress = False  # AI是否正在响应
        self.ai_response_done = False  # AI响应是否完成

        # 口型同步现在由AudioManager直接处理（模仿EdgeTTS）
        # 移除client中的引擎初始化和回调处理，避免重复

        # 设置组件回调
        self._setup_callbacks()

    def _ensure_project_root_in_path(self) -> str:
        """
        确保项目根目录在sys.path中，以便导入system.config

        Returns:
            项目根目录路径
        """
        import sys
        import os
        # 计算项目根目录（向上5级）
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        return project_root

    def _fix_ai_name(self, text: str) -> str:
        """
        修正AI响应中的名称引用
        将Qwen-Omni相关的自我介绍替换为娜迦日达
        """
        if not text:
            return text

        # 替换各种可能的自我介绍模式
        replacements = [
            # 英文变体
            ("Qwen-Omni", "娜迦日达"),
            ("Qwen Omni", "娜迦日达"),
            ("QwenOmni", "娜迦日达"),
            ("I am Qwen", "我是娜迦日达"),
            ("I'm Qwen", "我是娜迦日达"),
            ("My name is Qwen", "我叫娜迦日达"),

            # 中文变体
            ("千问万相", "娜迦日达"),
            ("千问", "娜迦日达"),
            ("通义千问", "娜迦日达"),
            ("我是Qwen", "我是娜迦日达"),
            ("我叫Qwen", "我叫娜迦日达"),
            ("我是千问", "我是娜迦日达"),
            ("我叫千问", "我叫娜迦日达"),

            # 确保大小写不敏感
            ("qwen-omni", "娜迦日达"),
            ("qwen omni", "娜迦日达"),
            ("QWEN", "娜迦日达"),
        ]

        result = text
        for old, new in replacements:
            # 使用大小写不敏感的替换
            import re
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            result = pattern.sub(new, result)

        return result

    def _setup_callbacks(self):
        """
        设置组件间的回调连接
        """
        # 音频管理器回调
        self.audio_manager.on_audio_input = self._on_audio_input
        self.audio_manager.on_playback_started = self._on_playback_started
        self.audio_manager.on_playback_ended = self._on_playback_ended
        # 口型同步现在由AudioManager内部直接处理（模仿EdgeTTS）

        # 状态管理器回调
        self.state_manager.add_state_callback(
            ConversationState.LISTENING,
            lambda: self.audio_manager.start_recording()
        )
        self.state_manager.add_state_callback(
            ConversationState.AI_SPEAKING,
            lambda: self.audio_manager.stop_recording()
        )
        self.state_manager.add_state_callback(
            ConversationState.COOLDOWN,
            lambda: logger.info("进入冷却期，防止误识别")
        )

    def _on_audio_input(self, audio_data: bytes):
        """
        处理音频输入
        """
        # 在AI说话期间，不发送音频数据到服务器（避免误触发）
        if self.state_manager.current_state == ConversationState.AI_SPEAKING:
            logger.debug("AI说话期间，不发送音频数据")
            return

        # 检查状态是否允许发送
        if not self.state_manager.can_accept_user_input():
            logger.debug("状态不允许发送音频")
            return

        # 发送到服务器
        if self.conversation:
            try:
                audio_b64 = base64.b64encode(audio_data).decode('ascii')
                self.conversation.append_audio(audio_b64)
                self.stats['messages_sent'] += 1
            except Exception as e:
                logger.error(f"发送音频失败: {e}")
                self.stats['errors'] += 1

    def _on_playback_started(self):
        """
        播放开始回调
        """
        logger.info("[状态] 音频播放开始，麦克风已静音")

        # Live2D嘴部同步现在由AudioManager内部处理（模仿EdgeTTS）

        # 确保在AI_SPEAKING状态
        if self.state_manager.current_state != ConversationState.AI_SPEAKING:
            self.state_manager.transition_to(ConversationState.AI_SPEAKING)
            logger.info("[状态] 转换到AI_SPEAKING状态")
        if self.on_status_callback:
            self.on_status_callback("ai_speaking")
            logger.info("[状态] 发送ai_speaking到UI（播放开始）")

    def _on_playback_ended(self):
        """
        播放结束回调
        """
        logger.info(f"[状态] 音频播放结束 - AI响应完成状态: {self.ai_response_done}")

        # Live2D嘴巴关闭由AudioManager内部处理（模仿EdgeTTS）

        # 检查是否正在断开连接，如果是则不进行状态转换
        if self.is_disconnecting:
            logger.info("[状态] 正在断开连接，跳过状态转换")
            return

        # 只有在AI响应真正完成后才进行状态转换
        if self.ai_response_done:
            logger.info("[状态] AI响应已完成，进入冷却期")
            # 正常的状态转换流程
            # 无论auto_reconnect设置如何，都进行状态转换
            # auto_reconnect只影响UI层的行为，不影响底层的状态管理
            self.state_manager.on_ai_response_ended()
            if self.on_status_callback:
                self.on_status_callback("cooldown")
                logger.info("[状态] 发送cooldown到UI")
        else:
            # AI还在响应中，保持ai_speaking状态
            logger.info("[状态] 音频播放暂停，但AI仍在响应，保持ai_speaking状态")
            if self.on_status_callback:
                self.on_status_callback("ai_speaking")
                logger.info("[状态] 保持ai_speaking状态")


    def _on_open(self):
        """
        连接建立时的回调
        """
        logger.info("WebSocket连接已建立")

        # 重置断开连接标志
        self.is_disconnecting = False

        # 重置响应状态标志
        self.ai_response_in_progress = False
        self.ai_response_done = False

        # 初始化音频管理器（确保重新设置所有回调）
        if self.audio_manager.initialize():
            # 重新设置组件回调（重要：重新连接时必须重新设置）
            self._setup_callbacks()

            # 清空所有缓冲区，确保没有上次会话的残留
            self.audio_manager.clear_output_buffer()

            self.audio_manager.start()
            logger.info("音频管理器已启动，缓冲区已清空")
        else:
            logger.error("音频管理器初始化失败")
            return

        # 转换到监听状态
        self.state_manager.transition_to(ConversationState.LISTENING)

        # 发送语音专用系统提示词（如果启用）
        if self.use_voice_prompt:
            try:
                # 获取语音专用提示词
                self._ensure_project_root_in_path()
                from system.config import get_prompt, config

                # 获取AI名称
                ai_name = config.system.ai_name

                # 获取对话风格提示词
                voice_prompt = get_prompt("conversation_style_prompt")

                # 发送系统提示词作为初始指令
                # 注意：通义千问可能需要通过特定的方式设置系统消息
                # 这里尝试通过发送文本的方式
                if self.conversation and voice_prompt:
                    logger.info(f"设置语音专用系统提示词，AI名称: {ai_name}")
                    # 通过发送一个系统消息来设置上下文
                    # 具体实现可能需要根据通义千问的API文档调整
                    pass  # 暂时保留，因为通义千问可能不支持直接设置系统提示词

            except Exception as e:
                logger.warning(f"加载语音提示词失败，使用默认设置: {e}")

        if self.on_status_callback:
            self.on_status_callback("connected")

    def _on_close(self, close_status_code: int, close_msg: str):
        """
        连接关闭时的回调
        """
        logger.info(f"连接已关闭: code={close_status_code}, msg={close_msg}")

        # 停止音频管理器
        self.audio_manager.stop()

        # 重置状态管理器
        self.state_manager.reset()

        if self.on_status_callback:
            self.on_status_callback("disconnected")

        # 自动重连
        if self.config['auto_reconnect'] and close_status_code != 1000:
            self._attempt_reconnect()

    def _on_event(self, response: dict):
        """
        处理服务器事件
        """
        try:
            event_type = response.get('type')

            if self.debug:
                logger.debug(f"事件: {event_type}")

            # 会话创建
            if event_type == 'session.created':
                session_id = response.get('session', {}).get('id')
                self.stats['session_id'] = session_id
                logger.info(f"会话已创建: {session_id}")

            # 用户语音识别结果
            elif event_type == 'conversation.item.input_audio_transcription.completed':
                transcript = response.get('transcript', '')
                if transcript:
                    logger.info(f"[用户语音识别]: {transcript}")
                    # 直接调用用户文本回调，不依赖状态判断
                    if self.on_user_text_callback:
                        try:
                            self.on_user_text_callback(transcript)
                        except Exception as e:
                            logger.error(f"用户文本回调错误: {e}")
                            import traceback
                            traceback.print_exc()

                    # 状态管理（仅用于防止自问自答）
                    if self.state_manager.current_state == ConversationState.LISTENING:
                        self.state_manager.on_user_speech_detected()
                        self.state_manager.on_user_speech_ended()

            # AI响应开始
            elif event_type in ['response.created', 'response.started']:
                logger.info(f"[状态] AI响应开始 - 事件: {event_type}")

                # 确保前一个响应已完全结束
                if self.audio_manager.is_playing:
                    logger.info("[状态] 检测到上一个响应还在播放，等待结束...")
                    # 给一点时间让播放循环结束
                    time.sleep(0.1)

                self.ai_response_in_progress = True
                self.ai_response_done = False
                self.state_manager.on_ai_response_started()

                # 立即彻底清空音频缓冲，防止残留
                self.audio_manager.clear_output_buffer()
                logger.info("[状态] 已清空音频缓冲区，准备新的响应")

                # 立即触发UI状态更新
                if self.on_status_callback:
                    self.on_status_callback("ai_speaking")
                    logger.info("[状态] 已发送ai_speaking状态到UI")

            # AI文本响应
            elif event_type == 'response.audio_transcript.delta':
                text = response.get('delta', '')
                if text:
                    # 修正AI名称引用
                    fixed_text = self._fix_ai_name(text)

                    if self.on_text_callback:
                        try:
                            self.on_text_callback(fixed_text)
                        except Exception as e:
                            logger.error(f"[Client] on_text_callback error: {e}")
                            import traceback
                            traceback.print_exc()

            # AI音频响应
            elif event_type == 'response.audio.delta':
                audio_b64 = response.get('delta', '')
                if audio_b64:
                    # 确保在AI_SPEAKING状态（防止状态过早转换）
                    if self.state_manager.current_state != ConversationState.AI_SPEAKING:
                        self.state_manager.on_ai_response_started()
                        logger.info("[状态] 收到音频，确保在AI_SPEAKING状态")

                    # 添加到播放队列
                    self.audio_manager.add_output_audio(audio_b64)

                    # 如果这是第一个音频片段，立即通知UI
                    if not self.ai_response_in_progress:
                        self.ai_response_in_progress = True
                        if self.on_status_callback:
                            self.on_status_callback("ai_speaking")
                            logger.info("[状态] 收到第一个音频片段，发送ai_speaking到UI")

            # 用户开始说话
            elif event_type == 'input_audio_buffer.speech_started':
                # 在AI说话期间忽略用户语音检测，避免意外打断
                if self.state_manager.current_state == ConversationState.AI_SPEAKING:
                    logger.debug("AI说话期间忽略语音检测事件")
                    return  # 直接返回，不处理此事件

                # 只在监听状态下响应
                if self.state_manager.current_state == ConversationState.LISTENING:
                    logger.info("检测到用户语音活动")
                    # 移除自动打断逻辑，只能通过手动操作打断
                    # if self.audio_manager.is_playing:
                    #     self.audio_manager.clear_output_buffer()

            # 响应完成
            elif event_type == 'response.done':
                logger.info("[状态] AI响应完成事件")
                self.ai_response_done = True
                self.ai_response_in_progress = False
                self.stats['messages_received'] += 1

                # 直接通知音频管理器响应已完成，不需要延迟
                if hasattr(self.audio_manager, 'mark_response_done'):
                    self.audio_manager.mark_response_done()
                    logger.info("[状态] 已标记音频管理器响应完成")

                # 通知UI响应已完成
                if self.on_response_complete_callback:
                    try:
                        self.on_response_complete_callback()
                        logger.info("[状态] 已触发响应完成回调")
                    except Exception as e:
                        logger.error(f"响应完成回调错误: {e}")
                        import traceback
                        traceback.print_exc()
                # 状态转换由音频播放结束触发

            # 错误事件
            elif event_type == 'error':
                error = response.get('error', {})
                logger.error(f"服务器错误: {error}")
                self.stats['errors'] += 1
                self.state_manager.transition_to(ConversationState.ERROR)

        except Exception as e:
            logger.error(f"事件处理错误: {e}")
            self.stats['errors'] += 1

    def _attempt_reconnect(self):
        """
        尝试重新连接
        """
        for attempt in range(self.config['max_reconnect_attempts']):
            logger.info(f"尝试重连 ({attempt + 1}/{self.config['max_reconnect_attempts']})")
            time.sleep(self.config['reconnect_interval'])

            try:
                self.connect()
                logger.info("重连成功")
                return
            except Exception as e:
                logger.error(f"重连失败: {e}")

        logger.error("达到最大重连次数，放弃重连")

    def connect(self):
        """
        建立连接
        """
        logger.info("正在连接到通义千问实时服务...")

        # 重置断开连接标志
        self.is_disconnecting = False

        # 重置响应状态标志
        self.ai_response_in_progress = False
        self.ai_response_done = False

        # 重置状态管理器（确保干净状态）
        self.state_manager.reset()

        # 重置统计信息
        self.stats = {
            'session_id': None,
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'start_time': 0
        }

        # 创建回调包装类
        class CallbackWrapper(OmniRealtimeCallback):
            def __init__(self, client):
                self.client = client

            def on_open(self):
                self.client._on_open()

            def on_close(self, close_status_code, close_msg):
                self.client._on_close(close_status_code, close_msg)

            def on_event(self, response: str):
                self.client._on_event(response)

        callback = CallbackWrapper(self)

        # 创建会话
        self.conversation = PatchedOmniRealtimeConversation(
            model=self.model,
            callback=callback,
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )

        # 连接
        self.conversation.connect(timeout=15)

        # 获取系统提示词（如果启用）
        instructions = None
        if self.use_voice_prompt:
            try:
                self._ensure_project_root_in_path()
                from system.config import get_prompt, config
                # 获取AI名称
                ai_name = config.system.ai_name
                # 获取对话风格提示词
                voice_prompt = get_prompt("conversation_style_prompt")
                # 获取对话风格提示词
                style_prompt = get_prompt("conversation_style_prompt")
                # 拼接完整的语音提示词
                instructions = f"{voice_prompt}\n\n{style_prompt}"
                logger.info(f"已加载语音提示词，AI名称: {ai_name}")
            except Exception as e:
                logger.warning(f"加载语音提示词失败: {e}")
                # 使用简单的默认指令
                instructions = "你是娜迦日达，一位充满智慧与温度的AI伙伴。请用简洁、自然的口语化方式回答问题。"

        # 尝试设置instructions参数
        session_config = {
            'output_modalities': [MultiModality.AUDIO, MultiModality.TEXT],
            'voice': self.voice,
            'input_audio_format': AudioFormat.PCM_16000HZ_MONO_16BIT,
            'output_audio_format': AudioFormat.PCM_24000HZ_MONO_16BIT,
            'enable_input_audio_transcription': True,
            'input_audio_transcription_model': 'gummy-realtime-v1',
            'enable_turn_detection': True,
            'turn_detection_type': 'server_vad',
        }

        # 如果有指令，尝试添加到配置中
        if instructions:
            session_config['instructions'] = instructions
            logger.info("尝试在update_session中设置instructions")

        self.conversation.update_session(**session_config)

        self.stats['start_time'] = time.time()
        logger.info("连接成功，系统就绪")

    def disconnect(self):
        """
        断开连接（增强版，确保资源完全释放）
        """
        logger.info("正在断开连接...")

        # 设置断开连接标志，防止状态转换
        self.is_disconnecting = True

        # 首先关闭自动重连，防止在断开过程中触发重连
        self.config['auto_reconnect'] = False

        try:
            # 1. 强制清理音频缓冲区（防止残留音频）
            if hasattr(self, 'audio_manager') and self.audio_manager:
                logger.debug("强制清理音频缓冲区...")

                # 先停止播放并彻底清理所有队列
                self.audio_manager.is_playing = False
                self.audio_manager.is_recording = False
                self.audio_manager.force_mute = True

                # 清空所有音频队列
                while not self.audio_manager.b64_output_queue.empty():
                    try:
                        self.audio_manager.b64_output_queue.get_nowait()
                    except:
                        pass

                while not self.audio_manager.output_queue.empty():
                    try:
                        self.audio_manager.output_queue.get_nowait()
                    except:
                        pass

                while not self.audio_manager.input_queue.empty():
                    try:
                        self.audio_manager.input_queue.get_nowait()
                    except:
                        pass

                # 清理回调函数，防止残留事件
                self.audio_manager.on_audio_input = None
                self.audio_manager.on_playback_started = None
                self.audio_manager.on_playback_ended = None

                # 停止音频管理器
                self.audio_manager.stop()
                # 不要设置为None，下次连接时会重新初始化

            # 2. 关闭会话（可能需要发送关闭消息）
            if self.conversation:
                try:
                    logger.debug("关闭会话连接...")
                    self.conversation.close()
                    self.conversation = None
                except Exception as e:
                    logger.error(f"关闭会话失败: {e}")

            # 3. 重置状态管理器
            if hasattr(self, 'state_manager') and self.state_manager:
                logger.debug("重置状态管理器...")
                self.state_manager.reset()

            # 4. 清除Live2D widget缓存（下次连接时重新获取）
            self._cached_live2d_widget = None
            self._live2d_widget_checked = False
            logger.debug("已清除Live2D widget缓存")

            # 5. 清理回调（防止内存泄漏）
            self.callback = None

            # 6. 清理统计信息
            self.stats = {
                'session_id': None,
                'messages_sent': 0,
                'messages_received': 0,
                'errors': 0,
                'start_time': 0
            }

            logger.info("连接已断开")

            # 重置断开连接标志
            self.is_disconnecting = False

        except Exception as e:
            logger.error(f"断开连接时发生错误: {e}", exc_info=True)

    def start(self):
        """
        启动客户端（兼容旧接口）
        """
        self.connect()

    def stop(self):
        """
        停止客户端（兼容旧接口）
        """
        self.disconnect()

    def is_active(self) -> bool:
        """
        检查客户端是否活跃
        """
        return (self.conversation is not None and
                self.audio_manager.is_running)

    def get_status(self) -> Dict[str, Any]:
        """
        获取客户端状态
        """
        runtime = time.time() - self.stats['start_time'] if self.stats['start_time'] > 0 else 0

        return {
            'is_active': self.is_active(),
            'session_id': self.stats['session_id'],
            'runtime': runtime,
            'stats': self.stats.copy(),
            'audio_status': self.audio_manager.get_status(),
            'state_status': self.state_manager.get_status()
        }

    def manual_interrupt(self):
        """
        手动打断AI说话
        仅在用户主动操作时调用
        """
        if self.state_manager.current_state == ConversationState.AI_SPEAKING:
            logger.info("用户手动打断AI说话")
            self.manual_interrupt_flag = True

            # 清空Base64队列，防止新的音频数据进入
            while not self.audio_manager.b64_output_queue.empty():
                try:
                    self.audio_manager.b64_output_queue.get_nowait()
                except:
                    pass

            # 调用音频管理器的打断方法
            if self.audio_manager:
                self.audio_manager.interrupt_playback()

            # 重置状态
            self.state_manager.transition_to(ConversationState.LISTENING)
            self.manual_interrupt_flag = False
            return True
        else:
            logger.debug("当前不在AI说话状态，无需打断")
            return False

    def update_config(self, config: Dict[str, Any]):
        """
        更新配置
        """
        # 更新客户端配置
        self.config.update(config)

        # 更新状态管理器配置
        if 'state_config' in config:
            self.state_manager.update_config(config['state_config'])

        # 更新音频管理器设置
        if 'vad_threshold' in config:
            self.audio_manager.set_vad_threshold(config['vad_threshold'])
        if 'echo_suppression' in config:
            self.audio_manager.set_echo_suppression(config['echo_suppression'])

        logger.info(f"配置已更新: {config}")

