# NagaAgent API 服务器

智能对话助手的 RESTful API 服务层，基于 FastAPI 构建。

## 目录结构

```
apiserver/
├── api_server.py               # 应用入口：FastAPI 实例、中间件、lifespan、公共模型
├── routes/                     # 路由模块（按功能域拆分）
│   ├── chat.py                 #   核心对话（/chat, /chat/stream）
│   ├── auth.py                 #   认证 + TTS/ASR 代理
│   ├── session.py              #   会话 CRUD
│   ├── system.py               #   系统信息 / 配置 / 健康检查 / 日志
│   ├── tools.py                #   工具状态 / 队列 / 前端轮询 / WebSocket
│   ├── extensions.py           #   OpenClaw / MCP / 技能 / 文档上传 / 旅行 / 记忆
│   └── forum.py                #   社区论坛代理（透传 NagaBusiness）
├── llm_service.py              # LLM 调用服务（挂载在 /llm）
├── message_manager.py          # 会话与消息统一管理
├── agentic_tool_loop.py        # Agentic 工具调用循环
├── intent_router.py            # 意图路由
├── context_compressor.py       # 上下文压缩
├── streaming_tool_extractor.py # 流式文本处理（句子切割 / TTS 推送）
├── response_util.py            # 响应解析工具
├── message_queue.py            # 消息队列
├── naga_auth.py                # NagaCAS 认证模块
├── naga_control.py             # 运行时控制（语音暂停等）
├── websocket_manager.py        # WebSocket 连接管理
├── travel_service.py           # 旅行功能服务
├── start_server.py             # 统一启动脚本
└── skills_templates/           # 内置技能模板
```

## API 接口总览

### 对话 — `routes/chat.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat` | 普通对话 |
| POST | `/chat/stream` | 流式对话（SSE），支持 Agentic 工具调用循环 |

**请求体** (`ChatRequest`)：
```json
{
  "message": "用户消息",
  "stream": false,
  "session_id": "可选会话ID",
  "disable_tts": false,
  "return_audio": false,
  "skill": "可选技能名称",
  "images": ["base64图片数据"],
  "temporary": false
}
```

### 认证 & 音频代理 — `routes/auth.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 登录 |
| GET  | `/auth/me` | 获取当前用户信息 |
| POST | `/auth/logout` | 登出 |
| POST | `/auth/register` | 注册 |
| GET  | `/auth/captcha` | 获取验证码 |
| POST | `/auth/send-verification` | 发送邮箱验证码 |
| POST | `/auth/refresh` | 刷新 Token |
| POST | `/tts/speech` | TTS 语音合成代理 |
| POST | `/asr/transcribe` | ASR 语音识别代理 |

### 会话管理 — `routes/session.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET    | `/sessions` | 获取所有会话列表 |
| GET    | `/sessions/{session_id}` | 获取会话详情 |
| DELETE | `/sessions/{session_id}` | 删除指定会话 |
| DELETE | `/sessions` | 清空所有会话 |

### 系统管理 — `routes/system.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/` | API 根路径 |
| GET  | `/health` | 健康检查 |
| GET  | `/health/full` | 完整健康检查（联动 Agent Server） |
| GET  | `/system/info` | 系统信息（版本、状态） |
| GET  | `/system/config` | 获取完整配置 |
| POST | `/system/config` | 更新配置 |
| GET  | `/system/prompt` | 获取系统提示词 |
| POST | `/system/prompt` | 更新系统提示词 |
| GET  | `/system/character` | 获取当前活跃角色信息 |
| GET  | `/update/latest` | 检查版本更新 |
| GET  | `/logs/context/statistics` | 日志上下文统计 |
| GET  | `/logs/context/load` | 加载日志上下文 |

`/system/config` 会读写用户数据目录中的运行时 `config.json`；缺失时由配置模板自动生成。模型连接字段包括 `api.provider`、`api.model`、`api.api_format` 和 `api.use_gateway`，用于区分本地模型供应商与 NagaModel 网关。保存配置时会过滤角色/自定义 Live2D 的运行时 `model.source`，只持久化 `custom_model_id` 等稳定字段；历史 `agentserver` / `mcpserver` 键会归一为 `agent_server` / `mcp_server`。

未登录且 `api.use_gateway=false` 时，OpenAI 兼容代理只接受真实本地 API 配置；`your-api-key-here` 与 `sk-placeholder-key-not-set` 会被识别为占位值并返回配置错误。

OpenClaw 配置桥接会在生成、迁移或注入配置时补齐 `gateway.mode=local`、当前 `gateway.port`、`hooks.path=/hooks` 与 `hooks.allowRequestSessionKey=true`，保证 `/hooks/agent` 和 sessionKey 调度链路可用。

### 工具 & WebSocket — `routes/tools.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/queue/push` | 推送消息到队列 |
| POST | `/tool_notification` | 工具调用状态通知 |
| POST | `/tool_result_callback` | 工具结果回调 |
| POST | `/tool_result` | 接收工具执行结果 |
| POST | `/save_tool_conversation` | 保存工具对话 |
| POST | `/ui_notification` | 前端 UI 通知控制 |
| POST | `/proactive_message` | 接收主动消息 |
| GET  | `/tool_status` | 工具状态轮询 |
| GET  | `/clawdbot/replies` | AgentServer 回复轮询 |
| GET  | `/live2d/actions` | Live2D 动作轮询 |
| GET  | `/music/commands` | 音乐指令轮询 |
| WS   | `/ws` | WebSocket 实时通信 |
| GET  | `/ws/stats` | WebSocket 连接统计 |
| POST | `/ws/broadcast` | WebSocket 广播 |

`/ui_notification` 支持 `show_mcp_result`，用于 MCP Server callback 将工具结果写入前端回复队列；前端会按 `tool-result` 结构折叠展示。工具通知、工具结果和 UI 通知接口会保留缺少参数等显式 `400` 错误，避免被统一包装成 `500`。

### 扩展功能 — `routes/extensions.py`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/openclaw/market/items` | OpenClaw 市场列表 |
| POST | `/openclaw/market/items/{id}/install` | 安装市场组件 |
| GET  | `/openclaw/tasks` | OpenClaw 任务列表 |
| GET  | `/openclaw/tasks/{task_id}` | 任务详情 |
| GET  | `/mcp/status` | MCP 服务状态 |
| GET  | `/mcp/tasks` | MCP 任务列表 |
| GET  | `/mcp/services` | MCP 服务列表 |
| POST | `/mcp/import` | 导入 MCP 配置 |
| PUT  | `/mcp/services/{name}` | 更新 MCP 服务 |
| DELETE | `/mcp/services/{name}` | 删除 MCP 服务 |
| POST | `/skills/import` | 导入自定义技能 |
| POST | `/upload/document` | 上传文档 |
| POST | `/upload/parse` | 上传并解析文档 |
| POST | `/travel/start` | 开始旅行会话 |
| GET  | `/travel/status` | 旅行状态 |
| POST | `/travel/stop` | 停止旅行会话 |
| GET  | `/travel/history` | 旅行历史列表 |
| GET  | `/travel/history/{session_id}` | 旅行历史详情 |
| POST | `/travel/sessions/{session_id}/browser` | 更新探索浏览器策略 |
| GET  | `/memory/stats` | 记忆系统统计 |
| GET  | `/memory/quintuples` | 获取五元组 |

技能管理接口会将 `name` 当作技能目录标识处理，只允许单段名称；空名称、`.`、`..`、包含 `/` 或 `\`、绝对路径、Windows 盘符路径和控制字符会被拒绝，避免写入、读取或删除越过技能目录边界。
| GET  | `/memory/quintuples/search` | 搜索五元组 |
| GET/POST | `/tools/search` | 搜索代理 |

旅行会话支持运行中更新 `browser_visible`、`browser_keep_open` 与 `browser_idle_timeout_seconds`；前端 `/forum/quota` 会同步这些设置并提供原始历史查看入口，用于排查 OpenClaw session 消息链路。

### 社区论坛 — `routes/forum.py`

所有 `/forum/api/*` 端点均为 NagaBusiness 服务的透传代理，包括帖子、评论、点赞、好友、消息、通知等 23 个接口。

## 架构说明

### 模块化路由

`api_server.py` 是应用入口，负责：
- FastAPI 实例创建与 lifespan 管理
- CORS 中间件 + Token 同步中间件
- 静态文件挂载（`/characters`）
- 公共辅助函数（`_call_agentserver`、`_save_conversation_and_logs` 等）
- Pydantic 请求/响应模型定义
- 统一注册所有 `APIRouter`

路由模块按功能域拆分到 `routes/` 目录下，各模块通过 `from apiserver.api_server import ...` 引用共享状态和公共函数。

### 相关服务

| 服务 | 说明 |
|------|------|
| `agentserver/` | 任务调度、智能体管理（独立进程） |
| `mcpserver/` | MCP 服务管理（独立进程） |
| `system/` | 配置系统、提示词仓库 |

### 对话处理流程

1. 用户发送消息到 `/chat` 或 `/chat/stream`
2. 构建系统提示词（角色 + 技能 + 上下文补充）
3. 调用 LLM API 获取回复
4. 若包含工具调用，进入 Agentic 工具调用循环
5. 流式模式下通过 SSE 实时推送文本片段
6. 保存对话历史与日志

## 启动方式

```bash
# 通过统一启动脚本
python apiserver/start_server.py api

# 直接使用 uvicorn
uvicorn apiserver.api_server:app --host 127.0.0.1 --port 8000
```

## 冒烟验证

```bash
# 无账号：启动缺失的本地后端并验证未登录、本地配置、工具通知和 OpenClaw 代理链路
uv run python scripts/smoke_backend.py --skip-auth --start-if-needed

# 有 NagaCAS 账号：额外验证验证码、登录和 /auth/me
uv run python scripts/smoke_backend.py --username "$NAGA_SMOKE_USERNAME" --password "$NAGA_SMOKE_PASSWORD" --start-if-needed
```

## 代理问题

如果使用了网络代理，测试本地 API 时需要绕过：
```bash
NO_PROXY="127.0.0.1,localhost" curl -X GET "http://127.0.0.1:8000/health"
```
