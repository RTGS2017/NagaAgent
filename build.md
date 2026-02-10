# Windows 打包说明（NagaAgent 本体）

## 概述

当前打包流程仅包含 NagaAgent 本体：
- 后端：`naga-backend`（PyInstaller）
- 前端：Electron 应用（electron-builder）

不再包含任何 OpenClaw 运行时准备、内嵌或安装步骤。

## 一键打包

在 Windows 环境执行：

```bash
python build.py
```

可选参数：

```bash
python build.py --skip-clean
python build.py --skip-backend
python build.py --skip-frontend
```

## 分步打包

### 1) 编译后端

```bash
uv sync --group build
uv run pyinstaller naga-backend.spec --clean --noconfirm
```

后端产物：
- `dist/naga-backend/`
- 并复制到 `frontend/backend-dist/naga-backend/`

### 2) 打包前端

```bash
cd frontend
npm install
npm run build
npx electron-builder --win
```

安装包产物：
- `frontend/release/`

## 安装后目录检查

安装后，`resources` 目录应包含后端资源：

```text
Naga Agent/
  resources/
    backend/
      naga-backend.exe
      _internal/
```

不应包含额外运行时目录。
