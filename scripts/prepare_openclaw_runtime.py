#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 内嵌运行时准备脚本

打包前运行，下载 Node.js 便携版并安装 OpenClaw 到 frontend/backend-dist/openclaw-runtime/。
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

# 下载缓存目录
CACHE_DIR = PROJECT_ROOT / ".cache"


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


# ============ 步骤 3: 安装 OpenClaw ============

def install_openclaw() -> None:
    """在 OPENCLAW_DIR 中 npm install openclaw@latest"""
    if OPENCLAW_DIR.exists():
        log(f"清理旧目录: {OPENCLAW_DIR}")
        shutil.rmtree(OPENCLAW_DIR)

    OPENCLAW_DIR.mkdir(parents=True, exist_ok=True)

    # 创建 package.json
    pkg_json = OPENCLAW_DIR / "package.json"
    pkg_json.write_text(
        '{"name": "openclaw-embedded", "private": true}',
        encoding="utf-8",
    )

    npm_cmd = str(NODE_DIR / "npm.cmd")
    node_exe = str(NODE_DIR / "node.exe")

    # 构建环境变量，确保使用内嵌 node
    env = os.environ.copy()
    env["PATH"] = f"{NODE_DIR}{os.pathsep}{env.get('PATH', '')}"

    log("安装 openclaw@latest ...")
    subprocess.run(
        [npm_cmd, "install", "openclaw@latest"],
        cwd=str(OPENCLAW_DIR),
        env=env,
        check=True,
    )

    # 验证
    openclaw_cmd = OPENCLAW_DIR / "node_modules" / ".bin" / "openclaw.cmd"
    clawhub_cmd = OPENCLAW_DIR / "node_modules" / ".bin" / "clawhub.cmd"
    if not openclaw_cmd.exists():
        raise FileNotFoundError(f"安装后未找到 {openclaw_cmd}")
    log(f"  openclaw.cmd: {openclaw_cmd}")
    log(f"  clawhub.cmd:  {clawhub_cmd} (exists={clawhub_cmd.exists()})")


# ============ 步骤 4: 清理不必要文件 ============

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


# ============ 步骤 5: 汇总 ============

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
    log(f"项目根目录: {PROJECT_ROOT}")
    log(f"输出目录:   {OUTPUT_DIR}")
    log("")

    zip_path = download_node()
    extract_node(zip_path)
    install_openclaw()
    cleanup()

    log("")
    print_summary()
    log("")
    log("准备完成！可以继续执行打包流程。")


if __name__ == "__main__":
    main()
