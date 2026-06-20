"""OpenClaw 技能市场、MCP 服务、技能导入、文件上传、旅行、记忆、搜索代理路由"""

import html
import json
import logging
import re
import shutil
import subprocess
import tempfile
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, List, Optional, Any, Tuple
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import yaml

from system.config import get_config, get_data_dir
from apiserver import naga_auth
from apiserver.api_server import _call_agentserver, FileUploadResponse
from apiserver.telemetry import emit_telemetry
from agentserver.openclaw.state_paths import get_openclaw_config_path, get_openclaw_state_dir

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ OpenClaw Skill Market ============

OPENCLAW_STATE_DIR = get_openclaw_state_dir()
OPENCLAW_SKILLS_DIR = OPENCLAW_STATE_DIR / "skills"
OPENCLAW_CONFIG_PATH = get_openclaw_config_path()
NAGA_DATA_DIR = get_data_dir()
NAGA_SKILLS_DIR = NAGA_DATA_DIR / "skills"
NAGA_PUBLIC_SKILLS_DIR = NAGA_SKILLS_DIR / "public"
NAGA_CACHE_SKILLS_DIR = NAGA_SKILLS_DIR / "cache"
NAGA_AGENTS_DIR = NAGA_DATA_DIR / "agents"
NAGA_AGENTS_MANIFEST_PATH = NAGA_AGENTS_DIR / "agents.json"
SKILLS_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "skills_templates"
MCPORTER_DIR = NAGA_DATA_DIR / "mcporter"
MCPORTER_CONFIG_PATH = MCPORTER_DIR / "config.json"
LEGACY_MCPORTER_DIR = Path.home() / ".mcporter"
LEGACY_MCPORTER_CONFIG_PATH = LEGACY_MCPORTER_DIR / "config.json"
SKILL_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
MAX_SKILL_NAME_LENGTH = 120

for _path in (OPENCLAW_SKILLS_DIR, NAGA_PUBLIC_SKILLS_DIR, NAGA_CACHE_SKILLS_DIR, NAGA_AGENTS_DIR):
    _path.mkdir(parents=True, exist_ok=True)

MARKET_ITEMS: List[Dict[str, Any]] = [
    {
        "id": "agent-browser",
        "title": "Agent Browser",
        "description": "Browser automation skill (offline template install, prebundled runtime preferred).",
        "skill_name": "agent-browser",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "agent-browser",
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


# ============ OpenClaw 辅助函数 ============


def _run_command(
    command: List[str],
    timeout: int = 30,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    import locale
    enc = locale.getpreferredencoding() or "utf-8"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=(sys.platform == "win32"),
        encoding=enc,
        errors="replace",
        cwd=cwd,
        env=env,
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def _download_text(url: str, timeout: int = 20) -> str:
    try:
        request = UrlRequest(url, headers={"User-Agent": "NagaAgent/market-installer"})
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"下载失败: {exc}")


def _write_skill_file(skill_name: str, content: str) -> Path:
    return _write_skill_file_to_dir(OPENCLAW_SKILLS_DIR, skill_name, content)


def _normalize_skill_name(skill_name: str) -> str:
    name = (skill_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="技能名称不能为空")
    if len(name) > MAX_SKILL_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"技能名称不能超过 {MAX_SKILL_NAME_LENGTH} 个字符")
    if name in {".", ".."}:
        raise HTTPException(status_code=400, detail="技能名称不能是路径保留名称")
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="技能名称不能包含路径分隔符")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise HTTPException(status_code=400, detail="技能名称不能包含控制字符")

    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise HTTPException(status_code=400, detail="技能名称不能是绝对路径或盘符路径")
    return name


def _resolve_child_dir(base_dir: Path, child_name: str, label: str = "技能名称") -> Path:
    name = _normalize_skill_name(child_name)
    base = base_dir.resolve(strict=False)
    target = (base / name).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 指向了不允许的目录")
    if target == base:
        raise HTTPException(status_code=400, detail=f"{label} 不能指向根目录")
    return target


def _resolve_skill_dir(base_dir: Path, skill_name: str) -> Path:
    return _resolve_child_dir(base_dir, skill_name, "技能名称")


def _resolve_agent_skills_dir(agent_id: str) -> Path:
    agent_dir = _resolve_child_dir(NAGA_AGENTS_DIR, agent_id, "agent_id")
    return agent_dir / "skills"


def _write_skill_file_to_dir(base_dir: Path, skill_name: str, content: str) -> Path:
    skill_dir = _resolve_skill_dir(base_dir, skill_name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path


def _load_agents_manifest() -> List[Dict[str, Any]]:
    if not NAGA_AGENTS_MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(NAGA_AGENTS_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    agents = data.get("agents")
    return agents if isinstance(agents, list) else []


def _get_agent_record(agent_id: str) -> Optional[Dict[str, Any]]:
    for agent in _load_agents_manifest():
        if agent.get("id") == agent_id:
            return agent
    return None


def _parse_skill_summary(
    skill_dir: Path,
    scope: str,
    source: str,
    owner: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        return None

    name = skill_dir.name
    description = ""
    version = "1.0.0"
    tags: List[str] = []

    try:
        content = skill_path.read_text(encoding="utf-8")
        match = SKILL_FRONTMATTER_PATTERN.match(content)
        if match:
            metadata = yaml.safe_load(match.group(1)) or {}
            name = metadata.get("name") or name
            description = metadata.get("description") or ""
            version = metadata.get("version") or version
            tags = list(metadata.get("tags") or [])
        if not description:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped and stripped != "---" and not stripped.startswith("#"):
                    description = stripped[:120]
                    break
    except Exception as exc:
        logger.warning(f"读取技能摘要失败 [{skill_path}]: {exc}")
        description = "技能内容解析失败"

    item = {
        "name": name,
        "description": description,
        "version": version,
        "tags": tags,
        "scope": scope,
        "source": source,
        "path": str(skill_path),
    }
    if owner:
        item.update({
            "owner_agent_id": owner.get("id"),
            "owner_agent_name": owner.get("name"),
            "owner_engine": owner.get("engine", "openclaw"),
        })
    return item


def _list_skill_dir(
    base_dir: Path,
    scope: str,
    source: str,
    owner: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if not base_dir.exists():
        return []

    items: List[Dict[str, Any]] = []
    for skill_dir in sorted(base_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        item = _parse_skill_summary(skill_dir, scope=scope, source=source, owner=owner)
        if item:
            items.append(item)
    return items


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


def _agent_browser_bin_name() -> str:
    return "agent-browser.cmd" if sys.platform == "win32" else "agent-browser"


def _resolve_packaged_openclaw_runtime_dir() -> Optional[Path]:
    candidates: List[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        candidates.append(meipass / "vendor" / "openclaw")
        candidates.append(meipass.parent.parent / "runtime" / "openclaw")
        candidates.append(meipass.parent.parent / "openclaw-runtime" / "openclaw")
    # 开发环境下也允许直接复用本地构建产物中的预装运行时
    candidates.append(Path(__file__).resolve().parent.parent.parent / "frontend" / "backend-dist" / "runtime" / "openclaw")
    # 开发模式：项目根 runtime/
    candidates.append(Path(__file__).resolve().parent.parent.parent / "runtime" / "openclaw")
    # 开发/打包通用：直接使用项目 vendor/openclaw
    candidates.append(Path(__file__).resolve().parent.parent.parent / "vendor" / "openclaw")
    for candidate in candidates:
        if (candidate / "node_modules").exists():
            return candidate
    return None


def _resolve_prebundled_agent_browser_cmd() -> Optional[str]:
    runtime_dir = _resolve_packaged_openclaw_runtime_dir()
    if not runtime_dir:
        return None
    cmd = runtime_dir / "node_modules" / ".bin" / _agent_browser_bin_name()
    return str(cmd) if cmd.exists() else None


def _agent_browser_browser_cache_dirs(runtime_dir: Path) -> List[Path]:
    return [
        runtime_dir / "node_modules" / "playwright-core" / ".local-browsers",
        runtime_dir / "node_modules" / "agent-browser" / "node_modules" / "playwright-core" / ".local-browsers",
    ]


def _has_agent_browser_native_bundle(runtime_dir: Optional[Path]) -> bool:
    if runtime_dir is None:
        return False
    bin_dir = runtime_dir / "node_modules" / "agent-browser" / "bin"
    if not bin_dir.exists():
        return False
    for candidate in bin_dir.iterdir():
        if candidate.is_file() and candidate.name.startswith("agent-browser-") and candidate.name != "agent-browser.js":
            return True
    return False


def _has_agent_browser_browser_cache(runtime_dir: Optional[Path]) -> bool:
    if runtime_dir is None:
        return False
    if _has_agent_browser_native_bundle(runtime_dir):
        return True
    for candidate in _agent_browser_browser_cache_dirs(runtime_dir):
        if candidate.exists():
            try:
                if any(candidate.iterdir()):
                    return True
            except Exception:
                return True
    return False


def _remove_agent_browser_browser_cache(runtime_dir: Optional[Path]) -> int:
    if runtime_dir is None:
        return 0
    removed = 0
    for candidate in _agent_browser_browser_cache_dirs(runtime_dir):
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1
    return removed


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


def _ensure_mcporter_storage() -> None:
    if MCPORTER_CONFIG_PATH.exists():
        MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
        return

    if LEGACY_MCPORTER_DIR.exists() and not MCPORTER_DIR.exists():
        MCPORTER_DIR.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(LEGACY_MCPORTER_DIR), str(MCPORTER_DIR))
            return
        except Exception:
            pass

    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_MCPORTER_CONFIG_PATH.exists() and not MCPORTER_CONFIG_PATH.exists():
        try:
            MCPORTER_CONFIG_PATH.write_text(
                LEGACY_MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        except Exception:
            pass


def _install_agent_browser() -> None:
    from agentserver.openclaw.embedded_runtime import get_embedded_runtime

    runtime = get_embedded_runtime()
    runtime_dir = _resolve_packaged_openclaw_runtime_dir()
    prebundled_cmd = _resolve_prebundled_agent_browser_cmd()
    if prebundled_cmd and _has_agent_browser_browser_cache(runtime_dir):
        if _has_agent_browser_native_bundle(runtime_dir):
            removed = _remove_agent_browser_browser_cache(runtime_dir)
            if removed > 0:
                logger.info(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        logger.info(f"检测到预装 agent-browser 与浏览器缓存，跳过在线安装: {prebundled_cmd}")
        return

    if getattr(sys, "frozen", False) and runtime_dir is None:
        raise RuntimeError("打包环境缺少内置 openclaw runtime，无法安装 agent-browser")

    install_root = runtime_dir or runtime.vendor_root
    npm_cmd = runtime.npm_path
    if npm_cmd is None:
        raise RuntimeError("未检测到内置/项目 npm，无法安装 agent-browser")

    env = runtime.env
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["CI"] = "1"

    logger.info(f"安装 agent-browser 到本地运行时目录: {install_root}")
    code, stdout, stderr = _run_command(
        [
            npm_cmd,
            "install",
            "agent-browser",
            "--global=false",
            "--location=project",
            "--prefix",
            str(install_root),
        ],
        timeout=3000,
        cwd=str(install_root),
        env=env,
    )
    if code != 0:
        raise RuntimeError(stderr or stdout or "npm install agent-browser 失败")

    if _has_agent_browser_native_bundle(install_root):
        removed = _remove_agent_browser_browser_cache(install_root)
        if removed > 0:
            logger.info(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        logger.info("agent-browser 当前版本自带原生浏览器二进制，跳过 playwright 安装")
        return

    logger.info("正在 playwright install chromium（下载浏览器，可能需要数分钟）...")
    code, stdout, stderr = _run_command(
        [npm_cmd, "exec", "--prefix", str(install_root), "playwright", "install", "chromium"],
        timeout=3000,
        cwd=str(install_root),
        env=env,
    )
    if code != 0:
        raise RuntimeError(stderr or stdout or "playwright install chromium 失败")
    prebundled_cmd = _resolve_prebundled_agent_browser_cmd()
    if prebundled_cmd is None and not (install_root / "node_modules" / ".bin" / _agent_browser_bin_name()).exists():
        raise RuntimeError("agent-browser 安装完成后仍未找到命令入口")
    logger.info("agent-browser 安装完成")


def _build_market_item(item: Dict[str, Any]) -> Dict[str, Any]:
    skill_name = str(item.get("skill_name") or item.get("id") or "unknown")
    skill_path = OPENCLAW_SKILLS_DIR / skill_name / "SKILL.md"
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "description": item.get("description"),
        "skill_name": skill_name,
        "enabled": item.get("enabled", True),
        "installed": skill_path.exists(),
        "skill_path": str(skill_path),
        "install_type": item.get("install", {}).get("type"),
    }


def _get_market_items_status() -> Dict[str, Any]:
    return {
        "openclaw": {
            "skills_dir": str(OPENCLAW_SKILLS_DIR),
            "config_path": str(OPENCLAW_CONFIG_PATH),
        },
        "items": [_build_market_item(item) for item in MARKET_ITEMS],
    }


# ============ OpenClaw 技能市场端点 ============


def _telemetry_config_keys(config: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(config, dict):
        return []
    keys = [str(key)[:80] for key in config.keys() if not str(key).startswith("_")]
    return sorted(keys)[:32]


def _emit_extensions_telemetry(
    event: str,
    props: Dict[str, Any],
    *,
    agent_id: Optional[str] = None,
) -> None:
    emit_telemetry(
        event,
        props,
        source="apiserver",
        agent_id=agent_id,
    )


@router.get("/openclaw/market/items")
def list_openclaw_market_items():
    """获取OpenClaw技能市场条目（同步端点，由 FastAPI 在线程池中执行）"""
    try:
        status = _get_market_items_status()
        return {"status": "success", **status}
    except Exception as e:
        logger.error(f"获取技能市场失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取技能市场失败: {str(e)}")


@router.post("/openclaw/market/items/{item_id}/install")
def install_openclaw_market_item(item_id: str, payload: Optional[Dict[str, Any]] = None):
    """安装指定OpenClaw技能市场条目（同步端点，由 FastAPI 在线程池中执行）"""
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
    telemetry_props = {
        "item_id": item_id,
        "skill_name": skill_name,
        "install_type": install_type,
        "has_payload": bool(payload),
    }

    try:
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

        if item_id == "agent-browser":
            _install_agent_browser()
        if item_id == "search":
            api_key = None
            if payload and isinstance(payload, dict):
                api_key = payload.get("api_key") or payload.get("FIRECRAWL_API_KEY")
            _update_mcporter_firecrawl_config(api_key)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "market_item_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
        )
        raise
    except Exception as e:
        _emit_extensions_telemetry(
            "market_item_install_fail",
            {
                **telemetry_props,
                "error": e,
            },
        )
        logger.error(f"安装技能失败({item_id}): {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")

    status = _get_market_items_status()
    installed_item = next((entry for entry in status.get("items", []) if entry.get("id") == item_id), None)
    _emit_extensions_telemetry(
        "market_item_install_success",
        {
            **telemetry_props,
            "installed": bool(installed_item and installed_item.get("installed")),
        },
    )
    return {
        "status": "success",
        "message": "安装完成",
        "item": installed_item,
        "openclaw": status.get("openclaw"),
    }


# ============ OpenClaw 任务状态查询 ============


@router.get("/openclaw/tasks")
async def api_openclaw_list_tasks():
    """列出本地缓存的 OpenClaw 任务（来自 agentserver）。

    agentserver 尚未启动或仍在预热时返回空列表，避免前端启动期持续 503。
    """
    try:
        return await _call_agentserver("GET", "/openclaw/tasks")
    except HTTPException as e:
        if e.status_code == 503:
            return {"status": "warming_up", "tasks": []}
        raise


@router.get("/openclaw/tasks/{task_id}")
async def api_openclaw_get_task(
    task_id: str,
    include_history: bool = False,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取 OpenClaw 任务状态（支持查看中间过程）"""
    return await _call_agentserver(
        "GET",
        f"/openclaw/tasks/{task_id}/detail",
        params={
            "include_history": str(include_history).lower(),
            "history_limit": history_limit,
            "include_tools": str(include_tools).lower(),
        },
    )


# ============ MCP 服务列表 & 导入 ============


def _load_mcporter_config() -> Dict[str, Any]:
    """读取 ~/.naga/mcporter/config.json，不存在或格式错误时返回空 dict。"""
    _ensure_mcporter_storage()
    if not MCPORTER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _normalize_mcp_scope(scope: Optional[str], *, strict: bool = False) -> str:
    value = (scope or "public").strip().lower()
    if value not in {"public", "private"}:
        if strict:
            raise HTTPException(status_code=400, detail=f"未知 MCP 范围: {scope}")
        return "public"
    return value


def _resolve_agent_name(agent_id: Optional[str]) -> Optional[str]:
    if not agent_id:
        return None
    agent = _get_agent_record(agent_id)
    return str(agent.get("name") or agent_id) if agent else None


def _attach_mcp_meta(
    config: Dict[str, Any],
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    scope: str = "public",
    agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    data = {k: v for k, v in config.items() if not str(k).startswith("_")}
    data["_scope"] = scope
    if display_name:
        data["_displayName"] = display_name
    if description:
        data["_description"] = description
    if scope == "private" and agent_id:
        data["_ownerAgentId"] = agent_id
    else:
        data.pop("_ownerAgentId", None)
    return data


def _list_public_enabled_external_mcp_names() -> List[str]:
    names: List[str] = []
    for name, cfg in _load_mcporter_config().get("mcpServers", {}).items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("_disabled", False):
            continue
        if _normalize_mcp_scope(cfg.get("_scope")) == "public":
            names.append(name)
    return names


def _refresh_mcp_runtime_state(preheat_service_names: Optional[List[str]] = None) -> None:
    try:
        from mcpserver.mcporter_bridge import invalidate_mcporter_cache, preheat_external_mcp_services
        from mcpserver.mcp_registry import auto_register_mcp, clear_registry

        invalidate_mcporter_cache()
        clear_registry()
        auto_register_mcp()
        if preheat_service_names:
            preheat_external_mcp_services(preheat_service_names)
    except Exception as exc:
        logger.warning("MCP runtime refresh failed: %s", exc)

    try:
        from apiserver.tool_schemas import invalidate_schema_cache

        invalidate_schema_cache()
    except Exception as exc:
        logger.warning("MCP schema cache refresh failed: %s", exc)

    try:
        from apiserver.intent_router import invalidate_tool_list_cache

        invalidate_tool_list_cache()
    except Exception as exc:
        logger.warning("MCP intent cache refresh failed: %s", exc)


def _check_agent_available(manifest: Dict[str, Any]) -> bool:
    """检查内置 agent 模块是否可导入"""
    entry = manifest.get("entryPoint", {})
    module_path = entry.get("module", "")
    if not module_path:
        return False
    try:
        __import__(module_path)
        return True
    except Exception as e:
        logger.warning(f"MCP 模块导入失败 {module_path}: {e}")
        return False


@router.get("/mcp/status")
async def get_mcp_status_offline():
    """MCP Server 未启动时返回离线状态，避免前端 503"""
    return {
        "server": "offline",
        "timestamp": datetime.now().isoformat(),
        "tasks": {"total": 0, "active": 0, "completed": 0, "failed": 0},
    }


@router.get("/mcp/tasks")
async def get_mcp_tasks_offline(status: Optional[str] = None):
    """MCP Server 未启动时返回空任务列表，避免前端 503"""
    return {"tasks": [], "total": 0}


@router.get("/mcp/services")
def get_mcp_services(agent_id: Optional[str] = None):
    """列出所有 MCP 服务并检查可用性（同步端点，由 FastAPI 在线程池中执行）"""
    services: List[Dict[str, Any]] = []

    # 1. 内置 agent（扫描 mcpserver 下所有 agent-manifest.json，与 mcp_registry 一致）
    mcpserver_dir = Path(__file__).resolve().parent.parent.parent / "mcpserver"
    if not mcpserver_dir.exists():
        logger.warning(f"MCP 目录不存在: {mcpserver_dir}")
    for manifest_path in sorted(mcpserver_dir.glob("**/agent-manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if manifest.get("agentType") != "mcp":
            continue
        available = _check_agent_available(manifest)
        services.append({
            "name": manifest.get("name", manifest_path.parent.name),
            "display_name": manifest.get("displayName", manifest.get("name", "")),
            "description": manifest.get("description", ""),
            "source": "builtin",
            "scope": "public",
            "owner_agent_id": None,
            "owner_agent_name": None,
            "available": available,
            "enabled": True,
        })

    # 2. mcporter 外部配置（~/.mcporter/config.json 中的 mcpServers）
    mcporter_config = _load_mcporter_config()
    # 打包模式下用内置运行时解析 npx/uvx 等命令
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime
        _runtime = get_embedded_runtime()
    except Exception:
        _runtime = None
    for name, cfg in mcporter_config.get("mcpServers", {}).items():
        if agent_id and _normalize_mcp_scope(cfg.get("_scope")) == "private" and cfg.get("_ownerAgentId") != agent_id:
            continue
        cmd = cfg.get("command", "")
        if cmd and _runtime:
            available = _runtime.resolve_command(cmd) is not None
        else:
            available = shutil.which(cmd) is not None if cmd else False
        # 提取 meta 字段（以 _ 开头的不属于 MCP 协议本身）
        display_name = cfg.get("_displayName", name)
        description = cfg.get("_description", "")
        disabled = cfg.get("_disabled", False)
        scope = _normalize_mcp_scope(cfg.get("_scope"))
        owner_agent_id = str(cfg.get("_ownerAgentId") or "").strip() or None
        if not description and cmd:
            description = f"{cmd} {' '.join(cfg.get('args', []))}"
        # 构建干净的 config（去掉 _ 开头的 meta 字段）
        clean_config = {k: v for k, v in cfg.items() if not k.startswith("_")}
        services.append({
            "name": name,
            "display_name": display_name,
            "description": description,
            "source": "mcporter",
            "scope": scope,
            "owner_agent_id": owner_agent_id,
            "owner_agent_name": _resolve_agent_name(owner_agent_id),
            "available": available,
            "enabled": not disabled,
            "config": clean_config,
        })

    return JSONResponse(
        content={"status": "success", "services": services},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


class McpImportRequest(BaseModel):
    name: str
    config: Dict[str, Any]
    display_name: Optional[str] = None
    description: Optional[str] = None
    scope: str = "public"
    agent_id: Optional[str] = None


@router.post("/mcp/import")
async def import_mcp_config(request: McpImportRequest):
    """将 MCP JSON 配置写入 ~/.naga/mcporter/config.json"""
    telemetry_props = {
        "name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "config_keys": _telemetry_config_keys(request.config),
        "has_display_name": bool((request.display_name or "").strip()),
        "has_description": bool((request.description or "").strip()),
    }
    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.setdefault("mcpServers", {})
        scope = _normalize_mcp_scope(request.scope, strict=True)
        agent_id = (request.agent_id or "").strip() or None
        if scope == "private":
            if not agent_id:
                raise HTTPException(status_code=400, detail="私有 MCP 必须指定 agent_id")
            if not _get_agent_record(agent_id):
                raise HTTPException(status_code=404, detail="目标干员不存在")
        telemetry_props["scope"] = scope
        telemetry_props["agent_id"] = agent_id
        servers[request.name] = _attach_mcp_meta(
            request.config,
            display_name=request.display_name,
            description=request.description,
            scope=scope,
            agent_id=agent_id,
        )
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "mcp_import_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "mcp_import_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("mcp_import_success", telemetry_props, agent_id=agent_id)
    return {"status": "success", "message": f"已添加 MCP 服务: {request.name}"}


@router.put("/mcp/services/{name}")
async def update_mcp_service(name: str, body: Dict[str, Any]):
    """更新 MCP 服务配置（支持 config / displayName / description / enabled）"""
    telemetry_props = {
        "name": name,
        "changed_fields": sorted(
            field for field in ("config", "displayName", "description", "enabled") if field in body
        ),
        "config_keys": _telemetry_config_keys(body.get("config")),
    }
    try:
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.get("mcpServers", {})
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"MCP 服务 {name} 不存在")
        existing = servers[name]
        telemetry_props["scope"] = _normalize_mcp_scope(existing.get("_scope"))
        telemetry_props["agent_id"] = str(existing.get("_ownerAgentId") or "").strip() or None
        if "config" in body:
            # 替换整个配置（但保留 meta 字段）
            meta_keys = {"_displayName", "_description", "_disabled", "_scope", "_ownerAgentId"}
            old_meta = {k: v for k, v in existing.items() if k in meta_keys}
            servers[name] = {**body["config"], **old_meta}
            existing = servers[name]
        if "displayName" in body:
            existing["_displayName"] = body["displayName"]
        if "description" in body:
            existing["_description"] = body["description"]
        if "enabled" in body:
            if body["enabled"]:
                existing.pop("_disabled", None)
            else:
                existing["_disabled"] = True
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "mcp_service_update_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "mcp_service_update_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    _emit_extensions_telemetry("mcp_service_update", telemetry_props, agent_id=telemetry_props.get("agent_id"))
    return {"status": "success", "message": f"已更新 MCP 服务: {name}"}


@router.delete("/mcp/services/{name}")
async def delete_mcp_service(name: str):
    """删除外部 MCP 服务配置"""
    telemetry_props = {"name": name}
    try:
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.get("mcpServers", {})
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"MCP 服务 {name} 不存在")
        existing = servers[name]
        telemetry_props["scope"] = _normalize_mcp_scope(existing.get("_scope"))
        telemetry_props["agent_id"] = str(existing.get("_ownerAgentId") or "").strip() or None
        telemetry_props["enabled"] = not bool(existing.get("_disabled", False))
        del servers[name]
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "mcp_service_delete_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "mcp_service_delete_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    _emit_extensions_telemetry("mcp_service_delete", telemetry_props, agent_id=telemetry_props.get("agent_id"))
    return {"status": "success", "message": f"已删除 MCP 服务: {name}"}


# ============ 技能导入 ============


class SkillImportRequest(BaseModel):
    name: str
    content: str
    scope: Optional[str] = None
    agent_id: Optional[str] = None


class SkillCloneRequest(BaseModel):
    name: str
    source_scope: str
    target_scope: str = "private"
    source_agent_id: Optional[str] = None
    target_agent_id: Optional[str] = None


class HubInstallRequest(BaseModel):
    name: str
    scope: str = "public"
    agent_id: Optional[str] = None
    source: str = "tencent-skillhub"

def _hub_base_url(source: str = "tencent-skillhub") -> str:
    normalized = (source or "tencent-skillhub").strip().lower()
    if normalized == "tencent-skillhub":
        return "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com"
    if normalized == "clawhub":
        return "https://clawhub.ai"
    if normalized == "mcp.so":
        return "https://mcp.so"
    raise HTTPException(status_code=400, detail=f"未知下载源: {source}")


def _build_hub_url(kind: str, name: str, source: str = "tencent-skillhub") -> str:
    base_url = _hub_base_url(source)
    if (source or "").strip().lower() == "tencent-skillhub":
        return f"{base_url}/{kind}/{name}"
    return f"{base_url}/api/hub/{kind}/{name}"


def _resolve_skillhub_cli() -> Optional[str]:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        project_runtime_root = runtime._get_project_runtime_root()
        candidates = [
            Path(runtime.runtime_root) / "skillhub" / "skills_store_cli.py" if runtime.runtime_root else None,
            project_runtime_root / "skillhub" / "skills_store_cli.py",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)
    except Exception:
        pass
    return None


def _resolve_skillhub_python() -> Optional[str]:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        return runtime.python_path
    except Exception:
        return None


def _resolve_clawhub_runtime() -> tuple[Optional[str], Optional[str]]:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        return runtime.node_path, runtime.npx_path
    except Exception:
        return None, None


def _normalize_mcpso_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").strip().lower())


def _resolve_mcpso_url(name_or_url: str) -> tuple[str, bool]:
    raw = (name_or_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请输入 MCP 名称或完整链接")
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw, True
    normalized_name = _normalize_mcpso_name(raw)
    return f"https://mcp.so/server/{normalized_name}/modelcontextprotocol", False


def _extract_json_code_blocks_from_html(page_html: str) -> List[str]:
    blocks = re.findall(r"```json\s*(.*?)\s*```", page_html, flags=re.S | re.I)
    normalized_blocks: List[str] = []
    for block in blocks:
        text = html.unescape(block)
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        stripped = text.strip()
        if stripped:
            normalized_blocks.append(stripped)
    return normalized_blocks


def _strip_json_line_comments(raw_text: str) -> str:
    result: List[str] = []
    in_string = False
    escaped = False
    i = 0
    length = len(raw_text)
    while i < length:
        ch = raw_text[i]
        nxt = raw_text[i + 1] if i + 1 < length else ""
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < length and raw_text[i] not in "\r\n":
                i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _parse_mcp_install_payload(block_text: str, fallback_name: str) -> tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    try:
        payload = json.loads(_strip_json_line_comments(block_text))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"获取到的 MCP 配置不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="获取到的 MCP 配置不是 JSON 对象")

    if isinstance(payload.get("mcpServers"), dict) and payload["mcpServers"]:
        mcp_name, config = next(iter(payload["mcpServers"].items()))
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="mcpServers 下的配置格式无效")
        return str(mcp_name), None, None, config

    mcp_section = payload.get("mcp")
    if isinstance(mcp_section, dict) and isinstance(mcp_section.get("servers"), dict) and mcp_section["servers"]:
        mcp_name, config = next(iter(mcp_section["servers"].items()))
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="mcp.servers 下的配置格式无效")
        return str(mcp_name), None, None, config

    if "command" in payload or "type" in payload or "url" in payload:
        return fallback_name, None, None, payload

    raise HTTPException(status_code=502, detail="未在 mcp.so 页面中找到可安装的 MCP 配置")


def _install_mcp_via_mcpso(name_or_url: str) -> tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    target_url, provided_full_url = _resolve_mcpso_url(name_or_url)
    req = UrlRequest(target_url, headers={"User-Agent": "NagaAgent/mcpso-installer"})
    try:
        with urlopen(req, timeout=20) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")
    except HTTPException:
        raise
    except Exception as exc:
        if provided_full_url:
            raise HTTPException(status_code=502, detail="获取mcp内容失败") from exc
        raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接") from exc

    blocks = _extract_json_code_blocks_from_html(page_html)
    if not blocks:
        if provided_full_url:
            raise HTTPException(status_code=502, detail="获取mcp内容失败")
        raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接")

    fallback_name = _normalize_mcpso_name(name_or_url)
    if provided_full_url:
        matched = re.search(r"/server/([^/]+)/", target_url)
        if matched:
            fallback_name = _normalize_mcpso_name(matched.group(1)) or fallback_name
    for block in reversed(blocks):
        try:
            return _parse_mcp_install_payload(block, fallback_name)
        except HTTPException:
            continue

    if provided_full_url:
        raise HTTPException(status_code=502, detail="获取mcp内容失败")
    raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接")


def _install_skill_via_tencent_skillhub(name: str) -> tuple[str, str]:
    cli = _resolve_skillhub_cli()
    python_bin = _resolve_skillhub_python()
    if not cli or not python_bin:
        raise HTTPException(
            status_code=503,
            detail="未找到内置腾讯 SkillHub CLI 或 Python 运行时，无法执行下载。",
        )
    with tempfile.TemporaryDirectory(prefix="naga-skillhub-") as tmp:
        install_dir = Path(tmp)
        try:
            subprocess.run(
                [python_bin, cli, "--dir", str(install_dir), "install", name, "--force"],
                check=True,
                cwd=str(install_dir),
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise HTTPException(status_code=502, detail=f"腾讯 SkillHub 安装失败: {stderr or exc}") from exc

        direct_path = install_dir / name / "SKILL.md"
        if direct_path.exists():
            return name, direct_path.read_text(encoding="utf-8")

        fallback_path = next(install_dir.rglob("SKILL.md"), None)
        if fallback_path is None:
            raise HTTPException(status_code=502, detail="腾讯 SkillHub 安装完成，但未找到 SKILL.md")

        resolved_name = fallback_path.parent.name or name
        return resolved_name, fallback_path.read_text(encoding="utf-8")


def _install_skill_via_clawhub(name: str) -> tuple[str, str]:
    node_bin, npx_bin = _resolve_clawhub_runtime()
    if not node_bin or not npx_bin:
        raise HTTPException(
            status_code=503,
            detail="未找到内置 Node runtime 或 npx，无法执行 ClawHub 下载。",
        )

    with tempfile.TemporaryDirectory(prefix="naga-clawhub-") as tmp:
        workdir = Path(tmp)
        try:
            subprocess.run(
                [
                    node_bin,
                    npx_bin,
                    "--yes",
                    "clawhub@latest",
                    "--no-input",
                    "--workdir",
                    str(workdir),
                    "--dir",
                    "skills",
                    "install",
                    name,
                    "--force",
                ],
                check=True,
                cwd=str(workdir),
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise HTTPException(status_code=502, detail=f"ClawHub 安装失败: {stderr or exc}") from exc

        direct_path = workdir / "skills" / name / "SKILL.md"
        if direct_path.exists():
            return name, direct_path.read_text(encoding="utf-8")

        fallback_path = next(workdir.rglob("SKILL.md"), None)
        if fallback_path is None:
            raise HTTPException(status_code=502, detail="ClawHub 安装完成，但未找到 SKILL.md")

        resolved_name = fallback_path.parent.name or name
        return resolved_name, fallback_path.read_text(encoding="utf-8")


def _render_skill_file_content(name: str, content: str) -> str:
    raw = (content or "").strip()
    if SKILL_FRONTMATTER_PATTERN.match(raw):
        return raw + ("\n" if not raw.endswith("\n") else "")
    return f"""---
name: {name}
description: 用户自定义技能
version: 1.0.0
author: User
tags:
  - custom
enabled: true
---

{raw}
"""


def _write_skill_to_scope(name: str, content: str, scope: str, agent_id: Optional[str] = None) -> Path:
    name = _normalize_skill_name(name)
    rendered_content = _render_skill_file_content(name, content)

    if scope == "openclaw-local":
        return _write_skill_file(name, rendered_content)
    if scope == "cache":
        return _write_skill_file_to_dir(NAGA_CACHE_SKILLS_DIR, name, rendered_content)
    if scope == "public":
        path = _write_skill_file_to_dir(NAGA_PUBLIC_SKILLS_DIR, name, rendered_content)
        try:
            from system.skill_manager import get_skill_manager

            get_skill_manager().refresh()
        except Exception:
            pass
        return path
    if scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 agent_id")
        agent = _get_agent_record(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="目标干员不存在")
        agent_skill_dir = _resolve_agent_skills_dir(agent_id)
        return _write_skill_file_to_dir(agent_skill_dir, name, rendered_content)

    raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")


def _delete_skill_from_scope(name: str, scope: str, agent_id: Optional[str] = None) -> Path:
    name = _normalize_skill_name(name)
    if scope == "cache":
        candidates = [_resolve_skill_dir(NAGA_CACHE_SKILLS_DIR, name), _resolve_skill_dir(OPENCLAW_SKILLS_DIR, name)]
    elif scope == "public":
        candidates = [_resolve_skill_dir(NAGA_PUBLIC_SKILLS_DIR, name)]
    elif scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 agent_id")
        candidates = [_resolve_skill_dir(_resolve_agent_skills_dir(agent_id), name)]
    else:
        raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")

    for path in candidates:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            if scope == "public":
                try:
                    from system.skill_manager import get_skill_manager

                    get_skill_manager().refresh()
                except Exception:
                    pass
            return path
    raise HTTPException(status_code=404, detail=f"技能不存在: {name}")


def _read_skill_content_from_scope(name: str, scope: str, agent_id: Optional[str] = None) -> str:
    name = _normalize_skill_name(name)
    candidates: List[Path]
    if scope == "cache":
        candidates = [
            _resolve_skill_dir(NAGA_CACHE_SKILLS_DIR, name) / "SKILL.md",
            _resolve_skill_dir(OPENCLAW_SKILLS_DIR, name) / "SKILL.md",
        ]
    elif scope == "public":
        candidates = [_resolve_skill_dir(NAGA_PUBLIC_SKILLS_DIR, name) / "SKILL.md"]
    elif scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 source_agent_id")
        candidates = [_resolve_skill_dir(_resolve_agent_skills_dir(agent_id), name) / "SKILL.md"]
    else:
        raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")

    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail=f"技能不存在: {name}")


def _fetch_hub_payload(kind: str, name: str, source: str = "tencent-skillhub") -> tuple[str, Any]:
    url = _build_hub_url(kind, name, source)
    headers = {"User-Agent": "NagaAgent/hub-installer"}
    if naga_auth.is_authenticated():
        token = naga_auth.get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    try:
        request = UrlRequest(url, headers=headers)
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
        text = body.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NagaHub 不可达: {exc}")

    if "json" in content_type.lower():
        try:
            return content_type, json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"NagaHub 返回了无效 JSON: {exc}")
    return content_type, text


def _parse_hub_skill_payload(name: str, payload: Any) -> tuple[str, str]:
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("skill") or payload.get("template") or payload.get("markdown")
        resolved_name = str(payload.get("name") or name).strip() or name
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="NagaHub skill 模板缺少 content")
        return resolved_name, content
    if isinstance(payload, str) and payload.strip():
        return name, payload
    raise HTTPException(status_code=502, detail="NagaHub skill 模板为空")


def _parse_hub_mcp_payload(name: str, payload: Any) -> tuple[str, Optional[str], Optional[str], Dict[str, Any]]:
    if isinstance(payload, dict):
        resolved_name = str(payload.get("name") or name).strip() or name
        display_name = payload.get("display_name") or payload.get("displayName")
        description = payload.get("description")
        config = payload.get("config") if isinstance(payload.get("config"), dict) else payload
        clean_config = {k: v for k, v in config.items() if not str(k).startswith("_")} if isinstance(config, dict) else None
        if not clean_config:
            raise HTTPException(status_code=502, detail="NagaHub MCP 模板缺少 config")
        return resolved_name, display_name, description, clean_config
    if isinstance(payload, str) and payload.strip():
        try:
            config = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"NagaHub MCP 模板不是合法 JSON: {exc}")
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="NagaHub MCP 模板必须返回 JSON 对象")
        return name, None, None, config
    raise HTTPException(status_code=502, detail="NagaHub MCP 模板为空")


def _normalize_memory_quintuple_item(item: Any) -> Optional[Dict[str, str]]:
    if isinstance(item, dict):
        if isinstance(item.get("quintuple"), (list, tuple)) and len(item["quintuple"]) >= 5:
            q = item["quintuple"]
            return {
                "subject": str(q[0] or ""),
                "subject_type": str(q[1] or ""),
                "predicate": str(q[2] or ""),
                "object": str(q[3] or ""),
                "object_type": str(q[4] or ""),
            }
        return {
            "subject": str(item.get("subject") or ""),
            "subject_type": str(item.get("subject_type") or item.get("subjectType") or ""),
            "predicate": str(item.get("predicate") or item.get("relation") or ""),
            "object": str(item.get("object") or ""),
            "object_type": str(item.get("object_type") or item.get("objectType") or ""),
        }
    if isinstance(item, (list, tuple)) and len(item) >= 5:
        return {
            "subject": str(item[0] or ""),
            "subject_type": str(item[1] or ""),
            "predicate": str(item[2] or ""),
            "object": str(item[3] or ""),
            "object_type": str(item[4] or ""),
        }
    return None


def _build_skill_catalog() -> Dict[str, Any]:
    public_skills = _list_skill_dir(
        NAGA_PUBLIC_SKILLS_DIR,
        scope="public",
        source="naga-public",
    )
    cache_skills = _list_skill_dir(
        NAGA_CACHE_SKILLS_DIR,
        scope="cache",
        source="naga-cache",
    ) + _list_skill_dir(
        OPENCLAW_SKILLS_DIR,
        scope="cache",
        source="openclaw-local",
    )

    private_skills: List[Dict[str, Any]] = []
    for agent in _load_agents_manifest():
        agent_id = agent.get("id")
        if not agent_id:
            continue
        try:
            agent_dir = _resolve_agent_skills_dir(str(agent_id))
        except HTTPException:
            continue
        private_skills.extend(
            _list_skill_dir(
                agent_dir,
                scope="private",
                source="agent-private",
                owner=agent,
            ),
        )

    return {
        "remote_hub": {
            "status": "configured",
            "base_url": _hub_base_url("tencent-skillhub"),
            "skill_endpoint_template": f"{_hub_base_url('tencent-skillhub')}/skill/{{skill_name}}",
            "mcp_endpoint_template": "https://mcp.so/server/{mcp_name}/modelcontextprotocol",
            "message": "当前 Skill 下载支持腾讯 SkillHub 与 ClawHub；MCP 下载当前使用 mcp.so 页面抓取。",
        },
        "local_cache": {
            "skills": cache_skills,
            "base_dirs": [str(NAGA_CACHE_SKILLS_DIR), str(OPENCLAW_SKILLS_DIR)],
        },
        "public_skills": {
            "skills": public_skills,
            "base_dir": str(NAGA_PUBLIC_SKILLS_DIR),
        },
        "private_skills": {
            "skills": private_skills,
            "base_dir": str(NAGA_AGENTS_DIR),
        },
    }


@router.get("/skills/catalog")
async def list_skill_catalog():
    return {
        "status": "success",
        "catalog": _build_skill_catalog(),
    }


@router.post("/skills/import")
async def import_custom_skill(request: SkillImportRequest):
    """创建自定义技能 SKILL.md"""
    scope = (request.scope or "openclaw-local").strip().lower()
    if scope == "legacy":
        scope = "openclaw-local"
    telemetry_props = {
        "name": request.name,
        "scope": scope,
        "agent_id": request.agent_id,
        "content_chars": len(request.content or ""),
        "has_frontmatter": bool(SKILL_FRONTMATTER_PATTERN.match((request.content or "").strip())),
    }
    try:
        skill_path = _write_skill_to_scope(request.name, request.content, scope, request.agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "skill_import_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "skill_import_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("skill_import_success", telemetry_props, agent_id=(request.agent_id or "").strip() or None)

    return {
        "status": "success",
        "message": f"技能已创建: {skill_path}",
        "scope": scope,
        "path": str(skill_path),
    }


@router.post("/skills/clone")
async def clone_skill(request: SkillCloneRequest):
    source_scope = (request.source_scope or "").strip().lower()
    target_scope = (request.target_scope or "private").strip().lower()
    source_agent_id = (request.source_agent_id or "").strip() or None
    target_agent_id = (request.target_agent_id or "").strip() or None

    if source_scope == "legacy":
        source_scope = "cache"
    if target_scope == "legacy":
        target_scope = "private"

    content = _read_skill_content_from_scope(request.name, source_scope, source_agent_id)
    skill_path = _write_skill_to_scope(request.name, content, target_scope, target_agent_id)

    return {
        "status": "success",
        "message": f"技能已复制: {request.name}",
        "source_scope": source_scope,
        "target_scope": target_scope,
        "path": str(skill_path),
    }


@router.delete("/skills/{name}")
async def delete_skill(name: str, scope: str, agent_id: Optional[str] = None):
    scope = (scope or "").strip().lower()
    if scope == "legacy":
        scope = "cache"
    telemetry_props = {
        "name": name,
        "scope": scope,
        "agent_id": agent_id,
    }
    try:
        skill_path = _delete_skill_from_scope(name, scope, agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "skill_delete_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "skill_delete_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("skill_delete", telemetry_props, agent_id=(agent_id or "").strip() or None)
    return {
        "status": "success",
        "message": f"技能已删除: {skill_path}",
        "scope": scope,
        "path": str(skill_path),
    }


@router.post("/hub/skills/install")
async def install_skill_from_hub(request: HubInstallRequest):
    telemetry_props = {
        "requested_name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "source": "hub",
        "hub_source": request.source,
    }
    try:
        normalized_source = (request.source or "").strip().lower()
        if normalized_source == "tencent-skillhub":
            skill_name, content = _install_skill_via_tencent_skillhub(request.name)
        elif normalized_source == "clawhub":
            skill_name, content = _install_skill_via_clawhub(request.name)
        else:
            _, payload = _fetch_hub_payload("skill", request.name, request.source)
            skill_name, content = _parse_hub_skill_payload(request.name, payload)
        telemetry_props["resolved_name"] = skill_name
        skill_path = _write_skill_to_scope(skill_name, content, request.scope, request.agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "hub_skill_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "hub_skill_install_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("hub_skill_install_success", telemetry_props, agent_id=(request.agent_id or "").strip() or None)
    return {
        "status": "success",
        "message": f"已从 Hub 安装技能: {skill_name}",
        "scope": request.scope,
        "path": str(skill_path),
        "name": skill_name,
        "source": "hub",
    }


@router.post("/hub/mcp/install")
async def install_mcp_from_hub(request: HubInstallRequest):
    telemetry_props = {
        "requested_name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "source": "hub",
        "hub_source": request.source,
    }
    try:
        normalized_source = (request.source or "").strip().lower()
        if normalized_source == "mcp.so":
            mcp_name, display_name, description, config = _install_mcp_via_mcpso(request.name)
        elif normalized_source == "tencent-skillhub":
            raise HTTPException(status_code=400, detail="腾讯 SkillHub 当前只支持 Skill CLI 安装，暂不支持 MCP 模板下载")
        elif normalized_source == "clawhub":
            raise HTTPException(status_code=400, detail="ClawHub 当前只支持 Skill 下载，暂不支持 MCP 模板下载")
        else:
            _, payload = _fetch_hub_payload("mcp", request.name, request.source)
            mcp_name, display_name, description, config = _parse_hub_mcp_payload(request.name, payload)

        scope = _normalize_mcp_scope(request.scope, strict=True)
        agent_id = (request.agent_id or "").strip() or None
        if scope == "private":
            if not agent_id:
                raise HTTPException(status_code=400, detail="私有 MCP 必须指定 agent_id")
            if not _get_agent_record(agent_id):
                raise HTTPException(status_code=404, detail="目标干员不存在")

        telemetry_props.update(
            {
                "resolved_name": mcp_name,
                "scope": scope,
                "agent_id": agent_id,
                "config_keys": _telemetry_config_keys(config),
                "has_display_name": bool((display_name or "").strip()) if isinstance(display_name, str) else bool(display_name),
                "has_description": bool((description or "").strip()) if isinstance(description, str) else bool(description),
            }
        )

        MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.setdefault("mcpServers", {})
        servers[mcp_name] = _attach_mcp_meta(
            config,
            display_name=display_name,
            description=description,
            scope=scope,
            agent_id=agent_id,
        )
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "hub_mcp_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "hub_mcp_install_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("hub_mcp_install_success", telemetry_props, agent_id=agent_id)
    return {
        "status": "success",
        "message": f"已从 Hub 安装 MCP: {mcp_name}",
        "scope": scope,
        "name": mcp_name,
        "source": "hub",
    }


# ============ 文件上传 ============


@router.post("/upload/document", response_model=FileUploadResponse)
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


@router.post("/upload/parse")
async def upload_parse(file: UploadFile = File(...)):
    """上传并解析文档内容（支持 .docx / .xlsx / .txt）"""
    import tempfile
    filename = file.filename or "unknown"
    suffix = Path(filename).suffix.lower()

    if suffix not in (".docx", ".xlsx", ".txt", ".csv", ".md"):
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {suffix}，支持 .docx / .xlsx / .txt / .csv / .md")

    # 写入临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        if suffix == ".docx":
            import importlib.util
            _docx_spec = importlib.util.spec_from_file_location(
                "docx_extract", Path(__file__).parent.parent / "skills_templates" / "office-docs" / "tools" / "docx_extract.py"
            )
            _docx_mod = importlib.util.module_from_spec(_docx_spec)
            _docx_spec.loader.exec_module(_docx_mod)
            lines = _docx_mod.extract_docx_text(tmp_path)
            content = "\n".join(lines)
        elif suffix == ".xlsx":
            import importlib.util
            import zipfile as _zf
            _xlsx_spec = importlib.util.spec_from_file_location(
                "xlsx_extract", Path(__file__).parent.parent / "skills_templates" / "office-docs" / "tools" / "xlsx_extract.py"
            )
            _xlsx_mod = importlib.util.module_from_spec(_xlsx_spec)
            _xlsx_spec.loader.exec_module(_xlsx_mod)
            with _zf.ZipFile(tmp_path, "r") as archive:
                shared_strings = _xlsx_mod._load_shared_strings(archive)
                sheets = _xlsx_mod._load_sheet_targets(archive)
                parts = []
                for name, path in sheets:
                    rows = _xlsx_mod._parse_sheet(archive, path, shared_strings, max_rows=500)
                    parts.append(f"## Sheet: {name}\n{_xlsx_mod._format_sheet_csv(rows, ',')}")
                content = "\n".join(parts)
        else:
            # txt / csv / md 直接读取
            content = tmp_path.read_text(encoding="utf-8", errors="replace")

        # 截断过长内容
        max_chars = 50000
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]

        return {
            "status": "success",
            "filename": filename,
            "content": content,
            "truncated": truncated,
            "char_count": len(content),
        }
    except Exception as e:
        logger.error(f"文档解析失败: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        tmp_path.unlink(missing_ok=True)


# ============ 旅行端点 ============


async def _create_travel_session_and_dispatch(payload: Dict[str, Any]) -> Dict[str, Any]:
    from apiserver.travel_service import create_session, get_open_session_for_agent, load_session, save_session, TravelStatus

    agent_id = payload.get("agent_id")
    if agent_id:
        agent = _get_agent_record(str(agent_id))
        if not agent:
            raise HTTPException(404, "指定的探索干员不存在")
        if agent.get("engine", "openclaw") != "openclaw":
            raise HTTPException(400, "网络探索目前仅支持 OpenClaw 干员执行")

    active_for_agent = get_open_session_for_agent(str(agent_id) if agent_id is not None else None)
    if active_for_agent:
        raise HTTPException(409, f"该干员已有进行中的探索: {active_for_agent.session_id}")

    session = create_session(
        agent_id=str(agent_id) if agent_id is not None else None,
        agent_name=str(agent.get("name") or "").strip() if agent_id is not None and agent else None,
        time_limit_minutes=payload.get("time_limit_minutes", 300),
        credit_limit=payload.get("credit_limit", 1000),
        want_friends=payload.get("want_friends", True),
        friend_description=payload.get("friend_description"),
        goal_prompt=payload.get("goal_prompt"),
        post_to_forum=payload.get("post_to_forum", True),
        deliver_full_report=payload.get("deliver_full_report", True),
        deliver_channel=payload.get("deliver_channel"),
        deliver_to=payload.get("deliver_to"),
        browser_visible=payload.get("browser_visible", False),
        browser_keep_open=payload.get("browser_keep_open", False),
        browser_idle_timeout_seconds=payload.get("browser_idle_timeout_seconds", 300),
    )
    emit_telemetry(
        "explore_start",
        {
            "time_limit_minutes": session.time_limit_minutes,
            "credit_limit": session.credit_limit,
            "want_friends": session.want_friends,
            "deliver_channel": session.deliver_channel,
            "deliver_full_report": session.deliver_full_report,
            "post_to_forum": session.post_to_forum,
            "goal_prompt_chars": len(session.goal_prompt or ""),
        },
        source="apiserver",
        session_id=session.session_id,
        agent_id=session.agent_id,
        trace_id=f"travel:{session.session_id}",
    )

    try:
        await _call_agentserver(
            "POST", "/travel/execute",
            json_body={"session_id": session.session_id},
            timeout_seconds=10.0,
        )
    except Exception as e:
        logger.warning(f"代理旅行到 agent server 失败（将本地标记失败）: {e}")
        s = load_session(session.session_id)
        s.status = TravelStatus.FAILED
        s.error = f"agent server 不可达: {e}"
        save_session(s)
        emit_telemetry(
            "explore_fail",
            {
                "stage": "dispatch",
                "error": e,
            },
            source="apiserver",
            session_id=session.session_id,
            agent_id=session.agent_id,
            trace_id=f"travel:{session.session_id}",
        )
        raise HTTPException(503, f"agent server 不可达: {e}")

    return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}


def _cancel_travel_session(session_id: str) -> Dict[str, Any]:
    from apiserver.travel_service import load_session, remove_session_browser_policy, save_session, TravelStatus

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    if session.status in {TravelStatus.COMPLETED, TravelStatus.FAILED, TravelStatus.CANCELLED}:
        return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}

    session.status = TravelStatus.CANCELLED
    session.completed_at = datetime.now().isoformat()
    save_session(session)
    remove_session_browser_policy(session.openclaw_session_key)
    emit_telemetry(
        "explore_cancel",
        {
            "elapsed_minutes": session.elapsed_minutes,
            "discoveries": len(session.discoveries),
        },
        source="apiserver",
        session_id=session.session_id,
        agent_id=session.agent_id,
        trace_id=f"travel:{session.session_id}",
    )
    return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}


@router.post("/travel/sessions")
async def create_travel_session(payload: Dict[str, Any]):
    return await _create_travel_session_and_dispatch(payload)


@router.get("/travel/sessions")
async def list_travel_sessions():
    from apiserver.travel_service import list_sessions

    sessions = list_sessions()
    return {"status": "success", "sessions": [s.model_dump() for s in sessions]}


@router.get("/travel/sessions/{session_id}")
async def get_travel_session(session_id: str):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")
    return {"status": "success", "session": session.model_dump()}


@router.get("/travel/sessions/{session_id}/report")
async def get_travel_session_report(session_id: str):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    report_path = (session.summary_report_path or "").strip()
    if not report_path:
        return {
            "status": "success",
            "exists": False,
            "path": None,
            "title": session.summary_report_title,
            "content": None,
            "missing_reason": "not_generated",
        }

    path = Path(report_path)
    if not path.exists():
        return {
            "status": "success",
            "exists": False,
            "path": report_path,
            "title": session.summary_report_title,
            "content": None,
            "missing_reason": "missing",
        }

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"读取探索成果文件失败: {e}")

    return {
        "status": "success",
        "exists": True,
        "path": report_path,
        "title": session.summary_report_title,
        "content": content,
    }


@router.get("/travel/sessions/{session_id}/history")
async def get_travel_session_history(session_id: str, limit: int = 0, include_tools: bool = True):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    session_key = (session.openclaw_session_key or "").strip()
    if not session_key:
        return {
            "status": "success",
            "session_id": session_id,
            "session_key": None,
            "messages": [],
        }

    history = await _call_agentserver(
        "GET",
        "/openclaw/history",
        params={
            "session_key": session_key,
            "limit": limit,
            "include_tools": str(include_tools).lower(),
        },
        timeout_seconds=20.0,
    )

    messages = []
    if isinstance(history, dict):
        raw_history = history.get("history")
        if isinstance(raw_history, dict):
            messages = raw_history.get("messages", []) or []

    return {
        "status": "success",
        "session_id": session_id,
        "session_key": session_key,
        "messages": messages,
    }


@router.post("/travel/sessions/{session_id}/stop")
async def stop_travel_session(session_id: str):
    return _cancel_travel_session(session_id)


@router.post("/travel/sessions/{session_id}/browser")
async def update_travel_browser_settings(session_id: str, payload: Dict[str, Any]):
    from apiserver.travel_service import append_progress_event, load_session, save_session, sync_session_browser_policy

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    visibility_changed = False
    if "browser_visible" in payload:
        next_visible = bool(payload.get("browser_visible"))
        visibility_changed = session.browser_visible != next_visible
        session.browser_visible = next_visible
    if "browser_keep_open" in payload:
        session.browser_keep_open = bool(payload.get("browser_keep_open"))
    if "browser_idle_timeout_seconds" in payload:
        session.browser_idle_timeout_seconds = max(30, int(payload.get("browser_idle_timeout_seconds") or 300))

    append_progress_event(
        session,
        "browser_settings_updated",
        "已更新探索浏览器策略。",
        meta={
            "browser_visible": session.browser_visible,
            "browser_keep_open": session.browser_keep_open,
            "browser_idle_timeout_seconds": session.browser_idle_timeout_seconds,
        },
    )
    save_session(session)
    sync_session_browser_policy(session)

    if visibility_changed and session.agent_id and session.status in {"pending", "running", "interrupted"}:
        try:
            await _call_agentserver(
                "POST",
                "/travel/browser-settings",
                json_body={
                    "session_id": session.session_id,
                    "browser_visible": session.browser_visible,
                },
                timeout_seconds=10.0,
            )
        except Exception as e:
            logger.warning(f"同步探索浏览器可见性到 agent_server 失败: {e}")

    return {"status": "success", "session": session.model_dump()}


@router.post("/travel/sessions/{session_id}/instruction")
async def send_travel_instruction(session_id: str, payload: Dict[str, Any]):
    from apiserver.travel_service import OPEN_TRAVEL_STATUSES, append_progress_event, load_session, save_session

    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message 不能为空")

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    if session.status not in OPEN_TRAVEL_STATUSES:
        raise HTTPException(409, "当前探索已结束，不能再追加指令")

    await _call_agentserver(
        "POST",
        "/travel/instruction",
        json_body={"session_id": session_id, "message": message},
        timeout_seconds=10.0,
    )
    append_progress_event(
        session,
        "instruction_requested",
        f"用户追加了探索指令：{message[:80]}",
        meta={"message": message[:400]},
    )
    save_session(session)
    return {"status": "success", "session": session.model_dump()}


@router.post("/travel/start")
async def travel_start(payload: Dict[str, Any]):
    """兼容旧接口。"""
    result = await _create_travel_session_and_dispatch(payload)
    return {"status": result["status"], "session_id": result["session_id"]}


@router.get("/travel/status")
async def travel_status():
    """兼容旧接口：返回任一活跃 session 或最近一条记录。"""
    from apiserver.travel_service import get_latest_session, list_active_sessions

    active = list_active_sessions()
    if active:
        return {"status": "success", "session": active[0].model_dump(), "active": True}

    latest = get_latest_session()
    if latest:
        return {"status": "success", "session": latest.model_dump(), "active": False}

    return {"status": "success", "session": None, "active": False}


@router.post("/travel/stop")
async def travel_stop(payload: Dict[str, Any] = None):
    """兼容旧接口：可选指定 session_id，否则停止最近活跃 session。"""
    from apiserver.travel_service import list_active_sessions

    session_id = (payload or {}).get("session_id")
    if not session_id:
        active = list_active_sessions()
        if not active:
            raise HTTPException(404, "没有进行中的旅行")
        session_id = active[0].session_id
    result = _cancel_travel_session(str(session_id))
    return {"status": result["status"], "session_id": result["session_id"]}


@router.get("/travel/history")
async def travel_history():
    """兼容旧接口。"""
    from apiserver.travel_service import list_sessions

    sessions = list_sessions()
    return {"status": "success", "sessions": [s.model_dump() for s in sessions]}


@router.get("/travel/history/{session_id}")
async def travel_history_detail(session_id: str):
    """兼容旧接口。"""
    return await get_travel_session(session_id)


# ============ 记忆 ============


@router.get("/memory/stats")
async def get_memory_stats():
    """获取记忆统计信息"""

    try:
        # 优先使用远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

        remote = get_remote_memory_client()
        if remote is not None:
            try:
                stats = await remote.get_stats()
                if stats.get("success") is not False:
                    return {"status": "success", "memory_stats": stats}
                logger.warning(f"远程记忆统计获取失败: {stats.get('error')}")
            except Exception as e:
                logger.warning(f"远程记忆统计异常: {e}")

        if should_prefer_remote_memory():
            return {
                "status": "success",
                "memory_stats": {"enabled": False, "message": "云端记忆服务暂不可用"},
            }

        # 回退到本地 summer_memory
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


@router.get("/memory/quintuples")
async def get_quintuples():
    """获取所有五元组 (用于知识图谱可视化)"""
    try:
        # 优先使用远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

        remote = get_remote_memory_client()
        remote_quintuples = []
        if remote is not None:
            try:
                result = await remote.get_quintuples(limit=500)
                if result.get("success") is not False:
                    quintuples_raw = result.get("quintuples") or result.get("results") or result.get("data") or []
                    for q in quintuples_raw:
                        normalized = _normalize_memory_quintuple_item(q)
                        if normalized:
                            remote_quintuples.append(normalized)
                else:
                    logger.warning(f"远程五元组获取失败: {result.get('error')}")
            except Exception as e:
                logger.warning(f"远程五元组获取异常: {e}")

        if should_prefer_remote_memory():
            return {
                "status": "success",
                "quintuples": remote_quintuples,
                "count": len(remote_quintuples),
                "message": "当前为云端记忆模式，未再回退本地知识图谱",
            }

        # 合并本地 summer_memory 数据（远程为空或失败时补充本地数据）
        local_quintuples = []
        try:
            from summer_memory.quintuple_graph import get_all_quintuples
            local_data = get_all_quintuples()  # returns set[tuple]
            local_quintuples = [
                {"subject": q[0], "subject_type": q[1], "predicate": q[2], "object": q[3], "object_type": q[4]}
                for q in local_data
            ]
        except ImportError:
            pass

        # 合并去重：以 (subject, predicate, object) 为唯一键
        seen = set()
        merged = []
        for q in remote_quintuples + local_quintuples:
            key = (q["subject"], q["predicate"], q["object"])
            if key not in seen:
                seen.add(key)
                merged.append(q)

        return {
            "status": "success",
            "quintuples": merged,
            "count": len(merged),
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "message": "记忆系统模块未找到"}
    except Exception as e:
        logger.error(f"获取五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取五元组失败: {str(e)}")


@router.get("/memory/quintuples/search")
async def search_quintuples(keywords: str = ""):
    """按关键词搜索五元组"""
    try:
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            raise HTTPException(status_code=400, detail="请提供搜索关键词")

        # 优先使用远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

        remote = get_remote_memory_client()
        if remote is not None:
            try:
                result = await remote.query_by_keywords(keyword_list)
                if result.get("success") is not False:
                    quintuples_raw = result.get("quintuples") or result.get("results") or result.get("data") or []
                    quintuples = []
                    for q in quintuples_raw:
                        normalized = _normalize_memory_quintuple_item(q)
                        if normalized:
                            quintuples.append(normalized)
                    return {"status": "success", "quintuples": quintuples, "count": len(quintuples)}
                else:
                    logger.warning(f"远程五元组搜索失败: {result.get('error')}")
            except Exception as e:
                logger.warning(f"远程五元组搜索异常: {e}")

        if should_prefer_remote_memory():
            return {
                "status": "success",
                "quintuples": [],
                "count": 0,
                "message": "当前为云端记忆模式，远程搜索暂不可用，未再回退本地知识图谱",
            }

        # 回退到本地 summer_memory
        from summer_memory.quintuple_graph import query_graph_by_keywords

        results = query_graph_by_keywords(keyword_list)
        return {
            "status": "success",
            "quintuples": [
                {"subject": q[0], "subject_type": q[1], "predicate": q[2], "object": q[3], "object_type": q[4]}
                for q in results
            ],
            "count": len(results),
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "message": "记忆系统模块未找到"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索五元组失败: {str(e)}")


# ============ 搜索代理 ============


@router.api_route("/tools/search", methods=["GET", "POST"])
async def proxy_search(request: Request):
    """统一搜索代理: 优先 NagaModel，回退 Brave，供 Naga 与 OpenClaw 共用。"""

    if request.method == "GET":
        params = dict(request.query_params)
    else:
        params = await request.json()

    import httpx

    async def _call_upstream(client: httpx.AsyncClient, url: str, headers: dict):
        if request.method == "GET":
            return await client.get(url, params=params, headers=headers, timeout=30)
        return await client.post(url, json=params, headers=headers, timeout=30)

    try:
        async with httpx.AsyncClient() as client:
            resp = None
            token = naga_auth.get_access_token()
            if not token and naga_auth.has_refresh_token():
                try:
                    await naga_auth.ensure_access_token()
                    token = naga_auth.get_access_token()
                except Exception as refresh_err:
                    logger.warning(f"搜索代理预刷新 access token 失败: {refresh_err}")

            if not token:
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]

            # 优先 Naga 登录态；401 时自动 refresh 一次
            if token:
                upstream_url = naga_auth.NAGA_MODEL_URL + "/tools/search"
                resp = await _call_upstream(
                    client,
                    upstream_url,
                    {"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401 and naga_auth.has_refresh_token():
                    logger.warning("搜索代理检测到 Naga token 过期，尝试刷新后重试")
                    try:
                        refresh_result = await naga_auth.refresh()
                        token = refresh_result.get("access_token") or naga_auth.get_access_token()
                        resp = await _call_upstream(
                            client,
                            upstream_url,
                            {"Authorization": f"Bearer {token}"},
                        )
                    except Exception as refresh_err:
                        logger.warning(f"搜索代理刷新 Naga token 失败: {refresh_err}")

            # Naga 不可用或仍然 401/403 时，回退 Brave
            if resp is None or resp.status_code in (401, 403):
                cfg = get_config()
                search_key = getattr(cfg.online_search, "search_api_key", "")
                search_base = getattr(cfg.online_search, "search_api_base", "")
                if not search_key or not search_base:
                    if resp is not None and resp.status_code in (401, 403):
                        detail = resp.text
                        raise HTTPException(status_code=401, detail=detail or "Naga 搜索认证失败，且未配置 Brave 搜索")
                    raise HTTPException(status_code=401, detail="未登录且未配置搜索服务")
                resp = await _call_upstream(
                    client,
                    search_base,
                    {
                        "Accept": "application/json",
                        "X-Subscription-Token": search_key,
                    },
                )

        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"搜索代理失败: {e}")
        return JSONResponse(
            content={"error": {"message": f"搜索服务不可用: {e}", "type": "upstream_error"}},
            status_code=502,
        )
