# Windows: OpenClaw 内嵌打包测试指南

## 概述

打包产物中内嵌 Node.js 便携版，首次启动时通过内嵌 npm 自动执行 `npm install openclaw`。

支持两层回退策略：
1. **全局安装**：openclaw 在 PATH 中 → 优先使用
2. **打包环境**：内嵌 Node.js + 运行时自动安装 openclaw

## 打包前准备

### 1. 准备 Node.js 便携版

在 Windows 环境下执行：

```bash
python scripts/prepare_openclaw_runtime.py
```

该脚本会：
- 下载 Node.js v22 LTS 便携版 (win-x64)
- 解压到 `frontend/backend-dist/openclaw-runtime/node/`

> OpenClaw 本身不再在构建时安装，首次启动时由内嵌 npm 自动执行 `npm install openclaw`。

执行完成后确认目录结构：

```
frontend/backend-dist/openclaw-runtime/
  node/
    node.exe
    npm.cmd
    ...
```

### 2. 编译后端

```bash
uv sync --group build
.\.venv\Scripts\activate
uv run pyinstaller naga-backend.spec --clean --noconfirm
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
    openclaw-runtime/
      node/
        node.exe
        npm.cmd
```

**通过标准**：`openclaw-runtime/node/` 目录存在且包含 `node.exe`。首次启动后会自动创建 `openclaw/` 目录。

### 测试 2：开发环境兼容性

在开发环境（未打包）下运行：

```bash
uv run main.py
```

**通过标准**：
- agentserver 正常启动，无报错
- 如果系统已安装 OpenClaw，功能正常（全局模式）
- 如果系统未安装 OpenClaw 且有 npm，自动尝试 `npm install -g openclaw`
- 日志中出现 `OpenClaw 运行时模式: global` 或 `unavailable`

### 测试 3：打包环境 Gateway 自动启动

在一台**未安装 Node.js 和 OpenClaw** 的 Windows 机器上安装并启动应用。

**通过标准**：
- 应用正常启动
- agentserver 日志中出现 `首次启动：正在安装 OpenClaw，请稍候...`
- 日志中出现 `OpenClaw 安装成功`
- 日志中出现 `内嵌 OpenClaw Gateway 已启动`
- 访问 `http://127.0.0.1:8001/openclaw/health` 返回正常状态

### 测试 4：首次运行自动配置生成

在一台没有 `~/.openclaw/` 目录的机器上首次启动。

**通过标准**：
- 日志中出现 `已自动生成 openclaw.json`
- 日志中出现 `已注入 Naga LLM 配置`
- `~/.openclaw/openclaw.json` 文件被自动创建
- 配置中包含 Naga 的 LLM provider 信息

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
| `agentserver/openclaw/llm_config_bridge.py` | 新建 | 配置自动生成 + LLM 桥接 |
| `system/logging_setup.py` | 新建 | 统一日志管理（文件轮转 + OpenClaw 专用日志） |
| `agentserver/openclaw/embedded_runtime.py` | 修改 | 打包环境运行时自动安装 openclaw |
| `agentserver/openclaw/detector.py` | 修改 | 打包环境检测 |
| `agentserver/openclaw/installer.py` | 修改 | 安装检测简化 |
| `agentserver/openclaw/__init__.py` | 修改 | 移除 source_runtime 导出 |
| `agentserver/agent_server.py` | 修改 | 两层回退启动流程 + 运行时按需安装 |
| `scripts/prepare_openclaw_runtime.py` | 修改 | 简化为仅下载 Node.js 便携版 |
| `scripts/build-win.py` | 修改 | 移除 submodule 检查，简化 openclaw 步骤 |
| `agentserver/openclaw/source_runtime.py` | 删除 | 不再需要 submodule 源码模式 |
| `main.py` | 修改 | 调用 setup_logging() 统一日志 |
| `build.md` | 修改 | 更新打包说明 |
