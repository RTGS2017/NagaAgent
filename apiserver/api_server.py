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
import uuid
import time
import threading
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

from nagaagent_core.api import uvicorn
from nagaagent_core.api import FastAPI, HTTPException, Request, UploadFile, File, Form
from nagaagent_core.api import CORSMiddleware
from nagaagent_core.api import StreamingResponse
from nagaagent_core.api import StaticFiles
from pydantic import BaseModel
from nagaagent_core.core import aiohttp
import shutil
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 流式文本处理模块（仅用于TTS）
from .message_manager import message_manager  # 导入统一的消息管理器

from .llm_service import get_llm_service  # 导入LLM服务

# 导入配置系统
try:
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.config import get_prompt, build_system_prompt  # 导入提示词仓库
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.config import get_prompt, build_system_prompt  # 导入提示词仓库
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理
from ui.utils.response_util import extract_message  # 导入消息提取工具

# 对话核心功能已集成到apiserver


# 统一后台意图分析触发函数 - 已整合到message_manager
def _trigger_background_analysis(session_id: str):
    """统一触发后台意图分析 - 委托给message_manager"""
    message_manager.trigger_background_analysis(session_id)


# 统一保存对话与日志函数 - 已整合到message_manager
def _save_conversation_and_logs(session_id: str, user_message: str, assistant_response: str):
    """统一保存对话历史与日志 - 委托给message_manager"""
    message_manager.save_conversation_and_logs(session_id, user_message, assistant_response)


# 回调工厂类已移除 - 功能已整合到streaming_tool_extractor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        print("[INFO] 正在初始化API服务器...")
        # 对话核心功能已集成到apiserver
        print("[SUCCESS] API服务器初始化完成")
        yield
    except Exception as e:
        print(f"[ERROR] API服务器初始化失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 正在清理资源...")
        # MCP服务现在由mcpserver独立管理，无需清理


# 创建FastAPI应用
app = FastAPI(title="NagaAgent API", description="智能对话助手API服务", version="4.0.0", lifespan=lifespan)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


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


async def _call_mcpserver(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 10.0,
) -> Any:
    """调用 MCP Server 内部接口"""
    import httpx
    from system.config import get_server_port

    port = get_server_port("mcp_server")
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            resp = await client.request(method, url, params=params)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MCP Server 不可达: {e}")
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


# ============ OpenClaw Skill Market ============

OPENCLAW_STATE_DIR = Path.home() / ".openclaw"
OPENCLAW_SKILLS_DIR = OPENCLAW_STATE_DIR / "skills"
OPENCLAW_CONFIG_PATH = OPENCLAW_STATE_DIR / "openclaw.json"
SKILLS_TEMPLATE_DIR = Path(__file__).resolve().parent / "skills_templates"
MCPORTER_DIR = Path.home() / ".mcporter"
MCPORTER_CONFIG_PATH = MCPORTER_DIR / "config.json"

MARKET_ITEMS: List[Dict[str, Any]] = [
    {
        "id": "agent-browser",
        "title": "Agent Browser",
        "description": "Browser automation skill (install SKILL.md only, demo mode).",
        "skill_name": "agent-browser",
        "enabled": True,
        "install": {
            "type": "remote_skill",
            "url": "https://raw.githubusercontent.com/vercel-labs/agent-browser/refs/heads/main/skills/agent-browser/SKILL.md",
        },
    },
    {
        "id": "office-docs",
        "title": "Office Docs (docx + xlsx)",
        "description": "Extract docx/xlsx content with local scripts (no extra deps).",
        "skill_name": "office-docs",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "office-docs",
        },
    },
    {
        "id": "brainstorming",
        "title": "Brainstorming",
        "description": "Guided ideation and design exploration skill.",
        "skill_name": "brainstorming",
        "enabled": True,
        "install": {
            "type": "remote_skill",
            "url": "https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/skills/brainstorming/SKILL.md",
        },
    },
    {
        "id": "context7",
        "title": "Context7 Docs",
        "description": "Query library/API docs via mcporter + context7 MCP (stdio).",
        "skill_name": "context7",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "context7",
        },
    },
    {
        "id": "search",
        "title": "Search (Firecrawl MCP)",
        "description": "Search MCP integration via mcporter + firecrawl-mcp.",
        "skill_name": "search",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "search",
        },
    },
]


def _run_command(command: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _get_openclaw_version() -> Optional[str]:
    if shutil.which("openclaw") is None:
        return None
    try:
        code, stdout, stderr = _run_command(["openclaw", "--version"], timeout=15)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        return None
    if code == 0:
        return stdout or stderr
    return None


def _get_openclaw_skills_data() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if shutil.which("openclaw") is None:
        return None, "openclaw_not_found"
    try:
        code, stdout, stderr = _run_command(["openclaw", "skills", "list", "--json"], timeout=30)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        return None, f"openclaw_skills_list_failed: {exc}"
    if code != 0:
        return None, stderr or stdout or "openclaw_skills_list_failed"
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError as exc:
        return None, f"openclaw_skills_list_invalid_json: {exc}"


def _download_text(url: str, timeout: int = 20) -> str:
    try:
        request = UrlRequest(url, headers={"User-Agent": "NagaAgent/market-installer"})
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"下载失败: {exc}")


def _write_skill_file(skill_name: str, content: str) -> Path:
    skill_dir = OPENCLAW_SKILLS_DIR / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


def _copy_template_dir(template_name: str, skill_name: str) -> None:
    template_dir = SKILLS_TEMPLATE_DIR / template_name
    if not template_dir.exists():
        raise FileNotFoundError(f"模板不存在: {template_dir}")
    skill_dir = OPENCLAW_SKILLS_DIR / skill_name
    for path in template_dir.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(template_dir)
        target_path = skill_dir / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target_path)


def _update_mcporter_firecrawl_config(api_key: Optional[str]) -> Path:
    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    mcporter_config: Dict[str, Any] = {}
    if MCPORTER_CONFIG_PATH.exists():
        try:
            mcporter_config = json.loads(MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mcporter_config = {}
    servers = mcporter_config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    server_entry = servers.get("firecrawl-mcp")
    if not isinstance(server_entry, dict):
        server_entry = {}
    env = server_entry.get("env")
    if not isinstance(env, dict):
        env = {}
    if api_key:
        env["FIRECRAWL_API_KEY"] = api_key
    elif "FIRECRAWL_API_KEY" not in env:
        env["FIRECRAWL_API_KEY"] = "YOUR_FIRECRAWL_API_KEY"
    server_entry.update({"command": "npx", "args": ["-y", "firecrawl-mcp"], "env": env})
    servers["firecrawl-mcp"] = server_entry
    mcporter_config["mcpServers"] = servers
    MCPORTER_CONFIG_PATH.write_text(json.dumps(mcporter_config, ensure_ascii=True, indent=2), encoding="utf-8")
    return MCPORTER_CONFIG_PATH


def _install_agent_browser() -> None:
    if shutil.which("npm") is None:
        raise RuntimeError("未找到 npm，无法安装 agent-browser")
    code, stdout, stderr = _run_command(["npm", "install", "-g", "agent-browser"], timeout=300)
    if code != 0:
        raise RuntimeError(stderr or stdout or "npm install -g agent-browser 失败")
    if shutil.which("agent-browser") is None:
        raise RuntimeError("agent-browser 未安装成功或未在 PATH 中")
    code, stdout, stderr = _run_command(["agent-browser", "install"], timeout=300)
    if code != 0:
        raise RuntimeError(stderr or stdout or "agent-browser install 失败")


def _build_market_item(
    item: Dict[str, Any],
    skills_data: Optional[Dict[str, Any]],
    openclaw_found: bool,
) -> Dict[str, Any]:
    skill_name_value = item.get("skill_name") or item.get("id") or "unknown"
    skill_name = str(skill_name_value)
    skill_entry = None
    if skills_data and isinstance(skills_data.get("skills"), list):
        for entry in skills_data.get("skills", []):
            if entry.get("name") == skill_name:
                skill_entry = entry
                break
    skill_path = OPENCLAW_SKILLS_DIR / skill_name / "SKILL.md"
    installed_by_file = skill_path.exists()
    installed = installed_by_file or bool(skill_entry)
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "description": item.get("description"),
        "skill_name": skill_name,
        "enabled": item.get("enabled", True),
        "installed": installed,
        "eligible": skill_entry.get("eligible") if skill_entry else None,
        "disabled": skill_entry.get("disabled") if skill_entry else None,
        "missing": skill_entry.get("missing") if skill_entry else None,
        "skill_path": str(skill_path),
        "openclaw_visible": bool(skill_entry) if openclaw_found else False,
        "install_type": item.get("install", {}).get("type"),
    }


def _get_market_items_status() -> Dict[str, Any]:
    openclaw_found = shutil.which("openclaw") is not None
    openclaw_version = _get_openclaw_version()
    skills_data, skills_error = _get_openclaw_skills_data()
    items = [_build_market_item(item, skills_data, openclaw_found) for item in MARKET_ITEMS]
    return {
        "openclaw": {
            "found": openclaw_found,
            "version": openclaw_version,
            "skills_dir": str(OPENCLAW_SKILLS_DIR),
            "config_path": str(OPENCLAW_CONFIG_PATH),
            "skills_error": skills_error,
        },
        "items": items,
    }


# 请求模型
class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: Optional[str] = None
    use_self_game: bool = False
    disable_tts: bool = False  # V17: 支持禁用服务器端TTS
    return_audio: bool = False  # V19: 支持返回音频URL供客户端播放
    skip_intent_analysis: bool = False  # 新增：跳过意图分析


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


# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """API根路径"""
    return {
        "name": "NagaAgent API",
        "version": "4.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "agent_ready": True, "timestamp": str(asyncio.get_event_loop().time())}


# ============ OpenClaw 任务状态查询（对外暴露在 API Server） ============


@app.get("/openclaw/tasks")
async def api_openclaw_list_tasks():
    """列出本地缓存的 OpenClaw 任务（来自 agentserver）"""
    return await _call_agentserver("GET", "/openclaw/tasks")


@app.get("/openclaw/tasks/{task_id}")
async def api_openclaw_get_task(
    task_id: str,
    include_history: bool = False,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取 OpenClaw 任务状态（支持查看中间过程）

    - `task_id`: 建议直接使用调度器的 task_id/request_id（agentserver /openclaw/send 支持透传）
    - `include_history=true`: 附带 OpenClaw sessions_history（可用于查看更细粒度过程）
    - `include_tools=true`: history 中尽量包含 tool 相关内容（取决于 OpenClaw 返回）
    """
    return await _call_agentserver(
        "GET",
        f"/openclaw/tasks/{task_id}/detail",
        params={
            "include_history": str(include_history).lower(),
            "history_limit": history_limit,
            "include_tools": str(include_tools).lower(),
        },
    )


@app.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    """获取系统信息"""

    return SystemInfoResponse(
        version="4.0.0",
        status="running",
        available_services=[],  # MCP服务现在由mcpserver独立管理
        api_key_configured=bool(config.api.api_key and config.api.api_key != "sk-placeholder-key-not-set"),
    )


@app.get("/system/config")
async def get_system_config():
    """获取完整系统配置"""
    try:
        config_data = get_config_snapshot()
        return {"status": "success", "config": config_data}
    except Exception as e:
        logger.error(f"获取系统配置失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@app.post("/system/config")
async def update_system_config(payload: Dict[str, Any]):
    """更新系统配置"""
    try:
        success = update_config(payload)
        if success:
            return {"status": "success", "message": "配置更新成功"}
        else:
            raise HTTPException(status_code=500, detail="配置更新失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新系统配置失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@app.get("/openclaw/market/items")
async def list_openclaw_market_items():
    """获取OpenClaw技能市场条目"""
    try:
        status = _get_market_items_status()
        return {"status": "success", **status}
    except Exception as e:
        logger.error(f"获取技能市场失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取技能市场失败: {str(e)}")


@app.post("/openclaw/market/items/{item_id}/install")
async def install_openclaw_market_item(item_id: str, payload: Optional[Dict[str, Any]] = None):
    """安装指定OpenClaw技能市场条目"""
    item = next((entry for entry in MARKET_ITEMS if entry.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    if not item.get("enabled", True):
        raise HTTPException(status_code=400, detail="条目暂不可安装")

    install_spec = item.get("install", {})
    install_type = install_spec.get("type")
    skill_name_value = item.get("skill_name") or item.get("id")
    if not skill_name_value:
        raise HTTPException(status_code=500, detail="技能名称缺失")
    skill_name = str(skill_name_value)

    try:
        if item_id == "agent-browser":
            _install_agent_browser()
        if item_id == "search":
            api_key = None
            if payload and isinstance(payload, dict):
                api_key = payload.get("api_key") or payload.get("FIRECRAWL_API_KEY")
            _update_mcporter_firecrawl_config(api_key)
        if install_type == "remote_skill":
            url = install_spec.get("url")
            if not url:
                raise HTTPException(status_code=500, detail="缺少安装URL")
            content = _download_text(url)
            _write_skill_file(skill_name, content)
        elif install_type == "template_dir":
            template_name = install_spec.get("template")
            if not template_name:
                raise HTTPException(status_code=500, detail="缺少模板名称")
            _copy_template_dir(template_name, skill_name)
        elif install_type == "none":
            raise HTTPException(status_code=400, detail="该条目不支持安装")
        else:
            raise HTTPException(status_code=400, detail="未知安装方式")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安装技能失败({item_id}): {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")

    status = _get_market_items_status()
    installed_item = next((entry for entry in status.get("items", []) if entry.get("id") == item_id), None)
    return {
        "status": "success",
        "message": "安装完成",
        "item": installed_item,
        "openclaw": status.get("openclaw"),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """普通对话接口 - 仅处理纯文本对话"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    try:
        # 分支: 启用博弈论流程（非流式，返回聚合文本）
        if request.use_self_game:
            # 配置项控制：失败时可跳过回退到普通对话 #
            skip_on_error = getattr(getattr(config, "game", None), "skip_on_error", True)  # 兼容无配置情况 #
            enabled = getattr(getattr(config, "game", None), "enabled", False)  # 控制总开关 #
            if enabled:
                try:
                    # 延迟导入以避免启动时循环依赖 #
                    from game.naga_game_system import NagaGameSystem  # 博弈系统入口 #
                    from game.core.models.config import GameConfig  # 博弈系统配置 #

                    # 创建系统并执行用户问题处理 #
                    system = NagaGameSystem(GameConfig())
                    system_response = await system.process_user_question(
                        user_question=request.message, user_id=request.session_id or "api_user"
                    )
                    return ChatResponse(
                        response=system_response.content, session_id=request.session_id, status="success"
                    )
                except Exception as e:
                    print(
                        f"[WARNING] 博弈论流程失败，将{'回退到普通对话' if skip_on_error else '返回错误'}: {e}"
                    )  # 运行时警告 #
                    if not skip_on_error:
                        raise HTTPException(status_code=500, detail=f"博弈论流程失败: {str(e)}")
                    # 否则继续走普通对话流程 #
            # 若未启用或被配置跳过，则直接回退到普通对话分支 #

        # 获取或创建会话ID
        session_id = message_manager.create_session(request.session_id)

        # 构建系统提示词（包含技能元数据）
        system_prompt = build_system_prompt(include_skills=True)

        # 使用消息管理器构建完整的对话消息（纯聊天，不触发工具）
        messages = message_manager.build_conversation_messages(
            session_id=session_id, system_prompt=system_prompt, current_message=request.message
        )

        # 使用整合后的LLM服务（支持 reasoning_content）
        llm_service = get_llm_service()
        llm_response = await llm_service.chat_with_context_and_reasoning(messages, config.api.temperature)

        # 处理完成
        # 统一保存对话历史与日志
        _save_conversation_and_logs(session_id, request.message, llm_response.content)

        # 在用户消息保存到历史后触发后台意图分析（除非明确跳过）
        if not request.skip_intent_analysis:
            _trigger_background_analysis(session_id=session_id)

        return ChatResponse(
            response=extract_message(llm_response.content) if llm_response.content else llm_response.content,
            reasoning_content=llm_response.reasoning_content,
            session_id=session_id,
            status="success",
        )
    except Exception as e:
        print(f"对话处理错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 - 流式文本处理交给streaming_tool_extractor用于TTS"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    async def generate_response() -> AsyncGenerator[str, None]:
        complete_text = ""  # V19: 用于累积完整文本以生成音频
        try:
            # 获取或创建会话ID
            session_id = message_manager.create_session(request.session_id)

            # 发送会话ID信息
            yield f"data: session_id: {session_id}\n\n"

            # 注意：这里不触发后台分析，将在对话保存后触发

            # 构建系统提示词（只使用对话风格提示词）
            system_prompt = build_system_prompt(include_skills=True)

            # 使用消息管理器构建完整的对话消息
            messages = message_manager.build_conversation_messages(
                session_id=session_id, system_prompt=system_prompt, current_message=request.message
            )

            # 初始化语音集成（根据voice_mode和return_audio决定）
            # V19: 如果客户端请求返回音频，则在服务器端生成
            voice_integration = None

            # V19: 混合模式下，如果请求return_audio，则在服务器生成音频
            # 修复双音频问题：return_audio时不启用实时TTS，只在最后生成完整音频
            should_enable_tts = (
                config.system.voice_enabled
                and not request.return_audio  # 修复：return_audio时不启用实时TTS
                and config.voice_realtime.voice_mode != "hybrid"
                and not request.disable_tts  # 兼容旧版本的disable_tts
            )

            if should_enable_tts:
                try:
                    from voice.output.voice_integration import get_voice_integration

                    voice_integration = get_voice_integration()
                    logger.info(
                        f"[API Server] 实时语音集成已启用 (return_audio={request.return_audio}, voice_mode={config.voice_realtime.voice_mode})"
                    )
                except Exception as e:
                    print(f"语音集成初始化失败: {e}")
            else:
                if request.return_audio:
                    logger.info("[API Server] return_audio模式，将在最后生成完整音频")
                elif config.voice_realtime.voice_mode == "hybrid" and not request.return_audio:
                    logger.info("[API Server] 混合模式下且未请求音频，不处理TTS")
                elif request.disable_tts:
                    logger.info("[API Server] 客户端禁用了TTS (disable_tts=True)")

            # 初始化流式文本切割器（仅用于TTS处理）
            # 始终创建tool_extractor以累积文本内容，确保日志保存
            tool_extractor = None
            try:
                from .streaming_tool_extractor import StreamingToolCallExtractor

                tool_extractor = StreamingToolCallExtractor()
                # 只有在需要实时TTS且不是return_audio模式时，才设置voice_integration
                if voice_integration and not request.return_audio:
                    tool_extractor.set_callbacks(
                        on_text_chunk=None,  # 不需要回调，直接处理TTS
                        voice_integration=voice_integration,
                    )
            except Exception as e:
                print(f"流式文本切割器初始化失败: {e}")

            # 使用整合后的流式处理（支持 reasoning_content）
            llm_service = get_llm_service()
            complete_reasoning = ""  # 累积推理内容
            async for chunk in llm_service.stream_chat_with_context(messages, config.api.temperature):
                # 新格式: chunk 是 "data: <base64_json>\n\n"，JSON 结构为 {"type": "content"|"reasoning", "text": "..."}
                # V19: 如果需要返回音频，累积文本（只累积 content，不累积 reasoning）
                if chunk.startswith("data: "):
                    try:
                        import base64
                        import json as json_module

                        data_str = chunk[6:].strip()
                        if data_str and data_str != "[DONE]":
                            decoded = base64.b64decode(data_str).decode("utf-8")
                            chunk_data = json_module.loads(decoded)
                            chunk_type = chunk_data.get("type", "content")
                            chunk_text = chunk_data.get("text", "")

                            if chunk_type == "content":
                                # 累积正式回答内容
                                if request.return_audio:
                                    complete_text += chunk_text
                                # TTS 只处理 content，不处理 reasoning
                                if tool_extractor:
                                    asyncio.create_task(tool_extractor.process_text_chunk(chunk_text))
                            elif chunk_type == "reasoning":
                                # 累积推理内容（可选：用于日志或 UI 显示）
                                complete_reasoning += chunk_text

                            # 保留 type 字段，将完整 JSON 结构重新 base64 编码后 yield
                            chunk_json = json_module.dumps({"type": chunk_type, "text": chunk_text})
                            text_b64 = base64.b64encode(chunk_json.encode('utf-8')).decode('ascii')
                            yield f"data: {text_b64}\n\n"
                            continue
                    except Exception as e:
                        logger.error(f"[API Server] 流式数据解析错误: {e}")

                yield chunk

            # 处理完成

            # V19: 如果请求返回音频，在这里生成并返回音频URL
            if request.return_audio and complete_text:
                try:
                    logger.info(f"[API Server V19] 生成音频，文本长度: {len(complete_text)}")

                    # 使用服务器端的TTS生成音频
                    from voice.tts_wrapper import generate_speech_safe
                    import tempfile
                    import uuid

                    # 生成音频文件
                    tts_voice = config.voice_realtime.tts_voice or "zh-CN-XiaoyiNeural"
                    audio_file = generate_speech_safe(
                        text=complete_text, voice=tts_voice, response_format="mp3", speed=1.0
                    )

                    # 直接使用voice/output播放音频，不再返回给客户端
                    try:
                        from voice.output.voice_integration import get_voice_integration

                        voice_integration = get_voice_integration()
                        voice_integration.receive_audio_url(audio_file)
                        logger.info(f"[API Server V19] 音频已直接播放: {audio_file}")
                    except Exception as e:
                        logger.error(f"[API Server V19] 音频播放失败: {e}")
                        # 如果播放失败，仍然返回给客户端作为备选
                        yield f"data: audio_url: {audio_file}\n\n"

                except Exception as e:
                    logger.error(f"[API Server V19] 音频生成失败: {e}")
                    # traceback已经在文件顶部导入，直接使用
                    print(f"[API Server V19] 详细错误信息:")
                    traceback.print_exc()

            # 完成流式文本切割器处理（非return_audio模式，不阻塞）
            if tool_extractor and not request.return_audio:
                try:
                    # 1.将剩余文本发送到voice_integration中的缓冲区
                    await tool_extractor.finish_processing()
                    pass
                except Exception as e:
                    print(f"流式文本切割器完成处理错误: {e}")

            # 完成语音处理
            if voice_integration and not request.return_audio:  # V19: return_audio模式不需要这里的处理
                try:
                    threading.Thread(
                        # 2.处理缓冲区中的剩余文本
                        target=voice_integration.finish_processing,
                        daemon=True,
                    ).start()
                except Exception as e:
                    print(f"语音集成完成处理错误: {e}")

            # 流式处理完成后，获取完整文本用于保存
            complete_response = ""
            if tool_extractor:
                try:
                    # 获取完整文本内容
                    complete_response = tool_extractor.get_complete_text()
                except Exception as e:
                    print(f"获取完整响应文本失败: {e}")
            elif request.return_audio:
                # V19: 如果是return_audio模式，使用累积的文本
                complete_response = complete_text

            # 统一保存对话历史与日志
            _save_conversation_and_logs(session_id, request.message, complete_response)

            # 在用户消息保存到历史后触发后台意图分析（除非明确跳过）
            if not request.skip_intent_analysis:
                _trigger_background_analysis(session_id)

            # [DONE] 信号已由 llm_service.stream_chat_with_context 发送，无需重复

        except Exception as e:
            print(f"流式对话处理错误: {e}")
            # 使用顶部导入的traceback
            traceback.print_exc()
            yield f"data: error:{str(e)}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        },
    )


@app.get("/memory/stats")
async def get_memory_stats():
    """获取记忆统计信息"""

    try:
        # 记忆系统现在由main.py直接管理
        try:
            from summer_memory.memory_manager import memory_manager

            if memory_manager and memory_manager.enabled:
                stats = memory_manager.get_memory_stats()
                return {"status": "success", "memory_stats": stats}
            else:
                return {"status": "success", "memory_stats": {"enabled": False, "message": "记忆系统未启用"}}
        except ImportError:
            return {"status": "success", "memory_stats": {"enabled": False, "message": "记忆系统模块未找到"}}
    except Exception as e:
        print(f"获取记忆统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取记忆统计失败: {str(e)}")


# ============ MCP Server 代理 ============

@app.get("/mcp/status")
async def get_mcp_status_proxy():
    """代理 MCP Server 状态查询"""
    return await _call_mcpserver("GET", "/status")


@app.get("/mcp/tasks")
async def get_mcp_tasks_proxy(status: Optional[str] = None):
    """代理 MCP 任务列表"""
    params = {"status": status} if status else None
    return await _call_mcpserver("GET", "/tasks", params=params)


@app.get("/memory/quintuples")
async def get_quintuples():
    """获取所有五元组 (用于知识图谱可视化)"""
    try:
        from summer_memory.quintuple_graph import get_all_quintuples
        quintuples = get_all_quintuples()  # returns set[tuple]
        return {
            "status": "success",
            "quintuples": [
                {"subject": q[0], "subject_type": q[1], "predicate": q[2],
                 "object": q[3], "object_type": q[4]}
                for q in quintuples
            ],
            "count": len(quintuples)
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "message": "记忆系统模块未找到"}
    except Exception as e:
        logger.error(f"获取五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取五元组失败: {str(e)}")


@app.get("/memory/quintuples/search")
async def search_quintuples(keywords: str = ""):
    """按关键词搜索五元组"""
    try:
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            raise HTTPException(status_code=400, detail="请提供搜索关键词")
        from summer_memory.quintuple_graph import query_graph_by_keywords
        results = query_graph_by_keywords(keyword_list)
        return {
            "status": "success",
            "quintuples": [
                {"subject": q[0], "subject_type": q[1], "predicate": q[2],
                 "object": q[3], "object_type": q[4]}
                for q in results
            ],
            "count": len(results)
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "message": "记忆系统模块未找到"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索五元组失败: {str(e)}")


@app.get("/sessions")
async def get_sessions():
    """获取所有会话信息 - 委托给message_manager"""
    try:
        return message_manager.get_all_sessions_api()
    except Exception as e:
        print(f"获取会话信息错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话的详细信息 - 委托给message_manager"""
    try:
        return message_manager.get_session_detail_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        print(f"获取会话详情错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话 - 委托给message_manager"""
    try:
        return message_manager.delete_session_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        print(f"删除会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions")
async def clear_all_sessions():
    """清空所有会话 - 委托给message_manager"""
    try:
        return message_manager.clear_all_sessions_api()
    except Exception as e:
        print(f"清空会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/document", response_model=FileUploadResponse)
async def upload_document(file: UploadFile = File(...), description: str = Form(None)):
    """上传文档接口"""
    try:
        # 确保上传目录存在
        upload_dir = Path("uploaded_documents")
        upload_dir.mkdir(exist_ok=True)

        # 使用原始文件名
        filename = file.filename
        file_path = upload_dir / filename

        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 获取文件信息
        stat = file_path.stat()

        return FileUploadResponse(
            filename=filename,
            file_path=str(file_path.absolute()),
            file_size=stat.st_size,
            file_type=file_path.suffix,
            upload_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        )
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


# 挂载LLM服务路由以支持 /llm/chat
from .llm_service import llm_app

app.mount("/llm", llm_app)


# 新增：日志解析相关API接口
@app.get("/logs/context/statistics")
async def get_log_context_statistics(days: int = 7):
    """获取日志上下文统计信息"""
    try:
        statistics = message_manager.get_context_statistics(days)
        return {"status": "success", "statistics": statistics}
    except Exception as e:
        print(f"获取日志上下文统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@app.get("/logs/context/load")
async def load_log_context(days: int = 3, max_messages: int = None):
    """加载日志上下文"""
    try:
        messages = message_manager.load_recent_context(days=days, max_messages=max_messages)
        return {"status": "success", "messages": messages, "count": len(messages), "days": days}
    except Exception as e:
        print(f"加载日志上下文错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"加载上下文失败: {str(e)}")


# Web前端工具状态轮询存储
_tool_status_store: Dict[str, Dict] = {"current": {"message": "", "visible": False}}

# Web前端 ClawdBot 回复存储（轮询获取）
_clawdbot_replies: list = []


@app.get("/tool_status")
async def get_tool_status():
    """获取当前工具调用状态（供Web前端轮询）"""
    return _tool_status_store.get("current", {"message": "", "visible": False})


@app.get("/clawdbot/replies")
async def get_clawdbot_replies():
    """获取并清空 ClawdBot 待显示回复（供Web前端轮询）"""
    replies = list(_clawdbot_replies)
    _clawdbot_replies.clear()
    return {"replies": replies}


@app.post("/tool_notification")
async def tool_notification(payload: Dict[str, Any]):
    """接收工具调用状态通知，只显示工具调用状态，不显示结果"""
    try:
        session_id = payload.get("session_id")
        tool_calls = payload.get("tool_calls", [])
        message = payload.get("message", "")
        stage = payload.get("stage", "")
        auto_hide_ms_raw = payload.get("auto_hide_ms", 0)

        try:
            auto_hide_ms = int(auto_hide_ms_raw)
        except (TypeError, ValueError):
            auto_hide_ms = 0

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        # 记录工具调用状态（不处理结果，结果由tool_result_callback处理）
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name", "未知工具")
            service_name = tool_call.get("service_name", "未知服务")
            status = tool_call.get("status", "starting")
            logger.info(f"工具调用状态: {tool_name} ({service_name}) - {status}")

        display_message = message
        if not display_message:
            if stage == "detecting":
                display_message = "正在检测工具调用"
            elif stage == "executing":
                display_message = f"检测到{len(tool_calls)}个工具调用，执行中"
            elif stage == "none":
                display_message = "未检测到工具调用"

        if stage == "hide":
            _hide_tool_status_in_ui()
        elif display_message:
            _emit_tool_status_to_ui(display_message, auto_hide_ms)

        return {
            "success": True,
            "message": "工具调用状态通知已接收",
            "tool_calls": tool_calls,
            "display_message": display_message,
            "stage": stage,
            "auto_hide_ms": auto_hide_ms,
        }

    except Exception as e:
        logger.error(f"工具调用通知处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@app.post("/tool_result_callback")
async def tool_result_callback(payload: Dict[str, Any]):
    """接收MCP工具执行结果回调，让主AI基于原始对话和工具结果重新生成回复"""
    try:
        session_id = payload.get("session_id")
        task_id = payload.get("task_id")
        result = payload.get("result", {})
        success = payload.get("success", False)

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        _emit_tool_status_to_ui("生成工具回调", 0)

        logger.info(f"[工具回调] 开始处理工具回调，会话: {session_id}, 任务ID: {task_id}")
        logger.info(f"[工具回调] 回调内容: {result}")

        # 获取工具执行结果
        tool_result = result.get("result", "执行成功") if success else result.get("error", "未知错误")
        logger.info(f"[工具回调] 工具执行结果: {tool_result}")

        # 获取原始对话的最后一条用户消息（触发工具调用的消息）
        session_messages = message_manager.get_messages(session_id)
        original_user_message = ""
        for msg in reversed(session_messages):
            if msg.get("role") == "user":
                original_user_message = msg.get("content", "")
                break

        # 构建包含工具结果的用户消息
        enhanced_message = f"{original_user_message}\n\n[工具执行结果]: {tool_result}"
        logger.info(f"[工具回调] 构建增强消息: {enhanced_message[:200]}...")

        # 构建对话风格提示词和消息
        system_prompt = build_system_prompt(include_skills=True)
        messages = message_manager.build_conversation_messages(
            session_id=session_id, system_prompt=system_prompt, current_message=enhanced_message
        )

        logger.info(f"[工具回调] 开始生成工具后回复...")

        # 使用LLM服务基于原始对话和工具结果重新生成回复
        try:
            llm_service = get_llm_service()
            response_text = await llm_service.chat_with_context(messages, temperature=0.7)
            logger.info(f"[工具回调] 工具后回复生成成功，内容: {response_text[:200]}...")
        except Exception as e:
            logger.error(f"[工具回调] 调用LLM服务失败: {e}")
            response_text = f"处理工具结果时出错: {str(e)}"

        # 只保存AI回复到历史记录（用户消息已在正常对话流程中保存）
        message_manager.add_message(session_id, "assistant", response_text)
        logger.info(f"[工具回调] AI回复已保存到历史")

        # 保存对话日志到文件
        message_manager.save_conversation_log(original_user_message, response_text, dev_mode=False)
        logger.info(f"[工具回调] 对话日志已保存")

        # 通过UI通知接口将AI回复发送给UI
        logger.info(f"[工具回调] 开始发送AI回复到UI...")
        await _notify_ui_refresh(session_id, response_text)
        _hide_tool_status_in_ui()

        logger.info(f"[工具回调] 工具结果处理完成，回复已发送到UI")

        return {
            "success": True,
            "message": "工具结果已通过主AI处理并返回给UI",
            "response": response_text,
            "task_id": task_id,
            "session_id": session_id,
        }

    except Exception as e:
        _hide_tool_status_in_ui()
        logger.error(f"[工具回调] 工具结果回调处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@app.post("/tool_result")
async def tool_result(payload: Dict[str, Any]):
    """接收工具执行结果并显示在UI上"""
    try:
        session_id = payload.get("session_id")
        result = payload.get("result", "")
        notification_type = payload.get("type", "")
        ai_response = payload.get("ai_response", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"工具执行结果: {result}")

        # 如果是工具完成后的AI回复，通过信号机制通知UI线程显示
        if notification_type == "tool_completed_with_ai_response" and ai_response:
            try:
                # 使用Qt信号机制在主线程中安全地更新UI
                from ui.controller.tool_chat import chat

                # 直接发射信号，确保在主线程中执行
                chat.tool_ai_response_received.emit(ai_response)
                logger.info(f"[UI] 已通过信号机制通知UI显示AI回复，长度: {len(ai_response)}")
            except Exception as e:
                logger.error(f"[UI] 调用UI控制器显示AI回复失败: {e}")

        return {"success": True, "message": "工具结果已接收", "result": result, "session_id": session_id}

    except Exception as e:
        logger.error(f"处理工具结果失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@app.post("/save_tool_conversation")
async def save_tool_conversation(payload: Dict[str, Any]):
    """保存工具对话历史"""
    try:
        session_id = payload.get("session_id")
        user_message = payload.get("user_message", "")
        assistant_response = payload.get("assistant_response", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"[保存工具对话] 开始保存工具对话历史，会话: {session_id}")

        # 保存用户消息（工具执行结果）
        if user_message:
            message_manager.add_message(session_id, "user", user_message)

        # 保存AI回复
        if assistant_response:
            message_manager.add_message(session_id, "assistant", assistant_response)

        logger.info(f"[保存工具对话] 工具对话历史已保存，会话: {session_id}")

        return {"success": True, "message": "工具对话历史已保存", "session_id": session_id}

    except Exception as e:
        logger.error(f"[保存工具对话] 保存工具对话历史失败: {e}")
        raise HTTPException(500, f"保存失败: {str(e)}")


@app.post("/ui_notification")
async def ui_notification(payload: Dict[str, Any]):
    """UI通知接口 - 用于直接控制UI显示"""
    try:
        session_id = payload.get("session_id")
        action = payload.get("action", "")
        ai_response = payload.get("ai_response", "")
        status_text = payload.get("status_text", "")
        auto_hide_ms_raw = payload.get("auto_hide_ms", 0)

        try:
            auto_hide_ms = int(auto_hide_ms_raw)
        except (TypeError, ValueError):
            auto_hide_ms = 0

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"UI通知: {action}, 会话: {session_id}")

        # 处理显示工具AI回复的动作
        if action == "show_tool_ai_response" and ai_response:
            try:
                from ui.controller.tool_chat import chat

                # 直接发射信号，确保在主线程中执行
                chat.tool_ai_response_received.emit(ai_response)
                logger.info(f"[UI通知] 已通过信号机制显示工具AI回复，长度: {len(ai_response)}")
                return {"success": True, "message": "AI回复已显示"}
            except Exception as e:
                logger.error(f"[UI通知] 显示工具AI回复失败: {e}")
                raise HTTPException(500, f"显示AI回复失败: {str(e)}")

        # 处理显示 ClawdBot 回复的动作
        if action == "show_clawdbot_response" and ai_response:
            _clawdbot_replies.append(ai_response)
            try:
                from ui.controller.tool_chat import chat

                chat.clawdbot_response_received.emit(ai_response)
                logger.info(f"[UI通知] 已通过信号机制显示 ClawdBot 回复，长度: {len(ai_response)}")
            except Exception as e:
                logger.warning(f"[UI通知] Qt信号发送失败（Web模式下正常）: {e}")
            return {"success": True, "message": "ClawdBot 回复已存储"}

        if action == "show_tool_status" and status_text:
            _emit_tool_status_to_ui(status_text, auto_hide_ms)
            return {"success": True, "message": "工具状态已显示"}

        if action == "hide_tool_status":
            _hide_tool_status_in_ui()
            return {"success": True, "message": "工具状态已隐藏"}

        return {"success": True, "message": "UI通知已处理"}

    except Exception as e:
        logger.error(f"处理UI通知失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


async def _trigger_chat_stream_no_intent(session_id: str, response_text: str):
    """触发聊天流式响应但不触发意图分析 - 发送纯粹的AI回复到UI"""
    try:
        logger.info(f"[UI发送] 开始发送AI回复到UI，会话: {session_id}")
        logger.info(f"[UI发送] 发送内容: {response_text[:200]}...")

        # 直接调用现有的流式对话接口，但跳过意图分析
        import httpx

        # 构建请求数据 - 使用纯粹的AI回复内容，并跳过意图分析
        chat_request = {
            "message": response_text,  # 直接使用AI回复内容，不加标记
            "stream": True,
            "session_id": session_id,
            "use_self_game": False,
            "disable_tts": False,
            "return_audio": False,
            "skip_intent_analysis": True,  # 关键：跳过意图分析
        }

        # 调用现有的流式对话接口
        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/chat/stream"

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", api_url, json=chat_request) as response:
                if response.status_code == 200:
                    # 处理流式响应，包括TTS切割
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            # 这里可以进一步处理流式响应
                            # 或者直接让UI处理流式响应
                            pass

                    logger.info(f"[UI发送] AI回复已成功发送到UI: {session_id}")
                    logger.info(f"[UI发送] 成功显示到UI")
                else:
                    logger.error(f"[UI发送] 调用流式对话接口失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI发送] 触发聊天流式响应失败: {e}")


async def _notify_ui_refresh(session_id: str, response_text: str):
    """通知UI刷新会话历史"""
    try:
        import httpx

        # 通过UI通知接口直接显示AI回复
        ui_notification_payload = {
            "session_id": session_id,
            "action": "show_tool_ai_response",
            "ai_response": response_text,
        }

        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/ui_notification"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(api_url, json=ui_notification_payload)
            if response.status_code == 200:
                logger.info(f"[UI通知] AI回复显示通知发送成功: {session_id}")
            else:
                logger.error(f"[UI通知] AI回复显示通知失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI通知] 通知UI刷新失败: {e}")


def _emit_tool_status_to_ui(status_text: str, auto_hide_ms: int = 0) -> None:
    """通过Qt信号向UI发送工具状态提示，同时更新Web可轮询的状态存储"""
    _tool_status_store["current"] = {"message": status_text, "visible": True}
    try:
        from ui.controller.tool_chat import chat

        chat.tool_status_received.emit(status_text, max(0, auto_hide_ms))
    except Exception as e:
        logger.error(f"[UI通知] 发送工具状态提示失败: {e}")


def _hide_tool_status_in_ui() -> None:
    """通过Qt信号隐藏工具状态提示，同时更新Web可轮询的状态存储"""
    _tool_status_store["current"] = {"message": "", "visible": False}
    try:
        from ui.controller.tool_chat import chat

        chat.tool_status_hide_requested.emit()
    except Exception as e:
        logger.error(f"[UI通知] 隐藏工具状态提示失败: {e}")


async def _send_ai_response_directly(session_id: str, response_text: str):
    """直接发送AI回复到UI"""
    try:
        import httpx

        # 使用非流式接口发送AI回复
        chat_request = {
            "message": f"[工具结果] {response_text}",  # 添加标记让UI知道这是工具结果
            "stream": False,
            "session_id": session_id,
            "use_self_game": False,
            "disable_tts": False,
            "return_audio": False,
            "skip_intent_analysis": True,
        }

        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/chat"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=chat_request)
            if response.status_code == 200:
                logger.info(f"[直接发送] AI回复已通过非流式接口发送到UI: {session_id}")
            else:
                logger.error(f"[直接发送] 非流式接口发送失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[直接发送] 直接发送AI回复失败: {e}")


# 工具执行结果已通过LLM总结并保存到对话历史中
# UI可以通过查询历史获取工具执行结果
