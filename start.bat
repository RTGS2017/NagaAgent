@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM 激活虚拟环境（若存在）
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo ========================================
echo   NagaAgent 启动脚本（后端 + 前端）
echo ========================================
echo.

REM 启动后端（新窗口，保持打开）
start "NagaAgent-Backend" cmd /k "cd /d "%~dp0" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python main.py"
echo [OK] 后端已在独立窗口启动
echo.

REM 等待后端服务就绪
echo 等待后端初始化（约 5 秒）...
timeout /t 5 /nobreak >nul

REM 启动前端（若存在 frontend 且已安装依赖）
if exist "frontend\package.json" (
    if exist "frontend\node_modules" (
        start "NagaAgent-Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
        echo [OK] 前端已在独立窗口启动
    ) else (
        echo [提示] 前端依赖未安装，请先执行: cd frontend ^&^& npm install
        echo 当前仅后端已启动。
    )
) else (
    echo [提示] 未检测到 frontend 目录，仅后端已启动。
)

echo.
echo ========================================
echo 后端窗口请勿关闭；使用 Electron 前端时请保持前端窗口打开。
echo 关闭时请分别在各窗口按 Ctrl+C 或关闭窗口。
echo ========================================
pause
