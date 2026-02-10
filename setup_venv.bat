@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================
echo   NagaAgent 虚拟环境重配
echo ========================================
echo.

REM 是否删除已有 .venv 并重建
if exist ".venv" (
    set /p RECREATE="已存在 .venv，是否删除并重建？(y/N): "
    if /i "!RECREATE!"=="y" (
        echo 正在删除旧虚拟环境...
        rmdir /s /q .venv
        echo 已删除。
    ) else (
        echo 保留现有 .venv，仅重新安装依赖。
    )
)

REM 若不存在则创建虚拟环境
if not exist ".venv" (
    echo 检测 Python 版本...
    python --version 2>nul
    if errorlevel 1 (
        echo [错误] 未找到 python，请先安装 Python 3.11 并加入 PATH
        pause
        exit /b 1
    )
    echo 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [OK] 虚拟环境已创建
)

call .venv\Scripts\activate.bat
echo.
echo 使用 pip 安装依赖（requirements.txt）...
python -m pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 虚拟环境重配完成。激活方式：
echo   .\.venv\Scripts\activate
echo 然后可运行: python main.py 或 start.bat
echo ========================================
pause
