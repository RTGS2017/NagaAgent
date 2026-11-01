#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 配置自动生成 + LLM 桥接

当 ~/.naga/openclaw/openclaw.json 不存在时，自动生成最小可用配置，
并注入 Naga 的 LLM 设置（api_key / base_url / model）。
不再依赖 `openclaw onboard` 命令。
"""

import json
import logging
import secrets
import shutil
from pathlib import Path
from typing import Dict, Any

from .state_paths import get_openclaw_config_path, get_openclaw_state_dir

logger = logging.getLogger("openclaw.bridge")


def _get_openclaw_paths():
    """统一使用 Naga OpenClaw 目录 (~/.naga/openclaw)。"""
    config_file = get_openclaw_config_path()
    return config_file.parent, config_file


def _get_openclaw_config_file() -> Path:
    return get_openclaw_config_path()


def _get_openclaw_config_dir() -> Path:
    return _get_openclaw_config_file().parent


def _migrate_legacy_config_if_needed() -> None:
    """兼容历史错误路径：~/.openclaw -> ~/.naga/openclaw"""
    config_file = _get_openclaw_config_file()
    config_dir = config_file.parent
    if config_file.exists():
        return
    try:
        legacy_cfg = Path.home() / ".openclaw" / "openclaw.json"
        if not legacy_cfg.exists():
            return

        config_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_cfg, config_file)
        logger.info(f"已迁移 OpenClaw 配置: {legacy_cfg} -> {config_file}")
    except Exception as e:
        logger.warning(f"迁移历史 OpenClaw 配置失败（忽略）: {e}")


def _apply_hooks_compat_patch(config_data: Dict[str, Any]) -> bool:
    """确保 hooks.allowRequestSessionKey=true，允许外部 relay 复用会话键。"""
    hooks = config_data.get("hooks", {})
    if hooks.get("allowRequestSessionKey") is True:
        return False
    hooks["allowRequestSessionKey"] = True
    config_data["hooks"] = hooks
    return True


def _apply_hooks_path_patch(config_data: Dict[str, Any]) -> bool:
    """确保 hooks.path 已显式设置为 /hooks，避免 Gateway 不注册 hooks 路由导致405。"""
    hooks = config_data.setdefault("hooks", {})
    if hooks.get("path") == "/hooks":
        return False
    hooks["path"] = "/hooks"
    return True


def _apply_gateway_mode_compat_patch(config_data: Dict[str, Any]) -> bool:
    """
    兼容 OpenClaw Gateway 启动约束：
    当 gateway.mode 缺失/为空时补齐为 local，避免启动被阻塞。
    """
    gateway = config_data.setdefault("gateway", {})
    mode = gateway.get("mode")
    if isinstance(mode, str) and mode.strip():
        return False
    gateway["mode"] = "local"
    return True


NAGA_GATEWAY_PORT = 20789


def _get_gateway_port() -> int:
    """从 system.config 读取端口（单一来源），import 失败则回退常量。"""
    try:
        from system.config import config as _cfg
        return _cfg.openclaw.gateway_port
    except Exception:
        return NAGA_GATEWAY_PORT


def _apply_gateway_port_patch(config_data: Dict[str, Any]) -> bool:
    """确保 gateway.port 与 NagaAgent 配置一致。"""
    port = _get_gateway_port()
    gateway = config_data.setdefault("gateway", {})
    if gateway.get("port") == port:
        return False
    gateway["port"] = port
    return True


def _apply_runtime_compat_patches(config_data: Dict[str, Any]) -> bool:
    """应用 Naga 启动 OpenClaw 所需的基础兼容补丁。"""
    changed = False
    changed = _apply_hooks_compat_patch(config_data) or changed
    changed = _apply_hooks_path_patch(config_data) or changed
    changed = _apply_gateway_mode_compat_patch(config_data) or changed
    changed = _apply_gateway_port_patch(config_data) or changed
    return changed


def _ensure_runtime_compat_patches(config_file: Path) -> bool:
    """确保已有 openclaw.json 也满足当前运行时要求。"""
    try:
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用运行时兼容补丁: {e}")
        return False

    if not _apply_runtime_compat_patches(config_data):
        return True

    try:
        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已补齐 OpenClaw 运行时兼容配置")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，运行时兼容补丁未生效: {e}")
        return False


def ensure_hooks_allow_request_session_key(auto_create: bool = False) -> bool:
    """
    确保 openclaw.json 中启用 hooks.allowRequestSessionKey=true。

    Args:
        auto_create: 当配置不存在时是否自动创建最小配置

    Returns:
        True 表示已满足条件（已存在或已修复），False 表示修复失败
    """
    config_file = _get_openclaw_config_file()
    if not config_file.exists():
        if not auto_create:
            logger.debug("openclaw.json 不存在，跳过 hooks.allowRequestSessionKey 兼容补丁")
            return False
        if not ensure_openclaw_config():
            return False
        config_file = _get_openclaw_config_file()

    try:
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 hooks 兼容补丁: {e}")
        return False

    changed = _apply_hooks_compat_patch(config_data)
    if not changed:
        return True

    try:
        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已启用 OpenClaw hooks.allowRequestSessionKey=true（允许外部 sessionKey）")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，hooks 兼容补丁未生效: {e}")
        return False


def ensure_gateway_local_mode(auto_create: bool = False) -> bool:
    """
    确保 openclaw.json 的 gateway.mode 已设置为 local（仅在缺失时补齐）。

    Args:
        auto_create: 当配置不存在时是否自动创建最小配置

    Returns:
        True 表示已满足条件（已存在或已修复），False 表示修复失败
    """
    config_file = _get_openclaw_config_file()
    if not config_file.exists():
        if not auto_create:
            logger.debug("openclaw.json 不存在，跳过 gateway.mode 兼容补丁")
            return False
        if not ensure_openclaw_config():
            return False
        config_file = _get_openclaw_config_file()

    try:
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 gateway.mode 兼容补丁: {e}")
        return False

    changed = _apply_gateway_mode_compat_patch(config_data)
    if not changed:
        return True

    try:
        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已补齐 OpenClaw gateway.mode=local（兼容旧配置）")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，gateway.mode 兼容补丁未生效: {e}")
        return False


def ensure_hooks_path(auto_create: bool = False) -> bool:
    """确保 openclaw.json 的 hooks.path 已显式设置为 /hooks。"""
    config_file = _get_openclaw_config_file()
    if not config_file.exists():
        if not auto_create:
            return False
        if not ensure_openclaw_config():
            return False
        config_file = _get_openclaw_config_file()

    try:
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 hooks.path 补丁: {e}")
        return False

    changed = _apply_hooks_path_patch(config_data)
    if not changed:
        return True

    try:
        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已补齐 OpenClaw hooks.path=/hooks（避免 Gateway 不注册 hooks 路由）")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，hooks.path 补丁未生效: {e}")
        return False


def ensure_gateway_port(auto_create: bool = False) -> bool:
    """确保 openclaw.json 的 gateway.port 与 NagaAgent 配置一致。"""
    config_file = _get_openclaw_config_file()
    if not config_file.exists():
        if not auto_create:
            return False
        if not ensure_openclaw_config():
            return False
        config_file = _get_openclaw_config_file()

    try:
        config_data = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 gateway.port 补丁: {e}")
        return False

    changed = _apply_gateway_port_patch(config_data)
    if not changed:
        return True

    port = _get_gateway_port()
    try:
        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"已将 gateway.port 更新为 {port}")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，gateway.port 补丁未生效: {e}")
        return False


def ensure_openclaw_config() -> bool:
    """
    确保 openclaw.json 存在，不存在则自动生成最小可用配置。

    Returns:
        是否成功（已存在或新建成功）
    """
    _migrate_legacy_config_if_needed()
    config_file = _get_openclaw_config_file()
    config_dir = config_file.parent

    if config_file.exists():
        logger.debug("openclaw.json 已存在，跳过生成")
        return _ensure_runtime_compat_patches(config_file)

    try:
        config_dir.mkdir(parents=True, exist_ok=True)

        gateway_token = secrets.token_hex(32)
        hooks_token = secrets.token_hex(32)

        minimal_config = {
            "gateway": {
                "mode": "local",
                "port": _get_gateway_port(),
                "bind": "loopback",
                "auth": {"mode": "token", "token": gateway_token},
            },
            "hooks": {
                "enabled": True,
                "path": "/hooks",
                "token": hooks_token,
                "allowRequestSessionKey": True,
            },
            "tools": {"allow": ["*"]},
            "agents": {
                "defaults": {
                    "workspace": str(get_openclaw_state_dir() / "workspace"),
                    "maxConcurrent": 4,
                }
            },
        }

        config_file.write_text(
            json.dumps(minimal_config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"已自动生成 openclaw.json: {config_file}")
        return True

    except Exception as e:
        logger.error(f"自动生成 openclaw.json 失败: {e}")
        return False


def inject_naga_llm_config() -> bool:
    """
    将 Naga 的 LLM + 搜索 配置注入 openclaw.json。

    - LLM: api_key / base_url / model → models.providers + agents.defaults.model
    - 搜索: online_search.search_api_key → env.BRAVE_API_KEY

    Returns:
        是否注入成功
    """
    config_file = _get_openclaw_config_file()
    config_dir = config_file.parent
    if not config_file.exists():
        logger.warning("openclaw.json 不存在，无法注入配置")
        return False

    try:
        from system.config import config as naga_config, get_data_dir

        config_data = json.loads(config_file.read_text(encoding="utf-8"))
        _apply_runtime_compat_patches(config_data)

        # ── LLM Provider ──
        # 使用本地 API Server 的 OpenAI 兼容代理端点（统一计费）
        from system.config import get_server_port
        api_port = get_server_port("api_server")
        base_url = f"http://127.0.0.1:{api_port}/v1"
        logger.info(f"OpenClaw 使用 Naga 代理端点: {base_url}/chat/completions")

        # 根据模型 ID 判断 provider 类型（让 OpenClaw 识别特殊模型）
        model_id = naga_config.api.model
        model_id_lower = model_id.lower()
        if "kimi" in model_id_lower or "moonshot" in model_id_lower:
            provider_name = "moonshot"
        elif "deepseek" in model_id_lower:
            provider_name = "deepseek"
        elif "glm" in model_id_lower:
            provider_name = "zhipu"
        elif "qwen" in model_id_lower:
            provider_name = "alibaba"
        elif "minimax" in model_id_lower:
            provider_name = "minimax"
        else:
            provider_name = "naga"
        full_model_id = f"{provider_name}/{model_id}"

        models_config = config_data.setdefault("models", {})
        models_config["mode"] = "merge"
        # 清空旧 providers 避免遗留无效配置导致校验失败
        providers = {}
        models_config["providers"] = providers
        providers[provider_name] = {
            "baseUrl": base_url,
            "apiKey": "naga-proxy-placeholder",
            "auth": "api-key",
            "api": "openai-completions",
            "models": [
                {
                    "id": model_id,
                    "name": model_id,
                    "reasoning": False,
                    "input": ["text"],
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    "contextWindow": 128000,
                    "maxTokens": naga_config.api.max_tokens,
                }
            ],
        }

        # 设置为默认模型
        agents = config_data.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        model = defaults.setdefault("model", {})
        model["primary"] = full_model_id

        # ── 搜索 API Key（Brave Search）──
        # 同步到 env.BRAVE_API_KEY + tools.web.search.apiKey 两处
        # 注：OpenClaw 不支持自定义 Brave base URL，但主路径搜索走 NagaAgent 本地执行
        search_key = getattr(naga_config.online_search, "search_api_key", "")
        env_section = config_data.setdefault("env", {})
        channels_section = config_data.setdefault("channels", {})
        tools_section = config_data.setdefault("tools", {})
        tools_section["loopDetection"] = {
            "enabled": True,
            "historySize": 20,
            "warningThreshold": 4,
            "criticalThreshold": 6,
            "globalCircuitBreakerThreshold": 8,
            "detectors": {
                "genericRepeat": True,
                "knownPollNoProgress": True,
                "pingPong": True,
            },
        }
        web_section = tools_section.setdefault("web", {})
        search_section = web_section.setdefault("search", {})
        search_section["enabled"] = True
        search_section["provider"] = "brave"
        # OpenClaw 只检查“有没有 key”，实际请求会被 BRAVE_SEARCH_BASE_URL 重定向到本地统一搜索代理。
        search_section["apiKey"] = "naga-search-proxy"
        env_section["BRAVE_API_KEY"] = "naga-search-proxy"

        # ── 公有技能目录共享给 OpenClaw ──
        shared_public_skills_dir = get_data_dir() / "skills" / "public"
        shared_public_skills_dir.mkdir(parents=True, exist_ok=True)
        skills_section = config_data.setdefault("skills", {})
        skills_load_section = skills_section.setdefault("load", {})
        extra_dirs = skills_load_section.setdefault("extraDirs", [])
        shared_public_path = str(shared_public_skills_dir)
        if shared_public_path not in extra_dirs:
            extra_dirs.append(shared_public_path)

        # ── 飞书通道注入（可选）──
        feishu_cfg = getattr(naga_config.openclaw, "feishu", None)
        if feishu_cfg and getattr(feishu_cfg, "enabled", False):
            app_id = getattr(feishu_cfg, "app_id", "").strip()
            app_secret = getattr(feishu_cfg, "app_secret", "").strip()
            if app_id and app_secret:
                feishu_channel = {
                    "enabled": True,
                    "appId": app_id,
                    "appSecret": app_secret,
                    "dmPolicy": getattr(feishu_cfg, "dm_policy", "open"),
                    "groupPolicy": getattr(feishu_cfg, "group_policy", "allowlist"),
                }
                allow_from = getattr(feishu_cfg, "allow_from", None) or []
                if allow_from:
                    feishu_channel["allowFrom"] = [str(item).strip() for item in allow_from if str(item).strip()]
                doc_owner_open_id = getattr(feishu_cfg, "doc_owner_open_id", None)
                if doc_owner_open_id:
                    feishu_channel["docOwnerOpenId"] = str(doc_owner_open_id).strip()
                channels_section["feishu"] = feishu_channel
            else:
                logger.warning("OpenClaw 飞书已启用，但缺少 app_id/app_secret，跳过通道注入")

        config_file.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # 创建 auth-profiles.json 让 OpenClaw 能找到 API key
        auth_profiles_path = config_dir / "agents" / "main" / "agent" / "auth-profiles.json"
        auth_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        auth_profiles = {
            f"{provider_name}:default": {
                "provider": provider_name,
                "mode": "api_key",
                "apiKey": "naga-proxy-placeholder"
            }
        }
        auth_profiles_path.write_text(
            json.dumps(auth_profiles, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(
            f"已注入 Naga 配置: model={full_model_id}, search_key={'已配置' if search_key else '未配置'}, "
            f"feishu={'已启用' if (feishu_cfg and getattr(feishu_cfg, 'enabled', False)) else '未启用'}"
        )
        return True

    except Exception as e:
        logger.error(f"注入配置失败: {e}")
        return False
