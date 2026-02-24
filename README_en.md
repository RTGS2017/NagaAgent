<div align="center">

# NagaAgent

**Four-Service AI Desktop Assistant — Streaming Tool Calls · Knowledge Graph Memory · Live2D · Voice**

[简体中文](README.md) | [繁體中文](README_tw.md) | [English](README_en.md)

![NagaAgent](https://img.shields.io/badge/NagaAgent-5.1.0-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-AGPL%203.0%20%7C%20Proprietary-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)

[![Stars](https://img.shields.io/github/stars/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Forks](https://img.shields.io/github/forks/Xxiii8322766509/NagaAgent?style=social)](https://github.com/Xxiii8322766509/NagaAgent)
[![Issues](https://img.shields.io/github/issues/Xxiii8322766509/NagaAgent)](https://github.com/Xxiii8322766509/NagaAgent/issues)

**[QQ Bot Integration: Undefined QQbot](https://github.com/69gg/Undefined/)**


</div>

---

**Dual licensed** · [AGPL-3.0](LICENSE) for open source | [Proprietary](LICENSE-CLOSED-SOURCE) for closed-source use (written consent required). Commercial: contact@nagaagent.com

---

## Overview

NagaAgent consists of four independent microservices:

| Service | Port | Responsibilities |
|---------|------|-----------------|
| **API Server** | 8000 | Chat, streaming tool calls, document upload, auth proxy, memory API, config management |
| **Agent Server** | 8001 | Background intent analysis, OpenClaw integration, task scheduling with compressed memory |
| **MCP Server** | 8003 | MCP tool registration / discovery / parallel dispatch |
| **Voice Service** | 5048 | TTS (Edge-TTS) + ASR (FunASR) + Realtime voice (Qwen Omni) |

`main.py` orchestrates all services as daemon threads. Frontend options: Electron + Vue 3 desktop or PyQt5 native GUI.

---

## Updates

| Date | Changes |
|------|---------|
| **2026-02-16** | 5.0.0 release: NagaModel gateway unified access (TTS/Embeddings/WebSearch), DeepSeek reasoning process real-time display, Mind Sea UI adaptive fix, BoxContainer noScroll mode |
| **2026-02-15** | Unified knowledge block injection + history pollution fix, LLM streaming retry, config hot-reload fix, skill workshop loading optimization, config.json write truncation fix, 7-day auto-login + auto-start on boot |
| **2026-02-14** | Remote memory service (NagaMemory cloud + local GRAG fallback), Mind Sea 3D rewrite, splash title animation with particles, progress bar stall detection & health polling, version update dialog, user agreement |
| **2026-02-13** | Floating ball mode (4-state animation), screenshot multimodal vision auto-switch, skill workshop refactor + Live2D emotion channel independent, login/registration flow improvements |
| **2026-02-12** | NagaCAS authentication + NagaModel gateway routing, Live2D 4-channel orthogonal animation, Agentic Tool Loop, Arknights-style splash screen, game guide MCP integration |
| **2026-02-11** | Embedded OpenClaw packaging, auto-generate config from template on startup |
| **2026-02-10** | Backend packaging optimization, skill workshop MCP status fix, terminal settings blank page fix, remove redundant Agent/MCP keeping only OpenClaw dispatch |
| **2026-02-09** | Frontend refactor, Live2D eye tracking disable, OpenClaw renamed to AgentServer |

---

## Core Modules

### Streaming Tool Call Loop

NagaAgent's tool calling does not rely on OpenAI's Function Calling API. Instead, the LLM embeds tool calls as JSON inside ` ```tool``` ` code blocks in its text output. This means **any OpenAI-compatible LLM provider works out of the box** — no function calling support required from the model.

**Single-round flow**:

```
LLM streaming output ──SSE──▶ Frontend displays text in real-time
       │                              │
       ▼                              ▼
  Accumulate full text          TTS sentence splitting
       │
       ▼
parse_tool_calls_from_text()
  ├─ Phase 1: Extract JSON from ```tool``` code blocks
  └─ Phase 2: Fallback to bare JSON extraction (backward compat)
       │
       ▼
  Classify by agentType
  ├─ "mcp"      → MCPManager.unified_call() (in-process)
  ├─ "openclaw"  → HTTP POST → Agent Server /openclaw/send
  └─ "live2d"   → asyncio.create_task() → UI notification
       │
       ▼
  asyncio.gather() parallel execution
       │
       ▼
  Inject tool results into messages, start next LLM round
```

**Implementation details**:

- **Text parsing**: Regex `r"```tool\s*\n([\s\S]*?)(?:```|\Z)"` extracts code blocks, `json5` for tolerant parsing (fallback to `json`), fullwidth characters (`｛｝：`) auto-normalized
- **Loop control**: Max 5 rounds (`max_loop_stream` configurable), terminates when no `agentType` JSON found in LLM output
- **SSE encoding**: Each chunk is `data: {"type":"content"|"reasoning","text":"..."}\n\n`, frontend splits via `ReadableStream` + `TextDecoder`
- **Result injection**: Formatted as `[Tool Result 1/N - service: tool (status)]` and appended to messages

Source: [`apiserver/agentic_tool_loop.py`](apiserver/agentic_tool_loop.py), [`apiserver/streaming_tool_extractor.py`](apiserver/streaming_tool_extractor.py)

---

### GRAG Knowledge Graph Memory

GRAG (Graph-RAG) automatically extracts quintuples `(subject, subject_type, predicate, object, object_type)` from conversations, stores them in Neo4j, and retrieves relevant memories as LLM context during chat.

**Extraction pipeline**:

1. **Structured output** (preferred): Calls `beta.chat.completions.parse()` with Pydantic model `QuintupleResponse`, `temperature=0.3`, up to 3 retries
2. **JSON fallback**: Prompts LLM to return a JSON array; on parse failure, extracts content between the first `[` and last `]`
3. **Filtering rules**: Only factual information (behaviors, entity relations, states, preferences); filters metaphors, hypotheticals, emotions, chitchat
4. **Entity types**: person / location / organization / item / concept / time / event / activity

**Task manager**:

- 3 asyncio worker coroutines consuming from `asyncio.Queue(maxsize=100)`
- SHA-256 deduplication: identical text with PENDING/RUNNING tasks is skipped
- Hourly auto-cleanup of tasks older than 24h
- Configurable timeout (default 12s) and retry count (default 2)

**Dual storage**:

- Local file `logs/knowledge_graph/quintuples.json` (JSON array, set-based dedup)
- Neo4j graph: `Entity` nodes + typed `Relationship` edges, `graph.merge()` upsert

**RAG retrieval**:

1. Extract keywords from user question (LLM-generated)
2. Cypher query: `MATCH (e1:Entity)-[r]->(e2:Entity) WHERE e1.name CONTAINS '{kw}' ... LIMIT 5`
3. Format as `subject(type) —[predicate]→ object(type)` and inject into LLM context

**Remote memory** (new in 5.0.0):

- `summer_memory/memory_client.py` interfaces with NagaMemory cloud service
- Logged-in users automatically use cloud storage; falls back to local GRAG on logout or offline
- API Server adds `/api/memory/*` proxy endpoints for frontend access

Source: [`summer_memory/`](summer_memory/)

---

### MCP Tool System

A pluggable tool architecture based on the [Model Context Protocol](https://modelcontextprotocol.io/), with each tool running as an independent agent.

**Built-in agents**:

| Agent | Directory | Function |
|-------|-----------|----------|
| `weather_time` | `mcpserver/agent_weather_time/` | Weather queries/forecasts, system time, auto city/IP detection |
| `open_launcher` | `mcpserver/agent_open_launcher/` | Scan installed apps, launch programs via natural language |
| `game_guide` | `mcpserver/agent_game_guide/` | Game strategy Q&A, damage calculation, team building, auto-screenshot injection |
| `online_search` | `mcpserver/agent_online_search/` | Web search via SearXNG |
| `crawl4ai` | `mcpserver/agent_crawl4ai/` | Web content extraction via Crawl4AI |
| `playwright_master` | `mcpserver/agent_playwright_master/` | Browser automation via Playwright |
| `vision` | `mcpserver/agent_vision/` | Screenshot analysis and visual Q&A |
| `mqtt_tool` | `mcpserver/agent_mqtt_tool/` | IoT device control via MQTT |
| `office_doc` | `mcpserver/agent_office_doc/` | docx/xlsx content extraction |

**Registration & discovery**:

```
mcpserver/
├── agent_weather_time/
│   ├── agent-manifest.json    ← Declares name, entryPoint.module/class, capabilities
│   └── weather_time_agent.py
├── agent_online_search/
│   ├── agent-manifest.json
│   └── ...
└── mcp_registry.py            ← scan_and_register_mcp_agents() globs **/agent-manifest.json
                                   importlib.import_module(module).ClassName() dynamic instantiation
```

- `MCPManager.unified_call(service_name, tool_call)` routes to the agent's `handle_handoff()`
- MCP Server `POST /schedule` supports batch calls via `asyncio.gather()` for parallel execution
- **Skill Market**: Frontend skill workshop supports one-click installation of community skills (Agent Browser, Brainstorming, Context7, Firecrawl Search, etc.), backend `GET /openclaw/market/items` + `POST /openclaw/market/items/{id}/install`

Source: [`mcpserver/`](mcpserver/)

---

### Electron Desktop

Built with Electron + Vue 3 + Vite + UnoCSS + PrimeVue.

#### Live2D Rendering & Animation

Uses **pixi-live2d-display** + **PixiJS WebGL** to render Cubism Live2D models. SSAA super-sampling: Canvas rendered at `width * ssaa`, CSS `transform: scale(1/ssaa)` for sharper output.

**4-channel orthogonal animation system** (`live2dController.ts`):

| Channel | Description | Parameters |
|---------|-------------|------------|
| **Body State** | Keyframe loop animation (idle/thinking/talking), hermite-smooth interpolation | Loaded from `naga-actions.json` |
| **Actions** | Queue-based head actions (nod/shake), FIFO single execution | AngleX/Y, EyeBallX/Y |
| **Emotions** | `.exp3.json` expression files, three blend modes (Add/Multiply/Overwrite) | Exponential decay transitions |
| **Tracking** | Pointer-following gaze, configurable start delay (`tracking_hold_delay_ms`) | Angle ±30, EyeBall ±1, BodyAngle ±10 |

Merge order: body state → mouth → actions → manual override → emotion blend → tracking blend.

#### Mind Sea Visualization (MindView)

Canvas 2D with hand-rolled 3D projection (not WebGL/SVG). Spherical coordinate camera `(theta, phi, distance)`, perspective division `700 / depth`.

**7-layer rendering**: Background gradient → floor grid → water surface → volumetric light (3 god rays) → particle system (3 layers, 125 particles) → bioluminescent plankton (10 with trails) → knowledge graph nodes and edges (depth-sorted painter's algorithm).

Quintuple-to-graph mapping: `subject`/`object` → nodes, `predicate` → directed edges, degree centrality → node height weight (high-degree nodes float higher), 100-node limit.

Interactions: click-drag to orbit, middle/shift-drag to pan, scroll to zoom, node drag/select, keyword search, touch gestures.

#### Floating Ball Mode

4-state animated window system: `classic` (normal) → `ball` (100×100 circle) → `compact` (420×100 collapsed) → `full` (420×N expanded).

easeOutCubic easing (`1 - (1 - t)^3`), 160ms / 60FPS transitions. Smart positioning: expands rightward from ball position, auto-clamps to screen bounds.

#### Splash Animation

1. **Title phase**: Black overlay + 40 golden rising particles + title image 2.4s CSS keyframe (fade in → hold → fade out)
2. **Progress phase**: Neural network particle background + Live2D cutout frame + gold progress bar (`requestAnimationFrame` interpolation, minimum speed 0.5 floor)
3. **Stall detection**: 3 seconds with no progress change shows restart hint, health polling every 1s after 25% to prevent signal loss
4. **Awaken**: Progress 100% shows pulsing "Click to Awaken" prompt

Source: [`frontend/`](frontend/)

---

### Voice Interaction

**TTS (Text-to-Speech)**:

- Edge-TTS engine, OpenAI-compatible endpoint `/v1/audio/speech`
- 3-thread pipeline: sentence queue → TTS API calls (Semaphore(2) concurrency) → pygame playback
- Live2D lip sync: `AdvancedLipSyncEngineV2` at 60FPS extracting 5 parameters (mouth_open / mouth_form / mouth_smile / eye_brow_up / eye_wide)
- Supports mp3 / aac / wav / opus / flac, optional FFmpeg transcoding

**ASR (Speech Recognition)**:

- FunASR local server with VAD endpoint detection and WebSocket real-time streaming
- Three-mode auto-switch: LOCAL (FunASR) → END_TO_END (Qwen Omni) → HYBRID (Qwen ASR + API Server)

**Realtime Voice Chat** (requires DashScope API Key):

- Full-duplex WebSocket voice interaction via Qwen Omni
- Echo suppression, VAD detection, audio chunking (200ms), session cooldown, max speech duration control

Source: [`voice/`](voice/)

---

### Agent Server & Task Scheduling

**OpenClaw Integration**:

- Connects to OpenClaw Gateway (port 18789) to dispatch AI coding assistants for computer tasks via natural language
- Three-tier fallback: packaged binary → global `openclaw` command → auto `npm install -g openclaw`
- `POST /openclaw/send` sends instructions, waits up to 120 seconds

**Task Scheduler** (`TaskScheduler`):

- Task step recording (purpose / content / output / analysis / success status)
- Auto-extraction of key facts and "key findings" / "important" markers
- Memory compression: when steps exceed threshold, LLM generates `CompressedMemory` (key_findings / failed_attempts / current_status / next_steps), keeping only the last N steps
- `schedule_parallel_execution()` via `asyncio.gather()` for parallel task execution

Source: [`agentserver/`](agentserver/)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                 Electron / PyQt5 Frontend                 │
│  Vue 3 + Vite + UnoCSS + PrimeVue + pixi-live2d-display  │
└────────────┬────────────┬────────────┬───────────────────┘
             │            │            │
     ┌───────▼──────┐ ┌──▼──────┐ ┌──▼──────┐
     │  API Server  │ │ Agent   │ │  Voice  │
     │   :8000      │ │ Server  │ │ Service │
     │              │ │  :8001  │ │  :5048  │
     │ - Chat/SSE   │ │         │ │         │
     │ - Tool calls │ │ - Intent│ │ - TTS   │
     │ - Documents  │ │   analysis│ │ - ASR │
     │ - Auth proxy │ │ - Task  │ │ - Real  │
     │ - Memory API │ │   sched │ │   time  │
     │ - Skill Mkt  │ │ - Open  │ │         │
     │ - Config     │ │   Claw  │ │         │
     └──────┬───────┘ └────┬────┘ └─────────┘
            │              │
     ┌──────▼──────┐  ┌───▼──────────┐
     │ MCP Server  │  │   OpenClaw   │
     │   :8003     │  │   Gateway    │
     │             │  │   :18789     │
     │ - Registry  │  └──────────────┘
     │ - Discovery │
     │ - Parallel  │
     └──────┬──────┘
            │
    ┌───────┴──────────────────────┐
    │   MCP Agents (pluggable)     │
    │ Weather | Search | Crawl     │
    │ Launcher | Guide | MQTT ...  │
    └──────────────────────────────┘
            │
     ┌──────▼──────┐
     │   Neo4j     │
     │   :7687     │
     │  Knowledge  │
     │   Graph     │
     └─────────────┘
```

### Directory Structure

```
NagaAgent/
├── apiserver/            # API Server — chat, streaming tool calls, auth, config
│   ├── api_server.py     #   FastAPI main app
│   ├── agentic_tool_loop.py  #   Multi-round tool call loop
│   ├── llm_service.py    #   LiteLLM unified LLM interface
│   └── streaming_tool_extractor.py  #   Streaming sentence split + TTS dispatch
├── agentserver/          # Agent Server — intent analysis, task scheduling, OpenClaw
│   ├── agent_server.py   #   FastAPI main app
│   └── task_scheduler.py #   Task orchestration + compressed memory
├── mcpserver/            # MCP Server — tool registration & dispatch
│   ├── mcp_server.py     #   FastAPI main app
│   ├── mcp_registry.py   #   Manifest scanning + dynamic registration
│   ├── mcp_manager.py    #   unified_call() routing
│   ├── agent_weather_time/
│   ├── agent_open_launcher/
│   ├── agent_game_guide/
│   ├── agent_online_search/
│   ├── agent_crawl4ai/
│   ├── agent_playwright_master/
│   ├── agent_vision/
│   ├── agent_mqtt_tool/
│   └── agent_office_doc/
├── summer_memory/        # GRAG knowledge graph
│   ├── quintuple_extractor.py  #   Quintuple extraction (structured output + JSON fallback)
│   ├── quintuple_graph.py      #   Neo4j + file dual storage
│   ├── quintuple_rag_query.py  #   Cypher keyword RAG retrieval
│   ├── task_manager.py         #   3-worker async task manager
│   ├── memory_manager.py       #   GRAG orchestrator
│   └── memory_client.py        #   NagaMemory remote client
├── voice/                # Voice service
│   ├── output/           #   TTS (Edge-TTS) + lip sync
│   └── input/            #   ASR (FunASR) + realtime voice (Qwen Omni)
├── guide_engine/         # Game guide engine — cloud RAG service
├── frontend/             # Electron + Vue 3 frontend
│   ├── electron/         #   Main process (window mgmt, floating ball, backend, hotkeys)
│   └── src/              #   Vue 3 app
│       ├── views/        #     MessageView / MindView / SkillView / ModelView / MemoryView / ConfigView
│       ├── components/   #     Live2dModel / SplashScreen / LoginDialog / ...
│       ├── composables/  #     useAuth / useStartupProgress / useVersionCheck / useToolStatus
│       └── utils/        #     live2dController (4-channel animation) / encoding / session
├── ui/                   # PyQt5 GUI (MVC)
├── system/               # Config loader, env checker, system prompts, background analyzer
├── main.py               # Unified entry point, orchestrates all services
├── config.json           # Runtime config (copy from config.json.example)
└── pyproject.toml        # Project metadata & dependencies
```

---

## Quick Start

### Requirements

- Python 3.11 (`>=3.11, <3.12`)
- Optional: [uv](https://github.com/astral-sh/uv) (faster dependency installation)
- Optional: Neo4j (knowledge graph memory)

### Installation

```bash
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# Option 1: Setup script (auto-detects env, creates venv, installs deps)
python setup.py

# Option 2: Using uv
uv sync

# Option 3: Manual
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Copy `config.json.example` to `config.json` and fill in your LLM API credentials:

```json
{
  "api": {
    "api_key": "your-api-key",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-v3.2"
  }
}
```

Works with any OpenAI-compatible API (DeepSeek, Qwen, OpenAI, Ollama, etc.).

### Launch

```bash
python main.py             # Full launch (API + Agent + MCP + Voice + GUI)
uv run main.py             # Using uv
python main.py --headless  # Headless mode (for Electron frontend)
```

All services are orchestrated by `main.py`. For development, each can be started independently:

```bash
uvicorn apiserver.api_server:app --host 127.0.0.1 --port 8000 --reload
uvicorn agentserver.agent_server:app --host 0.0.0.0 --port 8001
```

### Electron Frontend Development

```bash
cd frontend
npm install
npm run dev    # Dev mode (Vite + Electron)
npm run build  # Production build
```

---

## Optional Configuration

<details>
<summary><b>Knowledge Graph Memory (Neo4j)</b></summary>

Install Neo4j ([Docker](https://hub.docker.com/_/neo4j) or [Neo4j Desktop](https://neo4j.com/download/)), then configure:

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
<summary><b>Voice Interaction</b></summary>

```json
{
  "system": { "voice_enabled": true },
  "tts": { "port": 5048, "default_voice": "zh-CN-XiaoxiaoNeural" }
}
```

Realtime voice chat (requires Qwen DashScope API Key):

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
<summary><b>Live2D Avatar</b></summary>

```json
{
  "live2d": {
    "enabled": true,
    "model_path": "path/to/your/model.model3.json"
  }
}
```

Electron frontend Live2D config:

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
<summary><b>MQTT IoT</b></summary>

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

## Ports

| Service | Port | Description |
|---------|------|-------------|
| API Server | 8000 | Main interface: chat, config, auth, Skill Market |
| Agent Server | 8001 | Intent analysis, task scheduling, OpenClaw |
| MCP Server | 8003 | MCP tool registration & dispatch |
| Voice Service | 5048 | TTS / ASR |
| Neo4j | 7687 | Knowledge graph (optional) |
| OpenClaw Gateway | 18789 | AI coding assistant (optional) |

---

## Updating

```bash
python update.py  # Auto git pull + dependency sync
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Python version mismatch | Use Python 3.11, or use uv (manages Python versions automatically) |
| Port in use | Check if ports 8000, 8001, 8003, 5048 are available |
| Neo4j connection failed | Ensure Neo4j is running, verify config.json connection parameters |
| Progress bar stuck | Check API key config; restart hint appears after 3s; Electron auto-polls backend health |

```bash
python main.py --check-env --force-check  # Environment diagnostics
python main.py --quick-check              # Quick check
```

---

## Building

```bash
python build.py  # Build Windows one-click runner package, output to dist/
```

---

## Contributing

Issues and Pull Requests are welcome.

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Xxiii8322766509/NagaAgent&type=date&legend=top-left)](https://www.star-history.com/#Xxiii8322766509/NagaAgent&type=date&legend=top-left)
