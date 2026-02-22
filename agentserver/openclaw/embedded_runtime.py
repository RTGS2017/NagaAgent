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
import socket
import subprocess
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)
OPENCLAW_NPM_VERSION = "2026.2.17"

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

    @property
    def openclaw_installed(self) -> bool:
        """打包环境下 openclaw 是否已安装到运行时目录"""
        if not self.is_packaged or not self._runtime_root:
            return False
        return self.openclaw_path is not None

    def _get_install_state_file(self) -> Optional[Path]:
        """获取安装状态缓存文件路径"""
        if not self._runtime_root:
            return None
        return self._runtime_root / ".openclaw_install_state"

    def _read_install_state(self) -> Dict[str, Any]:
        """读取安装状态"""
        state_file = self._get_install_state_file()
        if not state_file or not state_file.exists():
            return {}
        try:
            import json

            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取安装状态失败: {e}")
            return {}

    def _write_install_state(self, auto_installed: bool) -> None:
        """写入安装状态"""
        state_file = self._get_install_state_file()
        if not state_file:
            return
        try:
            import json
            from datetime import datetime

            state = {
                "auto_installed": auto_installed,
                "install_time": datetime.now().isoformat(),
            }
            state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            logger.debug(f"已写入安装状态: auto_installed={auto_installed}")
        except Exception as e:
            logger.warning(f"写入安装状态失败: {e}")

    @property
    def is_auto_installed(self) -> bool:
        """是否是自动安装的 OpenClaw"""
        state = self._read_install_state()
        return state.get("auto_installed", False)

    @property
    def has_global_install(self) -> bool:
        """检测 PATH 中是否有全局安装的 openclaw 命令"""
        return shutil.which("openclaw") is not None

    @property
    def runtime_mode(self) -> str:
        """
        返回当前运行时模式：
        - "packaged": 打包环境内嵌运行时
        - "global": 全局安装的 openclaw
        - "unavailable": 不可用
        """
        if self.is_packaged:
            return "packaged"
        if shutil.which("openclaw"):
            return "global"
        return "unavailable"

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
            # npm install openclaw 后的路径：node_modules/.bin/openclaw
            if platform.system() == "Windows":
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "openclaw.cmd"
            else:
                cmd = self._runtime_root / "openclaw" / "node_modules" / ".bin" / "openclaw"
            return str(cmd) if cmd.exists() else None
        # 开发环境：检查全局安装
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

    # ============ 运行时安装 ============

    async def install_openclaw(self) -> bool:
        """在打包环境下用内嵌 npm 安装 openclaw"""
        npm = self.npm_path
        node = self.node_path
        if not npm or not node:
            logger.error("内嵌 Node.js/npm 不可用，无法安装 OpenClaw")
            return False

        runtime_root = self._runtime_root
        if runtime_root is None:
            logger.error("内嵌运行时目录不可用，无法安装 OpenClaw")
            return False

        install_dir = runtime_root / "openclaw"
        install_dir.mkdir(parents=True, exist_ok=True)

        logger.info("首次启动：正在安装 OpenClaw，请稍候...")
        try:
            proc = await asyncio.create_subprocess_exec(
                npm,
                "install",
                f"openclaw@{OPENCLAW_NPM_VERSION}",
                cwd=str(install_dir),
                env=self.env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            logger.error("npm install openclaw 超时（300秒）")
            return False
        except Exception as e:
            logger.error(f"npm install openclaw 执行异常: {e}")
            return False

        if proc.returncode != 0:
            logger.error(f"npm install openclaw 失败: {stderr.decode()[:500]}")
            return False

        # 验证安装
        if self.openclaw_path:
            logger.info(f"OpenClaw 安装成功: {self.openclaw_path}")
            self._write_install_state(auto_installed=True)
            return True
        logger.error("npm install 执行成功但 openclaw 未找到")
        return False

    async def uninstall_openclaw(self) -> bool:
        """
        卸载 OpenClaw（仅当是自动安装时）

        删除内容：
        - openclaw-runtime/openclaw/ 目录
        - ~/.openclaw/ 配置目录
        - .openclaw_install_state 缓存文件

        Returns:
            是否执行了卸载
        """
        if not self.is_auto_installed:
            logger.info("OpenClaw 不是自动安装的，跳过卸载")
            return False

        try:
            # 1. 停止 Gateway
            if self._gateway_process:
                logger.info("停止 Gateway 进程...")
                await self.stop_gateway()

            # 1.1 停止可能由其他会话/进程启动的 Gateway
            if self.has_gateway_process() or self.is_gateway_port_in_use():
                logger.info("检测到 Gateway 仍在运行，尝试执行 openclaw gateway stop...")
                await self._stop_gateway_via_cli()
                await asyncio.sleep(1)
                if self.has_gateway_process() or self.is_gateway_port_in_use():
                    logger.warning("Gateway 可能仍在运行，将继续执行清理")

            # 2. 删除 openclaw 目录
            if self._runtime_root:
                openclaw_dir = self._runtime_root / "openclaw"
                if openclaw_dir.exists():
                    import shutil

                    shutil.rmtree(openclaw_dir)
                    logger.info(f"已删除 OpenClaw 目录: {openclaw_dir}")

            # 3. 删除配置目录
            config_dir = Path.home() / ".openclaw"
            if config_dir.exists():
                import shutil

                shutil.rmtree(config_dir)
                logger.info(f"已删除配置目录: {config_dir}")

            # 4. 删除缓存文件
            state_file = self._get_install_state_file()
            if state_file and state_file.exists():
                state_file.unlink()
                logger.info("已删除安装状态缓存")

            logger.info("OpenClaw 卸载完成")
            return True

        except Exception as e:
            logger.error(f"卸载 OpenClaw 失败: {e}")
            return False

    # ============ Gateway 进程管理 ============

    async def _stop_gateway_via_cli(self, max_retries: int = 3, retry_interval_seconds: float = 1.0) -> bool:
        """通过 openclaw CLI 停止 Gateway（用于兜底，支持重试）。"""
        openclaw: Optional[str] = self.openclaw_path
        if not openclaw:
            logger.warning("找不到 openclaw 可执行文件，无法执行 gateway stop")
            return False

        attempts: int = max(1, max_retries)
        for attempt in range(1, attempts + 1):
            try:
                process = await asyncio.create_subprocess_exec(
                    openclaw,
                    "gateway",
                    "stop",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.env,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)

                if process.returncode == 0:
                    logger.info(f"已通过 openclaw gateway stop 停止 Gateway（第 {attempt} 次）")
                    return True

                err_text = stderr.decode(errors="ignore") if stderr else ""
                out_text = stdout.decode(errors="ignore") if stdout else ""
                logger.warning(
                    f"openclaw gateway stop 返回非0({process.returncode})，"
                    f"第 {attempt}/{attempts} 次，stdout={out_text[:200]} stderr={err_text[:200]}"
                )
            except asyncio.TimeoutError:
                logger.warning(f"openclaw gateway stop 执行超时（第 {attempt}/{attempts} 次）")
            except Exception as e:
                logger.warning(f"执行 openclaw gateway stop 失败（第 {attempt}/{attempts} 次）: {e}")

            if attempt < attempts:
                await asyncio.sleep(max(0.0, retry_interval_seconds))

        return False

    def has_gateway_process(self) -> bool:
        """检测系统中是否存在 OpenClaw Gateway 相关进程。"""
        try:
            import psutil
        except Exception as e:
            logger.debug(f"psutil 不可用，跳过 Gateway 进程检测: {e}")
            return False

        current_pid: int = os.getpid()
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                pid: int = int(proc.info.get("pid") or 0)
                if pid == current_pid:
                    continue

                name: str = str(proc.info.get("name") or "").lower()
                raw_cmdline = proc.info.get("cmdline") or []
                if isinstance(raw_cmdline, list):
                    cmdline_text = " ".join(str(item) for item in raw_cmdline).lower()
                else:
                    cmdline_text = str(raw_cmdline).lower()

                # openclaw gateway / node ... openclaw ... gateway
                if "openclaw" in cmdline_text and "gateway" in cmdline_text:
                    return True
                if name.startswith("openclaw") and "gateway" in cmdline_text:
                    return True
                if name.startswith("node") and "openclaw" in cmdline_text and "gateway" in cmdline_text:
                    return True
            except Exception:
                continue

        return False

    def is_gateway_port_in_use(self, host: str = "127.0.0.1", port: int = 18789) -> bool:
        """检测 Gateway 默认端口是否被占用。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex((host, port)) == 0
        except Exception:
            return False

    def _build_gateway_cmd(self) -> Optional[List[str]]:
        """构建启动 Gateway 的命令列表"""
        openclaw = self.openclaw_path
        if not openclaw:
            return None

        return [openclaw, "gateway"]

    async def start_gateway(self) -> bool:
        """
        启动 OpenClaw Gateway 进程。

        Returns:
            是否启动成功
        """
        if self._gateway_process is not None:
            logger.info("Gateway 进程已在运行")
            return True

        cmd = self._build_gateway_cmd()
        if not cmd:
            logger.error("找不到 openclaw 可执行文件，无法启动 Gateway")
            return False

        try:
            logger.info(f"启动 OpenClaw Gateway: {' '.join(cmd)}")
            self._gateway_process = await asyncio.create_subprocess_exec(
                *cmd,
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
            logger.error(f"启动 Gateway 失败: {e}")
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
        确保 OpenClaw 已完成初始化配置。

        打包环境和源码模式下：使用 llm_config_bridge 自动生成配置。
        全局安装：使用 openclaw onboard 命令。

        Returns:
            是否已完成初始化
        """
        config_file = Path.home() / ".openclaw" / "openclaw.json"
        if config_file.exists():
            try:
                from .llm_config_bridge import (
                    ensure_hooks_allow_request_session_key,
                    ensure_gateway_local_mode,
                    ensure_hooks_path,
                )

                ensure_hooks_allow_request_session_key(auto_create=False)
                ensure_gateway_local_mode(auto_create=False)
                ensure_hooks_path(auto_create=False)
            except Exception as e:
                logger.warning(f"配置兼容补丁执行失败（可忽略）: {e}")
            self._onboarded = True
            return True

        # 打包环境：自动生成配置
        if self.is_packaged:
            from .llm_config_bridge import (
                ensure_openclaw_config,
                inject_naga_llm_config,
                ensure_hooks_allow_request_session_key,
                ensure_gateway_local_mode,
            )

            try:
                ensure_openclaw_config()
                inject_naga_llm_config()
                ensure_hooks_allow_request_session_key(auto_create=False)
                ensure_gateway_local_mode(auto_create=False)
                self._onboarded = True
                logger.info("已自动生成 OpenClaw 配置")
                return True
            except Exception as e:
                logger.error(f"自动生成配置失败: {e}")
                return False

        # 全局安装：使用 openclaw onboard
        openclaw = self.openclaw_path
        if not openclaw:
            logger.warning("找不到 openclaw，无法执行 onboard，尝试 fallback 配置生成")
            return self._generate_fallback_config()

        try:
            logger.info("首次运行，执行 openclaw onboard 初始化...")
            process = await asyncio.create_subprocess_exec(
                openclaw,
                "onboard",
                "--install-daemon",
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
