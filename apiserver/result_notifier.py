#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果通知器 - 基于博弈论的任务结果通知机制
处理任务完成后的结果通知和状态更新
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)

class ResultNotifier:
    """结果通知器 - 基于博弈论的结果处理机制"""
    
    def __init__(self):
        self.notification_url = "http://localhost:8000/api/notify_task_result"  # 主服务器通知地址
        self.poller_task: Optional[asyncio.Task] = None
        self._start_poller()
    
    def _start_poller(self):
        """启动结果轮询器"""
        if self.poller_task is None:
            self.poller_task = asyncio.create_task(self._poll_results_loop())
    
    async def _poll_results_loop(self):
        """结果轮询循环 - 基于博弈论的结果处理机制"""
        while True:
            await asyncio.sleep(0.1)
            try:
                # 这里可以添加结果队列处理逻辑
                # 暂时保持空实现，等待集成到任务调度器
                pass
            except Exception as e:
                logger.error(f"结果轮询错误: {e}")
                await asyncio.sleep(0.1)
    
    def _build_result_summary(self, task_info: Dict[str, Any]) -> str:
        """构建结果摘要 - 基于博弈论的结果处理机制"""
        try:
            summary = "任务已完成"
            
            # 构建结果摘要
            result = task_info.get("result")
            if isinstance(result, dict):
                detail = result.get("result") or result.get("message") or result.get("reason") or ""
            else:
                detail = str(result) if result is not None else ""
            
            # 包含任务描述
            params = task_info.get("params") or {}
            desc = params.get("query") or params.get("instruction") or ""
            
            if detail and desc:
                summary = f"你的任务\"{desc}\"已完成：{detail}"[:240]
            elif detail:
                summary = f"你的任务已完成：{detail}"[:240]
            elif desc:
                summary = f"你的任务\"{desc}\"已完成"[:240]
            
            return summary
        except Exception:
            return "任务已完成"
    
    async def notify_task_completion(self, task_id: str, task_info: Dict[str, Any]):
        """通知任务完成 - 基于博弈论的结果处理机制"""
        try:
            summary = self._build_result_summary(task_info)
            session_id = task_info.get("session_id")
            
            # 发送通知到主服务器
            payload = {
                "text": summary,
                "session_id": session_id,
                "task_id": task_id
            }
            
            response = requests.post(
                self.notification_url,
                json=payload,
                timeout=0.5
            )
            
            if response.status_code == 200:
                logger.info(f"任务完成通知已发送: {task_id}")
            else:
                logger.warning(f"任务完成通知发送失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"任务完成通知失败: {e}")
    
    def update_task_status(self, task_id: str, status: str, result: Any = None, error: str = None):
        """更新任务状态 - 基于博弈论的状态管理机制"""
        try:
            # 这里可以添加任务状态更新逻辑
            logger.info(f"任务状态更新: {task_id} -> {status}")
            
            if result:
                logger.debug(f"任务结果: {result}")
            if error:
                logger.error(f"任务错误: {error}")
                
        except Exception as e:
            logger.error(f"任务状态更新失败: {e}")


# 全局通知器实例
_result_notifier = None

def get_result_notifier() -> ResultNotifier:
    """获取全局结果通知器实例"""
    global _result_notifier
    if _result_notifier is None:
        _result_notifier = ResultNotifier()
    return _result_notifier
