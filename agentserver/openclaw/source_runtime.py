#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 源码运行时管理器

开发环境下，当用户未全局安装 OpenClaw 时，自动回退到 submodule 源码运行。
要求：Node.js >= 22 + pnpm 可用。
"""

import os
import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class SourceRuntime:
    """
    源码运行时管理器

    从项目根目录下的 openclaw/ submodule 运行 OpenClaw。
    """

    def __init__(self) -> None:
        self._gateway_process: Optional[asyncio.subprocess.Process] = None
        self._source_root: Optional[Path] = self._resolve_source_root()
        self._built: bool = False

    # ============ 路径推导 ============

    @staticmethod
    def _resolve_source_root() -> Optional[Path]:
        """
        从当前文件推导到项目根目录下的 openclaw/ submodule。

        目录结构：
          项目根/
            agentserver/
              openclaw/
                source_runtime.py  <- __file__
            openclaw/              <- submodule
              openclaw.mjs
              package.json
        """
        # __file__ -> agentserver/openclaw/source_runtime.py
        # 向上 3 级到项目根目录
        project_root = Path(__file__).resolve().parent.parent.parent
        source_root = project_root / "openclaw"
        if source_root.exists() and (source_root / "package.json").exists():
            return source_root
        return None

    @property
    def source_root(self) -> Optional[Path]:
        return self._source_root

    # ============ 可用性检测 ============

    @property
    def is_available(self) -> bool:
        """检查源码模式是否可用：submodule 存在 + Node.js >= 22 + pnpm 可用"""
        if not self._source_root or not (self._source_root / "openclaw.mjs").exists():
            return False
        node_ok, _ = self._check_node_version()
        if not node_ok:
            return False
        if not self._check_pnpm_available():
            return False
        return True

    def _check_node_version(self) -> tuple[bool, Optional[str]]:
        """检查 Node.js 版本 >= 22"""
        node = shutil.which("node")
        if not node:
            return False, None
        try:
            result = subprocess.run(
                [node, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                version_str = result.stdout.strip().lstrip("v")
                major = int(version_str.split(".")[0])
                return major >= 22, version_str
        except Exception as e:
            logger.warning(f"检查 Node.js 版本失败: {e}")
        return False, None

    def _check_pnpm_available(self) -> bool:
        """检查 pnpm 是否可用"""
        return shutil.which("pnpm") is not None

    # ============ 命令与环境 ============

    @property
    def openclaw_cmd(self) -> Optional[List[str]]:
        """返回源码模式下的 openclaw 命令：[node_path, openclaw.mjs]"""
        if not self._source_root:
            return None
        node = shutil.which("node")
        if not node:
            return None
        mjs = self._source_root / "openclaw.mjs"
        if not mjs.exists():
            return None
        return [node, str(mjs)]

    @property
    def env(self) -> Dict[str, str]:
        """构建子进程环境变量，确保 submodule 的 node_modules/.bin 在 PATH 中"""
        env = os.environ.copy()
        if self._source_root:
            bin_dir = str(self._source_root / "node_modules" / ".bin")
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    # ============ 构建 ============

    async def ensure_built(self) -> bool:
        """
        确保 submodule 已构建。
        检查 openclaw/dist/entry.js 是否存在，不存在则执行 pnpm install && pnpm build。
        """
        if self._built:
            return True
        if not self._source_root:
            return False

        # 检查构建产物是否已存在
        dist_entry = self._source_root / "dist" / "entry.js"
        if dist_entry.exists():
            self._built = True
            logger.info("源码模式：构建产物已存在，跳过构建")
            return True

        pnpm = shutil.which("pnpm")
        if not pnpm:
            logger.error("源码模式：pnpm 不可用，无法构建")
            return False

        try:
            logger.info("源码模式：执行 pnpm install ...")
            proc = await asyncio.create_subprocess_exec(
                pnpm, "install",
                cwd=str(self._source_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0:
                logger.error(f"pnpm install 失败: {stderr.decode()[:500]}")
                return False

            logger.info("源码模式：执行 pnpm build ...")
            proc = await asyncio.create_subprocess_exec(
                pnpm, "build",
                cwd=str(self._source_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0:
                logger.error(f"pnpm build 失败: {stderr.decode()[:500]}")
                return False

            self._built = True
            logger.info("源码模式：构建完成")
            return True

        except asyncio.TimeoutError:
            logger.error("源码模式：构建超时")
            return False
        except Exception as e:
            logger.error(f"源码模式：构建失败: {e}")
            return False

    # ============ Gateway 进程管理 ============

    async def start_gateway(self) -> bool:
        """通过 node openclaw.mjs gateway 启动 Gateway 进程"""
        if self._gateway_process is not None:
            logger.info("源码模式：Gateway 进程已在运行")
            return True

        cmd = self.openclaw_cmd
        if not cmd:
            logger.error("源码模式：无法构建 openclaw 命令")
            return False

        try:
            logger.info(f"源码模式：启动 Gateway: {' '.join(cmd)} gateway")
            self._gateway_process = await asyncio.create_subprocess_exec(
                *cmd, "gateway",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._source_root),
                env=self.env,
            )
            # 等待 Gateway 就绪
            await asyncio.sleep(3)

            if self._gateway_process.returncode is not None:
                stderr = await self._gateway_process.stderr.read() if self._gateway_process.stderr else b""
                logger.error(
                    f"源码模式：Gateway 进程异常退出 (code={self._gateway_process.returncode}): "
                    f"{stderr.decode()[:500]}"
                )
                self._gateway_process = None
                return False

            logger.info("源码模式：Gateway 已启动")
            return True
        except Exception as e:
            logger.error(f"源码模式：启动 Gateway 失败: {e}")
            self._gateway_process = None
            return False

    async def stop_gateway(self) -> None:
        """停止 Gateway 进程"""
        if self._gateway_process is None:
            return
        try:
            logger.info("源码模式：正在停止 Gateway...")
            self._gateway_process.terminate()
            try:
                await asyncio.wait_for(self._gateway_process.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("源码模式：Gateway 进程未在 10 秒内退出，强制终止")
                self._gateway_process.kill()
                await self._gateway_process.wait()
            logger.info("源码模式：Gateway 已停止")
        except Exception as e:
            logger.error(f"源码模式：停止 Gateway 失败: {e}")
        finally:
            self._gateway_process = None

    @property
    def gateway_running(self) -> bool:
        """Gateway 进程是否在运行"""
        return self._gateway_process is not None and self._gateway_process.returncode is None

    # ============ Onboard / 配置 ============

    async def ensure_onboarded(self) -> bool:
        """
        确保 OpenClaw 已完成配置。
        委托给 llm_config_bridge 自动生成配置，不再调用 openclaw onboard。
        """
        from .llm_config_bridge import ensure_openclaw_config, inject_naga_llm_config

        try:
            ensure_openclaw_config()
            inject_naga_llm_config()
            return True
        except Exception as e:
            logger.error(f"源码模式：自动配置失败: {e}")
            return False


# ============ 全局单例 ============

_source_runtime: Optional[SourceRuntime] = None


def get_source_runtime() -> SourceRuntime:
    """获取全局 SourceRuntime 单例"""
    global _source_runtime
    if _source_runtime is None:
        _source_runtime = SourceRuntime()
    return _source_runtime
