#!/bin/bash
# NagaAgent 3.0 Setup Script for macOS/Linux
# Version managed by config.py

set -e

PYTHON_MIN_VERSION="3.10"
VENV_PATH=".venv"

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
if [[ $(printf '%s\n' "$PYTHON_MIN_VERSION" "$PYTHON_VERSION" | sort -V | head -n1) != "$PYTHON_MIN_VERSION" ]]; then
    echo "Python $PYTHON_MIN_VERSION or higher required, current version: $PYTHON_VERSION"
    exit 1
fi
echo "Python version check passed: $PYTHON_VERSION"

# 设置工作目录为脚本所在目录
cd "$(dirname "$0")"

# 删除旧虚拟环境
if [ -d "$VENV_PATH" ]; then
    echo "Removing existing virtual environment for clean install..."
    rm -rf "$VENV_PATH"
    echo "Old virtual environment removed successfully"
fi

# 创建新虚拟环境
echo "Creating fresh virtual environment..."
python3 -m venv "$VENV_PATH"
echo "Virtual environment created successfully"

# 激活虚拟环境
source "$VENV_PATH/bin/activate"
echo "Virtual environment activated successfully"

# 升级 pip
echo "Upgrading pip..."
pip install --upgrade pip

# 安装 setuptools 和 wheel
echo "Installing setuptools and wheel..."
pip install setuptools wheel

# 安装核心依赖
echo "Installing core dependencies (numpy, pandas, scipy)..."
pip install numpy pandas scipy

# 安装基础依赖
echo "Installing basic dependencies..."
pip install mcp openai openai-agents python-dotenv requests aiohttp pytz colorama python-dateutil

# 安装 GRAG 知识图谱依赖
echo "Installing GRAG knowledge graph dependencies..."
pip install py2neo pyvis matplotlib

# 安装 API server 依赖
echo "Installing API server dependencies..."
pip install flask-cors flask gevent fastapi

# 安装网络通信依赖
echo "Installing network communication dependencies..."
pip install librosa websockets

# 安装 AI/ML 依赖
echo "Installing AI/ML dependencies..."
pip install transformers

# 安装 GUI 依赖
echo "Installing GUI dependencies..."
pip install playwright greenlet pyee pygame html2text

# 安装 PyQt5
echo "Installing PyQt5..."
pip install PyQt5==5.15.11

# 安装音频处理依赖
echo "Installing audio processing dependencies..."
pip install sounddevice pyaudio edge-tts emoji

# 安装系统托盘依赖
echo "Installing system tray dependencies..."
pip install pystray

# 安装系统控制依赖
echo "Installing system control dependencies..."
pip install screen-brightness-control pycaw comtypes

# 安装 MCP 工具依赖
echo "Installing MCP tool dependencies..."
pip install jmcomic fastmcp

# 安装 MQTT 通信依赖
echo "Installing MQTT communication dependencies..."
pip install paho-mqtt

# 安装其他工具依赖
echo "Installing other tool dependencies..."
pip install tiktoken python-docx

# 安装 playwright 浏览器驱动
echo "Installing playwright browser drivers..."
python3 -m playwright install chromium

# 生成已安装依赖列表
echo "Generating installed requirements file..."
pip freeze > requirements_installed.txt

echo -e "\nEnvironment setup completed!"
echo "To install other browser drivers, run:"
echo "python3 -m playwright install firefox  # Install Firefox"
echo "python3 -m playwright install webkit   # Install WebKit"
echo -e "\nTo activate virtual environment manually, run:"
echo "source .venv/bin/activate"
echo -e "\nTo check installed packages, run:"
echo "pip list"
echo -e "\nTo deactivate virtual environment, run:"
echo "deactivate"
echo -e "\nSetup Summary:"
echo "- Virtual environment: $VENV_PATH"
echo "- Python version: $PYTHON_VERSION"
echo "- All core dependencies installed"
echo "- Playwright browser drivers ready"