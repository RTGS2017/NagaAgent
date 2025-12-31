#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent独立服务 - 基于博弈论的电脑控制智能体
提供意图识别和电脑控制任务执行功能
"""

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from system.config import config
from system.background_analyzer import get_background_analyzer
from agentserver.agent_computer_control import ComputerControlAgent
from agentserver.task_scheduler import get_task_scheduler, TaskStep
from agentserver.toolkit_manager import toolkit_manager

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI应用生命周期"""
    # startup
    try:
        # 初始化意图分析器
        Modules.analyzer = get_background_analyzer()
        # 初始化电脑控制智能体
        Modules.computer_control = ComputerControlAgent()
        # 初始化任务调度器
        Modules.task_scheduler = get_task_scheduler()
        
        # 设置LLM配置用于智能压缩
        if hasattr(config, 'api') and config.api:
            llm_config = {
                "model": config.api.model,
                "api_key": config.api.api_key,
                "api_base": config.api.base_url
            }
            Modules.task_scheduler.set_llm_config(llm_config)
        
        logger.info("NagaAgent电脑控制服务初始化完成")
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

    # 运行期
    yield

    # shutdown
    try:
        logger.info("NagaAgent电脑控制服务已关闭")
    except Exception as e:
        logger.error(f"服务关闭失败: {e}")

app = FastAPI(title="NagaAgent Computer Control Server", version="1.0.0", lifespan=lifespan)

class Modules:
    """全局模块管理器"""
    analyzer = None
    computer_control = None
    task_scheduler = None

def _now_iso() -> str:
    """获取当前时间ISO格式"""
    return datetime.now().isoformat()

async def _process_computer_control_task(instruction: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """处理电脑控制任务"""
    try:
        logger.info(f"开始处理电脑控制任务: {instruction}")
        
        # 直接调用电脑控制智能体
        result = await Modules.computer_control.handle_handoff({
            "action": "automate_task",
            "target": instruction,
            "parameters": {}
        })
        
        logger.info(f"电脑控制任务完成: {instruction}")
        return {
            "success": True,
            "result": result,
            "task_type": "computer_control",
            "instruction": instruction
        }
        
    except Exception as e:
        logger.error(f"电脑控制任务失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "task_type": "computer_control",
            "instruction": instruction
        }

async def _process_toolkit_call(service_name: str, tool_name: str, agent_call: Dict[str, Any]) -> Dict[str, Any]:
    """处理工具包调用"""
    try:
        logger.info(f"开始处理工具包调用: {service_name}.{tool_name}")
        
        # 提取工具参数（排除已知的字段）
        tool_params = {}
        for key, value in agent_call.items():
            if key not in ["agentType", "service_name", "tool_name", "task_type", "instruction", "parameters"]:
                tool_params[key] = value
        
        # 调用工具包管理器
        result = await toolkit_manager.call_tool(service_name, tool_name, tool_params)
        
        logger.info(f"工具包调用完成: {service_name}.{tool_name}")
        return {
            "success": True,
            "result": result,
            "task_type": "toolkit_call",
            "service_name": service_name,
            "tool_name": tool_name
        }
        
    except Exception as e:
        logger.error(f"工具包调用失败: {e}")
        return {
            "success": False,
            "error": str(e),
            "task_type": "toolkit_call",
            "service_name": service_name,
            "tool_name": tool_name
        }

async def _execute_agent_tasks_async(agent_calls: List[Dict[str, Any]], session_id: str, 
                                   analysis_session_id: str, request_id: str, callback_url: Optional[str] = None):
    """异步执行Agent任务 - 应用与MCP服务器相同的会话管理逻辑"""
    try:
        logger.info(f"[异步执行] 开始执行 {len(agent_calls)} 个Agent任务")
        
        # 处理每个Agent任务
        results = []
        for i, agent_call in enumerate(agent_calls):
            try:
                tool_name = agent_call.get("tool_name", "未知工具")
                service_name = agent_call.get("service_name", "未知服务")
                
                logger.info(f"[异步执行] 执行任务 {i+1}/{len(agent_calls)}: {tool_name} (服务: {service_name})")
                
                # 添加任务步骤到调度器
                await Modules.task_scheduler.add_task_step(request_id, TaskStep(
                    step_id=f"step_{i+1}",
                    task_id=request_id,
                    purpose=f"执行Agent任务: {tool_name}",
                    content=str(agent_call),
                    output="",
                    analysis=None,
                    success=True
                ))
                
                # 判断任务类型：电脑控制任务 vs 工具包调用
                if "instruction" in agent_call and agent_call.get("task_type") == "computer_control":
                    # 电脑控制任务
                    instruction = agent_call.get("instruction", "")
                    logger.info(f"[异步执行] 检测到电脑控制任务: {instruction}")
                    
                    result = await _process_computer_control_task(instruction, session_id)
                    results.append({
                        "agent_call": agent_call,
                        "result": result,
                        "step_index": i
                    })
                    
                    # 更新任务步骤结果
                    await Modules.task_scheduler.add_task_step(request_id, TaskStep(
                        step_id=f"step_{i+1}_result",
                        task_id=request_id,
                        purpose=f"任务结果: {tool_name}",
                        content=f"执行结果: {result.get('success', False)}",
                        output=str(result.get('result', '')),
                        analysis={"analysis": f"任务类型: 电脑控制, 工具: {tool_name}, 服务: {service_name}"},
                        success=result.get('success', False),
                        error=result.get('error')
                    ))
                    
                elif "tool_name" in agent_call and "service_name" in agent_call:
                    # 工具包调用
                    logger.info(f"[异步执行] 检测到工具包调用: {service_name}.{tool_name}")
                    
                    result = await _process_toolkit_call(service_name, tool_name, agent_call)
                    results.append({
                        "agent_call": agent_call,
                        "result": result,
                        "step_index": i
                    })
                    
                    # 更新任务步骤结果
                    await Modules.task_scheduler.add_task_step(request_id, TaskStep(
                        step_id=f"step_{i+1}_result",
                        task_id=request_id,
                        purpose=f"任务结果: {tool_name}",
                        content=f"执行结果: {result.get('success', False)}",
                        output=str(result.get('result', '')),
                        analysis={"analysis": f"任务类型: 工具包调用, 工具: {tool_name}, 服务: {service_name}"},
                        success=result.get('success', False),
                        error=result.get('error')
                    ))
                    
                else:
                    # 未知任务类型
                    logger.warning(f"[异步执行] 未知的任务类型: {agent_call}")
                    result = {
                        "success": False,
                        "error": f"未知的任务类型: {agent_call}"
                    }
                    results.append({
                        "agent_call": agent_call,
                        "result": result,
                        "step_index": i
                    })
                
                logger.info(f"[异步执行] 任务 {i+1} 完成: {result.get('success', False)}")
                
            except Exception as e:
                logger.error(f"[异步执行] 任务 {i+1} 执行失败: {e}")
                import traceback
                logger.error(f"[异步执行] 详细错误信息: {traceback.format_exc()}")
                results.append({
                    "agent_call": agent_call,
                    "result": {"success": False, "error": str(e)},
                    "step_index": i
                })
        
        # 发送回调通知（如果提供了回调URL）
        if callback_url:
            await _send_callback_notification(callback_url, request_id, session_id, analysis_session_id, results)
        
        logger.info(f"[异步执行] 所有Agent任务执行完成: {len(results)} 个任务")
        
    except Exception as e:
        logger.error(f"[异步执行] Agent任务执行失败: {e}")
        import traceback
        logger.error(f"[异步执行] 详细错误信息: {traceback.format_exc()}")
        # 发送错误回调
        if callback_url:
            await _send_callback_notification(callback_url, request_id, session_id, analysis_session_id, [], str(e))

async def _send_callback_notification(callback_url: str, request_id: str, session_id: str, 
                                    analysis_session_id: str, results: List[Dict[str, Any]], error: Optional[str] = None):
    """发送回调通知 - 应用与MCP服务器相同的回调机制"""
    try:
        import httpx
        
        callback_payload = {
            "request_id": request_id,
            "session_id": session_id,
            "analysis_session_id": analysis_session_id,
            "success": error is None,
            "error": error,
            "results": results,
            "completed_at": _now_iso()
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(callback_url, json=callback_payload)
            if response.status_code == 200:
                logger.info(f"[回调通知] Agent任务结果回调成功: {request_id}")
            else:
                logger.error(f"[回调通知] Agent任务结果回调失败: {response.status_code}")
                
    except Exception as e:
        logger.error(f"[回调通知] 发送Agent任务回调失败: {e}")

# ============ API端点 ============

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": _now_iso(),
        "modules": {
            "analyzer": Modules.analyzer is not None,
            "computer_control": Modules.computer_control is not None
        }
    }

@app.post("/schedule")
async def schedule_agent_tasks(payload: Dict[str, Any]):
    """统一的任务调度端点 - 应用与MCP服务器相同的会话管理逻辑"""
    if not Modules.computer_control or not Modules.task_scheduler:
        raise HTTPException(503, "电脑控制智能体或任务调度器未就绪")
    
    # 提取新的请求格式参数
    query = payload.get("query", "")
    agent_calls = payload.get("agent_calls", [])
    session_id = payload.get("session_id")
    analysis_session_id = payload.get("analysis_session_id")
    request_id = payload.get("request_id", str(uuid.uuid4()))
    callback_url = payload.get("callback_url")
    
    try:
        logger.info(f"[统一调度] 接收Agent任务调度请求: {query}")
        logger.info(f"[统一调度] 会话ID: {session_id}, 分析会话ID: {analysis_session_id}, 请求ID: {request_id}")
        
        if not agent_calls:
            return {
                "success": True,
                "status": "no_tasks",
                "message": "未发现可执行的Agent任务",
                "task_id": request_id,
                "accepted_at": _now_iso(),
                "session_id": session_id,
                "analysis_session_id": analysis_session_id
            }

        logger.info(f"[统一调度] 会话 {session_id} 发现 {len(agent_calls)} 个Agent任务")

        # 创建任务调度器任务
        task_id = await Modules.task_scheduler.create_task(
            task_id=request_id,
            purpose=f"执行Agent任务: {query}",
            session_id=session_id,
            analysis_session_id=analysis_session_id
        )

        # 异步执行任务（不阻塞响应）
        asyncio.create_task(_execute_agent_tasks_async(
            agent_calls, session_id, analysis_session_id, request_id, callback_url
        ))

        return {
            "success": True,
            "status": "scheduled",
            "task_id": request_id,
            "message": f"已调度 {len(agent_calls)} 个Agent任务",
            "accepted_at": _now_iso(),
            "session_id": session_id,
            "analysis_session_id": analysis_session_id
        }
        
    except Exception as e:
        logger.error(f"[统一调度] Agent任务调度失败: {e}")
        raise HTTPException(500, f"调度失败: {e}")

@app.post("/analyze_and_execute")
async def analyze_and_execute(payload: Dict[str, Any]):
    """意图分析和电脑控制任务执行 - 保持向后兼容"""
    if not Modules.analyzer or not Modules.computer_control:
        raise HTTPException(503, "分析器或电脑控制智能体未就绪")
    
    messages = (payload or {}).get("messages", [])
    if not isinstance(messages, list):
        raise HTTPException(400, "messages必须是{role, content}格式的列表")
    
    session_id = (payload or {}).get("session_id")
    
    try:
        # 直接执行电脑控制任务，不进行意图分析
        # 意图分析已在API服务器中完成，这里只负责执行具体的Agent任务

        # 从消息中提取任务指令
        tasks = []
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if "执行Agent任务:" in content:
                    # 提取任务指令
                    instruction = content.replace("执行Agent任务:", "").strip()
                    tasks.append({
                        "instruction": instruction
                    })

        if not tasks:
            return {
                "success": True,
                "status": "no_tasks",
                "message": "未发现可执行的电脑控制任务",
                "accepted_at": _now_iso(),
                "session_id": session_id
            }

        logger.info(f"会话 {session_id} 发现 {len(tasks)} 个电脑控制任务")

        # 处理每个任务
        results = []
        for task_instruction in tasks:
            result = await _process_computer_control_task(task_instruction, session_id)
            results.append(result)

        return {
            "success": True,
            "status": "completed",
            "tasks_processed": len(tasks),
            "results": results,
            "accepted_at": _now_iso(),
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"意图分析和任务执行失败: {e}")
        raise HTTPException(500, f"处理失败: {e}")

@app.get("/computer_control/availability")
async def get_computer_control_availability():
    """获取电脑控制可用性"""
    try:
        if not Modules.computer_control:
            return {"ready": False, "reasons": ["电脑控制智能体未初始化"]}
        
        # 检查电脑控制能力
        capabilities = Modules.computer_control.get_capabilities()
        return {
            "ready": capabilities.get("enabled", False),
            "capabilities": capabilities,
            "timestamp": _now_iso()
        }
    except Exception as e:
        logger.error(f"检查电脑控制可用性失败: {e}")
        return {"ready": False, "reasons": [f"检查失败: {e}"]}

@app.post("/computer_control/execute")
async def execute_computer_control_task(payload: Dict[str, Any]):
    """直接执行电脑控制任务"""
    if not Modules.computer_control:
        raise HTTPException(503, "电脑控制智能体未就绪")
    
    instruction = payload.get("instruction", "")
    if not instruction:
        raise HTTPException(400, "instruction不能为空")
    
    try:
        result = await _process_computer_control_task(instruction)
        return {
            "success": result.get("success", False),
            "result": result.get("result"),
            "error": result.get("error"),
            "instruction": instruction
        }
    except Exception as e:
        logger.error(f"执行电脑控制任务失败: {e}")
        raise HTTPException(500, f"执行失败: {e}")

# ============ 任务记忆管理API ============

@app.get("/tasks")
async def get_tasks(session_id: Optional[str] = None):
    """获取任务列表"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        running_tasks = await Modules.task_scheduler.get_running_tasks()
        return {
            "success": True,
            "running_tasks": running_tasks,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """获取指定任务状态"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        task_status = await Modules.task_scheduler.get_task_status(task_id)
        if not task_status:
            raise HTTPException(404, f"任务 {task_id} 不存在")
        
        return {
            "success": True,
            "task": task_status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/tasks/{task_id}/memory")
async def get_task_memory(task_id: str, include_key_facts: bool = True):
    """获取任务记忆摘要"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        memory_summary = await Modules.task_scheduler.get_task_memory_summary(task_id, include_key_facts)
        return {
            "success": True,
            "task_id": task_id,
            "memory_summary": memory_summary
        }
    except Exception as e:
        logger.error(f"获取任务记忆失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/memory/global")
async def get_global_memory():
    """获取全局记忆摘要"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        global_summary = await Modules.task_scheduler.get_global_memory_summary()
        failed_attempts = await Modules.task_scheduler.get_failed_attempts_summary()
        
        return {
            "success": True,
            "global_summary": global_summary,
            "failed_attempts": failed_attempts
        }
    except Exception as e:
        logger.error(f"获取全局记忆失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.post("/tasks/{task_id}/steps")
async def add_task_step(task_id: str, payload: Dict[str, Any]):
    """添加任务步骤"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        step = TaskStep(
            step_id=payload.get("step_id", str(uuid.uuid4())),
            task_id=task_id,
            purpose=payload.get("purpose", "执行步骤"),
            content=payload.get("content", ""),
            output=payload.get("output", ""),
            analysis=payload.get("analysis"),
            success=payload.get("success", True),
            error=payload.get("error")
        )
        
        await Modules.task_scheduler.add_task_step(task_id, step)
        
        return {
            "success": True,
            "message": "步骤添加成功",
            "step_id": step.step_id
        }
    except Exception as e:
        logger.error(f"添加任务步骤失败: {e}")
        raise HTTPException(500, f"添加失败: {e}")

@app.delete("/tasks/{task_id}/memory")
async def clear_task_memory(task_id: str):
    """清除任务记忆"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        success = await Modules.task_scheduler.clear_task_memory(task_id)
        if not success:
            raise HTTPException(404, f"任务 {task_id} 不存在")
        
        return {
            "success": True,
            "message": f"任务 {task_id} 的记忆已清除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除任务记忆失败: {e}")
        raise HTTPException(500, f"清除失败: {e}")

@app.delete("/memory/global")
async def clear_global_memory():
    """清除全局记忆"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        await Modules.task_scheduler.clear_all_memory()
        return {
            "success": True,
            "message": "全局记忆已清除"
        }
    except Exception as e:
        logger.error(f"清除全局记忆失败: {e}")
        raise HTTPException(500, f"清除失败: {e}")

# ============ 会话级别的记忆管理API ============

@app.get("/sessions")
async def get_all_sessions():
    """获取所有会话的摘要信息"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        sessions = await Modules.task_scheduler.get_all_sessions()
        return {
            "success": True,
            "sessions": sessions,
            "total_sessions": len(sessions)
        }
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/sessions/{session_id}/memory")
async def get_session_memory_summary(session_id: str):
    """获取会话记忆摘要"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        summary = await Modules.task_scheduler.get_session_memory_summary(session_id)
        if "error" in summary:
            raise HTTPException(404, summary["error"])
        
        return {
            "success": True,
            "session_id": session_id,
            "memory_summary": summary
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话记忆摘要失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/sessions/{session_id}/compressed_memories")
async def get_session_compressed_memories(session_id: str):
    """获取会话的压缩记忆"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        memories = await Modules.task_scheduler.get_session_compressed_memories(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "compressed_memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        logger.error(f"获取会话压缩记忆失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/sessions/{session_id}/key_facts")
async def get_session_key_facts(session_id: str):
    """获取会话的关键事实"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        key_facts = await Modules.task_scheduler.get_session_key_facts(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "key_facts": key_facts,
            "count": len(key_facts)
        }
    except Exception as e:
        logger.error(f"获取会话关键事实失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/sessions/{session_id}/failed_attempts")
async def get_session_failed_attempts(session_id: str):
    """获取会话的失败尝试"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        failed_attempts = await Modules.task_scheduler.get_session_failed_attempts(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "failed_attempts": failed_attempts,
            "count": len(failed_attempts)
        }
    except Exception as e:
        logger.error(f"获取会话失败尝试失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/sessions/{session_id}/tasks")
async def get_session_tasks(session_id: str):
    """获取会话的所有任务"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        tasks = await Modules.task_scheduler.get_session_tasks(session_id)
        return {
            "success": True,
            "session_id": session_id,
            "tasks": tasks,
            "count": len(tasks)
        }
    except Exception as e:
        logger.error(f"获取会话任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.delete("/sessions/{session_id}/memory")
async def clear_session_memory(session_id: str):
    """清除指定会话的记忆"""
    if not Modules.task_scheduler:
        raise HTTPException(503, "任务调度器未就绪")
    
    try:
        success = await Modules.task_scheduler.clear_session_memory(session_id)
        if not success:
            raise HTTPException(404, f"会话 {session_id} 不存在")
        
        return {
            "success": True,
            "message": f"会话 {session_id} 的记忆已清除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"清除会话记忆失败: {e}")
        raise HTTPException(500, f"清除失败: {e}")

# ============ 文件编辑工具包API ============

@app.get("/tools")
async def list_tools():
    """列出所有可用的工具"""
    try:
        tools = toolkit_manager.get_all_tools()
        return {
            "success": True,
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/toolkits")
async def list_toolkits():
    """列出所有可用的工具包"""
    try:
        toolkits = toolkit_manager.list_toolkits()
        return {
            "success": True,
            "toolkits": toolkits,
            "count": len(toolkits)
        }
    except Exception as e:
        logger.error(f"获取工具包列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.get("/toolkits/{toolkit_name}")
async def get_toolkit_info(toolkit_name: str):
    """获取工具包详细信息"""
    try:
        info = toolkit_manager.get_toolkit_info(toolkit_name)
        if not info:
            raise HTTPException(404, f"工具包不存在: {toolkit_name}")
        
        return {
            "success": True,
            "toolkit": info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取工具包信息失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")

@app.post("/tools/{toolkit_name}/{tool_name}")
async def call_tool(toolkit_name: str, tool_name: str, arguments: Dict[str, Any]):
    """调用工具"""
    try:
        result = await toolkit_manager.call_tool(toolkit_name, tool_name, arguments)
        return {
            "success": True,
            "toolkit": toolkit_name,
            "tool": tool_name,
            "result": result
        }
    except Exception as e:
        logger.error(f"调用工具失败 {toolkit_name}.{tool_name}: {e}")
        raise HTTPException(500, f"调用失败: {e}")

# ============ 文件编辑专用API ============

@app.post("/file/edit")
async def edit_file(request: Dict[str, str]):
    """编辑文件 - 使用SEARCH/REPLACE格式"""
    try:
        path = request.get("path")
        diff = request.get("diff")
        
        if not path or not diff:
            raise HTTPException(400, "缺少必要参数: path 和 diff")
        
        result = await toolkit_manager.call_tool("file_edit", "edit_file", {
            "path": path,
            "diff": diff
        })
        
        return {
            "success": True,
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"编辑文件失败: {e}")
        raise HTTPException(500, f"编辑失败: {e}")

@app.post("/file/write")
async def write_file(request: Dict[str, str]):
    """写入文件"""
    try:
        path = request.get("path")
        content = request.get("content")
        
        if not path or content is None:
            raise HTTPException(400, "缺少必要参数: path 和 content")
        
        result = await toolkit_manager.call_tool("file_edit", "write_file", {
            "path": path,
            "file_text": content
        })
        
        return {
            "success": True,
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"写入文件失败: {e}")
        raise HTTPException(500, f"写入失败: {e}")

@app.get("/file/read")
async def read_file(path: str):
    """读取文件"""
    try:
        result = await toolkit_manager.call_tool("file_edit", "read_file", {
            "path": path
        })
        
        return {
            "success": True,
            "content": result
        }
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        raise HTTPException(500, f"读取失败: {e}")

@app.get("/file/list")
async def list_files(directory: str = "."):
    """列出目录文件"""
    try:
        result = await toolkit_manager.call_tool("file_edit", "list_files", {
            "directory": directory
        })
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        raise HTTPException(500, f"列出失败: {e}")

if __name__ == "__main__":
    import uvicorn
    from agentserver.config import AGENT_SERVER_PORT
    uvicorn.run(app, host="0.0.0.0", port=AGENT_SERVER_PORT)