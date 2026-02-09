#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
本地语音适配器
使用 OpenAI Whisper API 进行语音转文本
"""

import logging
import threading
import time
from typing import Optional, Dict, Any
import wave
import tempfile
import os
from collections import deque

from ..core.base_client import BaseVoiceClient
from ..core.audio_manager import AudioManager
from ..core.state_manager import StateManager

logger = logging.getLogger(__name__)


class LocalVoiceClientAdapter(BaseVoiceClient):
    """
    本地语音客户端适配器
    使用 OpenAI Compatible API 进行语音识别
    """

    # 默认配置
    DEFAULT_MODEL = 'koboldcpp/GLM-ASR-Nano-1.6B-2512-Q4_K'
    DEFAULT_LANGUAGE = 'zh'

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **kwargs
    ):
        """
        初始化本地适配器

        参数:
            api_key: API密钥
            model: 模型名称（默认: koboldcpp/GLM-ASR-Nano-1.6B-2512-Q4_K）
            language: 语言代码（默认: zh）
            **kwargs: 其他参数
        """
        super().__init__(api_key, **kwargs)

        self.model = model or self.DEFAULT_MODEL
        self.language = language or self.DEFAULT_LANGUAGE

        # 音频配置
        self.input_sample_rate = kwargs.get('input_sample_rate', 16000)
        self.chunk_size_ms = kwargs.get('chunk_size_ms', 200)
        self.vad_threshold = kwargs.get('vad_threshold', 0.02)
        self.echo_suppression = kwargs.get('echo_suppression', True)

        # 音频管理器
        self._audio_manager = AudioManager(
            input_sample_rate=self.input_sample_rate,
            output_sample_rate=24000,
            chunk_size_ms=self.chunk_size_ms,
            vad_threshold=self.vad_threshold,
            echo_suppression=self.echo_suppression
        )

        # 状态管理器
        self._state_manager = StateManager(debug=self.debug)

        # 音频缓冲区（用于累积语音数据）
        self._audio_buffer = deque()
        self._is_speaking = False
        self._silence_counter = 0
        self._silence_threshold = 10  # 连续静音块数阈值

        # OpenAI 客户端
        self._openai_client = None

        # 统计信息
        self.stats = {
            'session_id': None,
            'transcriptions': 0,
            'errors': 0,
            'start_time': 0
        }

        # 设置组件回调
        self._setup_callbacks()

        logger.info(f"LocalVoiceClientAdapter initialized: model={self.model}, language={self.language}")

    def _setup_callbacks(self):
        """设置回调桥接"""
        def user_text_bridge(text):
            if self.on_user_text_callback:
                self.on_user_text_callback(text)

        def status_bridge(status):
            if self.on_status_callback:
                self.on_status_callback(status)

        # 设置音频管理器的回调
        self._audio_manager.on_audio_input = self._on_audio_input
        self._audio_manager.on_playback_started = self._on_playback_started
        self._audio_manager.on_playback_ended = self._on_playback_ended

        # 设置状态管理器的回调
        self._state_manager.on_user_text_callback = user_text_bridge
        self._state_manager.on_status_callback = status_bridge

        logger.debug("Callbacks bridged successfully")

    def _init_openai_client(self):
        """初始化 OpenAI 客户端"""
        try:
            from openai import OpenAI
            self._openai_client = OpenAI(base_url="http://127.0.0.1:5001/v1",api_key=self.api_key)
            logger.info("OpenAI client initialized successfully")
            return True
        except ImportError:
            logger.error("OpenAI library not installed. Please install: pip install openai")
            self._trigger_error(ImportError("OpenAI library not installed"))
            return False
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            self._trigger_error(e)
            return False

    def connect(self) -> bool:
        """
        建立连接

        返回:
            bool: 连接是否成功
        """
        try:
            # 初始化 OpenAI 客户端
            if not self._init_openai_client():
                return False

            # 初始化音频管理器
            if not self._audio_manager.initialize():
                logger.error("Failed to initialize audio manager")
                return False

            # 启动音频管理器
            self._audio_manager.start()

            self.stats['start_time'] = time.time()
            self.stats['session_id'] = f"local_{int(time.time())}"

            self._trigger_status('connected')
            logger.info("LocalVoiceClientAdapter connected successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self._trigger_error(e)
            return False

    def disconnect(self):
        """断开连接"""
        try:
            # 停止音频管理器
            self._audio_manager.stop()

            # 清空音频缓冲区
            self._audio_buffer.clear()

            self._trigger_status('disconnected')
            logger.info("LocalVoiceClientAdapter disconnected")

        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            self._trigger_error(e)

    def is_active(self) -> bool:
        """检查客户端是否活跃"""
        return self._audio_manager.is_running

    def manual_interrupt(self) -> bool:
        """手动打断AI说话"""
        try:
            # 清空音频缓冲区
            self._audio_buffer.clear()
            self._is_speaking = False
            logger.info("Manual interrupt triggered")
            return True
        except Exception as e:
            logger.error(f"Error during manual interrupt: {e}")
            self._trigger_error(e)
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        return {
            'active': self.is_active(),
            'provider': 'local',
            'model': self.model,
            'language': self.language,
            'stats': self.stats,
            'state': self._state_manager.get_state().value if self._state_manager else 'unknown'
        }

    def _on_audio_input(self, audio_data: bytes):
        """
        处理音频输入

        参数:
            audio_data: 音频数据
        """
        try:
            # 计算音频能量（简单的 VAD）
            import numpy as np
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            energy = np.mean(np.abs(audio_array)) / 32768.0  # 归一化到 0-1

            # 检测语音活动
            if energy > self.vad_threshold:
                # 检测到语音
                if not self._is_speaking:
                    self._is_speaking = True
                    self._silence_counter = 0
                    self._trigger_status('listening')
                    logger.debug("Speech detected")

                # 累积音频数据
                self._audio_buffer.append(audio_data)
                self._silence_counter = 0
            else:
                # 检测到静音
                if self._is_speaking:
                    self._silence_counter += 1

                    # 如果连续静音超过阈值，认为语音结束
                    if self._silence_counter >= self._silence_threshold:
                        self._is_speaking = False
                        self._trigger_status('processing')
                        logger.debug("Speech ended, transcribing...")
                        # 在新线程中进行转录，避免阻塞音频输入
                        threading.Thread(
                            target=self._transcribe_audio,
                            daemon=True
                        ).start()

        except Exception as e:
            logger.error(f"Error processing audio input: {e}")
            self._trigger_error(e)

    def _on_playback_started(self):
        """播放开始回调"""
        logger.debug("Playback started")
        self._trigger_status('ai_speaking')

    def _on_playback_ended(self):
        """播放结束回调"""
        logger.debug("Playback ended")
        self._trigger_status('listening')

    def _transcribe_audio(self):
        """使用 OpenAI Whisper API 转录音频"""
        try:
            # 获取累积的音频数据
            if not self._audio_buffer:
                logger.debug("No audio data to transcribe")
                return

            # 合并所有音频块
            audio_data = b''.join(self._audio_buffer)

            if len(audio_data) < 1000:
                logger.debug("Not enough audio data for transcription")
                return

            logger.info(f"Transcribing audio data: {len(audio_data)} bytes")

            # 创建临时 WAV 文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # 写入 WAV 文件
                with wave.open(temp_path, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)  # 16-bit
                    wav_file.setframerate(self.input_sample_rate)
                    wav_file.writeframes(audio_data)

                # 调用 OpenAI Whisper API
                with open(temp_path, 'rb') as audio_file:
                    response = self._openai_client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        language=self.language
                    )

                # 获取转录文本
                transcribed_text = response.text.strip()

                if transcribed_text:
                    logger.info(f"Transcribed text: {transcribed_text}")
                    self.stats['transcriptions'] += 1

                    # 触发用户文本回调
                    if self.on_user_text_callback:
                        self.on_user_text_callback(transcribed_text)

            finally:
                # 删除临时文件
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

            # 清空音频缓冲区
            self._audio_buffer.clear()

        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            self.stats['errors'] += 1
            self._trigger_error(e)
            # 清空音频缓冲区
            self._audio_buffer.clear()

    def set_callbacks(self, **kwargs):
        """重载设置回调函数"""
        super().set_callbacks(**kwargs)
        # 重新桥接回调
        self._setup_callbacks()

    @property
    def audio_manager(self):
        """暴露音频管理器"""
        return self._audio_manager if hasattr(self, '_audio_manager') else None

    @property
    def state_manager(self):
        """暴露状态管理器"""
        return self._state_manager if hasattr(self, '_state_manager') else None
