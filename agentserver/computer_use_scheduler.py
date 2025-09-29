#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电脑控制调度器 - 基于博弈论的电脑控制调度机制
"""

import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ComputerUseScheduler:
    """电脑控制调度器 - 串行化电脑操作任务"""
    
    def __init__(self):
        self.computer_use_queue: Optional[asyncio.Queue] = None
        self.computer_use_running: bool = False
        self.active_task_id: Optional[str] = None
    
    async def queue_computer_use_task(self, task_id: str, instruction: str, screenshot: Optional[bytes] = None):
        """排队电脑控制任务"""
        if self.computer_use_queue is None:
            self.computer_use_queue = asyncio.Queue()
        
        await self.computer_use_queue.put({
            "task_id": task_id,
            "instruction": instruction,
            "screenshot": screenshot
        })
        
        logger.info(f"电脑控制任务已排队: {task_id}")
    
    def is_computer_use_busy(self) -> bool:
        """检查电脑控制是否忙碌"""
        return self.computer_use_running
    
    def get_active_task_id(self) -> Optional[str]:
        """获取活跃任务ID"""
        return self.active_task_id


# 全局调度器实例
_computer_use_scheduler = None

def get_computer_use_scheduler() -> ComputerUseScheduler:
    """获取全局电脑控制调度器实例"""
    global _computer_use_scheduler
    if _computer_use_scheduler is None:
        _computer_use_scheduler = ComputerUseScheduler()
    return _computer_use_scheduler
