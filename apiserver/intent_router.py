#!/usr/bin/env python3
"""
Nano 意图路由器

在主 LLM 调用前，用 gpt-4.1-nano 做一次极快的意图分类，
判断用户消息需要哪些工具，然后只注入相关工具的文档到主 prompt。
闲聊场景跳过全部工具指令，prompt 大幅缩短。

失败回退：如果 nano 调用失败 → 返回 None，主流程回退到全量注入。
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from litellm import acompletion

from . import naga_auth
from system.config import get_config

logger = logging.getLogger("IntentRouter")

# 路由模型
ROUTER_MODEL = "gpt-4.1-nano"

# 内置工具名称（非 MCP、非 Skill）
BUILTIN_TOOLS = {"openclaw", "tool", "live2d"}


@dataclass
class RouteResult:
    """路由结果"""
    needed_builtins: List[str] = field(default_factory=list)  # ["openclaw"] or []
    needed_mcp: List[str] = field(default_factory=list)       # ["game_guide"] or []
    needed_skills: List[str] = field(default_factory=list)    # ["web-search"] or []
    search_query: Optional[str] = None  # 搜索关键词（openclaw:关键词 格式提取）

    @property
    def needs_tools(self) -> bool:
        return bool(self.needed_builtins or self.needed_mcp or self.needed_skills)

    @property
    def needs_pre_search(self) -> bool:
        return bool(self.search_query)


# ── 工具列表缓存 ──

_cached_tool_list: Optional[str] = None


def invalidate_tool_list_cache():
    """当 skill 或 MCP 服务变更时调用，清除缓存"""
    global _cached_tool_list
    _cached_tool_list = None


def _build_tool_list() -> str:
    """构建路由 prompt 中的工具列表（缓存）"""
    global _cached_tool_list
    if _cached_tool_list is not None:
        return _cached_tool_list

    lines = []

    # 内置工具
    lines.append("## 系统内置")
    lines.append("- openclaw: 联网搜索、网页浏览、代码执行、文件操作、定时任务等（任何需要联网、查资料、搜索的场景都需要）")
    lines.append("- live2d: 虚拟形象表情动作")
    lines.append("")

    # MCP 服务
    lines.append("## MCP服务")
    try:
        from mcpserver.mcp_registry import MANIFEST_CACHE, auto_register_mcp
        auto_register_mcp()
        for name, manifest in MANIFEST_CACHE.items():
            desc = manifest.get("description", "")
            # 取描述的第一句
            short_desc = desc.split("。")[0] if desc else name
            lines.append(f"- {name}: {short_desc}")
    except Exception:
        lines.append("- (MCP服务未加载)")
    lines.append("")

    # Skills
    lines.append("## 技能")
    try:
        from system.skill_manager import get_skill_manager
        for meta in get_skill_manager().get_all_metadata():
            lines.append(f"- {meta.name}: {meta.description}")
    except Exception:
        pass

    _cached_tool_list = "\n".join(lines)
    return _cached_tool_list


# ── 路由 prompt ──

ROUTER_SYSTEM_PROMPT = """根据用户最新消息，判断需要调用哪些工具。用 {{工具名}} 格式输出，多个工具用空格分隔。不需要工具时输出 {{none}}。
如果需要联网搜索，使用 {{openclaw:搜索关键词}} 格式，附带精简的搜索关键词。

{tool_list}"""

# few-shot 示例（user/assistant 对）
_FEW_SHOT_EXAMPLES = [
    {"role": "user", "content": "帮我搜一下今天黄金价格"},
    {"role": "assistant", "content": "{{openclaw:今天黄金价格}}"},
    {"role": "user", "content": "你好呀"},
    {"role": "assistant", "content": "{{none}}"},
    {"role": "user", "content": "这关怎么打"},
    {"role": "assistant", "content": "{{game_guide}}"},
    {"role": "user", "content": "明日方舟初雪有什么技能"},
    {"role": "assistant", "content": "{{game_guide}}"},
    {"role": "user", "content": "银灰三技能专三DPS多少"},
    {"role": "assistant", "content": "{{game_guide}}"},
    {"role": "user", "content": "崩铁花火怎么配队"},
    {"role": "assistant", "content": "{{game_guide}}"},
    {"role": "user", "content": "帮我看看屏幕上有什么"},
    {"role": "assistant", "content": "{{screen_vision}}"},
    {"role": "user", "content": "搜一下最近的新闻然后写个总结"},
    {"role": "assistant", "content": "{{openclaw:最近新闻}}"},
    {"role": "user", "content": "帮我关一下语音"},
    {"role": "assistant", "content": "{{naga_control}}"},
    {"role": "user", "content": "你现在用的什么模型"},
    {"role": "assistant", "content": "{{naga_control}}"},
    {"role": "user", "content": "把温度调到0.5"},
    {"role": "assistant", "content": "{{naga_control}}"},
    {"role": "user", "content": "播放一首音乐"},
    {"role": "assistant", "content": "{{naga_control}}"},
]


def _build_router_messages(messages: List[Dict], user_msg: str) -> List[Dict]:
    """构建给 nano 的消息列表：system + few-shot + 最近对话 + 用户最新消息"""
    system_content = ROUTER_SYSTEM_PROMPT.format(tool_list=_build_tool_list())

    # 取最近几轮对话作为上下文（跳过 system 消息）
    recent = []
    non_system = [m for m in messages if m.get("role") != "system"]
    # 取最后 4 条（约 2 轮对话）
    for m in non_system[-4:]:
        content = m.get("content", "")
        if isinstance(content, list):
            # 多模态消息，提取文本部分
            content = " ".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        # 截断过长内容
        if len(content) > 200:
            content = content[:200] + "…"
        recent.append({"role": m["role"], "content": content})

    # 确保最后一条是用户消息
    if not recent or recent[-1].get("role") != "user":
        user_content = user_msg[:200] + "…" if len(user_msg) > 200 else user_msg
        recent.append({"role": "user", "content": user_content})

    return [{"role": "system", "content": system_content}] + _FEW_SHOT_EXAMPLES + recent


# ── LLM 调用参数（复用 context_compressor 的模式） ──

def _get_router_llm_params() -> Dict:
    """获取路由模型的 LLM 调用参数"""
    if naga_auth.should_use_model_gateway():
        token = naga_auth.get_access_token()
        return {
            "api_key": token,
            "api_base": naga_auth.NAGA_MODEL_URL + "/",
            "extra_body": {"user_token": token},
        }
    cfg = get_config()
    params: Dict = {"api_key": cfg.api.api_key}
    if cfg.api.api_format == "anthropic":
        if cfg.api.base_url and "anthropic.com" not in cfg.api.base_url:
            params["api_base"] = cfg.api.base_url.rstrip("/")
    elif cfg.api.base_url:
        params["api_base"] = cfg.api.base_url.rstrip("/") + "/"
    return params


def _get_router_model_name() -> str:
    """获取路由模型名称（LiteLLM 格式）"""
    if naga_auth.should_use_model_gateway():
        return f"openai/{ROUTER_MODEL}"
    cfg = get_config()
    if cfg.api.api_format == "anthropic":
        return f"anthropic/{ROUTER_MODEL}"
    base_url = (cfg.api.base_url or "").lower()
    if "openai.com" in base_url:
        return ROUTER_MODEL
    return f"openai/{ROUTER_MODEL}"


# ── 解析输出 ──

# 从 {tool_name} 或 {tool_name:参数} 格式中提取工具名和可选参数
_TOOL_TAG_RE = re.compile(r"\{(\w+)(?::([^}]+))?\}")


def _parse_router_output(output: str) -> RouteResult:
    """解析 nano 的输出，用正则从 {xxx} 或 {xxx:参数} 中提取工具名"""
    result = RouteResult()

    # 优先用正则提取 {xxx} / {xxx:param} 标签
    names = []
    search_query = None
    for m in _TOOL_TAG_RE.finditer(output):
        name = m.group(1).lower()
        param = m.group(2)  # 可能是 None
        names.append(name)
        if name == "openclaw" and param:
            search_query = param.strip()

    # 兜底：如果没提取到任何标签，按行分割裸文本
    if not names:
        names = []
        for line in output.strip().split("\n"):
            name = line.strip().lower().lstrip("-•*").strip()
            if "→" in name:
                name = name.split("→")[-1].strip()
            if name:
                names.append(name)

    if not names or names == ["none"]:
        return result

    # 获取已知 MCP 服务名和技能名用于匹配
    known_mcp = set()
    try:
        from mcpserver.mcp_registry import MANIFEST_CACHE, auto_register_mcp
        auto_register_mcp()
        known_mcp = set(MANIFEST_CACHE.keys())
    except Exception:
        pass

    known_skills = set()
    try:
        from system.skill_manager import get_skill_manager
        known_skills = {m.name.lower() for m in get_skill_manager().get_all_metadata()}
    except Exception:
        pass

    for name in names:
        if name == "none":
            continue

        if name in BUILTIN_TOOLS:
            result.needed_builtins.append(name)
        elif name in {k.lower() for k in known_mcp}:
            # 恢复原始大小写
            for k in known_mcp:
                if k.lower() == name:
                    result.needed_mcp.append(k)
                    break
        elif name in known_skills:
            # 恢复原始大小写
            from system.skill_manager import get_skill_manager
            for m in get_skill_manager().get_all_metadata():
                if m.name.lower() == name:
                    result.needed_skills.append(m.name)
                    break
        else:
            # 未知工具名，可能是 nano 幻觉，忽略
            logger.debug(f"[IntentRouter] 忽略未知工具名: {name}")

    result.search_query = search_query
    return result


# ── 主入口 ──

async def classify_intent(
    messages: List[Dict],
    user_msg: str,
) -> Optional[RouteResult]:
    """
    用 nano 模型快速分类用户意图。

    Args:
        messages: 当前对话历史（含 system prompt）
        user_msg: 用户最新消息原文

    Returns:
        RouteResult 或 None（失败时回退到全量注入）
    """
    try:
        router_messages = _build_router_messages(messages, user_msg)

        response = await acompletion(
            model=_get_router_model_name(),
            messages=router_messages,
            temperature=0,
            max_tokens=80,
            **_get_router_llm_params(),
        )

        output = response.choices[0].message.content or ""
        result = _parse_router_output(output)

        tools_str = 'none' if not result.needs_tools else ', '.join(result.needed_builtins + result.needed_mcp + result.needed_skills)
        search_str = f" | search_query=\"{result.search_query}\"" if result.search_query else ""
        logger.info(
            f"[IntentRouter] 用户: \"{user_msg[:50]}\" → {tools_str}{search_str}"
        )

        return result

    except Exception as e:
        logger.warning(f"[IntentRouter] 分类失败，回退到全量注入: {e}")
        return None
