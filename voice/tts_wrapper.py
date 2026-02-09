# -*- coding: utf-8 -*-
"""
TTS包装器 - 解决asyncio事件循环冲突问题
"""

import asyncio
import threading
import logging
import tempfile
import edge_tts

logger = logging.getLogger(__name__)


class TTSWrapper:
    """TTS包装器，处理asyncio和线程安全问题"""

    def __init__(self):
        self._loop = None
        self._thread = None
        self._start_loop()

    def _start_loop(self):
        """在独立线程中启动事件循环"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        # 等待事件循环启动
        while self._loop is None:
            threading.Event().wait(0.01)

    def generate_speech_safe(self, text, voice, response_format="mp3", speed=1.0):
        """线程安全的TTS生成"""
        try:
            # 在独立的事件循环中运行异步任务
            future = asyncio.run_coroutine_threadsafe(
                self._generate_audio_async(text, voice, response_format, speed),
                self._loop
            )

            # 等待结果（最多30秒）
            result = future.result(timeout=30)
            return result

        except Exception as e:
            logger.error(f"[TTS包装器] 生成语音失败: {e}")
            import traceback
            traceback.print_exc()

            # 回退方案：尝试直接使用edge_tts的同步方法
            return self._fallback_generate(text, voice, response_format, speed)

    async def _generate_audio_async(self, text, voice, response_format, speed):
        """异步生成音频"""
        try:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{response_format}")
            temp_path = temp_file.name
            temp_file.close()

            # 转换速度为edge_tts格式
            speed_rate = self._speed_to_rate(speed)

            logger.info(f"[TTS包装器] 生成语音: voice={voice}, speed={speed_rate}, format={response_format}")

            # 使用edge_tts生成音频
            communicator = edge_tts.Communicate(text=text, voice=voice, rate=speed_rate)
            await communicator.save(temp_path)

            logger.info(f"[TTS包装器] 语音生成成功: {temp_path}")
            return temp_path

        except Exception as e:
            logger.error(f"[TTS包装器] 异步生成失败: {e}")
            raise

    def _fallback_generate(self, text, voice, response_format, speed):
        """回退生成方案"""
        try:
            logger.info("[TTS包装器] 使用回退方案生成语音")

            # 创建新的事件循环（在当前线程）
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # 创建临时文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{response_format}")
                temp_path = temp_file.name
                temp_file.close()

                # 转换速度
                speed_rate = self._speed_to_rate(speed)

                # 同步运行异步任务
                communicator = edge_tts.Communicate(text=text, voice=voice, rate=speed_rate)
                loop.run_until_complete(communicator.save(temp_path))

                logger.info(f"[TTS包装器] 回退方案成功: {temp_path}")
                return temp_path

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"[TTS包装器] 回退方案失败: {e}")

            # 最终回退：创建一个静音文件
            return self._create_silent_file(response_format)

    def _speed_to_rate(self, speed):
        """转换速度到edge-tts格式"""
        if speed < 0 or speed > 2:
            speed = 1.0
        percentage_change = (speed - 1) * 100
        return f"{percentage_change:+.0f}%"

    def _create_silent_file(self, response_format):
        """创建静音文件作为最终回退"""
        logger.warning("[TTS包装器] 创建静音文件作为回退")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{response_format}")
        temp_path = temp_file.name
        temp_file.close()
        return temp_path

    def cleanup(self):
        """清理资源"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread:
                self._thread.join(timeout=1.0)


# 全局TTS包装器实例
_global_tts_wrapper = None


def get_tts_wrapper():
    """获取全局TTS包装器实例"""
    global _global_tts_wrapper
    if _global_tts_wrapper is None:
        _global_tts_wrapper = TTSWrapper()
    return _global_tts_wrapper


def generate_speech_safe(text, voice, response_format="mp3", speed=1.0):
    """安全的TTS生成函数（供外部调用）"""
    wrapper = get_tts_wrapper()
    return wrapper.generate_speech_safe(text, voice, response_format, speed)