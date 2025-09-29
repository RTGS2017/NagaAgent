#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
并行执行引擎 - 基于博弈论的并行执行机制
支持多进程并行执行任务
"""

import asyncio
import multiprocessing as mp
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class TaskInfo:
    """任务信息"""
    id: str
    type: str
    status: str
    start_time: str
    params: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    pid: Optional[int] = None
    _proc: Optional[mp.Process] = None

class ParallelExecutor:
    """并行执行器 - 基于博弈论的并行处理机制"""
    
    def __init__(self):
        self.task_registry: Dict[str, TaskInfo] = {}
        self.result_queue: Optional[mp.Queue] = None
        self.poller_task: Optional[asyncio.Task] = None
        self._start_poller()
    
    def _start_poller(self):
        """启动结果轮询器"""
        if self.poller_task is None:
            self.poller_task = asyncio.create_task(self._poll_results_loop())
    
    def _now_iso(self) -> str:
        """获取当前时间ISO格式"""
        return datetime.utcnow().isoformat() + "Z"
    
    def _spawn_task(self, kind: str, args: Dict[str, Any]) -> TaskInfo:
        """生成任务 - 基于博弈论的任务生成机制"""
        task_id = str(uuid.uuid4())
        info = TaskInfo(
            id=task_id,
            type=kind,
            status="running",
            start_time=self._now_iso(),
            params=args,
            result=None,
            error=None,
            pid=None,
            _proc=None
        )
        
        # Ensure result queue exists lazily
        if self.result_queue is None:
            self.result_queue = mp.Queue()
        
        if kind == "processor":
            p = mp.Process(target=self._worker_processor, args=(task_id, args.get("query", ""), self.result_queue))
            info.pid = None
            self.task_registry[task_id] = info
            p.daemon = True
            p.start()
            info.pid = p.pid
            info._proc = p
            return info
        elif kind == "computer_use":
            # Queue the task for exclusive execution by the scheduler
            info.status = "queued"
            info.pid = None
            self.task_registry[task_id] = info
            # 这里可以添加计算机控制队列逻辑
            return info
        else:
            raise ValueError(f"Unknown task kind: {kind}")
    
    def _worker_processor(self, task_id: str, query: str, queue: mp.Queue):
        """处理器工作进程 - 基于博弈论的处理器机制"""
        try:
            # Lazy import to avoid heavy init in parent
            from agentserver.core.agent_manager import get_agent_manager
            import asyncio as _aio
            
            agent_manager = get_agent_manager()
            
            # Log MCP processing start
            print(f"[MCP] Starting processor task {task_id} with query: {query[:100]}...")
            
            # 使用Naga的智能任务处理
            result = _aio.run(agent_manager.process_intelligent_task(query))
            
            # Log MCP processing result
            if result.get('status') == 'success':
                task_type = result.get('task_type', 'unknown')
                execution_time = result.get('execution_time', 0)
                print(f"[MCP] ✅ Task {task_id} executed successfully using {task_type} in {execution_time:.2f}s")
            else:
                error = result.get('error', 'no reason provided')
                print(f"[MCP] ❌ Task {task_id} failed to execute: {error}")
            
            queue.put({"task_id": task_id, "success": result.get('status') == 'success', "result": result})
        except Exception as e:
            print(f"[MCP] 💥 Task {task_id} crashed with error: {str(e)}")
            queue.put({"task_id": task_id, "success": False, "error": str(e)})
    
    async def _poll_results_loop(self):
        """结果轮询循环 - 基于博弈论的结果处理机制"""
        while True:
            await asyncio.sleep(0.1)
            try:
                if self.result_queue is None:
                    continue
                while True:
                    try:
                        msg = self.result_queue.get_nowait()
                    except Exception:
                        break
                    if not isinstance(msg, dict):
                        continue
                    tid = msg.get("task_id")
                    if not tid or tid not in self.task_registry:
                        continue
                    info = self.task_registry[tid]
                    info.status = "completed" if msg.get("success") else "failed"
                    if "result" in msg:
                        info.result = msg["result"]
                    if "error" in msg:
                        info.error = msg["error"]
                    
                    logger.info(f"任务 {tid} 完成: {info.status}")
            except Exception:
                pass
    
    async def execute_parallel_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行执行多个任务"""
        results = []
        
        for task in tasks:
            try:
                # 根据任务类型选择执行方式
                if task.get("type") == "mcp" or task.get("type") == "agent":
                    task_info = self._spawn_task("processor", {"query": task.get("query", "")})
                else:
                    task_info = self._spawn_task("processor", {"query": task.get("query", "")})
                
                results.append({
                    "task_id": task_info.id,
                    "status": task_info.status,
                    "start_time": task_info.start_time
                })
                
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                results.append({
                    "task_id": str(uuid.uuid4()),
                    "status": "failed",
                    "error": str(e)
                })
        
        return results
    
    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务状态"""
        return self.task_registry.get(task_id)
    
    def get_running_tasks(self) -> List[TaskInfo]:
        """获取运行中的任务"""
        return [info for info in self.task_registry.values() if info.status in ["running", "queued"]]


# 全局执行器实例
_parallel_executor = None

def get_parallel_executor() -> ParallelExecutor:
    """获取全局并行执行器实例"""
    global _parallel_executor
    if _parallel_executor is None:
        _parallel_executor = ParallelExecutor()
    return _parallel_executor
