#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 状态检测器
自动检测 OpenClaw 安装状态、配置和 Gateway 连接
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OpenClawStatus:
    """OpenClaw 状态信息"""
    # 安装状态
    installed: bool = False
    source_mode: bool = False
    config_path: Optional[str] = None

    # Gateway 配置
    gateway_url: Optional[str] = None
    gateway_port: int = 18789
    gateway_token: Optional[str] = None
    gateway_enabled: bool = False

    # Hooks 配置
    hooks_enabled: bool = False
    hooks_token: Optional[str] = None

    # 连接状态
    gateway_reachable: bool = False

    # 其他信息
    version: Optional[str] = None
    workspace: Optional[str] = None
    primary_model: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "installed": self.installed,
            "source_mode": self.source_mode,
            "config_path": self.config_path,
            "gateway_url": self.gateway_url,
            "gateway_port": self.gateway_port,
            "gateway_token": self.gateway_token,
            "gateway_enabled": self.gateway_enabled,
            "hooks_enabled": self.hooks_enabled,
            "hooks_token": self.hooks_token,
            "gateway_reachable": self.gateway_reachable,
            "version": self.version,
            "workspace": self.workspace,
            "primary_model": self.primary_model
        }


class OpenClawDetector:
    """OpenClaw 状态检测器"""

    # OpenClaw 配置目录
    OPENCLAW_DIR = Path.home() / ".openclaw"
    OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"

    def __init__(self):
        self._cached_status: Optional[OpenClawStatus] = None

    def detect(self, check_connection: bool = False) -> OpenClawStatus:
        """
        检测 OpenClaw 状态

        Args:
            check_connection: 是否检查 Gateway 连接状态

        Returns:
            OpenClawStatus 对象
        """
        status = OpenClawStatus()

        # 1. 检查是否安装（目录是否存在）
        if self.OPENCLAW_DIR.exists():
            status.installed = True
            status.config_path = str(self.OPENCLAW_CONFIG)

            # 2. 读取配置文件
            if self.OPENCLAW_CONFIG.exists():
                try:
                    config = self._read_config()
                    if config:
                        self._parse_config(config, status)
                except Exception as e:
                    logger.warning(f"读取 OpenClaw 配置失败: {e}")

        # 打包环境下，即使 ~/.openclaw/ 不存在，只要内嵌运行时可用也标记为已安装
        from .embedded_runtime import get_embedded_runtime
        runtime = get_embedded_runtime()
        if not status.installed:
            if runtime.is_packaged and runtime.openclaw_path:
                status.installed = True
                logger.info("打包环境：内嵌运行时可用，标记 OpenClaw 为已安装")

        # 3. 检查 Gateway 连接（可选）
        if check_connection and status.gateway_url:
            status.gateway_reachable = self._check_gateway_connection(status.gateway_url)

        self._cached_status = status
        return status

    def _read_config(self) -> Optional[Dict[str, Any]]:
        """读取 OpenClaw 配置文件"""
        try:
            with open(self.OPENCLAW_CONFIG, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 OpenClaw 配置文件失败: {e}")
            return None

    def _parse_config(self, config: Dict[str, Any], status: OpenClawStatus):
        """解析配置文件"""
        # Gateway 配置
        gateway = config.get("gateway", {})
        status.gateway_enabled = gateway.get("enabled", False)
        status.gateway_port = gateway.get("port", 18789)

        # 构建 Gateway URL
        host = gateway.get("host", "127.0.0.1")
        bind = gateway.get("bind", "loopback")
        if bind == "loopback":
            host = "127.0.0.1"
        status.gateway_url = f"http://{host}:{status.gateway_port}"

        # 认证 token
        auth = gateway.get("auth", {})
        if auth.get("mode") == "token":
            status.gateway_token = auth.get("token")
        elif auth.get("mode") == "password":
            # password 模式使用 password 作为 token
            status.gateway_token = auth.get("password")

        # Hooks 配置
        hooks = config.get("hooks", {})
        status.hooks_enabled = hooks.get("enabled", False)
        status.hooks_token = hooks.get("token")

        # 版本信息
        meta = config.get("meta", {})
        status.version = meta.get("lastTouchedVersion")

        # Agent 配置
        agents = config.get("agents", {})
        defaults = agents.get("defaults", {})
        status.workspace = defaults.get("workspace")

        # 主模型
        model_config = defaults.get("model", {})
        status.primary_model = model_config.get("primary")

    def _check_gateway_connection(self, url: str) -> bool:
        """检查 Gateway 连接状态"""
        try:
            import socket
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 18789

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except Exception as e:
            logger.debug(f"Gateway 连接检查失败: {e}")
            return False

    async def check_gateway_health_async(self, url: str, token: Optional[str] = None) -> Dict[str, Any]:
        """异步检查 Gateway 健康状态"""
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{url}/", headers=headers)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "reachable": True,
                        "url": url
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "reachable": True,
                        "url": url,
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unreachable",
                "reachable": False,
                "url": url,
                "error": str(e)
            }

    def get_cached_status(self) -> Optional[OpenClawStatus]:
        """获取缓存的状态"""
        return self._cached_status

    def get_token(self) -> Optional[str]:
        """快速获取 gateway token"""
        if self._cached_status:
            return self._cached_status.gateway_token

        status = self.detect()
        return status.gateway_token

    def get_hooks_token(self) -> Optional[str]:
        """快速获取 hooks token"""
        if self._cached_status:
            return self._cached_status.hooks_token

        status = self.detect()
        return status.hooks_token

    def get_gateway_url(self) -> Optional[str]:
        """快速获取 Gateway URL"""
        if self._cached_status:
            return self._cached_status.gateway_url

        status = self.detect()
        return status.gateway_url

    def is_installed(self) -> bool:
        """检查是否安装"""
        return self.OPENCLAW_DIR.exists()


# 全局检测器实例
_detector: Optional[OpenClawDetector] = None


def get_openclaw_detector() -> OpenClawDetector:
    """获取全局检测器实例"""
    global _detector
    if _detector is None:
        _detector = OpenClawDetector()
    return _detector


def detect_openclaw(check_connection: bool = False) -> OpenClawStatus:
    """快速检测 OpenClaw 状态"""
    return get_openclaw_detector().detect(check_connection)


def get_openclaw_token() -> Optional[str]:
    """快速获取 OpenClaw gateway token"""
    return get_openclaw_detector().get_token()


def get_openclaw_hooks_token() -> Optional[str]:
    """快速获取 OpenClaw hooks token"""
    return get_openclaw_detector().get_hooks_token()


def get_openclaw_gateway_url() -> Optional[str]:
    """快速获取 OpenClaw Gateway URL"""
    return get_openclaw_detector().get_gateway_url()
