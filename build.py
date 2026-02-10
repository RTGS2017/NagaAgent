#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent 一键打包脚本

用法:
    python build.py                          # 完整打包
    python build.py --skip-backend           # 跳过后端编译
    python build.py --skip-frontend          # 跳过前端打包
    python build.py --skip-clean             # 跳过清理缓存

流程:
    Step 0: 清理缓存 (dist, build, frontend/backend-dist 等)
    Step 1: PyInstaller 编译后端
    Step 2: Electron 打包前端

最终产物: frontend/release/Naga Agent Setup x.x.x.exe
"""

import sys
import time
import shutil
import argparse
import platform
import subprocess
from pathlib import Path
from typing import Optional

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIST_DIR = FRONTEND_DIR / "backend-dist"

# 需要清理的缓存目录
CLEAN_DIRS: list[tuple[Path, str]] = [
    (PROJECT_ROOT / "dist", "PyInstaller 输出"),
    (PROJECT_ROOT / "build", "PyInstaller 中间文件"),
    (BACKEND_DIST_DIR / "naga-backend", "后端复制目标"),
    (FRONTEND_DIR / "dist", "Vite 构建输出"),
    (FRONTEND_DIR / "dist-electron", "Electron 构建输出"),
    (FRONTEND_DIR / "release", "Electron-builder 最终产物"),
]


# ============ 日志工具 ============


class Colors:
    """ANSI 颜色码"""

    RESET = "\033[0m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    BOLD = "\033[1m"


def log(msg: str, color: str = "") -> None:
    """带时间戳的日志输出"""
    ts = time.strftime("%H:%M:%S")
    prefix = f"{Colors.CYAN}[{ts}]{Colors.RESET} "
    if color:
        print(f"{prefix}{color}{msg}{Colors.RESET}")
    else:
        print(f"{prefix}{msg}")


def log_step(step: int, title: str) -> None:
    """打印步骤标题"""
    print()
    log(f"{'=' * 50}", Colors.BOLD)
    log(f"Step {step}: {title}", Colors.BOLD + Colors.GREEN)
    log(f"{'=' * 50}", Colors.BOLD)


def log_ok(msg: str) -> None:
    log(f"  [OK] {msg}", Colors.GREEN)


def log_warn(msg: str) -> None:
    log(f"  [WARN] {msg}", Colors.YELLOW)


def log_err(msg: str) -> None:
    log(f"  [ERROR] {msg}", Colors.RED)


# ============ 工具函数 ============


def check_command(cmd: str) -> Optional[str]:
    """检查命令是否可用，返回路径或 None"""
    return shutil.which(cmd)


def run_cmd(
    cmd: list[str],
    cwd: Optional[Path] = None,
    desc: str = "",
) -> None:
    """执行命令，失败时抛出异常"""
    cwd = cwd or PROJECT_ROOT
    cmd_str = " ".join(cmd)
    log(f"  $ {cmd_str}")

    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        # 不捕获输出，直接打印到终端
    )

    if result.returncode != 0:
        raise RuntimeError(f"命令执行失败 (exit={result.returncode}): {desc or cmd_str}")


def remove_dir(path: Path, label: str) -> None:
    """删除目录（如存在）"""
    if path.exists():
        shutil.rmtree(path)
        log_ok(f"已清理: {path.relative_to(PROJECT_ROOT)} ({label})")


def format_duration(seconds: float) -> str:
    """格式化耗时"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


# ============ 步骤实现 ============


def step_clean() -> None:
    """Step 0: 清理缓存"""
    log_step(0, "清理缓存")
    cleaned = 0
    for path, label in CLEAN_DIRS:
        if path.exists():
            remove_dir(path, label)
            cleaned += 1

    if cleaned == 0:
        log("  无需清理，所有缓存目录均不存在")
    else:
        log(f"  共清理 {cleaned} 个目录")


def step_backend() -> None:
    """Step 1: PyInstaller 编译后端"""
    log_step(1, "PyInstaller 编译后端")

    spec_file = PROJECT_ROOT / "naga-backend.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"spec 文件不存在: {spec_file}")

    # 2.1 确保 build 依赖已安装
    log("  安装 build 依赖...")
    run_cmd(
        ["uv", "sync", "--group", "build"],
        desc="uv sync --group build",
    )

    # 2.2 执行 PyInstaller
    log("  编译后端...")
    run_cmd(
        ["uv", "run", "pyinstaller", "naga-backend.spec", "--clean", "--noconfirm"],
        desc="PyInstaller 编译",
    )

    # 2.3 验证输出
    src = PROJECT_ROOT / "dist" / "naga-backend"
    if not src.exists():
        raise RuntimeError(f"PyInstaller 输出目录不存在: {src}")

    exe = src / "naga-backend.exe"
    if not exe.exists():
        raise RuntimeError(f"后端可执行文件未生成: {exe}")

    # 2.4 复制到 frontend/backend-dist/
    dst = BACKEND_DIST_DIR / "naga-backend"
    dst.parent.mkdir(parents=True, exist_ok=True)
    log(f"  复制后端到 {dst.relative_to(PROJECT_ROOT)} ...")
    shutil.copytree(str(src), str(dst))

    log_ok("后端编译完成")


def step_frontend() -> None:
    """Step 2: Electron 打包前端"""
    log_step(2, "Electron 打包前端")

    if not FRONTEND_DIR.exists():
        raise FileNotFoundError(f"前端目录不存在: {FRONTEND_DIR}")

    # 3.1 npm install
    log("  安装前端依赖...")
    run_cmd(
        ["npm", "install"],
        cwd=FRONTEND_DIR,
        desc="npm install",
    )

    # 3.2 构建 Vue 应用
    log("  构建前端...")
    run_cmd(
        ["npm", "run", "build"],
        cwd=FRONTEND_DIR,
        desc="npm run build",
    )

    # 3.3 Electron 打包
    log("  打包 Electron 应用...")
    run_cmd(
        ["npx", "electron-builder", "--win"],
        cwd=FRONTEND_DIR,
        desc="electron-builder --win",
    )

    # 3.4 验证产物
    release_dir = FRONTEND_DIR / "release"
    if not release_dir.exists():
        raise RuntimeError(f"release 目录未生成: {release_dir}")

    # 查找 .exe 安装程序
    exe_files = list(release_dir.glob("*.exe"))
    if exe_files:
        for f in exe_files:
            size_mb = f.stat().st_size / 1024 / 1024
            log_ok(f"产物: {f.name} ({size_mb:.1f} MB)")
    else:
        log_warn("未找到 .exe 安装程序，请检查 release/ 目录")


# ============ 主流程 ============


def check_prerequisites(args: argparse.Namespace) -> None:
    """检查前置依赖"""
    log("检查前置依赖...")

    if platform.system() != "Windows":
        raise RuntimeError(f"当前平台: {platform.system()}，此脚本仅支持 Windows 打包")

    # 检查 uv（后端编译需要）
    if not args.skip_backend:
        if not check_command("uv"):
            raise RuntimeError("未找到 uv，请先安装: https://docs.astral.sh/uv/")
        log_ok("uv 可用")

    # 检查 npm / node（前端打包需要）
    if not args.skip_frontend:
        if not check_command("node"):
            raise RuntimeError("未找到 node，请先安装 Node.js 22+")
        if not check_command("npm"):
            raise RuntimeError("未找到 npm，请先安装 Node.js 22+")
        log_ok("node / npm 可用")


def main() -> None:
    parser = argparse.ArgumentParser(description="NagaAgent 一键打包脚本")
    parser.add_argument("--skip-clean", action="store_true", help="跳过清理缓存")
    parser.add_argument("--skip-backend", action="store_true", help="跳过后端编译")
    parser.add_argument("--skip-frontend", action="store_true", help="跳过前端打包")
    args = parser.parse_args()

    print()
    log("NagaAgent 一键打包", Colors.BOLD + Colors.GREEN)
    log(f"项目根目录: {PROJECT_ROOT}")
    print()

    total_start = time.time()

    try:
        # 前置检查
        check_prerequisites(args)

        # Step 0: 清理
        if not args.skip_clean:
            t = time.time()
            step_clean()
            log(f"  耗时: {format_duration(time.time() - t)}")

        # Step 1: 后端编译
        if not args.skip_backend:
            t = time.time()
            step_backend()
            log(f"  耗时: {format_duration(time.time() - t)}")
        else:
            log("\n  [SKIP] 跳过后端编译", Colors.YELLOW)

        # Step 2: 前端打包
        if not args.skip_frontend:
            t = time.time()
            step_frontend()
            log(f"  耗时: {format_duration(time.time() - t)}")
        else:
            log("\n  [SKIP] 跳过前端打包", Colors.YELLOW)

        # 完成
        total = time.time() - total_start
        print()
        log(f"{'=' * 50}", Colors.BOLD)
        log(f"打包完成！总耗时: {format_duration(total)}", Colors.BOLD + Colors.GREEN)
        log(f"{'=' * 50}", Colors.BOLD)

    except Exception as e:
        total = time.time() - total_start
        print()
        log_err(str(e))
        log(f"打包失败，已耗时: {format_duration(total)}", Colors.RED)
        sys.exit(1)


if __name__ == "__main__":
    main()
