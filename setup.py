import os
import platform
import subprocess
import shutil
import sys
from pathlib import Path
import re

def find_python_command(preferred_versions=None):
    """
    在 PATH 中查找可用的 python 可执行文件，并返回第一个匹配的命令及其版本输出。
    preferred_versions: 按优先级排列的命令列表（例如 ["python3.11", "python3", "python"]）
    返回 (命令, 版本输出字符串) 或 (None, None)
    """
    if preferred_versions is None:
        preferred_versions = ["python3.11", "python3", "python"]
    for cmd in preferred_versions:
        try:
            # 通过 `--version` 获取版本信息（部分 Python 将输出到 stderr）
            proc = subprocess.run([cmd, "--version"], capture_output=True, text=True)
            out = (proc.stdout or proc.stderr).strip()
            if out:
                return cmd, out
        except FileNotFoundError:
            # 命令不存在，继续尝试下一个
            continue
    return None, None

def parse_version(version_output: str):
    """
    从版本输出字符串中解析出版本号（匹配 X.Y 或 X.Y.Z）
    返回匹配的版本字符串或 None
    """
    m = re.search(r"(\d+\.\d+\.\d+|\d+\.\d+)", version_output)
    return m.group(1) if m else None

def is_python_compatible() -> tuple[bool, str]:
    """
    仅接受 Python 3.11（任何补丁版本）。返回 (是否兼容, 使用的 python 命令字符串 或 "")
    """
    cmd, out = find_python_command(["python3.11", "python3", "python"])
    if not cmd:
        return False, ""
    ver = parse_version(out) or ""
    try:
        parts = [int(x) for x in ver.split(".")]
    except Exception:
        return False, cmd
    # 仅允许 3.11.x
    if len(parts) >= 2 and parts[0] == 3 and parts[1] == 11:
        return True, cmd
    return False, cmd

def is_uv_available() -> bool:
    """
    检查是否安装并在 PATH 中可用的 `uv` 工具
    """
    proc = subprocess.run(["uv", "-V"], capture_output=True, text=True)
    out = (proc.stdout or proc.stderr).strip()
    if out:
        return True
    return False

if __name__ == "__main__":
    print("开始进行初始化")
    # 检测是否存在 uv，用于更快或统一的依赖同步方案
    uv = is_uv_available()
    if uv:
        print("   ✅ 检测到 uv，可用以同步依赖，跳过python版本检测")
    else:
        print("   ℹ️ 未检测到 uv，回退使用 pip/venv 安装")
    
    # 检查 Python 版本是否兼容
    if not uv:
        ok, python_cmd = is_python_compatible()
        if not ok:
            print("   ❌ 请安装 Python 3.11 并确保可执行文件在 PATH 中（尝试 python3.11/python3/python），或前往https://docs.astral.sh/uv/getting-started/installation/安装uv")
            sys.exit(1)
        print(f"   ✅ 使用 Python 可执行文件: {python_cmd}")

    repo_root = Path(__file__).parent.resolve()
    venv_dir = repo_root / ".venv"

    if uv:
        # 使用 uv 来同步依赖并安装 playwright 的 chromium
        try:
            subprocess.run(["uv", "sync"], check=True)
            subprocess.run(["uv", "run", "python", "-m", "playwright", "install", "chromium"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"   ❌ uv 操作失败: {e}")
            sys.exit(1)
    else:
        # 创建虚拟环境（venv）
        try:
            subprocess.run([python_cmd, "-m", "venv", str(venv_dir)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"   ❌ 创建虚拟环境失败: {e}")
            sys.exit(1)

        # 虚拟环境中 Python 可执行文件的路径（Windows 和类 Unix 不同）
        if platform.system() == "Windows":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        if not venv_python.exists():
            print("   ❌ 虚拟环境 Python 未找到，安装中断")
            sys.exit(1)

        # 升级 pip 并安装 requirements.txt 中的依赖，然后安装 playwright 的 chromium
        try:
            subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
            req_file = repo_root / "requirements.txt"
            if req_file.exists():
                subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(req_file)], check=True)
            else:
                # 如果没有 requirements.txt，则跳过 pip 安装
                print("   ⚠️ requirements.txt 未找到，跳过 pip 安装")
            subprocess.run([str(venv_python), "-m", "playwright", "install", "chromium"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"   ❌ 依赖安装失败: {e}")
            sys.exit(1)

    # 处理配置文件 config.json：如果不存在则从 config.json.example 复制一份
    cfg = repo_root / "config.json"
    example = repo_root / "config.json.example"
    if not cfg.exists():
        if example.exists():
            try:
                shutil.copyfile(str(example), str(cfg))
                print("   ✅ 已创建 config.json")
            except Exception as e:
                print(f"   ❌ 复制 config.json.example 失败: {e}")
                sys.exit(1)
        else:
            print("   ❌ config.json.example 不存在，无法创建 config.json")
            sys.exit(1)
    else:
        print("   ✅ config.json 已存在")

    # 使用系统默认编辑器打开 config.json，便于用户编辑
    print("   📥 使用系统默认编辑器打开 config.json，请根据需要进行修改")
    try:
        if platform.system() == "Windows":
            # Windows 下使用 os.startfile 打开文件
            os.startfile(str(cfg))
        elif platform.system() == "Darwin":
            # macOS 使用 open
            subprocess.run(["open", str(cfg)])
        else:
            # 大多数 Linux 发行版使用 xdg-open
            subprocess.run(["xdg-open", str(cfg)])
    except Exception as e:
        print(f"   ⚠️ 无法自动打开 config.json: {e}")
    print("初始化完成，可以启动程序（start.bat/sh）")
