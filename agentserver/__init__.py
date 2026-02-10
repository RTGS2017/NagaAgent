"""
NagaAgent独立服务 - 通过OpenClaw执行任务
提供意图识别和OpenClaw任务调度功能
"""

from .agent_server import app, Modules

__all__ = [
    'app',
    'Modules',
]
