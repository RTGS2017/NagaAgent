"""系统信息、健康检查、配置、日志、更新路由"""

import asyncio
import copy
import logging
import traceback
from typing import Dict, Any, List
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from system.config import get_config, VERSION, build_system_prompt
from system.config_value_utils import is_placeholder_api_key, preserve_existing_api_key_if_placeholder
from system.config_manager import get_config_snapshot, update_config
from system.live2d_assets import (
    create_custom_live2d_model,
    delete_custom_live2d_model,
    get_custom_live2d_model,
    list_custom_live2d_models,
)
from apiserver.message_manager import message_manager
from apiserver.api_server import SystemInfoResponse
from apiserver.telemetry import emit_telemetry

logger = logging.getLogger(__name__)

router = APIRouter()


def _notification_telemetry_snapshot(config_data: Dict[str, Any]) -> Dict[str, Any]:
    notifications = config_data.get("notifications", {}) or {}
    openclaw = config_data.get("openclaw", {}) or {}
    feishu_channel = openclaw.get("feishu", {}) or {}
    feishu_notify = notifications.get("feishu", {}) or {}
    qq_notify = notifications.get("qq", {}) or {}

    qq_target = str(qq_notify.get("binding_target") or "").strip()
    qq_code = str(qq_notify.get("email_verification_code") or "").strip()
    feishu_target = (
        str(feishu_notify.get("recipient_chat_id") or "").strip()
        if feishu_notify.get("recipient_type") == "chat_id"
        else str(feishu_notify.get("recipient_open_id") or "").strip()
    )

    return {
        "qq_enabled": bool(qq_notify.get("enabled")),
        "qq_has_binding": bool(qq_target),
        "qq_has_verification_code": bool(qq_code),
        "feishu_enabled": bool(feishu_notify.get("enabled")),
        "feishu_recipient_type": str(feishu_notify.get("recipient_type") or "open_id"),
        "feishu_has_target": bool(feishu_target),
        "feishu_has_app": bool(str(feishu_channel.get("app_id") or "").strip()) and bool(str(feishu_channel.get("app_secret") or "").strip()),
        "feishu_deliver_full_report": bool(feishu_notify.get("deliver_full_report", True)),
    }


def _sanitize_system_config_payload(
    payload: Dict[str, Any],
    current_config: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """清洗前端配置保存 payload，避免动态资源 URL 被持久化。"""
    sanitized = _normalize_system_config_aliases(copy.deepcopy(payload))
    system_config = sanitized.get("system")
    if isinstance(system_config, dict):
        system_config["version"] = VERSION
    if current_config is not None:
        preserve_existing_api_key_if_placeholder(sanitized, current_config)

    web_live2d = sanitized.get("web_live2d")
    if not isinstance(web_live2d, dict):
        return sanitized

    web_live2d.pop("custom_models", None)
    model_block = web_live2d.get("model")
    if not isinstance(model_block, dict):
        return sanitized

    source = str(model_block.get("source") or "").strip()
    parsed_source = urlparse(source)
    is_local_dynamic_url = (
        parsed_source.scheme in {"http", "https"}
        and parsed_source.hostname in {"localhost", "127.0.0.1"}
        and (
            parsed_source.path.startswith("/characters/")
            or parsed_source.path.startswith("/custom-live2d/")
        )
    )
    if source.startswith("naga-char://") or is_local_dynamic_url:
        model_block.pop("source", None)
    return sanitized


def _normalize_system_config_aliases(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """将历史前端键名归一为后端配置 schema 键名。"""
    alias_map = {
        "agentserver": "agent_server",
        "mcpserver": "mcp_server",
    }
    for legacy_key, canonical_key in alias_map.items():
        legacy_value = config_data.pop(legacy_key, None)
        if legacy_value is None:
            continue
        if canonical_key not in config_data:
            config_data[canonical_key] = legacy_value
    return config_data


# ============ 根路径 & 健康检查 ============


@router.get("/", response_model=Dict[str, str])
async def root():
    """API根路径"""
    return {
        "name": "NagaAgent API",
        "version": VERSION,
        "status": "running",
        "docs": "/docs",
    }


@router.get("/health")
async def health_check():
    """健康检查"""
    from apiserver.websocket_manager import get_websocket_manager

    ws_manager = get_websocket_manager()
    ws_stats = ws_manager.get_stats()

    return {
        "status": "healthy",
        "agent_ready": True,
        "websocket_connections": ws_stats["total_connections"],
        "timestamp": str(asyncio.get_running_loop().time()),
    }


@router.get("/health/full")
async def full_health_check():
    """完整健康检查（调用Agent Server的全面检查）"""
    import httpx
    from system.config import get_server_port

    agent_port = get_server_port("agent_server")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"http://127.0.0.1:{agent_port}/health/full")
            if resp.status_code == 200:
                return resp.json()
            else:
                raise HTTPException(resp.status_code, "Agent Server健康检查失败")
    except httpx.ConnectError:
        raise HTTPException(503, "无法连接到Agent Server")
    except Exception as e:
        raise HTTPException(500, f"健康检查失败: {e}")


# ============ 系统信息 & 配置 ============


@router.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    """获取系统信息"""

    return SystemInfoResponse(
        version=VERSION,
        status="running",
        available_services=[],  # MCP服务现在由mcpserver独立管理
        api_key_configured=not is_placeholder_api_key(get_config().api.api_key),
    )


@router.get("/system/config")
async def get_system_config():
    """获取完整系统配置（web_live2d.model.source 由角色系统动态注入）"""
    try:
        config_data = _normalize_system_config_aliases(copy.deepcopy(get_config_snapshot()))
        system_config = config_data.setdefault("system", {})
        if not isinstance(system_config, dict):
            system_config = {}
            config_data["system"] = system_config
        system_config["version"] = VERSION

        # 动态注入角色 Live2D 模型路径；未启用角色时按 custom_model_id 注入自定义模型路径。
        injected_model_source = False
        try:
            from system.config import load_character
            from urllib.parse import quote
            char_name = get_config().system.active_character
            if char_name:
                char_data = load_character(char_name)
                port = get_config().api_server.port
                encoded_name = quote(char_name, safe="")
                encoded_model = quote(char_data["live2d_model"], safe="/")
                model_url = f"http://localhost:{port}/characters/{encoded_name}/{encoded_model}"
                config_data.setdefault("web_live2d", {}).setdefault("model", {})["source"] = model_url
                injected_model_source = True
        except Exception as char_err:
            logger.warning(f"角色模型路径注入失败: {char_err}")
        if not injected_model_source:
            web_live2d = config_data.setdefault("web_live2d", {})
            model_block = web_live2d.setdefault("model", {})
            custom_model_id = str(web_live2d.get("custom_model_id") or "").strip()
            if custom_model_id:
                try:
                    custom_model = get_custom_live2d_model(custom_model_id, get_config().api_server.port)
                    if custom_model:
                        model_block["source"] = custom_model["source"]
                except Exception as custom_err:
                    logger.warning(f"自定义 Live2D 模型路径注入失败: {custom_err}")

        return {"status": "success", "config": config_data}
    except Exception as e:
        logger.error(f"获取系统配置失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.post("/system/config")
async def update_system_config(payload: Dict[str, Any]):
    """更新系统配置（自动过滤角色系统动态注入的 live2d 模型路径，避免写入 config.json）"""
    try:
        before_snapshot = get_config_snapshot()
        before_notification = _notification_telemetry_snapshot(before_snapshot)
        sanitized_payload = _sanitize_system_config_payload(payload, before_snapshot)

        success = update_config(sanitized_payload)
        if success:
            after_snapshot = get_config_snapshot()
            after_notification = _notification_telemetry_snapshot(after_snapshot)
            if after_notification != before_notification:
                emit_telemetry(
                    "notification_settings_updated",
                    {
                        "before": before_notification,
                        "after": after_notification,
                    },
                    source="apiserver",
                )
            return {"status": "success", "message": "配置更新成功"}
        else:
            raise HTTPException(status_code=500, detail="配置更新失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新系统配置失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.post("/system/notifications/qq/test")
async def test_qq_notification(payload: Dict[str, Any]):
    qq_user_id = str(payload.get("qq_user_id") or "").strip()
    if not qq_user_id:
        raise HTTPException(status_code=400, detail="缺少 QQ 号")

    try:
        from agentserver.travel_notifications import QQNotifyDeliveryError, send_test_qq_notification
        from apiserver import naga_auth

        naga_user_id = ""
        user = naga_auth.get_user_info()
        if not user:
            token = naga_auth.get_access_token()
            if token:
                user = await naga_auth.get_me(token)

        if user:
            naga_user_id = str(user.get("user_id") or user.get("username") or "").strip()

        status = await send_test_qq_notification(qq_user_id, None, naga_user_id=naga_user_id)
        emit_telemetry(
            "qq_notification_test_sent",
            {
                "qq_user_id": qq_user_id,
                "status": status,
                "naga_user_id": naga_user_id,
            },
            source="apiserver",
        )
        return {"status": "success", "delivery_status": status}
    except QQNotifyDeliveryError as e:
        logger.error(f"QQ 通知测试发送失败: {e}")
        emit_telemetry(
            "qq_notification_test_fail",
            {
                "qq_user_id": qq_user_id,
                "error": str(e),
                "status_code": e.status_code,
            },
            source="apiserver",
        )
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"QQ 通知测试发送失败: {e}")
        emit_telemetry(
            "qq_notification_test_fail",
            {
                "qq_user_id": qq_user_id,
                "error": str(e),
            },
            source="apiserver",
        )
        raise HTTPException(status_code=500, detail=f"QQ 通知测试发送失败: {e}")


@router.get("/system/prompt")
async def get_system_prompt(include_skills: bool = False):
    """获取系统提示词（默认只返回人格提示词，不包含技能列表）"""
    try:
        prompt = build_system_prompt()
        return {"status": "success", "prompt": prompt}
    except Exception as e:
        logger.error(f"获取系统提示词失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取系统提示词失败: {str(e)}")


@router.post("/system/prompt")
async def update_system_prompt(payload: Dict[str, Any]):
    """更新系统提示词"""
    try:
        content = payload.get("content")
        if not content:
            raise HTTPException(status_code=400, detail="缺少content参数")
        from system.config import save_prompt

        save_prompt("conversation_style_prompt", content)
        return {"status": "success", "message": "提示词更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新系统提示词失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"更新系统提示词失败: {str(e)}")


@router.get("/system/character")
async def get_active_character():
    """获取当前活跃角色信息及资源路径"""
    try:
        from system.config import load_character
        from urllib.parse import quote
        char_name = get_config().system.active_character
        char_data = load_character(char_name)
        port = get_config().api_server.port
        encoded_name = quote(char_name, safe="")
        encoded_model = quote(char_data["live2d_model"], safe="/")
        model_url = f"http://localhost:{port}/characters/{encoded_name}/{encoded_model}"
        return {
            "status": "success",
            "character": {
                "name": char_name,
                "ai_name": char_data["ai_name"],
                "user_name": char_data["user_name"],
                "live2d_model_url": model_url,
                "prompt_file": char_data["prompt_file"],
            },
        }
    except Exception as e:
        logger.error(f"获取角色信息失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取角色信息失败: {str(e)}")


@router.get("/system/characters")
async def list_characters():
    """列出所有角色模板"""
    try:
        from system.config import CHARACTERS_DIR, load_character
        from urllib.parse import quote

        active_name = get_config().system.active_character
        port = get_config().api_server.port
        characters = []
        if CHARACTERS_DIR.exists():
            for char_dir in sorted(CHARACTERS_DIR.iterdir()):
                if not char_dir.is_dir() or char_dir.name.startswith("."):
                    continue
                try:
                    data = load_character(char_dir.name)
                except Exception as char_err:
                    logger.warning(f"读取角色模板失败 [{char_dir.name}]: {char_err}")
                    continue

                characters.append({
                    "name": char_dir.name,
                    "ai_name": data.get("ai_name"),
                    "bio": data.get("bio"),
                    "voice": data.get("voice"),
                    "prompt_file": data.get("prompt_file"),
                    "portrait": data.get("portrait"),
                    "live2d_model": data.get("live2d_model"),
                    "live2d_model_url": (
                        f"http://localhost:{port}/characters/{quote(char_dir.name, safe='')}/{quote(data.get('live2d_model') or '', safe='/')}"
                        if data.get("live2d_model") else None
                    ),
                    "active": char_dir.name == active_name,
                })

        return {
            "status": "success",
            "active_character": active_name,
            "characters": characters,
        }
    except Exception as e:
        logger.error(f"获取角色模板列表失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取角色模板列表失败: {str(e)}")


@router.get("/system/live2d/custom-models")
async def list_live2d_custom_models() -> Dict[str, Any]:
    """列出用户上传的自定义 Live2D 模型。"""
    try:
        models = list_custom_live2d_models(get_config().api_server.port)
        return {"status": "success", "models": models}
    except Exception as e:
        logger.error(f"获取自定义 Live2D 模型失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取自定义 Live2D 模型失败: {str(e)}")


@router.post("/system/live2d/custom-models")
async def upload_live2d_custom_model(
    name: str = Form(...),
    files: List[UploadFile] = File(...),
    model_path: str = Form(""),
) -> Dict[str, Any]:
    """上传一整套 Live2D 模型资源并登记 .model3.json 入口。"""
    try:
        model = await create_custom_live2d_model(
            name=name,
            files=files,
            requested_model_path=model_path or None,
            api_port=get_config().api_server.port,
        )
        return {"status": "success", "model": model}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传自定义 Live2D 模型失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"上传自定义 Live2D 模型失败: {str(e)}")


@router.delete("/system/live2d/custom-models/{model_id}")
async def remove_live2d_custom_model(model_id: str) -> Dict[str, Any]:
    """删除用户上传的自定义 Live2D 模型。"""
    try:
        deleted = delete_custom_live2d_model(model_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="自定义 Live2D 模型不存在")
        return {"status": "success", "message": "自定义 Live2D 模型已删除"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"删除自定义 Live2D 模型失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除自定义 Live2D 模型失败: {str(e)}")


# ============ 更新检查 ============

_GITHUB_LATEST_RELEASE_URL = "https://api.github.com/repos/RTGS2017/NagaAgent/releases/latest"
_GITHUB_API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "NagaAgent-Update-Checker",
    "X-GitHub-Api-Version": "2022-11-28",
}
_UPDATE_ASSET_SUFFIXES: Dict[str, tuple[str, ...]] = {
    "windows": (".exe",),
    "macos": (".dmg",),
    "linux": (".appimage",),
}


def _select_github_release_asset(assets: List[Dict[str, Any]], platform: str) -> Dict[str, Any] | None:
    suffixes = _UPDATE_ASSET_SUFFIXES.get(platform, _UPDATE_ASSET_SUFFIXES["linux"])
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        if name.endswith((".blockmap", ".yml", ".yaml")):
            continue
        if name.endswith(suffixes):
            return asset
    return None


def _github_release_to_update_payload(release: Dict[str, Any], platform: str) -> Dict[str, Any]:
    version = str(release.get("tag_name") or release.get("name") or "").strip().removeprefix("v")
    if not version:
        raise ValueError("GitHub Release 缺少版本号")

    raw_assets = release.get("assets")
    assets = raw_assets if isinstance(raw_assets, list) else []
    asset = _select_github_release_asset(assets, platform)
    return {
        "version": version,
        "description": str(release.get("body") or release.get("name") or "").strip(),
        "force_update": False,
        "download_url": asset.get("browser_download_url") if asset else None,
        "file_size": asset.get("size") if asset else None,
        "has_update": True,
        "source": "github",
        "release_url": release.get("html_url"),
    }


async def _fetch_github_latest_update(client: httpx.AsyncClient, platform: str) -> Dict[str, Any]:
    response = await client.get(_GITHUB_LATEST_RELEASE_URL, headers=_GITHUB_API_HEADERS)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("GitHub Release 响应格式无效")
    return _github_release_to_update_payload(payload, platform)


async def _fetch_business_latest_update(client: httpx.AsyncClient, platform: str) -> Dict[str, Any]:
    from apiserver import naga_auth

    response = await client.get(
        f"{naga_auth.BUSINESS_URL}/api/app/NagaAgent/latest",
        params={"platform": platform},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("version"):
        raise ValueError("业务更新服务未返回有效版本")

    download_url = payload.get("download_url")
    if download_url and not str(download_url).startswith(("http://", "https://")):
        payload["download_url"] = f"{naga_auth.BUSINESS_URL}{download_url}"
    payload["source"] = "business"
    return payload


@router.get("/update/latest")
async def proxy_update_check(platform: str = "windows") -> Dict[str, Any]:
    """以 GitHub Release 为版本源，无法访问时回退到业务更新服务。"""
    normalized_platform = platform if platform in _UPDATE_ASSET_SUFFIXES else "linux"
    errors: List[str] = []

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            return await _fetch_github_latest_update(client, normalized_platform)
        except Exception as exc:
            errors.append(f"GitHub: {exc}")
            logger.warning("GitHub 更新检查失败，准备回退业务服务: %s", exc)

        try:
            return await _fetch_business_latest_update(client, normalized_platform)
        except Exception as exc:
            errors.append(f"Business: {exc}")
            logger.warning("业务更新检查失败: %s", exc)

    logger.error("全部更新源不可用: %s", "; ".join(errors))
    raise HTTPException(status_code=502, detail="更新服务暂不可用，请稍后重试")


# ============ 日志上下文 ============


@router.get("/logs/context/statistics")
async def get_log_context_statistics(days: int = 7):
    """获取日志上下文统计信息"""
    try:
        statistics = message_manager.get_context_statistics(days)
        return {"status": "success", "statistics": statistics}
    except Exception as e:
        print(f"获取日志上下文统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/logs/context/load")
async def load_log_context(days: int = 3, max_messages: int = None):
    """加载日志上下文"""
    try:
        messages = message_manager.load_recent_context(days=days, max_messages=max_messages)
        return {"status": "success", "messages": messages, "count": len(messages), "days": days}
    except Exception as e:
        print(f"加载日志上下文错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"加载上下文失败: {str(e)}")
