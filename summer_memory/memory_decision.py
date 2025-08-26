import logging
import json
import asyncio
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

# 添加项目根目录到路径
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from config import config
from openai import OpenAI, AsyncOpenAI

# 初始化OpenAI客户端
client = OpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

async_client = AsyncOpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

logger = logging.getLogger(__name__)

# 定义Pydantic模型
class MemoryQueryDecision(BaseModel):
    """记忆查询决策结果"""
    should_query: bool
    query_keywords: List[str]
    memory_types: List[str]
    query_reason: str
    confidence: float

class MemoryGenerationDecision(BaseModel):
    """记忆生成决策结果"""
    should_store: bool
    memory_type: str
    importance_score: float
    key_entities: List[str]
    storage_reason: str
    confidence: float

class MemoryDecisionResult(BaseModel):
    """记忆决策结果"""
    query_decision: MemoryQueryDecision
    generation_decision: MemoryGenerationDecision

class MemoryDecisionMaker:
    """记忆决策器"""
    
    def __init__(self):
        self.enabled = getattr(config.grag, 'memory_decision_enabled', True)
        
    async def decide_memory_query(self, user_question: str) -> MemoryQueryDecision:
        """决定是否需要查询记忆，以及查询什么"""
        if not self.enabled:
            return MemoryQueryDecision(
                should_query=False,
                query_keywords=[],
                memory_types=[],
                query_reason="记忆决策功能未启用",
                confidence=0.0
            )
        
        # 首先尝试结构化输出
        try:
            return await self._decide_memory_query_structured(user_question)
        except Exception as e:
            logger.warning(f"结构化输出失败，回退到传统方法: {e}")
            return await self._decide_memory_query_fallback(user_question)
    
    async def _decide_memory_query_structured(self, user_question: str) -> MemoryQueryDecision:
        """使用结构化输出进行记忆查询决策"""
        system_prompt = """
你是一个专业的记忆查询决策专家。你的任务是分析用户的问题，判断是否需要查询历史记忆，以及需要查询哪些类型的记忆。

记忆类型包括：
- fact: 事实记忆（人物、地点、物体等基本信息）
- process: 过程记忆（事件、活动、流程等）
- emotion: 情感记忆（情感、态度、偏好等）
- meta: 元记忆（关于记忆本身的记忆）

请仔细分析用户问题，提取关键信息，并做出决策。
"""
        
        max_retries = 1  # 减少重试次数，失败后立即回退
        
        for attempt in range(max_retries + 1):
            try:
                completion = await async_client.beta.chat.completions.parse(
                    model=config.api.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请分析以下用户问题，决定是否需要查询记忆：\n\n问题：{user_question}"}
                    ],
                    response_format=MemoryQueryDecision,
                    max_tokens=config.api.max_tokens,
                    temperature=0.3,
                    timeout=600 + (attempt * 20)
                )
                
                result = completion.choices[0].message.parsed
                logger.info(f"记忆查询决策成功: should_query={result.should_query}, keywords={result.query_keywords}")
                return result
                
            except Exception as e:
                logger.warning(f"结构化输出失败 (第{attempt + 1}次): {e}")
                # 立即回退到传统方法，不再重试
                break
        
        # 立即调用回退方法
        logger.info("结构化输出失败，立即回退到传统JSON解析方法")
        return await self._decide_memory_query_fallback(user_question)
    
    async def _decide_memory_query_fallback(self, user_question: str) -> MemoryQueryDecision:
        """传统JSON解析的记忆查询决策（回退方案）"""
        prompt = f"""
分析以下用户问题，决定是否需要查询历史记忆，并返回JSON格式的决策结果。

用户问题：{user_question}

请返回以下格式的JSON：
{{
    "should_query": true/false,
    "query_keywords": ["关键词1", "关键词2"],
    "memory_types": ["fact", "process"],
    "query_reason": "决策原因",
    "confidence": 0.8
}}

记忆类型说明：
- fact: 事实记忆（人物、地点、物体等基本信息）
- process: 过程记忆（事件、活动、流程等）
- emotion: 情感记忆（情感、态度、偏好等）
- meta: 元记忆（关于记忆本身的记忆）
"""
        
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                response = await async_client.chat.completions.create(
                    model=config.api.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=config.api.max_tokens,
                    temperature=0.3,
                    timeout=600
                )
                
                content = response.choices[0].message.content.strip()
                data = json.loads(content)
                
                result = MemoryQueryDecision(**data)
                logger.info(f"传统方法记忆查询决策成功: should_query={result.should_query}")
                return result
                
            except Exception as e:
                logger.error(f"传统方法失败 (第{attempt + 1}次): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)
        
        # 最终回退：简单规则
        return MemoryQueryDecision(
            should_query=len(user_question) > 10,
            query_keywords=[user_question[:10]],
            memory_types=["fact"],
            query_reason="默认决策",
            confidence=0.5
        )
    
    async def decide_memory_generation(self, user_question: str, ai_response: str) -> MemoryGenerationDecision:
        """决定是否需要生成记忆，以及生成什么类型的记忆"""
        if not self.enabled:
            return MemoryGenerationDecision(
                should_store=False,
                memory_type="fact",
                importance_score=0.0,
                key_entities=[],
                storage_reason="记忆决策功能未启用",
                confidence=0.0
            )
        
        # 首先尝试结构化输出
        try:
            return await self._decide_memory_generation_structured(user_question, ai_response)
        except Exception as e:
            logger.warning(f"结构化输出失败，回退到传统方法: {e}")
            return await self._decide_memory_generation_fallback(user_question, ai_response)
    
    async def _decide_memory_generation_structured(self, user_question: str, ai_response: str) -> MemoryGenerationDecision:
        """使用结构化输出进行记忆生成决策"""
        system_prompt = """
你是一个专业的记忆生成决策专家。你的任务是分析用户问题和AI回复的对话对，判断是否需要生成记忆，以及生成什么类型的记忆。

记忆类型包括：
- fact: 事实记忆（人物、地点、物体等基本信息）
- process: 过程记忆（事件、活动、流程等）
- emotion: 情感记忆（情感、态度、偏好等）
- meta: 元记忆（关于记忆本身的记忆）

重要性分数范围：0.0-1.0，分数越高表示越重要

请仔细分析对话内容，识别关键信息，并做出决策。
"""
        
        max_retries = 1  # 减少重试次数，失败后立即回退
        
        for attempt in range(max_retries + 1):
            try:
                completion = await async_client.beta.chat.completions.parse(
                    model=config.api.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请分析以下对话对，决定是否需要生成记忆：\n\n用户：{user_question}\n\nAI：{ai_response}"}
                    ],
                    response_format=MemoryGenerationDecision,
                    max_tokens=config.api.max_tokens,
                    temperature=0.3,
                    timeout=600 + (attempt * 20)
                )
                
                result = completion.choices[0].message.parsed
                logger.info(f"记忆生成决策成功: should_store={result.should_store}, type={result.memory_type}")
                return result
                
            except Exception as e:
                logger.warning(f"结构化输出失败 (第{attempt + 1}次): {e}")
                # 立即回退到传统方法，不再重试
                break
        
        # 立即调用回退方法
        logger.info("结构化输出失败，立即回退到传统JSON解析方法")
        return await self._decide_memory_generation_fallback(user_question, ai_response)
    
    async def _decide_memory_generation_fallback(self, user_question: str, ai_response: str) -> MemoryGenerationDecision:
        """传统JSON解析的记忆生成决策（回退方案）"""
        prompt = f"""
分析以下对话对，决定是否需要生成记忆，并返回JSON格式的决策结果。

用户：{user_question}
AI：{ai_response}

请返回以下格式的JSON：
{{
    "should_store": true/false,
    "memory_type": "fact",
    "importance_score": 0.8,
    "key_entities": ["实体1", "实体2"],
    "storage_reason": "决策原因",
    "confidence": 0.8
}}

记忆类型说明：
- fact: 事实记忆（人物、地点、物体等基本信息）
- process: 过程记忆（事件、活动、流程等）
- emotion: 情感记忆（情感、态度、偏好等）
- meta: 元记忆（关于记忆本身的记忆）
"""
        
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                response = await async_client.chat.completions.create(
                    model=config.api.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=config.api.max_tokens,
                    temperature=0.3,
                    timeout=600
                )
                
                content = response.choices[0].message.content.strip()
                data = json.loads(content)
                
                result = MemoryGenerationDecision(**data)
                logger.info(f"传统方法记忆生成决策成功: should_store={result.should_store}")
                return result
                
            except Exception as e:
                logger.error(f"传统方法失败 (第{attempt + 1}次): {e}")
                if attempt < max_retries:
                    await asyncio.sleep(1)
        
        # 最终回退：简单规则
        return MemoryGenerationDecision(
            should_store=len(user_question) > 5 and len(ai_response) > 10,
            memory_type="fact",
            importance_score=0.5,
            key_entities=[user_question[:10]],
            storage_reason="默认决策",
            confidence=0.5
        )

# 全局实例
memory_decision_maker = MemoryDecisionMaker()