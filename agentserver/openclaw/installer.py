#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 安装器
处理 OpenClaw 的安装、初始化和配置流程
"""

import os
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InstallMethod(Enum):
    """安装方式"""
    NPM = "npm"
    SCRIPT = "script"
    SOURCE = "source"
    UNKNOWN = "unknown"


class InstallStatus(Enum):
    """安装状态"""
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    INSTALLING = "installing"
    FAILED = "failed"
    NEEDS_SETUP = "needs_setup"


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    status: InstallStatus
    message: str
    version: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
            "version": self.version,
            "details": self.details
        }


class OpenClawInstaller:
    """
    OpenClaw 安装器

    负责检测、安装和初始化 OpenClaw
    打包环境下通过 EmbeddedRuntime 获取路径和环境变量。
    """

    OPENCLAW_DIR = Path.home() / ".openclaw"
    OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"

    def _get_runtime(self):
        """获取 EmbeddedRuntime 实例"""
        from .embedded_runtime import get_embedded_runtime
        return get_embedded_runtime()

    # 默认配置模板（使用免费的 GLM 模型作为兜底）
    DEFAULT_CONFIG_TEMPLATE = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": "zai/glm-4.7"
                },
                "models": {
                    "zai/glm-4.7": {
                        "alias": "GLM"
                    }
                },
                "workspace": str(Path.home() / ".openclaw" / "workspace"),
                "compaction": {
                    "mode": "safeguard"
                },
                "maxConcurrent": 4
            }
        },
        "tools": {
            "allow": ["*"]
        },
        "hooks": {
            "enabled": True,
            "token": ""  # 将在初始化时生成
        },
        "gateway": {
            "port": 18789,
            "mode": "local",
            "bind": "loopback",
            "auth": {
                "mode": "token",
                "token": ""  # 将在初始化时生成
            }
        }
    }

    @staticmethod
    def build_config_from_naga() -> Dict[str, Any]:
        """从 NagaAgent config.api 构建 OpenClaw 配置"""
        import json
        import secrets
        from system.config import config

        token = secrets.token_hex(24)
        api = config.api
        workspace = str(Path.home() / ".openclaw" / "workspace")

        return {
            "meta": {
                "lastTouchedVersion": "naga-generated",
                "lastTouchedAt": "",
            },
            "env": {"shellEnv": {"enabled": False}},
            "models": {
                "providers": {
                    "naga-provider": {
                        "baseUrl": api.base_url,
                        "apiKey": api.api_key,
                        "auth": "api-key",
                        "api": "openai-completions",
                        "headers": {},
                        "authHeader": False,
                        "models": [{
                            "id": api.model,
                            "name": api.model,
                            "api": "openai-completions",
                            "reasoning": False,
                            "input": ["text"],
                            "cost": {"input": 1, "output": 1, "cacheRead": 1, "cacheWrite": 1},
                            "contextWindow": 128000,
                            "maxTokens": api.max_tokens,
                            "compat": {"maxTokensField": "max_tokens"},
                        }],
                    }
                }
            },
            "agents": {
                "defaults": {
                    "model": {"primary": f"naga-provider/{api.model}"},
                    "models": {f"naga-provider/{api.model}": {"alias": "NAGA"}},
                    "workspace": workspace,
                    "compaction": {"mode": "safeguard"},
                    "maxConcurrent": 4,
                    "subagents": {"maxConcurrent": 8},
                }
            },
            "hooks": {"enabled": True, "path": "/hooks", "token": token},
            "gateway": {
                "port": 18789,
                "mode": "local",
                "bind": "loopback",
                "auth": {"mode": "token", "token": token},
            },
            "skills": {"install": {"nodeManager": "npm"}},
        }

    def __init__(self):
        self._install_status = InstallStatus.NOT_INSTALLED

    # ============ 检测方法 ============

    def check_installation(self) -> Tuple[InstallStatus, Optional[str]]:
        """
        检查 OpenClaw 安装状态

        Returns:
            (安装状态, 版本号)
        """
        runtime = self._get_runtime()

        # 1. 检查命令是否可用
        openclaw_exe = runtime.openclaw_path
        if not openclaw_exe:
            return InstallStatus.NOT_INSTALLED, None

        # 2. 获取版本
        try:
            result = subprocess.run(
                [openclaw_exe, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=runtime.env,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                # 3. 检查配置是否完成
                if self.OPENCLAW_CONFIG.exists():
                    return InstallStatus.INSTALLED, version
                else:
                    return InstallStatus.NEEDS_SETUP, version
        except Exception as e:
            logger.warning(f"检查 OpenClaw 版本失败: {e}")

        return InstallStatus.NOT_INSTALLED, None

    def check_node_version(self) -> Tuple[bool, Optional[str]]:
        """
        检查 Node.js 版本（需要 Node 22+）

        Returns:
            (是否满足要求, 版本号)
        """
        runtime = self._get_runtime()
        return runtime.get_node_version()

    def check_npm_available(self) -> bool:
        """检查 npm 是否可用"""
        runtime = self._get_runtime()
        return runtime.npm_path is not None

    # ============ 安装方法 ============

    async def install(self, method: InstallMethod = InstallMethod.NPM) -> InstallResult:
        """
        安装 OpenClaw

        Args:
            method: 安装方式

        Returns:
            InstallResult 对象
        """
        # 1. 检查是否已安装
        status, version = self.check_installation()
        if status == InstallStatus.INSTALLED:
            return InstallResult(
                success=True,
                status=InstallStatus.INSTALLED,
                message=f"OpenClaw 已安装 (v{version})",
                version=version
            )

        # 2. 检查 Node.js
        node_ok, node_version = self.check_node_version()
        if not node_ok:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"需要 Node.js 22+，当前版本: {node_version or '未安装'}",
                details={"node_version": node_version}
            )

        # 3. 执行安装
        self._install_status = InstallStatus.INSTALLING

        if method == InstallMethod.NPM:
            return await self._install_via_npm()
        elif method == InstallMethod.SCRIPT:
            return await self._install_via_script()
        else:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"不支持的安装方式: {method.value}"
            )

    async def _install_via_npm(self, retry_with_sharp_fix: bool = False) -> InstallResult:
        """通过 npm 安装

        Args:
            retry_with_sharp_fix: 是否使用 SHARP_IGNORE_GLOBAL_LIBVIPS=1 环境变量重试
        """
        runtime = self._get_runtime()

        # 打包环境下 OpenClaw 已内嵌，无需 npm install
        if runtime.is_packaged:
            if runtime.openclaw_path:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="打包环境：OpenClaw 已内嵌",
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="打包环境：内嵌 OpenClaw 不可用",
                )

        try:
            logger.info("通过 npm 安装 OpenClaw...")

            # 构建环境变量
            env = runtime.env
            if retry_with_sharp_fix:
                env["SHARP_IGNORE_GLOBAL_LIBVIPS"] = "1"
                logger.info("使用 SHARP_IGNORE_GLOBAL_LIBVIPS=1 重试安装...")

            npm_exe = runtime.npm_path or "npm"

            process = await asyncio.create_subprocess_exec(
                npm_exe, "install", "-g", "openclaw@latest",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300  # 5 分钟超时
            )

            if process.returncode == 0:
                # 验证安装
                status, version = self.check_installation()
                if status in [InstallStatus.INSTALLED, InstallStatus.NEEDS_SETUP]:
                    self._install_status = status
                    return InstallResult(
                        success=True,
                        status=status,
                        message=f"OpenClaw 安装成功 (v{version})",
                        version=version
                    )

            # 检查是否是 sharp 模块错误，如果是则重试
            error_msg = stderr.decode() if stderr else ""
            if not retry_with_sharp_fix and "sharp" in error_msg.lower():
                logger.warning("检测到 sharp 模块错误，尝试使用环境变量修复...")
                return await self._install_via_npm(retry_with_sharp_fix=True)

            # 安装失败
            self._install_status = InstallStatus.FAILED
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"npm 安装失败: {error_msg[:200]}",
                details={"stderr": error_msg}
            )

        except asyncio.TimeoutError:
            self._install_status = InstallStatus.FAILED
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message="安装超时（5分钟）"
            )
        except Exception as e:
            self._install_status = InstallStatus.FAILED
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装异常: {str(e)}"
            )

    async def _install_via_script(self) -> InstallResult:
        """通过官方脚本安装"""
        try:
            logger.info("通过官方脚本安装 OpenClaw...")

            # 下载并运行脚本
            process = await asyncio.create_subprocess_shell(
                "curl -fsSL https://openclaw.ai/install.sh | bash",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300
            )

            if process.returncode == 0:
                status, version = self.check_installation()
                if status in [InstallStatus.INSTALLED, InstallStatus.NEEDS_SETUP]:
                    self._install_status = status
                    return InstallResult(
                        success=True,
                        status=status,
                        message=f"OpenClaw 安装成功 (v{version})",
                        version=version
                    )

            self._install_status = InstallStatus.FAILED
            error_msg = stderr.decode() if stderr else "未知错误"
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"脚本安装失败: {error_msg[:200]}"
            )

        except Exception as e:
            self._install_status = InstallStatus.FAILED
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装异常: {str(e)}"
            )

    # ============ 初始化方法 ============

    async def setup(self, hooks_token: Optional[str] = None, interactive: bool = False) -> InstallResult:
        """
        初始化 OpenClaw 配置

        使用 `openclaw onboard` 命令进行初始化配置

        Args:
            hooks_token: Hooks 认证 token（不传则自动生成）
            interactive: 是否交互模式（默认非交互）

        Returns:
            InstallResult 对象
        """
        # 检查是否已安装
        status, version = self.check_installation()
        if status == InstallStatus.NOT_INSTALLED:
            return InstallResult(
                success=False,
                status=InstallStatus.NOT_INSTALLED,
                message="OpenClaw 未安装，请先安装"
            )

        try:
            # 运行 onboard 命令（官方推荐的初始化方式）
            logger.info("运行 OpenClaw onboard...")

            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            # 构建命令参数
            cmd = [openclaw_exe, "onboard"]
            if not interactive:
                cmd.append("--install-daemon")  # 非交互模式，自动安装守护进程

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL if not interactive else None,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120  # 2 分钟超时
            )

            # 配置 hooks token
            if hooks_token and self.OPENCLAW_CONFIG.exists():
                from .config_manager import OpenClawConfigManager
                config_manager = OpenClawConfigManager()
                config_manager.set_hooks_token(hooks_token)
                config_manager.set_hooks_enabled(True)

            # 检查最终状态
            final_status, final_version = self.check_installation()
            if final_status == InstallStatus.INSTALLED:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="OpenClaw 初始化完成",
                    version=final_version,
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=final_status,
                    message="初始化后配置文件未生成，请检查",
                    version=version
                )

        except asyncio.TimeoutError:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message="初始化超时（2分钟）"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"初始化失败: {str(e)}"
            )

    # ============ Gateway 管理 ============

    async def install_gateway_service(self) -> InstallResult:
        """安装 Gateway 为系统服务"""
        status, version = self.check_installation()
        if status != InstallStatus.INSTALLED:
            return InstallResult(
                success=False,
                status=status,
                message="OpenClaw 未正确安装或配置"
            )

        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "gateway", "install",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60
            )

            if process.returncode == 0:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 服务安装成功",
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"Gateway 服务安装失败: {stderr.decode() if stderr else '未知错误'}"
                )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装 Gateway 服务失败: {str(e)}"
            )

    async def start_gateway(self, background: bool = True) -> InstallResult:
        """
        启动 Gateway

        使用 `openclaw gateway start` 命令

        Args:
            background: 是否后台运行

        Returns:
            InstallResult 对象
        """
        status, version = self.check_installation()
        if status != InstallStatus.INSTALLED:
            return InstallResult(
                success=False,
                status=status,
                message="OpenClaw 未正确安装或配置"
            )

        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            if background:
                # 使用 gateway start 命令启动
                process = await asyncio.create_subprocess_exec(
                    openclaw_exe, "gateway", "start",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=runtime.env,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=30
                )

                # 等待一下确保启动
                await asyncio.sleep(2)

                # 检查是否启动成功
                from .detector import detect_openclaw
                oc_status = detect_openclaw(check_connection=True)

                if oc_status.gateway_reachable:
                    return InstallResult(
                        success=True,
                        status=InstallStatus.INSTALLED,
                        message="Gateway 启动成功",
                        details={"gateway_url": oc_status.gateway_url}
                    )
                else:
                    # 可能需要先安装服务
                    return InstallResult(
                        success=False,
                        status=InstallStatus.FAILED,
                        message="Gateway 启动后无法连接，可能需要先运行 'openclaw gateway install'"
                    )
            else:
                # 前台运行（用于调试）
                process = await asyncio.create_subprocess_exec(
                    openclaw_exe, "gateway",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=runtime.env,
                )
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 已启动（前台模式）"
                )

        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"启动 Gateway 失败: {str(e)}"
            )

    async def stop_gateway(self) -> InstallResult:
        """停止 Gateway"""
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "gateway", "stop",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            return InstallResult(
                success=process.returncode == 0,
                status=InstallStatus.INSTALLED if process.returncode == 0 else InstallStatus.FAILED,
                message="Gateway 已停止" if process.returncode == 0 else f"停止失败: {stderr.decode() if stderr else '未知错误'}"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"停止 Gateway 失败: {str(e)}"
            )

    async def restart_gateway(self) -> InstallResult:
        """重启 Gateway"""
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "gateway", "restart",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            # 等待重启完成
            await asyncio.sleep(2)

            # 验证连接
            from .detector import detect_openclaw
            oc_status = detect_openclaw(check_connection=True)

            if oc_status.gateway_reachable:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 重启成功",
                    details={"gateway_url": oc_status.gateway_url}
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="Gateway 重启后无法连接"
                )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"重启 Gateway 失败: {str(e)}"
            )

    async def check_gateway_status(self) -> Dict[str, Any]:
        """检查 Gateway 状态"""
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "gateway", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )

            return {
                "success": process.returncode == 0,
                "running": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "running": False,
                "error": str(e)
            }

    async def run_doctor(self) -> Dict[str, Any]:
        """
        运行 OpenClaw 健康检查

        使用 `openclaw doctor` 命令检查系统状态
        """
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "doctor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            return {
                "success": process.returncode == 0,
                "healthy": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "healthy": False,
                "error": str(e)
            }

    async def check_status(self) -> Dict[str, Any]:
        """
        检查 OpenClaw 运行状态

        使用 `openclaw status` 命令
        """
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )

            return {
                "success": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ============ Skills 管理 ============

    async def install_skill(self, skill_slug: str) -> InstallResult:
        """
        安装 Skill

        Args:
            skill_slug: Skill 标识符

        Returns:
            InstallResult 对象
        """
        try:
            logger.info(f"安装 Skill: {skill_slug}")

            runtime = self._get_runtime()
            clawhub_exe = runtime.clawhub_path or "clawhub"

            process = await asyncio.create_subprocess_exec(
                clawhub_exe, "install", skill_slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120
            )

            if process.returncode == 0:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message=f"Skill '{skill_slug}' 安装成功",
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"Skill 安装失败: {stderr.decode() if stderr else '未知错误'}"
                )

        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装 Skill 异常: {str(e)}"
            )

    async def list_skills(self) -> List[Dict[str, Any]]:
        """列出已安装的 Skills"""
        try:
            runtime = self._get_runtime()
            openclaw_exe = runtime.openclaw_path or "openclaw"

            process = await asyncio.create_subprocess_exec(
                openclaw_exe, "skills", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            if process.returncode == 0:
                # 解析输出（简单解析）
                output = stdout.decode() if stdout else ""
                return [{"raw_output": output}]
            else:
                return []

        except Exception as e:
            logger.error(f"列出 Skills 失败: {e}")
            return []


# 全局安装器实例
_installer: Optional[OpenClawInstaller] = None


def get_openclaw_installer() -> OpenClawInstaller:
    """获取全局安装器实例"""
    global _installer
    if _installer is None:
        _installer = OpenClawInstaller()
    return _installer
