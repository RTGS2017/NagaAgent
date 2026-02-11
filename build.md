# Windows 打包说明（OpenClaw 预装）

## 概述

Windows 安装包在构建阶段会预装 OpenClaw，用户安装后首次启动不再执行 `npm install openclaw`。

打包后启动策略：

1. 如果用户本机已安装全局 `openclaw`，优先使用全局版本。
2. 如果用户本机未安装全局 `openclaw`，自动使用安装包内置的预装 OpenClaw。
3. 使用内置 OpenClaw 时，会自动生成 `~/.openclaw/openclaw.json` 并注入 Naga LLM 配置。

卸载行为：

- 若运行时判定使用的是内嵌 OpenClaw，会写入安装状态，卸载程序会清理 `~/.openclaw`。
- 若运行时使用的是用户全局 OpenClaw，不会触发该清理逻辑。

## 一键构建（推荐）

在 Windows 环境执行：

```bash
python scripts/build-win.py
```

常用参数：

- `--backend-only`：仅构建后端，不打包 Electron
- `--skip-openclaw`：跳过 OpenClaw 运行时准备（不建议发布包使用）
- `--debug`：安装后启动时弹出后端日志终端

## 构建流程

`scripts/build-win.py` 会自动执行：

1. 检查 Python / uv / Node.js / npm 环境
2. `uv sync --group build`
3. 下载并解压 Node.js 便携版到 `frontend/backend-dist/openclaw-runtime/node/`
4. 在 `frontend/backend-dist/openclaw-runtime/openclaw/` 预装 OpenClaw
5. 使用 PyInstaller 构建后端
6. 使用 electron-builder 生成 Windows 安装包

## 产物校验

安装包构建完成后，检查以下关键文件：

- `frontend/backend-dist/naga-backend/naga-backend.exe`
- `frontend/backend-dist/openclaw-runtime/node/node.exe`
- `frontend/backend-dist/openclaw-runtime/node/npm.cmd`
- `frontend/backend-dist/openclaw-runtime/openclaw/node_modules/.bin/openclaw.cmd`

Electron 安装包输出目录：`frontend/release/`

## 运行时验证

在一台未安装 Node.js / OpenClaw 的 Windows 机器上安装并启动，预期：

- 应用可正常启动
- 日志中不应出现首次启动安装 OpenClaw 的等待流程
- 日志出现“使用预装内嵌 OpenClaw”相关信息
- `~/.openclaw/openclaw.json` 自动生成
- 访问 `http://127.0.0.1:8001/openclaw/health` 返回正常
