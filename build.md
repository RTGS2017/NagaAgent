# OpenClaw 内嵌打包测试指南

## 概述

本次变更将 OpenClaw 运行时（Node.js + OpenClaw npm 包）内嵌到打包产物中，使用户无需预先安装 Node.js 和 OpenClaw 即可使用 OpenClaw 调度功能。

## 打包前准备

### 1. 准备 OpenClaw 运行时

在 Windows 环境下执行：

```bash
python scripts/prepare_openclaw_runtime.py
```

该脚本会：
- 下载 Node.js v22 LTS 便携版 (win-x64)
- 在 `frontend/backend-dist/openclaw-runtime/openclaw/` 中安装 `openclaw@latest`
- 清理不必要文件减小体积

执行完成后确认目录结构：

```
frontend/backend-dist/openclaw-runtime/
  node/
    node.exe
    npm.cmd
    node_modules/npm/
  openclaw/
    package.json
    node_modules/
      .bin/openclaw.cmd
      .bin/clawhub.cmd
```

### 2. 编译后端

```bash
uv sync
uv pip install pyinstaller
uv run pyinstaller naga-backend.spec
xcopy /E /I dist\naga-backend frontend\backend-dist\naga-backend
```

### 3. 打包 Electron 应用

```bash
cd frontend
npm install
npm run build
npx electron-builder --win
```

产物位于 `frontend/release/Naga Agent Setup 1.0.0.exe`。

## 测试项

### 测试 1：安装后目录结构验证

安装 exe 后，检查安装目录：

```
Naga Agent/
  resources/
    backend/
      naga-backend.exe
      _internal/
    openclaw-runtime/        <-- 新增
      node/
        node.exe
        npm.cmd
      openclaw/
        node_modules/
          .bin/openclaw.cmd
          .bin/clawhub.cmd
```

**通过标准**：`openclaw-runtime` 目录存在且包含上述文件。

### 测试 2：开发环境兼容性

在开发环境（未打包）下运行：

```bash
uv run main.py
```

**通过标准**：
- agentserver 正常启动，无报错
- 如果系统已安装 OpenClaw，功能正常
- 如果系统未安装 OpenClaw，行为与之前一致（提示未安装）

### 测试 3：打包环境 Gateway 自动启动

在一台**未安装 Node.js 和 OpenClaw** 的 Windows 机器上安装并启动应用。

**通过标准**：
- 应用正常启动
- agentserver 日志中出现 `内嵌运行时目录: ...`
- 日志中出现 `内嵌 OpenClaw Gateway 已启动`
- 访问 `http://127.0.0.1:8001/openclaw/health` 返回正常状态

### 测试 4：首次运行自动 onboard

在一台没有 `~/.openclaw/` 目录的机器上首次启动。

**通过标准**：
- 日志中出现 `首次运行，执行 openclaw onboard 初始化...`
- 日志中出现 `OpenClaw onboard 初始化完成`
- `~/.openclaw/openclaw.json` 文件被自动创建

### 测试 5：端口冲突处理

先手动启动一个 OpenClaw Gateway（占用 18789 端口），再启动应用。

**通过标准**：
- 日志中出现 `端口 18789 已被占用，跳过内嵌 Gateway 启动`
- 应用正常运行，使用已有的 Gateway

### 测试 6：应用关闭时 Gateway 停止

正常关闭应用。

**通过标准**：
- 日志中出现 `正在停止内嵌 OpenClaw Gateway...`
- 日志中出现 `内嵌 OpenClaw Gateway 已停止`
- 端口 18789 被释放

### 测试 7：OpenClaw 功能验证

在打包环境下测试 OpenClaw 核心功能：

1. 访问 `http://127.0.0.1:8001/openclaw/install/check` — 应返回 `status: "installed"`
2. 访问 `http://127.0.0.1:8001/openclaw/gateway/status` — 应返回 `running: true`
3. 访问 `http://127.0.0.1:8001/openclaw/doctor` — 应返回 `healthy: true`
4. 通过前端界面发送 OpenClaw 消息，确认调度功能正常

## 变更文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agentserver/openclaw/embedded_runtime.py` | 新建 | 内嵌运行时管理核心模块 |
| `scripts/prepare_openclaw_runtime.py` | 新建 | 打包前运行时准备脚本 |
| `agentserver/openclaw/installer.py` | 修改 | 所有命令调用改为通过 EmbeddedRuntime |
| `agentserver/openclaw/detector.py` | 修改 | 打包环境下标记已安装 |
| `agentserver/agent_server.py` | 修改 | 自动启动/停止内嵌 Gateway |
| `agentserver/openclaw/__init__.py` | 修改 | 导出新模块 |
| `frontend/electron-builder.yml` | 修改 | extraResources 新增 openclaw-runtime |
