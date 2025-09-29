#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AgentServer - 多智能体协作服务器
基于博弈论项目设计的多智能体协作框架
"""

__version__ = "1.0.0"
__author__ = "NagaAgent Team"

# 导入核心组件
from .core.agent_manager import get_agent_manager, process_intelligent_task
from .core.task_planner import TaskPlanner
from .core.task_executor import TaskExecutor
from .core.multi_agent_coordinator import get_coordinator, coordinate_task

__all__ = [
    "get_agent_manager",
    "process_intelligent_task", 
    "TaskPlanner",
    "TaskExecutor",
    "get_coordinator",
    "coordinate_task"
]
