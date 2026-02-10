#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 内嵌运行时准备脚本

打包前运行：下载 Node.js 便携版到 frontend/backend-dist/openclaw-runtime/node/
首次启动时由 embedded_runtime.install_openclaw() 通过内嵌 npm 安装 openclaw。

用法: python scripts/prepare_openclaw_runtime.py
"""

import shutil
import zipfile
import urllib.request
from pathlib import Path

# ============ 配置 ============

NODE_VERSION = "22.13.1"
NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"

# 输出目录（相对于项目根目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "backend-dist" / "openclaw-runtime"
NODE_DIR = OUTPUT_DIR / "node"

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


# ============ 汇总 ============

def print_summary() -> None:
    """打印最终目录结构和大小"""
    if not OUTPUT_DIR.exists():
        log("输出目录不存在")
        return
    total = sum(f.stat().st_size for f in OUTPUT_DIR.rglob("*") if f.is_file())
    log(f"运行时总大小: {total / 1024 / 1024:.1f} MB")
    log(f"输出目录: {OUTPUT_DIR}")
    log("目录结构:")
    log(f"  node/  (首次启动时 npm install openclaw 会创建 openclaw/ 目录)")
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

    log("")
    print_summary()
    log("")
    log("准备完成！首次启动时将通过内嵌 npm 自动安装 openclaw。")


if __name__ == "__main__":
    main()
