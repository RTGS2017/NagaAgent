#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent独立服务 - 基于博弈论架构的意图分析和任务调度服务
提供意图分析、任务规划和调度功能
"""

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import multiprocessing as mp

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from system.config import config
from agentserver.core.agent_manager import get_agent_manager
from agentserver.task_planner import TaskPlanner
from agentserver.task_scheduler import TaskScheduler
from agentserver.task_deduper import get_task_deduper
from agentserver.background_analyzer import get_background_analyzer
from agentserver.parallel_executor import get_parallel_executor
from agentserver.computer_use_scheduler import get_computer_use_scheduler
from apiserver.result_notifier import get_result_notifier
from apiserver.capability_manager import get_capability_manager

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

app = FastAPI(title="NagaAgent Server", version="1.0.0")

class Modules:
    """全局模块管理器"""
    agent_manager = None
    planner: Optional[TaskPlanner] = None
    scheduler: Optional[TaskScheduler] = None
    analyzer = None
    deduper = None
    
    # 任务跟踪
    task_registry: Dict[str, Dict[str, Any]] = {}
    result_queue: Optional[mp.Queue] = None
    poller_task: Optional[asyncio.Task] = None
    
    # 分析器配置
    analyzer_enabled: bool = True
    analyzer_profile: Dict[str, Any] = {}
    
    # Agent功能标志
    agent_flags: Dict[str, Any] = {
        "mcp_enabled": True,
        "agent_enabled": True,
        "intent_analysis_enabled": True
    }

def _now_iso() -> str:
    """获取当前时间ISO格式"""
    return datetime.now().isoformat()

def _collect_existing_task_descriptions(session_id: Optional[str] = None) -> List[tuple[str, str]]:
    """收集现有任务描述，用于去重判断"""
    items: List[tuple[str, str]] = []
    
    # 从任务注册表收集
    for tid, info in Modules.task_registry.items():
        try:
            if info.get("status") in ("queued", "running"):
                if session_id and info.get("session_id") not in (None, session_id):
                    continue
                params = info.get("params") or {}
                desc = params.get("query") or params.get("instruction") or ""
                if desc:
                    items.append((tid, desc))
        except Exception:
            continue
    
    return items

def _is_duplicate_task(query: str, session_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """使用LLM判断查询是否与现有任务重复"""
    try:
        if not Modules.deduper:
            return False, None
        candidates = _collect_existing_task_descriptions(session_id)
        res = Modules.deduper.judge(query, candidates)
        return bool(res.get("duplicate")), res.get("matched_id")
    except Exception as e:
        logger.error(f"去重判断失败: {e}")
        return False, None

async def _background_analyze_and_plan(messages: List[Dict[str, Any]], session_id: Optional[str] = None):
    """后台异步意图分析和任务规划"""
    if not Modules.analyzer or not Modules.planner:
        logger.warning("分析器或规划器未就绪")
        return
    
    try:
        loop = asyncio.get_running_loop()
        # 将同步LLM调用卸载到线程池，避免阻塞事件循环
        analysis = await loop.run_in_executor(None, Modules.analyzer.analyze, messages)
    except Exception as e:
        logger.error(f"意图分析失败: {e}")
        return
    
    try:
        tasks = analysis.get("tasks", []) if isinstance(analysis, dict) else []
        
        if not tasks:
            logger.info(f"会话 {session_id} 未发现可执行任务")
            return
        
        logger.info(f"会话 {session_id} 发现 {len(tasks)} 个潜在任务")
        
        # 为每个任务创建规划
        for task_query in tasks:
            try:
                task_id = str(uuid.uuid4())
                # 检查是否重复
                dup, matched_id = _is_duplicate_task(task_query, session_id)
                if dup:
                    logger.info(f"任务重复，跳过: {task_query} (匹配: {matched_id})")
                    continue
                
                # 创建任务规划
                task_plan = await Modules.planner.assess_and_plan(task_id, task_query, register=True)
                
                # 添加会话上下文
                if session_id:
                    task_plan.meta["session_id"] = session_id
                
                # 根据规划结果调度任务
                if task_plan.meta.get("mcp", {}).get("can_execute") and Modules.agent_flags.get("mcp_enabled", False):
                    # MCP任务调度
                    for step in task_plan.steps:
                        step_id = str(uuid.uuid4())
                        await Modules.scheduler.schedule_mcp_task(step_id, step, session_id)
                        logger.info(f"已调度MCP任务: {step}")
                
                elif task_plan.meta.get("agent", {}).get("can_execute") and Modules.agent_flags.get("agent_enabled", False):
                    # Agent任务调度
                    agent_task_id = str(uuid.uuid4())
                    await Modules.scheduler.schedule_agent_task(agent_task_id, task_query, session_id)
                    logger.info(f"已调度Agent任务: {task_query}")
                
                else:
                    logger.info(f"任务无法执行: {task_query}")
                    
            except Exception as e:
                logger.error(f"任务规划失败: {e}")
                continue
                
    except Exception as e:
        logger.error(f"任务处理失败: {e}")

# ============ API端点 ============

@app.on_event("startup")
async def startup_event():
    """服务启动时初始化模块"""
    try:
        # 初始化Agent管理器
        Modules.agent_manager = get_agent_manager()
        
        # 初始化任务规划器
        Modules.planner = TaskPlanner()
        
        # 初始化任务调度器
        Modules.scheduler = TaskScheduler()
        
        # 初始化意图分析器
        Modules.analyzer = get_background_analyzer()
        
        # 初始化任务去重器
        Modules.deduper = get_task_deduper()
        
        logger.info("NagaAgent服务初始化完成")
        
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时清理资源"""
    try:
        if Modules.poller_task:
            Modules.poller_task.cancel()
        logger.info("NagaAgent服务已关闭")
    except Exception as e:
        logger.error(f"服务关闭失败: {e}")

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": _now_iso(),
        "modules": {
            "analyzer": Modules.analyzer is not None,
            "planner": Modules.planner is not None,
            "scheduler": Modules.scheduler is not None,
            "agent_manager": Modules.agent_manager is not None
        }
    }

@app.post("/analyze_and_plan")
async def analyze_and_plan(payload: Dict[str, Any]):
    """意图分析和任务规划端点"""
    if not Modules.analyzer or not Modules.planner:
        raise HTTPException(503, "分析器/规划器未就绪")
    
    messages = (payload or {}).get("messages", [])
    if not isinstance(messages, list):
        raise HTTPException(400, "messages必须是{role, content}格式的列表")
    
    session_id = (payload or {}).get("session_id")
    
    # Fire-and-forget后台处理
    asyncio.create_task(_background_analyze_and_plan(messages, session_id))
    
    return {
        "success": True, 
        "status": "processed", 
        "accepted_at": _now_iso(),
        "session_id": session_id
    }

@app.post("/agent/flags")
async def set_agent_flags(payload: Dict[str, Any]):
    """设置Agent功能标志"""
    try:
        flags = (payload or {}).get("flags", {})
        Modules.agent_flags.update(flags)
        
        logger.info(f"Agent标志已更新: {Modules.agent_flags}")
        
        return {
            "success": True, 
            "agent_flags": Modules.agent_flags
        }
    except Exception as e:
        logger.error(f"设置Agent标志失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")

@app.get("/tasks")
async def get_tasks(session_id: Optional[str] = None):
    """获取任务列表"""
    try:
        tasks = []
        for tid, info in Modules.task_registry.items():
            if session_id and info.get("session_id") != session_id:
                continue
            tasks.append({
                "task_id": tid,
                "status": info.get("status"),
                "params": info.get("params", {}),
                "created_at": info.get("created_at")
            })
        
        return {
            "success": True,
            "tasks": tasks,
            "count": len(tasks)
        }
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    try:
        if task_id in Modules.task_registry:
            Modules.task_registry[task_id]["status"] = "cancelled"
            logger.info(f"任务 {task_id} 已取消")
            return {"success": True, "message": "任务已取消"}
        else:
            raise HTTPException(404, "任务不存在")
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        raise HTTPException(500, f"取消失败: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
