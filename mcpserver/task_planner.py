#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务规划器 - 智能任务分析和路由
基于博弈论项目的设计，为Naga项目提供智能任务规划能力
"""

import asyncio
import logging
import json
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("TaskPlanner")

@dataclass
class Task:
    """任务数据结构"""
    id: str
    title: str
    original_query: str
    task_type: str = "unknown"  # agent, mcp, computer_use, hybrid
    steps: List[str] = field(default_factory=list)
    status: str = "queued"  # queued | running | done | failed
    priority: int = 1  # 1-5, 5最高优先级
    created_at: datetime = field(default_factory=datetime.now)
    meta: Dict[str, Any] = field(default_factory=dict)

class TaskPlanner:
    """任务规划器 - 智能分析任务并选择最佳执行方式"""
    
    def __init__(self, agent_manager=None, mcp_manager=None):
        self.agent_manager = agent_manager
        self.mcp_manager = mcp_manager
        self.task_pool: Dict[str, Task] = {}
        self.execution_history: List[Dict[str, Any]] = []
        
    async def analyze_and_plan(self, query: str, context: Optional[Dict[str, Any]] = None) -> Task:
        """
        分析任务并制定执行计划
        
        Args:
            query: 用户查询
            context: 上下文信息
            
        Returns:
            Task: 规划好的任务
        """
        task_id = str(uuid.uuid4())
        
        # 1. 任务类型分析
        task_type = await self._analyze_task_type(query, context)
        
        # 2. 根据任务类型制定执行计划
        if task_type == "agent":
            steps = await self._plan_agent_execution(query)
        elif task_type == "mcp":
            steps = await self._plan_mcp_execution(query)
        elif task_type == "computer_use":
            steps = await self._plan_computer_use_execution(query)
        elif task_type == "hybrid":
            steps = await self._plan_hybrid_execution(query)
        else:
            steps = [f"处理查询: {query}"]
        
        # 3. 创建任务对象
        task = Task(
            id=task_id,
            title=query[:50] + "..." if len(query) > 50 else query,
            original_query=query,
            task_type=task_type,
            steps=steps,
            status="queued",
            priority=self._calculate_priority(query, context),
            meta={
                "context": context or {},
                "analysis_timestamp": datetime.now().isoformat()
            }
        )
        
        # 4. 注册到任务池
        self.task_pool[task_id] = task
        
        logger.info(f"任务规划完成: {task_id} - {task_type} - {len(steps)}步骤")
        return task
    
    async def _analyze_task_type(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """分析任务类型"""
        # 简单的关键词匹配规则（可以扩展为LLM分析）
        query_lower = query.lower()
        
        # 电脑控制相关关键词
        computer_keywords = [
            "打开", "关闭", "点击", "输入", "截图", "操作", "控制", "运行程序",
            "打开文件", "关闭窗口", "切换窗口", "复制", "粘贴", "保存"
        ]
        
        # MCP工具相关关键词
        mcp_keywords = [
            "搜索", "查询", "获取", "下载", "天气", "时间", "计算", "翻译",
            "文件操作", "网络请求", "API调用"
        ]
        
        # Agent对话相关关键词
        agent_keywords = [
            "聊天", "对话", "解释", "分析", "建议", "帮助", "回答", "讨论"
        ]
        
        # 判断任务类型
        if any(keyword in query_lower for keyword in computer_keywords):
            return "computer_use"
        elif any(keyword in query_lower for keyword in mcp_keywords):
            return "mcp"
        elif any(keyword in query_lower for keyword in agent_keywords):
            return "agent"
        else:
            # 默认使用Agent处理
            return "agent"
    
    async def _plan_agent_execution(self, query: str) -> List[str]:
        """规划Agent执行步骤"""
        return [
            f"使用Agent处理查询: {query}",
            "生成回复内容",
            "返回处理结果"
        ]
    
    async def _plan_mcp_execution(self, query: str) -> List[str]:
        """规划MCP工具执行步骤"""
        return [
            f"分析MCP工具需求: {query}",
            "选择合适的MCP工具",
            "执行工具调用",
            "处理工具结果"
        ]
    
    async def _plan_computer_use_execution(self, query: str) -> List[str]:
        """规划电脑控制执行步骤"""
        return [
            f"分析电脑控制需求: {query}",
            "截取当前屏幕",
            "生成控制指令",
            "执行屏幕操作"
        ]
    
    async def _plan_hybrid_execution(self, query: str) -> List[str]:
        """规划混合执行步骤"""
        return [
            f"分析混合任务需求: {query}",
            "分解为多个子任务",
            "并行执行不同组件",
            "整合执行结果"
        ]
    
    def _calculate_priority(self, query: str, context: Optional[Dict[str, Any]] = None) -> int:
        """计算任务优先级"""
        # 简单的优先级计算逻辑
        if context and context.get("urgent"):
            return 5
        elif "紧急" in query or "立即" in query:
            return 4
        elif "重要" in query:
            return 3
        else:
            return 2
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息"""
        return self.task_pool.get(task_id)
    
    def update_task_status(self, task_id: str, status: str, result: Optional[Any] = None):
        """更新任务状态"""
        if task_id in self.task_pool:
            self.task_pool[task_id].status = status
            if result:
                self.task_pool[task_id].meta["result"] = result
            
            # 记录执行历史
            self.execution_history.append({
                "task_id": task_id,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "result": result
            })
    
    def get_task_list(self, status_filter: Optional[str] = None) -> List[Task]:
        """获取任务列表"""
        tasks = list(self.task_pool.values())
        if status_filter:
            tasks = [task for task in tasks if task.status == status_filter]
        return sorted(tasks, key=lambda x: (x.priority, x.created_at), reverse=True)
    
    def clear_completed_tasks(self):
        """清理已完成的任务"""
        completed_tasks = [task_id for task_id, task in self.task_pool.items() 
                          if task.status in ["done", "failed"]]
        for task_id in completed_tasks:
            del self.task_pool[task_id]
        logger.info(f"清理了 {len(completed_tasks)} 个已完成任务")
