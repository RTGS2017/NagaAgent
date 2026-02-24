# NagaAgent Windows 打包指南

## 环境要求

| 工具 | 版本 | 安装方式 |
|------|------|----------|
| Python | >= 3.11, < 3.12 | [python.org](https://www.python.org/downloads/) |
| uv | latest | `pip install uv` |
| Node.js | >= 22 | [nodejs.org](https://nodejs.org/) |
| npm | >= 10 | 随 Node.js 安装 |
| Git | latest | [git-scm.com](https://git-scm.com/) |

> 打包机必须是 Windows x64 系统。

## 一键打包

项目提供自动化脚本，一条命令完成全流程：

```powershell
# 完整构建（推荐）
python scripts/build-win.py

# 调试模式（安装后弹出后端日志终端）
python scripts/build-win.py --debug

# 仅编译后端（跳过 Electron 打包）
python scripts/build-win.py --backend-only

# 跳过 OpenClaw 运行时准备（加速重复构建）
python scripts/build-win.py --skip-openclaw
```

## 手动分步构建

如需手动控制每个阶段，按以下步骤操作：

### Step 1: 同步 Python 依赖

```powershell
cd <项目根目录>
uv sync --group build
```

这会安装所有运行时依赖 + PyInstaller。

### Step 2: 准备 OpenClaw 运行时

OpenClaw 需要独立的 Node.js 运行时。打包时预装可避免用户首次启动等待。

```powershell
# 下载 Node.js v22.13.1 便携版
# 手动下载: https://nodejs.org/dist/v22.13.1/node-v22.13.1-win-x64.zip
# 解压到: frontend/backend-dist/openclaw-runtime/node/

# 用内嵌 Node.js 预装 OpenClaw
cd frontend/backend-dist/openclaw-runtime
..\openclaw-runtime\node\npm.cmd install openclaw --location=project
```

预装完成后目录结构：

```
frontend/backend-dist/openclaw-runtime/
  node/             # Node.js v22.13.1 便携版
    node.exe
    npm.cmd
    ...
  openclaw/         # 预装的 OpenClaw
    node_modules/
    package.json
    package-lock.json
```

> 如果 `node_modules/.bin/openclaw.cmd` 未自动生成，脚本会自动补一个 shim。

### Step 3: PyInstaller 编译后端

```powershell
cd <项目根目录>

uv run pyinstaller naga-backend.spec ^
  --distpath frontend/backend-dist ^
  --clean -y
```

产物位于 `frontend/backend-dist/naga-backend/naga-backend.exe`。

编译配置说明（`naga-backend.spec`）：
- 入口文件：`main.py`（以 `--headless` 模式运行，无 PyQt UI）
- 打包数据：`system/prompts/`、`config.json`、`agentserver/`、`apiserver/`、`voice/`、`skills/` 等
- 排除大型库：PyQt5、torch、tensorflow、scipy、pandas、matplotlib 等（减小体积）
- 输出模式：`COLLECT`（目录形式，非单文件）

### Step 4: 安装前端依赖

```powershell
cd frontend
npm install
```

### Step 5: Electron 打包

```powershell
cd frontend

# 构建 Vue 前端 + Electron 打包
npm run dist:win
```

等效于依次执行：
1. `vue-tsc -b` — TypeScript 类型检查
2. `vite build` — 构建 Vue SPA + Electron main/preload
3. `electron-builder --win` — 打 NSIS 安装包

### Step 6: 获取产物

```
frontend/release/
  Naga Agent Setup 5.1.0.exe    # NSIS 安装包
  Naga Agent Setup 5.1.0.exe.blockmap
```

## 产物结构

安装后的目录结构：

```
Naga Agent/
  Naga Agent.exe               # Electron 主进程
  resources/
    app.asar                   # Vue 前端 + Electron 代码
    backend/                   # PyInstaller 后端二进制
      naga-backend.exe
      ...（依赖库）
    openclaw-runtime/          # OpenClaw 运行时
      node/                    # Node.js 便携版
      openclaw/                # 预装的 OpenClaw
      LICENSE
```

## 常见问题

### PyInstaller 编译报 ModuleNotFoundError

在 `naga-backend.spec` 的 `hiddenimports` 列表中添加缺失的模块名。

### Electron 打包时找不到后端二进制

确保 `frontend/backend-dist/naga-backend/naga-backend.exe` 存在。`electron-builder.yml` 中 `extraResources` 配置了从该路径打包。

### 安装包体积过大

- 检查 `naga-backend.spec` 的 `excludes` 列表，确认大型库已排除
- 检查 `electron-builder.yml` 的 `files` 排除规则
- 用 `--skip-openclaw` 跳过 OpenClaw 运行时（约 80MB）

### OpenClaw 首次启动卡住

如果未预装 OpenClaw 运行时，首次启动会下载 Node.js + 安装 OpenClaw，可能需要几分钟。建议构建时不要 `--skip-openclaw`。

### 代码签名

当前配置未启用代码签名（`identity: null`）。Windows SmartScreen 可能拦截未签名的安装包。如需签名，在 `electron-builder.yml` 中配置证书：

```yaml
win:
  certificateFile: path/to/cert.pfx
  certificatePassword: xxx
```
