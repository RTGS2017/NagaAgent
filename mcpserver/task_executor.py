#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务执行器 - 统一的任务执行和调度
基于博弈论项目的设计，为Naga项目提供智能任务执行能力
"""

import asyncio
import logging
import multiprocessing as mp
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from dataclasses import dataclass

from .task_planner import Task, TaskPlanner
from .agent_manager import get_agent_manager
from .mcp_manager import get_mcp_manager

logger = logging.getLogger("TaskExecutor")

@dataclass
class ExecutionResult:
    """执行结果数据结构"""
    task_id: str
    success: bool
    result: Any = None
    error: str = ""
    execution_time: float = 0.0
    timestamp: datetime = None

class TaskExecutor:
    """任务执行器 - 统一的任务执行和调度"""
    
    def __init__(self, task_planner: TaskPlanner):
        self.task_planner = task_planner
        self.agent_manager = get_agent_manager()
        self.mcp_manager = get_mcp_manager()
        
        # 任务执行状态
        self.running_tasks: Dict[str, Dict[str, Any]] = {}
        self.result_queue: Optional[mp.Queue] = None
        self.execution_history: List[ExecutionResult] = []
        
        # 执行器状态
        self.is_running = False
        self.max_concurrent_tasks = 5
        
    async def start(self):
        """启动任务执行器"""
        if self.is_running:
            return
            
        self.is_running = True
        self.result_queue = mp.Queue()
        
        # 启动结果处理任务
        asyncio.create_task(self._result_processor())
        
        logger.info("任务执行器已启动")
    
    async def stop(self):
        """停止任务执行器"""
        self.is_running = False
        
        # 终止所有运行中的任务
        for task_id, task_info in list(self.running_tasks.items()):
            await self._terminate_task(task_id)
        
        logger.info("任务执行器已停止")
    
    async def execute_task(self, task: Task) -> ExecutionResult:
        """执行单个任务"""
        start_time = datetime.now()
        
        try:
            logger.info(f"开始执行任务: {task.id} - {task.task_type}")
            
            # 更新任务状态
            self.task_planner.update_task_status(task.id, "running")
            self.running_tasks[task.id] = {
                "task": task,
                "start_time": start_time,
                "status": "running"
            }
            
            # 根据任务类型执行
            if task.task_type == "agent":
                result = await self._execute_agent_task(task)
            elif task.task_type == "mcp":
                result = await self._execute_mcp_task(task)
            elif task.task_type == "computer_use":
                result = await self._execute_computer_use_task(task)
            elif task.task_type == "hybrid":
                result = await self._execute_hybrid_task(task)
            else:
                result = await self._execute_default_task(task)
            
            # 计算执行时间
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 创建执行结果
            execution_result = ExecutionResult(
                task_id=task.id,
                success=result.get("success", False),
                result=result.get("result"),
                error=result.get("error", ""),
                execution_time=execution_time,
                timestamp=datetime.now()
            )
            
            # 更新任务状态
            status = "done" if execution_result.success else "failed"
            self.task_planner.update_task_status(task.id, status, execution_result.result)
            
            # 记录执行历史
            self.execution_history.append(execution_result)
            
            # 从运行中任务移除
            self.running_tasks.pop(task.id, None)
            
            logger.info(f"任务执行完成: {task.id} - {status} - {execution_time:.2f}s")
            return execution_result
            
        except Exception as e:
            logger.error(f"任务执行异常: {task.id} - {str(e)}")
            
            execution_result = ExecutionResult(
                task_id=task.id,
                success=False,
                error=str(e),
                execution_time=(datetime.now() - start_time).total_seconds(),
                timestamp=datetime.now()
            )
            
            self.task_planner.update_task_status(task.id, "failed", str(e))
            self.running_tasks.pop(task.id, None)
            return execution_result
    
    async def _execute_agent_task(self, task: Task) -> Dict[str, Any]:
        """执行Agent任务"""
        try:
            # 选择默认Agent或根据上下文选择
            agent_name = task.meta.get("context", {}).get("agent_name", "default")
            
            # 调用Agent
            result = await self.agent_manager.call_agent(
                agent_name=agent_name,
                prompt=task.original_query
            )
            
            return {
                "success": result.get("status") == "success",
                "result": result.get("result", ""),
                "error": result.get("error", "")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_mcp_task(self, task: Task) -> Dict[str, Any]:
        """执行MCP任务"""
        try:
            # 分析需要的MCP工具
            query = task.original_query
            
            # 这里可以集成更智能的工具选择逻辑
            # 暂时使用简单的工具调用
            result = await self.mcp_manager.unified_call(
                service_name="default",
                tool_name="process_query",
                args={"query": query}
            )
            
            return {
                "success": True,
                "result": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_computer_use_task(self, task: Task) -> Dict[str, Any]:
        """执行电脑控制任务"""
        try:
            # 这里可以集成电脑控制功能
            # 暂时返回模拟结果
            return {
                "success": True,
                "result": f"电脑控制任务已执行: {task.original_query}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_hybrid_task(self, task: Task) -> Dict[str, Any]:
        """执行混合任务"""
        try:
            # 混合任务需要多个组件协作
            results = []
            
            # 并行执行多个子任务
            for step in task.steps:
                if "agent" in step.lower():
                    result = await self._execute_agent_task(task)
                elif "mcp" in step.lower():
                    result = await self._execute_mcp_task(task)
                else:
                    result = {"success": True, "result": f"执行步骤: {step}"}
                
                results.append(result)
            
            # 整合结果
            success = all(r.get("success", False) for r in results)
            combined_result = "\n".join([r.get("result", "") for r in results if r.get("result")])
            
            return {
                "success": success,
                "result": combined_result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _execute_default_task(self, task: Task) -> Dict[str, Any]:
        """执行默认任务"""
        return {
            "success": True,
            "result": f"默认处理: {task.original_query}"
        }
    
    async def _terminate_task(self, task_id: str):
        """终止任务"""
        if task_id in self.running_tasks:
            task_info = self.running_tasks[task_id]
            # 这里可以添加具体的任务终止逻辑
            self.task_planner.update_task_status(task_id, "cancelled")
            del self.running_tasks[task_id]
    
    async def _result_processor(self):
        """结果处理器 - 处理来自子进程的结果"""
        while self.is_running:
            try:
                if self.result_queue and not self.result_queue.empty():
                    result = self.result_queue.get_nowait()
                    # 处理结果
                    logger.info(f"收到任务结果: {result}")
            except Exception as e:
                logger.error(f"结果处理异常: {e}")
            
            await asyncio.sleep(0.1)
    
    def get_running_tasks(self) -> List[Dict[str, Any]]:
        """获取正在运行的任务"""
        return [
            {
                "task_id": task_id,
                "task_type": task_info["task"].task_type,
                "start_time": task_info["start_time"],
                "status": task_info["status"]
            }
            for task_id, task_info in self.running_tasks.items()
        ]
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计信息"""
        total_tasks = len(self.execution_history)
        successful_tasks = len([r for r in self.execution_history if r.success])
        failed_tasks = total_tasks - successful_tasks
        
        avg_execution_time = 0
        if total_tasks > 0:
            avg_execution_time = sum(r.execution_time for r in self.execution_history) / total_tasks
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "failed_tasks": failed_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "avg_execution_time": avg_execution_time,
            "running_tasks": len(self.running_tasks)
        }
