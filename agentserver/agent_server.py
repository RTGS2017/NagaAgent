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
from contextlib import asynccontextmanager

from system.config import config
from system.background_analyzer import get_background_analyzer
from agentserver.agent_computer_control import ComputerControlAgent
from agentserver.task_scheduler import get_task_scheduler, TaskStep
from agentserver.toolkit_manager import toolkit_manager
from agentserver.openclaw import get_openclaw_client, set_openclaw_config

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
        if hasattr(config, "api") and config.api:
            llm_config = {"model": config.api.model, "api_key": config.api.api_key, "api_base": config.api.base_url}
            Modules.task_scheduler.set_llm_config(llm_config)

        # 初始化 OpenClaw 客户端 - 优先从检测器读取配置
        try:
            from agentserver.openclaw import detect_openclaw, OpenClawConfig as ClientOpenClawConfig

            # 检测 OpenClaw 安装状态
            openclaw_status = detect_openclaw(check_connection=False)

            if openclaw_status.installed:
                # 使用检测到的配置
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=openclaw_status.gateway_url or "http://127.0.0.1:18789",
                    gateway_token=openclaw_status.gateway_token,
                    hooks_token=openclaw_status.hooks_token,
                    timeout=120,
                )
                logger.info(f"从 ~/.openclaw 检测到 OpenClaw 配置: {openclaw_config.gateway_url}")
                logger.info(
                    f"  - gateway_token: {'***' + openclaw_config.gateway_token[-8:] if openclaw_config.gateway_token else '未配置'}"
                )
                logger.info(
                    f"  - hooks_token: {'***' + openclaw_config.hooks_token[-8:] if openclaw_config.hooks_token else '未配置'}"
                )
            else:
                # 回退到 config.json 中的配置
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=getattr(config.openclaw, "gateway_url", "http://127.0.0.1:18789")
                    if hasattr(config, "openclaw")
                    else "http://127.0.0.1:18789",
                    gateway_token=getattr(config.openclaw, "gateway_token", None)
                    if hasattr(config, "openclaw")
                    else None,
                    hooks_token=getattr(config.openclaw, "hooks_token", None) if hasattr(config, "openclaw") else None,
                    timeout=120,
                )
                logger.info(f"OpenClaw 未检测到安装，使用配置文件: {openclaw_config.gateway_url}")

            Modules.openclaw_client = get_openclaw_client(openclaw_config)
            logger.info(f"OpenClaw客户端初始化完成: {openclaw_config.gateway_url}")
        except Exception as e:
            logger.warning(f"OpenClaw客户端初始化失败（可选功能）: {e}")
            Modules.openclaw_client = None

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
    openclaw_client = None


def _now_iso() -> str:
    """获取当前时间ISO格式"""
    return datetime.now().isoformat()


async def _process_computer_control_task(instruction: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """处理电脑控制任务"""
    try:
        logger.info(f"开始处理电脑控制任务: {instruction}")

        # 直接调用电脑控制智能体
        result = await Modules.computer_control.handle_handoff(
            {"action": "automate_task", "target": instruction, "parameters": {}}
        )

        logger.info(f"电脑控制任务完成: {instruction}")
        return {"success": True, "result": result, "task_type": "computer_control", "instruction": instruction}

    except Exception as e:
        logger.error(f"电脑控制任务失败: {e}")
        return {"success": False, "error": str(e), "task_type": "computer_control", "instruction": instruction}


async def _execute_agent_tasks_async(
    agent_calls: List[Dict[str, Any]],
    session_id: str,
    analysis_session_id: str,
    request_id: str,
    callback_url: Optional[str] = None,
):
    """异步执行Agent任务 - 应用与MCP服务器相同的会话管理逻辑"""
    try:
        logger.info(f"[异步执行] 开始执行 {len(agent_calls)} 个Agent任务")

        # 处理每个Agent任务
        results = []
        for i, agent_call in enumerate(agent_calls):
            try:
                instruction = agent_call.get("instruction", "")
                tool_name = agent_call.get("tool_name", "未知工具")
                service_name = agent_call.get("service_name", "未知服务")

                logger.info(f"[异步执行] 执行任务 {i + 1}/{len(agent_calls)}: {tool_name} - {instruction}")

                # 添加任务步骤到调度器
                await Modules.task_scheduler.add_task_step(
                    request_id,
                    TaskStep(
                        step_id=f"step_{i + 1}",
                        task_id=request_id,
                        purpose=f"执行Agent任务: {tool_name}",
                        content=instruction,
                        output="",
                        analysis=None,
                        success=True,
                    ),
                )

                # 执行电脑控制任务
                result = await _process_computer_control_task(instruction, session_id)
                results.append({"agent_call": agent_call, "result": result, "step_index": i})

                # 更新任务步骤结果
                await Modules.task_scheduler.add_task_step(
                    request_id,
                    TaskStep(
                        step_id=f"step_{i + 1}_result",
                        task_id=request_id,
                        purpose=f"任务结果: {tool_name}",
                        content=f"执行结果: {result.get('success', False)}",
                        output=str(result.get("result", "")),
                        analysis={
                            "analysis": f"任务类型: {result.get('task_type', 'unknown')}, 工具: {tool_name}, 服务: {service_name}"
                        },
                        success=result.get("success", False),
                        error=result.get("error"),
                    ),
                )

                logger.info(f"[异步执行] 任务 {i + 1} 完成: {result.get('success', False)}")

            except Exception as e:
                logger.error(f"[异步执行] 任务 {i + 1} 执行失败: {e}")
                results.append(
                    {"agent_call": agent_call, "result": {"success": False, "error": str(e)}, "step_index": i}
                )

        # 发送回调通知（如果提供了回调URL）
        if callback_url:
            await _send_callback_notification(callback_url, request_id, session_id, analysis_session_id, results)

        logger.info(f"[异步执行] 所有Agent任务执行完成: {len(results)} 个任务")

    except Exception as e:
        logger.error(f"[异步执行] Agent任务执行失败: {e}")
        # 发送错误回调
        if callback_url:
            await _send_callback_notification(callback_url, request_id, session_id, analysis_session_id, [], str(e))


async def _send_callback_notification(
    callback_url: str,
    request_id: str,
    session_id: str,
    analysis_session_id: str,
    results: List[Dict[str, Any]],
    error: Optional[str] = None,
):
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
            "completed_at": _now_iso(),
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
        "modules": {"analyzer": Modules.analyzer is not None, "computer_control": Modules.computer_control is not None},
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
                "analysis_session_id": analysis_session_id,
            }

        logger.info(f"[统一调度] 会话 {session_id} 发现 {len(agent_calls)} 个Agent任务")

        # 创建任务调度器任务
        task_id = await Modules.task_scheduler.create_task(
            task_id=request_id,
            purpose=f"执行Agent任务: {query}",
            session_id=session_id,
            analysis_session_id=analysis_session_id,
        )

        # 异步执行任务（不阻塞响应）
        asyncio.create_task(
            _execute_agent_tasks_async(agent_calls, session_id, analysis_session_id, request_id, callback_url)
        )

        return {
            "success": True,
            "status": "scheduled",
            "task_id": request_id,
            "message": f"已调度 {len(agent_calls)} 个Agent任务",
            "accepted_at": _now_iso(),
            "session_id": session_id,
            "analysis_session_id": analysis_session_id,
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
                    tasks.append({"instruction": instruction})

        if not tasks:
            return {
                "success": True,
                "status": "no_tasks",
                "message": "未发现可执行的电脑控制任务",
                "accepted_at": _now_iso(),
                "session_id": session_id,
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
            "session_id": session_id,
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
        return {"ready": capabilities.get("enabled", False), "capabilities": capabilities, "timestamp": _now_iso()}
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
            "instruction": instruction,
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
        return {"success": True, "running_tasks": running_tasks, "session_id": session_id}
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

        return {"success": True, "task": task_status}
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
        return {"success": True, "task_id": task_id, "memory_summary": memory_summary}
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

        return {"success": True, "global_summary": global_summary, "failed_attempts": failed_attempts}
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
            error=payload.get("error"),
        )

        await Modules.task_scheduler.add_task_step(task_id, step)

        return {"success": True, "message": "步骤添加成功", "step_id": step.step_id}
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

        return {"success": True, "message": f"任务 {task_id} 的记忆已清除"}
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
        return {"success": True, "message": "全局记忆已清除"}
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
        return {"success": True, "sessions": sessions, "total_sessions": len(sessions)}
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

        return {"success": True, "session_id": session_id, "memory_summary": summary}
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
        return {"success": True, "session_id": session_id, "compressed_memories": memories, "count": len(memories)}
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
        return {"success": True, "session_id": session_id, "key_facts": key_facts, "count": len(key_facts)}
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
            "count": len(failed_attempts),
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
        return {"success": True, "session_id": session_id, "tasks": tasks, "count": len(tasks)}
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

        return {"success": True, "message": f"会话 {session_id} 的记忆已清除"}
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
        return {"success": True, "tools": tools, "count": len(tools)}
    except Exception as e:
        logger.error(f"获取工具列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/toolkits")
async def list_toolkits():
    """列出所有可用的工具包"""
    try:
        toolkits = toolkit_manager.list_toolkits()
        return {"success": True, "toolkits": toolkits, "count": len(toolkits)}
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

        return {"success": True, "toolkit": info}
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
        return {"success": True, "toolkit": toolkit_name, "tool": tool_name, "result": result}
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

        result = await toolkit_manager.call_tool("file_edit", "edit_file", {"path": path, "diff": diff})

        return {"success": True, "result": result}
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

        result = await toolkit_manager.call_tool("file_edit", "write_file", {"path": path, "file_text": content})

        return {"success": True, "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"写入文件失败: {e}")
        raise HTTPException(500, f"写入失败: {e}")


@app.get("/file/read")
async def read_file(path: str):
    """读取文件"""
    try:
        result = await toolkit_manager.call_tool("file_edit", "read_file", {"path": path})

        return {"success": True, "content": result}
    except Exception as e:
        logger.error(f"读取文件失败: {e}")
        raise HTTPException(500, f"读取失败: {e}")


@app.get("/file/list")
async def list_files(directory: str = "."):
    """列出目录文件"""
    try:
        result = await toolkit_manager.call_tool("file_edit", "list_files", {"directory": directory})

        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"列出文件失败: {e}")
        raise HTTPException(500, f"列出失败: {e}")


# ============ OpenClaw 集成 API ============


@app.get("/openclaw/health")
async def openclaw_health_check():
    """检查 OpenClaw Gateway 健康状态"""
    if not Modules.openclaw_client:
        return {"success": False, "status": "not_configured", "message": "OpenClaw 客户端未配置"}

    try:
        health = await Modules.openclaw_client.health_check()
        return {"success": True, "health": health}
    except Exception as e:
        logger.error(f"OpenClaw 健康检查失败: {e}")
        return {"success": False, "status": "error", "error": str(e)}


@app.post("/openclaw/config")
async def configure_openclaw(payload: Dict[str, Any]):
    """配置 OpenClaw 连接

    请求体:
    - gateway_url: Gateway 地址 (默认 http://localhost:18789)
    - token: 认证 token
    - timeout: 超时时间
    - default_model: 默认模型
    - default_channel: 默认通道
    """
    try:
        from agentserver.openclaw import OpenClawConfig as ClientOpenClawConfig

        openclaw_config = ClientOpenClawConfig(
            gateway_url=payload.get("gateway_url", "http://localhost:18789"),
            token=payload.get("token"),
            timeout=payload.get("timeout", 120),
            default_model=payload.get("default_model"),
            default_channel=payload.get("default_channel", "last"),
        )
        set_openclaw_config(openclaw_config)
        Modules.openclaw_client = get_openclaw_client()

        logger.info(f"OpenClaw 配置更新: {openclaw_config.gateway_url}")

        return {"success": True, "message": "OpenClaw 配置已更新", "gateway_url": openclaw_config.gateway_url}
    except Exception as e:
        logger.error(f"OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


@app.post("/openclaw/send")
async def openclaw_send_message(payload: Dict[str, Any]):
    """
    发送消息给 OpenClaw Agent

    使用 POST /hooks/agent 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - message: 消息内容 (必需)
    - task_id: 外部任务ID（可选；用于与调度器task_id对齐）
    - session_key: 会话标识 (可选)
    - name: hook 名称 (可选)
    - channel: 消息通道 (可选)
    - to: 接收者 (可选)
    - model: 模型名称 (可选)
    - wake_mode: 唤醒模式 now/next-heartbeat (可选)
    - deliver: 是否投递 (可选)
    - timeout_seconds: 等待结果超时时间，默认120秒 (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    message = payload.get("message")
    if not message:
        raise HTTPException(400, "message 不能为空")

    # 如果提供了 task_id 但未提供 session_key，则默认使用 task_id 派生稳定会话键，便于按任务查看中间过程
    task_id = payload.get("task_id")
    session_key = payload.get("session_key")
    if task_id and not session_key:
        session_key = f"naga:task:{task_id}"

    try:
        task = await Modules.openclaw_client.send_message(
            message=message,
            session_key=session_key,
            name=payload.get("name"),
            channel=payload.get("channel"),
            to=payload.get("to"),
            model=payload.get("model"),
            wake_mode=payload.get("wake_mode", "now"),
            deliver=payload.get("deliver", False),
            timeout_seconds=payload.get("timeout_seconds", 120),
            task_id=task_id,
        )

        return {
            "success": task.status.value != "failed",
            "task": task.to_dict(),
            "reply": task.result.get("reply") if task.result else None,
            "replies": task.result.get("replies") if task.result else None,
        }
    except Exception as e:
        logger.error(f"OpenClaw 发送消息失败: {e}")
        raise HTTPException(500, f"发送失败: {e}")


@app.post("/openclaw/wake")
async def openclaw_wake(payload: Dict[str, Any]):
    """
    触发 OpenClaw 系统事件

    使用 POST /hooks/wake 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - text: 事件描述 (必需)
    - mode: 触发模式 now/next-heartbeat (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    text = payload.get("text")
    if not text:
        raise HTTPException(400, "text 不能为空")

    try:
        result = await Modules.openclaw_client.wake(text=text, mode=payload.get("mode", "now"))
        return result
    except Exception as e:
        logger.error(f"OpenClaw 触发事件失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.post("/openclaw/tools/invoke")
async def openclaw_invoke_tool(payload: Dict[str, Any]):
    """
    直接调用 OpenClaw 工具

    使用 POST /tools/invoke 端点
    文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api

    请求体:
    - tool: 工具名称 (必需)
    - args: 工具参数 (可选)
    - action: 动作 (可选)
    - session_key: 会话标识 (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    tool = payload.get("tool")
    if not tool:
        raise HTTPException(400, "tool 不能为空")

    try:
        result = await Modules.openclaw_client.invoke_tool(
            tool=tool, args=payload.get("args"), action=payload.get("action"), session_key=payload.get("session_key")
        )
        return result
    except Exception as e:
        logger.error(f"OpenClaw 工具调用失败: {e}")
        raise HTTPException(500, f"调用失败: {e}")


# ============ OpenClaw 本地任务查询 API ============


@app.get("/openclaw/tasks")
async def openclaw_get_local_tasks():
    """获取本地缓存的所有 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        tasks = Modules.openclaw_client.get_all_tasks()
        return {"success": True, "tasks": [task.to_dict() for task in tasks], "count": len(tasks)}
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}")
async def openclaw_get_task(task_id: str):
    """获取单个 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if task:
            return {"success": True, "task": task.to_dict()}
        else:
            raise HTTPException(404, f"任务不存在: {task_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}/detail")
async def openclaw_get_task_detail(
    task_id: str,
    include_history: bool = True,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取单个 OpenClaw 任务详情（包含本地 events 与可选 sessions_history）"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if not task:
            raise HTTPException(404, f"任务不存在: {task_id}")

        resp: Dict[str, Any] = {
            "success": True,
            "task": task.to_dict(),
        }

        if include_history:
            if task.session_key:
                history = await Modules.openclaw_client.get_sessions_history(
                    session_key=task.session_key,
                    limit=history_limit,
                    include_tools=include_tools,
                )
                resp["history"] = history
            else:
                resp["history"] = {"success": True, "messages": [], "note": "task_has_no_session_key"}

        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务详情失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.delete("/openclaw/tasks/completed")
async def openclaw_clear_completed_tasks():
    """清理已完成的 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        Modules.openclaw_client.clear_completed_tasks()
        return {"success": True, "message": "已清理完成的任务"}
    except Exception as e:
        logger.error(f"清理 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"清理失败: {e}")


@app.get("/openclaw/session")
async def openclaw_get_session():
    """
    获取当前 OpenClaw 调度终端会话信息

    用于在设置界面显示 Naga 调度 OpenClaw 的终端连接状态

    返回:
    - 有活跃会话: session_key, created_at, last_activity, message_count, last_run_id, status
    - 无会话: has_session=False, message="请和 OpenClaw 交互以显示交互终端"
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        session_info = Modules.openclaw_client.get_session_info()

        if session_info is None:
            return {"has_session": False, "message": "请和 OpenClaw 交互以显示交互终端"}

        return {"has_session": True, "session": session_info}
    except Exception as e:
        logger.error(f"获取 OpenClaw 会话信息失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/history")
async def openclaw_get_history(session_key: Optional[str] = None, limit: int = 20):
    """
    获取 OpenClaw 会话历史消息

    用于在设置界面显示 OpenClaw Agent 的对话内容

    Args:
        session_key: 会话标识，不传则使用默认会话
        limit: 返回消息条数限制

    Returns:
        会话历史消息列表
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.get_sessions_history(session_key=session_key, limit=limit)
        return result
    except Exception as e:
        logger.error(f"获取 OpenClaw 会话历史失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/status")
async def openclaw_get_status():
    """
    获取 OpenClaw 当前状态

    调用 session_status 工具获取实时状态

    Returns:
        OpenClaw 当前状态文本
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.get_session_status()
        return result
    except Exception as e:
        logger.error(f"获取 OpenClaw 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


# ============ OpenClaw 安装和配置管理 API ============


@app.get("/openclaw/install/check")
async def openclaw_check_installation():
    """
    检查 OpenClaw 安装状态

    Returns:
        安装状态信息
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        status, version = installer.check_installation()

        # 检查 Node.js
        node_ok, node_version = installer.check_node_version()

        return {
            "success": True,
            "status": status.value,
            "version": version,
            "node_ok": node_ok,
            "node_version": node_version,
            "npm_available": installer.check_npm_available(),
        }
    except Exception as e:
        logger.error(f"检查 OpenClaw 安装状态失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


@app.post("/openclaw/install")
async def openclaw_install(payload: Dict[str, Any] = None):
    """
    安装 OpenClaw

    请求体:
    - method: 安装方式 ("npm" 或 "script"，默认 "npm")

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer, InstallMethod

        installer = get_openclaw_installer()

        method_str = (payload or {}).get("method", "npm")
        method = InstallMethod.NPM if method_str == "npm" else InstallMethod.SCRIPT

        result = await installer.install(method)

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 OpenClaw 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/setup")
async def openclaw_setup(payload: Dict[str, Any] = None):
    """
    初始化 OpenClaw 配置

    请求体:
    - hooks_token: Hooks 认证 token（可选，不传则自动生成）

    Returns:
        初始化结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        hooks_token = (payload or {}).get("hooks_token")

        result = await installer.setup(hooks_token)

        return result.to_dict()
    except Exception as e:
        logger.error(f"初始化 OpenClaw 失败: {e}")
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/openclaw/gateway/start")
async def openclaw_start_gateway():
    """启动 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.start_gateway(background=True)

        return result.to_dict()
    except Exception as e:
        logger.error(f"启动 Gateway 失败: {e}")
        raise HTTPException(500, f"启动失败: {e}")


@app.post("/openclaw/gateway/stop")
async def openclaw_stop_gateway():
    """停止 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.stop_gateway()

        return result.to_dict()
    except Exception as e:
        logger.error(f"停止 Gateway 失败: {e}")
        raise HTTPException(500, f"停止失败: {e}")


@app.post("/openclaw/gateway/restart")
async def openclaw_restart_gateway():
    """重启 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.restart_gateway()

        return result.to_dict()
    except Exception as e:
        logger.error(f"重启 Gateway 失败: {e}")
        raise HTTPException(500, f"重启失败: {e}")


@app.post("/openclaw/gateway/install")
async def openclaw_install_gateway_service():
    """安装 Gateway 为系统服务"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.install_gateway_service()

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 Gateway 服务失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.get("/openclaw/gateway/status")
async def openclaw_gateway_status():
    """获取 Gateway 状态"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.check_gateway_status()

        return result
    except Exception as e:
        logger.error(f"获取 Gateway 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/doctor")
async def openclaw_doctor():
    """运行 OpenClaw 健康检查"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.run_doctor()

        return result
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


# ============ OpenClaw 配置管理 API ============


@app.get("/openclaw/config")
async def openclaw_get_config():
    """
    获取 OpenClaw 配置摘要

    只返回安全的配置信息，不包含 token 等敏感数据
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        summary = config_manager.get_current_config_summary()

        return {"success": True, "config": summary}
    except Exception as e:
        logger.error(f"获取 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/config/set")
async def openclaw_set_config(payload: Dict[str, Any]):
    """
    设置 OpenClaw 配置

    只允许修改白名单中的字段

    请求体:
    - field: 字段路径（如 "agents.defaults.model.primary"）
    - value: 新值

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        field = payload.get("field")
        value = payload.get("value")

        if not field:
            raise HTTPException(400, "field 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.set(field, value)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/model")
async def openclaw_set_model(payload: Dict[str, Any]):
    """
    设置默认模型

    请求体:
    - model: 模型标识符（如 "zai/glm-4.7"）
    - alias: 模型别名（可选）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        model = payload.get("model")
        alias = payload.get("alias")

        if not model:
            raise HTTPException(400, "model 不能为空")

        config_manager = get_openclaw_config_manager()

        results = []

        # 设置主模型
        result = config_manager.set_primary_model(model)
        results.append(result.to_dict())

        # 设置别名（如果提供）
        if alias:
            alias_result = config_manager.add_model_alias(model, alias)
            results.append(alias_result.to_dict())

        return {"success": all(r["success"] for r in results), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置模型失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/hooks")
async def openclaw_configure_hooks(payload: Dict[str, Any]):
    """
    配置 Hooks

    请求体:
    - enabled: 是否启用（可选）
    - token: Hooks token（可选，不传则自动生成）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        results = []

        # 启用/禁用
        if "enabled" in payload:
            result = config_manager.set_hooks_enabled(payload["enabled"])
            results.append(result.to_dict())

        # 设置 token
        if "token" in payload:
            token = payload["token"]
        elif payload.get("generate_token"):
            token = config_manager.generate_hooks_token()
        else:
            token = None

        if token:
            result = config_manager.set_hooks_token(token)
            results.append(result.to_dict())

        return {
            "success": all(r["success"] for r in results) if results else True,
            "results": results,
            "token": token,  # 返回生成的 token
        }
    except Exception as e:
        logger.error(f"配置 Hooks 失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


# ============ OpenClaw Skills 管理 API ============


@app.get("/openclaw/skills")
async def openclaw_list_skills():
    """列出已安装的 Skills"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        skills = await installer.list_skills()

        return {"success": True, "skills": skills}
    except Exception as e:
        logger.error(f"列出 Skills 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/skills/install")
async def openclaw_install_skill(payload: Dict[str, Any]):
    """
    安装 Skill

    请求体:
    - skill: Skill 标识符

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        skill = payload.get("skill")
        if not skill:
            raise HTTPException(400, "skill 不能为空")

        installer = get_openclaw_installer()
        result = await installer.install_skill(skill)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安装 Skill 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/skills/enable")
async def openclaw_enable_skill(payload: Dict[str, Any]):
    """
    启用/禁用 Skill

    请求体:
    - skill: Skill 名称
    - enabled: 是否启用

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        skill = payload.get("skill")
        enabled = payload.get("enabled", True)

        if not skill:
            raise HTTPException(400, "skill 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.enable_skill(skill, enabled)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用/禁用 Skill 失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


if __name__ == "__main__":
    import uvicorn
    from agentserver.config import AGENT_SERVER_PORT

    uvicorn.run(app, host="0.0.0.0", port=AGENT_SERVER_PORT)
