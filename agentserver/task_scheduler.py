#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用任务调度器 - 融合智能记忆管理的任务调度系统"""

import asyncio  # 异步支持 #
import uuid  # 任务ID #
import json  # JSON处理 #
import logging  # 日志 #
import time  # 时间处理 #
from typing import Any, Dict, List, Optional  # 类型标注 #
from dataclasses import dataclass, field  # 数据类 #

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class TaskStep:
    """任务步骤数据类"""
    step_id: str
    task_id: str
    purpose: str  # 步骤目的
    content: str  # 步骤内容
    output: str = ""  # 步骤输出
    analysis: Optional[Dict[str, Any]] = None  # 分析结果
    timestamp: float = field(default_factory=time.time)
    success: bool = True  # 是否成功
    error: Optional[str] = None  # 错误信息

@dataclass
class CompressedMemory:
    """压缩记忆数据类"""
    memory_id: str
    key_findings: List[str]  # 关键发现
    failed_attempts: List[str]  # 失败尝试
    current_status: str  # 当前状态
    next_steps: List[str]  # 建议步骤
    source_steps: int  # 来源步骤数
    timestamp: float = field(default_factory=time.time)

class _TaskScheduler:
    """通用任务调度器 - 融合智能记忆管理"""

    def __init__(self, config: Optional[Any] = None) -> None:
        # 导入配置
        if config is None:
            from agentserver.config import get_task_scheduler_config
            config = get_task_scheduler_config()
        
        self.config = config
        
        # 基础任务管理
        self.task_registry: Dict[str, Dict[str, Any]] = {}  # 任务注册表
        self._lock = asyncio.Lock()  # 并发锁
        
        # 智能记忆管理
        self.max_steps = config.max_steps  # 最大保存步骤数
        self.compression_threshold = config.compression_threshold  # 压缩阈值
        self.keep_last_steps = config.keep_last_steps  # 压缩后保留步骤数
        self.task_steps: Dict[str, List[TaskStep]] = {}  # 任务步骤历史
        self.compressed_memories: List[CompressedMemory] = []  # 压缩记忆
        self.key_facts: Dict[str, str] = {}  # 关键事实存储
        self.failed_attempts: Dict[str, int] = {}  # 失败尝试计数
        self.llm_config: Optional[Dict[str, Any]] = None  # LLM配置
        
        # 会话级别的记忆管理 - 新增功能
        self.session_memories: Dict[str, Dict[str, Any]] = {}  # 会话记忆：session_id -> {tasks, compressed_memories, key_facts}
        self.session_task_mapping: Dict[str, str] = {}  # 任务ID到会话ID的映射
        self.analysis_session_mapping: Dict[str, str] = {}  # 分析会话ID到原始会话ID的映射

    def set_llm_config(self, config: Dict[str, Any]) -> None:
        """设置LLM配置用于智能压缩"""
        self.llm_config = config

    async def create_task(self, task_id: str, purpose: str, session_id: Optional[str] = None, 
                         analysis_session_id: Optional[str] = None) -> str:
        """创建新任务 - 应用与MCP服务器相同的会话管理逻辑，并关联会话记忆"""
        async with self._lock:
            self.task_registry[task_id] = {
                "id": task_id,
                "purpose": purpose,
                "session_id": session_id,
                "analysis_session_id": analysis_session_id,
                "status": "created",
                "created_at": time.time(),
                "steps_count": 0
            }
            
            # 初始化任务步骤列表
            if task_id not in self.task_steps:
                self.task_steps[task_id] = []
            
            # 会话级别的记忆管理
            if session_id:
                # 建立任务到会话的映射
                self.session_task_mapping[task_id] = session_id
                
                # 建立分析会话到原始会话的映射
                if analysis_session_id:
                    self.analysis_session_mapping[analysis_session_id] = session_id
                
                # 初始化会话记忆（如果不存在）
                if session_id not in self.session_memories:
                    self.session_memories[session_id] = {
                        "tasks": [],
                        "compressed_memories": [],
                        "key_facts": {},
                        "failed_attempts": {},
                        "created_at": time.time(),
                        "last_activity": time.time()
                    }
                
                # 将会话记忆与任务关联
                self.session_memories[session_id]["tasks"].append(task_id)
                self.session_memories[session_id]["last_activity"] = time.time()
            
            logger.info(f"[任务创建] 创建任务: {task_id}, 目的: {purpose}, 会话: {session_id}, 分析会话: {analysis_session_id}")
            return task_id

    async def add_task_step(self, task_id: str, step: TaskStep) -> None:
        """添加任务步骤到历史记录，并更新会话级别的记忆管理"""
        async with self._lock:
            if task_id not in self.task_steps:
                self.task_steps[task_id] = []
            
            self.task_steps[task_id].append(step)
            
            # 提取关键事实
            self._extract_key_facts(step)
            
            # 记录失败尝试
            if not step.success:
                self.failed_attempts[step.content] = self.failed_attempts.get(step.content, 0) + 1
            
            # 会话级别的记忆管理
            session_id = self.session_task_mapping.get(task_id)
            if session_id and session_id in self.session_memories:
                # 更新会话记忆中的关键事实
                fact_key = f"task:{task_id}:step:{step.step_id}"
                if fact_key in self.key_facts:
                    self.session_memories[session_id]["key_facts"][fact_key] = self.key_facts[fact_key]
                
                # 更新会话记忆中的失败尝试
                if not step.success:
                    session_failed = self.session_memories[session_id]["failed_attempts"]
                    session_failed[step.content] = session_failed.get(step.content, 0) + 1
                
                # 更新会话活动时间
                self.session_memories[session_id]["last_activity"] = time.time()
            
            # 检查是否需要压缩记忆
            if len(self.task_steps[task_id]) >= self.compression_threshold:
                await self._compress_memory(task_id)

    def _extract_key_facts(self, step: TaskStep) -> None:
        """从步骤中提取关键事实"""
        # 提取关键命令和结果
        if step.content and step.output:
            output_summary = step.output[:self.config.output_summary_length] + ("..." if len(step.output) > self.config.output_summary_length else "")
            fact_key = f"task:{step.task_id}:step:{step.step_id}"
            self.key_facts[fact_key] = f"命令：{step.content}, 结果: {output_summary}"
        
        # 提取分析结论
        if step.analysis and "analysis" in step.analysis:
            analysis = step.analysis["analysis"]
            if "关键发现" in analysis or "重要" in analysis:
                fact_key = f"analysis:{hash(analysis)}"
                self.key_facts[fact_key] = analysis

    async def _compress_memory(self, task_id: str) -> None:
        """压缩任务记忆"""
        if not self.llm_config or task_id not in self.task_steps:
            return
        
        logger.info(f"开始压缩任务 {task_id} 的记忆...")
        
        # 构建压缩提示
        prompt = self._build_compression_prompt(task_id)
        
        try:
            # 调用LLM进行压缩
            compressed_data = await self._call_llm_compression(prompt)
            
            # 创建压缩记忆对象
            memory = CompressedMemory(
                memory_id=str(uuid.uuid4()),
                key_findings=compressed_data.get("key_findings", []),
                failed_attempts=compressed_data.get("failed_attempts", []),
                current_status=compressed_data.get("current_status", "未知状态"),
                next_steps=compressed_data.get("next_steps", []),
                source_steps=len(self.task_steps[task_id])
            )
            
            # 更新失败尝试记录
            for attempt in memory.failed_attempts:
                self.failed_attempts[attempt] = self.failed_attempts.get(attempt, 0) + 1
            
            self.compressed_memories.append(memory)
            
            # 会话级别的压缩记忆管理
            session_id = self.session_task_mapping.get(task_id)
            if session_id and session_id in self.session_memories:
                self.session_memories[session_id]["compressed_memories"].append(memory)
                logger.info(f"[会话记忆] 会话 {session_id} 添加压缩记忆: {len(memory.key_findings)}个关键发现")
            
            logger.info(f"记忆压缩成功: 添加了{len(memory.key_findings)}个关键发现")
            
        except Exception as e:
            logger.error(f"记忆压缩失败: {e}")
            # 创建错误记忆
            error_memory = CompressedMemory(
                memory_id=str(uuid.uuid4()),
                key_findings=[f"压缩失败: {str(e)}"],
                failed_attempts=[],
                current_status="压缩失败",
                next_steps=["重新尝试压缩"],
                source_steps=len(self.task_steps[task_id])
            )
            self.compressed_memories.append(error_memory)
        
        # 清空历史记录，保留最后几步
        keep_last = min(self.keep_last_steps, len(self.task_steps[task_id]))
        self.task_steps[task_id] = self.task_steps[task_id][-keep_last:]

    def _build_compression_prompt(self, task_id: str) -> str:
        """构建压缩提示"""
        prompt = """
你是一个专业的任务执行助手，需要压缩任务执行历史记录。请执行以下任务：
1. 识别并提取关键的技术细节和发现
2. 标记已尝试但失败的解决方案
3. 总结当前任务状态和下一步建议
4. 以JSON格式返回以下结构的数据：
{
  "key_findings": ["发现1", "发现2"],
  "failed_attempts": ["命令1", "命令2"],
  "current_status": "当前状态描述",
  "next_steps": ["建议1", "建议2"]
}

任务ID: {task_id}
历史记录:
""".format(task_id=task_id)
        
        # 添加关键事实
        prompt += "关键事实摘要:\n"
        recent_facts = list(self.key_facts.items())[-self.config.key_facts_compression_limit:]  # 最近关键事实
        for _, value in recent_facts:
            prompt += f"- {value}\n"
        
        # 添加历史步骤
        steps = self.task_steps[task_id][-self.compression_threshold:]
        for i, step in enumerate(steps):
            prompt += f"\n步骤 {i+1}:\n"
            prompt += f"- 目的: {step.purpose}\n"
            prompt += f"- 命令: {step.content}\n"
            if step.output:
                prompt += f"- 输出: {step.output[:self.config.step_output_display_length]}{'...' if len(step.output) > self.config.step_output_display_length else ''}\n"
            if step.analysis:
                analysis = step.analysis.get("analysis", "无分析")
                prompt += f"- 分析: {analysis}\n"
            if not step.success:
                prompt += f"- 状态: 失败 - {step.error}\n"
        
        return prompt

    async def _call_llm_compression(self, prompt: str) -> Dict[str, Any]:
        """调用LLM进行记忆压缩"""
        try:
            import litellm
            litellm.enable_json_schema_validation = True
            
            response = litellm.completion(
                model=self.llm_config["model"],
                api_key=self.llm_config["api_key"],
                api_base=self.llm_config["api_base"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            
            json_str = response.choices[0].message.content.strip()
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"LLM压缩调用失败: {e}")
            return {
                "key_findings": [f"压缩失败: {str(e)}"],
                "failed_attempts": [],
                "current_status": "压缩失败",
                "next_steps": ["检查LLM配置"]
            }

    async def schedule_parallel_execution(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """并行调度执行给定任务列表，返回结果列表"""
        if not tasks:
            return []

        async def _run_task(task: Dict[str, Any]) -> Dict[str, Any]:
            task_id = task.get("id") or str(uuid.uuid4())
            async with self._lock:
                self.task_registry[task_id] = {
                    "id": task_id,
                    "type": task.get("type") or "processor",
                    "status": "running",
                    "params": task.get("params") or {},
                    "context": task.get("context"),
                    "created_at": time.time()
                }

            try:
                # 创建任务步骤记录
                step = TaskStep(
                    step_id=str(uuid.uuid4()),
                    task_id=task_id,
                    purpose=task.get("purpose", "执行任务"),
                    content=str(task.get("params", {})),
                    success=True
                )
                
                # 占位执行：此处可接入真实执行器
                await asyncio.sleep(0)
                result = {
                    "success": True,
                    "result": None,
                    "task_type": self.task_registry[task_id]["type"],
                }
                
                step.output = str(result)
                await self.add_task_step(task_id, step)
                
                return result
            except Exception as e:
                # 记录失败的步骤
                step = TaskStep(
                    step_id=str(uuid.uuid4()),
                    task_id=task_id,
                    purpose=task.get("purpose", "执行任务"),
                    content=str(task.get("params", {})),
                    success=False,
                    error=str(e)
                )
                await self.add_task_step(task_id, step)
                
                return {"success": False, "error": str(e)}
            finally:
                async with self._lock:
                    entry = self.task_registry.get(task_id)
                    if entry is not None:
                        entry["status"] = "completed"
                        entry["completed_at"] = time.time()

        coros = [_run_task(t) for t in tasks]
        return await asyncio.gather(*coros, return_exceptions=False)

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查询指定任务状态"""
        async with self._lock:
            return self.task_registry.get(task_id)

    async def get_running_tasks(self) -> List[Dict[str, Any]]:
        """获取运行中任务列表"""
        async with self._lock:
            return [t for t in self.task_registry.values() if t.get("status") == "running"]

    async def get_task_memory_summary(self, task_id: str, include_key_facts: bool = True) -> str:
        """获取任务记忆摘要"""
        async with self._lock:
            summary = ""
            
            # 1. 关键事实摘要
            if include_key_facts and self.key_facts:
                summary += "关键事实:\n"
                task_facts = [v for k, v in self.key_facts.items() if f"task:{task_id}" in k]
                for fact in task_facts[-self.config.key_facts_summary_limit:]:  # 显示最近关键事实
                    summary += f"- {fact}\n"
                summary += "\n"
            
            # 2. 压缩记忆摘要
            if self.compressed_memories:
                summary += "压缩记忆块:\n"
                for i, mem in enumerate(self.compressed_memories[-self.config.compressed_memory_summary_limit:]):  # 显示最近压缩块
                    summary += f"记忆块 #{len(self.compressed_memories)-i}:\n"
                    summary += f"- 状态: {mem.current_status}\n"
                    summary += f"- 关键发现: {', '.join(mem.key_findings[:self.config.key_findings_display_limit])}"
                    if len(mem.key_findings) > self.config.key_findings_display_limit:
                        summary += f" 等{len(mem.key_findings)}项"
                    summary += "\n"
                    
                    if mem.failed_attempts:
                        summary += f"- 失败尝试: {', '.join(mem.failed_attempts[:self.config.failed_attempts_display_limit])}"
                        if len(mem.failed_attempts) > self.config.failed_attempts_display_limit:
                            summary += f" 等{len(mem.failed_attempts)}项"
                        summary += "\n"
                    
                    if mem.next_steps:
                        summary += f"- 建议步骤: {mem.next_steps[0]}\n"
                    
                    summary += f"- 来源: 基于{mem.source_steps}个历史步骤\n\n"
            
            # 3. 最近详细步骤
            if task_id in self.task_steps and self.task_steps[task_id]:
                summary += "最近详细步骤:\n"
                for i, step in enumerate(self.task_steps[task_id]):
                    step_num = len(self.task_steps[task_id]) - i
                    summary += f"步骤 {step_num}:\n"
                    summary += f"- 目的: {step.purpose}\n"
                    summary += f"- 命令: {step.content}\n"
                    
                    if step.output:
                        summary += f"- 输出: {step.output[:self.config.step_output_display_length]}{'...' if len(step.output) > self.config.step_output_display_length else ''}\n"
                    
                    if step.analysis:
                        analysis = step.analysis.get("analysis", "无分析")
                        summary += f"- 分析: {analysis}\n"
                    
                    if not step.success:
                        summary += f"- 状态: 失败 - {step.error}\n"
                    
                    # 显示失败次数
                    if step.content in self.failed_attempts:
                        summary += f"- 历史失败次数: {self.failed_attempts[step.content]}\n"
                    
                    summary += "\n"
            
            return summary if summary else "无历史记录"

    async def get_global_memory_summary(self) -> str:
        """获取全局记忆摘要"""
        async with self._lock:
            summary = "全局任务记忆摘要\n"
            summary += "=" * 50 + "\n"
            
            # 任务统计
            total_tasks = len(self.task_registry)
            running_tasks = len([t for t in self.task_registry.values() if t.get("status") == "running"])
            completed_tasks = len([t for t in self.task_registry.values() if t.get("status") == "completed"])
            
            summary += "任务统计:\n"
            summary += f"- 总任务数: {total_tasks}\n"
            summary += f"- 运行中: {running_tasks}\n"
            summary += f"- 已完成: {completed_tasks}\n\n"
            
            # 记忆统计
            total_steps = sum(len(steps) for steps in self.task_steps.values())
            total_compressed = len(self.compressed_memories)
            total_facts = len(self.key_facts)
            total_failures = len(self.failed_attempts)
            
            summary += "记忆统计:\n"
            summary += f"- 总步骤数: {total_steps}\n"
            summary += f"- 压缩记忆块: {total_compressed}\n"
            summary += f"- 关键事实: {total_facts}\n"
            summary += f"- 失败尝试: {total_failures}\n\n"
            
            # 最近活动
            if self.compressed_memories:
                summary += "最近压缩记忆:\n"
                for mem in self.compressed_memories[-self.config.compressed_memory_global_limit:]:  # 最近压缩记忆
                    summary += f"- {mem.current_status} (基于{mem.source_steps}步骤)\n"
                    if mem.key_findings:
                        summary += f"  关键发现: {mem.key_findings[0]}\n"
                summary += "\n"
            
            return summary

    async def get_failed_attempts_summary(self) -> Dict[str, int]:
        """获取失败尝试摘要"""
        async with self._lock:
            return self.failed_attempts.copy()

    async def clear_task_memory(self, task_id: str) -> bool:
        """清除指定任务的记忆"""
        async with self._lock:
            if task_id in self.task_steps:
                del self.task_steps[task_id]
                logger.info(f"已清除任务 {task_id} 的记忆")
                return True
            return False

    async def clear_all_memory(self) -> None:
        """清除所有记忆"""
        async with self._lock:
            self.task_steps.clear()
            self.compressed_memories.clear()
            self.key_facts.clear()
            self.failed_attempts.clear()
            # 清除会话级别的记忆
            self.session_memories.clear()
            self.session_task_mapping.clear()
            self.analysis_session_mapping.clear()
            logger.info("已清除所有记忆")

    # ============ 会话级别的记忆管理方法 ============
    
    async def get_session_memory_summary(self, session_id: str) -> Dict[str, Any]:
        """获取会话记忆摘要"""
        async with self._lock:
            if session_id not in self.session_memories:
                return {"error": f"会话 {session_id} 不存在"}
            
            session_memory = self.session_memories[session_id]
            
            # 构建会话摘要
            summary = {
                "session_id": session_id,
                "created_at": session_memory["created_at"],
                "last_activity": session_memory["last_activity"],
                "tasks_count": len(session_memory["tasks"]),
                "compressed_memories_count": len(session_memory["compressed_memories"]),
                "key_facts_count": len(session_memory["key_facts"]),
                "failed_attempts_count": len(session_memory["failed_attempts"]),
                "tasks": session_memory["tasks"],
                "recent_key_facts": list(session_memory["key_facts"].values())[-5:],  # 最近5个关键事实
                "recent_compressed_memories": [
                    {
                        "memory_id": mem.memory_id,
                        "key_findings": mem.key_findings[:3],  # 前3个关键发现
                        "current_status": mem.current_status,
                        "source_steps": mem.source_steps
                    }
                    for mem in session_memory["compressed_memories"][-3:]  # 最近3个压缩记忆
                ],
                "failed_attempts": dict(list(session_memory["failed_attempts"].items())[-5:])  # 最近5个失败尝试
            }
            
            return summary
    
    async def get_session_compressed_memories(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的压缩记忆"""
        async with self._lock:
            if session_id not in self.session_memories:
                return []
            
            session_memory = self.session_memories[session_id]
            return [
                {
                    "memory_id": mem.memory_id,
                    "key_findings": mem.key_findings,
                    "failed_attempts": mem.failed_attempts,
                    "current_status": mem.current_status,
                    "next_steps": mem.next_steps,
                    "source_steps": mem.source_steps
                }
                for mem in session_memory["compressed_memories"]
            ]
    
    async def get_session_key_facts(self, session_id: str) -> Dict[str, str]:
        """获取会话的关键事实"""
        async with self._lock:
            if session_id not in self.session_memories:
                return {}
            
            return self.session_memories[session_id]["key_facts"].copy()
    
    async def get_session_failed_attempts(self, session_id: str) -> Dict[str, int]:
        """获取会话的失败尝试"""
        async with self._lock:
            if session_id not in self.session_memories:
                return {}
            
            return self.session_memories[session_id]["failed_attempts"].copy()
    
    async def get_session_tasks(self, session_id: str) -> List[Dict[str, Any]]:
        """获取会话的所有任务"""
        async with self._lock:
            if session_id not in self.session_memories:
                return []
            
            tasks = []
            for task_id in self.session_memories[session_id]["tasks"]:
                if task_id in self.task_registry:
                    task_info = self.task_registry[task_id].copy()
                    task_info["steps_count"] = len(self.task_steps.get(task_id, []))
                    tasks.append(task_info)
            
            return tasks
    
    async def clear_session_memory(self, session_id: str) -> bool:
        """清除指定会话的记忆"""
        async with self._lock:
            if session_id not in self.session_memories:
                return False
            
            # 清除会话相关的任务
            for task_id in self.session_memories[session_id]["tasks"]:
                if task_id in self.task_steps:
                    del self.task_steps[task_id]
                if task_id in self.task_registry:
                    del self.task_registry[task_id]
                if task_id in self.session_task_mapping:
                    del self.session_task_mapping[task_id]
            
            # 清除会话记忆
            del self.session_memories[session_id]
            
            # 清除分析会话映射
            analysis_sessions_to_remove = [
                analysis_id for analysis_id, orig_session_id in self.analysis_session_mapping.items()
                if orig_session_id == session_id
            ]
            for analysis_id in analysis_sessions_to_remove:
                del self.analysis_session_mapping[analysis_id]
            
            logger.info(f"已清除会话 {session_id} 的所有记忆")
            return True
    
    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话的摘要信息"""
        async with self._lock:
            sessions = []
            for session_id, session_memory in self.session_memories.items():
                sessions.append({
                    "session_id": session_id,
                    "created_at": session_memory["created_at"],
                    "last_activity": session_memory["last_activity"],
                    "tasks_count": len(session_memory["tasks"]),
                    "compressed_memories_count": len(session_memory["compressed_memories"]),
                    "key_facts_count": len(session_memory["key_facts"]),
                    "failed_attempts_count": len(session_memory["failed_attempts"])
                })
            
            # 按最后活动时间排序
            sessions.sort(key=lambda x: x["last_activity"], reverse=True)
            return sessions


_SCHEDULER: Optional[_TaskScheduler] = None


def get_task_scheduler(config: Optional[Any] = None) -> _TaskScheduler:
    """获取全局任务调度器单例"""
    global _SCHEDULER
    if _SCHEDULER is None:
        _SCHEDULER = _TaskScheduler(config)
    return _SCHEDULER


