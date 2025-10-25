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

@app.post("/analyze_and_execute")
async def analyze_and_execute(payload: Dict[str, Any]):
    """意图分析和电脑控制任务执行"""
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)  # 使用8002端口