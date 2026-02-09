#!/bin/bash
# 编译 NagaAgent 后端为独立二进制
# 产物目录: frontend/backend-dist/naga-backend/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Building NagaAgent Backend ==="
echo "Project root: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "❌ PyInstaller not found. Install with: pip install pyinstaller"
    exit 1
fi

# 编译
pyinstaller naga-backend.spec \
    --distpath frontend/backend-dist \
    --workpath build/pyinstaller \
    --clean -y

echo ""
echo "✅ Backend built successfully!"
echo "   Output: frontend/backend-dist/naga-backend/"
echo ""
echo "   Test with: ./frontend/backend-dist/naga-backend/naga-backend --headless"
