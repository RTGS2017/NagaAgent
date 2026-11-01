"""核心对话路由（/chat, /chat/stream）"""

import asyncio
import logging
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

from pydantic import BaseModel

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from system.config import (
    build_context_supplement,
    build_system_prompt,
    get_config,
    get_data_dir,
    strip_prompt_comment_lines,
)
from system.character_bundle import is_legacy_character_identity
from apiserver.agent_directory import (
    BUILTIN_NAGA_AGENT_ID,
    NAGA_CORE_ENGINES,
    builtin_naga_descriptor,
    format_agent_directory_text,
    list_agent_descriptors,
    normalize_agent_engine,
    resolve_agent_descriptor,
)
from apiserver import naga_auth
from apiserver.message_manager import message_manager
from apiserver.llm_service import get_llm_service
from apiserver.response_util import extract_message
from apiserver.telemetry import emit_telemetry
from apiserver.api_server import (
    ChatRequest,
    ChatResponse,
    _vlm_sessions,
    _save_conversation_and_logs,
    _notify_conversation_event,
    _is_voice_runtime_paused,
    _call_agentserver,
)
from apiserver.routes.tools import _update_proactive_activity_silent

logger = logging.getLogger(__name__)

router = APIRouter()


@dataclass
class _AgentPromptContext:
    agent_id: str
    name: str
    engine: str
    character_template: str | None
    system_prompt: str
    agent_soul_prompt: str
    agent_notebook_prompt: str
    agent_long_term_memory_prompt: str
    skills_prompt: str
    available_mcp_tools_text: str
    skill_manager: object | None


class AgentRelayRequest(BaseModel):
    message: str
    target_agent_id: str | None = None
    target_agent_name: str | None = None
    source_agent_id: str | None = None
    source_agent_name: str | None = None
    purpose: str | None = None
    context: str | None = None
    timeout_seconds: int = 120
    session_id: str | None = None
    wait_for_reply: bool = True


def _load_agent_manifest_record(agent_id: str) -> dict | None:
    manifest_path = get_data_dir() / "agents" / "agents.json"
    if not manifest_path.exists():
        return None
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("agents", []):
            if item.get("id") == agent_id:
                item = dict(item)
                item["engine"] = normalize_agent_engine(item.get("engine"))
                return item
    except Exception as e:
        logger.warning(f"[NagaCore] 读取干员 manifest 失败: {e}")
    return None


def _resolve_agent_display_name(agent_id: str | None, fallback: str | None = None) -> str:
    descriptor = resolve_agent_descriptor(agent_id=agent_id, include_builtin=True) if agent_id else None
    if descriptor:
        return descriptor.name
    return (fallback or "").strip() or "娜迦"


def _build_relay_session_key(source_agent_id: str | None, target_agent_id: str) -> str:
    source_key = (source_agent_id or "user").strip() or "user"
    return f"relay:{source_key}:{target_agent_id}"


def _compose_relay_message(request: AgentRelayRequest, target_name: str) -> str:
    source_name = _resolve_agent_display_name(request.source_agent_id, request.source_agent_name)
    parts = [
        "[跨干员通信]",
        f"目标干员：{target_name}",
        f"来源干员：{source_name}",
    ]
    if request.purpose:
        parts.append(f"任务目的：{request.purpose.strip()}")
    if request.context:
        parts.append("补充上下文：\n" + request.context.strip())
    parts.append(
        "请直接完成下述请求，并给出可被上游干员直接转述的答复。"
        "优先给结论、步骤、风险点，不要寒暄。"
    )
    parts.append("请求内容：\n" + request.message.strip())
    return "\n\n".join(parts)


async def _relay_to_naga_core(target_agent_id: str | None, relay_message: str, session_id: str) -> dict:
    response = await chat(
        ChatRequest(
            message=relay_message,
            session_id=session_id,
            agent_id=target_agent_id,
            temporary=False,
        )
    )
    return {
        "success": response.status == "success",
        "reply": response.response,
        "session_id": response.session_id,
        "reasoning_content": response.reasoning_content,
    }


async def _relay_to_openclaw(target_agent_id: str, relay_message: str, session_key: str, timeout_seconds: int) -> dict:
    runtime_resp = await _call_agentserver(
        "GET",
        f"/openclaw/agents/{target_agent_id}/runtime",
        params={"wake": "true"},
        timeout_seconds=min(timeout_seconds, 45),
    )
    runtime = runtime_resp.get("runtime", {}) if isinstance(runtime_resp, dict) else {}
    if not runtime.get("running") or not runtime.get("port"):
        return {
            "success": False,
            "reply": "",
            "error": "目标 OpenClaw 干员未能成功唤醒",
            "session_key": session_key,
            "runtime": runtime,
        }

    logger.info(
        "[AgentRelay] 目标 OpenClaw 已解析: id=%s port=%s wake=%s",
        target_agent_id,
        runtime.get("port"),
        runtime.get("woken"),
    )

    response = await _call_agentserver(
        "POST",
        f"/openclaw/agents/{target_agent_id}/send",
        json_body={
            "message": relay_message,
            "timeout_seconds": timeout_seconds,
            "session_key": session_key,
            "name": "AgentRelay",
        },
        timeout_seconds=timeout_seconds + 30,
    )
    replies = response.get("replies") or []
    reply = "\n".join(replies).strip() if replies else str(response.get("reply") or "").strip()
    return {
        "success": bool(response.get("success", False)),
        "reply": reply,
        "error": response.get("error"),
        "session_key": session_key,
        "runtime": runtime,
    }


@router.get("/agents/directory")
async def get_agent_directory():
    return {
        "status": "success",
        "agents": [item.to_dict() for item in list_agent_descriptors(include_builtin=True)],
    }


@router.post("/agents/relay")
async def relay_agent_message(request: AgentRelayRequest):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    target = resolve_agent_descriptor(
        agent_id=request.target_agent_id,
        agent_name=request.target_agent_name,
        include_builtin=True,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="目标干员不存在，请先列出通讯录后再指定目标")

    if request.source_agent_id and request.source_agent_id == target.id:
        raise HTTPException(status_code=400, detail="不能把消息转发给自己")

    relay_message = _compose_relay_message(request, target.name)
    relay_session = request.session_id or _build_relay_session_key(request.source_agent_id, target.id)
    emit_telemetry(
        "agent_relay_request",
        {
            "target_engine": target.engine,
            "wait_for_reply": request.wait_for_reply,
            "timeout_seconds": request.timeout_seconds,
            "has_context": bool(request.context),
            "has_source_agent": bool(request.source_agent_id),
        },
        source="apiserver",
        session_id=relay_session,
        agent_id=target.id,
        trace_id=f"relay:{relay_session}",
    )

    if target.id == BUILTIN_NAGA_AGENT_ID or target.engine in NAGA_CORE_ENGINES:
        result = await _relay_to_naga_core(
            None if target.id == BUILTIN_NAGA_AGENT_ID else target.id,
            relay_message,
            relay_session,
        )
    else:
        result = await _relay_to_openclaw(
            target.id,
            relay_message,
            relay_session,
            max(5, min(request.timeout_seconds, 600)),
        )

    emit_telemetry(
        "agent_relay_success" if result.get("success") else "agent_relay_fail",
        {
            "target_engine": target.engine,
            "runtime": result.get("runtime"),
            "error": result.get("error"),
        },
        source="apiserver",
        session_id=relay_session,
        agent_id=target.id,
        trace_id=f"relay:{relay_session}",
    )

    return {
        "status": "success" if result.get("success") else "error",
        "success": bool(result.get("success")),
        "target": target.to_dict(),
        "source": {
            "agent_id": request.source_agent_id,
            "agent_name": _resolve_agent_display_name(request.source_agent_id, request.source_agent_name),
        },
        "reply": result.get("reply", ""),
        "session_id": result.get("session_id"),
        "session_key": result.get("session_key"),
        "error": result.get("error"),
        "target_runtime": result.get("runtime"),
    }


def _read_text_snippet(path: Path, max_chars: int = 4000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = strip_prompt_comment_lines(path.read_text(encoding="utf-8")).strip()
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[已截断]"


def _load_memory_section(memory_dir: Path) -> str:
    if not memory_dir.exists():
        return ""
    files = [
        path for path in memory_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    ]
    if not files:
        return ""
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    chunks: list[str] = []
    for memory_file in files[:3]:
        content = _read_text_snippet(memory_file, max_chars=1200)
        if not content:
            continue
        chunks.append(f"### {memory_file.name}\n{content}")
    if not chunks:
        return ""
    return "\n\n".join(chunks)


def _build_agent_prompt_context(agent_id: str | None) -> _AgentPromptContext | None:
    if not agent_id:
        return None

    record = _load_agent_manifest_record(agent_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"NagaCore 干员不存在: {agent_id}")

    engine = normalize_agent_engine(record.get("engine"))
    if engine not in NAGA_CORE_ENGINES:
        raise HTTPException(status_code=400, detail=f"干员 [{record.get('name') or agent_id}] 不是 NagaCore 引擎")

    from system.skill_manager import SkillManager

    agent_dir = get_data_dir() / "agents" / agent_id
    identity_path = agent_dir / "IDENTITY.md"
    soul_path = agent_dir / "SOUL.md"
    notes_path = agent_dir / "notes" / "CLAUDE.md"
    private_skills_dir = agent_dir / "skills"
    public_skills_dir = get_data_dir() / "skills" / "public"
    project_skills_dir = Path(__file__).resolve().parents[2] / "skills"

    identity_override = _read_text_snippet(identity_path, max_chars=16000)
    if identity_override and record.get("character_template"):
        try:
            if is_legacy_character_identity(identity_override, record.get("character_template")):
                identity_override = ""
        except Exception as e:
            logger.warning(f"[NagaCore] 判断旧版角色模板 [{record.get('character_template')}] 失败: {e}")

    try:
        system_prompt = build_system_prompt(
            record.get("character_template"),
            identity_override=identity_override,
        )
    except Exception as e:
        logger.warning(f"[NagaCore] 装配 tier1 提示词失败 [{record.get('character_template')}] : {e}")
        system_prompt = identity_override or build_system_prompt()

    soul_text = _read_text_snippet(soul_path, max_chars=5000)
    notes_text = _read_text_snippet(notes_path, max_chars=4000)
    memory_section = _load_memory_section(agent_dir / "memory")

    skill_manager = SkillManager(skills_dirs=[project_skills_dir, public_skills_dir, private_skills_dir])
    skills_prompt = skill_manager.generate_skills_prompt()
    available_mcp_tools_text = ""
    try:
        from mcpserver.mcp_registry import auto_register_mcp
        from mcpserver.mcp_manager import get_mcp_manager

        auto_register_mcp()
        available_mcp_tools_text = get_mcp_manager().format_available_services_for_agent(agent_id) or "（暂无MCP服务注册）"
    except Exception:
        available_mcp_tools_text = "（MCP服务未启动）"

    return _AgentPromptContext(
        agent_id=agent_id,
        name=record.get("name") or agent_id,
        engine=engine,
        character_template=record.get("character_template"),
        system_prompt=system_prompt,
        agent_soul_prompt=soul_text,
        agent_notebook_prompt=notes_text,
        agent_long_term_memory_prompt=memory_section,
        skills_prompt=skills_prompt,
        available_mcp_tools_text=available_mcp_tools_text,
        skill_manager=skill_manager,
    )


def _build_multi_agent_context_section(agent_ctx: _AgentPromptContext | None) -> str:
    current = builtin_naga_descriptor()
    if agent_ctx is not None:
        current.name = agent_ctx.name
        current.id = agent_ctx.agent_id
        current.engine = agent_ctx.engine
        current.character_template = agent_ctx.character_template

    directory_text = format_agent_directory_text()
    return (
        "## 当前身份与协作边界\n\n"
        f"你当前身份：{current.name}\n"
        f"当前干员ID：{current.id}\n"
        f"当前引擎：{current.engine}\n\n"
        "规则：\n"
        "- 你只能代表当前干员自己思考和回答\n"
        "- 其他现有干员不会自动参与\n"
        "- 如果任务需要其他现有干员参与，必须调用 `agent_relay`\n"
        "- 如果用户明确点名其他干员、要求多人分工、要求不同人设分别给意见，先确认通讯录，再转发\n"
        "- `openclaw` Agent 模式是临时复杂执行器，不等于通讯录干员\n\n"
        "## 当前可联系干员\n\n"
        "以下是当前通讯录中的干员：\n"
        f"{directory_text}\n\n"
        "使用建议：\n"
        "- 名字或ID不确定时，先调用 `agents_list`\n"
        "- 需要多人协作时，可以多次调用 `agent_relay`\n"
        "- 如果当前干员自己就能完成任务，优先自己直接调用工具\n"
    )


def _supports_function_calling(model_name: str) -> bool:
    """检测模型是否支持原生 function calling"""
    model_lower = model_name.lower()
    # 支持 function calling 的品牌
    supported = ["gpt", "claude", "gemini", "grok"]
    # 不支持的品牌
    unsupported = ["deepseek", "qwen", "llama", "mistral", "yi-"]

    if any(s in model_lower for s in unsupported):
        return False
    if any(s in model_lower for s in supported):
        return True
    # 默认不使用（保守策略）
    return False


def _parse_memory_result(mem_result: dict) -> str:
    """解析 NagaMemory 返回结果，兼容 quintuples / memories / answer 三种格式"""
    if not mem_result.get("success"):
        return ""

    # 调试：打印返回的数据结构
    logger.debug(f"[RAG] mem_result keys: {list(mem_result.keys())}")
    if "memories" in mem_result:
        logger.debug(f"[RAG] memories count: {len(mem_result.get('memories', []))}")
    if "quintuples" in mem_result:
        logger.debug(f"[RAG] quintuples count: {len(mem_result.get('quintuples', []))}")
    if "answer" in mem_result:
        logger.debug(f"[RAG] answer length: {len(mem_result.get('answer', ''))}")

    # 格式1: quintuples 列表（旧版本 / 本地 GRAG）
    quints = mem_result.get("quintuples") or []

    # 格式2: memories 列表（远程 NagaMemory，每条含五元组字段）
    memories = mem_result.get("memories") or []
    if memories and not quints:
        for m in memories:
            # 新格式：直接包含 subject/relation/object 字段
            if isinstance(m, dict) and "subject" in m:
                quints.append((
                    m.get("subject", ""),
                    m.get("subject_type", ""),
                    m.get("relation", ""),
                    m.get("object", ""),
                    m.get("object_type", "")
                ))
            # 旧格式：包含 quintuples 子字段
            elif isinstance(m, dict):
                mq = m.get("quintuples") or []
                quints.extend(mq)

    if quints:
        mem_lines = []
        for q in quints:
            if isinstance(q, (list, tuple)) and len(q) >= 5:
                mem_lines.append(f"- {q[0]}({q[1]}) —[{q[2]}]→ {q[3]}({q[4]})")
            elif isinstance(q, dict):
                mem_lines.append(
                    f"- {q.get('subject', '')}({q.get('subject_type', '')}) "
                    f"—[{q.get('predicate', '')}]→ "
                    f"{q.get('object', '')}({q.get('object_type', '')})"
                )
        if mem_lines:
            logger.info(f"[RAG] 召回 {len(mem_lines)} 条记忆注入上下文")
            return (
                "\n\n## 相关记忆\n\n以下是从知识图谱中检索到的与用户问题相关的记忆，"
                "请参考这些信息回答：\n" + "\n".join(mem_lines)
            )

    # 格式3: answer 文本（语义搜索直接返回）
    answer = mem_result.get("answer")
    if answer:
        logger.info("[RAG] 召回记忆（answer 模式）注入上下文")
        return f"\n\n## 相关记忆\n\n以下是从知识图谱中检索到的与用户问题相关的记忆：\n{answer}"

    return ""


# ============ 内部辅助函数 ============


async def _trigger_chat_stream_no_intent(session_id: str, response_text: str):
    """触发聊天流式响应但不触发意图分析 - 发送纯粹的AI回复到UI"""
    try:
        logger.info(f"[UI发送] 开始发送AI回复到UI，会话: {session_id}")
        logger.info(f"[UI发送] 发送内容: {response_text[:200]}...")

        # 直接调用现有的流式对话接口，但跳过意图分析
        import httpx

        # 构建请求数据 - 使用纯粹的AI回复内容，并跳过意图分析
        chat_request = {
            "message": response_text,  # 直接使用AI回复内容，不加标记
            "stream": True,
            "session_id": session_id,
            "disable_tts": False,
            "return_audio": False,

        }

        # 调用现有的流式对话接口
        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/chat/stream"

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", api_url, json=chat_request) as response:
                if response.status_code == 200:
                    # 处理流式响应，包括TTS切割
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            # 这里可以进一步处理流式响应
                            # 或者直接让UI处理流式响应
                            pass

                    logger.info(f"[UI发送] AI回复已成功发送到UI: {session_id}")
                    logger.info("[UI发送] 成功显示到UI")
                else:
                    logger.error(f"[UI发送] 调用流式对话接口失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI发送] 触发聊天流式响应失败: {e}")


async def _send_ai_response_directly(session_id: str, response_text: str):
    """直接发送AI回复到UI"""
    try:
        import httpx

        # 使用非流式接口发送AI回复
        chat_request = {
            "message": f"[工具结果] {response_text}",  # 添加标记让UI知道这是工具结果
            "stream": False,
            "session_id": session_id,
            "disable_tts": False,
            "return_audio": False,

        }

        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/chat"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=chat_request)
            if response.status_code == 200:
                logger.info(f"[直接发送] AI回复已通过非流式接口发送到UI: {session_id}")
            else:
                logger.error(f"[直接发送] 非流式接口发送失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[直接发送] 直接发送AI回复失败: {e}")


# ============ 对话端点 ============


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """普通对话接口 - 仅处理纯文本对话"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    t_started = time.monotonic()
    session_id: str | None = None
    try:
        # 更新ProactiveVision的用户活动时间
        asyncio.create_task(_update_proactive_activity_silent())

        agent_ctx = _build_agent_prompt_context(request.agent_id)

        # 技能调度前缀：让 LLM 明确知道当前处于技能模式
        user_message = request.message
        if request.skill:
            skill_labels = "，".join(f"【{s.strip()}】" for s in request.skill.split(",") if s.strip())
            user_message = f"调度技能{skill_labels}：{user_message}"
        session_id = message_manager.create_session(request.session_id, temporary=request.temporary)
        emit_telemetry(
            "chat_send",
            {
                "mode": "non_stream",
                "temporary": request.temporary,
                "has_images": bool(request.images),
                "skill_selected": bool(request.skill),
                "skill_count": len([s for s in (request.skill or "").split(",") if s.strip()]),
            },
            source="apiserver",
            session_id=session_id,
            agent_id=request.agent_id,
            trace_id=f"chat:{session_id}",
        )

        # 系统提示词 = 纯人格
        system_prompt = agent_ctx.system_prompt if agent_ctx else build_system_prompt()

        # 先构建对话消息（人格在 messages[0]）
        effective_message = user_message
        messages = message_manager.build_conversation_messages(
            session_id=session_id, system_prompt=system_prompt, current_message=effective_message
        )

        # RAG 记忆召回
        rag_section = ""

        async def _query_rag():
            nonlocal rag_section
            try:
                from summer_memory.memory_client import get_remote_memory_client

                remote_mem = get_remote_memory_client()
                if remote_mem:
                    mem_result = await remote_mem.query_memory(question=request.message, limit=5)
                    rag_section = _parse_memory_result(mem_result)
            except Exception as e:
                logger.warning(f"[RAG] 记忆召回失败: {e}")

        await _query_rag()

        # 检测模型是否支持原生 function calling
        current_model = get_config().api.model
        supports_fc = _supports_function_calling(current_model)

        # 构建附加知识
        supplement = build_context_supplement(
            include_skills=True,
            include_tool_instructions=not supports_fc,  # 不支持原生FC时注入文本指令
            skill_name=request.skill,
            rag_section=rag_section,
            multi_agent_context_section=_build_multi_agent_context_section(agent_ctx),
            skills_prompt_override=agent_ctx.skills_prompt if agent_ctx else None,
            skill_instructions_override=(
                agent_ctx.skill_manager.get_skill_instructions(request.skill)
                if agent_ctx and request.skill and agent_ctx.skill_manager
                else None
            ),
            available_mcp_tools_override=agent_ctx.available_mcp_tools_text if agent_ctx else None,
            agent_soul_prompt=agent_ctx.agent_soul_prompt if agent_ctx else "",
            agent_notebook_prompt=agent_ctx.agent_notebook_prompt if agent_ctx else "",
            agent_long_term_memory_prompt=(
                agent_ctx.agent_long_term_memory_prompt if agent_ctx else ""
            ),
        )
        messages.append({"role": "system", "content": supplement})

        # 使用整合后的LLM服务（支持 reasoning_content）
        llm_service = get_llm_service()
        llm_response = await llm_service.chat_with_context_and_reasoning(messages, get_config().api.temperature)

        # 处理完成
        # 统一保存对话历史与日志
        _save_conversation_and_logs(session_id, user_message, llm_response.content)
        emit_telemetry(
            "chat_finish",
            {
                "mode": "non_stream",
                "duration_ms": int((time.monotonic() - t_started) * 1000),
                "response_chars": len(llm_response.content or ""),
                "reasoning_chars": len(llm_response.reasoning_content or ""),
            },
            source="apiserver",
            session_id=session_id,
            agent_id=request.agent_id,
            trace_id=f"chat:{session_id}",
        )

        return ChatResponse(
            response=extract_message(llm_response.content) if llm_response.content else llm_response.content,
            reasoning_content=llm_response.reasoning_content,
            session_id=session_id,
            status="success",
        )
    except Exception as e:
        print(f"对话处理错误: {e}")
        traceback.print_exc()
        emit_telemetry(
            "chat_error",
            {
                "mode": "non_stream",
                "duration_ms": int((time.monotonic() - t_started) * 1000),
                "error": e,
            },
            source="apiserver",
            session_id=session_id,
            agent_id=request.agent_id,
            trace_id=f"chat:{session_id}" if session_id else None,
        )
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 - 使用 agentic tool loop 实现多轮工具调用"""

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    # 技能调度前缀：让 LLM 明确知道当前处于技能模式
    user_message = request.message
    if request.skill:
        skill_labels = "，".join(f"【{s.strip()}】" for s in request.skill.split(",") if s.strip())
        user_message = f"调度技能{skill_labels}：{user_message}"

    async def generate_response() -> AsyncGenerator[str, None]:
        complete_text = ""  # 用于累积最终轮的完整文本（供 return_audio 模式使用）
        _mq_initialized = False  # 标记消息队列是否已设置 active
        session_id: str | None = None
        first_response_sent = False
        try:
            import time as _time
            t_api_start = _time.monotonic()
            agent_ctx = _build_agent_prompt_context(request.agent_id)

            # 获取或创建会话ID
            session_id = message_manager.create_session(request.session_id, temporary=request.temporary)
            emit_telemetry(
                "chat_send",
                {
                    "mode": "stream",
                    "temporary": request.temporary,
                    "has_images": bool(request.images),
                    "skill_selected": bool(request.skill),
                    "skill_count": len([s for s in (request.skill or "").split(",") if s.strip()]),
                },
                source="apiserver",
                session_id=session_id,
                agent_id=request.agent_id,
                trace_id=f"chat:{session_id}",
            )

            # ★ 通知对话开始 + 设置消息队列状态
            from apiserver.message_queue import get_message_queue
            mq = get_message_queue()
            mq.set_conversation_active(True)
            _mq_initialized = True
            asyncio.create_task(_notify_conversation_event("started"))

            # 发送会话ID信息
            yield f"data: session_id: {session_id}\n\n"

            # 系统提示词 = 纯人格
            system_prompt = agent_ctx.system_prompt if agent_ctx else build_system_prompt()

            # 用户消息使用带技能前缀的版本
            effective_message = user_message

            # ★ 检查是否有临时屏幕消息需要提升为正式上下文
            ephemeral = mq.promote_ephemeral_screen()
            if ephemeral:
                message_manager.add_message(session_id, "user", f"[屏幕观察] {ephemeral.content}")
                logger.info("[ChatStream] 提升临时屏幕消息为正式上下文")

            # 先构建对话消息（人格在 messages[0]）
            messages = message_manager.build_conversation_messages(
                session_id=session_id, system_prompt=system_prompt, current_message=effective_message
            )

            # ====== RAG 记忆召回 ======
            yield 'data: {"type":"status","text":"回忆中..."}\n\n'
            rag_section = ""

            async def _query_rag_stream():
                nonlocal rag_section
                try:
                    from summer_memory.memory_client import get_remote_memory_client

                    remote_mem = get_remote_memory_client()
                    if not remote_mem:
                        logger.info("[RAG] 未登录或无可用 token，跳过远程记忆召回")
                        return

                    # 构建包含历史对话的查询上下文（前2轮 + 当前消息）
                    context_parts = []
                    recent_messages = [m for m in messages if m.get("role") in ("user", "assistant")][-4:]
                    if recent_messages:
                        context_parts.append("近期对话：")
                        for msg in recent_messages:
                            role_label = "用户" if msg["role"] == "user" else "助手"
                            content = msg.get("content", "")
                            if isinstance(content, str):
                                context_parts.append(f"- {role_label}: {content[:100]}")
                        context_parts.append(f"\n当前问题: {request.message}")
                        query_text = "\n".join(context_parts)
                    else:
                        query_text = request.message

                    logger.info(f"[RAG] 开始查询记忆: question='{request.message[:50]}...'")
                    mem_result = await remote_mem.query_memory(question=query_text, limit=5)
                    logger.debug(f"[RAG] 记忆服务器响应: success={mem_result.get('success')}")
                    logger.debug(f"[RAG] 完整响应: {mem_result}")

                    rag_section = _parse_memory_result(mem_result)
                    if not rag_section:
                        logger.info("[RAG] 未召回到相关记忆（结果为空）")
                except Exception as e:
                    logger.warning(f"[RAG] 记忆召回失败: {e}")

            await _query_rag_stream()

            # 检测模型是否支持原生 function calling
            current_model = get_config().api.model
            supports_fc = _supports_function_calling(current_model)
            logger.info(f"[ChatStream] 模型 {current_model} function calling 支持: {supports_fc}")

            # 构建附加知识
            yield 'data: {"type":"status","text":"组织上下文"}\n\n'
            supplement = build_context_supplement(
                include_skills=True,
                include_tool_instructions=not supports_fc,  # 不支持原生FC时注入文本指令
                skill_name=request.skill,
                rag_section=rag_section,
                multi_agent_context_section=_build_multi_agent_context_section(agent_ctx),
                skills_prompt_override=agent_ctx.skills_prompt if agent_ctx else None,
                skill_instructions_override=(
                    agent_ctx.skill_manager.get_skill_instructions(request.skill)
                    if agent_ctx and request.skill and agent_ctx.skill_manager
                    else None
                ),
                available_mcp_tools_override=agent_ctx.available_mcp_tools_text if agent_ctx else None,
                agent_soul_prompt=agent_ctx.agent_soul_prompt if agent_ctx else "",
                agent_notebook_prompt=agent_ctx.agent_notebook_prompt if agent_ctx else "",
                agent_long_term_memory_prompt=(
                    agent_ctx.agent_long_term_memory_prompt if agent_ctx else ""
                ),
            )
            messages.append({"role": "system", "content": supplement})

            # 获取工具 schemas（仅在支持原生 function calling 时传递）
            tools = None
            if supports_fc:
                from apiserver.tool_schemas import get_all_tool_schemas
                tools = get_all_tool_schemas(agent_id=request.agent_id)
                logger.info(f"[ChatStream] 使用原生 function calling，工具数: {len(tools) if tools else 0}")
            else:
                logger.info("[ChatStream] 使用文本解析模式（模型不支持原生 function calling）")

            # 如果携带截屏图片，将最后一条 user 消息改为多模态格式（OpenAI vision 兼容）
            if request.images:
                # 找到最后一条 user 消息的索引（跳过末尾的 system supplement）
                user_idx = None
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get("role") == "user":
                        user_idx = i
                        break
                if user_idx is not None:
                    last_user_msg = messages[user_idx]
                    content_parts = [{"type": "text", "text": last_user_msg["content"]}]
                    for img_data in request.images:
                        content_parts.append({"type": "image_url", "image_url": {"url": img_data}})
                    messages[user_idx] = {
                        "role": "user",
                        "content": content_parts,
                    }

            # 初始化语音集成（根据voice_mode和return_audio决定）
            voice_integration = None

            should_enable_tts = (
                get_config().system.voice_enabled
                and not request.return_audio  # return_audio时不启用实时TTS
                and get_config().voice_realtime.voice_mode != "hybrid"
                and not request.disable_tts
                and not _is_voice_runtime_paused()
            )

            if should_enable_tts:
                try:
                    from voice.output.voice_integration import get_voice_integration

                    voice_integration = get_voice_integration()
                    logger.info(
                        f"[API Server] 实时语音集成已启用 (return_audio={request.return_audio}, voice_mode={get_config().voice_realtime.voice_mode})"
                    )
                except Exception as e:
                    print(f"语音集成初始化失败: {e}")
            else:
                if request.return_audio:
                    logger.info("[API Server] return_audio模式，将在最后生成完整音频")
                elif get_config().voice_realtime.voice_mode == "hybrid" and not request.return_audio:
                    logger.info("[API Server] 混合模式下且未请求音频，不处理TTS")
                elif request.disable_tts:
                    logger.info("[API Server] 客户端禁用了TTS (disable_tts=True)")

            # 初始化流式文本切割器（仅用于TTS处理）
            tool_extractor = None
            try:
                from apiserver.streaming_tool_extractor import StreamingToolCallExtractor

                tool_extractor = StreamingToolCallExtractor()
                if voice_integration and not request.return_audio:
                    tool_extractor.set_callbacks(
                        on_text_chunk=None,
                        voice_integration=voice_integration,
                    )
            except Exception as e:
                print(f"流式文本切割器初始化失败: {e}")

            # ====== Agentic Tool Loop ======
            yield 'data: {"type":"status","text":"娜迦打字中..."}\n\n'
            from apiserver.agentic_tool_loop import run_agentic_loop

            t_prepare_elapsed = _time.monotonic() - t_api_start
            logger.info(f"[ChatStream] 预处理完成: {t_prepare_elapsed:.2f}s "
                        f"(消息构建+RAG+启动压缩+supplement+voice初始化)")

            # 如果本次携带图片，标记此会话为 VLM 会话
            if request.images:
                _vlm_sessions.add(session_id)

            # 如果当前会话曾发送过图片，持续使用视觉模型
            model_override = None
            use_vlm = session_id in _vlm_sessions
            cc = get_config().computer_control
            if use_vlm and cc.enabled and (cc.api_key or naga_auth.should_use_model_gateway()):
                model_override = {
                    "model": cc.model,
                    "api_base": cc.model_url,
                    "api_key": cc.api_key,
                    "provider": "gemini" if "gemini" in (cc.model or "").lower() else get_config().api.provider,
                }
                logger.info(f"[API Server] VLM 会话，使用视觉模型: {cc.model}")

            complete_reasoning = ""
            # 记录每轮的content，用于在每轮结束时完成TTS处理
            current_round_text = ""
            is_tool_event = False  # 标记当前是否在处理工具事件（不送TTS）
            was_compressed = False  # 运行时是否执行过上下文压缩（用于保存 info 标记）
            # 累积所有轮次内容（含工具结果），用于持久化完整对话
            all_rounds_content = ""
            had_tool_events = False

            async for chunk in run_agentic_loop(
                messages,
                session_id,
                model_override=model_override,
                tools=tools,
                source_agent_id=request.agent_id,
            ):
                if chunk.startswith("data: "):
                    try:
                        import json as json_module

                        data_str = chunk[6:].strip()
                        if data_str and data_str != "[DONE]":
                            chunk_data = json_module.loads(data_str)
                            chunk_type = chunk_data.get("type", "content")
                            chunk_text = chunk_data.get("text", "")

                            if chunk_type == "content":
                                # 累积本轮内容（TTS + 保存）
                                current_round_text += chunk_text
                                if request.return_audio:
                                    complete_text += chunk_text
                                if chunk_text and not first_response_sent:
                                    first_response_sent = True
                                    emit_telemetry(
                                        "chat_first_token",
                                        {
                                            "mode": "stream",
                                            "first_response_ms": int((_time.monotonic() - t_api_start) * 1000),
                                            "kind": "content",
                                        },
                                        source="apiserver",
                                        session_id=session_id,
                                        agent_id=request.agent_id,
                                        trace_id=f"chat:{session_id}",
                                    )
                                # TTS：每轮的正常content都发送（不含工具内容）
                                if tool_extractor and not is_tool_event:
                                    asyncio.create_task(tool_extractor.process_text_chunk(chunk_text))
                            elif chunk_type == "reasoning":
                                complete_reasoning += chunk_text
                                if chunk_text and not first_response_sent:
                                    first_response_sent = True
                                    emit_telemetry(
                                        "chat_first_token",
                                        {
                                            "mode": "stream",
                                            "first_response_ms": int((_time.monotonic() - t_api_start) * 1000),
                                            "kind": "reasoning",
                                        },
                                        source="apiserver",
                                        session_id=session_id,
                                        agent_id=request.agent_id,
                                        trace_id=f"chat:{session_id}",
                                    )
                            elif chunk_type == "round_end":
                                # 每轮结束时，完成TTS处理并重置
                                has_more = chunk_data.get("has_more", False)
                                if has_more:
                                    # 中间轮：累积本轮内容到持久化缓冲
                                    all_rounds_content += current_round_text
                                if has_more and tool_extractor and not request.return_audio:
                                    # 中间轮结束，flush TTS缓冲
                                    try:
                                        await tool_extractor.finish_processing()
                                    except Exception as e:
                                        logger.debug(f"中间轮TTS flush失败: {e}")
                                    if voice_integration:
                                        try:
                                            threading.Thread(
                                                target=voice_integration.finish_processing,
                                                daemon=True,
                                            ).start()
                                        except Exception:
                                            pass
                                    # 重新初始化 tool_extractor 给下一轮使用
                                    try:
                                        from apiserver.streaming_tool_extractor import StreamingToolCallExtractor
                                        tool_extractor = StreamingToolCallExtractor()
                                        if voice_integration and not request.return_audio:
                                            tool_extractor.set_callbacks(
                                                on_text_chunk=None,
                                                voice_integration=voice_integration,
                                            )
                                    except Exception:
                                        pass
                                current_round_text = ""
                            elif chunk_type == "tool_calls":
                                is_tool_event = True
                                had_tool_events = True
                                if chunk_data.get("calls") and not first_response_sent:
                                    first_response_sent = True
                                    emit_telemetry(
                                        "chat_first_token",
                                        {
                                            "mode": "stream",
                                            "first_response_ms": int((_time.monotonic() - t_api_start) * 1000),
                                            "kind": "tool_calls",
                                        },
                                        source="apiserver",
                                        session_id=session_id,
                                        agent_id=request.agent_id,
                                        trace_id=f"chat:{session_id}",
                                    )
                                for call in chunk_data.get("calls", []):
                                    svc = call.get("service_name") or call.get("agentType") or "tool"
                                    tn = call.get("tool_name") or ""
                                    label = f"{svc}: {tn}" if tn else svc
                                    payload = json_module.dumps(call, ensure_ascii=False, indent=2)
                                    all_rounds_content += f"\n```tool-call\n{label}\n{payload}\n```\n"
                            elif chunk_type == "tool_results":
                                is_tool_event = True
                                # 将工具结果格式化为 tool-result 代码块，用于持久化
                                had_tool_events = True
                                for r in chunk_data.get("results", []):
                                    st = "\u2705" if r.get("status") == "success" else "\u274c"
                                    svc = r.get("service_name", "unknown")
                                    tn = r.get("tool_name", "")
                                    label = f"{svc}: {tn}" if tn else svc
                                    rt = (r.get("result", "") or "").strip()
                                    all_rounds_content += f"\n```tool-result\n{st} {label}\n{rt}\n```\n"
                            elif chunk_type == "round_start":
                                # 新一轮开始，重置工具事件标记
                                is_tool_event = False
                            elif chunk_type == "compress_info":
                                # 运行时压缩完成，标记后续需要保存 info 消息
                                was_compressed = True

                            # 透传所有 chunk 给前端（content/reasoning/tool events）
                            yield chunk
                            continue
                    except Exception as e:
                        logger.error(f"[API Server] 流式数据解析错误: {e}")

                yield chunk

            # ====== 流式处理完成 ======

            # V19: 如果请求返回音频，在这里生成并返回音频URL
            if request.return_audio and complete_text:
                try:
                    logger.info(f"[API Server V19] 生成音频，文本长度: {len(complete_text)}")

                    from voice.tts_wrapper import generate_speech_safe

                    tts_voice = get_config().voice_realtime.tts_voice or "zh-CN-XiaoyiNeural"
                    audio_file = generate_speech_safe(
                        text=complete_text, voice=tts_voice, response_format="mp3", speed=1.0
                    )

                    try:
                        from voice.output.voice_integration import get_voice_integration

                        voice_integration = get_voice_integration()
                        voice_integration.receive_audio_url(audio_file)
                        logger.info(f"[API Server V19] 音频已直接播放: {audio_file}")
                    except Exception as e:
                        logger.error(f"[API Server V19] 音频播放失败: {e}")
                        yield f"data: audio_url: {audio_file}\n\n"

                except Exception as e:
                    logger.error(f"[API Server V19] 音频生成失败: {e}")
                    traceback.print_exc()

            # 完成流式文本切割器处理（最终轮）
            if tool_extractor and not request.return_audio:
                try:
                    await tool_extractor.finish_processing()
                except Exception as e:
                    print(f"流式文本切割器完成处理错误: {e}")

            # 完成语音处理（最终轮）
            if voice_integration and not request.return_audio:
                try:
                    threading.Thread(
                        target=voice_integration.finish_processing,
                        daemon=True,
                    ).start()
                except Exception as e:
                    print(f"语音集成完成处理错误: {e}")

            # 获取完整文本用于保存
            complete_response = ""
            if tool_extractor:
                try:
                    complete_response = tool_extractor.get_complete_text()
                except Exception as e:
                    print(f"获取完整响应文本失败: {e}")
            elif request.return_audio:
                complete_response = complete_text

            # fallback: 如果 tool_extractor 没有累积到文本，使用最后一轮的 current_round_text
            if not complete_response and current_round_text:
                complete_response = current_round_text

            # 如果有工具事件，将所有轮次内容（含工具结果块）拼接为完整响应
            if had_tool_events:
                # 追加最后一轮内容（最终 LLM 回复）
                final_text = complete_response or current_round_text
                all_rounds_content += final_text
                complete_response = all_rounds_content.strip()

            # 统一保存对话历史与日志
            _save_conversation_and_logs(session_id, user_message, complete_response)
            emit_telemetry(
                "chat_finish",
                {
                    "mode": "stream",
                    "duration_ms": int((_time.monotonic() - t_api_start) * 1000),
                    "response_chars": len(complete_response or ""),
                    "reasoning_chars": len(complete_reasoning or ""),
                    "had_tool_events": had_tool_events,
                },
                source="apiserver",
                session_id=session_id,
                agent_id=request.agent_id,
                trace_id=f"chat:{session_id}",
            )

            # ★ 通知对话结束 + 设置消息队列状态
            mq.set_conversation_active(False)
            asyncio.create_task(_notify_conversation_event("ended"))

            # 运行时压缩成功时，在会话末尾追加 info 标记
            # 该标记持久化到磁盘，下次启动用于判断上一个会话是否已被压缩
            if was_compressed:
                message_manager.add_message(session_id, "info", "【已压缩上下文】")

            # [DONE] 信号已由 llm_service.stream_chat_with_context 发送，无需重复

        except Exception as e:
            print(f"流式对话处理错误: {e}")
            traceback.print_exc()
            emit_telemetry(
                "chat_error",
                {
                    "mode": "stream",
                    "error": e,
                },
                source="apiserver",
                session_id=session_id,
                agent_id=request.agent_id,
                trace_id=f"chat:{session_id}" if session_id else None,
            )
            yield f"data: error:{str(e)}\n\n"
        finally:
            # ★ 确保对话结束事件一定触发，即使异常/客户端断开
            if _mq_initialized:
                try:
                    from apiserver.message_queue import get_message_queue
                    _mq = get_message_queue()
                    if _mq.is_conversation_active():
                        _mq.set_conversation_active(False)
                        asyncio.create_task(_notify_conversation_event("ended"))
                except Exception:
                    pass

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        },
    )
