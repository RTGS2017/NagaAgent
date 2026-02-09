#!/bin/bash
# NagaAgent 完整构建脚本
# 1. PyInstaller 编译 Python 后端
# 2. electron-builder 打包 Electron 前端 + 后端二进制
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "  NagaAgent Build Pipeline"
echo "=========================================="

# Step 1: 编译后端
echo ""
echo "=== Step 1: Build Python Backend ==="
"$SCRIPT_DIR/build-backend.sh"

# Step 2: 编译前端 + 打包
echo ""
echo "=== Step 2: Build Electron App ==="
cd "$PROJECT_ROOT/frontend"

# 确保依赖已安装
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# 构建 + 打包
npm run dist

echo ""
echo "=========================================="
echo "  Build Complete!"
echo "  Output: frontend/release/"
echo "=========================================="
