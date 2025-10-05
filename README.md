# NagaAgent 4.0

![NagaAgent Logo](https://img.shields.io/badge/NagaAgent-4.0-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)

![Star History](https://img.shields.io/github/stars/Xxiii8322766509/NagaAgent?style=social)![Forks](https://img.shields.io/github/forks/Xxiii8322766509/NagaAgent?style=social)![Issues](https://img.shields.io/github/issues/Xxiii8322766509/NagaAgent)![Pull Requests](https://img.shields.io/github/issues-pr/Xxiii8322766509/NagaAgent)

![UI 预览](ui/README.jpg)

---

<a href="https://www.star-history.com/#Xxiii8322766509/NagaAgent&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Xxiii8322766509/NagaAgent&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Xxiii8322766509/NagaAgent&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Xxiii8322766509/NagaAgent&type=Date" />
 </picture>
</a>

---

**🐍 智能对话助手 | 多平台支持 | 丰富生态 | 易于扩展**

---

## 🎬 快速入门视频

**[点击观看 NagaAgent 快速入门视频](https://www.pylindex.top/naga/intro.mp4)**

---

NagaAgent 是一个功能强大的智能对话助手，集成了先进的人工智能技术，提供自然语言交互、智能任务执行、知识图谱记忆等多种功能。通过模块化的 MCP (Model Context Protocol) 服务架构，支持灵活的功能扩展和自定义 Agent 开发。

---

### 🎯 项目亮点

✅ **🧠 智能记忆**: 基于 Neo4j 的 GRAG 知识图谱记忆系统，自动提取和记忆对话内容

✅ **🔧 丰富生态**: 内置 20+ MCP 服务，涵盖文件操作、浏览器控制、系统管理等领域

✅ **🎤 语音交互**: 支持实时语音输入输出，兼容 OpenAI TTS API

✅ **🖥️ 现代界面**: 基于 PyQt5 的精美 GUI，支持 Live2D 虚拟形象

✅ **🌐 完整 API**: RESTful API 接口，支持流式输出和 SSE

✅ **📱 系统托盘**: 完整的后台运行和自启动支持

✅ **🤖 多Agent协作**: 智能任务调度和多 Agent 协同工作

✅ **🌳 深度思考**: 基于遗传算法的多分支思考引擎

✅ **🔄 配置热更新**: 实时配置变更，无需重启应用

✅ **💾 持久化上下文**: 重启后自动恢复历史对话

✅ **🛡️ 安全可靠**: 会话隔离和权限管理

---

## 🚀 快速开始

### 📋 系统要求

- **操作系统**: Windows 10/11, macOS 10.15+, Linux
- **Python**: 3.11
- **Docker**: 用于 Neo4j 数据库（可选，也可使用neo4j desktop）

### 🔧 安装方式

#### 方式一：自动配置

<details>
<summary><strong>Windows 用户</strong></summary>

```powershell
# 克隆项目
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 一键配置环境
.\setup.ps1

# 复制配置文件模板
cp config.json.example config.json

# 配置 API 密钥
notepad config.json
```
</details>

<details>
<summary><strong>macOS 用户</strong></summary>

```bash
# 克隆项目
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 一键配置环境
chmod +x setup_mac.sh
./setup_mac.sh

# 复制配置文件模板
cp config.json.example config.json

# 配置 API 密钥
vim config.json
```
</details>

<details>
<summary><strong>Linux 用户</strong></summary>

```bash
# 克隆项目
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 复制配置文件模板
cp config.json.example config.json

# 配置 API 密钥
vi config.json
```
</details>

#### 方式二：手动配置

<details>
<summary><strong>使用传统 pip 安装</strong></summary>

```bash
# 1. 克隆项目
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 2. 创建虚拟环境
python -m venv .venv

# 3. 激活虚拟环境
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 4. 复制配置文件
cp config.json.example config.json

# 5. 安装依赖
pip install -r requirements.txt

# 6. 配置 API 密钥
# 编辑 config.json 文件，填入你的 API 密钥
```
</details>

<details>
<summary><strong>使用 uv 安装（更快）</strong></summary>

```bash
# 1. 安装 uv（如果未安装）
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 克隆项目
git clone https://github.com/Xxiii8322766509/NagaAgent.git
cd NagaAgent

# 3. 复制配置文件
cp config.json.example config.json

# 4. 使用 uv 创建虚拟环境并安装依赖
uv sync

# 5. 激活虚拟环境（可选，uv 会自动处理）
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate   # Windows
# 也可以使用uv run main.py直接启动

# 6. 配置 API 密钥
# 编辑 config.json 文件，填入你的 API 密钥
```
</details>

### 🗄️ 启动 Neo4j 数据库（用于知识图谱）

<details>
<summary><strong>使用 Docker（推荐）</strong></summary>

```bash
# 启动 Neo4j 容器
docker run -d \
  --restart always \
  --name naga-neo4j \
  --publish=7474:7474 \
  --publish=7687:7687 \
  --env NEO4J_AUTH=neo4j/your_password \
  --volume=neo4j_data:/data \
  neo4j:latest
```

如果端口被占用，可以使用其他端口：
```bash
--publish=8474:7474 --publish=8687:7687
```
并相应修改config.json中的配置
</details>

<details>
<summary><strong>不使用 Docker</strong></summary>

1. 下载并安装 Neo4j Desktop
2. 创建新项目并启动数据库
3. 在 config.json 中配置连接参数
</details>

### ⚙️ 配置 API 密钥

编辑 `config.json` 文件，设置 LLM API：

```json
{
  "api": {
    "api_key": "your-api-key-here",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 8192
  }
}
```

支持所有提供OpenAI兼容接口的模型服务商。
### 🚀 启动应用

<details>
<summary><strong>Windows 启动方式</strong></summary>
打开start_with_tray.bat
</details>

<details>
<summary><strong>macOS/Linux 启动方式</strong></summary>

```bash
# 直接启动
python main.py

# 或使用脚本
./start.sh
```
</details>

启动后将自动开启：
- 🖥️ PyQt5 图形界面（端口无需配置）
- 🌐 RESTful API 服务器（默认 8000）
- 🤖 Agent 服务器（默认 8001）
- 🔧 MCP 服务器（默认 8003）
- 🎤 TTS 语音服务（默认 5048）
- 🧠 GRAG 知识图谱系统

---

## 📁 项目架构

NagaAgent 4.0 采用微服务架构设计，各功能模块独立且可扩展：

```
NagaAgent/
├── 📁 main.py                 # 主程序入口
├── 📁 config.json            # 配置文件
├── 📁 apiserver/             # API 服务层（端口 8000）
│   ├── api_server.py         # FastAPI 主服务器
│   ├── llm_service.py        # LLM 服务接口
│   ├── message_manager.py    # 消息管理器
│   └── streaming_tool_extractor.py  # 流式工具提取
├── 📁 agentserver/           # Agent 服务层（端口 8001）
│   ├── agent_server.py       # Agent 管理服务器
│   ├── agent_manager.py      # Agent 任务调度器
│   └── agent_computer_control/  # 电脑控制 Agent
├── 📁 mcpserver/             # MCP 服务层（端口 8003）
│   ├── mcp_server.py         # MCP 主服务器
│   ├── mcp_manager.py        # MCP 服务管理器
│   ├── mcp_registry.py       # 服务注册中心
│   ├── agent_bilibili_video/ # B站视频 Agent
│   ├── agent_comic_downloader/  # 漫画下载 Agent
│   ├── agent_crawl4ai/       # 网页爬虫 Agent
│   ├── agent_memory/         # 记忆管理 Agent
│   ├── agent_naga_portal/    # Naga 门户 Agent
│   ├── agent_online_search/  # 在线搜索 Agent
│   ├── agent_playwright_master/  # 浏览器自动化 Agent
│   ├── agent_weather_time/   # 天气时间 Agent
│   └── agent_system_control/ # 系统控制 Agent
├── 📁 summer_memory/         # GRAG 知识图谱系统
│   ├── memory_manager.py     # 记忆管理器
│   ├── quintuple_extractor.py  # 五元组提取器
│   ├── graph.py             # Neo4j 图操作
│   └── rag_query_tri.py     # RAG 查询引擎
├── 📁 voice/                # 语音交互系统
│   ├── input/               # 语音输入（ASR）
│   │   └── unified_voice_manager.py  # 统一语音管理
│   └── output/              # 语音输出（TTS）
│       ├── tts_handler.py   # TTS 处理器
│       └── server.py        # TTS 服务器
├── 📁 ui/                   # 用户界面
│   ├── pyqt_chat_window.py  # 主聊天窗口
│   ├── message_renderer.py  # 消息渲染器
│   ├── live2d/             # Live2D 虚拟形象
│   └── tray/               # 系统托盘
├── 📁 system/              # 系统核心
│   ├── config.py           # 全局配置
│   └── system_checker.py   # 系统检测
└── 📁 mqtt_tool/           # MQTT 工具
```

---

## 🛠️ 详细安装指南

### 📦 依赖管理

NagaAgent 使用 `nagaagent-core` 核心包整合了主要依赖：

```bash
# 安装所有依赖
pip install -r requirements.txt

# 或使用 uv（更快）
uv sync
```

### 🔍 系统环境检测

```bash
# 运行环境检测
python main.py --check-env

# 检查内容包括：
- Python 版本兼容性
- 虚拟环境状态
- 核心依赖包完整性
- 配置文件有效性
- 端口可用性
- Neo4j 连接状态
```

### ⚠️ 常见问题解决

<details>
<summary><strong>Windows 环境问题</strong></summary>

**问题：C++ 编译工具缺失**
```powershell
# 下载安装 Microsoft Visual C++ Build Tools
# https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

**问题：权限错误**
```powershell
# 以管理员身份运行 PowerShell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```
</details>

<details>
<summary><strong>macOS 环境问题</strong></summary>

**问题：Python 版本过低**
```bash
brew install python@3.11
echo 'export PATH="/usr/local/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
```

**问题：PyAudio 安装失败**
```bash
brew install portaudio
pip install pyaudio
```
</details>

<details>
<summary><strong>Linux 环境问题</strong></summary>

**问题：系统依赖缺失**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3-dev portaudio19-dev

# CentOS/RHEL
sudo yum install python3-devel portaudio-devel
```

**问题：Docker 权限**
```bash
sudo usermod -aG docker $USER
newgrp docker
```
</details>

---

## ⚙️ 配置说明

### 完整配置文件示例

`config.json` 包含所有模块的配置：

```json
{
  "system": {
    "version": "4.0",
    "ai_name": "娜迦日达",
    "debug": true,
    "log_level": "DEBUG"
  },
  "api": {
    "api_key": "your-api-key",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 8192,
    "persistent_context": true,
    "context_load_days": 3
  },
  "api_server": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8000,
    "auto_start": true,
    "docs_enabled": true
  },
  "grag": {
    "enabled": true,
    "auto_extract": true,
    "context_length": 5,
    "similarity_threshold": 0.6,
    "neo4j_uri": "neo4j://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your_password"
  },
  "voice_realtime": {
    "enabled": false,
    "provider": "qwen",
    "api_key": "your-dashscope-api-key",
    "model": "qwen3-omni-flash-realtime"
  },
  "live2d": {
    "enabled": false,
    "model_path": "ui/live2d/live2d_models/characters/llny/mianfeimox/llny.model3.json",
    "fallback_image": "ui/standby.png"
  },
  "online_search": {
    "searxng_url": "https://searxng.pylindex.top",
    "engines": ["google", "bing", "duckduckgo"],
    "num_results": 5
  }
}
```

### 配置热更新

NagaAgent 支持实时配置更新，无需重启：

```python
# 配置变更会自动生效
# 修改 config.json 后保存即可
# 支持的配置项：
- API 参数（温度、模型等）
- 系统设置（调试模式、日志级别）
- GRAG 参数（阈值、上下文长度）
- UI 设置（透明度、主题）
```

---

## 🌟 核心功能

### 1. 🧠 GRAG 知识图谱记忆系统

基于 Neo4j 的持久化记忆系统，能够：
- 自动提取对话中的实体、关系和属性
- 构建知识图谱并进行可视化
- 基于相似度的智能检索
- 支持历史对话导入

### 2. 🔧 MCP 服务生态

内置丰富的 MCP 服务：

| 服务名称 | 功能描述 | 调用示例 |
|---------|---------|---------|
| computer_control | 电脑控制（鼠标键盘） | 点击、输入、截图 |
| file_manager | 文件管理 | 读写、搜索、编辑 |
| coder | 代码执行 | Python 代码运行 |
| weather_time | 天气查询 | 实时天气、时间 |
| comic_downloader | 漫画下载 | 支持多平台 |
| bilibili_video | B站视频 | 搜索、下载 |
| memory | 记忆管理 | 查询、管理知识图谱 |
| system_control | 系统控制 | 音量、亮度、WiFi |
| online_search | 在线搜索 | Google、Bing 搜索 |

### 3. 🎤 实时语音交互

- **语音输入**：支持多种 ASR 引擎
- **语音输出**：兼容 OpenAI TTS API
- **流式处理**：边说边听，实时交互
- **多语言支持**：中文、英文等多种语言

### 4. 🤖 多 Agent 协作

智能任务调度系统：
- 意图识别和任务分解
- 多 Agent 并行执行
- 结果整合和反馈
- 支持复杂工作流

### 5. 🎭 Live2D 虚拟形象

- 独立 Live2D 渲染引擎
- 丰富的动画和表情
- 鼠标交互响应
- 自动回退到静态图片

### 6. 🌳 深度思考引擎

基于遗传算法的思考系统：
- 多分支并行思考
- 问题难度评估
- 用户偏好学习
- 思考路径优化

---

## 🌐 RESTful API 服务

### API 服务器（端口 8000）

提供完整的 REST API 接口：

#### 核心端点

```http
# 流式对话
POST /chat/stream
Content-Type: application/json

{
  "message": "你好",
  "session_id": "user123",
  "stream": true
}

# 普通对话
POST /chat
Content-Type: application/json

{
  "message": "帮我写个Python脚本",
  "session_id": "user123"
}

# 会话管理
GET /sessions          # 获取所有会话
GET /sessions/{id}     # 获取会话详情
DELETE /sessions/{id}  # 删除会话

# 系统信息
GET /health           # 健康检查
GET /system/info      # 系统信息
GET /system/stats     # 运行统计
```

#### SSE 流式输出

```javascript
// JavaScript 示例
const eventSource = new EventSource('/chat/stream');
eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log(data.content);
};
```

### Agent 服务器（端口 8001）

Agent 任务调度接口：

```http
# 提交任务
POST /tasks
{
  "agent_name": "computer_control",
  "task": {"action": "click", "x": 100, "y": 200}
}

# 查询任务
GET /tasks/{task_id}

# 获取能力列表
GET /capabilities
```

### MCP 服务器（端口 8003）

MCP 服务管理接口：

```http
# 获取所有服务
GET /mcp/services

# 获取服务详情
GET /mcp/services/{service_name}

# 执行工具
POST /mcp/services/{service_name}/tools/{tool_name}
```

---

## 🔧 工具调用系统

### 调用格式

#### MCP 服务调用
```json
{
  "agentType": "mcp",
  "service_name": "computer_control",
  "tool_name": "click",
  "x": 100,
  "y": 200
}
```

#### Agent 调用
```json
{
  "agentType": "agent",
  "agent_name": "WeatherAgent",
  "prompt": "查询北京今天的天气"
}
```

### 调用流程

1. LLM 分析用户意图
2. 生成工具调用 JSON
3. 系统解析并路由到对应服务
4. 执行工具并返回结果
5. LLM 处理结果并继续或结束

### 最大循环次数

- 流式模式：5 次
- 非流式模式：5 次
- 可在配置文件中调整

---

## 📝 开发指南

### 创建自定义 Agent

1. **创建 MCP 类型 Agent**

```python
# mcpserver/agent_mytool/agent_mytool.py
from mcpserver.agents import Agent

class MyToolAgent(Agent):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="我的自定义工具"
        )

    async def handle_handoff(self, **kwargs):
        # 实现工具逻辑
        return {"result": "执行成功"}
```

2. **创建 agent-manifest.json**

```json
{
  "name": "my_tool",
  "displayName": "我的工具",
  "description": "自定义工具描述",
  "version": "1.0.0",
  "agentType": "mcp",
  "entryPoint": {
    "module": "agent_mytool.agent_mytool",
    "class": "MyToolAgent"
  }
}
```

3. **重启服务自动注册**

### Agent 配置最佳实践

1. 使用环境变量管理敏感信息
2. 合理设置 temperature 和 max_tokens
3. 优化提示词，使用占位符
4. 设置合理的会话 TTL

### 性能优化建议

1. 启用配置缓存
2. 控制并发 Agent 数量
3. 定期清理过期会话
4. 监控系统资源使用

---

## ❓ 常见问题

### Q: 如何查看运行日志？

A: 日志位置：
- 主日志：`logs/naga_agent.log`
- API 日志：`logs/api_server.log`
- MCP 日志：`logs/mcp_server.log`

### Q: 如何重置知识图谱？

A:
```bash
# 清空 Neo4j 数据
docker exec -it naga-neo4j cypher-shell -u neo4j -p your_password "MATCH (n) DETACH DELETE n"
```

### Q: 端口冲突怎么办？

A: 修改 `config.json` 中的端口配置：
```json
{
  "api_server": {"port": 8001},
  "agentserver": {"port": 8002},
  "mcpserver": {"port": 8004}
}
```

### Q: 如何备份配置和数据？

A:
```bash
# 备份配置
cp config.json config.json.backup

# 备份 Neo4j 数据
docker exec naga-neo4j neo4j-admin dump --database=neo4j --to=/dump/backup.dump
```

### Q: 如何开启调试模式？

A: 修改 `config.json`：
```json
{
  "system": {
    "debug": true,
    "log_level": "DEBUG"
  }
}
```

---

## 🤝 贡献指南

我们欢迎所有形式的贡献！

### 贡献方式

1. **Fork 项目**
2. **创建特性分支** (`git checkout -b feature/AmazingFeature`)
3. **提交更改** (`git commit -m 'Add some AmazingFeature'`)
4. **推送分支** (`git push origin feature/AmazingFeature`)
5. **提交 Pull Request**

### 开发规范

- 添加适当的注释和文档
- 确保测试通过
- 更新相关文档

### 联系方式

- **Issues**: [GitHub Issues](https://github.com/Xxiii8322766509/NagaAgent/issues)
- **讨论**: [GitHub Discussions](https://github.com/Xxiii8322766509/NagaAgent/discussions)
- **邮箱**: 1781393885@qq.com

---

## 🙏 致谢

感谢以下开源项目和贡献者：

- [OpenAI](https://openai.com/) - 强大的 AI 模型以及库支持
- [Neo4j](https://neo4j.com/) - 图数据库
- [PyQt5](https://riverbankcomputing.com/software/pyqt/) - GUI 框架
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架
- [MCP](https://modelcontextprotocol.io/) - 模型上下文协议
- 所有贡献者和社区成员

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

<div align="center">⭐ 如果这个项目对您有帮助，请考虑给我们一个 Star！
</div>
