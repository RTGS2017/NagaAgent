#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志管理

打包环境下将详细日志写入安装目录的 logs/ 文件夹，支持轮转。
开发环境下写入项目根目录的 logs/ 文件夹。
"""

import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

# 是否为 PyInstaller 打包环境
IS_PACKAGED: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _resolve_log_dir() -> Path:
    """推导日志目录"""
    if IS_PACKAGED:
        # PyInstaller: sys._MEIPASS 是 _internal 目录
        # _internal -> backend -> resources (安装目录)
        install_dir = Path(sys._MEIPASS).parent.parent  # type: ignore[attr-defined]
        return install_dir / "logs"
    else:
        # 开发环境：项目根目录 / logs
        return Path(__file__).resolve().parent.parent / "logs"


def setup_logging() -> None:
    """统一初始化日志系统"""
    log_dir = _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 文件 Handler — 详细日志，带轮转
    file_handler = RotatingFileHandler(
        log_dir / "naga-backend.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    # 控制台 Handler — 简洁输出
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    # 配置 root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # 抑制第三方库噪音
    for name in ["httpcore", "httpx", "urllib3", "asyncio"]:
        logging.getLogger(name).setLevel(logging.WARNING)

    # OpenClaw 专用日志文件
    openclaw_handler = RotatingFileHandler(
        log_dir / "openclaw.log",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8",
    )
    openclaw_handler.setLevel(logging.DEBUG)
    openclaw_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logging.getLogger("agentserver.openclaw").addHandler(openclaw_handler)
