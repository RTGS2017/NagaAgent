#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 配置自动生成 + LLM 桥接

当 ~/.openclaw/openclaw.json 不存在时，自动生成最小可用配置，
并注入 Naga 的 LLM 设置（api_key / base_url / model）。
不再依赖 `openclaw onboard` 命令。
"""

import json
import logging
import secrets
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG_FILE = OPENCLAW_CONFIG_DIR / "openclaw.json"


def _apply_hooks_compat_patch(config_data: Dict[str, Any]) -> bool:
    """兼容 OpenClaw 新版 hooks 约束，确保允许外部请求携带 sessionKey。"""
    hooks = config_data.setdefault("hooks", {})
    if hooks.get("allowRequestSessionKey") is True:
        return False
    hooks["allowRequestSessionKey"] = True
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


def ensure_hooks_allow_request_session_key(auto_create: bool = False) -> bool:
    """
    确保 openclaw.json 中启用 hooks.allowRequestSessionKey=true。

    Args:
        auto_create: 当配置不存在时是否自动创建最小配置

    Returns:
        True 表示已满足条件（已存在或已修复），False 表示修复失败
    """
    if not OPENCLAW_CONFIG_FILE.exists():
        if not auto_create:
            logger.debug("openclaw.json 不存在，跳过 hooks.allowRequestSessionKey 兼容补丁")
            return False
        if not ensure_openclaw_config():
            return False

    try:
        config_data = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 hooks 兼容补丁: {e}")
        return False

    changed = _apply_hooks_compat_patch(config_data)
    if not changed:
        return True

    try:
        OPENCLAW_CONFIG_FILE.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已启用 OpenClaw hooks.allowRequestSessionKey=true（兼容外部 sessionKey）")
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
    if not OPENCLAW_CONFIG_FILE.exists():
        if not auto_create:
            logger.debug("openclaw.json 不存在，跳过 gateway.mode 兼容补丁")
            return False
        if not ensure_openclaw_config():
            return False

    try:
        config_data = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 gateway.mode 兼容补丁: {e}")
        return False

    changed = _apply_gateway_mode_compat_patch(config_data)
    if not changed:
        return True

    try:
        OPENCLAW_CONFIG_FILE.write_text(
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
    if not OPENCLAW_CONFIG_FILE.exists():
        if not auto_create:
            return False
        if not ensure_openclaw_config():
            return False

    try:
        config_data = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"读取 openclaw.json 失败，无法应用 hooks.path 补丁: {e}")
        return False

    changed = _apply_hooks_path_patch(config_data)
    if not changed:
        return True

    try:
        OPENCLAW_CONFIG_FILE.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("已补齐 OpenClaw hooks.path=/hooks（避免 Gateway 不注册 hooks 路由）")
        return True
    except Exception as e:
        logger.error(f"写入 openclaw.json 失败，hooks.path 补丁未生效: {e}")
        return False


def ensure_openclaw_config() -> bool:
    """
    确保 openclaw.json 存在，不存在则自动生成最小可用配置。

    Returns:
        是否成功（已存在或新建成功）
    """
    if OPENCLAW_CONFIG_FILE.exists():
        logger.debug("openclaw.json 已存在，跳过生成")
        return True

    try:
        OPENCLAW_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        gateway_token = secrets.token_hex(32)
        hooks_token = secrets.token_hex(32)

        minimal_config = {
            "gateway": {
                "mode": "local",
                "port": 18789,
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
                    "workspace": str(OPENCLAW_CONFIG_DIR / "workspace"),
                    "maxConcurrent": 4,
                }
            },
        }

        OPENCLAW_CONFIG_FILE.write_text(
            json.dumps(minimal_config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"已自动生成 openclaw.json: {OPENCLAW_CONFIG_FILE}")
        return True

    except Exception as e:
        logger.error(f"自动生成 openclaw.json 失败: {e}")
        return False


def inject_naga_llm_config() -> bool:
    """
    将 Naga 的 LLM 配置注入 openclaw.json。

    读取 Naga 的 api_key / base_url / model，写入 openclaw.json 的
    models.providers 和 agents.defaults.model.primary。

    Returns:
        是否注入成功
    """
    if not OPENCLAW_CONFIG_FILE.exists():
        logger.warning("openclaw.json 不存在，无法注入 LLM 配置")
        return False

    try:
        from system.config import config as naga_config

        config_data = json.loads(OPENCLAW_CONFIG_FILE.read_text(encoding="utf-8"))
        _apply_hooks_compat_patch(config_data)
        _apply_gateway_mode_compat_patch(config_data)

        # 构建 naga provider
        provider_name = "naga"
        model_id = naga_config.api.model
        full_model_id = f"{provider_name}/{model_id}"

        models_config = config_data.setdefault("models", {})
        models_config["mode"] = "merge"
        providers = models_config.setdefault("providers", {})
        providers[provider_name] = {
            "baseUrl": naga_config.api.base_url.rstrip("/"),
            "apiKey": naga_config.api.api_key,
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

        OPENCLAW_CONFIG_FILE.write_text(
            json.dumps(config_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"已注入 Naga LLM 配置: provider={provider_name}, model={full_model_id}")
        return True

    except Exception as e:
        logger.error(f"注入 LLM 配置失败: {e}")
        return False
