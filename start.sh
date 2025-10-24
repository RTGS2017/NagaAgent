#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/.venv"
VENV_PY="$VENV/bin/python"

if [ -x "$VENV_PY" ]; then
    # 将所有传入参数传给 main.py
    exec "$VENV_PY" "$DIR/main.py" "$@"
else
    echo "❌ 未检测到虚拟环境，请先运行 setup.bat 进行初始化，或手动配置。" >&2
    exit 2
fi