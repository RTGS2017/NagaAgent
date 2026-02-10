#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 内嵌运行时准备脚本

打包前运行：
  1. 下载 Node.js 便携版
  2. 从 openclaw/ submodule 构建
  3. 将构建产物复制到 frontend/backend-dist/openclaw-runtime/

用法: python scripts/prepare_openclaw_runtime.py
"""

import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request
from pathlib import Path

# ============ 配置 ============

NODE_VERSION = "22.13.1"
NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"

# 输出目录（相对于项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "backend-dist" / "openclaw-runtime"
NODE_DIR = OUTPUT_DIR / "node"
OPENCLAW_DIR = OUTPUT_DIR / "openclaw"

# submodule 源码目录
SUBMODULE_DIR = PROJECT_ROOT / "openclaw"

# 下载缓存目录
CACHE_DIR = PROJECT_ROOT / ".cache"

# 需要从 submodule 复制到运行时的目录/文件（参考 package.json files 字段）
COPY_ITEMS = [
    "dist",
    "openclaw.mjs",
    "package.json",
    "skills",
    "extensions",
    "assets",
    "docs",
]


def log(msg: str) -> None:
    print(f"[prepare-openclaw] {msg}")


# ============ 步骤 1: 下载 Node.js ============

def download_node() -> Path:
    """下载 Node.js 便携版 zip，返回本地路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"node-v{NODE_VERSION}-win-x64.zip"
    cached = CACHE_DIR / zip_name

    if cached.exists():
        log(f"使用缓存: {cached}")
        return cached

    log(f"下载 Node.js v{NODE_VERSION} ...")
    log(f"  URL: {NODE_DIST_URL}")
    urllib.request.urlretrieve(NODE_DIST_URL, str(cached))
    log(f"  下载完成: {cached} ({cached.stat().st_size / 1024 / 1024:.1f} MB)")
    return cached


# ============ 步骤 2: 解压 Node.js ============

def extract_node(zip_path: Path) -> None:
    """解压 Node.js 到 OUTPUT_DIR/node/"""
    if NODE_DIR.exists():
        log(f"清理旧目录: {NODE_DIR}")
        shutil.rmtree(NODE_DIR)

    NODE_DIR.mkdir(parents=True, exist_ok=True)

    log(f"解压 Node.js 到 {NODE_DIR} ...")
    with zipfile.ZipFile(zip_path, "r") as zf:
        prefix = f"node-v{NODE_VERSION}-win-x64/"
        for member in zf.infolist():
            if not member.filename.startswith(prefix):
                continue
            rel = member.filename[len(prefix):]
            if not rel:
                continue
            target = NODE_DIR / rel
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    # 验证
    node_exe = NODE_DIR / "node.exe"
    npm_cmd = NODE_DIR / "npm.cmd"
    if not node_exe.exists():
        raise FileNotFoundError(f"解压后未找到 {node_exe}")
    if not npm_cmd.exists():
        raise FileNotFoundError(f"解压后未找到 {npm_cmd}")
    log(f"  node.exe: {node_exe}")
    log(f"  npm.cmd:  {npm_cmd}")


# ============ 步骤 3: 确保 pnpm 可用 ============

def ensure_pnpm(env: dict) -> str:
    """确保 pnpm 可用，返回 pnpm 可执行路径"""
    # 先检查系统 pnpm
    pnpm = shutil.which("pnpm")
    if pnpm:
        log(f"使用系统 pnpm: {pnpm}")
        return pnpm

    # 使用内嵌 Node.js 的 corepack 启用 pnpm
    node_exe = str(NODE_DIR / "node.exe")
    npx_cmd = str(NODE_DIR / "npx.cmd")

    log("系统未安装 pnpm，尝试通过 corepack 启用...")
    try:
        subprocess.run(
            [npx_cmd, "corepack", "enable"],
            env=env, check=True, capture_output=True,
        )
        # corepack 启用后 pnpm 应该在 NODE_DIR 中
        pnpm_cmd = NODE_DIR / "pnpm.cmd"
        if pnpm_cmd.exists():
            log(f"  corepack 启用成功: {pnpm_cmd}")
            return str(pnpm_cmd)
    except Exception as e:
        log(f"  corepack 启用失败: {e}")

    # 回退：通过 npm 安装 pnpm
    log("通过 npm 全局安装 pnpm...")
    npm_cmd = str(NODE_DIR / "npm.cmd")
    subprocess.run(
        [npm_cmd, "install", "-g", "pnpm"],
        env=env, check=True,
    )
    pnpm = shutil.which("pnpm", path=env.get("PATH", ""))
    if pnpm:
        return pnpm
    raise RuntimeError("无法安装 pnpm")


# ============ 步骤 4: 从 submodule 构建 OpenClaw ============

def build_openclaw_from_submodule() -> None:
    """在 submodule 目录执行 pnpm install + pnpm build，然后复制产物"""
    if not SUBMODULE_DIR.exists():
        raise FileNotFoundError(
            f"OpenClaw submodule 不存在: {SUBMODULE_DIR}\n"
            "请先运行: git submodule update --init --recursive"
        )

    pkg_json = SUBMODULE_DIR / "package.json"
    if not pkg_json.exists():
        raise FileNotFoundError(f"submodule 中未找到 package.json: {pkg_json}")

    # 构建环境变量
    env = os.environ.copy()
    env["PATH"] = f"{NODE_DIR}{os.pathsep}{env.get('PATH', '')}"

    pnpm = ensure_pnpm(env)

    # 执行 pnpm install
    log("在 submodule 中执行 pnpm install ...")
    subprocess.run(
        [pnpm, "install"],
        cwd=str(SUBMODULE_DIR),
        env=env,
        check=True,
    )

    # 执行 pnpm build
    log("在 submodule 中执行 pnpm build ...")
    subprocess.run(
        [pnpm, "build"],
        cwd=str(SUBMODULE_DIR),
        env=env,
        check=True,
    )

    # 验证构建产物
    dist_entry = SUBMODULE_DIR / "dist" / "entry.js"
    if not dist_entry.exists():
        raise FileNotFoundError(f"构建后未找到 {dist_entry}")
    log(f"  构建成功: {dist_entry}")


# ============ 步骤 5: 复制构建产物到运行时目录 ============

def copy_build_artifacts() -> None:
    """将 submodule 构建产物复制到 OPENCLAW_DIR"""
    if OPENCLAW_DIR.exists():
        log(f"清理旧目录: {OPENCLAW_DIR}")
        shutil.rmtree(OPENCLAW_DIR)

    OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)

    # 复制 files 字段中的目录/文件
    for item_name in COPY_ITEMS:
        src = SUBMODULE_DIR / item_name
        dst = OPENCLAW_DIR / item_name
        if src.is_dir():
            shutil.copytree(src, dst)
            log(f"  复制目录: {item_name}/")
        elif src.is_file():
            shutil.copy2(src, dst)
            log(f"  复制文件: {item_name}")
        else:
            log(f"  跳过（不存在）: {item_name}")

    # 安装生产依赖到运行时目录
    log("安装生产依赖到运行时目录...")
    env = os.environ.copy()
    env["PATH"] = f"{NODE_DIR}{os.pathsep}{env.get('PATH', '')}"
    pnpm = ensure_pnpm(env)

    # 复制 package.json 后用 pnpm install --prod 安装生产依赖
    subprocess.run(
        [pnpm, "install", "--prod", "--no-frozen-lockfile"],
        cwd=str(OPENCLAW_DIR),
        env=env,
        check=True,
    )

    # 验证
    mjs = OPENCLAW_DIR / "openclaw.mjs"
    if not mjs.exists():
        raise FileNotFoundError(f"复制后未找到 {mjs}")
    log(f"  openclaw.mjs: {mjs}")
    log(f"  dist/entry.js: {OPENCLAW_DIR / 'dist' / 'entry.js'}")


# ============ 步骤 6: 清理不必要文件 ============

def cleanup() -> None:
    """删除不必要的文件以减小体积"""
    log("清理不必要文件 ...")
    removed_size = 0

    # Node.js 中不需要的目录
    for name in ["include", "lib", "share"]:
        d = NODE_DIR / name
        if d.exists():
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d)
            removed_size += size
            log(f"  删除 node/{name}/ ({size / 1024 / 1024:.1f} MB)")

    # 删除 Node.js 文档
    for pattern in ["*.md", "LICENSE", "CHANGELOG*"]:
        for f in NODE_DIR.glob(pattern):
            if f.is_file():
                removed_size += f.stat().st_size
                f.unlink()

    # 删除 openclaw 中的文档和测试
    for pattern in ["**/README.md", "**/CHANGELOG*", "**/LICENSE"]:
        for f in OPENCLAW_DIR.rglob(pattern.split("/")[-1]):
            if f.is_file() and "node_modules" in str(f):
                removed_size += f.stat().st_size
                f.unlink()

    log(f"  共清理 {removed_size / 1024 / 1024:.1f} MB")


# ============ 步骤 7: 汇总 ============

def print_summary() -> None:
    """打印最终目录结构和大小"""
    total = sum(f.stat().st_size for f in OUTPUT_DIR.rglob("*") if f.is_file())
    log(f"运行时总大小: {total / 1024 / 1024:.1f} MB")
    log(f"输出目录: {OUTPUT_DIR}")
    log("目录结构:")
    for item in sorted(OUTPUT_DIR.iterdir()):
        if item.is_dir():
            size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
            log(f"  {item.name}/ ({size / 1024 / 1024:.1f} MB)")


# ============ 主流程 ============

def main() -> None:
    log(f"项目根目录:   {PROJECT_ROOT}")
    log(f"submodule 目录: {SUBMODULE_DIR}")
    log(f"输出目录:     {OUTPUT_DIR}")
    log("")

    zip_path = download_node()
    extract_node(zip_path)
    build_openclaw_from_submodule()
    copy_build_artifacts()
    cleanup()

    log("")
    print_summary()
    log("")
    log("准备完成！可以继续执行打包流程。")


if __name__ == "__main__":
    main()
