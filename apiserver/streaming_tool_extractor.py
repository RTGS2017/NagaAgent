#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式文本切割器
负责将LLM流式输出按句切割并发送给语音集成（TTS）。不再检测或处理工具调用。
"""

import re
import json
import logging
import asyncio
import sys
import os
from typing import Callable, Optional, Dict, List
import threading

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from system.config import config, AI_NAME  # 导入配置系统
except ImportError:
    # 如果直接导入失败，尝试从父目录导入
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 工具调用解析/执行已不再需要

logger = logging.getLogger("StreamingToolCallExtractor")

# TTS 文本分节常量
MAX_SENTENCE_LENGTH = 50   # 缓冲池最大长度，超过即强制截断
MIN_SENTENCE_LENGTH = 30   # 30字开始找断点，50字强制截断
SECONDARY_BREAKS = "，、,— "  # 次要断点字符（逗号、顿号、空格、破折号）

class CallbackManager:
    """回调函数管理器 - 统一处理同步/异步回调"""
    
    def __init__(self):
        self.callbacks = {}
        self.callback_types = {}  # 缓存回调函数类型
    
    def register_callback(self, name: str, callback: Optional[Callable]):
        """注册回调函数"""
        self.callbacks[name] = callback
        if callback:
            # 缓存函数类型，避免重复检查
            self.callback_types[name] = asyncio.iscoroutinefunction(callback)
        else:
            self.callback_types[name] = False
    
    async def call_callback(self, name: str, *args, **kwargs):
        """统一调用回调函数"""
        callback = self.callbacks.get(name)
        if not callback:
            return None
            
        try:
            if self.callback_types.get(name, False):
                # 异步回调
                return await callback(*args, **kwargs)
            else:
                # 同步回调
                return callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"回调函数 {name} 执行错误: {e}")
            return None

class StreamingToolCallExtractor:
    """流式文本切割器 - 实时按句切割并发送给TTS，支持工具调用处理"""
    
    def __init__(self, mcp_manager=None):
        self.mcp_manager = mcp_manager
        self.text_buffer = ""  # 普通文本缓冲区
        self.complete_text = ""  # 完整文本内容
        self.sentence_endings = r"[。？！；\.\?\!\;]"  # 断句标点

        # 代码块跳过状态（不发送给 TTS）
        self.in_code_block = False
        self.backtick_count = 0

        # 使用回调管理器
        self.callback_manager = CallbackManager()
        
        # 语音集成（可选）
        self.voice_integration = None

        # 文字-语音同步：首个 TTS 就绪前缓冲前端显示
        self._pending_display = []  # [(text, type), ...]
        self._first_tts_ready = None  # threading.Event from voice_integration
        
        # 工具调用功能已移除
        self.tool_calls_queue = None
        
    def set_callbacks(self, 
                     on_text_chunk: Optional[Callable] = None,
                     voice_integration=None):
        """设置回调函数"""
        # 注册回调函数（仅文本块）
        self.callback_manager.register_callback("text_chunk", on_text_chunk)
        self.voice_integration = voice_integration
        # 获取语音同步事件（首个 TTS 片段就绪后解除文字缓冲）
        if voice_integration and hasattr(voice_integration, 'first_tts_ready'):
            self._first_tts_ready = voice_integration.first_tts_ready
        else:
            self._first_tts_ready = None
    
    async def process_text_chunk(self, text_chunk: str):
        """
        处理文本块，实时按句切割并发送给语音集成

        处理流程：
        1. 累积完整文本（用于最终保存）
        2. 逐字符检查：跳过代码块，检测句子结束符
        3. 遇到结束符时立即切割并发送完整句子到TTS
        4. 缓冲区超过 MAX_SENTENCE_LENGTH 时强制截断
        """
        if not text_chunk:
            return None

        # 文字-语音同步：首个 TTS 未就绪前缓冲文字，就绪后一次性 flush
        results = []
        if self._first_tts_ready and not self._first_tts_ready.is_set():
            self._pending_display.append((text_chunk, "chunk"))
        else:
            # flush 之前缓冲的文本
            if self._pending_display:
                for _pt, _pp in self._pending_display:
                    _r = await self.callback_manager.call_callback("text_chunk", _pt, _pp)
                    if _r:
                        results.append(_r)
                self._pending_display.clear()
            result = await self.callback_manager.call_callback("text_chunk", text_chunk, "chunk")
            if result:
                results.append(result)

        # 累积完整文本（用于最终保存到数据库）
        self.complete_text += text_chunk

        # 逐字符累积并检查分节条件
        for char in text_chunk:
            # --- 代码块检测：反引号计数 ---
            if char == '`':
                self.backtick_count += 1
                continue  # 反引号本身不进入 TTS 缓冲区
            else:
                if self.backtick_count >= 3:
                    # 切换代码块状态
                    if not self.in_code_block:
                        # 进入代码块前，把缓冲区文本发走并刷新语音缓冲区
                        self._send_and_flush_voice(self.text_buffer.strip())
                        self.text_buffer = ""
                    self.in_code_block = not self.in_code_block
                self.backtick_count = 0

            # 代码块内容跳过，不发送给 TTS
            if self.in_code_block:
                continue

            self.text_buffer += char

            # 条件1：遇到句子结束标点 → 立即截断发送
            if re.search(self.sentence_endings, char):
                sentence = self.text_buffer.strip()
                if sentence:
                    self._send_to_voice_integration(sentence)
                self.text_buffer = ""

            # 条件2：缓冲区超过最大长度且无标点 → 强制截断
            elif len(self.text_buffer) >= MAX_SENTENCE_LENGTH:
                cut_pos = self._find_best_cut_position(self.text_buffer)
                sentence = self.text_buffer[:cut_pos].strip()
                if sentence:
                    self._send_to_voice_integration(sentence)
                self.text_buffer = self.text_buffer[cut_pos:]

        return results if results else None

    def _find_best_cut_position(self, text: str) -> int:
        """在缓冲区中找到最佳截断位置（从后往前找次要断点）"""
        for i in range(len(text) - 1, MIN_SENTENCE_LENGTH - 1, -1):
            if text[i] in SECONDARY_BREAKS:
                return i + 1  # 断点字符包含在前一段
        # 无任何断点 → 直接在最大长度处截断
        return len(text)
    
    async def _flush_text_buffer(self):
        """刷新文本缓冲区 - 处理流式结束时的剩余文本"""
        # 处理末尾未结束的反引号序列
        if self.backtick_count >= 3:
            self.in_code_block = not self.in_code_block
        self.backtick_count = 0

        # 发送剩余文本并刷新语音缓冲区（确保无标点短文本也能进 TTS 队列）
        text = self.text_buffer
        self.text_buffer = ""
        self._send_and_flush_voice(text)
        return None
    
    def _send_to_voice_integration(self, text: str):
        """发送文本到语音集成（不阻塞文本流）"""
        if self.voice_integration:
            try:
                threading.Thread(
                    target=self.voice_integration.receive_text_chunk,
                    args=(text,),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"发送到语音集成失败: {e}")

    def _send_and_flush_voice(self, text: str = ""):
        """发送文本并刷新语音集成缓冲区，确保所有剩余文本进入 TTS 队列。
        在回复结束、进入代码块时调用。"""
        if self.voice_integration:
            try:
                def _do():
                    if text and text.strip():
                        self.voice_integration.receive_text_chunk(text)
                    self.voice_integration.finish_processing()
                threading.Thread(target=_do, daemon=True).start()
            except Exception as e:
                logger.error(f"发送并刷新语音集成失败: {e}")
    
    async def finish_processing(self):
        """完成处理，清理剩余内容"""
        # flush 所有未显示的缓冲文本（TTS 迟迟未就绪的兜底）
        if self._pending_display:
            for _pt, _pp in self._pending_display:
                await self.callback_manager.call_callback("text_chunk", _pt, _pp)
            self._pending_display.clear()
        await self._flush_text_buffer()
        return None
    
    def get_complete_text(self) -> str:
        """获取完整文本内容"""
        return self.complete_text
    
    def reset(self):
        """重置提取器状态"""
        self.text_buffer = ""
        self.complete_text = ""
        self.in_code_block = False
        self.backtick_count = 0
        self._pending_display.clear()
    
    async def process_streaming_response(self, llm_service, messages: List[Dict], 
                                       temperature: Optional[float] = None, voice_integration=None):
        """处理流式响应，整合LLM调用和TTS处理"""
        if voice_integration:
            self.voice_integration = voice_integration
        
        async for chunk in llm_service.stream_chat_with_context(messages, temperature):
            if chunk.startswith("data: "):
                try:
                    data_str = chunk[6:].strip()
                    if data_str == '[DONE]':
                        break
                    chunk_data = json.loads(data_str)
                    text = chunk_data.get("text", "")
                    if text:
                        await self.process_text_chunk(text)
                except Exception as e:
                    logger.error(f"处理流式响应块失败: {e}")
                    continue
            else:
                # 直接处理文本内容
                await self.process_text_chunk(chunk)
        
        # 完成处理
        await self.finish_processing()
        return self.get_complete_text()

