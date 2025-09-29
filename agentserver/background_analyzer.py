#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台意图分析器 - 基于博弈论的对话分析机制
分析对话片段，提取潜在任务意图
"""

import asyncio
import logging
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from system.prompt_repository import get_prompt

logger = logging.getLogger(__name__)

class ConversationAnalyzer:
    """
    对话分析器模块：分析语音对话轮次以推断潜在任务意图
    输入是跨服务器的文本转录片段；输出是零个或多个标准化的任务查询
    """
    def __init__(self):
        # 使用Naga的配置系统
        try:
            from system.config import config
            self.llm = ChatOpenAI(
                model=config.api.model,
                base_url=config.api.base_url,
                api_key=config.api.api_key,
                temperature=0
            )
        except ImportError:
            # 降级配置
            self.llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                base_url="https://api.openai.com/v1",
                api_key="sk-placeholder",
                temperature=0
            )
            logger.warning("无法导入配置，使用默认LLM设置")

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        lines = []
        for m in messages[-20:]:
            role = m.get('role', 'user')
            text = m.get('text', '')
            lines.append(f"{role}: {text}")
        conversation = "\n".join(lines)
        return get_prompt("conversation_analyzer_prompt", conversation=conversation)

    def analyze(self, messages: List[Dict[str, str]]):
        prompt = self._build_prompt(messages)
        resp = self.llm.invoke([
            {"role": "system", "content": "You are a precise task intent extractor."},
            {"role": "user", "content": prompt},
        ])
        text = resp.content.strip()
        import json
        try:
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
        except Exception as e:
            print(f"Analyzer parse error: {e}")
            data = {"tasks": [], "reason": "parse error", "raw": text}
        return data


class BackgroundAnalyzer:
    """后台分析器 - 管理异步意图分析"""
    
    def __init__(self):
        self.analyzer = ConversationAnalyzer()
        self.running_analyses = {}
    
    async def analyze_intent_async(self, messages: List[Dict[str, str]], session_id: str):
        """异步意图分析 - 基于博弈论的背景分析机制"""
        try:
            loop = asyncio.get_running_loop()
            # Offload sync LLM call to threadpool to avoid blocking event loop
            analysis = await loop.run_in_executor(None, self.analyzer.analyze, messages)
        except Exception as e:
            logger.error(f"意图分析失败: {e}")
            return {"has_tasks": False, "reason": f"分析失败: {e}", "tasks": [], "priority": "low"}
        
        try:
            import uuid as _uuid
            tasks = analysis.get("tasks", []) if isinstance(analysis, dict) else []
            
            if not tasks:
                logger.debug(f"会话 {session_id} 未发现可执行任务")
                return {"has_tasks": False, "reason": "未发现可执行任务", "tasks": [], "priority": "low"}
            
            logger.info(f"会话 {session_id} 发现 {len(tasks)} 个潜在任务")
            
            # 返回分析结果
            result = {
                "has_tasks": True,
                "reason": analysis.get("reason", "发现潜在任务"),
                "tasks": tasks,
                "priority": "medium"  # 可以根据任务数量或类型调整优先级
            }
            
            # 记录任务详情
            for task in tasks:
                logger.info(f"发现任务: {task}")
            
            return result
                
        except Exception as e:
            logger.error(f"任务处理失败: {e}")
            return {"has_tasks": False, "reason": f"处理失败: {e}", "tasks": [], "priority": "low"}


# 全局分析器实例
_background_analyzer = None

def get_background_analyzer() -> BackgroundAnalyzer:
    """获取全局后台分析器实例"""
    global _background_analyzer
    if _background_analyzer is None:
        _background_analyzer = BackgroundAnalyzer()
    return _background_analyzer
