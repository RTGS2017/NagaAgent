#!/usr/bin/env python3
"""
上下文压缩模块

两种压缩场景：
1. **启动压缩**：每次新会话启动时，将上一个会话的历史消息压缩为摘要，
   注入 system prompt 的 <compress> 标签中。
2. **运行时压缩**：agentic loop 每轮开始前检查，当总 token 超过阈值时
   压缩早期消息，防止超长上下文导致 API 报错。

压缩后的摘要格式：
    以下是上次对话的压缩记录：
    <compress>
    {摘要文本}
    </compress>
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import litellm
from litellm import acompletion

from . import naga_auth
from system.config import get_config

logger = logging.getLogger("ContextCompressor")

# ── 常量 ──
TOKEN_THRESHOLD = 100_000       # 运行时压缩：总 token 超过此值触发
MAX_KEEP_LOOPS = 10             # 最多保留的最近 loop 数
MAX_KEEP_TOKENS = 10_000        # 保留区 token 上限
COMPRESS_MODEL = "gpt-4.1-nano"

COMPRESS_MARKER = "以下是上次对话的压缩记录："


def _load_summarize_prompt() -> str:
    """从 system/prompts/context_compress_prompt.txt 加载压缩提示词"""
    from system.config import get_prompt_manager
    prompt = get_prompt_manager()._load_prompt("context_compress_prompt")
    if not prompt:
        raise FileNotFoundError("context_compress_prompt.txt not found")
    return prompt


@dataclass
class CompressResult:
    """压缩结果"""
    messages: List[Dict]                        # 压缩后（或原始）的消息列表
    sse_events: List[str] = field(default_factory=list)  # 要转发给前端的 SSE 事件
    compressed: bool = False                    # 是否实际执行了压缩


# ── Token 计数 ──

def count_tokens(messages: List[Dict], model: str = "gpt-4") -> int:
    """计算消息列表的 token 数"""
    try:
        return litellm.token_counter(model=model, messages=messages)
    except Exception as e:
        total_chars = sum(len(_msg_text(m)) for m in messages)
        estimated = int(total_chars * 1.2)
        logger.debug(f"token_counter 失败，使用粗略估算 {estimated}: {e}")
        return estimated


def _msg_text(msg: Dict) -> str:
    """提取消息的纯文本（兼容多模态 content）"""
    content = msg.get("content", "")
    if isinstance(content, list):
        return "\n".join(
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        )
    return str(content)


# ── 启动压缩 ──

async def compress_for_startup(
    prev_messages: List[Dict],
    previous_compress: str = "",
) -> Optional[str]:
    """将上一个会话的消息 + 更早的压缩记录合并压缩为新的摘要。

    滚动继承：previous_compress 是上一个 session 存储的压缩结果，
    包含更早对话的累积上下文。新摘要会继承其中仍有效的信息。

    Args:
        prev_messages: 上一个会话的原始消息列表
        previous_compress: 上一个会话继承的压缩记录（可为空）

    Returns:
        压缩后的摘要文本，失败返回 None
    """
    if not prev_messages and not previous_compress:
        return None

    # 组装压缩输入：旧压缩记录 + 新对话
    parts = []
    if previous_compress:
        parts.append(f"=== 更早对话的压缩记录 ===\n{previous_compress}")
    if prev_messages:
        conversation_text = _format_messages_for_summary(prev_messages)
        parts.append(f"=== 最近一次对话的内容 ===\n{conversation_text}")

    full_text = "\n\n".join(parts)
    summary = await _generate_summary(full_text)
    if summary:
        logger.info(
            f"[启动压缩] 压缩完成: {len(prev_messages)} 条消息"
            f"{f' + {len(previous_compress)} 字旧摘要' if previous_compress else ''}"
            f" → {len(summary)} 字新摘要"
        )
    return summary


def build_compress_block(summary: str) -> str:
    """构建注入 system prompt 的 <compress> 文本块"""
    return f"\n\n{COMPRESS_MARKER}\n<compress>\n{summary}\n</compress>"


# ── Loop 切分 ──

def _split_into_loops(messages: List[Dict], start_idx: int) -> List[List[Dict]]:
    """将消息按 loop 切分。

    一个 loop = 一条 user 消息 + 后续所有非 user 消息（assistant / tool / system 等），
    直到下一条 user 消息。开头没有 user 的连续消息也归为一个 loop。
    """
    loops: List[List[Dict]] = []
    current: List[Dict] = []

    for msg in messages[start_idx:]:
        if msg.get("role") == "user":
            if current:
                loops.append(current)
            current = [msg]
        else:
            current.append(msg)

    if current:
        loops.append(current)

    return loops


def _select_recent_loops(loops: List[List[Dict]]) -> Tuple[List[List[Dict]], List[List[Dict]]]:
    """从末尾向前选取 loop，满足 loop 数 ≤ MAX_KEEP_LOOPS 且 token ≤ MAX_KEEP_TOKENS。

    Returns:
        (early_loops, recent_loops)
    """
    if not loops:
        return [], []

    kept: List[List[Dict]] = []
    kept_tokens = 0

    for loop in reversed(loops):
        if len(kept) >= MAX_KEEP_LOOPS:
            break
        loop_tokens = count_tokens(loop)
        if kept and kept_tokens + loop_tokens > MAX_KEEP_TOKENS:
            break
        kept.insert(0, loop)
        kept_tokens += loop_tokens

    # 至少保留最后 1 个 loop（当前用户消息所在的 loop）
    if not kept and loops:
        kept = [loops[-1]]

    split_point = len(loops) - len(kept)
    return loops[:split_point], loops[split_point:]


# ── SSE 格式化 ──

def _sse(chunk_type: str, **kwargs) -> str:
    """格式化一条 SSE 事件"""
    data = {"type": chunk_type, **kwargs}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 运行时压缩（agentic loop 每轮调用） ──

async def compress_context(messages: List[Dict]) -> CompressResult:
    """当消息 token 数超过阈值时压缩上下文。

    在 agentic loop 每轮开始前调用。

    Returns:
        CompressResult，包含压缩后的 messages 和要发给前端的 SSE 事件列表
    """
    # ── 1. 检查是否需要压缩 ──
    total_tokens = count_tokens(messages)
    if total_tokens <= TOKEN_THRESHOLD:
        logger.debug(f"[压缩] {total_tokens} tokens ≤ {TOKEN_THRESHOLD}，跳过")
        return CompressResult(messages=messages)

    events: List[str] = []
    events.append(_sse("compress_start",
                       text=f"上下文过长（{total_tokens:,} tokens），正在压缩历史消息…"))

    # ── 2. 分离 system prompt ──
    system_msg = messages[0] if messages[0]["role"] == "system" else None
    start_idx = 1 if system_msg else 0

    # ── 3. 按 loop 切分并选取保留区 ──
    all_loops = _split_into_loops(messages, start_idx)
    early_loops, recent_loops = _select_recent_loops(all_loops)

    if not early_loops:
        logger.info("[压缩] 没有可压缩的早期消息，跳过")
        events.append(_sse("compress_end", text="无需压缩，所有消息已在保留范围内"))
        return CompressResult(messages=messages, sse_events=events)

    early_messages = [msg for loop in early_loops for msg in loop]
    recent_messages = [msg for loop in recent_loops for msg in loop]

    events.append(_sse("compress_progress",
                       text=f"压缩 {len(early_loops)} 个对话轮次，保留最近 {len(recent_loops)} 轮…"))

    # ── 4. 调用 LLM 生成摘要 ──
    conversation_text = _format_messages_for_summary(early_messages)
    summary = await _generate_summary(conversation_text)

    if not summary:
        logger.warning("[压缩] 摘要生成失败，返回原始消息")
        events.append(_sse("compress_end", text="压缩失败，使用原始上下文"))
        return CompressResult(messages=messages, sse_events=events)

    # ── 5. 组装压缩后的消息：摘要写入 system prompt 的 <compress> 标签 ──
    compressed = []
    if system_msg:
        # 将摘要追加到 system prompt 内部
        sp_content = system_msg["content"]
        # 如果已有 <compress> 块，替换；否则追加
        if "<compress>" in sp_content and "</compress>" in sp_content:
            import re
            sp_content = re.sub(
                r"以下是上次对话的压缩记录：\s*<compress>[\s\S]*?</compress>",
                f"{COMPRESS_MARKER}\n<compress>\n{summary}\n</compress>",
                sp_content,
            )
        else:
            sp_content += build_compress_block(summary)
        compressed.append({"role": "system", "content": sp_content})
    else:
        # 无 system prompt 时作为独立 system 消息
        compressed.append({
            "role": "system",
            "content": f"{COMPRESS_MARKER}\n<compress>\n{summary}\n</compress>",
        })
    compressed.extend(recent_messages)

    compressed_tokens = count_tokens(compressed)
    saved = total_tokens - compressed_tokens

    events.append(_sse("compress_end",
                       text=f"压缩完成：{total_tokens:,} → {compressed_tokens:,} tokens（节省 {saved:,}）"))
    # 通知前端插入 info 标记（持久化到会话历史，但不计入 LLM 上下文）
    events.append(_sse("compress_info", text="【已压缩上下文】"))

    logger.info(
        f"[压缩] {total_tokens} → {compressed_tokens} tokens "
        f"(节省 {saved}, 压缩 {len(early_loops)} loops, 保留 {len(recent_loops)} loops)"
    )

    return CompressResult(messages=compressed, sse_events=events, compressed=True)


# ── 辅助函数 ──

def _format_messages_for_summary(messages: List[Dict]) -> str:
    """将消息列表格式化为摘要用的文本"""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = _msg_text(msg)
        if len(content) > 3000:
            content = content[:3000] + "…[截断]"
        role_label = {"user": "用户", "assistant": "助手", "system": "系统", "tool": "工具结果"}.get(role, role)
        lines.append(f"【{role_label}】{content}")
    return "\n\n".join(lines)


def _get_compress_llm_params() -> Dict:
    """获取压缩模型的 LLM 调用参数"""
    if naga_auth.is_authenticated():
        token = naga_auth.get_access_token()
        return {
            "api_key": token,
            "api_base": naga_auth.NAGA_MODEL_URL + "/",
            "extra_body": {"user_token": token},
        }
    cfg = get_config()
    params: Dict = {"api_key": cfg.api.api_key}
    if cfg.api.base_url:
        params["api_base"] = cfg.api.base_url.rstrip("/") + "/"
    return params


def _get_compress_model_name() -> str:
    """获取压缩模型名称（LiteLLM 格式）"""
    if naga_auth.is_authenticated():
        return f"openai/{COMPRESS_MODEL}"
    base_url = (get_config().api.base_url or "").lower()
    if "openai.com" in base_url:
        return COMPRESS_MODEL
    return f"openai/{COMPRESS_MODEL}"


async def _generate_summary(conversation_text: str) -> Optional[str]:
    """调用轻量 LLM 生成对话摘要"""
    try:
        response = await acompletion(
            model=_get_compress_model_name(),
            messages=[
                {"role": "system", "content": _load_summarize_prompt()},
                {"role": "user", "content": conversation_text},
            ],
            temperature=0.3,
            max_tokens=5500,
            timeout=60,
            **_get_compress_llm_params(),
        )
        summary = response.choices[0].message.content or ""
        logger.info(f"[压缩] 摘要生成成功，{len(summary)} 字")
        return summary.strip()
    except Exception as e:
        logger.error(f"[压缩] 摘要生成失败: {e}")
        return None
