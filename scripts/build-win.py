#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent Windows 完整构建脚本

流程：
  1. 环境检查（Python, Node.js, npm）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 运行时（下载 Node.js 便携版 + 预装 OpenClaw）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 输出汇总

默认在构建阶段预装 OpenClaw，用户安装后首次启动可直接使用。

用法:
  python scripts/build-win.py            # 完整构建
  python scripts/build-win.py --skip-openclaw   # 跳过 OpenClaw 运行时准备
  python scripts/build-win.py --backend-only    # 仅编译后端
"""

import os
import sys
import shutil
import subprocess
import argparse
import time
import zipfile
import urllib.request
from pathlib import Path
from typing import Optional

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIST_DIR = FRONTEND_DIR / "backend-dist"
RUNTIME_DIR = BACKEND_DIST_DIR / "openclaw-runtime"
NODE_RUNTIME_DIR = RUNTIME_DIR / "node"
OPENCLAW_RUNTIME_DIR = RUNTIME_DIR / "openclaw"
SPEC_FILE = PROJECT_ROOT / "naga-backend.spec"

# 最低版本要求
MIN_NODE_MAJOR = 22
MIN_PYTHON = (3, 11)

# OpenClaw 运行时版本
NODE_VERSION = "22.13.1"
NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
CACHE_DIR = PROJECT_ROOT / ".cache"


def log(msg: str) -> None:
    print(f"[build-win] {msg}")


def log_step(step: int, total: int, title: str) -> None:
    print()
    print(f"{'=' * 50}")
    print(f"  Step {step}/{total}: {title}")
    print(f"{'=' * 50}")


def run(
    cmd: list[str],
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """执行命令并实时输出。自动通过 shutil.which 解析 .cmd/.bat（Windows）"""
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        check=check,
    )


def get_cmd_version(cmd: str, args: list[str] | None = None) -> Optional[str]:
    """获取命令版本号，失败返回 None。通过 shutil.which 解析 .cmd/.bat"""
    resolved = shutil.which(cmd)
    if not resolved:
        return None
    try:
        result = subprocess.run(
            [resolved, *(args or ["--version"])],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ============ Step 1: 环境检查 ============


def check_environment() -> bool:
    """检查构建所需的工具是否就绪"""
    ok = True

    if os.name != "nt":
        log("  当前系统不是 Windows  ✗  (build-win.py 仅支持 Windows 打包)")
        return False

    # Python 版本
    py_ver = sys.version_info[:2]
    if py_ver >= MIN_PYTHON:
        log(f"  Python {sys.version.split()[0]}  ✓")
    else:
        log(f"  Python {sys.version.split()[0]}  ✗  (需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
        ok = False

    # uv
    uv_ver = get_cmd_version("uv", ["-V"])
    if uv_ver:
        log(f"  {uv_ver}  ✓")
    else:
        log("  uv 未安装  ✗  (pip install uv)")
        ok = False

    # Node.js
    node_ver = get_cmd_version("node")
    if node_ver:
        major = int(node_ver.lstrip("v").split(".")[0])
        status = "✓" if major >= MIN_NODE_MAJOR else f"✗  (需要 >= {MIN_NODE_MAJOR})"
        log(f"  Node.js {node_ver}  {status}")
        if major < MIN_NODE_MAJOR:
            ok = False
    else:
        log(f"  Node.js 未安装  ✗  (需要 >= {MIN_NODE_MAJOR})")
        ok = False

    # npm
    npm_ver = get_cmd_version("npm")
    if npm_ver:
        log(f"  npm {npm_ver}  ✓")
    else:
        log("  npm 未安装  ✗")
        ok = False

    return ok


# ============ Step 2: 同步依赖 ============


def sync_dependencies() -> None:
    """uv sync + build 依赖组"""
    run(["uv", "sync", "--group", "build"], cwd=PROJECT_ROOT)
    log("Python 依赖同步完成")


# ============ Step 3: 准备 OpenClaw 运行时 ============


def download_node_runtime() -> Path:
    """下载 Node.js 便携版 zip，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"node-v{NODE_VERSION}-win-x64.zip"
    zip_path = CACHE_DIR / zip_name

    if zip_path.exists():
        log(f"使用缓存 Node.js 包: {zip_path}")
        return zip_path

    log(f"下载 Node.js v{NODE_VERSION}: {NODE_DIST_URL}")
    urllib.request.urlretrieve(NODE_DIST_URL, str(zip_path))
    log(f"Node.js 下载完成: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return zip_path


def extract_node_runtime(zip_path: Path) -> None:
    """解压 Node.js 到 openclaw-runtime/node"""
    if NODE_RUNTIME_DIR.exists():
        log(f"清理旧 Node.js 运行时: {NODE_RUNTIME_DIR}")
        shutil.rmtree(NODE_RUNTIME_DIR)

    NODE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    log(f"解压 Node.js 到: {NODE_RUNTIME_DIR}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        prefix = f"node-v{NODE_VERSION}-win-x64/"
        for member in zf.infolist():
            if not member.filename.startswith(prefix):
                continue
            rel = member.filename[len(prefix) :]
            if not rel:
                continue
            target = NODE_RUNTIME_DIR / rel
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    node_exe = NODE_RUNTIME_DIR / "node.exe"
    npm_cmd = NODE_RUNTIME_DIR / "npm.cmd"
    if not node_exe.exists():
        raise FileNotFoundError(f"解压后缺少 node.exe: {node_exe}")
    if not npm_cmd.exists():
        raise FileNotFoundError(f"解压后缺少 npm.cmd: {npm_cmd}")
    log("Node.js 便携版解压完成")


def preinstall_openclaw() -> None:
    """在内嵌运行时目录中预装 OpenClaw"""
    npm_cmd = NODE_RUNTIME_DIR / "npm.cmd"
    if not npm_cmd.exists():
        raise FileNotFoundError(f"npm.cmd 不存在: {npm_cmd}")

    if OPENCLAW_RUNTIME_DIR.exists():
        log(f"清理旧 OpenClaw 运行时: {OPENCLAW_RUNTIME_DIR}")
        shutil.rmtree(OPENCLAW_RUNTIME_DIR)
    OPENCLAW_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{NODE_RUNTIME_DIR}{os.pathsep}{env.get('PATH', '')}"
    env["NPM_CONFIG_AUDIT"] = "false"
    env["NPM_CONFIG_FUND"] = "false"
    # 强制 project 本地安装，避免用户 npmrc 中 global=true/prefix 干扰
    env["NPM_CONFIG_GLOBAL"] = "false"

    log("预装 OpenClaw（npm install openclaw）...")
    run(
        [
            str(npm_cmd),
            "install",
            "openclaw",
            "--global=false",
            "--location=project",
            "--prefix",
            str(OPENCLAW_RUNTIME_DIR),
        ],
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    openclaw_bin_dir = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin"
    openclaw_cmd = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / "openclaw.cmd"
    openclaw_mjs = OPENCLAW_RUNTIME_DIR / "node_modules" / "openclaw" / "openclaw.mjs"

    # 某些 npm/环境组合下不会生成 .cmd，补一个相对路径 shim（供打包后运行）
    if not openclaw_cmd.exists() and openclaw_mjs.exists():
        openclaw_bin_dir.mkdir(parents=True, exist_ok=True)
        shim = '@echo off\r\nsetlocal\r\n"%~dp0..\\..\\..\\node\\node.exe" "%~dp0..\\openclaw\\openclaw.mjs" %*\r\n'
        openclaw_cmd.write_text(shim, encoding="utf-8")
        log(f"检测到缺少 openclaw.cmd，已自动生成 shim: {openclaw_cmd}")

    if not openclaw_cmd.exists():
        fallback_bin = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / "openclaw"
        if fallback_bin.exists():
            log(f"警告：未找到 openclaw.cmd，存在 openclaw 脚本: {fallback_bin}")
        if openclaw_mjs.exists():
            log(f"警告：未找到 openclaw.cmd，存在 mjs 入口: {openclaw_mjs}")
        node_modules_dir = OPENCLAW_RUNTIME_DIR / "node_modules"
        pkg_json = OPENCLAW_RUNTIME_DIR / "package.json"
        lock_file = OPENCLAW_RUNTIME_DIR / "package-lock.json"
        log(f"诊断：package.json exists={pkg_json.exists()} path={pkg_json}")
        log(f"诊断：package-lock.json exists={lock_file.exists()} path={lock_file}")
        log(f"诊断：node_modules exists={node_modules_dir.exists()} path={node_modules_dir}")
        if node_modules_dir.exists():
            top_level = [p.name for p in node_modules_dir.iterdir()][:20]
            log(f"诊断：node_modules 顶层(前20)={top_level}")
        raise FileNotFoundError(f"OpenClaw 预装失败，未找到可用的 openclaw.cmd: {openclaw_cmd}")
    log(f"OpenClaw 预装完成: {openclaw_cmd}")


def prepare_openclaw_runtime() -> None:
    """准备 OpenClaw 运行时：Node.js 便携版 + OpenClaw 预装"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = download_node_runtime()
    extract_node_runtime(zip_path)
    preinstall_openclaw()
    log("OpenClaw 运行时准备完成（已预装，无需首次启动安装）")


# ============ Step 4: PyInstaller 编译后端 ============


def build_backend() -> None:
    """用 PyInstaller 编译 Python 后端"""
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"spec 文件不存在: {SPEC_FILE}")

    work_dir = PROJECT_ROOT / "build" / "pyinstaller"
    work_dir.mkdir(parents=True, exist_ok=True)

    run(
        [
            "uv",
            "run",
            "pyinstaller",
            str(SPEC_FILE),
            "--distpath",
            str(BACKEND_DIST_DIR),
            "--workpath",
            str(work_dir),
            "--clean",
            "-y",
        ],
        cwd=PROJECT_ROOT,
    )

    # 验证产物
    backend_exe = BACKEND_DIST_DIR / "naga-backend" / "naga-backend.exe"
    if not backend_exe.exists():
        raise FileNotFoundError(f"后端编译产物缺失: {backend_exe}")
    log(f"后端编译完成: {backend_exe}")


# ============ Step 5: Electron 前端构建 + 打包 ============


def build_frontend(debug: bool = False) -> None:
    """构建 Vue 前端 + Electron 打包。

    debug=True 时会注入 electron-builder metadata，
    让安装后的 Electron 主进程以“调试控制台模式”启动后端。
    """
    # 安装前端依赖
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("安装前端依赖...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    # 构建 + 打包（npm run dist:win = vue-tsc + vite build + electron-builder --win）
    if debug:
        log("调试构建模式：已启用后端日志终端（安装后会弹 cmd 实时输出）")
        run(
            [
                "npm",
                "run",
                "dist:win",
                "--",
                "-c.extraMetadata.nagaDebugConsole=true",
            ],
            cwd=FRONTEND_DIR,
        )
    else:
        run(["npm", "run", "dist:win"], cwd=FRONTEND_DIR)

    log("Electron 打包完成")


# ============ Step 6: 汇总 ============


def print_summary() -> None:
    """打印构建产物信息"""
    print()
    print("=" * 50)
    print("  构建完成!")
    print("=" * 50)

    # 后端产物
    backend_dir = BACKEND_DIST_DIR / "naga-backend"
    if backend_dir.exists():
        size = sum(f.stat().st_size for f in backend_dir.rglob("*") if f.is_file())
        log(f"后端产物: {backend_dir}  ({size / 1024 / 1024:.0f} MB)")

    # OpenClaw 运行时
    runtime_dir = BACKEND_DIST_DIR / "openclaw-runtime"
    if runtime_dir.exists():
        size = sum(f.stat().st_size for f in runtime_dir.rglob("*") if f.is_file())
        log(f"OpenClaw 运行时: {runtime_dir}  ({size / 1024 / 1024:.0f} MB)")

    # Electron 安装包
    release_dir = FRONTEND_DIR / "release"
    if release_dir.exists():
        for f in release_dir.glob("*.exe"):
            log(f"安装包: {f}  ({f.stat().st_size / 1024 / 1024:.0f} MB)")


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NagaAgent Windows 构建脚本")
    parser.add_argument(
        "--skip-openclaw",
        action="store_true",
        help="跳过 OpenClaw 运行时准备（Node 便携版 + OpenClaw 预装）",
    )
    parser.add_argument("--backend-only", action="store_true", help="仅编译后端，不打包 Electron")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试打包：安装后启动时弹出后端日志终端（仅 Windows 生效）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_time = time.time()

    # 计算总步骤数
    total_steps = 2  # 环境检查 + 同步依赖
    if not args.skip_openclaw:
        total_steps += 1
    total_steps += 1  # 编译后端
    if not args.backend_only:
        total_steps += 1  # 前端打包

    step = 0

    # Step 1: 环境检查
    step += 1
    log_step(step, total_steps, "环境检查")
    if not check_environment():
        log("环境检查未通过，请先安装缺失的工具")
        sys.exit(1)

    # Step 2: 同步依赖
    step += 1
    log_step(step, total_steps, "同步 Python 依赖")
    sync_dependencies()

    # Step 3: OpenClaw 运行时
    if not args.skip_openclaw:
        step += 1
        log_step(step, total_steps, "准备 OpenClaw 运行时（含预装）")
        prepare_openclaw_runtime()

    # Step 4: 编译后端
    step += 1
    log_step(step, total_steps, "PyInstaller 编译后端")
    build_backend()

    # Step 5: 前端打包
    if not args.backend_only:
        step += 1
        title = "Electron 前端打包（DEBUG）" if args.debug else "Electron 前端打包"
        log_step(step, total_steps, title)
        build_frontend(debug=args.debug)

    # 汇总
    print_summary()
    elapsed = time.time() - start_time
    log(f"总耗时: {elapsed / 60:.1f} 分钟")


if __name__ == "__main__":
    main()
