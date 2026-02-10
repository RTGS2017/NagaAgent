#!/usr/bin/env python3
"""
LLM服务模块
提供统一的LLM调用接口，替代conversation_core.py中的get_response方法
使用 LiteLLM 统一处理多模型的 COT/reasoning_content
"""

import logging
import sys
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import litellm
from litellm import acompletion
from fastapi import FastAPI, HTTPException
from system.config import config

# 配置日志
logger = logging.getLogger("LLMService")


@dataclass
class LLMResponse:
    """LLM响应结构，包含内容和推理过程"""
    content: str
    reasoning_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"content": self.content}
        if self.reasoning_content:
            result["reasoning_content"] = self.reasoning_content
        return result

class LLMService:
    """LLM服务类 - 使用 LiteLLM 提供统一的LLM调用接口，支持 COT/reasoning_content"""

    def __init__(self):
        self._initialized = False
        self._initialize_client()

    def _initialize_client(self):
        """初始化 LiteLLM 配置"""
        try:
            # 配置 LiteLLM 使用自定义 base_url
            litellm.api_key = config.api.api_key
            # 设置自定义端点（如果不是标准 OpenAI）
            if config.api.base_url and "openai.com" not in config.api.base_url:
                litellm.api_base = config.api.base_url.rstrip('/') + '/'
            self._initialized = True
            logger.info("LLM服务 (LiteLLM) 初始化成功")
        except Exception as e:
            logger.error(f"LLM服务初始化失败: {e}")
            self._initialized = False

    def _get_model_name(self) -> str:
        """获取 LiteLLM 格式的模型名称"""
        model = config.api.model
        base_url = config.api.base_url.lower() if config.api.base_url else ""

        # 根据 base_url 判断提供商，添加正确的前缀
        if "deepseek" in base_url:
            if not model.startswith("deepseek/"):
                return f"deepseek/{model}"
        elif "openrouter" in base_url:
            if not model.startswith("openrouter/"):
                return f"openrouter/{model}"
        elif "openai.com" in base_url:
            # OpenAI 不需要前缀
            return model
        else:
            # 对于其他自定义端点，使用 openai/ 前缀以兼容 OpenAI 格式
            if not model.startswith("openai/"):
                return f"openai/{model}"
        return model

    async def get_response(self, prompt: str, temperature: float = 0.7) -> str:
        """为其他模块提供API调用接口（保持向后兼容，只返回 content）"""
        response = await self.get_response_with_reasoning(prompt, temperature)
        return response.content

    async def get_response_with_reasoning(self, prompt: str, temperature: float = 0.7) -> LLMResponse:
        """为其他模块提供API调用接口，返回包含 reasoning_content 的完整响应"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        try:
            response = await acompletion(
                model=self._get_model_name(),
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=config.api.max_tokens,
                api_key=config.api.api_key,
                api_base=config.api.base_url.rstrip('/') + '/' if config.api.base_url else None
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "",
                reasoning_content=getattr(message, 'reasoning_content', None)
            )
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return LLMResponse(content=f"API调用出错: {str(e)}")

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self._initialized

    async def chat_with_context(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """带上下文的聊天调用（保持向后兼容，只返回 content）"""
        response = await self.chat_with_context_and_reasoning(messages, temperature)
        return response.content

    async def chat_with_context_and_reasoning(self, messages: List[Dict], temperature: float = 0.7) -> LLMResponse:
        """带上下文的聊天调用，返回包含 reasoning_content 的完整响应"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        try:
            response = await acompletion(
                model=self._get_model_name(),
                messages=messages,
                temperature=temperature,
                max_tokens=config.api.max_tokens if hasattr(config.api, 'max_tokens') else None,
                api_key=config.api.api_key,
                api_base=config.api.base_url.rstrip('/') + '/' if config.api.base_url else None
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "",
                reasoning_content=getattr(message, 'reasoning_content', None)
            )
        except Exception as e:
            logger.error(f"上下文聊天调用失败: {e}")
            return LLMResponse(content=f"聊天调用出错: {str(e)}")

    async def stream_chat_with_context(self, messages: List[Dict], temperature: float = 0.7):
        """带上下文的流式聊天调用，支持 reasoning_content 交织输出

        Yields:
            格式为 "data: <base64_json>\n\n" 的 SSE 事件
            JSON 结构: {"type": "content"|"reasoning", "text": "..."}
        """
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                yield self._format_sse_chunk("content", "LLM服务不可用: 客户端初始化失败")
                return

        try:
            response = await acompletion(
                model=self._get_model_name(),
                messages=messages,
                temperature=temperature,
                max_tokens=config.api.max_tokens if hasattr(config.api, 'max_tokens') else None,
                stream=True,
                api_key=config.api.api_key,
                api_base=config.api.base_url.rstrip('/') + '/' if config.api.base_url else None
            )

            async for chunk in response:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 处理 reasoning_content（思考过程）
                reasoning = getattr(delta, 'reasoning_content', None)
                if reasoning:
                    yield self._format_sse_chunk("reasoning", reasoning)

                # 处理 content（正式回答）
                content = getattr(delta, 'content', None)
                if content:
                    yield self._format_sse_chunk("content", content)

        except Exception as e:
            logger.error(f"流式聊天调用失败: {e}")
            yield self._format_sse_chunk("content", f"流式调用出错: {str(e)}")

    def _format_sse_chunk(self, chunk_type: str, text: str) -> str:
        """格式化 SSE 数据块

        Args:
            chunk_type: "content" 或 "reasoning"
            text: 文本内容

        Returns:
            SSE 格式的数据块
        """
        import base64
        import json
        data = {"type": chunk_type, "text": text}
        b64 = base64.b64encode(json.dumps(data, ensure_ascii=False).encode('utf-8')).decode('ascii')
        return f"data: {b64}\n\n"

# 全局LLM服务实例
_llm_service: Optional[LLMService] = None

def get_llm_service() -> LLMService:
    """获取全局LLM服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

# 创建独立的LLM服务API
llm_app = FastAPI(
    title="LLM Service API",
    description="LLM服务API",
    version="1.0.0"
)

@llm_app.post("/llm/chat")
async def llm_chat(request: Dict[str, Any]):
    """LLM聊天接口 - 为其他模块提供LLM调用服务"""
    try:
        prompt = request.get("prompt", "")
        temperature = request.get("temperature", 0.7)
        
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt参数不能为空")
        
        llm_service = get_llm_service()
        response = await llm_service.get_response(prompt, temperature)
        
        return {
            "status": "success",
            "response": response,
            "temperature": temperature
        }
        
    except Exception as e:
        logger.error(f"LLM聊天接口异常: {e}")
        raise HTTPException(status_code=500, detail=f"LLM服务异常: {str(e)}")

