#!/usr/bin/env python3
"""
Agentic Tool Loop 核心引擎
实现单LLM agentic loop：模型在对话中发起工具调用，接收结果，再继续推理，直到不再需要工具。
"""

import asyncio
import json
import logging
import re
import time as _time
from json import JSONDecodeError
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from system.config import get_config, get_server_port
from apiserver.agent_directory import format_agent_directory_text, resolve_agent_descriptor
from apiserver import naga_auth
from apiserver.tool_schemas import resolve_mcp_func_name

logger = logging.getLogger(__name__)

_TOOL_SECTION_BEGIN = "<|tool_calls_section_begin|>"
_TOOL_SECTION_END = "<|tool_calls_section_end|>"
_TOOL_CALL_BEGIN = "<|tool_call_begin|>functions."
_TOOL_CALL_ARG_BEGIN = "<|tool_call_argument_begin|>"
_TOOL_CALL_END = "<|tool_call_end|>"

# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------


def _normalize_fullwidth_json_chars(text: str) -> str:
    """将常见全角JSON相关字符归一化为ASCII"""
    if not text:
        return text
    translation_table = str.maketrans(
        {
            "｛": "{",
            "｝": "}",
            "：": ":",
            "，": ",",
            "\u201c": '"',
            "\u201d": '"',
            "\u2018": "'",
            "\u2019": "'",
        }
    )
    return text.translate(translation_table)


def _extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """从文本中提取所有顶层JSON对象（花括号深度匹配 + json5/json 解析 + agentType过滤）"""

    def _loads(s: str) -> Any:
        try:
            import json5 as _json5

            return _json5.loads(s)
        except Exception:
            return json.loads(s)

    objects: List[Dict[str, Any]] = []
    start: Optional[int] = None
    depth = 0

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start : i + 1].strip()
                    start = None
                    if candidate in ("{}", "{ }"):
                        continue
                    try:
                        parsed = _loads(candidate)
                    except Exception:
                        continue
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                    elif isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict):
                                objects.append(item)

    # 只保留含 agentType 字段的对象
    return [obj for obj in objects if isinstance(obj.get("agentType"), str) and obj["agentType"]]


def _extract_tool_blocks(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """从 ```tool``` 代码块中提取工具调用JSON。

    Returns:
        (clean_text, tool_calls) — clean_text 是移除代码块后的纯文本
    """

    tool_calls: List[Dict[str, Any]] = []
    # 匹配 ```tool ... ``` 代码块（允许未闭合的尾部块用 \Z 兜底）
    # 注意: 用 [ \t]* 而非 \s* 避免吃掉换行符; 用 \Z 而非 $ 避免 MULTILINE 下提前匹配行尾
    pattern = re.compile(r"```tool[ \t]*\n([\s\S]*?)(?:```|\Z)")

    for match in pattern.finditer(text):
        block_content = match.group(1).strip()
        if not block_content:
            continue
        normalized = _normalize_fullwidth_json_chars(block_content)
        extracted = _extract_json_objects(normalized)
        tool_calls.extend(extracted)

    # 从文本中移除 ```tool...``` 代码块
    clean_text = pattern.sub("", text).strip()
    # 清理多余空行
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text, tool_calls


def _convert_special_tool_call_to_dispatch(tool_name: str, arguments: Any) -> List[Dict[str, Any]]:
    args = arguments if isinstance(arguments, dict) else {"value": arguments}

    if tool_name == "web_search":
        queries = args.get("queries")
        if isinstance(queries, list):
            shared_args = {k: v for k, v in args.items() if k != "queries"}
            dispatches: List[Dict[str, Any]] = []
            for query in queries:
                if not isinstance(query, str) or not query.strip():
                    continue
                dispatch_args = dict(shared_args)
                dispatch_args["query"] = query.strip()
                dispatches.append({
                    "agentType": "tool",
                    "tool_name": "web_search",
                    "args": dispatch_args,
                })
            if dispatches:
                return dispatches

    return [{
        "agentType": "tool",
        "tool_name": tool_name,
        "args": args,
    }]


def _extract_special_tool_calls(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """提取 Kimi/OpenAI 兼容层泄露出的特殊工具调用语法。"""
    if _TOOL_CALL_BEGIN not in text:
        return text, []

    decoder = json.JSONDecoder()
    tool_calls: List[Dict[str, Any]] = []
    clean_parts: List[str] = []
    cursor = 0

    while True:
        start = text.find(_TOOL_CALL_BEGIN, cursor)
        if start < 0:
            clean_parts.append(text[cursor:])
            break

        section_start = text.rfind(_TOOL_SECTION_BEGIN, cursor, start)
        clean_parts.append(text[cursor:section_start if section_start >= 0 else start])

        name_start = start + len(_TOOL_CALL_BEGIN)
        colon = text.find(":", name_start)
        arg_start = text.find(_TOOL_CALL_ARG_BEGIN, colon if colon >= 0 else name_start)
        if colon < 0 or arg_start < 0:
            clean_parts.append(text[start:])
            break

        tool_name = text[name_start:colon].strip()
        json_start = arg_start + len(_TOOL_CALL_ARG_BEGIN)

        try:
            arguments, consumed = decoder.raw_decode(text[json_start:])
        except JSONDecodeError:
            logger.warning("[AgenticLoop] 无法解析特殊工具调用 JSON，保留原始文本")
            clean_parts.append(text[start:])
            break

        tool_calls.extend(_convert_special_tool_call_to_dispatch(tool_name, arguments))

        end = text.find(_TOOL_CALL_END, json_start + consumed)
        if end < 0:
            cursor = json_start + consumed
        else:
            cursor = end + len(_TOOL_CALL_END)
            if text.startswith(_TOOL_SECTION_END, cursor):
                cursor += len(_TOOL_SECTION_END)

    clean_text = "".join(clean_parts).strip()
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text, tool_calls


def parse_tool_calls_from_text(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """从LLM完整输出中提取所有工具调用JSON。

    优先从 ```tool``` 代码块提取，回退到裸JSON行提取（向后兼容）。

    Returns:
        (clean_text, tool_calls) — clean_text 是去掉工具调用后的纯文本
    """
    # 优先使用 ```tool``` 代码块
    clean_text, tool_calls = _extract_tool_blocks(text)
    if tool_calls:
        return clean_text, tool_calls

    clean_text, tool_calls = _extract_special_tool_calls(text)
    if tool_calls:
        return clean_text, tool_calls

    # 回退：从裸文本中提取含 agentType 的JSON对象（向后兼容）
    normalized = _normalize_fullwidth_json_chars(text)
    tool_calls = _extract_json_objects(normalized)

    if not tool_calls:
        return text, []

    # 从原始文本中移除工具调用JSON所在的行
    clean_lines = []
    for line in text.split("\n"):
        norm_line = _normalize_fullwidth_json_chars(line.strip())
        if norm_line:
            extracted = _extract_json_objects(norm_line)
            if extracted:
                continue  # 跳过包含工具调用的行
        clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()
    return clean_text, tool_calls


# ---------------------------------------------------------------------------
# OpenClaw 共享客户端与可用性预检
# ---------------------------------------------------------------------------

_shared_openclaw_client: Optional[httpx.AsyncClient] = None


def _get_openclaw_client() -> httpx.AsyncClient:
    """获取或创建共享的 httpx 客户端（避免每次调用都新建连接）"""
    global _shared_openclaw_client
    if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
        _shared_openclaw_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=150.0, connect=10.0),
            proxy=None,  # localhost 请求不走系统代理
        )
    return _shared_openclaw_client


_openclaw_available: Optional[bool] = None
_openclaw_check_time: float = 0.0
_OPENCLAW_CHECK_TTL = 30.0
_openclaw_start_attempted: bool = False  # 每次进程生命周期内只自动启动一次


async def _check_openclaw_available() -> bool:
    """检查 OpenClaw 服务是否可用，不可用时尝试自动启动"""
    global _openclaw_available, _openclaw_check_time, _openclaw_start_attempted
    now = _time.monotonic()
    if _openclaw_available is not None and (now - _openclaw_check_time) < _OPENCLAW_CHECK_TTL:
        return _openclaw_available

    agent_base = f"http://localhost:{get_server_port('agent_server')}"
    client = _get_openclaw_client()

    _openclaw_available = await _probe_openclaw_health(client, agent_base)

    # 不可用且还没尝试过自动启动 → 启动一次
    if not _openclaw_available and not _openclaw_start_attempted:
        _openclaw_start_attempted = True
        logger.info("[AgenticLoop] OpenClaw gateway 不可用，尝试自动启动...")
        try:
            resp = await client.post(f"{agent_base}/openclaw/gateway/start", timeout=45.0)
            if resp.status_code == 200:
                start_result = resp.json()
                # start_gateway 内部已经等待并检查了连通性
                if start_result.get("success"):
                    logger.info("[AgenticLoop] OpenClaw gateway 启动成功")
                    # 再确认一次 health
                    _openclaw_available = await _probe_openclaw_health(client, agent_base)
                    if not _openclaw_available:
                        # start 说成功但 health 还没好，短暂等待
                        await asyncio.sleep(2)
                        _openclaw_available = await _probe_openclaw_health(client, agent_base)
                else:
                    msg = start_result.get("message", "未知原因")
                    logger.warning(f"[AgenticLoop] OpenClaw gateway 启动失败: {msg}")
            else:
                logger.warning(f"[AgenticLoop] OpenClaw gateway 启动请求失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[AgenticLoop] OpenClaw gateway 自动启动异常: {e}")

    _openclaw_check_time = _time.monotonic()
    return _openclaw_available


async def _probe_openclaw_health(client: httpx.AsyncClient, agent_base: str) -> bool:
    """探测 OpenClaw gateway 是否健康"""
    try:
        resp = await client.get(f"{agent_base}/openclaw/health", timeout=3.0)
        data = resp.json()
        return (
            resp.status_code == 200
            and data.get("success", False)
            and data.get("health", {}).get("status") == "healthy"
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 工具执行
# ---------------------------------------------------------------------------


async def _execute_mcp_call(call: Dict[str, Any], source_agent_id: Optional[str] = None) -> Dict[str, Any]:
    """执行单个MCP调用"""
    service_name = call.get("service_name", "")
    tool_name = call.get("tool_name", "")

    if not service_name and tool_name in {
        "ask_guide",
        "ask_guide_with_screenshot",
        "calculate_damage",
        "get_team_recommendation",
    }:
        service_name = "game_guide"
        call["service_name"] = service_name

    # 游戏攻略功能仅登录用户可用
    if service_name == "game_guide":
        if not naga_auth.is_authenticated():
            return {
                "tool_call": call,
                "result": "游戏攻略功能需要登录 Naga 账号后才能使用，请先登录。",
                "status": "error",
                "service_name": service_name,
                "tool_name": tool_name,
            }

    try:
        from mcpserver.mcp_registry import is_service_visible_to_agent
        from mcpserver.mcp_manager import get_mcp_manager

        if not is_service_visible_to_agent(service_name, agent_id=source_agent_id):
            return {
                "tool_call": call,
                "result": f"当前干员无权访问 MCP 服务: {service_name}",
                "status": "error",
                "service_name": service_name,
                "tool_name": tool_name,
            }

        manager = get_mcp_manager()
        t0 = _time.monotonic()
        result = await manager.unified_call(service_name, call)
        elapsed = _time.monotonic() - t0
        logger.info(f"[AgenticLoop] MCP调用完成: {service_name}/{tool_name} 耗时 {elapsed:.2f}s")
        return {
            "tool_call": call,
            "result": result,
            "status": "success",
            "service_name": service_name,
            "tool_name": tool_name,
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] MCP调用失败: service={service_name}, error={e}")
        return {
            "tool_call": call,
            "result": f"调用失败: {e}",
            "status": "error",
            "service_name": service_name,
            "tool_name": tool_name,
        }


async def _execute_openclaw_call(call: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    """执行单个OpenClaw调用（Agent 模式，通过 /hooks/agent 走二次 LLM）"""
    message = call.get("message", "")
    task_type = call.get("task_type", "message")

    if not message:
        return {
            "tool_call": call,
            "result": "缺少message字段",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }

    if not await _check_openclaw_available():
        return {
            "tool_call": call,
            "result": "OpenClaw 服务当前不可用，请稍后重试",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }

    payload = {
        "message": message,
        "session_key": call.get("session_key", f"naga_{session_id}"),
        "name": "Naga",
        "wake_mode": "now",
        "timeout_seconds": 120,
    }

    if task_type == "cron" and call.get("schedule"):
        payload["message"] = f"[定时任务 cron: {call.get('schedule')}] {message}"
    elif task_type == "reminder" and call.get("at"):
        payload["message"] = f"[提醒 在 {call.get('at')} 后] {message}"

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/send",
            json=payload,
        )
        if response.status_code == 200:
            result_data = response.json()
            # 先检查 agent_server 返回的 success 标记
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or "OpenClaw任务执行失败"
                return {
                    "tool_call": call,
                    "result": f"联网搜索失败: {error_msg}",
                    "status": "error",
                    "service_name": "openclaw",
                    "tool_name": task_type,
                }
            # agent_server 返回两个字段：replies(列表，异步轮询时填充) 和 reply(字符串，同步完成时填充)
            replies = result_data.get("replies") or []
            if replies:
                combined = "\n".join(replies)
            elif result_data.get("reply"):
                combined = result_data["reply"]
            else:
                combined = "任务已提交，暂无返回结果"
            return {
                "tool_call": call,
                "result": combined,
                "status": "success",
                "service_name": "openclaw",
                "tool_name": task_type,
            }
        else:
            return {
                "tool_call": call,
                "result": f"HTTP {response.status_code}: {response.text[:200]}",
                "status": "error",
                "service_name": "openclaw",
                "tool_name": task_type,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw调用失败: {e}")
        return {
            "tool_call": call,
            "result": f"调用失败: {e}",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }


async def _execute_naga_search(call: Dict[str, Any]) -> Dict[str, Any]:
    """通过 NagaBusiness 搜索代理执行 web_search（已登录时优先使用）"""
    tool_args = call.get("args", {})
    query = tool_args.get("query", "") or tool_args.get("q", "")
    count = tool_args.get("count", 10)
    freshness = tool_args.get("freshness")

    if not query:
        return {
            "tool_call": call, "result": "缺少搜索关键词",
            "status": "error", "service_name": "naga_search", "tool_name": "web_search",
        }

    try:
        token = naga_auth.get_access_token()
        params: Dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness

        client = _get_openclaw_client()
        t0 = _time.monotonic()
        resp = await client.post(
            naga_auth.NAGA_MODEL_URL + "/tools/search",
            json=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        elapsed = _time.monotonic() - t0

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                error_msg = error_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            except Exception:
                error_msg = f"HTTP {resp.status_code}"
            logger.error(f"[AgenticLoop] Naga搜索代理错误: {error_msg}")
            return {
                "tool_call": call, "result": f"搜索失败: {error_msg}",
                "status": "error", "service_name": "naga_search", "tool_name": "web_search",
            }

        data = resp.json()
        results = data.get("web", {}).get("results", [])
        # 格式化搜索结果为可读文本
        if not results:
            readable = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                desc = r.get("description", "")
                age = r.get("age", "")
                lines.append(f"{i}. {title}")
                lines.append(f"   URL: {url}")
                if desc:
                    lines.append(f"   摘要: {desc}")
                if age:
                    lines.append(f"   时间: {age}")
                lines.append("")
            readable = "\n".join(lines)

        logger.info(f"[AgenticLoop] Naga搜索完成: query=\"{query}\" 耗时 {elapsed:.2f}s, 结果数={len(results)}")
        return {
            "tool_call": call, "result": readable,
            "status": "success", "service_name": "naga_search", "tool_name": "web_search",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] Naga搜索代理异常: {e}")
        return {
            "tool_call": call, "result": f"搜索异常: {e}",
            "status": "error", "service_name": "naga_search", "tool_name": "web_search",
        }


async def _execute_brave_search(call: Dict[str, Any]) -> Dict[str, Any]:
    """通过配置的 Brave Search API Key 直接搜索（未登录 Naga 时使用）"""
    tool_args = call.get("args", {})
    query = tool_args.get("query", "") or tool_args.get("q", "")
    count = tool_args.get("count", 10)
    freshness = tool_args.get("freshness")

    if not query:
        return {
            "tool_call": call, "result": "缺少搜索关键词",
            "status": "error", "service_name": "brave_search", "tool_name": "web_search",
        }

    try:
        cfg = get_config()
        api_key = cfg.online_search.search_api_key
        api_base = cfg.online_search.search_api_base

        params: Dict[str, Any] = {"q": query, "count": count}
        if freshness:
            params["freshness"] = freshness

        client = _get_openclaw_client()
        t0 = _time.monotonic()
        resp = await client.get(
            api_base,
            params=params,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            timeout=30.0,
        )
        elapsed = _time.monotonic() - t0

        if resp.status_code != 200:
            try:
                error_data = resp.json()
                error_msg = str(error_data)[:200]
            except Exception:
                error_msg = f"HTTP {resp.status_code}"
            logger.error(f"[AgenticLoop] Brave搜索错误: {error_msg}")
            return {
                "tool_call": call, "result": f"搜索失败: {error_msg}",
                "status": "error", "service_name": "brave_search", "tool_name": "web_search",
            }

        data = resp.json()
        results = data.get("web", {}).get("results", [])
        if not results:
            readable = "未找到相关搜索结果。"
        else:
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("url", "")
                desc = r.get("description", "")
                age = r.get("age", "")
                lines.append(f"{i}. {title}")
                lines.append(f"   URL: {url}")
                if desc:
                    lines.append(f"   摘要: {desc}")
                if age:
                    lines.append(f"   时间: {age}")
                lines.append("")
            readable = "\n".join(lines)

        logger.info(f"[AgenticLoop] Brave搜索完成: query=\"{query}\" 耗时 {elapsed:.2f}s, 结果数={len(results)}")
        return {
            "tool_call": call, "result": readable,
            "status": "success", "service_name": "brave_search", "tool_name": "web_search",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] Brave搜索异常: {e}")
        return {
            "tool_call": call, "result": f"搜索异常: {e}",
            "status": "error", "service_name": "brave_search", "tool_name": "web_search",
        }


async def execute_pre_search(query: str, count: int = 8) -> Optional[str]:
    """
    前置搜索：在主 LLM 调用前执行搜索，返回格式化的搜索结果文本。
    复用 3-tier 搜索回退链：NagaBusiness → Brave → None
    """
    # 构造虚拟 call dict 供搜索函数使用
    call = {"args": {"query": query, "count": count}}

    if naga_auth.is_authenticated():
        result = await _execute_naga_search(call)
        if result.get("status") == "success" and result.get("result"):
            return result["result"]

    cfg = get_config()
    if cfg.online_search.search_api_key:
        result = await _execute_brave_search(call)
        if result.get("status") == "success" and result.get("result"):
            return result["result"]

    return None  # 无可用搜索源，跳过前置搜索


# Gateway 可直接调用的工具（/tools/invoke），其余为 agent-session 工具需走 /hooks/agent
_GATEWAY_DIRECT_TOOLS = frozenset({
    "web_search", "web_fetch", "browser",
    "memory_search", "memory_get",
    "sessions_list", "sessions_history", "session_status",
    "agents_list", "cron", "message", "tts", "canvas", "nodes",
})

# 可本地执行的工具（无需经过 OpenClaw，直接本地完成）
_LOCAL_EXEC_TOOLS = frozenset({
    "exec", "read", "write", "edit", "ls", "find", "grep", "process", "image",
    "sessions_spawn", "sessions_send", "gateway", "agents_list", "agent_relay",
})


async def _execute_openclaw_tool_call(
    call: Dict[str, Any],
    source_agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 OpenClaw 工具。
    Gateway 级工具直接走 /tools/invoke；
    agent-session 级工具（exec/read/write 等）走 /hooks/agent 让 agent 代执行。
    """
    tool_name = call.get("tool_name", "")
    tool_args = call.get("args", {})

    if not tool_name:
        return {
            "tool_call": call, "result": "缺少 tool_name",
            "status": "error", "service_name": "openclaw_tool", "tool_name": "unknown",
        }

    # web_search: 已登录走 Naga 代理，未登录有 key 走 Brave，都没有走 OpenClaw
    if tool_name == "web_search":
        if naga_auth.is_authenticated():
            return await _execute_naga_search(call)
        cfg = get_config()
        if cfg.online_search.search_api_key:
            return await _execute_brave_search(call)

    # 本地可执行工具：直接在本机执行，不经过 OpenClaw agent session
    if tool_name in _LOCAL_EXEC_TOOLS:
        return await _execute_local_tool(call, tool_name, tool_args, source_agent_id=source_agent_id)

    if not await _check_openclaw_available():
        return {
            "tool_call": call, "result": "OpenClaw 服务当前不可用，请稍后重试",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    try:
        client = _get_openclaw_client()
        t0 = _time.monotonic()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/tools/invoke",
            json={"tool": tool_name, "args": tool_args},
        )
        elapsed = _time.monotonic() - t0
        if response.status_code == 200:
            result_data = response.json()
            # 先检查 agent_server 层面的 success 标记（如 tool_not_found）
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or result_data.get("detail") or "工具调用失败"
                logger.error(f"[AgenticLoop] OpenClaw工具返回失败: {tool_name}, error={error_msg}")
                return {
                    "tool_call": call, "result": f"调用失败: {error_msg}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }
            # agent_server 返回 { success: true, result: { ok, result: { content: [...] } } }
            # invoke_tool 包了一层，需解开两层 result 才能到 OpenClaw 的原始工具输出
            result_content = result_data.get("result", result_data)
            if isinstance(result_content, dict) and "result" in result_content:
                result_content = result_content["result"]

            # 检查 OpenClaw 工具级别的错误（isError 标记 或 error 字段）
            if isinstance(result_content, dict) and (result_content.get("isError") or "error" in result_content):
                readable = _extract_openclaw_tool_result(result_content)
                logger.error(f"[AgenticLoop] OpenClaw工具错误: {tool_name}, result={readable[:300]}")
                return {
                    "tool_call": call, "result": f"工具执行错误: {readable}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }

            readable = _extract_openclaw_tool_result(result_content)

            # 检测嵌套在 content text 中的 JSON 错误（如 {"error": "missing_brave_api_key", ...}）
            if readable.lstrip().startswith("{"):
                try:
                    parsed = json.loads(readable)
                    if isinstance(parsed, dict) and "error" in parsed:
                        error_msg = parsed.get("message") or str(parsed["error"])
                        logger.error(f"[AgenticLoop] OpenClaw工具错误: {tool_name}, error={error_msg}")
                        return {
                            "tool_call": call, "result": f"工具执行错误: {error_msg}",
                            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                        }
                except (json.JSONDecodeError, TypeError):
                    pass

            logger.info(f"[AgenticLoop] OpenClaw直接工具调用完成: {tool_name} 耗时 {elapsed:.2f}s, 结果长度={len(readable)}")
            logger.info(f"[AgenticLoop] OpenClaw工具结果预览: {readable[:300]}")
            return {
                "tool_call": call, "result": readable,
                "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
        else:
            logger.error(f"[AgenticLoop] OpenClaw直接工具调用HTTP错误: {tool_name}, status={response.status_code}, body={response.text[:200]}")
            return {
                "tool_call": call, "result": f"调用失败: HTTP {response.status_code} - {response.text[:200]}",
                "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw直接工具调用失败: {tool_name}, error={e}")
        return {
            "tool_call": call, "result": f"调用异常: {e}",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }


async def _execute_local_tool(
    call: Dict[str, Any],
    tool_name: str,
    tool_args: Dict[str, Any],
    source_agent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """本地直接执行 agent-session 级工具（exec/read/write/ls/grep 等），不经过 OpenClaw。"""
    import subprocess as _sp
    from pathlib import Path as _Path

    def _ok(text: str) -> Dict[str, Any]:
        return {
            "tool_call": call, "result": text,
            "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    def _err(text: str) -> Dict[str, Any]:
        return {
            "tool_call": call, "result": text,
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    try:
        if tool_name == "exec":
            cmd = tool_args.get("command", "")
            if not cmd:
                return _err("缺少 command 参数")
            timeout = min(tool_args.get("timeout", 60), 300)
            workdir = tool_args.get("workdir")
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return _err(f"命令执行超时 ({timeout}s)")
            out = (stdout or b"").decode(errors="replace")
            err = (stderr or b"").decode(errors="replace")
            text = out
            if err:
                text += f"\n[stderr]\n{err}" if out else err
            if proc.returncode != 0:
                text += f"\n[exit code: {proc.returncode}]"
            return _ok(text[:50000] if text else "(无输出)")

        elif tool_name == "read":
            fp = tool_args.get("file_path", "")
            if not fp:
                return _err("缺少 file_path 参数")
            p = _Path(fp).expanduser()
            if not p.exists():
                return _err(f"文件不存在: {fp}")
            content = p.read_text(encoding="utf-8", errors="replace")
            return _ok(content[:100000])

        elif tool_name == "write":
            fp = tool_args.get("file_path", "")
            content = tool_args.get("content", "")
            if not fp:
                return _err("缺少 file_path 参数")
            p = _Path(fp).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return _ok(f"已写入 {fp} ({len(content)} 字符)")

        elif tool_name == "edit":
            fp = tool_args.get("file_path", "")
            old = tool_args.get("old_string", "")
            new = tool_args.get("new_string", "")
            if not fp or not old:
                return _err("缺少 file_path 或 old_string 参数")
            p = _Path(fp).expanduser()
            if not p.exists():
                return _err(f"文件不存在: {fp}")
            text = p.read_text(encoding="utf-8", errors="replace")
            if old not in text:
                return _err(f"未找到要替换的文本")
            text = text.replace(old, new, 1)
            p.write_text(text, encoding="utf-8")
            return _ok(f"已替换 {fp}")

        elif tool_name == "ls":
            path = tool_args.get("path", ".")
            p = _Path(path).expanduser()
            if not p.is_dir():
                return _err(f"目录不存在: {path}")
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            lines = []
            for e in entries[:500]:
                prefix = "d " if e.is_dir() else "  "
                lines.append(f"{prefix}{e.name}")
            return _ok("\n".join(lines) if lines else "(空目录)")

        elif tool_name == "find":
            pattern = tool_args.get("pattern", "*")
            path = tool_args.get("path", ".")
            p = _Path(path).expanduser()
            matches = sorted(p.rglob(pattern))[:200]
            return _ok("\n".join(str(m) for m in matches) if matches else "未找到匹配文件")

        elif tool_name == "grep":
            import re as _re
            pattern = tool_args.get("pattern", "")
            path = tool_args.get("path", ".")
            include = tool_args.get("include", "")
            if not pattern:
                return _err("缺少 pattern 参数")
            p = _Path(path).expanduser()
            glob_pat = include if include else "**/*"
            files = p.rglob(glob_pat) if p.is_dir() else [p]
            results = []
            try:
                regex = _re.compile(pattern)
            except _re.error as e:
                return _err(f"正则表达式错误: {e}")
            for f in files:
                if not f.is_file() or f.stat().st_size > 2_000_000:
                    continue
                try:
                    for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{f}:{i}: {line.rstrip()}")
                            if len(results) >= 200:
                                break
                except Exception:
                    continue
                if len(results) >= 200:
                    break
            return _ok("\n".join(results) if results else "未找到匹配")

        elif tool_name == "agents_list":
            return _ok(format_agent_directory_text())

        elif tool_name == "agent_relay":
            return await _execute_agent_relay(call, tool_args, source_agent_id)

        elif tool_name == "image":
            url = tool_args.get("url", "")
            return _err(f"image 工具暂不支持本地执行，请使用 openclaw__agent 模式: {url}")

        elif tool_name == "process":
            return _err("process 工具暂不支持本地执行，请使用 openclaw__agent 模式")

        else:
            # sessions_spawn, sessions_send, gateway 等走 OpenClaw agent session 降级
            return await _execute_openclaw_session_tool(call, tool_name, tool_args)

    except Exception as e:
        logger.error(f"[AgenticLoop] 本地工具执行失败: {tool_name}, error={e}")
        return _err(f"执行失败: {e}")


async def _execute_agent_relay(
    call: Dict[str, Any],
    tool_args: Dict[str, Any],
    source_agent_id: Optional[str],
) -> Dict[str, Any]:
    target_agent_id = str(tool_args.get("target_agent_id") or "").strip() or None
    target_agent_name = str(tool_args.get("target_agent_name") or "").strip() or None
    message = str(tool_args.get("message") or "").strip()
    if not message:
        return {
            "tool_call": call,
            "result": "缺少 message 参数",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    if not target_agent_id and not target_agent_name:
        return {
            "tool_call": call,
            "result": "缺少目标干员，请先调用 agents_list 再指定 target_agent_id 或 target_agent_name",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    target = resolve_agent_descriptor(agent_id=target_agent_id, agent_name=target_agent_name, include_builtin=True)
    if target is None:
        return {
            "tool_call": call,
            "result": "目标干员不存在，请先调用 agents_list 检查通讯录",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    payload = {
        "message": message,
        "target_agent_id": target.id,
        "source_agent_id": source_agent_id,
        "purpose": tool_args.get("purpose"),
        "context": tool_args.get("context"),
        "timeout_seconds": max(5, min(int(tool_args.get("timeout_seconds", 120) or 120), 600)),
    }

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('api_server')}/agents/relay",
            json=payload,
            timeout=payload["timeout_seconds"] + 30,
        )
        if response.status_code != 200:
            return {
                "tool_call": call,
                "result": f"转发失败: HTTP {response.status_code} {response.text[:300]}",
                "status": "error",
                "service_name": "agent_directory",
                "tool_name": "agent_relay",
            }
        data = response.json()
        if not data.get("success", False):
            return {
                "tool_call": call,
                "result": data.get("error") or "目标干员未返回成功结果",
                "status": "error",
                "service_name": "agent_directory",
                "tool_name": "agent_relay",
            }
        reply = str(data.get("reply") or "").strip() or "(目标干员未返回正文)"
        result_text = (
            f"目标干员: {data.get('target', {}).get('name', target.name)}\n"
            f"目标引擎: {data.get('target', {}).get('engine', target.engine)}\n"
            f"回复:\n{reply}"
        )
        return {
            "tool_call": call,
            "result": result_text,
            "status": "success",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] 干员转发失败: {e}")
        return {
            "tool_call": call,
            "result": f"转发异常: {e}",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }


async def _execute_openclaw_session_tool(
    call: Dict[str, Any], tool_name: str, tool_args: Dict[str, Any]
) -> Dict[str, Any]:
    """通过 agent session (/hooks/agent) 执行需要 OpenClaw agent 的工具。"""
    args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
    instruction = f"请直接使用 {tool_name} 工具执行以下操作，只返回工具执行结果：\n{args_str}"

    payload = {
        "message": instruction,
        "session_key": f"naga_tool_{tool_name}",
        "name": "Naga",
        "wake_mode": "now",
        "timeout_seconds": 120,
    }

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/send",
            json=payload,
        )
        if response.status_code == 200:
            result_data = response.json()
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or "agent 会话执行失败"
                return {
                    "tool_call": call, "result": f"调用失败: {error_msg}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }
            replies = result_data.get("replies") or []
            reply = "\n".join(replies) if replies else (result_data.get("reply") or "任务已提交，暂无返回结果")
            return {
                "tool_call": call, "result": reply,
                "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
        else:
            return {
                "tool_call": call, "result": f"HTTP {response.status_code}: {response.text[:200]}",
                "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw session工具调用失败: {tool_name}, error={e}")
        return {
            "tool_call": call, "result": f"调用异常: {e}",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }


def _extract_openclaw_tool_result(result: Any) -> str:
    """从 OpenClaw /tools/invoke 返回值中提取可读文本"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 标准格式: { content: [{ type: "text", text: "..." }] }
        content = result.get("content", [])
        if isinstance(content, list) and content:
            texts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif "text" in item:
                        texts.append(str(item["text"]))
                elif isinstance(item, str):
                    texts.append(item)
            if texts:
                return "\n".join(texts)
        # 备选: 直接有 text 字段
        if "text" in result:
            return str(result["text"])
        # 备选: 有 error/message 字段（OpenClaw 错误响应）
        if "error" in result:
            return f"错误: {result['error']}"
        if "message" in result:
            return str(result["message"])
        # 兜底: JSON dump
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, list):
        # 直接是 content 数组
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)
    return str(result)


async def _execute_naga_control(call: Dict[str, Any]) -> Dict[str, Any]:
    """执行 Naga 自身控制操作（直接调用，无需 HTTP）"""
    from .naga_control import execute

    action = call.get("action", "")
    params = call.get("params", {})

    t0 = _time.monotonic()
    result = await execute(action, params)
    elapsed = _time.monotonic() - t0
    logger.info(f"[AgenticLoop] NagaControl 完成: {action} 耗时 {elapsed:.2f}s")

    return {
        "tool_call": call,
        "result": json.dumps(result, ensure_ascii=False),
        "status": "success" if result.get("success") else "error",
        "service_name": "naga_control",
        "tool_name": action,
    }


async def _send_live2d_actions(live2d_calls: List[Dict[str, Any]], session_id: str):
    """Fire-and-forget发送Live2D动作到UI"""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=5.0)) as client:
            for call in live2d_calls:
                action_name = call.get("action", "")
                logger.info(f"[AgenticLoop] 发送 Live2D 动作: {action_name}, 完整调用: {call}")
                if not action_name:
                    continue
                payload = {
                    "session_id": session_id,
                    "action": "live2d_action",
                    "action_name": action_name,
                }
                try:
                    await client.post(
                        f"http://localhost:{get_server_port('api_server')}/ui_notification",
                        json=payload,
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[AgenticLoop] Live2D动作发送失败: {e}")


async def execute_tool_calls(
    tool_calls: List[Dict[str, Any]],
    session_id: str,
    source_agent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """按 agentType 分组并行执行工具调用（不包含 live2d）。

    Returns:
        [{"tool_call": {...}, "result": "...", "status": "success|error", "service_name": "...", "tool_name": "..."}]
    """
    tasks = []
    for call in tool_calls:
        agent_type = call.get("agentType", "")
        if agent_type == "mcp":
            tasks.append(_execute_mcp_call(call, source_agent_id=source_agent_id))
        elif agent_type == "openclaw":
            tasks.append(_execute_openclaw_call(call, session_id))
        elif agent_type in ("tool", "openclaw_tool"):
            tasks.append(_execute_openclaw_tool_call(call, source_agent_id=source_agent_id))
        elif agent_type == "naga_control":
            tasks.append(_execute_naga_control(call))
        else:
            logger.warning(f"[AgenticLoop] 未知agentType: {agent_type}, 跳过: {call}")

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append(
                {
                    "tool_call": {},
                    "result": f"执行异常: {r}",
                    "status": "error",
                    "service_name": "unknown",
                    "tool_name": "unknown",
                }
            )
        else:
            final.append(r)
    return final


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------


def format_tool_results_for_llm(results: List[Dict[str, Any]]) -> str:
    """将工具执行结果格式化为LLM可理解的文本"""
    parts = []
    total = len(results)
    for idx, r in enumerate(results, 1):
        svc = r.get("service_name", "unknown")
        tool = r.get("tool_name", "")
        status = r.get("status", "unknown")
        result_text = r.get("result", "")
        label = f"{svc}"
        if tool:
            label += f": {tool}"
        parts.append(f"[工具结果 {idx}/{total} - {label} ({status})]\n{result_text}")
    return "\n\n".join(parts)


def format_tool_result_for_display(result: Any) -> Any:
    """保留工具原始结构，并在字符串结果中解开常见 JSON 包装。"""
    if not isinstance(result, str):
        return result

    text = result.strip()
    if not text:
        return ""

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return result

    if isinstance(parsed, dict):
        if "data" in parsed and parsed.get("status") in {"success", "ok"}:
            return parsed["data"]
        if "result" in parsed:
            return parsed["result"]
    return parsed


# ---------------------------------------------------------------------------
# SSE 辅助
# ---------------------------------------------------------------------------


def _format_sse_event(event_type: str, data: Any) -> str:
    """格式化扩展SSE事件"""
    payload = {"type": event_type}
    if isinstance(data, dict):
        payload.update(data)
    else:
        payload["data"] = data
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Native Function Calling → Dispatch 格式转换
# ---------------------------------------------------------------------------


def _convert_native_to_dispatch(native_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 OpenAI function call 格式转换为现有 dispatch 格式

    命名约定: {agentType}__{service_name}__{tool_name}
    - tool__web_search → agentType="tool", tool_name="web_search"
    - mcp__weather_time__today_weather → agentType="mcp", service_name="weather_time", tool_name="today_weather"
    - openclaw__agent → agentType="openclaw", task_type="message"
    - live2d__action → agentType="live2d"
    - naga_control__command → agentType="naga_control"

    MCP 工具名在生成时可能被 sanitize（service_name/command 含中文等非法字符），
    故优先用 resolve_mcp_func_name() 反查还原原始名，查不到再 fallback 到 split。
    """
    result = []
    for call in native_calls:
        name = call.get("name", "")
        raw_args = call.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            args = {}

        parts = name.split("__", 2)
        agent_type = parts[0]

        dispatch: Dict[str, Any] = {"agentType": agent_type}

        if agent_type == "openclaw_tool" and len(parts) >= 2:
            # 兼容旧格式
            dispatch["agentType"] = "tool"
            dispatch["tool_name"] = parts[1]
            dispatch["args"] = args
        elif agent_type == "tool" and len(parts) >= 2:
            dispatch["tool_name"] = parts[1]
            dispatch["args"] = args
        elif agent_type == "mcp" and len(parts) >= 3:
            # 优先用反查映射还原原始 service_name/command（function name 可能被 sanitize 过）
            resolved = resolve_mcp_func_name(name)
            if resolved is not None:
                dispatch["service_name"], dispatch["tool_name"] = resolved
            else:
                dispatch["service_name"] = parts[1]
                dispatch["tool_name"] = parts[2]
            # MCP 工具参数直接展开到 dispatch 顶层（与现有格式一致）
            dispatch.update(args)
        elif agent_type == "openclaw":
            dispatch["task_type"] = "message"
            dispatch.update(args)
        elif agent_type == "live2d":
            dispatch.update(args)
        elif agent_type == "naga_control":
            dispatch.update(args)
        else:
            dispatch.update(args)

        # 保存原始信息用于 tool message 回注
        dispatch["_tool_call_id"] = call.get("id", "")
        dispatch["_original_name"] = name
        dispatch["_original_args"] = raw_args if isinstance(raw_args, str) else json.dumps(args, ensure_ascii=False)

        result.append(dispatch)
    return result


def _build_native_assistant_message(
    clean_text: str,
    calls: List[Dict[str, Any]],
    reasoning_content: str = "",
) -> Dict[str, Any]:
    """构造 OpenAI 兼容的 assistant tool_calls 历史消息。"""
    assistant_msg: Dict[str, Any] = {
        "role": "assistant",
        "content": clean_text or None,
        "tool_calls": [
            {
                "id": c.get("_tool_call_id", f"call_{i}"),
                "type": "function",
                "function": {
                    "name": c.get("_original_name", ""),
                    "arguments": c.get("_original_args", "{}"),
                },
            }
            for i, c in enumerate(calls)
        ],
    }
    if reasoning_content.strip():
        assistant_msg["reasoning_content"] = reasoning_content
    return assistant_msg


# ---------------------------------------------------------------------------
# Agentic Loop 核心
# ---------------------------------------------------------------------------


async def run_agentic_loop(
    messages: List[Dict[str, Any]],
    session_id: str,
    max_rounds: int = 5,
    model_override: Optional[Dict[str, str]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    source_agent_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Agentic tool loop 核心。

    流式输出SSE chunks，包含：
    - content/reasoning chunks（透传自LLM）
    - round_start/tool_calls/tool_results/round_end 事件

    每一轮的content都会完整流式输出（供TTS使用），工具内容不混入content流。

    Args:
        messages: 完整的对话消息列表（含system prompt）
        session_id: 会话ID
        max_rounds: 最大循环轮数
        model_override: 临时模型覆盖参数（用于视觉模型等场景）
        tools: OpenAI function calling schemas（可选，传入时启用原生工具调用）

    Yields:
        SSE格式的data chunks
    """
    from .llm_service import get_llm_service

    llm_service = get_llm_service()

    consecutive_failures = 0  # 连续全部失败的轮次计数
    needs_summary = False  # 是否需要进行最终总结轮
    t_loop_start = _time.monotonic()

    for round_num in range(1, max_rounds + 1):
        t_round_start = _time.monotonic()
        # 0. 上下文压缩：每轮开始前检查 token 是否超限
        #    round 1 压缩历史对话，round 2+ 压缩上一轮工具结果膨胀的上下文
        try:
            from .context_compressor import compress_context
            compress_result = await compress_context(messages)
            if compress_result.compressed:
                messages[:] = compress_result.messages
            for sse_event in compress_result.sse_events:
                yield sse_event
        except Exception as e:
            logger.debug(f"[AgenticLoop] 上下文压缩跳过: {e}")

        # 1. 通知前端开始新一轮
        if round_num > 1:
            yield _format_sse_event("round_start", {"round": round_num})

        # 2. 流式调用LLM，累积完整输出
        complete_text = ""
        complete_reasoning = ""
        native_calls = None  # 原生 function calling 结果
        t_llm_start = _time.monotonic()

        # 总结轮不传 tools（禁止再次工具调用）
        round_tools = tools if round_num <= max_rounds else None

        async for chunk in llm_service.stream_chat_with_context(messages, get_config().api.temperature,
                                                                 model_override=model_override,
                                                                 tools=round_tools):
            if chunk.startswith("data: "):
                try:
                    data_str = chunk[6:].strip()
                    if data_str and data_str != "[DONE]":
                        chunk_data = json.loads(data_str)
                        chunk_type = chunk_data.get("type", "content")
                        chunk_text = chunk_data.get("text", "")

                        if chunk_type == "content":
                            complete_text += chunk_text
                        elif chunk_type == "reasoning":
                            complete_reasoning += chunk_text
                        elif chunk_type == "tool_calls_native":
                            # 原生 function calling：完整 tool_calls JSON
                            try:
                                native_calls = json.loads(chunk_text)
                            except (json.JSONDecodeError, TypeError):
                                logger.warning(f"[AgenticLoop] native tool_calls 解析失败: {chunk_text[:200]}")
                            continue  # 不透传此内部事件给前端
                except Exception:
                    pass

            # 透传所有SSE chunks给前端（content + reasoning）
            yield chunk

        # 3. 从完整输出中解析工具调用
        #    优先使用 native tool calls，回退到文本解析（兼容期）
        t_llm_elapsed = _time.monotonic() - t_llm_start
        logger.info(
            f"[AgenticLoop] Round {round_num} LLM流式输出完成: {t_llm_elapsed:.2f}s, "
            f"content={len(complete_text)}字, reasoning={len(complete_reasoning)}字, "
            f"native_calls={'yes' if native_calls else 'no'}"
        )
        logger.debug(
            f"[AgenticLoop] Round {round_num} complete_text ({len(complete_text)} chars): {complete_text[:300]!r}"
        )

        use_native = False
        if native_calls:
            tool_calls = _convert_native_to_dispatch(native_calls)
            clean_text = complete_text  # native 模式下 content 就是纯文本
            use_native = True
            logger.info(f"[AgenticLoop] Round {round_num}: 使用原生 function calling, {len(tool_calls)} 个工具调用")
        else:
            clean_text, tool_calls = parse_tool_calls_from_text(complete_text)

        # 4. 分离 live2d 和可执行调用
        actionable_calls = [tc for tc in tool_calls if tc.get("agentType") != "live2d"]
        live2d_calls = [tc for tc in tool_calls if tc.get("agentType") == "live2d"]

        # 4a. 如果检测到了任何工具调用，发送 content_clean 让前端替换掉带有工具代码块的原文
        if tool_calls and clean_text != complete_text:
            # 保留工具调用前的简短说明文字（如"让我查一下"），仅移除 ```tool``` 代码块
            yield _format_sse_event("content_clean", {"text": clean_text})

        # 4b. 所有工具调用都先透传给前端，再触发实际执行/动画。
        call_descriptions = []
        for tc in tool_calls:
            desc = {"agentType": tc.get("agentType", "")}
            if tc.get("agentType") == "live2d":
                desc["service_name"] = "live2d"
                if tc.get("action"):
                    desc["tool_name"] = tc["action"]
            if tc.get("service_name"):
                desc["service_name"] = tc["service_name"]
            if tc.get("tool_name"):
                desc["tool_name"] = tc["tool_name"]
            if tc.get("message"):
                desc["message"] = tc["message"][:100]
            call_descriptions.append(desc)
        if call_descriptions:
            yield _format_sse_event("tool_calls", {"calls": call_descriptions})

        # 4c. Live2D 在工具调用已经进入消息流后再异步触发，避免生成正文时频繁变脸。
        if live2d_calls:
            asyncio.create_task(_send_live2d_actions(live2d_calls, session_id))

        # 5. 如果没有可执行的工具调用，循环结束
        if not actionable_calls:
            # 模型只返回了 live2d 调用而没有文字内容时（Anthropic 常见行为），
            # 需要将 live2d tool call 的结果回注并再调用一轮 LLM 来生成文字回复
            if live2d_calls and not complete_text.strip() and use_native and round_num < max_rounds:
                logger.info(f"[AgenticLoop] Round {round_num}: 模型仅返回 live2d 调用无正文，"
                            f"回注 tool result 继续下一轮获取文字回复")
                assistant_msg = _build_native_assistant_message("", live2d_calls, complete_reasoning)
                messages.append(assistant_msg)
                for c in live2d_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c.get("_tool_call_id", ""),
                        "content": "已执行",
                    })
                yield _format_sse_event("round_end", {"round": round_num, "has_more": True})
                continue

            t_round_elapsed = _time.monotonic() - t_round_start
            t_total_elapsed = _time.monotonic() - t_loop_start
            logger.info(f"[AgenticLoop] Round {round_num}: 无工具调用，循环结束 "
                        f"(本轮 {t_round_elapsed:.2f}s, 总计 {t_total_elapsed:.2f}s)")
            # 发送本轮结束信号
            yield _format_sse_event("round_end", {"round": round_num, "has_more": False})
            break

        logger.info(f"[AgenticLoop] Round {round_num}: 检测到 {len(actionable_calls)} 个工具调用")

        # 7. 并行执行工具调用
        t_tool_start = _time.monotonic()
        results = await execute_tool_calls(actionable_calls, session_id, source_agent_id=source_agent_id)
        t_tool_elapsed = _time.monotonic() - t_tool_start
        logger.info(f"[AgenticLoop] Round {round_num}: 工具执行完成 {t_tool_elapsed:.2f}s "
                    f"({len(results)} 个工具)")

        # 7a. 检测连续失败：本轮所有工具是否全部失败
        all_failed = all(r.get("status") == "error" for r in results)
        if all_failed:
            consecutive_failures += 1
            logger.warning(f"[AgenticLoop] Round {round_num}: 本轮所有工具调用失败 (连续 {consecutive_failures} 轮)")
        else:
            consecutive_failures = 0

        # 8. 通知前端工具结果
        result_summaries = []
        for r in results:
            result_summaries.append(
                {
                    "service_name": r.get("service_name", "unknown"),
                    "tool_name": r.get("tool_name", ""),
                    "status": r.get("status", "unknown"),
                    "result": format_tool_result_for_display(r.get("result", "")),
                }
            )
        yield _format_sse_event("tool_results", {"results": result_summaries})

        # 9. 将本轮LLM输出 + 工具结果注入消息历史
        if use_native:
            # 标准 function calling 格式：assistant message + tool messages
            assistant_msg = _build_native_assistant_message(clean_text, actionable_calls, complete_reasoning)
            messages.append(assistant_msg)
            for call_item, result_item in zip(actionable_calls, results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_item.get("_tool_call_id", ""),
                    "content": result_item.get("result", ""),
                })
        else:
            # 兼容期：旧格式 user message
            assistant_content = clean_text if clean_text else "(工具调用中)"
            messages.append({"role": "assistant", "content": assistant_content})
            tool_result_text = format_tool_results_for_llm(results)
            messages.append({"role": "user", "content": tool_result_text})

        # ★ 消息队列注入：在工具执行完毕、下一轮 LLM 调用前，注入排队消息
        # 合并到最后一条 user 消息中，避免连续多条 user 破坏角色交替
        try:
            from .message_queue import get_message_queue
            mq = get_message_queue()
            queued = mq.drain()
            if queued:
                inject_parts = []
                for qm in queued:
                    tag = f"[{qm.source}]" if qm.source != "user" else ""
                    inject_parts.append(f"{tag} {qm.content}".strip())
                inject_text = "\n\n".join(inject_parts)
                # 追加到最后一条 user 消息（即工具结果），保持角色交替
                messages[-1]["content"] += f"\n\n--- 排队消息 ---\n{inject_text}"
                logger.info(
                    f"[AgenticLoop] 注入 {len(queued)} 条排队消息: "
                    f"{[q.source for q in queued]}"
                )
                yield _format_sse_event(
                    "queued_messages",
                    {"count": len(queued), "sources": [q.source for q in queued]},
                )
        except Exception as e:
            logger.debug(f"[AgenticLoop] 消息队列注入跳过: {e}")

        # 9a. 连续失败达到阈值时提前终止，进入总结轮
        if consecutive_failures >= 2:
            logger.warning(f"[AgenticLoop] 连续 {consecutive_failures} 轮工具全部失败，提前终止循环")
            yield _format_sse_event("round_end", {"round": round_num, "has_more": True})
            needs_summary = True
            break

        # 发送本轮结束信号
        yield _format_sse_event("round_end", {"round": round_num, "has_more": True})

        t_round_elapsed = _time.monotonic() - t_round_start
        t_total_elapsed = _time.monotonic() - t_loop_start
        logger.info(f"[AgenticLoop] Round {round_num}: 本轮完成 {t_round_elapsed:.2f}s "
                    f"(LLM={t_llm_elapsed:.2f}s + 工具={t_tool_elapsed:.2f}s), "
                    f"总计 {t_total_elapsed:.2f}s，继续下一轮")

    else:
        # max_rounds 用尽
        needs_summary = True

    # 最终总结轮：强制 LLM 基于已有工具结果生成回复，不再允许工具调用
    if needs_summary:
        logger.warning(f"[AgenticLoop] 执行最终总结轮")

        # 总结轮前也检查压缩（多轮工具调用后 context 可能已经很大）
        try:
            from .context_compressor import compress_context
            compress_result = await compress_context(messages)
            if compress_result.compressed:
                messages[:] = compress_result.messages
            for sse_event in compress_result.sse_events:
                yield sse_event
        except Exception as e:
            logger.debug(f"[AgenticLoop] 总结轮压缩跳过: {e}")

        # 通知前端开始总结轮（重要：触发 api_server 重置 is_tool_event 标记）
        yield _format_sse_event("round_start", {"round": max_rounds + 1, "summary": True})

        # 注入总结指令
        messages.append({
            "role": "user",
            "content": (
                "[系统提示] 工具调用轮次已用尽。请根据以上所有工具返回结果，直接回答用户的问题。"
                "如果所有工具都失败了，请诚实告知用户当前无法完成该操作，并给出建议。"
                "不要再发起任何工具调用。"
            ),
        })

        # 最终总结轮：流式输出（不传 tools，禁止再发起工具调用）
        async for chunk in llm_service.stream_chat_with_context(messages, get_config().api.temperature,
                                                                 model_override=model_override,
                                                                 tools=None):
            yield chunk

        yield _format_sse_event("round_end", {"round": max_rounds + 1, "has_more": False})
