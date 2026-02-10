# NagaAgent Server

基于博弈论架构的独立意图分析和任务调度服务。

## 架构特点

### 微服务架构
- **独立服务**：意图分析作为独立的HTTP服务运行
- **异步处理**：Fire-and-forget模式，不阻塞主流程
- **任务调度**：分析结果直接转化为可执行任务

### 核心组件

当前调度仅使用以下三者，**不再使用** AgentManager / Task Planner。

- **Agent Server** (`agent_server.py`)：FastAPI，提供 `/schedule`、`/openclaw/*` 等接口，管理 analyzer / task_scheduler / openclaw_client。
- **Task Scheduler** (`task_scheduler.py`)：任务与步骤记忆、会话关联、压缩记忆；仅被 `/schedule` 使用。
- **OpenClaw** (`openclaw/`)：与 OpenClaw Gateway 通信，所有“执行电脑任务”通过 `openclaw_client.send_message()` 完成。

**OpenClaw 调度流程**详见 [OPENCLAW_FLOW.md](./OPENCLAW_FLOW.md)。

Task Scheduler 使用示例：

```python
from agentserver.task_scheduler import get_task_scheduler, TaskStep

task_scheduler = get_task_scheduler()
task_id = await task_scheduler.create_task(task_id="...", purpose="...", session_id="...")
await task_scheduler.add_task_step(task_id, TaskStep(step_id="...", task_id=task_id, purpose="...", content="...", output=""))
```

## API接口

### 意图识别与电脑控制执行
```http
POST /analyze_and_execute
Content-Type: application/json

{
    "messages": [
        {"role": "user", "content": "帮我打开浏览器并搜索Python教程"}
    ],
    "session_id": "main_session"
}
```

### 任务管理
```http
GET /tasks?session_id=main_session
GET /tasks/{task_id}
POST /tasks/{task_id}/cancel
```

### 健康检查
```http
GET /health
```

## 启动方式

### 统一启动（推荐）
Agent Server已集成到主流程中，通过`main.py`统一启动：

```bash
python main.py
```

这将同时启动：
- 主对话流程
- Agent Server (端口8001)
- API服务器 (端口8000)
- 语音输出服务
- 其他后台服务

### 独立启动（开发调试）
如果需要独立启动Agent Server进行调试：

```bash
uvicorn agentserver.agent_server:app --host 0.0.0.0 --port 8001
```

## 配置说明

在 `agentserver/config.py` 中可以配置：
- 服务端口和主机
- 任务超时时间
- 意图分析开关
- 日志级别等

## 与主流程集成

主对话流程通过HTTP客户端调用Agent Server：

```python
# 在apiserver/api_server.py中
async def _call_agent_server_analyze(self, messages, session_id):
    url = "http://localhost:8001/analyze_and_plan"
    payload = {"messages": messages, "session_id": session_id}
    # 发送请求...
```

## 优势对比

### 相比原集成架构的优势：
1. **解耦性**：意图分析独立运行，不影响主对话流程
2. **可扩展性**：支持分布式部署和负载均衡
3. **任务驱动**：分析结果直接转化为可执行任务
4. **容错性**：服务故障不影响主流程

### 适用场景：
- 需要大规模任务自动化的场景
- 多用户并发处理
- 分布式部署需求
- 任务执行监控和管理

## 注意事项

1. **服务依赖**：需要确保Agent Server在端口8001运行
2. **网络延迟**：HTTP调用会增加少量延迟
3. **错误处理**：需要处理网络异常和服务不可用情况
4. **资源管理**：需要合理配置任务并发数和超时时间

## 更新记录

- 移除已废弃的 `agent_manager.py`（任务规划与执行由 task_scheduler + openclaw 直接完成）。详见 [OPENCLAW_FLOW.md](./OPENCLAW_FLOW.md)。