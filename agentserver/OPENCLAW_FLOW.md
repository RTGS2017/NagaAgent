# OpenClaw 调度流程说明

当前 Agent Server 的 OpenClaw 相关流程**不经过** AgentManager，仅使用以下组件。

## 启动时初始化（lifespan）

1. **Modules.analyzer** = `get_background_analyzer()` — 意图/博弈论分析器  
2. **Modules.task_scheduler** = `get_task_scheduler()` — 任务与步骤记忆调度  
3. **Modules.openclaw_client** = `get_openclaw_client(...)` — OpenClaw Gateway 客户端（从 `~/.openclaw` 或 config 读取）

## 流程一：统一调度（/schedule）

调用方（如 API 或 MCP）已做好意图分析，直接下发 `agent_calls` 时使用。

```
POST /schedule
  body: { query, agent_calls[], session_id?, analysis_session_id?, request_id?, callback_url? }
  ↓
1. 校验 openclaw_client、task_scheduler 就绪
2. 若 agent_calls 为空 → 返回 no_tasks
3. task_scheduler.create_task(request_id, purpose, session_id, analysis_session_id)
4. asyncio.create_task(_execute_agent_tasks_async(...))  # 异步执行，不阻塞
5. 立即返回 { success, status: "scheduled", task_id, ... }
  ↓
_execute_agent_tasks_async:
  对每个 agent_call:
    - task_scheduler.add_task_step(step_id, task_id, purpose, content, ...)
    - result = await _process_openclaw_task(instruction, session_id)
    - task_scheduler.add_task_step(..., result)
  若有 callback_url → _send_callback_notification(...)
```

**核心执行**：`_process_openclaw_task(instruction, session_id)`  
→ `Modules.openclaw_client.send_message(instruction, session_id)`，等待 OpenClaw 执行并返回结果。

## 流程二：直接发送 OpenClaw（/openclaw/send）

博弈论分析器产生 OpenClaw 任务后，直接发到 Agent Server 的发送接口（不经过 /schedule）。

```
background_analyzer（或其它调用方）
  ↓
POST http://localhost:{agent_server_port}/openclaw/send
  body: { message, session_key?, name?, wake_mode?, timeout_seconds? }
  ↓
agent_server.openclaw_send_message
  → Modules.openclaw_client.send_message(...)
  → 返回 { task, replies, ... }
```

## 流程三：兼容入口（/analyze_and_execute）

旧版“意图分析+执行”的兼容接口，从 messages 里提取「执行Agent任务: xxx」后逐个执行。

```
POST /analyze_and_execute
  body: { messages: [{role, content}], session_id? }
  ↓
从 messages 中提取 content 含 "执行Agent任务:" 的 instruction
  ↓
对每个 task: result = await _process_openclaw_task(instruction, session_id)
  ↓
返回 { success, status: "completed", tasks_processed, results }
```

## 组件职责小结

| 组件 | 用途 |
|------|------|
| **analyzer** (background_analyzer) | 意图/博弈论分析，产生 agent_calls 或直接调 /openclaw/send |
| **task_scheduler** | 仅被 /schedule 使用：创建任务、记录步骤、压缩记忆、会话关联 |
| **openclaw_client** | 所有“执行 OpenClaw 任务”的统一出口：send_message、健康检查、安装/配置等 |

**已废弃、不再使用**：`agent_manager`（AgentManager）。任务规划与执行已由 `task_scheduler` + `openclaw_client` 直接完成。
