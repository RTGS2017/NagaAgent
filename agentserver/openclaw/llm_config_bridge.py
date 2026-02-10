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
from typing import Optional

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_DIR = Path.home() / ".openclaw"
OPENCLAW_CONFIG_FILE = OPENCLAW_CONFIG_DIR / "openclaw.json"


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
                "token": hooks_token,
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
