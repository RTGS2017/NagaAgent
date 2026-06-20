---
name: naga-config
description: Naga 自身配置管理技能。用于查看和修改 Naga 系统设置、添加 MCP 工具服务、导入自定义技能、搜索可用 MCP 工具。当用户要求修改设置、添加工具或技能时使用此技能。
version: 1.0.0
author: Naga Team
tags:
  - config
  - settings
  - mcp
  - skill
  - self-management
enabled: true
---

# Naga 自身配置管理技能

本技能让你能够管理和配置 Naga 系统本身，包括修改系统设置、添加 MCP 工具服务、导入自定义技能。

## 1. 查看和修改系统配置

### 读取当前配置
```
GET /system/config
```
返回完整的系统配置 JSON，包含以下主要分区：
- `system` — 基础设置（ai_name, voice_enabled, stream_mode, debug, log_level）
- `api` — LLM 模型设置（api_key, base_url, model, temperature, max_tokens, max_history_rounds）
- `grag` — 知识图谱设置（enabled, auto_extract, similarity_threshold, neo4j 连接）
- `tts` — 语音合成设置（default_voice, default_speed, default_language）
- `online_search` — 搜索引擎设置（searxng_url, engines, num_results）
- `live2d` — Live2D 虚拟形象设置（enabled, model_path, animation_enabled）
- `handoff` — 工具调用循环设置（max_loop_stream, max_loop_non_stream）
- `voice_realtime` — 实时语音对话设置（enabled, provider, model, voice）
- `weather` — 天气 API 设置
- `mqtt` — MQTT 物联网设置
- `crawl4ai` — 网页爬取设置
- `computer_control` — 计算机视觉控制设置

### 修改配置
```
POST /system/config
Content-Type: application/json

{完整的配置 JSON 对象}
```

**重要**：修改配置时需要发送完整的配置对象。建议先 GET 获取当前配置，修改需要的字段后再 POST 回去。

### 常见配置操作示例

**切换 LLM 模型**：修改 `api.model`、`api.base_url`、`api.api_key`
**调整创造力**：修改 `api.temperature`（0.0=精确，1.0=创意，2.0=随机）
**修改 AI 名称**：修改 `system.ai_name`
**开关语音**：修改 `system.voice_enabled`
**开关知识图谱**：修改 `grag.enabled` 和 `grag.auto_extract`
**调整搜索结果数**：修改 `online_search.num_results`

## 2. 查看已有 MCP 工具服务

```
GET /mcp/services
```
返回所有 MCP 服务列表，包括：
- `name` — 服务名称
- `displayName` — 显示名称
- `description` — 描述
- `source` — 来源（`builtin` 内置 / `mcporter` 外部配置）
- `available` — 是否可用

## 3. 添加 MCP 工具服务

MCP 服务通过 JSON 配置添加，配置会写入 `~/.mcporter/config.json`。

```
POST /mcp/import
Content-Type: application/json

{
  "name": "服务名称",
  "config": {
    "command": "npx",
    "args": ["-y", "@mcp/server-name"],
    "type": "stdio"
  }
}
```

### MCP 配置格式

**stdio 类型**（通过 Node.js 命令启动）：
```json
{
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-xxx"],
  "type": "stdio"
}
```

**SSE/URL 类型**（通过 HTTP 连接）：
```json
{
  "url": "https://mcp-server.example.com/sse",
  "type": "sse"
}
```

### 搜索可用的 MCP 工具

当用户需要某个功能但目前没有对应的 MCP 工具时，使用内置的网络搜索工具（online_search）搜索：
- 搜索关键词：`MCP server <功能描述> npm` 或 `Model Context Protocol <功能> server`
- 常见 MCP 服务注册在 npm 的 `@modelcontextprotocol/` 组织下
- 也可以在 GitHub 搜索：`modelcontextprotocol site:github.com`
- 找到后，用 `POST /mcp/import` 添加对应的 JSON 配置

## 4. 查看技能仓库

```
GET /openclaw/market/items
```
返回所有可安装的技能列表。

### 安装技能市场中的技能
```
POST /openclaw/market/items/{item_id}/install
```

## 5. 导入自定义技能

```
POST /skills/import
Content-Type: application/json

{
  "name": "技能名称",
  "content": "技能描述和指令内容（Markdown 格式）"
}
```

技能文件会被创建为 `skills/{name}/SKILL.md`，包含 YAML frontmatter 元数据和 Markdown 内容。技能会在下次对话时自动加载到系统提示词中。

`name` 是单段技能目录标识，不能是空值、`.`、`..`，也不能包含 `/`、`\`、绝对路径、Windows 盘符路径或控制字符。

### 自定义技能内容建议格式
```markdown
# 技能标题

简要描述这个技能做什么。

## 触发条件
描述何时应使用此技能。

## 执行步骤
1. 第一步
2. 第二步

## 输出格式
描述期望的输出格式。
```

## 6. 查看和修改系统提示词

### 获取当前系统提示词
```
GET /system/prompt
```

### 设置系统提示词
```
POST /system/prompt
Content-Type: application/json

{
  "content": "新的系统提示词内容"
}
```

## 注意事项

- 网络搜索、网址访问和文件访问功能使用 Naga 内置的 clawdbot 工具，不需要额外的 MCP 服务
- 修改配置后会立即生效，无需重启
- 添加 MCP 服务后，需要在服务列表中确认其状态为可用
- 敏感信息（如 API 密钥）在回复用户时应适当掩码处理
