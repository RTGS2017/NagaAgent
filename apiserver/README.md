# NagaAgent API服务器

基于博弈论的智能API服务器，提供多智能体协作、任务调度、电脑控制等高级功能。

## 🚀 功能特性

### 核心功能
- **智能对话**: 支持普通对话和流式对话
- **多智能体协作**: 基于博弈论的多智能体协调机制
- **任务调度**: 异步任务调度和并行执行
- **电脑控制**: 智能电脑操作和自动化
- **MCP服务集成**: 支持多种MCP服务的调用
- **记忆系统**: 集成记忆管理功能

### 基于博弈论的高级功能 ✨
- **后台意图分析**: 异步分析对话意图，提取潜在任务
- **任务去重**: LLM智能判断任务重复性
- **并行执行**: 多进程并行任务处理
- **电脑控制调度**: 串行化电脑操作任务
- **结果通知**: 任务完成后的智能通知机制
- **能力管理**: 动态检查和刷新系统能力

### 工具调用循环
- **自动解析**: 自动解析LLM返回的`<<<[HANDOFF]>>>`格式工具调用
- **递归执行**: 支持多轮工具调用循环，最大循环次数可配置
- **错误处理**: 完善的错误处理和回退机制
- **流式支持**: 支持流式和非流式两种模式

### 流式工具调用提取 ✨
- **实时检测**: 实时检测AI输出中的工具调用，支持中英文括号
- **智能分离**: 自动分离普通文本和工具调用，不阻塞前端显示
- **异步执行**: 工具调用异步执行，不影响文本流式输出
- **嵌套支持**: 支持嵌套括号的复杂工具调用格式
- **错误恢复**: 工具调用失败时自动恢复文本输出

## 📋 API接口

### 基础接口

#### GET `/`
- **描述**: API根路径
- **返回**: 服务器基本信息

#### GET `/health`
- **描述**: 健康检查
- **返回**: 服务器状态信息

#### GET `/system/info`
- **描述**: 获取系统信息
- **返回**: 版本、状态、可用服务等

### 任务管理接口 ✨ 新功能

#### GET `/tasks/{task_id}`
- **描述**: 获取任务状态
- **返回**: 任务详细信息

#### GET `/tasks`
- **描述**: 获取任务列表
- **返回**: 所有任务的状态列表

### 电脑控制接口 ✨ 新功能

#### GET `/computer-use/status`
- **描述**: 获取电脑控制状态
- **返回**: 当前电脑控制任务状态

#### POST `/computer-use/schedule`
- **描述**: 调度电脑控制任务
- **请求体**:
  ```json
  {
    "task_id": "任务ID",
    "instruction": "操作指令",
    "screenshot": "base64截图（可选）",
    "session_id": "会话ID（可选）"
  }
  ```

### 能力管理接口 ✨ 新功能

#### GET `/capabilities`
- **描述**: 获取系统能力列表
- **返回**: MCP和电脑控制能力状态

#### GET `/mcp/availability`
- **描述**: 获取MCP可用性
- **返回**: MCP服务可用性状态

#### GET `/computer-use/availability`
- **描述**: 获取电脑控制可用性
- **返回**: 电脑控制功能可用性状态

#### POST `/agent/flags`
- **描述**: 设置代理标志
- **请求体**:
  ```json
  {
    "mcp_enabled": true,
    "computer_use_enabled": true
  }
  ```

#### GET `/agent/flags`
- **描述**: 获取代理标志
- **返回**: 当前代理配置状态

### 对话接口

#### POST `/chat`
- **描述**: 普通对话接口
- **请求体**:
  ```json
  {
    "message": "用户消息",
    "stream": false,
    "session_id": "会话ID（可选）"
  }
  ```
- **返回**:
  ```json
  {
    "response": "AI回复",
    "session_id": "会话ID",
    "status": "success"
  }
  ```

#### POST `/chat/stream`
- **描述**: 流式对话接口 - 支持流式工具调用提取
- **请求体**: 同普通对话
- **返回**: Server-Sent Events格式的流式响应
- **特殊标记**:
  - `[SENTENCE]`: 完整句子标记
  - `[TOOL_CALL]`: 工具调用开始标记
  - `[TOOL_RESULT]`: 工具执行结果标记
  - `[TOOL_ERROR]`: 工具执行错误标记

### MCP服务接口

#### POST `/mcp/handoff`
- **描述**: MCP服务调用
- **请求体**:
  ```json
  {
    "service_name": "服务名称",
    "task": {
      "action": "操作",
      "params": {}
    },
    "session_id": "会话ID（可选）"
  }
  ```

#### GET `/mcp/services`
- **描述**: 获取可用MCP服务列表

### 系统管理接口

#### POST `/system/devmode`
- **描述**: 切换开发者模式

#### GET `/memory/stats`
- **描述**: 获取记忆系统统计信息

## ⚙️ 配置

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `API_SERVER_HOST` | `127.0.0.1` | API服务器主机地址 |
| `API_SERVER_PORT` | `8000` | API服务器端口 |
| `API_SERVER_RELOAD` | `False` | 是否开启自动重载 |
| `MaxhandoffLoopStream` | `5` | 流式模式最大工具调用循环次数 |
| `MaxhandoffLoopNonStream` | `5` | 非流式模式最大工具调用循环次数 |
| `Showhandoff` | `False` | 是否显示工具调用输出 |

### 工具调用格式

LLM返回的工具调用应使用以下格式：

```
<<<[HANDOFF]>>>
tool_name: 「始」服务名称「末」
param1: 「始」参数值1「末」
param2: 「始」参数值2「末」
<<<[END_HANDOFF]>>>
```

## 🚀 启动方式

### 方式1: 直接启动
```bash
python apiserver/start_server.py
```

### 方式2: 使用uvicorn
```bash
uvicorn apiserver.api_server:app --host 127.0.0.1 --port 8000 --reload
```

### 方式3: 环境变量配置
```bash
export API_SERVER_HOST=0.0.0.0
export API_SERVER_PORT=8080
export API_SERVER_RELOAD=True
python apiserver/start_server.py
```

## 📖 使用示例

### Python客户端示例

```python
import requests
import json

# 普通对话
response = requests.post("http://127.0.0.1:8000/chat", json={
    "message": "你好，请帮我查询今天的天气",
    "stream": False
})
print(response.json())

# 流式对话
response = requests.post("http://127.0.0.1:8000/chat/stream", json={
    "message": "请帮我分析这张图片",
    "stream": True
}, stream=True)

for line in response.iter_lines():
    if line:
        data = line.decode('utf-8')
        if data.startswith('data: '):
            try:
                json_data = json.loads(data[6:])
                print(json_data)
            except:
                pass
```

### MCP服务调用示例

```python
import requests

# 调用天气服务
response = requests.post("http://127.0.0.1:8000/mcp/handoff", json={
    "service_name": "WeatherAgent",
    "task": {
        "action": "get_weather",
        "params": {
            "city": "北京"
        }
    }
})
print(response.json())
```

## 🏗️ 架构说明

### 核心模块

- **`api_server.py`**: 主API服务器，提供所有RESTful接口
- **`message_manager.py`**: 消息管理器，统一管理会话和消息
- **`prompt_logger.py`**: 提示日志记录器，记录对话历史
- **`streaming_tool_extractor.py`**: 流式工具调用提取器
- **`tool_call_utils.py`**: 工具调用工具函数

### 任务管理模块（已迁移到agentserver）

- **`agentserver/task_scheduler.py`**: 任务调度器，基于博弈论的任务调度机制
- **`agentserver/background_analyzer.py`**: 后台意图分析器，异步分析对话意图
- **`agentserver/parallel_executor.py`**: 并行执行器，多进程任务处理
- **`agentserver/task_deduper.py`**: 任务去重器，LLM智能判断任务重复性
- **`agentserver/computer_use_scheduler.py`**: 电脑控制调度器，串行化电脑操作
- **`agentserver/result_notifier.py`**: 结果通知器，任务完成后的通知机制
- **`agentserver/capability_manager.py`**: 能力管理器，动态检查系统能力

### 辅助模块

- **`start_server.py`**: 服务器启动脚本

### 静态资源

- **`static/`**: 静态文件目录
  - `document_upload.html`: 文档上传页面

### 基于博弈论的工作流程

1. **对话接收**: 用户发送消息到API服务器
2. **后台分析**: 异步触发意图分析，提取潜在任务
3. **任务去重**: 智能判断是否与现有任务重复
4. **任务调度**: 根据任务类型选择合适的执行策略
5. **并行执行**: 多进程并行处理任务
6. **结果通知**: 任务完成后通知主服务器
7. **能力管理**: 动态检查和刷新系统能力

### 工具调用循环流程

1. **接收用户消息**
2. **调用LLM API**
3. **解析工具调用**
4. **执行工具调用**
5. **将结果返回给LLM**
6. **重复步骤2-5直到无工具调用或达到最大循环次数**

### 流式工具调用提取流程 ✨

1. **接收AI流式输出**
2. **实时字符级检测**
   - 检测 `{` 或 `｛` 开始工具调用
   - 检测 `}` 或 `｝` 结束工具调用
   - 支持嵌套括号计数
3. **智能分离处理**
   - 普通文本：直接发送到前端显示
   - 工具调用：异步执行，不阻塞文本流
4. **结果整合**
   - 工具执行结果返回给LLM继续处理
   - 错误处理：工具失败时继续文本输出

### 错误处理

- 工具调用失败时会记录错误信息
- 达到最大循环次数时会停止
- 支持回退到原始处理方式
- 任务执行失败时自动重试机制

### 扩展开发

如需添加新的功能模块，可以：

1. **添加新的调度器**: 在`task_scheduler.py`中注册新的调度策略
2. **扩展能力管理**: 在`capability_manager.py`中添加新的能力检查
3. **自定义执行器**: 在`parallel_executor.py`中添加新的执行逻辑
4. **新增API接口**: 在`api_server.py`中添加新的RESTful接口

## 📝 注意事项

1. **系统要求**: 确保MCP服务已正确配置和启动
2. **任务调度**: 工具调用循环次数不宜设置过大，避免无限循环
3. **流式处理**: 流式模式下工具调用循环会暂时关闭流式输出
4. **记忆系统**: 开发者模式下不会保存对话日志到GRAG记忆系统
5. **电脑控制**: 电脑控制任务会串行执行，确保操作安全
6. **任务去重**: 系统会自动判断任务重复性，避免重复执行
7. **异步处理**: 后台意图分析不会阻塞主对话流程

## 🔧 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `API_SERVER_HOST` | `127.0.0.1` | API服务器主机地址 |
| `API_SERVER_PORT` | `8000` | API服务器端口 |
| `API_SERVER_RELOAD` | `False` | 是否开启自动重载 |
| `MaxhandoffLoopStream` | `5` | 流式模式最大工具调用循环次数 |
| `MaxhandoffLoopNonStream` | `5` | 非流式模式最大工具调用循环次数 |
| `Showhandoff` | `False` | 是否显示工具调用输出 |

### 基于博弈论的配置

- **任务去重阈值**: 可配置LLM判断任务重复的相似度阈值
- **并行执行数量**: 可配置同时执行的最大任务数量
- **电脑控制超时**: 可配置电脑控制任务的超时时间
- **结果通知延迟**: 可配置任务完成后的通知延迟时间

## 代理问题

如果你使用了代理服务器，测试本地API时需要绕过代理：
```bash
NO_PROXY="127.0.0.1,localhost" curl -X GET "http://127.0.0.1:8000/health"
``` 