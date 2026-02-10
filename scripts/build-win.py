#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent Windows 完整构建脚本

流程：
  1. 环境检查（Python, Node.js, npm, git submodule）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 内嵌运行时（从 submodule 构建）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 输出汇总

用法:
  python scripts/build-win.py            # 完整构建
  python scripts/build-win.py --skip-openclaw   # 跳过 OpenClaw 准备
  python scripts/build-win.py --backend-only    # 仅编译后端
"""

import os
import sys
import shutil
import subprocess
import argparse
import time
from pathlib import Path
from typing import Optional

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIST_DIR = FRONTEND_DIR / "backend-dist"
SPEC_FILE = PROJECT_ROOT / "naga-backend.spec"
SUBMODULE_DIR = PROJECT_ROOT / "openclaw"
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "prepare_openclaw_runtime.py"

# 最低版本要求
MIN_NODE_MAJOR = 22
MIN_PYTHON = (3, 11)


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
    """执行命令并实时输出"""
    log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
    )


def get_cmd_version(cmd: str, args: list[str] | None = None) -> Optional[str]:
    """获取命令版本号，失败返回 None"""
    try:
        result = subprocess.run(
            [cmd, *(args or ["--version"])],
            capture_output=True, text=True, timeout=10,
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

    # git submodule
    if SUBMODULE_DIR.exists() and (SUBMODULE_DIR / "package.json").exists():
        log(f"  openclaw submodule  ✓")
    else:
        log("  openclaw submodule 未初始化  ✗")
        log("  请运行: git submodule update --init --recursive")
        ok = False

    return ok


# ============ Step 2: 同步依赖 ============

def sync_dependencies() -> None:
    """uv sync + build 依赖组"""
    run(["uv", "sync", "--group", "build"], cwd=PROJECT_ROOT)
    log("Python 依赖同步完成")


# ============ Step 3: 准备 OpenClaw 运行时 ============

def prepare_openclaw() -> None:
    """调用 prepare_openclaw_runtime.py 构建内嵌运行时"""
    if not PREPARE_SCRIPT.exists():
        raise FileNotFoundError(f"准备脚本不存在: {PREPARE_SCRIPT}")
    run([sys.executable, str(PREPARE_SCRIPT)], cwd=PROJECT_ROOT)
    # 验证产物
    runtime_dir = BACKEND_DIST_DIR / "openclaw-runtime"
    mjs = runtime_dir / "openclaw" / "openclaw.mjs"
    node_exe = runtime_dir / "node" / "node.exe"
    if not mjs.exists():
        raise FileNotFoundError(f"OpenClaw 构建产物缺失: {mjs}")
    if not node_exe.exists():
        raise FileNotFoundError(f"Node.js 便携版缺失: {node_exe}")
    log("OpenClaw 运行时准备完成")


# ============ Step 4: PyInstaller 编译后端 ============

def build_backend() -> None:
    """用 PyInstaller 编译 Python 后端"""
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"spec 文件不存在: {SPEC_FILE}")

    work_dir = PROJECT_ROOT / "build" / "pyinstaller"
    work_dir.mkdir(parents=True, exist_ok=True)

    run(
        [
            "uv", "run", "pyinstaller", str(SPEC_FILE),
            "--distpath", str(BACKEND_DIST_DIR),
            "--workpath", str(work_dir),
            "--clean", "-y",
        ],
        cwd=PROJECT_ROOT,
    )

    # 验证产物
    backend_exe = BACKEND_DIST_DIR / "naga-backend" / "naga-backend.exe"
    if not backend_exe.exists():
        raise FileNotFoundError(f"后端编译产物缺失: {backend_exe}")
    log(f"后端编译完成: {backend_exe}")


# ============ Step 5: Electron 前端构建 + 打包 ============

def build_frontend() -> None:
    """构建 Vue 前端 + Electron 打包"""
    # 安装前端依赖
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("安装前端依赖...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    # 构建 + 打包（npm run dist:win = vue-tsc + vite build + electron-builder --win）
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
    parser.add_argument("--skip-openclaw", action="store_true", help="跳过 OpenClaw 运行时准备")
    parser.add_argument("--backend-only", action="store_true", help="仅编译后端，不打包 Electron")
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
        log_step(step, total_steps, "准备 OpenClaw 运行时")
        prepare_openclaw()

    # Step 4: 编译后端
    step += 1
    log_step(step, total_steps, "PyInstaller 编译后端")
    build_backend()

    # Step 5: 前端打包
    if not args.backend_only:
        step += 1
        log_step(step, total_steps, "Electron 前端打包")
        build_frontend()

    # 汇总
    print_summary()
    elapsed = time.time() - start_time
    log(f"总耗时: {elapsed / 60:.1f} 分钟")


if __name__ == "__main__":
    main()