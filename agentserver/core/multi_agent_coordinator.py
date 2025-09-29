#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多智能体协调器 - 统一的多智能体协作管理
基于博弈论的多智能体协调机制，为Naga项目提供智能体协作能力
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import uuid
from dataclasses import dataclass, field

from .agent_manager import get_agent_manager

logger = logging.getLogger("MultiAgentCoordinator")

@dataclass
class AgentCapability:
    """智能体能力描述"""
    agent_id: str
    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)
    priority: int = 1
    is_available: bool = True

@dataclass
class CollaborationTask:
    """协作任务"""
    id: str
    title: str
    description: str
    participants: List[str] = field(default_factory=list)  # 参与的智能体ID
    status: str = "pending"  # pending | running | completed | failed
    created_at: datetime = field(default_factory=datetime.now)
    results: Dict[str, Any] = field(default_factory=dict)

class MultiAgentCoordinator:
    """多智能体协调器 - 统一管理多个智能体的协作"""
    
    def __init__(self):
        self.agent_manager = get_agent_manager()
        # 任务规划器现在通过apiserver的task_scheduler处理
        # self.task_planner = None  # 删除重复功能
        # self.task_executor = None  # 删除重复功能
        
        # 智能体注册表
        self.registered_agents: Dict[str, AgentCapability] = {}
        
        # 协作任务管理
        self.collaboration_tasks: Dict[str, CollaborationTask] = {}
        
        # 协调策略
        self.coordination_strategies = {
            "sequential": self._sequential_coordination,
            "parallel": self._parallel_coordination,
            "hierarchical": self._hierarchical_coordination,
            "consensus": self._consensus_coordination
        }
        
        # 初始化
        self._init_coordinator()
    
    def _init_coordinator(self):
        """初始化协调器"""
        try:
            # 任务规划器现在通过apiserver的task_scheduler处理
            # 不再需要从agent_manager获取task_planner和task_executor
            
            # 注册默认智能体
            self._register_default_agents()
            
            logger.info("多智能体协调器初始化完成")
            
        except Exception as e:
            logger.error(f"多智能体协调器初始化失败: {e}")
    
    def _register_default_agents(self):
        """注册默认智能体"""
        # 注册基础智能体
        default_agents = [
            AgentCapability(
                agent_id="general_assistant",
                name="通用助手",
                description="处理一般性对话和任务",
                capabilities=["对话", "问答", "解释", "建议"],
                priority=3
            ),
            AgentCapability(
                agent_id="task_planner",
                name="任务规划师",
                description="分析和规划复杂任务",
                capabilities=["任务分析", "步骤分解", "资源分配"],
                priority=4
            ),
            AgentCapability(
                agent_id="tool_executor",
                name="工具执行器",
                description="执行具体的工具调用",
                capabilities=["MCP工具", "API调用", "文件操作"],
                priority=2
            )
        ]
        
        for agent in default_agents:
            self.registered_agents[agent.agent_id] = agent
        
        logger.info(f"已注册 {len(default_agents)} 个默认智能体")
    
    def register_agent(self, agent_capability: AgentCapability):
        """注册新的智能体"""
        self.registered_agents[agent_capability.agent_id] = agent_capability
        logger.info(f"已注册智能体: {agent_capability.name} ({agent_capability.agent_id})")
    
    def unregister_agent(self, agent_id: str):
        """注销智能体"""
        if agent_id in self.registered_agents:
            del self.registered_agents[agent_id]
            logger.info(f"已注销智能体: {agent_id}")
    
    async def coordinate_task(self, query: str, strategy: str = "sequential", 
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        协调多智能体执行任务
        
        Args:
            query: 任务查询
            strategy: 协调策略 (sequential, parallel, hierarchical, consensus)
            context: 上下文信息
            
        Returns:
            Dict[str, Any]: 协调结果
        """
        try:
            # 创建协作任务
            collaboration_task = CollaborationTask(
                id=str(uuid.uuid4()),
                title=query[:50] + "..." if len(query) > 50 else query,
                description=query,
                status="pending"
            )
            
            self.collaboration_tasks[collaboration_task.id] = collaboration_task
            
            # 选择合适的智能体
            selected_agents = await self._select_agents_for_task(query, context)
            collaboration_task.participants = [agent.agent_id for agent in selected_agents]
            
            logger.info(f"开始协调任务: {collaboration_task.id} - 策略: {strategy} - 参与者: {len(selected_agents)}")
            
            # 执行协调策略
            if strategy in self.coordination_strategies:
                result = await self.coordination_strategies[strategy](
                    collaboration_task, selected_agents, query, context
                )
            else:
                result = await self._default_coordination(
                    collaboration_task, selected_agents, query, context
                )
            
            # 更新任务状态
            collaboration_task.status = "completed" if result.get("success") else "failed"
            collaboration_task.results = result
            
            return {
                "task_id": collaboration_task.id,
                "strategy": strategy,
                "participants": [agent.name for agent in selected_agents],
                "result": result
            }
            
        except Exception as e:
            logger.error(f"协调任务失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _select_agents_for_task(self, query: str, context: Optional[Dict[str, Any]] = None) -> List[AgentCapability]:
        """为任务选择合适的智能体"""
        # 简单的智能体选择逻辑
        selected_agents = []
        
        # 根据查询内容选择智能体
        query_lower = query.lower()
        
        # 总是包含通用助手
        if "general_assistant" in self.registered_agents:
            selected_agents.append(self.registered_agents["general_assistant"])
        
        # 根据关键词选择专业智能体
        if any(keyword in query_lower for keyword in ["规划", "分析", "分解", "步骤"]):
            if "task_planner" in self.registered_agents:
                selected_agents.append(self.registered_agents["task_planner"])
        
        if any(keyword in query_lower for keyword in ["工具", "执行", "调用", "操作"]):
            if "tool_executor" in self.registered_agents:
                selected_agents.append(self.registered_agents["tool_executor"])
        
        # 如果没有选择到智能体，使用通用助手
        if not selected_agents:
            selected_agents = [self.registered_agents.get("general_assistant")]
        
        return [agent for agent in selected_agents if agent and agent.is_available]
    
    async def _sequential_coordination(self, task: CollaborationTask, agents: List[AgentCapability], 
                                    query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """顺序协调策略 - 智能体依次执行"""
        results = []
        
        for i, agent in enumerate(agents):
            try:
                logger.info(f"顺序执行: {agent.name} ({i+1}/{len(agents)})")
                
                # 构建上下文，包含前一个智能体的结果
                agent_context = context or {}
                if results:
                    agent_context["previous_results"] = results[-1]
                
                # 调用智能体
                result = await self._call_agent(agent, query, agent_context)
                results.append({
                    "agent": agent.name,
                    "result": result,
                    "step": i + 1
                })
                
            except Exception as e:
                logger.error(f"智能体 {agent.name} 执行失败: {e}")
                results.append({
                    "agent": agent.name,
                    "error": str(e),
                    "step": i + 1
                })
        
        return {
            "success": len(results) > 0,
            "strategy": "sequential",
            "results": results
        }
    
    async def _parallel_coordination(self, task: CollaborationTask, agents: List[AgentCapability], 
                                   query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """并行协调策略 - 智能体同时执行"""
        try:
            # 并行执行所有智能体
            tasks = []
            for agent in agents:
                task_coro = self._call_agent(agent, query, context)
                tasks.append(task_coro)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            processed_results = []
            for i, (agent, result) in enumerate(zip(agents, results)):
                if isinstance(result, Exception):
                    processed_results.append({
                        "agent": agent.name,
                        "error": str(result),
                        "step": i + 1
                    })
                else:
                    processed_results.append({
                        "agent": agent.name,
                        "result": result,
                        "step": i + 1
                    })
            
            return {
                "success": len(processed_results) > 0,
                "strategy": "parallel",
                "results": processed_results
            }
            
        except Exception as e:
            logger.error(f"并行协调失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _hierarchical_coordination(self, task: CollaborationTask, agents: List[AgentCapability], 
                                       query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """层次协调策略 - 主智能体协调其他智能体"""
        # 选择主智能体（优先级最高的）
        main_agent = max(agents, key=lambda x: x.priority)
        other_agents = [agent for agent in agents if agent != main_agent]
        
        try:
            # 主智能体分析任务
            main_result = await self._call_agent(main_agent, query, context)
            
            # 主智能体决定是否需要其他智能体协助
            if other_agents and main_result.get("needs_assistance"):
                # 协调其他智能体
                sub_results = []
                for agent in other_agents:
                    sub_result = await self._call_agent(agent, query, {
                        "main_result": main_result,
                        "context": context
                    })
                    sub_results.append({
                        "agent": agent.name,
                        "result": sub_result
                    })
                
                return {
                    "success": True,
                    "strategy": "hierarchical",
                    "main_agent": main_agent.name,
                    "main_result": main_result,
                    "sub_results": sub_results
                }
            else:
                return {
                    "success": True,
                    "strategy": "hierarchical",
                    "main_agent": main_agent.name,
                    "result": main_result
                }
                
        except Exception as e:
            logger.error(f"层次协调失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _consensus_coordination(self, task: CollaborationTask, agents: List[AgentCapability], 
                                    query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """共识协调策略 - 多个智能体达成共识"""
        try:
            # 所有智能体并行执行
            tasks = [self._call_agent(agent, query, context) for agent in agents]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 分析结果，寻找共识
            valid_results = []
            for agent, result in zip(agents, results):
                if not isinstance(result, Exception):
                    valid_results.append({
                        "agent": agent.name,
                        "result": result
                    })
            
            # 简单的共识算法（可以扩展为更复杂的）
            if len(valid_results) >= 2:
                # 选择最相似的结果
                consensus_result = valid_results[0]["result"]
            else:
                consensus_result = valid_results[0]["result"] if valid_results else None
            
            return {
                "success": consensus_result is not None,
                "strategy": "consensus",
                "consensus_result": consensus_result,
                "all_results": valid_results
            }
            
        except Exception as e:
            logger.error(f"共识协调失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _default_coordination(self, task: CollaborationTask, agents: List[AgentCapability], 
                                  query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """默认协调策略"""
        return await self._sequential_coordination(task, agents, query, context)
    
    async def _call_agent(self, agent: AgentCapability, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用智能体"""
        try:
            # 根据智能体类型调用不同的方法
            if agent.agent_id == "general_assistant":
                return await self.agent_manager.call_agent("default", query)
            elif agent.agent_id == "task_planner":
                # 通过apiserver的task_scheduler处理任务规划
                try:
                    from apiserver.task_scheduler import get_task_scheduler
                    task_scheduler = get_task_scheduler()
                    
                    # 创建任务并调度
                    import uuid
                    task_id = str(uuid.uuid4())
                    
                    # 注册任务到调度器
                    task_scheduler.task_registry[task_id] = {
                        "id": task_id,
                        "type": "processor",
                        "status": "queued",
                        "params": {"query": query},
                        "context": context
                    }
                    
                    return {
                        "task_id": task_id,
                        "task_type": "processor",
                        "status": "queued",
                        "message": "任务已提交到调度器"
                    }
                except Exception as e:
                    return {"error": f"任务规划器调用失败: {e}"}
            elif agent.agent_id == "tool_executor":
                # 通过apiserver的task_scheduler处理工具执行
                try:
                    from apiserver.task_scheduler import get_task_scheduler
                    task_scheduler = get_task_scheduler()
                    
                    # 调度工具执行任务
                    tasks = [{
                        "type": "processor",
                        "params": {"query": query},
                        "session_id": context.get("session_id") if context else None
                    }]
                    
                    results = await task_scheduler.schedule_parallel_execution(tasks)
                    return {
                        "message": "工具执行器处理完成",
                        "results": results
                    }
                except Exception as e:
                    return {"error": f"工具执行器调用失败: {e}"}
            else:
                # 默认使用通用助手
                return await self.agent_manager.call_agent("default", query)
                
        except Exception as e:
            logger.error(f"调用智能体 {agent.name} 失败: {e}")
            return {"error": str(e)}
    
    def get_registered_agents(self) -> List[Dict[str, Any]]:
        """获取已注册的智能体列表"""
        return [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "capabilities": agent.capabilities,
                "priority": agent.priority,
                "is_available": agent.is_available
            }
            for agent in self.registered_agents.values()
        ]
    
    def get_collaboration_tasks(self) -> List[Dict[str, Any]]:
        """获取协作任务列表"""
        return [
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "participants": task.participants,
                "created_at": task.created_at.isoformat(),
                "results": task.results
            }
            for task in self.collaboration_tasks.values()
        ]

# 全局协调器实例
_COORDINATOR = None

def get_coordinator() -> MultiAgentCoordinator:
    """获取全局协调器实例"""
    global _COORDINATOR
    if _COORDINATOR is None:
        _COORDINATOR = MultiAgentCoordinator()
    return _COORDINATOR

# 便捷函数
async def coordinate_task(query: str, strategy: str = "sequential", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """便捷的协调任务函数"""
    coordinator = get_coordinator()
    return await coordinator.coordinate_task(query, strategy, context)

def register_agent(agent_capability: AgentCapability):
    """便捷的智能体注册函数"""
    coordinator = get_coordinator()
    coordinator.register_agent(agent_capability)

def get_registered_agents() -> List[Dict[str, Any]]:
    """便捷的智能体列表获取函数"""
    coordinator = get_coordinator()
    return coordinator.get_registered_agents()
