"""
增强版电脑控制代理 - 基于博弈论的完整实现
集成AI模型、任务调度、视觉分析等功能
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime
import uuid

from .computer_use_adapter import ComputerUseAdapter
from .visual_analyzer import VisualAnalyzer
from .task_planner import TaskPlanner
from .action_executor import ActionExecutor

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class ComputerControlTask:
    """电脑控制任务"""
    id: str
    instruction: str
    status: str = "queued"  # queued, running, completed, failed
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

class EnhancedComputerControlAgent:
    """增强版电脑控制代理"""
    
    def __init__(self):
        """初始化代理"""
        self.adapter = ComputerUseAdapter()
        self.visual_analyzer = VisualAnalyzer()
        self.task_planner = TaskPlanner()
        self.executor = ActionExecutor()
        
        # 任务管理
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[str, ComputerControlTask] = {}
        self.completed_tasks: Dict[str, ComputerControlTask] = {}
        
        # 状态标志
        self.is_running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        
        logger.info("增强版电脑控制代理初始化完成")
    
    async def start(self):
        """启动代理服务"""
        if self.is_running:
            return
        
        self.is_running = True
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("电脑控制代理服务已启动")
    
    async def stop(self):
        """停止代理服务"""
        self.is_running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("电脑控制代理服务已停止")
    
    async def _scheduler_loop(self):
        """任务调度循环，基于博弈论的实现"""
        while self.is_running:
            try:
                # 检查是否有待处理的任务
                if not self.task_queue.empty():
                    task = await self.task_queue.get()
                    await self._process_task(task)
                else:
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"任务调度循环错误: {e}")
                await asyncio.sleep(1)
    
    async def _process_task(self, task: ComputerControlTask):
        """处理单个任务"""
        try:
            task.status = "running"
            task.started_at = datetime.now()
            self.active_tasks[task.id] = task
            
            logger.info(f"开始处理任务 {task.id}: {task.instruction}")
            
            # 使用智能任务执行
            result = await self.adapter.run_instruction(task.instruction)
            
            task.result = result
            task.status = "completed" if result.get("success", False) else "failed"
            task.completed_at = datetime.now()
            
            # 移动到已完成任务
            self.completed_tasks[task.id] = task
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            
            logger.info(f"任务 {task.id} 处理完成: {task.status}")
            
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            
            # 移动到已完成任务
            self.completed_tasks[task.id] = task
            if task.id in self.active_tasks:
                del self.active_tasks[task.id]
            
            logger.error(f"任务 {task.id} 处理失败: {e}")
    
    async def submit_task(self, instruction: str) -> str:
        """提交新任务"""
        task_id = str(uuid.uuid4())
        task = ComputerControlTask(
            id=task_id,
            instruction=instruction
        )
        
        await self.task_queue.put(task)
        logger.info(f"任务已提交: {task_id}")
        
        return task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        # 检查活跃任务
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            return {
                "id": task.id,
                "status": task.status,
                "instruction": task.instruction,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None
            }
        
        # 检查已完成任务
        if task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
            return {
                "id": task.id,
                "status": task.status,
                "instruction": task.instruction,
                "created_at": task.created_at.isoformat(),
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "result": task.result,
                "error": task.error
            }
        
        return None
    
    async def handle_handoff(self, task: Dict[str, Any]) -> str:
        """处理handoff调用"""
        try:
            action = task.get('action', '')
            target = task.get('target', '')
            parameters = task.get('parameters', {})
            
            logger.info(f"收到电脑控制任务: {action} - {target}")
            
            # 构建指令
            if action == 'automate_task':
                instruction = target
            else:
                instruction = f"{action}: {target}"
                if parameters:
                    instruction += f" (参数: {parameters})"
            
            # 提交任务
            task_id = await self.submit_task(instruction)
            
            # 等待任务完成（简化版本，实际应该异步处理）
            await asyncio.sleep(0.1)  # 给任务一些时间开始
            
            return json.dumps({
                "status": "success",
                "task_id": task_id,
                "message": f"电脑控制任务已提交: {instruction}",
                "instruction": instruction
            }, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"处理电脑控制任务失败: {e}")
            return json.dumps({
                "status": "error",
                "error": str(e),
                "message": f"任务处理失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def get_status(self) -> Dict[str, Any]:
        """获取代理状态"""
        return {
            "is_running": self.is_running,
            "queue_size": self.task_queue.qsize(),
            "active_tasks": len(self.active_tasks),
            "completed_tasks": len(self.completed_tasks),
            "adapter_status": self.adapter.get_status()
        }
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """获取可用工具列表"""
        return [
            {
                "name": "click",
                "description": "点击屏幕指定位置",
                "parameters": {
                    "x": {"type": "number", "description": "X坐标"},
                    "y": {"type": "number", "description": "Y坐标"},
                    "button": {"type": "string", "description": "鼠标按钮", "default": "left"}
                }
            },
            {
                "name": "type",
                "description": "输入文本",
                "parameters": {
                    "text": {"type": "string", "description": "要输入的文本"}
                }
            },
            {
                "name": "screenshot",
                "description": "截取屏幕截图",
                "parameters": {}
            },
            {
                "name": "find_element",
                "description": "查找屏幕元素",
                "parameters": {
                    "text": {"type": "string", "description": "要查找的文本"}
                }
            },
            {
                "name": "automate_task",
                "description": "自动化执行复杂任务",
                "parameters": {
                    "instruction": {"type": "string", "description": "任务指令"}
                }
            }
        ]
