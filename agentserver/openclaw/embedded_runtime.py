#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 内嵌运行时管理

打包环境下使用内嵌的 Node.js + OpenClaw，开发环境下使用系统 PATH。
"""

import os
import sys
import shutil
import asyncio
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# 是否为 PyInstaller 打包环境
IS_PACKAGED: bool = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


class EmbeddedRuntime:
    """
    内嵌运行时管理器

    打包环境：从 resources/openclaw-runtime/ 加载 Node.js 和 OpenClaw
    开发环境：使用系统 PATH 中的 node / openclaw / clawhub
    """

    def __init__(self) -> None:
        self._gateway_process: Optional[asyncio.subprocess.Process] = None
        self._runtime_root: Optional[Path] = None
        self._onboarded: bool = False

        if IS_PACKAGED:
            self._runtime_root = self._resolve_runtime_root()
            if self._runtime_root and self._runtime_root.exists():
                logger.info(f"内嵌运行时目录: {self._runtime_root}")
            else:
                logger.warning(f"内嵌运行时目录不存在: {self._runtime_root}")
                self._runtime_root = None

    # ============ 路径推导 ============

    @staticmethod
    def _resolve_runtime_root() -> Path:
        """
        推导内嵌运行时根目录。

        打包后目录结构：
          resources/
            backend/
              naga-backend.exe
              _internal/          <- sys._MEIPASS
            openclaw-runtime/
              node/
              openclaw/
        """
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        # _internal -> backend -> resources -> openclaw-runtime
        return meipass.parent.parent / "openclaw-runtime"

    @property
    def is_packaged(self) -> bool:
        return IS_PACKAGED and self._runtime_root is not None

    @property
    def runtime_root(self) -> Optional[Path]:
        return self._runtime_root

    # ============ 可执行文件路径 ============

    @property
    def node_path(self) -> Optional[str]:
        """Node.js 可执行文件路径"""
        if self.is_packaged:
            assert self._runtime_root is not None
            exe = self._runtime_root / "node" / "node.exe"
            return str(exe) if exe.exists() else None
        return shutil.which("node")

    @property
    def npm_path(self) -> Optional[str]:
        """npm 可执行文件路径"""
        if self.is_packaged:
            assert self._runtime_root is not None
            cmd = self._runtime_root / "node" / "npm.cmd"
            return str(cmd) if cmd.exists() else None
        return shutil.which("npm")

    @property
    def openclaw_path(self) -> Optional[str]:
        """openclaw CLI 可执行文件路径"""
        if self.is_packaged:
            assert self._runtime_root is not None
            if platform.system() == "Windows":
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "openclaw.cmd"
            else:
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "openclaw"
            return str(cmd) if cmd.exists() else None
        return shutil.which("openclaw")

    @property
    def clawhub_path(self) -> Optional[str]:
        """clawhub CLI 可执行文件路径"""
        if self.is_packaged:
            assert self._runtime_root is not None
            if platform.system() == "Windows":
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "clawhub.cmd"
            else:
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "clawhub"
            return str(cmd) if cmd.exists() else None
        return shutil.which("clawhub")

    # ============ 环境变量 ============

    @property
    def env(self) -> Dict[str, str]:
        """构建子进程环境变量，确保内嵌 node 优先"""
        env = os.environ.copy()
        if self.is_packaged and self._runtime_root is not None:
            node_dir = str(self._runtime_root / "node")
            bin_dir = str(self._runtime_root / "openclaw" / "node_modules" / ".bin")
            # 将内嵌路径放在 PATH 最前面
            env["PATH"] = f"{node_dir}{os.pathsep}{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    # ============ Node.js 版本检测 ============

    def get_node_version(self) -> tuple[bool, Optional[str]]:
        """
        获取 Node.js 版本并检查是否满足要求 (>=22)

        Returns:
            (是否满足要求, 版本号字符串)
        """
        node = self.node_path
        if not node:
            return False, None
        try:
            result = subprocess.run(
                [node, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                env=self.env,
            )
            if result.returncode == 0:
                version_str = result.stdout.strip().lstrip("v")
                major = int(version_str.split(".")[0])
                return major >= 22, version_str
        except Exception as e:
            logger.warning(f"检查 Node.js 版本失败: {e}")
        return False, None

    # ============ Gateway 进程管理 ============

    async def start_gateway(self) -> bool:
        """
        启动内嵌 OpenClaw Gateway 进程。

        Returns:
            是否启动成功
        """
        if self._gateway_process is not None:
            logger.info("内嵌 Gateway 进程已在运行")
            return True

        openclaw = self.openclaw_path
        if not openclaw:
            logger.error("找不到 openclaw 可执行文件，无法启动 Gateway")
            return False

        try:
            logger.info(f"启动内嵌 OpenClaw Gateway: {openclaw} gateway")
            self._gateway_process = await asyncio.create_subprocess_exec(
                openclaw, "gateway",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            # 轮询等待 Gateway 就绪（替代固定 sleep(3)）
            import socket
            ready = False
            for attempt in range(15):  # 最多等 15 秒
                await asyncio.sleep(1)
                if self._gateway_process.returncode is not None:
                    break  # 进程已退出
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    if sock.connect_ex(("127.0.0.1", 18789)) == 0:
                        ready = True
                        sock.close()
                        break
                    sock.close()
                except Exception:
                    pass

            if self._gateway_process.returncode is not None:
                stderr = await self._gateway_process.stderr.read() if self._gateway_process.stderr else b""
                logger.error(f"Gateway 进程异常退出 (code={self._gateway_process.returncode}): {stderr.decode()[:500]}")
                self._gateway_process = None
                return False

            if ready:
                logger.info("内嵌 OpenClaw Gateway 已启动（端口就绪）")
            else:
                logger.warning("Gateway 进程运行中但端口未就绪，继续运行...")
            return self._gateway_process is not None and self._gateway_process.returncode is None
        except Exception as e:
            logger.error(f"启动内嵌 Gateway 失败: {e}")
            self._gateway_process = None
            return False

    async def stop_gateway(self) -> None:
        """停止内嵌 Gateway 进程"""
        if self._gateway_process is None:
            return
        try:
            logger.info("正在停止内嵌 OpenClaw Gateway...")
            self._gateway_process.terminate()
            try:
                await asyncio.wait_for(self._gateway_process.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("Gateway 进程未在 10 秒内退出，强制终止")
                self._gateway_process.kill()
                await self._gateway_process.wait()
            logger.info("内嵌 OpenClaw Gateway 已停止")
        except Exception as e:
            logger.error(f"停止 Gateway 失败: {e}")
        finally:
            self._gateway_process = None

    @property
    def gateway_running(self) -> bool:
        """Gateway 进程是否在运行"""
        return self._gateway_process is not None and self._gateway_process.returncode is None

    # ============ Onboard 初始化 ============

    def _generate_fallback_config(self) -> bool:
        """onboard 失败时的兜底：直接生成 ~/.openclaw/openclaw.json"""
        import json

        config_dir = Path.home() / ".openclaw"
        config_file = config_dir / "openclaw.json"
        workspace_dir = config_dir / "workspace"

        try:
            config_dir.mkdir(parents=True, exist_ok=True)
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # 从 installer 的 build_config_from_naga() 获取配置，避免重复代码
            from .installer import OpenClawInstaller
            openclaw_config = OpenClawInstaller.build_config_from_naga()

            config_file.write_text(
                json.dumps(openclaw_config, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"Fallback 配置已生成: {config_file}")
            return True
        except Exception as e:
            logger.error(f"生成 fallback 配置失败: {e}")
            return False

    async def ensure_onboarded(self) -> bool:
        """
        确保 OpenClaw 已完成 onboard 初始化。
        如果 ~/.openclaw/openclaw.json 不存在则自动执行 `openclaw onboard`。

        Returns:
            是否已完成初始化
        """
        config_file = Path.home() / ".openclaw" / "openclaw.json"
        if config_file.exists():
            self._onboarded = True
            return True

        openclaw = self.openclaw_path
        if not openclaw:
            logger.warning("找不到 openclaw，无法执行 onboard，尝试 fallback 配置生成")
            return self._generate_fallback_config()

        try:
            logger.info("首次运行，执行 openclaw onboard 初始化...")
            process = await asyncio.create_subprocess_exec(
                openclaw, "onboard", "--install-daemon",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=self.env,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)

            if config_file.exists():
                self._onboarded = True
                logger.info("OpenClaw onboard 初始化完成")
                return True
            else:
                logger.warning(f"onboard 执行后配置文件未生成: {stderr.decode()[:300]}")
        except asyncio.TimeoutError:
            logger.error("openclaw onboard 超时")
        except Exception as e:
            logger.error(f"openclaw onboard 失败: {e}")

        # onboard 失败，尝试 fallback 直接生成配置
        if not config_file.exists():
            logger.warning("openclaw onboard 未生成配置，使用 fallback 直接生成...")
            if self._generate_fallback_config():
                self._onboarded = True
                return True
        return False


# ============ 全局单例 ============

_runtime: Optional[EmbeddedRuntime] = None


def get_embedded_runtime() -> EmbeddedRuntime:
    """获取全局 EmbeddedRuntime 单例"""
    global _runtime
    if _runtime is None:
        _runtime = EmbeddedRuntime()
    return _runtime
