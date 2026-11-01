#!/usr/bin/env python3
"""
NagaAgent API服务器
提供RESTful API接口访问NagaAgent功能
"""

import asyncio
import json
import sys
import traceback
import os
import logging
import time
import threading
from datetime import datetime
import subprocess
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, AsyncGenerator, Any, Tuple
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError

# 在导入其他模块前先设置HTTP库日志级别
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

# 创建logger实例
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import shutil
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 流式文本处理模块（仅用于TTS）
from .message_manager import message_manager  # 导入统一的消息管理器

from .llm_service import get_llm_service  # 导入LLM服务
from . import naga_auth  # NagaCAS 认证模块

# 记录哪些会话曾发送过图片，后续消息继续走 VLM 直到新会话
_vlm_sessions: set = set()

# 导入配置系统
try:
    from system.config import get_config, AI_NAME  # 使用新的配置系统
    from system.config import get_prompt, build_system_prompt, build_context_supplement  # 导入提示词仓库
    from system.config import VERSION  # 版本号（唯一来源：pyproject.toml）
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.config import get_config  # 使用新的配置系统
    from system.config import build_system_prompt, build_context_supplement  # 导入提示词仓库
    from system.config import VERSION  # 版本号（唯一来源：pyproject.toml）
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理

# 对话核心功能已集成到apiserver


# 统一保存对话与日志函数 - 已整合到message_manager
def _save_conversation_and_logs(session_id: str, user_message: str, assistant_response: str):
    """统一保存对话历史与日志 - 委托给message_manager"""
    message_manager.save_conversation_and_logs(session_id, user_message, assistant_response)


async def _notify_conversation_event(event: str):
    """通知 agent_server 对话生命周期事件"""
    try:
        from system.config import get_server_port
        import httpx

        async with httpx.AsyncClient(timeout=3.0, proxy=None) as client:
            await client.post(
                f"http://localhost:{get_server_port('agent_server')}/dogtag/conversation_event",
                json={"event": event},
            )
        logger.info(f"[ConversationEvent] 已通知 agent_server: {event}")
    except Exception as e:
        logger.debug(f"[ConversationEvent] 通知失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        print("[INFO] 正在初始化API服务器...")
        # 对话核心功能已集成到apiserver

        # 加载活跃角色配置
        try:
            from system.config import set_active_character, get_config as _gc
            char_name = _gc().system.active_character
            set_active_character(char_name)
        except Exception as e:
            print(f"[WARN] 角色加载失败，使用默认提示词目录: {e}")

        try:
            from apiserver.telemetry import get_telemetry_manager
            await get_telemetry_manager().start()
        except Exception as e:
            print(f"[WARN] Telemetry 初始化失败: {e}")

        print("[SUCCESS] API服务器初始化完成")
        yield
    except Exception as e:
        print(f"[ERROR] API服务器初始化失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 正在清理资源...")
        # MCP服务现在由mcpserver独立管理，无需清理
        try:
            from apiserver.telemetry import get_telemetry_manager
            await get_telemetry_manager().shutdown()
        except Exception as e:
            print(f"[WARN] Telemetry 清理失败: {e}")


# 创建FastAPI应用
app = FastAPI(title="NagaAgent API", description="智能对话助手API服务", version=VERSION, lifespan=lifespan)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def sync_auth_token(request: Request, call_next):
    """每次请求自动同步前端 token 到后端认证状态，避免 token 刷新后后端仍持有旧 token"""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token and token != naga_auth.get_access_token():
            naga_auth.restore_token(token)
    response = await call_next(request)
    return response


# 挂载静态文件
from fastapi.staticfiles import StaticFiles as _StaticFiles
from system.config import CHARACTERS_DIR as _CHARACTERS_DIR
from system.live2d_assets import CUSTOM_LIVE2D_DIR as _CUSTOM_LIVE2D_DIR
if _CHARACTERS_DIR.exists():
    app.mount("/characters", _StaticFiles(directory=str(_CHARACTERS_DIR)), name="characters")
else:
    # 容错：目录缺失时不阻塞 API 启动，避免打包缺资源导致 8000 端口起不来
    try:
        _CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        logger.warning(f"角色目录缺失，已创建空目录: {_CHARACTERS_DIR}")
        app.mount("/characters", _StaticFiles(directory=str(_CHARACTERS_DIR)), name="characters")
    except Exception as e:
        logger.error(f"角色静态目录初始化失败，将跳过 /characters 挂载: {e}")

try:
    _CUSTOM_LIVE2D_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/custom-live2d", _StaticFiles(directory=str(_CUSTOM_LIVE2D_DIR)), name="custom-live2d")
except Exception as e:
    logger.error(f"自定义 Live2D 静态目录初始化失败，将跳过 /custom-live2d 挂载: {e}")

# ============ 运行时状态检查（naga_control） ============


def _is_voice_runtime_paused() -> bool:
    """检查语音是否被 naga_control 运行时暂停"""
    try:
        from apiserver.naga_control import is_voice_paused
        return is_voice_paused()
    except Exception:
        return False


# ============ 内部服务代理 ============


async def _call_agentserver(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 15.0,
) -> Any:
    """调用 agentserver 内部接口（用于透传 OpenClaw 状态查询等能力）"""
    import httpx
    from system.config import get_server_port

    port = get_server_port("agent_server")
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            resp = await client.request(method, url, params=params, json=json_body)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"agentserver 不可达: {e}")
    if resp.status_code >= 400:
        detail = resp.text
        try:
            detail = resp.json()
        except Exception:
            pass
        raise HTTPException(status_code=resp.status_code, detail=detail)
    try:
        return resp.json()
    except Exception:
        return resp.text


# ============ Pydantic 请求/响应模型 ============


class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    disable_tts: bool = False  # V17: 支持禁用服务器端TTS
    return_audio: bool = False  # V19: 支持返回音频URL供客户端播放
    skill: Optional[str] = None  # 用户主动选择的技能名称，注入完整指令到系统提示词
    images: Optional[List[str]] = None  # 截屏图片 base64 数据列表（data:image/png;base64,...）
    temporary: bool = False  # 临时会话标记，临时会话不持久化到磁盘


class ChatResponse(BaseModel):
    response: str
    reasoning_content: Optional[str] = None  # COT 思考过程内容
    session_id: Optional[str] = None
    status: str = "success"


class SystemInfoResponse(BaseModel):
    version: str
    status: str
    available_services: List[str]
    api_key_configured: bool


class FileUploadResponse(BaseModel):
    filename: str
    file_path: str
    file_size: int
    file_type: str
    upload_time: str
    status: str = "success"
    message: str = "文件上传成功"


class DocumentProcessRequest(BaseModel):
    file_path: str
    action: str = "read"  # read, analyze, summarize
    session_id: Optional[str] = None


# 挂载LLM服务路由以支持 /llm/chat
from .llm_service import llm_app

app.mount("/llm", llm_app)


# ============ 注册路由模块 ============

from .routes.forum import router as forum_router
from .routes.auth import router as auth_router
from .routes.session import router as session_router
from .routes.system import router as system_router
from .routes.tools import router as tools_router
from .routes.extensions import router as extensions_router
from .routes.chat import router as chat_router
from .routes.openai_proxy import router as openai_proxy_router
from .routes.telemetry import router as telemetry_router

app.include_router(forum_router)
app.include_router(auth_router)
app.include_router(session_router)
app.include_router(system_router)
app.include_router(tools_router)
app.include_router(extensions_router)
app.include_router(chat_router)
app.include_router(openai_proxy_router)
app.include_router(telemetry_router)
