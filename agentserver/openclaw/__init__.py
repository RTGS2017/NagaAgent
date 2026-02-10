#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 模块

官方文档: https://docs.openclaw.ai/
"""

from .openclaw_client import (
    OpenClawClient,
    OpenClawConfig,
    OpenClawTask,
    OpenClawSessionInfo,
    TaskStatus,
    get_openclaw_client,
    set_openclaw_config
)

from .detector import (
    OpenClawStatus,
    OpenClawDetector,
    get_openclaw_detector,
    detect_openclaw,
    get_openclaw_token,
    get_openclaw_hooks_token,
    get_openclaw_gateway_url
)

from .installer import (
    OpenClawInstaller,
    InstallMethod,
    InstallStatus,
    InstallResult,
    get_openclaw_installer
)

from .config_manager import (
    OpenClawConfigManager,
    ConfigUpdateResult,
    get_openclaw_config_manager
)

from .embedded_runtime import (
    EmbeddedRuntime,
    get_embedded_runtime
)

__all__ = [
    # Client
    "OpenClawClient",
    "OpenClawConfig",
    "OpenClawTask",
    "OpenClawSessionInfo",
    "TaskStatus",
    "get_openclaw_client",
    "set_openclaw_config",
    # Detector
    "OpenClawStatus",
    "OpenClawDetector",
    "get_openclaw_detector",
    "detect_openclaw",
    "get_openclaw_token",
    "get_openclaw_hooks_token",
    "get_openclaw_gateway_url",
    # Installer
    "OpenClawInstaller",
    "InstallMethod",
    "InstallStatus",
    "InstallResult",
    "get_openclaw_installer",
    # Config Manager
    "OpenClawConfigManager",
    "ConfigUpdateResult",
    "get_openclaw_config_manager",
    # Embedded Runtime
    "EmbeddedRuntime",
    "get_embedded_runtime",
]
