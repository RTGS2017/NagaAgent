#!/usr/bin/env python3
"""
LLM服务模块
提供统一的LLM调用接口，替代conversation_core.py中的get_response方法
"""

import logging
import sys
import os
from typing import Optional, Dict, Any, List

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nagaagent_core.core import AsyncOpenAI
from nagaagent_core.api import FastAPI, HTTPException
from system.config import config

# 配置日志
logger = logging.getLogger("LLMService")

class LLMService:
    """LLM服务类 - 提供统一的LLM调用接口"""
    
    def __init__(self):
        self.async_client: Optional[AsyncOpenAI] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """初始化OpenAI客户端"""
        try:
            self.async_client = AsyncOpenAI(
                api_key=config.api.api_key, 
                base_url=config.api.base_url.rstrip('/') + '/'
            )
            logger.info("LLM服务客户端初始化成功")
        except Exception as e:
            logger.error(f"LLM服务客户端初始化失败: {e}")
            self.async_client = None
    
    async def get_response(self, prompt: str, temperature: float = 0.7) -> str:
        """为其他模块提供API调用接口"""
        if not self.async_client:
            self._initialize_client()
            if not self.async_client:
                return f"LLM服务不可用: 客户端初始化失败"
        
        try:
            response = await self.async_client.chat.completions.create(
                model=config.api.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=config.api.max_tokens
            )
            return response.choices[0].message.content
        except RuntimeError as e:
            if "handler is closed" in str(e):
                logger.debug(f"忽略连接关闭异常，重新创建客户端: {e}")
                # 重新创建客户端并重试
                self._initialize_client()
                if self.async_client:
                    response = await self.async_client.chat.completions.create(
                        model=config.api.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=config.api.max_tokens
                    )
                    return response.choices[0].message.content
                else:
                    return f"LLM服务不可用: 重连失败"
            else:
                logger.error(f"API调用失败: {e}")
                return f"API调用出错: {str(e)}"
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return f"API调用出错: {str(e)}"
    
    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self.async_client is not None
    
    async def chat_with_context(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """带上下文的聊天调用"""
        if not self.async_client:
            self._initialize_client()
            if not self.async_client:
                return f"LLM服务不可用: 客户端初始化失败"
        
        try:
            response = await self.async_client.chat.completions.create(
                model=config.api.model,
                messages=messages,
                temperature=temperature,
                max_tokens=config.api.max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"上下文聊天调用失败: {e}")
            return f"聊天调用出错: {str(e)}"
    
    async def stream_chat_with_context(self, messages: List[Dict], temperature: float = 0.7):
        """带上下文的流式聊天调用"""
        if not self.async_client:
            self._initialize_client()
            if not self.async_client:
                yield f"LLM服务不可用: 客户端初始化失败"
                return
        
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=180, connect=60, sock_read=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{config.api.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.api.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "Connection": "keep-alive"
                    },
                    json={
                        "model": config.api.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": config.api.max_tokens,
                        "stream": True
                    }
                ) as resp:
                    if resp.status != 200:
                        yield f"LLM API调用失败 (状态码: {resp.status})"
                        return
                    
                    async for chunk in resp.content.iter_chunked(1024):
                        if not chunk:
                            break
                        try:
                            data = chunk.decode('utf-8')
                            lines = data.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line.startswith('data: '):
                                    data_str = line[6:]
                                    if data_str == '[DONE]':
                                        return
                                    try:
                                        import json
                                        data = json.loads(data_str)
                                        if 'choices' in data and len(data['choices']) > 0:
                                            delta = data['choices'][0].get('delta', {})
                                            if 'content' in delta:
                                                import base64
                                                content = delta['content']
                                                b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
                                                yield f"data: {b64}\n\n"
                                    except json.JSONDecodeError:
                                        continue
                        except UnicodeDecodeError:
                            continue
        except Exception as e:
            logger.error(f"流式聊天调用失败: {e}")
            yield f"data: 流式调用出错: {str(e)}\n\n"

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

