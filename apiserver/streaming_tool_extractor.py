#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
流式文本切割器
负责将LLM流式输出按句切割并发送给语音集成（TTS）。不再检测或处理工具调用。
"""

import re
import logging
import asyncio
import sys
import os
from typing import Callable, Optional, Dict, List

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from system.config import config, AI_NAME  # 导入配置系统
except ImportError:
    # 如果直接导入失败，尝试从父目录导入
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 工具调用解析/执行已不再需要

logger = logging.getLogger("StreamingToolCallExtractor")

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
        
        # 使用回调管理器
        self.callback_manager = CallbackManager()
        
        # 语音集成（可选）
        self.voice_integration = None
        
        # 工具调用功能已移除
        self.tool_calls_queue = None
        
    def set_callbacks(self, 
                     on_text_chunk: Optional[Callable] = None,
                     voice_integration=None):
        """设置回调函数"""
        # 注册回调函数（仅文本块）
        self.callback_manager.register_callback("text_chunk", on_text_chunk)
        self.voice_integration = voice_integration
    
    async def process_text_chunk(self, text_chunk: str):
        """
        处理文本块，实时按句切割并发送给语音集成
        
        处理流程：
        1. 累积完整文本（用于最终保存）
        2. 逐字符检查句子结束符
        3. 遇到结束符时立即切割并发送完整句子到TTS
        4. 保留未完成的句子部分继续累积
        """
        if not text_chunk:
            return None
        
        
        # 调用文本块回调，将文本发送到前端
        results = []
        result = await self.callback_manager.call_callback("text_chunk", text_chunk, "chunk")
        if result:
            results.append(result)

        # 累积完整文本（用于最终保存到数据库）
        self.complete_text += text_chunk
            
        # 实时按句切割并发送到TTS
        for char in text_chunk:
            self.text_buffer += char
            # 检查是否遇到句子结束符（。？！；等）
            if re.search(self.sentence_endings, char):
                # 立即切割并发送完整句子到TTS
                sentences = re.split(self.sentence_endings, self.text_buffer)
                if len(sentences) > 1:
                    complete_sentence = sentences[0] + char
                    if complete_sentence.strip():
                        # 立即发送到语音集成进行TTS合成（不阻塞文本流）
                        self._send_to_voice_integration(complete_sentence)
                    # 保留未完成的句子部分，继续累积
                    remaining_sentences = [s for s in sentences[1:] if s.strip()]
                    self.text_buffer = "".join(remaining_sentences)
        return results if results else None
    
    async def _flush_text_buffer(self):
        """刷新文本缓冲区 - 处理流式结束时的剩余文本"""
        if self.text_buffer:
            # 立即发送剩余的未完成句子到语音集成（不阻塞）
            self._send_to_voice_integration(self.text_buffer)
            
            self.text_buffer = ""
            return None
        return None
    
    def _send_to_voice_integration(self, text: str):
        """发送文本到语音集成（不阻塞文本流）"""
        if self.voice_integration:
            try:
                # 在独立线程中处理TTS，不阻塞文本流
                import threading
                threading.Thread(
                    target=self.voice_integration.receive_text_chunk,
                    args=(text,),
                    daemon=True
                ).start()
            except Exception as e:
                logger.error(f"发送到语音集成失败: {e}")
    
    # 工具调用相关方法已移除，功能已迁移到background_analyzer
    
    async def finish_processing(self):
        """完成处理，清理剩余内容"""
        results = []
        
        # 处理剩余的文本
        if self.text_buffer:
            result = await self._flush_text_buffer()
            if result:
                results.append(result)
        
        return results if results else None
    
    def get_complete_text(self) -> str:
        """获取完整文本内容"""
        return self.complete_text
    
    def reset(self):
        """重置提取器状态"""
        self.text_buffer = ""
        self.complete_text = ""
    
    async def process_streaming_response(self, llm_service, messages: List[Dict], 
                                       temperature: float = 0.7, voice_integration=None):
        """处理流式响应，整合LLM调用和TTS处理"""
        if voice_integration:
            self.voice_integration = voice_integration
        
        async for chunk in llm_service.stream_chat_with_context(messages, temperature):
            if chunk.startswith("data: "):
                # 解码base64内容
                try:
                    import base64
                    data_str = chunk[6:].strip()
                    if data_str == '[DONE]':
                        break
                    decoded = base64.b64decode(data_str).decode('utf-8')
                    await self.process_text_chunk(decoded)
                except Exception as e:
                    logger.error(f"处理流式响应块失败: {e}")
                    continue
            else:
                # 直接处理文本内容
                await self.process_text_chunk(chunk)
        
        # 完成处理
        await self.finish_processing()
        return self.get_complete_text()

