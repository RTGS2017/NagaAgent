#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务去重器 - 基于博弈论的重复检测机制
使用LLM判断任务是否重复
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class TaskDeduper:
    """
    基于博弈论的任务去重器
    使用LLM判断新任务是否与现有任务语义重复（等价或严格子集）
    """

    def __init__(self):
        # 使用Naga的配置系统
        try:
            from system.config import config
            from langchain_openai import ChatOpenAI
            
            self.llm = ChatOpenAI(
                model=config.api.model,
                base_url=config.api.base_url,
                api_key=config.api.api_key,
                temperature=0,
            )
        except ImportError:
            # 降级配置
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    model="gpt-3.5-turbo",
                    base_url="https://api.openai.com/v1",
                    api_key="sk-placeholder",
                    temperature=0,
                )
            except ImportError:
                self.llm = None
                logger.warning("无法导入LLM，任务去重功能将不可用")

    def _build_prompt(self, new_task: str, candidates: List[Tuple[str, str]]) -> str:
        lines = ["New task:", new_task.strip(), "\nExisting tasks:"]
        for tid, desc in candidates:
            lines.append(f"- id={tid}: {desc}")
        lines.append(
            "\nTask: Decide whether the NEW task duplicates ANY existing task (same goal or a strict subset). "
            "Ignore superficial wording differences. Scan the existing tasks; "
            "if you find a duplicate, immediately return that task's id. If none are duplicate, use null. "
            "Output this strict JSON array (no prose): [matched_id_or_null, duplicate_boolean]."
        )
        return "\n".join(lines)
    
    def judge(self, new_task: str, candidates: List[Tuple[str, str]]) -> Dict[str, Any]:
        if not new_task or not candidates or not self.llm:
            return {"duplicate": False, "matched_id": None}

        try:
            prompt = self._build_prompt(new_task, candidates)
            resp = self.llm.invoke([
                {"role": "system", "content": "You are a careful deduplication judge."},
                {"role": "user", "content": prompt},
            ])
            text = (resp.content or "").strip()
            
            try:
                if text.startswith("```"):
                    text = text.replace("```json", "").replace("```", "").strip()
                data = json.loads(text)
                # Preferred contract: JSON array [matched_id_or_null, duplicate_boolean]
                if isinstance(data, list) and len(data) >= 2:
                    matched_id = data[0]
                    duplicate = bool(data[1])
                    return {"duplicate": duplicate, "matched_id": matched_id}
                # Fallback: accept dict shape if model returns it
                if isinstance(data, dict):
                    return {
                        "duplicate": bool(data.get("duplicate", False)),
                        "matched_id": data.get("matched_id")
                    }
                # Unknown shape
                return {"duplicate": False, "matched_id": None}
            except Exception:
                return {"duplicate": False, "matched_id": None}
        except Exception as e:
            logger.error(f"任务去重判断失败: {e}")
            return {"duplicate": False, "matched_id": None}


# 全局去重器实例
_task_deduper = None

def get_task_deduper() -> TaskDeduper:
    """获取全局任务去重器实例"""
    global _task_deduper
    if _task_deduper is None:
        _task_deduper = TaskDeduper()
    return _task_deduper
