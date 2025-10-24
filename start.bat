@echo off
chcp 65001 > nul
if exist ".venv\" (
    .venv\Scripts\python.exe main.py
) else (
    echo "❌ 未检测到虚拟环境，请先运行 setup.bat 进行初始化，或手动配置。"
    pause > nul
)  