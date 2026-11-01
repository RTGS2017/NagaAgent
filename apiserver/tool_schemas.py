#!/usr/bin/env python3
"""
工具 Schema 生成模块
将 MCP manifests + OpenClaw 工具表 + Live2D + naga_control 转换为 OpenAI function calling 格式。

命名约定：{agentType}__{service_name}__{tool_name}
  - tool__web_search
  - mcp__weather_time__today_weather
  - openclaw__agent
  - live2d__action
  - naga_control__command

OpenAI 要求 tools[*].function.name 匹配 ^[a-zA-Z0-9_-]+$。MCP 的 service_name/command
可能含中文、空格等非法字符，故生成时经 _make_mcp_func_name() 做 sanitize（非法字符替换为
下划线并追加短哈希），并登记到 _mcp_name_map 供解析端无损还原。
"""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

_schema_cache: Dict[str, List[Dict[str, Any]]] = {}

# function name -> (service_name, command) 反查映射
# 用于在 sanitize 之后仍能把 OpenAI function name 还原回原始 MCP 服务名/命令。
# 刻意不随 schema 缓存一起清空：func_name 由原始值确定性派生（同输入恒等同输出），
# 此表是 _make_mcp_func_name 的纯函数缓存，只增不清。否则 MCP 注册变更若发生在
# 「LLM 已拿到工具列表」与「解析其 tool_call」之间，映射会被清空导致解析错误回退到 split。
_mcp_name_map: Dict[str, Tuple[str, str]] = {}


def invalidate_schema_cache():
    """MCP 注册变更时调用，清除缓存"""
    _schema_cache.clear()


# ---------------------------------------------------------------------------
# function name 规范化
# OpenAI 要求 tools[*].function.name 匹配 ^[a-zA-Z0-9_-]+$，
# 而 MCP 的 service_name / command 可能含中文、空格等非法字符。
# ---------------------------------------------------------------------------

_INVALID_FUNC_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_func_name_part(part: str) -> str:
    """将名称片段中不符合 ^[a-zA-Z0-9_-]+$ 的字符替换为下划线"""
    return _INVALID_FUNC_NAME_CHARS.sub("_", part)


def _make_mcp_func_name(service_name: str, command: str) -> str:
    """生成符合 OpenAI 正则的 MCP function name，并登记反查映射。

    - 纯 ASCII 安全名保持原样（向后兼容已有命名约定）；
    - 含非法字符时，先逐字符替换为下划线，再追加基于原始值的短哈希，
      以保证唯一、确定且可通过 _mcp_name_map 无损还原。
    """
    safe_service = _sanitize_func_name_part(service_name)
    safe_command = _sanitize_func_name_part(command)
    func_name = f"mcp__{safe_service}__{safe_command}"
    if safe_service != service_name or safe_command != command:
        # 用 NUL 作为分隔符，避免 service/command 边界歧义
        digest = hashlib.md5(f"{service_name}\x00{command}".encode("utf-8")).hexdigest()[:6]
        func_name = f"{func_name}_{digest}"
    _mcp_name_map[func_name] = (service_name, command)
    return func_name


def resolve_mcp_func_name(func_name: str) -> Optional[Tuple[str, str]]:
    """根据 function name 还原 (service_name, command)，未登记返回 None"""
    return _mcp_name_map.get(func_name)


def get_all_tool_schemas(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """返回所有可用工具的 OpenAI function calling schemas"""
    cache_key = agent_id or "__public__"
    cached = _schema_cache.get(cache_key)
    if cached is not None:
        return cached

    schemas: List[Dict[str, Any]] = []
    schemas.extend(_build_openclaw_tool_schemas())
    schemas.extend(_build_openclaw_agent_schema())
    schemas.extend(_build_mcp_schemas(agent_id=agent_id))
    schemas.extend(_build_live2d_schema())
    schemas.extend(_build_naga_control_schema())

    _schema_cache[cache_key] = schemas
    logger.info(f"[ToolSchemas] 生成 {len(schemas)} 个工具 schema")
    return schemas


# ---------------------------------------------------------------------------
# OpenClaw 直接工具（~30 个，从 agentic_tool_prompt.txt 的参数表硬编码）
# ---------------------------------------------------------------------------

_OPENCLAW_TOOLS = [
    {
        "name": "web_search",
        "description": "联网搜索。搜索实时信息、新闻、价格、天气等。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "count": {"type": "integer", "description": "结果数量(1-10)", "default": 10},
                "freshness": {"type": "string", "description": "时效过滤: pd(24h)/pw(周)/pm(月)/py(年)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "获取网页内容。抓取指定URL的页面内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标URL"},
                "extractMode": {"type": "string", "description": "提取模式: markdown/text"},
                "maxChars": {"type": "integer", "description": "最大字符数"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser",
        "description": "浏览器自动化操作。启动、导航、截图、交互等。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: status/start/stop/open/snapshot/screenshot/navigate/act等"},
                "targetUrl": {"type": "string", "description": "目标URL"},
                "ref": {"type": "string", "description": "元素引用"},
                "selector": {"type": "string", "description": "CSS选择器"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "exec",
        "description": "执行shell命令。运行系统命令并返回输出。",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的命令"},
                "workdir": {"type": "string", "description": "工作目录"},
                "timeout": {"type": "integer", "description": "超时秒数"},
                "background": {"type": "boolean", "description": "是否后台运行"},
                "pty": {"type": "boolean", "description": "是否使用伪终端"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "process",
        "description": "管理exec进程。查看、轮询、终止进程。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: list/poll/log/write/kill等"},
                "sessionId": {"type": "string", "description": "会话ID"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "read",
        "description": "读取文件内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write",
        "description": "写入文件内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit",
        "description": "编辑文件（查找替换）。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "文件路径"},
                "old_string": {"type": "string", "description": "要替换的文本"},
                "new_string": {"type": "string", "description": "替换后的文本"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "grep",
        "description": "搜索文件内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "搜索模式"},
                "path": {"type": "string", "description": "搜索路径"},
                "include": {"type": "string", "description": "文件类型过滤"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "find",
        "description": "查找文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "文件名模式"},
                "path": {"type": "string", "description": "搜索路径"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "ls",
        "description": "列出目录内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目录路径"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "image",
        "description": "分析图片内容。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "图片路径或URL"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "memory_search",
        "description": "语义搜索记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "maxResults": {"type": "integer", "description": "最大结果数"},
                "minScore": {"type": "number", "description": "最低相关度分数"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_get",
        "description": "读取记忆片段。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "记忆路径"},
                "from": {"type": "integer", "description": "起始行号"},
                "lines": {"type": "integer", "description": "行数"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "cron",
        "description": "定时任务管理。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: status/list/add/update/remove/run/wake等"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "message",
        "description": "发消息到渠道。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "消息内容"},
                "channel": {"type": "string", "description": "目标渠道"},
                "target": {"type": "string", "description": "目标用户"},
                "media": {"type": "string", "description": "媒体附件"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "tts",
        "description": "文字转语音。",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要转换的文本"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "sessions_spawn",
        "description": "启动子Agent会话。",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "任务描述"},
                "label": {"type": "string", "description": "会话标签"},
                "model": {"type": "string", "description": "使用的模型"},
                "agentId": {"type": "string", "description": "Agent ID"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "sessions_list",
        "description": "列出所有会话。",
        "parameters": {
            "type": "object",
            "properties": {
                "kinds": {"type": "string", "description": "会话类型过滤"},
                "limit": {"type": "integer", "description": "数量限制"},
                "messageLimit": {"type": "integer", "description": "消息数量限制"},
            },
        },
    },
    {
        "name": "sessions_history",
        "description": "获取会话历史。",
        "parameters": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string", "description": "会话Key"},
                "limit": {"type": "integer", "description": "数量限制"},
            },
            "required": ["sessionKey"],
        },
    },
    {
        "name": "sessions_send",
        "description": "向会话发送消息。",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "消息内容"},
                "sessionKey": {"type": "string", "description": "会话Key"},
                "label": {"type": "string", "description": "标签"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "session_status",
        "description": "获取会话状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "sessionKey": {"type": "string", "description": "会话Key"},
            },
        },
    },
    {
        "name": "agents_list",
        "description": "列出当前通讯录中可联系的现有干员。在跨干员委派、多人分工或用户点名某个干员之前优先调用。",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "agent_relay",
        "description": "把消息转发给另一名现有干员并等待其回复。用于多干员协作，不要把它和临时 OpenClaw 执行器混用。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string", "description": "目标干员 ID"},
                "target_agent_name": {"type": "string", "description": "目标干员名称，可替代 ID"},
                "message": {"type": "string", "description": "要转发给目标干员的消息"},
                "purpose": {"type": "string", "description": "转发目的或期望产出"},
                "context": {"type": "string", "description": "补充上下文"},
                "timeout_seconds": {"type": "integer", "description": "等待秒数，默认 120"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "canvas",
        "description": "节点画布控制。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: present/hide/navigate/eval/snapshot等"},
                "node": {"type": "string", "description": "节点标识"},
            },
            "required": ["action", "node"],
        },
    },
    {
        "name": "nodes",
        "description": "节点发现与控制。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: status/describe/notify/camera_snap/run等"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "gateway",
        "description": "网关管理。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "操作: restart/config.get/config.patch等"},
            },
            "required": ["action"],
        },
    },
]


def _build_openclaw_tool_schemas() -> List[Dict[str, Any]]:
    """构建 OpenClaw 直接工具的 function calling schemas"""
    schemas = []
    for tool in _OPENCLAW_TOOLS:
        schemas.append({
            "type": "function",
            "function": {
                "name": f"tool__{tool['name']}",
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        })
    return schemas


# ---------------------------------------------------------------------------
# OpenClaw Agent 模式（单个 message 参数）
# ---------------------------------------------------------------------------


def _build_openclaw_agent_schema() -> List[Dict[str, Any]]:
    """构建 OpenClaw Agent 模式 schema（复杂多步任务）"""
    return [{
        "type": "function",
        "function": {
            "name": "openclaw__agent",
            "description": "临时 OpenClaw 复杂执行器。仅当没有合适现有干员可委派，且任务需要临时多步推理、研究或复杂执行时使用；不要把它当成通讯录干员。",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "完整的任务描述"},
                },
                "required": ["message"],
            },
        },
    }]


# ---------------------------------------------------------------------------
# MCP 本地工具（从 MANIFEST_CACHE 动态生成）
# ---------------------------------------------------------------------------


def _build_mcp_schemas(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """从 MCP 注册表动态生成 function calling schemas"""
    schemas = []
    try:
        from mcpserver.mcp_registry import MANIFEST_CACHE, auto_register_mcp, list_visible_service_names
        auto_register_mcp()
        visible_services = set(list_visible_service_names(agent_id))

        for service_name, manifest in MANIFEST_CACHE.items():
            if service_name not in visible_services:
                continue
            tools = manifest.get("capabilities", {}).get("invocationCommands", [])
            for tool in tools:
                command = tool.get("command", "")
                if not command:
                    continue

                description = tool.get("description", "").split("\n")[0]  # 首行
                example = tool.get("example", "")
                declared_parameters = tool.get("parameters")

                if isinstance(declared_parameters, dict):
                    schema = {
                        "type": "function",
                        "function": {
                            "name": _make_mcp_func_name(service_name, command),
                            "description": f"[MCP/{service_name}] {description}",
                            "parameters": declared_parameters,
                        },
                    }
                    schemas.append(schema)
                    continue

                # 从 example JSON 推断参数
                params_properties = {}
                params_required = []
                if example:
                    try:
                        example_obj = json.loads(example)
                        for key, val in example_obj.items():
                            if key in ("tool_name", "service_name", "agentType"):
                                continue  # 跳过元字段
                            param_type = "string"
                            if isinstance(val, bool):
                                param_type = "boolean"
                            elif isinstance(val, int):
                                param_type = "integer"
                            elif isinstance(val, float):
                                param_type = "number"
                            params_properties[key] = {"type": param_type}
                            # example 中出现的参数都视为可选；有值的视为必填
                            if val and val != "...":
                                params_required.append(key)
                    except (json.JSONDecodeError, TypeError):
                        pass

                func_name = _make_mcp_func_name(service_name, command)
                schema = {
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "description": f"[MCP/{service_name}] {description}",
                        "parameters": {
                            "type": "object",
                            "properties": params_properties,
                        },
                    },
                }
                if params_required:
                    schema["function"]["parameters"]["required"] = params_required

                schemas.append(schema)
    except Exception as e:
        logger.warning(f"[ToolSchemas] MCP schema 生成失败: {e}")

    return schemas


# ---------------------------------------------------------------------------
# Live2D 动作
# ---------------------------------------------------------------------------


def _build_live2d_schema() -> List[Dict[str, Any]]:
    """构建 Live2D 动作 schema"""
    return [{
        "type": "function",
        "function": {
            "name": "live2d__action",
            "description": "Live2D虚拟形象动作。根据对话情感选择合适的表情动作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "动作名称",
                        "enum": ["normal", "happy", "enjoy", "sad", "surprise"],
                    },
                },
                "required": ["action"],
            },
        },
    }]


# ---------------------------------------------------------------------------
# Naga 自身控制
# ---------------------------------------------------------------------------


def _build_naga_control_schema() -> List[Dict[str, Any]]:
    """构建 naga_control schema"""
    return [{
        "type": "function",
        "function": {
            "name": "naga_control__command",
            "description": "控制Naga自身功能：语音开关、模型切换、角色切换、音乐播放、记忆管理等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "操作名称: get_config/update_config/get_status/toggle_voice/toggle_live2d/set_model/list_characters/switch_character/list_sessions/clear_session/list_skills/toggle_skill/list_mcp_services/start_travel/stop_travel/get_memory_stats/play_music/send_notification",
                    },
                    "params": {
                        "type": "object",
                        "description": "操作参数（不同操作所需参数不同）",
                        "additionalProperties": True,
                    },
                },
                "required": ["action"],
            },
        },
    }]
