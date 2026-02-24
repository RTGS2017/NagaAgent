#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NagaAgent 跨平台构建脚本（Windows / macOS / Linux）

流程：
  1. 环境检查（Python, uv, Node.js, npm）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 运行时（下载 Node.js 便携版 + 预装 OpenClaw）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 输出汇总

默认在构建阶段预装 OpenClaw，用户安装后首次启动可直接使用。

用法:
  python scripts/build.py                  # 完整构建（自动检测平台）
  python scripts/build.py --skip-openclaw  # 跳过 OpenClaw 运行时准备
  python scripts/build.py --backend-only   # 仅编译后端
  python scripts/build.py --force-openclaw # 强制重装 OpenClaw
  python scripts/build.py --debug          # 调试模式（仅 Windows 生效）
"""

import os
import sys
import platform
import shutil
import subprocess
import argparse
import time
import zipfile
import tarfile
import json
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11 fallback
import urllib.request
from pathlib import Path
from typing import Optional

# ============ 平台检测 ============

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
PLATFORM_TAG = "win" if IS_WINDOWS else "mac" if IS_MACOS else "linux"

# macOS: 区分 arm64 (Apple Silicon) 和 x86_64 (Intel)
MAC_ARCH = "arm64" if platform.machine() == "arm64" else "x64"

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent
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
OPENCLAW_VERSION = "2026.2.17"
CACHE_DIR = PROJECT_ROOT / ".cache"

# Node.js 下载地址（按平台）
if IS_WINDOWS:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-win-x64.zip"
elif IS_MACOS:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-darwin-{MAC_ARCH}.tar.gz"
else:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-linux-x64.tar.xz"

NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ARCHIVE}"

# 平台相关路径
NODE_BIN = "node.exe" if IS_WINDOWS else "bin/node"
NPM_BIN = "npm.cmd" if IS_WINDOWS else "bin/npm"
BACKEND_EXT = ".exe" if IS_WINDOWS else ""
INSTALLER_GLOB = "*.exe" if IS_WINDOWS else "*.dmg" if IS_MACOS else "*.AppImage"


def read_version() -> str:
    """从 pyproject.toml 读取版本号（唯一版本源）"""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def sync_frontend_version() -> None:
    """将 pyproject.toml 版本同步到 package.json（electron-builder 用它生成安装包文件名）"""
    ver = read_version()
    pkg_path = FRONTEND_DIR / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    if pkg.get("version") == ver:
        return
    pkg["version"] = ver
    pkg_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"已同步版本 {ver} → package.json")


def log(msg: str) -> None:
    print(f"[build] {msg}")


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

    platform_name = "Windows" if IS_WINDOWS else "macOS" if IS_MACOS else "Linux"
    log(f"  平台: {platform_name} ({platform.machine()})  ✓")
    log(f"  构建版本: {read_version()}")

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
    """下载 Node.js 便携版，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = CACHE_DIR / NODE_ARCHIVE

    if archive_path.exists():
        log(f"使用缓存 Node.js 包: {archive_path}")
        return archive_path

    log(f"下载 Node.js v{NODE_VERSION}: {NODE_DIST_URL}")
    urllib.request.urlretrieve(NODE_DIST_URL, str(archive_path))
    log(f"Node.js 下载完成: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return archive_path


def _extract_zip(archive_path: Path) -> None:
    """解压 .zip 格式的 Node.js（Windows）"""
    prefix = f"node-v{NODE_VERSION}-win-x64/"
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            if not member.filename.startswith(prefix):
                continue
            rel = member.filename[len(prefix):]
            if not rel:
                continue
            target = NODE_RUNTIME_DIR / rel
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _extract_tarball(archive_path: Path) -> None:
    """解压 .tar.gz / .tar.xz 格式的 Node.js（macOS / Linux）"""
    # 推断 archive 内的顶层目录名
    stem = NODE_ARCHIVE
    for suffix in (".tar.gz", ".tar.xz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    prefix = f"{stem}/"

    mode = "r:gz" if archive_path.name.endswith(".tar.gz") else "r:xz"
    with tarfile.open(archive_path, mode) as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue
            target = NODE_RUNTIME_DIR / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                # 保留符号链接（macOS/Linux Node.js 中 bin/node -> ../lib/... 等）
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.symlink(member.linkname, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tf.extractfile(member)
                if extracted:
                    with open(target, "wb") as dst:
                        shutil.copyfileobj(extracted, dst)
                    # 保留可执行权限
                    if member.mode & 0o111:
                        target.chmod(target.stat().st_mode | 0o755)


def extract_node_runtime(archive_path: Path) -> None:
    """解压 Node.js 到 openclaw-runtime/node"""
    if NODE_RUNTIME_DIR.exists():
        log(f"清理旧 Node.js 运行时: {NODE_RUNTIME_DIR}")
        shutil.rmtree(NODE_RUNTIME_DIR)

    NODE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    log(f"解压 Node.js 到: {NODE_RUNTIME_DIR}")
    if archive_path.suffix == ".zip":
        _extract_zip(archive_path)
    else:
        _extract_tarball(archive_path)

    # 验证关键文件
    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    npm_bin = NODE_RUNTIME_DIR / NPM_BIN
    if not node_bin.exists():
        raise FileNotFoundError(f"解压后缺少 node: {node_bin}")
    if not npm_bin.exists():
        raise FileNotFoundError(f"解压后缺少 npm: {npm_bin}")
    log("Node.js 便携版解压完成")


def preinstall_openclaw(force: bool = False) -> None:
    """在内嵌运行时目录中预装 OpenClaw"""
    npm_bin = NODE_RUNTIME_DIR / NPM_BIN
    if not npm_bin.exists():
        raise FileNotFoundError(f"npm 不存在: {npm_bin}")

    # 检测已安装版本
    if IS_WINDOWS:
        openclaw_entry = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / "openclaw.cmd"
    else:
        openclaw_entry = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / "openclaw"

    openclaw_pkg = OPENCLAW_RUNTIME_DIR / "node_modules" / "openclaw" / "package.json"
    installed_version: Optional[str] = None
    if openclaw_pkg.exists():
        try:
            installed_version = json.loads(openclaw_pkg.read_text(encoding="utf-8")).get("version")
        except Exception:
            installed_version = None

    if not force and openclaw_entry.exists() and installed_version == OPENCLAW_VERSION:
        log(f"OpenClaw 已预装且版本匹配: {installed_version}，跳过安装")
        return
    if not force and openclaw_entry.exists():
        log(
            f"检测到已安装 OpenClaw 版本 {installed_version or 'unknown'}，"
            f"目标版本 {OPENCLAW_VERSION}，将执行重装"
        )

    if OPENCLAW_RUNTIME_DIR.exists():
        log(f"清理旧 OpenClaw 运行时: {OPENCLAW_RUNTIME_DIR}")
        shutil.rmtree(OPENCLAW_RUNTIME_DIR)
    OPENCLAW_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if IS_WINDOWS:
        env["PATH"] = f"{NODE_RUNTIME_DIR}{os.pathsep}{env.get('PATH', '')}"
    else:
        node_bin_dir = NODE_RUNTIME_DIR / "bin"
        env["PATH"] = f"{node_bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["NPM_CONFIG_AUDIT"] = "false"
    env["NPM_CONFIG_FUND"] = "false"
    env["NPM_CONFIG_GLOBAL"] = "false"

    pkg_spec = f"openclaw@{OPENCLAW_VERSION}"
    log(f"预装 OpenClaw（npm install {pkg_spec}）...")
    run(
        [
            str(npm_bin),
            "install",
            pkg_spec,
            "--global=false",
            "--location=project",
            "--prefix",
            str(OPENCLAW_RUNTIME_DIR),
        ],
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    openclaw_bin_dir = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin"
    openclaw_mjs = OPENCLAW_RUNTIME_DIR / "node_modules" / "openclaw" / "openclaw.mjs"

    # 某些 npm/环境组合下不会生成入口脚本，补一个相对路径 shim（供打包后运行）
    if not openclaw_entry.exists() and openclaw_mjs.exists():
        openclaw_bin_dir.mkdir(parents=True, exist_ok=True)
        if IS_WINDOWS:
            shim = '@echo off\r\nsetlocal\r\n"%~dp0..\\..\\..\\node\\node.exe" "%~dp0..\\openclaw\\openclaw.mjs" %*\r\n'
            openclaw_entry.write_text(shim, encoding="utf-8")
        else:
            shim = '#!/bin/sh\nexec "$(dirname "$0")/../../../node/bin/node" "$(dirname "$0")/../openclaw/openclaw.mjs" "$@"\n'
            openclaw_entry.write_text(shim, encoding="utf-8")
            openclaw_entry.chmod(0o755)
        log(f"检测到缺少 openclaw 入口，已自动生成 shim: {openclaw_entry}")

    if not openclaw_entry.exists():
        # 诊断信息
        if IS_WINDOWS:
            fallback_bin = openclaw_bin_dir / "openclaw"
        else:
            fallback_bin = openclaw_bin_dir / "openclaw.cmd"
        if fallback_bin.exists():
            log(f"警告：未找到预期入口，但存在替代脚本: {fallback_bin}")
        if openclaw_mjs.exists():
            log(f"警告：存在 mjs 入口: {openclaw_mjs}")
        node_modules_dir = OPENCLAW_RUNTIME_DIR / "node_modules"
        pkg_json = OPENCLAW_RUNTIME_DIR / "package.json"
        lock_file = OPENCLAW_RUNTIME_DIR / "package-lock.json"
        log(f"诊断：package.json exists={pkg_json.exists()} path={pkg_json}")
        log(f"诊断：package-lock.json exists={lock_file.exists()} path={lock_file}")
        log(f"诊断：node_modules exists={node_modules_dir.exists()} path={node_modules_dir}")
        if node_modules_dir.exists():
            top_level = [p.name for p in node_modules_dir.iterdir()][:20]
            log(f"诊断：node_modules 顶层(前20)={top_level}")
        raise FileNotFoundError(f"OpenClaw 预装失败，未找到可用入口: {openclaw_entry}")
    log(f"OpenClaw 预装完成: {openclaw_entry}")


def prepare_openclaw_runtime(force: bool = False) -> None:
    """准备 OpenClaw 运行时：Node.js 便携版 + OpenClaw 预装"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = download_node_runtime()
    extract_node_runtime(archive_path)
    preinstall_openclaw(force=force)
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
    backend_bin = BACKEND_DIST_DIR / "naga-backend" / f"naga-backend{BACKEND_EXT}"
    if not backend_bin.exists():
        raise FileNotFoundError(f"后端编译产物缺失: {backend_bin}")
    log(f"后端编译完成: {backend_bin}")


# ============ Step 5: Electron 前端构建 + 打包 ============


def build_frontend(debug: bool = False) -> None:
    """构建 Vue 前端 + Electron 打包。

    debug=True 时（仅 Windows）会注入 electron-builder metadata，
    让安装后的 Electron 主进程以"调试控制台模式"启动后端。
    """
    # 同步版本号 pyproject.toml → package.json
    sync_frontend_version()

    # 安装前端依赖
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("安装前端依赖...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    dist_script = f"dist:{PLATFORM_TAG}"

    if debug and IS_WINDOWS:
        log("调试构建模式：已启用后端日志终端（安装后会弹 cmd 实时输出）")
        run(
            [
                "npm",
                "run",
                dist_script,
                "--",
                "-c.extraMetadata.nagaDebugConsole=true",
            ],
            cwd=FRONTEND_DIR,
        )
    else:
        if debug and not IS_WINDOWS:
            log("注意：--debug 调试控制台仅在 Windows 上生效，已忽略")
        run(["npm", "run", dist_script], cwd=FRONTEND_DIR)

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
        for f in release_dir.glob(INSTALLER_GLOB):
            log(f"安装包: {f}  ({f.stat().st_size / 1024 / 1024:.0f} MB)")


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NagaAgent 跨平台构建脚本")
    parser.add_argument(
        "--skip-openclaw",
        action="store_true",
        help="跳过 OpenClaw 运行时准备（Node 便携版 + OpenClaw 预装）",
    )
    parser.add_argument("--backend-only", action="store_true", help="仅编译后端，不打包 Electron")
    parser.add_argument(
        "--force-openclaw",
        action="store_true",
        help="强制重新安装 OpenClaw（先删除旧安装）",
    )
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
        prepare_openclaw_runtime(force=args.force_openclaw)

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
