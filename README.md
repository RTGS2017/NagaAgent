# NagaAgent 3.0

> 智能对话助手，支持多MCP服务、流式语音交互、GRAG知识图谱记忆系统、RESTful API接口、极致精简代码风格。

---

## ⚡ 快速开始
1. 克隆项目
   ```bash
   git clone [项目地址]
   cd NagaAgent
   ```
2. 一键配置

   **Windows:**
   ```powershell
   .\setup.ps1
   ```
   **Mac:**
   ```bash
   chmod +x quick_deploy_mac.sh
   ./quick_deploy_mac.sh
   ```
   - 自动创建虚拟环境并安装依赖
   - 配置支持toolcall的LLM，推荐DeepSeekV3
   - 初始化GRAG知识图谱记忆系统
3. 启动

   **Windows:**
   ```powershell
   .\start.bat
   ```
   **Mac:**
   ```bash
   ./start_mac.sh
   ```

启动后将自动开启PyQt5界面和RESTful API服务器，可同时使用界面对话和API接口。

---

## 🖥️ 系统要求
- **Windows:** Windows 10/11 + PowerShell 5.1+
- **Mac:** macOS 10.15 (Catalina) 或更高版本 + Homebrew
- **通用:** Python 3.8+ (推荐 3.11)

---

## 🛠️ 依赖安装与环境配置

### Windows 环境
- 所有依赖见`pyproject.toml`
- 推荐使用 `uv` 作为包管理器，自动处理依赖安装和虚拟环境
- 如遇`greenlet`、`pyaudio`等安装失败，需先装[Microsoft Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)，勾选C++ build tools
- 浏览器自动化需`playwright`，首次用需`python -m playwright install chromium`
- 依赖安装命令：
  ```powershell
  # 推荐使用 uv（现代化包管理器）
  uv sync
  python -m playwright install chromium
  
  # 或者使用传统 pip
  python -m venv .venv
  .venv\Scripts\Activate
  pip install -e .
  python -m playwright install chromium
  ```

### Mac 环境
- 系统依赖通过Homebrew安装：
  ```bash
  # 安装基础依赖
  brew install python@3.11 portaudio
  brew install --cask google-chrome
  ```
- Python依赖安装：
  ```bash
  # 推荐使用 uv（现代化包管理器）
  uv sync
  python -m playwright install chromium
  
  # 或者使用传统 pip
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -e .
  python -m playwright install chromium
  ```
- 如遇PyAudio安装失败：
  ```bash
  brew install portaudio
  uv sync --extra audio  # 或 pip install pyaudio
  ```

### 环境检查（跨平台通用）
```bash
python check_env.py
```

---

## ⚙️ 配置说明

### 重要配置变更说明
**v3.0版本配置简化：**
- 移除了`config.json`中的`mcp_services`和`agent_services`静态配置字段
- 系统现在通过动态扫描`agent-manifest.json`文件自动发现和注册服务
- 所有服务信息通过动态服务池实时查询，无需手动维护服务列表

### API 配置
修改 `config.json` 文件中的 `api` 部分：
```json
{
  "api": {
    "api_key": "your-api-key-here",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "temperature": 0.7,
    "max_tokens": 2000,
    "max_history_rounds": 10
  }
}
```

**配置参数说明：**
- `api_key`: LLM API密钥
- `base_url`: API基础URL
- `model`: 使用的模型名称
- `temperature`: 温度参数（0.0-1.0，控制随机性）
- `max_tokens`: 最大输出token数
- `max_history_rounds`: 最大历史对话轮数

### API服务器配置
在 `config.json` 中可配置API服务器相关参数：
```json
{
  "api_server": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8000,
    "auto_start": true,
    "docs_enabled": true
  }
}
```

### GRAG知识图谱记忆系统配置
在 `config.json` 中可配置GRAG记忆系统：
```json
{
  "grag": {
    "enabled": true,
    "auto_extract": true,
    "context_length": 5,
    "similarity_threshold": 0.6,
    "neo4j_uri": "neo4j://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your_password",
    "neo4j_database": "neo4j"
  }
}
```

### 获取 API 密钥
1. 访问对应的LLM服务商官网（如DeepSeek、OpenAI等）
2. 注册账号并创建 API 密钥
3. 将密钥填入 `config.json` 文件的 `api.api_key` 字段

---

## 🌟 主要特性
- **全局变量/路径/密钥统一`config.py`管理**，支持.env和环境变量，所有变量唯一、无重复定义
- **RESTful API接口**，自动启动HTTP服务器，支持完整对话功能和流式输出，可集成到任何前端或服务
- DeepSeek流式对话，支持上下文召回与GRAG知识图谱检索
- **GRAG知识图谱记忆系统**，基于Neo4j的三元组知识图谱，自动提取对话中的实体关系，支持记忆查询和管理
- **HANDOFF工具调用循环**，自动解析和执行LLM返回的工具调用，支持多轮递归调用
- **多Agent能力扩展：浏览器、文件、代码等多种Agent即插即用，所有Agent均可通过工具调用循环机制统一调用**
- **跨平台兼容：Windows/Mac自动适配，浏览器路径自动检测，依赖智能安装**
- **流式语音交互**，基于Edge-TTS的OpenAI兼容语音合成，支持pygame后台直接播放和智能分句
- 代码极简，注释全中文，组件解耦，便于扩展
- PyQt5动画与UI，支持PNG序列帧，loading动画极快
- 日志/检索/索引/主题/参数全部自动管理
- 记忆权重动态调整，支持AI/人工标记important，权重/阈值/清理策略全部在`config.py`统一管理
- **所有前端UI与后端解耦，前端只需解析后端JSON，自动适配message/data.content等多种返回结构**
- **前端换行符自动适配，无论后端返回`\n`还是`\\n`，PyQt界面都能正确分行显示**
- **所有Agent的注册元数据已集中在`mcpserver/mcp_registry.py`，主流程和管理器极简，扩展维护更方便。只需维护一处即可批量注册/扩展所有Agent服务。**
- **自动注册/热插拔Agent机制，新增/删除Agent只需增删py文件，无需重启主程序**
- **Agent Manifest标准化**，统一的`agent-manifest.json`格式，支持完整的字段验证和类型检查
- **动态服务池查询**，系统通过扫描`agent-manifest.json`文件自动发现和注册服务，无需手动配置静态服务列表
- **AgentManager独立系统**，支持Agent的配置加载、会话管理、消息组装和LLM调用，提供完整的Agent生命周期管理
- **智能占位符替换**，支持Agent配置、环境变量、时间信息等多种占位符，实现动态提示词生成
- **完整消息序列构建**，自动组装系统消息、历史消息和用户消息，确保对话上下文完整性
- **多模型提供商支持**，支持OpenAI、DeepSeek、Anthropic等多种LLM提供商，每个Agent可独立配置
- **会话隔离与TTL管理**，支持多用户多会话隔离，自动清理过期会话数据
- **统一工具调用接口**，MCP和Agent类型服务通过统一的HANDOFF格式调用，支持混合调用场景
- 聊天窗口支持**Markdown语法**，包括标题、粗体、斜体、代码块、表格、图片等。

---

## 🗂️ 目录结构
```
NagaAgent/
├── main.py                     # 主入口
├── config.py                   # 全局配置
├── conversation_core.py        # 对话核心（含工具调用循环主逻辑）
├── apiserver/                  # API服务器模块
│   ├── api_server.py           # FastAPI服务器
│   ├── start_server.py         # 启动脚本
│   └── README.md               # API文档
├── agent/                      # 预处理系统模块
│   ├── preprocessor.py         # 消息预处理
│   ├── plugin_manager.py       # 插件管理
│   ├── api_server.py           # 代理API服务器
│   ├── image_processor.py      # 图片处理
│   ├── start_server.py         # 启动脚本
│   └── README.md               # 预处理系统文档
├── mcpserver/
│   ├── mcp_manager.py          # MCP服务管理
│   ├── mcp_registry.py         # Agent注册与schema元数据
│   ├── agent_manager.py        # Agent管理器（独立系统）
│   ├── dynamic_agent_registry.py # 动态Agent注册系统
│   ├── AGENT_MANIFEST_TEMPLATE.json # Agent manifest模板
│   ├── MANIFEST_STANDARDIZATION.md # Manifest标准化规范
│   ├── agent_xxx/              # 各类自定义Agent（如file、coder、browser等）
│   │   └── agent-manifest.json # Agent配置文件
├── agent_configs/              # Agent配置文件目录
│   ├── agents.json             # Agent配置主文件
│   └── *.json                  # 其他Agent配置文件
├── pyproject.toml              # 项目配置和依赖
├── setup.ps1                   # Windows配置脚本
├── start.bat                   # Windows启动脚本
├── setup_mac.sh                # Mac配置脚本
├── quick_deploy_mac.sh         # Mac一键部署脚本
├── check_env.py                # 跨平台环境检查
├── summer_memory/              # GRAG知识图谱记忆系统
│   ├── memory_manager.py       # 记忆管理器
│   ├── extractor_ds_tri.py     # 三元组提取器
│   ├── graph.py                # Neo4j图谱操作
│   ├── rag_query_tri.py        # 记忆查询
│   ├── visualize.py            # 图谱可视化
│   ├── main.py                 # 独立运行入口
│   └── triples.json            # 三元组缓存
├── logs/                       # 日志（含历史txt对话）
│   ├── 2025-04-27.txt
│   ├── 2025-05-05.txt
│   └── ...
├── voice/                      # 语音相关
│   ├── voice_config.py
│   └── voice_handler.py
├── ui/                         # 前端UI
│   ├── pyqt_chat_window.py     # PyQt聊天窗口
│   └── response_utils.py       # 前端通用响应解析工具
├── models/                     # 模型等
├── README.md                   # 项目说明
└── ...
```

---

## 🔧 工具调用循环机制

### 系统概述
NagaAgent支持两种类型的工具调用：
- **MCP服务调用**：通过`agentType: mcp`调用MCP类型的Agent
- **Agent服务调用**：通过`agentType: agent`调用Agent类型的Agent

### 工具调用格式
系统支持两种格式的工具调用：

#### MCP服务调用格式
```json
{
  "agentType": "mcp",
  "service_name": "MCP服务名称",
  "tool_name": "工具名称",
  "参数名": "参数值"
}
```

#### Agent服务调用格式
```json
{
  "agentType": "agent",
  "agent_name": "Agent名称",
  "prompt": "任务内容"
}
```

### 工具调用流程
1. **LLM输出HANDOFF格式**：LLM根据用户需求输出工具调用请求
2. **自动解析agentType**：系统首先解析agentType字段，确定调用类型
3. **路由到对应管理器**：
   - `mcp`类型 → 路由到MCPManager处理
   - `agent`类型 → 路由到AgentManager处理
4. **执行工具调用**：调用对应的服务执行具体任务
5. **结果返回LLM**：将工具执行结果返回给LLM
6. **循环处理**：重复步骤2-5，直到LLM输出普通文本或无工具调用

### 配置参数
```python
# config.py中的工具调用循环配置
MAX_handoff_LOOP_STREAM = 5      # 流式模式最大工具调用循环次数
MAX_handoff_LOOP_NON_STREAM = 5  # 非流式模式最大工具调用循环次数
SHOW_handoff_OUTPUT = False      # 是否显示工具调用输出
```

### 使用示例

#### MCP服务调用示例
```python
# 浏览器操作
await mcp.handoff(
    service_name="playwright",
    task={"action": "open_browser", "url": "https://www.bilibili.com"}
)

# 文件操作
await mcp.handoff(
    service_name="file",
    task={"action": "read", "path": "test.txt"}
)

# 代码执行
await mcp.handoff(
    service_name="coder",
    task={"action": "run", "file": "main.py"}
)
```

#### Agent服务调用示例
```python
# 调用对话Agent
result = await agent_manager.call_agent(
    agent_name="ExampleAgent",
    prompt="请帮我分析这份数据",
    session_id="user_123"
)

# 通过工具调用循环调用Agent
# LLM会输出：
# <<<[HANDOFF]>>>
# agentType: 「始」agent「末」
# agent_name: 「始」ExampleAgent「末」
# prompt: 「始」请帮我分析这份数据「末」
# <<<[END_HANDOFF]>>>
```

#### 混合调用示例
```python
# 一个完整的工具调用循环可能包含：
# 1. 调用文件Agent读取数据
# 2. 调用分析Agent处理数据
# 3. 调用浏览器Agent展示结果

# LLM会自动选择合适的Agent类型：
# - 文件操作 → MCP类型
# - 数据分析 → Agent类型
# - 浏览器操作 → MCP类型
```

---

## 🌐 多Agent与MCP服务
- **所有Agent的注册、schema、描述均集中在`mcpserver/mcp_registry.py`，批量管理，极简扩展**
- 支持浏览器、文件、代码等多种Agent，全部可通过工具调用循环机制统一调用
- Agent能力即插即用，自动注册/热插拔，无需重启主程序
- **动态服务池查询**：支持实时查询服务信息、按能力搜索、获取工具列表等

### 动态服务池查询功能

#### 核心查询方法
```python
from mcpserver.mcp_registry import (
    get_all_services_info,      # 获取所有服务信息
    get_service_info,           # 获取单个服务详情
    query_services_by_capability, # 按能力搜索服务
    get_service_statistics,     # 获取统计信息
    get_available_tools         # 获取服务工具列表
)

# 获取所有服务信息
services_info = get_all_services_info()

# 按能力搜索服务
file_services = query_services_by_capability("文件")

# 获取服务统计
stats = get_service_statistics()
```

#### MCPManager查询接口
```python
from mcpserver.mcp_manager import get_mcp_manager

mcp_manager = get_mcp_manager()

# 获取可用服务列表
available_services = mcp_manager.get_available_services()

# 获取过滤后的服务（MCP vs Agent）
filtered_services = mcp_manager.get_available_services_filtered()

# 查询服务详情
service_detail = mcp_manager.query_service_by_name("FileAgent")

# 按能力搜索
matching_services = mcp_manager.query_services_by_capability("文件")

# 获取服务工具
tools = mcp_manager.get_service_tools("FileAgent")
```

#### API端点
- `GET /mcp/services` - 获取所有服务列表和统计信息
- `GET /mcp/services/{service_name}` - 获取指定服务详情
- `GET /mcp/services/search/{capability}` - 按能力搜索服务
- `GET /mcp/services/{service_name}/tools` - 获取服务工具列表
- `GET /mcp/statistics` - 获取服务统计信息

#### 查询结果示例
```json
{
  "status": "success",
  "services": [
    {
      "name": "FileAgent",
      "description": "支持文件的读写、创建、删除、目录管理等操作。",
      "display_name": "文件操作Agent",
      "version": "1.0.0",
      "available_tools": [
        {
          "name": "read",
          "description": "读取指定文件内容",
          "example": "{\"action\": \"read\", \"path\": \"test.txt\"}"
        }
      ]
    }
  ],
  "statistics": {
    "total_services": 5,
    "total_tools": 17,
    "registered_services": ["CoderAgent", "FileAgent", "AppLauncherAgent", "WeatherTimeAgent", "SystemControlAgent"],
    "last_update": "动态更新"
  }
}
```

### 典型用法示例

```python
# 读取文件内容
await s.mcp.handoff(
  service_name="file",
  task={"action": "read", "path": "test.txt"}
)
# 运行Python代码
await s.mcp.handoff(
  service_name="coder",
  task={"action": "run", "file": "main.py"}
)
```

## 🤖 AgentManager 独立系统

### 系统概述
AgentManager是一个独立的Agent注册和调用系统，支持从配置文件动态加载Agent定义，提供统一的调用接口和完整的生命周期管理。系统支持两种类型的Agent：
- **MCP类型Agent**：通过`agent-manifest.json`注册，支持工具调用和复杂任务处理
- **Agent类型Agent**：通过配置文件注册，专注于对话和LLM调用

### 核心功能

#### 1. 配置管理
- **动态配置加载**：从`agent_configs/`目录自动扫描和加载Agent配置文件
- **配置验证**：自动验证Agent配置的完整性和有效性
- **热重载**：支持运行时重新加载配置，无需重启系统
- **环境变量支持**：支持从环境变量和`.env`文件加载敏感配置

#### 2. 会话管理
- **多会话支持**：每个Agent支持多个独立的会话上下文
- **历史记录**：自动维护对话历史，支持上下文召回
- **会话过期**：自动清理过期的会话数据，节省内存
- **会话隔离**：不同用户和不同Agent的会话完全隔离

#### 3. 消息组装
- **系统消息**：自动构建Agent身份、行为、风格的系统提示词
- **历史消息**：集成多轮对话历史，保持上下文连续性
- **用户消息**：处理当前用户输入，支持占位符替换
- **消息验证**：自动验证消息序列的格式和完整性

#### 4. 智能占位符替换
支持多种类型的占位符替换：

**Agent配置占位符**：
- `{{AgentName}}` - Agent名称
- `{{MaidName}}` - Agent名称（兼容旧格式）
- `{{BaseName}}` - 基础名称
- `{{Description}}` - 描述信息
- `{{ModelId}}` - 模型ID
- `{{Temperature}}` - 温度参数
- `{{MaxTokens}}` - 最大输出token数
- `{{ModelProvider}}` - 模型提供商

**环境变量占位符**：
- `{{ENV_VAR_NAME}}` - 系统环境变量（支持任意大写字母和下划线的环境变量）

**时间占位符**：
- `{{CurrentTime}}` - 当前时间 (HH:MM:SS)
- `{{CurrentDate}}` - 当前日期 (YYYY-MM-DD)
- `{{CurrentDateTime}}` - 完整时间 (YYYY-MM-DD HH:MM:SS)

#### 5. LLM集成
- **多模型支持**：支持OpenAI、DeepSeek等多种LLM提供商
- **配置隔离**：每个Agent使用独立的模型配置（API密钥、基础URL等）
- **错误处理**：完善的API调用错误处理和重试机制
- **调试模式**：支持详细的调试日志输出

### 配置文件格式

#### Agent配置文件示例
```json
{
  "ExampleAgent": {
    "model_id": "deepseek-chat",
    "name": "示例助手",
    "base_name": "ExampleAgent",
    "system_prompt": "你是{{AgentName}}，一个专业的{{Description}}。\n\n当前时间：{{CurrentDateTime}}\n模型：{{ModelId}}\n温度：{{Temperature}}\n\n请用中文回答，保持专业和友好的态度。",
    "max_output_tokens": 8192,
    "temperature": 0.7,
    "description": "智能助手，擅长回答各种问题",
    "model_provider": "openai",
    "api_base_url": "https://api.deepseek.com/v1",
    "api_key": "{{DEEPSEEK_API_KEY}}"
  }
}
```

#### 配置字段说明
- `model_id`: LLM模型ID（必需）
- `name`: Agent显示名称（中文，必需）
- `base_name`: Agent基础名称（英文）
- `system_prompt`: 系统提示词，支持占位符
- `max_output_tokens`: 最大输出token数（默认8192）
- `temperature`: 温度参数（0.0-1.0，默认0.7）
- `description`: Agent功能描述
- `model_provider`: 模型提供商（默认openai）
- `api_base_url`: API基础URL（可选，默认使用提供商标准URL）
- `api_key`: API密钥（支持环境变量占位符）

#### 环境变量配置示例
```bash
# .env文件示例
DEEPSEEK_API_KEY=your_deepseek_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 使用示例

#### 基本调用
```python
from mcpserver.agent_manager import get_agent_manager

# 获取AgentManager实例
agent_manager = get_agent_manager()

# 调用Agent
result = await agent_manager.call_agent(
    agent_name="ExampleAgent",
    prompt="请帮我分析这份数据",
    session_id="user_123"
)

if result["status"] == "success":
    print(result["result"])
else:
    print(f"调用失败: {result['error']}")
```

#### 便捷函数调用
```python
from mcpserver.agent_manager import call_agent, list_agents, get_agent_info

# 便捷调用
result = await call_agent("ExampleAgent", "你好")

# 获取Agent列表
agents = list_agents()
for agent in agents:
    print(f"{agent['name']}: {agent['description']}")

# 获取Agent详细信息
agent_info = get_agent_info("ExampleAgent")
if agent_info:
    print(f"模型: {agent_info['model_id']}")
    print(f"温度: {agent_info['temperature']}")
```

#### 会话管理
```python
# 获取会话历史
history = agent_manager.get_agent_session_history("ExampleAgent", "user_123")

# 更新会话历史
agent_manager.update_agent_session_history(
    "ExampleAgent", 
    "用户消息", 
    "助手回复", 
    "user_123"
)

# 检查会话是否过期
is_expired = agent_manager._is_context_expired(timestamp)
```

#### 配置管理
```python
# 重新加载配置
agent_manager.reload_configs()

# 启用调试模式
agent_manager.debug_mode = True

# 获取可用Agent列表
available_agents = agent_manager.get_available_agents()
```

### 系统集成

#### 与MCP系统的集成
AgentManager与MCP系统完全集成，支持统一的调用接口：

```python
# 通过MCP系统调用Agent
result = await mcp_manager.unified_call(
    service_name="ExampleAgent",
    tool_name="call",
    args={"prompt": "用户输入"}
)
```

#### 工具调用格式
```
<<<[HANDOFF]>>>
agentType: 「始」agent「末」
agent_name: 「始」ExampleAgent「末」
prompt: 「始」用户任务内容「末」
<<<[END_HANDOFF]>>>
```

#### 动作调用格式
```python
# 通过动作调用Agent
result = await agent_manager.call_agent_by_action(
    agent_name="ExampleAgent",
    action_args={
        "action": "analyze_data",
        "data_type": "csv",
        "file_path": "data.csv"
    }
)
```

### 高级功能

#### 1. 消息序列验证
自动验证消息序列的格式和完整性：
- 检查消息格式是否正确
- 确保系统消息在开头
- 验证角色和内容字段
- 支持消息序列的完整性检查

#### 2. 调试模式
启用调试模式可查看详细的消息组装过程：
```python
agent_manager.debug_mode = True
```

#### 3. 定期清理
系统自动定期清理过期的会话数据，默认每小时执行一次。

#### 4. 错误处理
- **配置错误**：自动检测和报告配置问题
- **API错误**：完善的LLM API调用错误处理
- **会话错误**：会话数据损坏时的自动恢复
- **网络错误**：网络连接问题的重试机制

#### 5. 性能优化
- **内存管理**：自动清理过期会话，防止内存泄漏
- **缓存机制**：Agent配置缓存，提高响应速度
- **并发支持**：支持多个Agent的并发调用
- **资源限制**：可配置的最大历史消息数量限制

### 系统架构

#### 组件关系
```
AgentManager
├── 配置管理 (AgentConfig)
├── 会话管理 (AgentSession)
├── 消息组装 (MessageBuilder)
├── 占位符替换 (PlaceholderReplacer)
├── LLM集成 (LLMClient)
└── 错误处理 (ErrorHandler)
```

#### 数据流
1. **配置加载** → 从文件加载Agent配置
2. **会话初始化** → 创建或恢复会话上下文
3. **消息组装** → 构建完整的消息序列
4. **占位符替换** → 处理动态内容替换
5. **LLM调用** → 调用对应的LLM API
6. **结果处理** → 更新会话历史并返回结果

---

## 📋 Agent Manifest标准化

### 标准化规范
所有Agent必须使用标准化的`agent-manifest.json`配置文件，确保一致性和可维护性。

#### 必需字段
- `name`: Agent唯一标识符
- `displayName`: 显示名称
- `version`: 版本号（x.y.z格式）
- `description`: 功能描述
- `author`: 作者或模块名称
- `agentType`: Agent类型（mcp/agent）
- `entryPoint`: 入口点配置（module和class）

#### 可选字段
- `factory`: 工厂函数配置
- `communication`: 通信配置
- `capabilities`: 能力描述
- `inputSchema`: 输入模式定义
- `configSchema`: 配置模式定义
- `runtime`: 运行时信息

### 验证和测试
```bash
# 验证所有manifest文件
python test_manifest_standardization.py
```

### 模板和文档
- 模板文件：`mcpserver/AGENT_MANIFEST_TEMPLATE.json`
- 规范文档：`mcpserver/MANIFEST_STANDARDIZATION.md`
- 动态注册系统：`mcpserver/dynamic_agent_registry.py`

### 创建新Agent

#### 创建MCP类型Agent
1. 在`mcpserver/`目录下创建新的Agent目录
2. 复制`AGENT_MANIFEST_TEMPLATE.json`到Agent目录
3. 修改manifest文件内容
4. 创建Agent实现类
5. 重启系统自动注册

#### 创建Agent类型Agent
1. 在`agent_configs/`目录下创建配置文件
2. 定义Agent配置（模型、提示词等）
3. 配置环境变量（API密钥等）
4. 重启系统自动加载

### AgentManager配置

#### 基础配置
```python
# config.py中的AgentManager配置
AGENT_MANAGER_CONFIG = {
    "config_dir": "agent_configs",  # 配置文件目录
    "max_history_rounds": 7,        # 最大历史轮数
    "context_ttl_hours": 24,        # 上下文TTL（小时）
    "debug_mode": True,             # 调试模式
    "cleanup_interval": 3600        # 清理间隔（秒）
}
```

#### 会话配置
```python
# 会话管理配置
SESSION_CONFIG = {
    "max_messages": 14,             # 最大消息数量（max_history_rounds * 2）
    "session_timeout": 86400,       # 会话超时时间（秒）
    "auto_cleanup": True            # 自动清理过期会话
}
```

#### 模型配置
```python
# 支持的模型提供商配置
MODEL_PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-3.5-turbo"
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat"
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-3-sonnet-20240229"
    }
}
```

---

## 📝 前端UI与响应适配
- **所有后端返回均为结构化JSON，前端通过`ui/response_utils.py`的`extract_message`方法自动适配多种返回格式**
- 优先显示`data.content`，其次`message`，最后原样返回，兼容所有Agent
- PyQt前端自动将所有`\n`和`\\n`换行符转为`<br>`，多行内容显示无障碍
- UI动画、主题、昵称、透明度等全部可在`config.py`和`pyqt_chat_window.py`灵活配置

---

## 🔊 流式语音交互
- 支持语音输入（流式识别，自动转文字）与语音输出（流式合成，边播边出）
- 依赖与配置详见`voice/voice_config.py`和README相关章节

---

## 📝 其它亮点
- 记忆权重、遗忘阈值、冗余去重、短期/长期记忆容量等全部在`config.py`统一管理，便于灵活调整
- 主题归类、召回、权重提升、清理等全部自动化，AI/人工可标记important内容，重要内容一年内不会被清理
- 检索日志自动记录，参数可调，GRAG配置示例见`config.py`
- 聊天窗口背景透明度、用户名、主题树召回、流式输出、侧栏动画等全部可自定义
- 支持历史对话一键导入GRAG知识图谱记忆系统，兼容主题、分层、三元组等所有新特性
- **工具调用循环自动执行机制，支持多轮递归调用，最大循环次数可配置**

---

## 🆙 历史对话兼容升级
- 支持将旧版txt对话内容一键导入GRAG知识图谱记忆系统，兼容主题、分层、三元组等所有新特性。
- 激活指令：
  ```
  #夏园系统兼容升级
  ```
  - 系统会自动遍历logs目录下所有txt日志，列出所有历史对话内容并编号，输出到终端和`summer_memory/history_dialogs.json`。
- 用户可查看编号后，选择导入方式：
  - 全部导入：
    ```
    python summer_memory/main.py import all
    ```
  - 选择性导入（如第1、3、5-8条）：
    ```
    python summer_memory/main.py import 1,3,5-8
    ```
- 兼容过程自动判重，已入库内容不会重复导入，支持断点续跑。
- 兼容内容全部走AI自动主题归类与分层，完全与新系统一致。
- 详细进度、结果和异常均有反馈，安全高效。

---

## ❓ 常见问题

- 环境检查：`python check_env.py`

### Windows 环境
- Python版本/依赖/虚拟环境/浏览器驱动等问题，详见`setup.ps1`与本README
- IDE报import错误，重启并选择正确解释器
- 语音依赖安装失败，先装C++ Build Tools

### Mac 环境
- Python版本过低：`brew install python@3.11`
- PyAudio安装失败：`brew install portaudio && pip install pyaudio`
- 权限问题：`chmod +x *.sh`

### API服务器问题
- 端口占用：修改`config.py`中的`API_SERVER_PORT`
- 代理干扰：临时禁用代理 `unset ALL_PROXY http_proxy https_proxy`
- 依赖缺失：确保安装了FastAPI和Uvicorn `pip install fastapi uvicorn[standard]`
- 无法访问：检查防火墙设置，确保端口未被阻塞

### 工具调用问题
- 工具调用循环次数过多：调整`config.py`中的`MAX_handoff_LOOP_STREAM`和`MAX_handoff_LOOP_NON_STREAM`
- 工具调用失败：检查MCP服务是否正常运行，查看日志输出
- 格式错误：确保LLM输出严格遵循HANDOFF格式

### GRAG记忆系统问题
- Neo4j连接失败：检查Neo4j服务是否启动，确认连接参数正确
- 记忆查询无结果：检查三元组是否正确提取和存储
- 性能问题：调整`config.py`中的GRAG相关参数

### 通用问题
- 浏览器无法启动，检查playwright安装与网络
- 主题树/索引/参数/密钥全部在`config.py`统一管理
- 聊天输入`#devmode`进入开发者模式，后续对话不写入GRAG记忆，仅用于工具调用测试

### AgentManager问题
- **Agent配置加载失败**：检查`agent_configs/`目录下的JSON文件格式是否正确
- **API调用失败**：确认API密钥配置正确，检查网络连接
- **会话历史丢失**：检查会话TTL配置，确认会话未过期
- **占位符替换失败**：确认环境变量已正确设置
- **内存占用过高**：调整`max_history_rounds`参数，减少历史消息数量

### 最佳实践

#### Agent配置最佳实践
1. **使用环境变量**：敏感信息如API密钥应使用环境变量
2. **合理设置参数**：根据任务需求调整temperature和max_output_tokens
3. **优化提示词**：使用占位符实现动态内容，提高灵活性
4. **会话管理**：合理设置会话TTL，避免内存泄漏

#### 性能优化建议
1. **缓存配置**：启用配置缓存，减少文件读取开销
2. **并发控制**：合理控制并发Agent调用数量
3. **资源清理**：定期清理过期会话和临时数据
4. **监控日志**：启用调试模式监控系统性能

#### 安全建议
1. **API密钥管理**：使用环境变量或密钥管理服务
2. **输入验证**：对用户输入进行验证和清理
3. **错误处理**：避免在错误信息中泄露敏感信息
4. **访问控制**：实现适当的访问控制机制

---

## 📝 许可证
MIT License

---

如需详细功能/API/扩展说明，见各模块注释与代码，所有变量唯一、注释中文、极致精简。

## 聊天窗口自定义
1. 聊天窗口背景透明度由`config.BG_ALPHA`统一控制，取值0~1，默认0.4。
2. 用户名自动识别电脑名，变量`config.USER_NAME`，如需自定义可直接修改该变量。

## 智能历史召回机制
1. 默认按主题分片检索历史，极快且相关性高。
2. 若分片查不到，自动兜底遍历所有主题分片模糊检索，话题跳跃也能召回历史。
3. GRAG知识图谱查询支持直接调用，返回全局最相关历史。
4. 兜底逻辑已集成主流程，无需手动切换。

## ⚡️ 全新流式输出机制
- AI回复支持前后端全链路流式输出，边生成边显示，极致丝滑。
- 后端采用async生成器yield分段内容，前端Worker线程streaming信号实时追加到对话框。
- 彻底无终端print污染，支持大文本不卡顿。
- 如遇依赖包冲突，建议彻底清理全局PYTHONPATH和环境变量，仅用虚拟环境。

## 侧栏与主聊天区动画优化说明
- 侧栏点击切换时，侧栏宽度、主聊天区宽度、输入框高度均采用同步动画，提升视觉流畅度。
- 输入框隐藏采用高度动画，动画结束后自动清除焦点，避免输入法残留。
- 线程处理增加自动释放，避免内存泄漏。
- 相关动画效果可在`ui/pyqt_chat_window.py`的`toggle_full_img`方法中自定义。

### 使用方法
- 点击侧栏即可切换立绘展开/收起，主聊天区和输入框会自动让位并隐藏/恢复。
- 动画时长、缓动曲线等可根据需要调整源码参数。

## 工具调用循环机制详解

### 核心特性
- **自动解析**：系统自动解析LLM返回的HANDOFF格式工具调用
- **递归执行**：支持多轮工具调用循环，最大循环次数可配置
- **错误处理**：完善的错误处理和回退机制
- **流式支持**：支持流式和非流式两种模式

### 工具调用格式
LLM必须严格按照以下格式输出工具调用：

```
<<<[HANDOFF]>>>
tool_name: 「始」服务名称「末」
param1: 「始」参数值1「末」
param2: 「始」参数值2「末」
<<<[END_HANDOFF]>>>
```

### 执行流程
1. **接收用户消息**
2. **调用LLM API**
3. **解析HANDOFF格式工具调用**
4. **执行工具调用（通过MCP服务）**
5. **将结果返回给LLM**
6. **重复步骤2-5直到无工具调用或达到最大循环次数**

### 配置参数
```python
# config.py中的工具调用循环配置
MAX_handoff_LOOP_STREAM = 5      # 流式模式最大工具调用循环次数
MAX_handoff_LOOP_NON_STREAM = 5  # 非流式模式最大工具调用循环次数
SHOW_handoff_OUTPUT = False      # 是否显示工具调用输出
```

### 错误处理
- 工具调用失败时会记录错误信息并继续执行
- 达到最大循环次数时会停止
- 支持回退到原始处理方式

### 扩展开发
如需添加新的工具调用处理逻辑，可以：
1. 在`mcpserver/`目录下添加新的Agent
2. 在`mcpserver/mcp_registry.py`中注册新Agent
3. 更新API接口以支持新的功能

---

## 🌐 RESTful API 服务

NagaAgent内置完整的RESTful API服务器，启动时自动开启，支持所有对话功能：

### API接口说明

- **基础地址**: `http://127.0.0.1:8000` (可在config.py中配置)
- **交互式文档**: `http://127.0.0.1:8000/docs`
- **OpenAPI规范**: `http://127.0.0.1:8000/openapi.json`

### 主要接口

#### 健康检查
```bash
GET /health
```

#### 对话接口
```bash
# 普通对话
POST /chat
{
  "message": "你好，娜迦",
  "session_id": "optional-session-id"
}

# 流式对话 (Server-Sent Events)
POST /chat/stream
{
  "message": "请介绍一下人工智能的发展历程"
}
```

#### 系统管理接口
```bash
# 获取系统信息
GET /system/info

# 切换开发者模式
POST /system/devmode

# 获取记忆统计
GET /memory/stats
``` 

## MCP服务Agent化升级说明

- 所有MCP服务（如文件、代码、浏览器、应用启动、系统控制、天气等）已全部升级为标准Agent风格：
  - 统一继承自`agents.Agent`，具备`name`、`instructions`属性和`handle_handoff`异步方法
  - 变量全部走`config.py`统一管理，避免重复定义
  - 注释全部中文，文件/类/函数注释一行，变量注释右侧#
  - 支持多agent协作，ControllerAgent可智能分配任务给BrowserAgent、ContentAgent等
  - 注册中心`mcp_registry.py`自动发现并注册所有实现了`handle_handoff`的Agent实例，支持热插拔
  - 注册时自动输出所有已注册agent的名称和说明，便于调试
  - 简化Agent类型：只支持`mcp`和`agent`两种类型

- handoff机制全部通过`handle_handoff`异步方法调度，兼容HANDOFF和handoff两种格式

- 新增/删除agent只需增删py文件，无需重启主程序

- 详细接口和参数请参考各Agent代码注释与`config.py`配置 

## 更新日志

- 工具调用格式已优化，改为纯JSON格式，更加简洁规范，具体示例如下：

```
{
  "agentType": "mcp",
  "service_name": "MCP服务名称",
  "tool_name": "工具名称",
  "参数名": "参数值"
}
```

如需调用Agent服务，格式如下：

```
{
  "agentType": "agent",
  "agent_name": "Agent名称",
  "prompt": "任务内容"
}
``` 
