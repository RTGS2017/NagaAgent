<div align="center">

# NagaAgent

**四服务协同的 AI 桌面助手 — 流式工具调用 · 知识图谱记忆 · Live2D · 语音交互**

[简体中文](README.md)  | [English](README_en.md)

![NagaAgent](https://img.shields.io/badge/NagaAgent-5.1.0-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-AGPL%203.0%20%7C%20Proprietary-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)

[![Stars](https://img.shields.io/github/stars/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Forks](https://img.shields.io/github/forks/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Issues](https://img.shields.io/github/issues/Xxiii8322766509/NagaAgent)](https://github.com/Xxiii8322766509/NagaAgent/issues)

 **[QQ 机器人联动：Undefined QQbot](https://github.com/69gg/Undefined/)**


</div>

---

**双许可证** · 开源采用 [AGPL-3.0](LICENSE)，闭源采用 [专属许可](LICENSE-CLOSED-SOURCE)（需书面授权）。商业合作：contact@nagaagent.com / bilibili【柏斯阔落】

---

## 概述

NagaAgent 由四个独立微服务组成：

| 服务 | 端口 | 职责 |
|------|------|------|
| **API Server** | 8000 | 对话、流式工具调用、文档上传、认证代理、记忆 API、配置管理 |
| **Agent Server** | 8001 | 后台意图分析、OpenClaw 集成、任务调度与压缩记忆 |
| **MCP Server** | 8003 | MCP 工具注册/发现/并行调度 |
| **Voice Service** | 5048 | TTS (Edge-TTS) + ASR (FunASR) + 实时语音 (Qwen Omni) |

`main.py` 统一编排启动，所有服务以 daemon thread 运行。前端可选 Electron + Vue 3 桌面端或 PyQt5 原生 GUI。

---

## 更新日志

| 日期 | 内容 |
|------|------|
| **2026-02-16** | 5.0.0 发布：NagaModel 网关统一接入（TTS/Embeddings/WebSearch）、DeepSeek 推理思考过程实时展示、记忆云海 UI 自适应修复、BoxContainer noScroll 模式 |
| **2026-02-15** | 统一附加知识块 + 消除历史污染、LLM 流式重试、配置热更新修复、技能工坊加载优化、config.json 写入截断修复、七天自动登录 + 开机自启动 |
| **2026-02-14** | 远程记忆微服务（NagaMemory 云端 + 本地 GRAG 回退）、意识海 3D 重写、启动标题动画与粒子效果、进度条停滞检测与健康轮询、版本更新检查弹窗、用户使用协议 |
| **2026-02-13** | 悬浮球模式（4 状态动画）、截屏多模态视觉模型自动切换、技能工坊重构 + Live2D 表情通道独立、登录注册流程完善 |
| **2026-02-12** | NagaCAS 认证 + NagaModel 网关路由、Live2D 4 通道正交动画架构、Agentic Tool Loop、明日方舟风格启动界面、游戏攻略 MCP 接通 |
| **2026-02-11** | 嵌入式 OpenClaw 打包、启动时自动从模板生成配置文件 |
| **2026-02-10** | 后端打包优化、技能工坊 MCP 状态修复、终端设置页面空白修复、去除冗余 Agent/MCP 仅保留 OpenClaw 调度 |
| **2026-02-09** | 前端重构、Live2D 禁用眼睛追踪、OpenClaw 更名为 AgentServer |

---

## 核心模块

### 流式工具调用循环

NagaAgent 的工具调用不依赖 OpenAI Function Calling API，而是让 LLM 在文本输出中以 ` ```tool``` ` 代码块内嵌 JSON 描述工具调用。这意味着**任何 OpenAI 兼容的 LLM 提供商都可以直接使用**，无需模型本身支持 function calling。

**单轮流程**：

```
LLM 流式输出 ──SSE──▶ 前端实时显示文本
       │                    │
       ▼                    ▼
  完整文本拼接         TTS 分句播放
       │
       ▼
parse_tool_calls_from_text()
  ├─ Phase 1: 提取 ```tool``` 代码块内的 JSON
  └─ Phase 2: 兜底提取裸 JSON（向后兼容）
       │
       ▼
  按 agentType 分类
  ├─ "mcp"     → MCPManager.unified_call()（进程内）
  ├─ "openclaw" → HTTP POST → Agent Server /openclaw/send
  └─ "live2d"  → asyncio.create_task() → UI 通知
       │
       ▼
  asyncio.gather() 并行执行
       │
       ▼
  工具结果注入 messages，进入下一轮 LLM 调用
```

**实现细节**：

- **文本解析**：正则 `r"```tool\s*\n([\s\S]*?)(?:```|\Z)"` 提取代码块，`json5` 容错解析（兜底 `json`），全角字符（`｛｝：`）自动标准化
- **循环控制**：最大 5 轮（`max_loop_stream` 可配），每轮 LLM 输出无 `agentType` JSON 则终止
- **SSE 编码**：每个 chunk 为 `data: {"type":"content"|"reasoning","text":"..."}\n\n`，前端 `ReadableStream` + `TextDecoder` 实时拆分
- **工具结果回注**：格式化为 `[工具结果 1/N - service: tool (status)]` 追加到 messages 中

源码：[`apiserver/agentic_tool_loop.py`](apiserver/agentic_tool_loop.py)、[`apiserver/streaming_tool_extractor.py`](apiserver/streaming_tool_extractor.py)

---

### GRAG 知识图谱记忆

GRAG（Graph-RAG）从对话中自动提取五元组 `(主体, 主体类型, 谓词, 客体, 客体类型)` 并存入 Neo4j，对话时自动检索相关记忆作为 LLM 上下文。

**提取流程**：

1. **结构化提取**（优先）：调用 `beta.chat.completions.parse()` + Pydantic 模型 `QuintupleResponse`，`temperature=0.3`，最多重试 3 次
2. **JSON 兜底**：Prompt 要求 LLM 返回 JSON 数组，解析失败则取首个 `[` 到末尾 `]` 之间的内容
3. **过滤规则**：只提取事实信息（行为、实体关系、状态、偏好），过滤隐喻、假设、纯情感、闲聊
4. **实体类型**：person / location / organization / item / concept / time / event / activity

**任务管理器**：

- 3 个 asyncio worker 协程消费 `asyncio.Queue(maxsize=100)`
- SHA-256 去重：相同文本的 PENDING/RUNNING 任务自动跳过
- 每小时自动清理超过 24h 的已完成任务
- 可配置超时（默认 12 秒）和重试次数（默认 2 次）

**双重存储**：

- 本地文件 `logs/knowledge_graph/quintuples.json`（JSON 数组，set 去重）
- Neo4j 图数据库：`Entity` 节点 + 类型化 `Relationship` 关系边，`graph.merge()` upsert

**RAG 检索**：

1. 提取用户问题关键词（LLM 生成）
2. Cypher 查询：`MATCH (e1:Entity)-[r]->(e2:Entity) WHERE e1.name CONTAINS '{kw}' ... LIMIT 5`
3. 格式化为 `主体(类型) —[谓词]→ 客体(类型)` 注入 LLM 上下文

**远程记忆**（5.0.0 新增）：

- `summer_memory/memory_client.py` 对接 NagaMemory 云端服务
- 登录用户自动使用云端存储，退出登录或离线时自动回退本地 GRAG
- API Server 新增 `/api/memory/*` 代理端点，前端通过 API Server 中转

源码：[`summer_memory/`](summer_memory/)

---

### MCP 工具系统

基于 [Model Context Protocol](https://modelcontextprotocol.io/) 的可插拔工具架构，每个工具以独立 Agent 形式运行。

**内置 Agent**：

| Agent | 目录 | 功能 |
|-------|------|------|
| `weather_time` | `mcpserver/agent_weather_time/` | 天气查询/预报、系统时间、自动城市/IP 检测 |
| `open_launcher` | `mcpserver/agent_open_launcher/` | 扫描系统已安装应用，自然语言启动程序 |
| `game_guide` | `mcpserver/agent_game_guide/` | 游戏策略问答、伤害计算、配队推荐、自动截图注入 |
| `online_search` | `mcpserver/agent_online_search/` | 基于 SearXNG 的网络搜索 |
| `crawl4ai` | `mcpserver/agent_crawl4ai/` | 基于 Crawl4AI 的网页内容提取 |
| `playwright_master` | `mcpserver/agent_playwright_master/` | 基于 Playwright 的浏览器自动化 |
| `vision` | `mcpserver/agent_vision/` | 截图分析与视觉问答 |
| `mqtt_tool` | `mcpserver/agent_mqtt_tool/` | MQTT 协议 IoT 设备控制 |
| `office_doc` | `mcpserver/agent_office_doc/` | docx/xlsx 内容提取 |

**注册与发现**：

```
mcpserver/
├── agent_weather_time/
│   ├── agent-manifest.json    ← 声明 name, entryPoint.module/class, capabilities
│   └── weather_time_agent.py
├── agent_online_search/
│   ├── agent-manifest.json
│   └── ...
└── mcp_registry.py            ← scan_and_register_mcp_agents() glob 扫描 **/agent-manifest.json
                                   importlib.import_module(module).ClassName() 动态实例化
```

- `MCPManager.unified_call(service_name, tool_call)` 路由到对应 Agent 的 `handle_handoff()`
- MCP Server `POST /schedule` 支持批量调用，`asyncio.gather()` 并行执行
- **Skill Market**：前端技能工坊支持一键安装社区 Skill（Agent Browser、Brainstorming、Context7、Firecrawl Search 等），后端 `GET /openclaw/market/items` + `POST /openclaw/market/items/{id}/install`

源码：[`mcpserver/`](mcpserver/)

---

### Electron 桌面端

基于 Electron + Vue 3 + Vite + UnoCSS + PrimeVue 的桌面客户端。

#### Live2D 渲染与动画

使用 **pixi-live2d-display** + **PixiJS WebGL** 渲染 Cubism Live2D 模型。SSAA 超采样抗锯齿：Canvas 按 `width * ssaa` 渲染，CSS `transform: scale(1/ssaa)` 缩放。

**4 通道正交动画系统**（`live2dController.ts`）：

| 通道 | 说明 | 参数 |
|------|------|------|
| **体态 (State)** | 关键帧循环动画（idle/thinking/talking），hermite 平滑插值 | 从 `naga-actions.json` 加载 |
| **动作 (Action)** | 队列式头部动作（点头/摇头），FIFO 单一执行 | AngleX/Y, EyeBallX/Y |
| **表情 (Emotion)** | `.exp3.json` 表情文件，三种混合模式（Add/Multiply/Overwrite） | 指数衰减过渡 |
| **追踪 (Tracking)** | 鼠标指针跟随视线，可配延迟启动（`tracking_hold_delay_ms`） | Angle ±30, EyeBall ±1, BodyAngle ±10 |

合并顺序：体态 → 嘴形 → 动作 → 手动覆盖 → 表情混合 → 追踪混合。

#### 意识海可视化（MindView）

Canvas 2D + 手写 3D 投影（非 WebGL/SVG），球面坐标相机 `(theta, phi, distance)`，透视除法 `700 / depth`。

**7 层渲染**：背景渐变 → 地面网格 → 水面平面 → 体积光（3 束光柱） → 粒子系统（3 层 125 颗） → 生物荧光浮游生物（10 个带拖尾） → 知识图谱节点与边（深度排序 painter's algorithm）。

五元组到图的映射：`subject`/`object` → 节点，`predicate` → 有向边，度中心性 → 节点高度权重（高权节点上浮），100 节点上限。

交互：单击拖拽旋转、中键/Shift+拖拽平移、滚轮缩放、节点拖拽/点选、关键词搜索过滤、触屏手势。

#### 悬浮球模式

4 状态动画窗口系统：`classic`（正常）→ `ball`（100×100 圆球）→ `compact`（420×100 折叠）→ `full`（420×N 展开）。

easeOutCubic 缓动（`1 - (1 - t)^3`），160ms / 60FPS 过渡。智能定位：从球位置向右展开，自动贴合屏幕边界。

#### 启动动画

1. **标题阶段**：黑色遮罩 + 40 颗金色上升粒子 + 标题图片 2.4s CSS keyframe（渐入 → 停留 → 渐出）
2. **进度阶段**：Neural Network 粒子背景 + Live2D 透出框 + 金色进度条（`requestAnimationFrame` 插值，最低速度 0.5 兜底）
3. **停滞检测**：3 秒无进度变化显示重启提示，25% 后每秒轮询后端 `/health` 防止信号丢失
4. **唤醒**：进度 100% 后显示"点击唤醒"脉冲提示

源码：[`frontend/`](frontend/)

---

### 语音交互

**TTS（语音合成）**：

- Edge-TTS 引擎，OpenAI 兼容接口 `/v1/audio/speech`
- 3 线程流水线：分句队列 → TTS API 调用（Semaphore(2) 并发控制）→ pygame 播放
- Live2D 口型同步：`AdvancedLipSyncEngineV2` 60FPS 提取 5 个参数（mouth_open / mouth_form / mouth_smile / eye_brow_up / eye_wide）
- 支持 mp3 / aac / wav / opus / flac 格式，FFmpeg 可选转码

**ASR（语音识别）**：

- FunASR 本地服务器，支持 VAD 端点检测和 WebSocket 实时流
- 三模式自动切换：LOCAL（FunASR）→ END_TO_END（Qwen Omni）→ HYBRID（Qwen ASR + API Server）

**实时语音对话**（需 DashScope API Key）：

- 基于 Qwen Omni 的全双工 WebSocket 语音交互
- 回声抑制、VAD 检测、音频分块（200ms）、会话冷却、最大语音时长控制

源码：[`voice/`](voice/)

---

### Agent Server 与任务调度

**OpenClaw 集成**：

- 对接 OpenClaw Gateway（端口 18789），通过自然语言调度 AI 编程助手执行电脑任务
- 三级回退：打包内嵌 → 全局 `openclaw` 命令 → 自动 `npm install -g openclaw`
- `POST /openclaw/send` 发送指令，最长等待 120 秒

**任务调度器**（`TaskScheduler`）：

- 任务步骤记录（目的/内容/输出/分析/成功与否）
- 自动提取关键事实和"关键发现"/"重要"标记
- 内存压缩：步骤数超过阈值时调用 LLM 生成 `CompressedMemory`（key_findings / failed_attempts / current_status / next_steps），只保留最近 N 步
- `schedule_parallel_execution()` 通过 `asyncio.gather()` 并行执行任务列表

源码：[`agentserver/`](agentserver/)

---

## 架构

```
┌──────────────────────────────────────────────────────────┐
│                   Electron / PyQt5 前端                    │
│  Vue 3 + Vite + UnoCSS + PrimeVue + pixi-live2d-display  │
└────────────┬────────────┬────────────┬───────────────────┘
             │            │            │
     ┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────┐
     │  API Server  │ │ Agent   │ │  Voice  │
     │   :8000      │ │ Server  │ │ Service │
     │              │ │  :8001  │ │  :5048  │
     │ - 对话/SSE   │ │         │ │         │
     │ - 工具调用   │ │ - 意图  │ │ - TTS   │
     │ - 文档上传   │ │   分析  │ │ - ASR   │
     │ - 认证代理   │ │ - 任务  │ │ - 实时  │
     │ - 记忆API    │ │   调度  │ │   语音  │
     │ - Skill市场  │ │ - Open  │ │         │
     │ - 配置管理   │ │   Claw  │ │         │
     └──────┬───────┘ └────┬────┘ └─────────┘
            │              │
     ┌──────▼──────┐  ┌───▼──────────┐
     │ MCP Server  │  │   OpenClaw   │
     │   :8003     │  │   Gateway    │
     │             │  │   :18789     │
     │ - 工具注册  │  └──────────────┘
     │ - Agent发现 │
     │ - 并行调度  │
     └──────┬──────┘
            │
    ┌───────┴──────────────────────┐
    │   MCP Agents (可插拔工具)     │
    │ 天气 | 搜索 | 抓取 | 视觉    │
    │ 启动器 | 攻略 | 文档 | MQTT  │
    └──────────────────────────────┘
            │
     ┌──────▼──────┐
     │   Neo4j     │
     │   :7687     │
     │  知识图谱   │
     └─────────────┘
```

### 目录结构

```
NagaAgent/
├── apiserver/            # API Server — 对话、流式工具调用、认证、配置管理
│   ├── api_server.py     #   FastAPI 主应用
│   ├── agentic_tool_loop.py  #   多轮工具调用循环
│   ├── llm_service.py    #   LiteLLM 统一 LLM 调用
│   └── streaming_tool_extractor.py  #   流式分句 + TTS 分发
├── agentserver/          # Agent Server — 意图分析、任务调度、OpenClaw
│   ├── agent_server.py   #   FastAPI 主应用
│   └── task_scheduler.py #   任务编排 + 压缩记忆
├── mcpserver/            # MCP Server — 工具注册与调度
│   ├── mcp_server.py     #   FastAPI 主应用
│   ├── mcp_registry.py   #   manifest 扫描 + 动态注册
│   ├── mcp_manager.py    #   unified_call() 路由
│   ├── agent_weather_time/
│   ├── agent_open_launcher/
│   ├── agent_game_guide/
│   ├── agent_online_search/
│   ├── agent_crawl4ai/
│   ├── agent_playwright_master/
│   ├── agent_vision/
│   ├── agent_mqtt_tool/
│   └── agent_office_doc/
├── summer_memory/        # GRAG 知识图谱
│   ├── quintuple_extractor.py  #   五元组提取（结构化输出 + JSON 兜底）
│   ├── quintuple_graph.py      #   Neo4j + 文件双重存储
│   ├── quintuple_rag_query.py  #   Cypher 关键词 RAG 检索
│   ├── task_manager.py         #   3 worker 异步任务管理器
│   ├── memory_manager.py       #   GRAG 总管理器
│   └── memory_client.py        #   NagaMemory 远程客户端
├── voice/                # 语音服务
│   ├── output/           #   TTS (Edge-TTS) + 口型同步
│   └── input/            #   ASR (FunASR) + 实时语音 (Qwen Omni)
├── guide_engine/         # 游戏攻略引擎 — 云端 RAG 服务
├── frontend/             # Electron + Vue 3 前端
│   ├── electron/         #   主进程（窗口管理、悬浮球、后端管理、热键）
│   └── src/              #   Vue 3 应用
│       ├── views/        #     MessageView / MindView / SkillView / ModelView / MemoryView / ConfigView
│       ├── components/   #     Live2dModel / SplashScreen / LoginDialog / ...
│       ├── composables/  #     useAuth / useStartupProgress / useVersionCheck / useToolStatus
│       └── utils/        #     live2dController (4通道动画) / encoding / session
├── ui/                   # PyQt5 GUI (MVC)
├── system/               # 配置加载、环境检测、系统提示词、后台分析器
├── main.py               # 统一入口，编排所有服务
├── config.json           # 运行时配置（从 config.json.example 复制）
└── pyproject.toml        # 项目元数据与依赖
```

---

## 快速开始

### 环境要求

- Python 3.11（`>=3.11, <3.12`）
- 可选：[uv](https://github.com/astral-sh/uv)（加速依赖安装）
- 可选：Neo4j（知识图谱记忆）

### 安装

```bash
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 方式一：setup 脚本（自动检测环境、创建虚拟环境、安装依赖）
python setup.py

# 方式二：uv
uv sync

# 方式三：手动
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### 配置

复制 `config.json.example` 为 `config.json`，填入 LLM API 信息：

```json
{
  "api": {
    "api_key": "your-api-key",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-v3.2"
  }
}
```

支持所有 OpenAI 兼容 API（DeepSeek、通义千问、OpenAI、Ollama 等）。

### 启动

```bash
python main.py             # 完整启动（API + Agent + MCP + Voice + GUI）
uv run main.py             # 使用 uv
python main.py --headless  # 无 GUI 模式（配合 Electron 前端）
```

所有服务由 `main.py` 统一编排，也可单独启动：

```bash
uvicorn apiserver.api_server:app --host 127.0.0.1 --port 8000 --reload
uvicorn agentserver.agent_server:app --host 0.0.0.0 --port 8001
```

### Electron 前端开发

```bash
cd frontend
npm install
npm run dev    # 开发模式（Vite + Electron）
npm run build  # 构建生产包
```

---

## 可选配置

<details>
<summary><b>知识图谱记忆（Neo4j）</b></summary>

安装 Neo4j（[Docker](https://hub.docker.com/_/neo4j) 或 [Neo4j Desktop](https://neo4j.com/download/)），然后配置：

```json
{
  "grag": {
    "enabled": true,
    "neo4j_uri": "neo4j://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your-password"
  }
}
```
</details>

<details>
<summary><b>语音交互</b></summary>

```json
{
  "system": { "voice_enabled": true },
  "tts": { "port": 5048, "default_voice": "zh-CN-XiaoxiaoNeural" }
}
```

实时语音对话（需通义千问 DashScope API Key）：

```json
{
  "voice_realtime": {
    "enabled": true,
    "provider": "qwen",
    "api_key": "your-dashscope-key",
    "model": "qwen3-omni-flash-realtime"
  }
}
```
</details>

<details>
<summary><b>Live2D 虚拟形象</b></summary>

```json
{
  "live2d": {
    "enabled": true,
    "model_path": "path/to/your/model.model3.json"
  }
}
```

Electron 前端 Live2D 配置：

```json
{
  "web_live2d": {
    "ssaa": 2,
    "model": {
      "source": "./models/your-model/model.model3.json",
      "x": 0.5,
      "y": 1.3,
      "size": 6800
    },
    "face_y_ratio": 0.13,
    "tracking_hold_delay_ms": 100
  }
}
```
</details>

<details>
<summary><b>MQTT 物联网</b></summary>

```json
{
  "mqtt": {
    "enabled": true,
    "broker": "mqtt-broker-address",
    "port": 1883,
    "topic": "naga/agent/topic"
  }
}
```
</details>

---

## 端口一览

| 服务 | 端口 | 说明 |
|------|------|------|
| API Server | 8000 | 主接口：对话、配置、认证、Skill 市场 |
| Agent Server | 8001 | 意图分析、任务调度、OpenClaw |
| MCP Server | 8003 | MCP 工具注册与调度 |
| Voice Service | 5048 | TTS / ASR |
| Neo4j | 7687 | 知识图谱（可选） |
| OpenClaw Gateway | 18789 | AI 编程助手（可选） |

---

## 更新

```bash
python update.py  # 自动 git pull + 依赖同步
```

---

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| Python 版本不兼容 | 使用 Python 3.11；或使用 uv（自动管理 Python 版本） |
| 端口被占用 | 检查 8000、8001、8003、5048 是否可用 |
| Neo4j 连接失败 | 确认 Neo4j 服务已启动，检查 config.json 中的连接参数 |
| 启动卡在进度条 | 检查 API Key 是否配置正确；3 秒后出现重启提示；Electron 会自动轮询后端健康状态 |

```bash
python main.py --check-env --force-check  # 环境诊断
python main.py --quick-check              # 快速检查
```

---

## 构建

```bash
python build.py  # 构建 Windows 一键运行整合包，输出到 dist/
```

---

## 贡献

欢迎提交 Issue 和 Pull Request。如有问题，可加入 QQ 频道 nagaagent1。

---

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=RTGS2017/NagaAgent&type=date&legend=top-left)](https://www.star-history.com/#RTGS2017/NagaAgent&type=date&legend=top-left)
