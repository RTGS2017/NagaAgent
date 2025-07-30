# NagaAgent API服务器

NagaAgent的RESTful API服务器，提供智能对话、MCP服务调用等功能，并兼容OpenAI API规范。

## 🚀 功能特性

### 核心功能
- **智能对话**: 支持普通对话和流式对话
- **工具调用循环**: 自动解析和执行LLM返回的工具调用
- **MCP服务集成**: 支持多种MCP服务的调用
- **记忆系统**: 集成记忆管理功能
- **开发者模式**: 支持开发者模式切换
- **OpenAI兼容**: 兼容OpenAI Chat Completions API规范

### 工具调用循环
- **自动解析**: 自动解析LLM返回的`<<<[HANDOFF]>>>`格式工具调用
- **递归执行**: 支持多轮工具调用循环，最大循环次数可配置
- **错误处理**: 完善的错误处理和回退机制
- **流式支持**: 支持流式和非流式两种模式

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
- **描述**: 流式对话接口
- **请求体**: 同普通对话
- **返回**: Server-Sent Events格式的流式响应

### OpenAI兼容接口

#### GET `/v1/models`
- **描述**: 获取可用模型列表（OpenAI兼容）
- **返回**: OpenAI格式的模型列表

#### POST `/v1/chat/completions`
- **描述**: 聊天完成接口（OpenAI兼容）
- **请求体**: OpenAI Chat Completions格式
- **返回**: OpenAI格式的响应或流式响应

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

### API密钥认证

API服务器支持API密钥认证，密钥配置有以下优先级：

1. 首先使用`api_server.api_key`字段（API服务器专用密钥）
2. 如果未设置，则使用`api.api_key`字段（主API密钥）
3. 如果都未设置或设置为`sk-placeholder-key-not-set`，则跳过API密钥验证

当配置了API密钥时，所有OpenAI兼容的API端点都需要在请求头中包含：
```
Authorization: Bearer YOUR_API_KEY
```

或者在查询参数中包含：
```
?api_key=YOUR_API_KEY
```

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
.venv\Scripts\activate
python apiserver/start_server.py
```

### 方式2: 使用uvicorn
```bash
.venv\Scripts\activate
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

### OpenAI兼容API使用示例

```python
import openai

# 配置客户端
client = openai.OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="sk-not-required"
)

# 聊天完成
response = client.chat.completions.create(
    model="naga-agent",
    messages=[
        {"role": "user", "content": "你好，介绍一下你自己"}
    ],
    stream=False
)

print(response.choices[0].message.content)

# 流式聊天完成
stream = client.chat.completions.create(
    model="naga-agent",
    messages=[
        {"role": "user", "content": "写一首关于春天的诗"}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
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

## 🔧 开发说明

### 工具调用循环流程

1. **接收用户消息**
2. **调用LLM API**
3. **解析工具调用**
4. **执行工具调用**
5. **将结果返回给LLM**
6. **重复步骤2-5直到无工具调用或达到最大循环次数**

### 错误处理

- 工具调用失败时会记录错误信息
- 达到最大循环次数时会停止
- 支持回退到原始处理方式

### 扩展开发

如需添加新的工具调用处理逻辑，可以：

1. 修改`ToolCallProcessor`类
2. 在`conversation_core.py`中添加新的处理逻辑
3. 更新API接口以支持新的功能

## 📝 注意事项

1. 确保MCP服务已正确配置和启动
2. 工具调用循环次数不宜设置过大，避免无限循环
3. 流式模式下工具调用循环会暂时关闭流式输出
4. 开发者模式下不会保存对话日志到GRAG记忆系统

## 代理问题

如果你使用了代理服务器，测试本地API时需要绕过代理：
```bash
NO_PROXY="127.0.0.1,localhost" curl -X GET "http://127.0.0.1:8000/health"
```