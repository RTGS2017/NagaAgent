"""工具状态、消息队列、前端轮询、主动消息、WebSocket 路由"""

import json
import logging
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from system.config import build_system_prompt, build_context_supplement
from apiserver.message_manager import message_manager
from apiserver.llm_service import get_llm_service
from apiserver.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ 全局队列状态 ============

# Web前端工具状态轮询存储
_tool_status_store: Dict[str, Dict] = {"current": {"message": "", "visible": False}}

# Web前端 AgentServer 回复存储（轮询获取）
_clawdbot_replies: list = []

# Web前端 Live2D 动作队列（轮询获取）
_live2d_actions: list = []

# Web前端 音乐控制队列（轮询获取）
_music_commands: list = []


# ============ 辅助函数 ============


def _emit_tool_status_to_ui(status_text: str, auto_hide_ms: int = 0) -> None:
    """更新工具状态存储，前端通过轮询获取"""
    _tool_status_store["current"] = {"message": status_text, "visible": True}


def _hide_tool_status_in_ui() -> None:
    """隐藏工具状态，前端通过轮询获取"""
    _tool_status_store["current"] = {"message": "", "visible": False}


def _format_tool_payload(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(value)


def _build_tool_result_blocks(results: list[Dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in results:
        service_name = str(item.get("service_name") or "mcp")
        tool_name = str(item.get("tool_name") or "").strip()
        ok = str(item.get("status") or "").lower() in {"ok", "success"}
        marker = "✅" if ok else "❌"
        label = f"{service_name}: {tool_name}" if tool_name else service_name
        result = item.get("result") if ok else item.get("error", item.get("result", ""))
        blocks.append(f"```tool-result\n{marker} {label}\n{_format_tool_payload(result).strip()}\n```")
    return "\n\n".join(blocks)


async def _update_proactive_activity_silent():
    """异步更新用户活动时间（静默失败，不影响主流程）"""
    try:
        import httpx
        from system.config import get_server_port

        agent_port = get_server_port("agent_server")
        activity_url = f"http://127.0.0.1:{agent_port}/proactive_vision/activity"

        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(activity_url)
    except Exception:
        pass  # 静默失败，不影响主对话流程


async def _notify_ui_refresh(session_id: str, response_text: str):
    """通知UI刷新会话历史"""
    try:
        import httpx

        # 通过UI通知接口直接显示AI回复
        ui_notification_payload = {
            "session_id": session_id,
            "action": "show_tool_ai_response",
            "ai_response": response_text,
        }

        from system.config import get_server_port

        api_url = f"http://localhost:{get_server_port('api_server')}/ui_notification"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(api_url, json=ui_notification_payload)
            if response.status_code == 200:
                logger.info(f"[UI通知] AI回复显示通知发送成功: {session_id}")
            else:
                logger.error(f"[UI通知] AI回复显示通知失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI通知] 通知UI刷新失败: {e}")


# ============ 前端轮询端点 ============


@router.get("/tool_status")
async def get_tool_status():
    """获取当前工具调用状态（供Web前端轮询）"""
    return _tool_status_store.get("current", {"message": "", "visible": False})


@router.get("/clawdbot/replies")
async def get_clawdbot_replies():
    """获取并清空 AgentServer 待显示回复（供Web前端轮询）"""
    replies = list(_clawdbot_replies)
    _clawdbot_replies.clear()
    return {"replies": replies}


@router.get("/live2d/actions")
async def get_live2d_actions():
    """获取并清空 Live2D 动作队列（供Web前端轮询）"""
    actions = list(_live2d_actions)
    _live2d_actions.clear()
    return {"actions": actions}


@router.get("/music/commands")
async def get_music_commands():
    """获取并清空音乐控制指令队列（供Web前端轮询）"""
    commands = list(_music_commands)
    _music_commands.clear()
    return {"commands": commands}


# ============ 消息队列 ============


@router.post("/queue/push")
async def queue_push(payload: Dict[str, Any]):
    """接收外部消息并入队或设置临时屏幕消息

    source: "screen_monitor" | "heartbeat"
    对话进行中 → 入队等待注入
    对话未进行 → 直接推送 UI（心跳通过 clawdbot_replies，屏幕通过临时槽）
    """
    content = payload.get("content", "")
    source = payload.get("source", "unknown")
    metadata = payload.get("metadata", {})

    if not content:
        return {"status": "empty"}

    from apiserver.message_queue import get_message_queue
    mq = get_message_queue()

    # 屏幕监测：同时设置临时消息槽（无论对话是否活跃）
    if source == "screen_monitor":
        mq.set_ephemeral_screen(content, metadata)

    # 如果对话正在进行，入队等待注入
    if mq.is_conversation_active():
        mq.push(content, source, metadata)
        return {"status": "queued"}
    else:
        # 对话未进行：心跳消息直接推送 UI
        if source == "heartbeat":
            _clawdbot_replies.append(content)
        return {"status": "direct"}


# ============ 工具通知 & 回调 ============


@router.post("/tool_notification")
async def tool_notification(payload: Dict[str, Any]):
    """接收工具调用状态通知，只显示工具调用状态，不显示结果"""
    try:
        session_id = payload.get("session_id")
        tool_calls = payload.get("tool_calls", [])
        message = payload.get("message", "")
        stage = payload.get("stage", "")
        auto_hide_ms_raw = payload.get("auto_hide_ms", 0)

        try:
            auto_hide_ms = int(auto_hide_ms_raw)
        except (TypeError, ValueError):
            auto_hide_ms = 0

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        # 记录工具调用状态（不处理结果，结果由tool_result_callback处理）
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name", "未知工具")
            service_name = tool_call.get("service_name", "未知服务")
            status = tool_call.get("status", "starting")
            logger.info(f"工具调用状态: {tool_name} ({service_name}) - {status}")

        display_message = message
        if not display_message:
            if stage == "detecting":
                display_message = "正在检测工具调用"
            elif stage == "executing":
                display_message = f"检测到{len(tool_calls)}个工具调用，执行中"
            elif stage == "none":
                display_message = "未检测到工具调用"

        if stage == "hide":
            _hide_tool_status_in_ui()
        elif display_message:
            _emit_tool_status_to_ui(display_message, auto_hide_ms)

        return {
            "success": True,
            "message": "工具调用状态通知已接收",
            "tool_calls": tool_calls,
            "display_message": display_message,
            "stage": stage,
            "auto_hide_ms": auto_hide_ms,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"工具调用通知处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.post("/tool_result_callback")
async def tool_result_callback(payload: Dict[str, Any]):
    """接收MCP工具执行结果回调，让主AI基于原始对话和工具结果重新生成回复"""
    try:
        session_id = payload.get("session_id")
        task_id = payload.get("task_id")
        result = payload.get("result", {})
        success = payload.get("success", False)

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        _emit_tool_status_to_ui("生成工具回调", 0)

        logger.info(f"[工具回调] 开始处理工具回调，会话: {session_id}, 任务ID: {task_id}")
        logger.info(f"[工具回调] 回调内容: {result}")

        # 获取工具执行结果
        tool_result = result.get("result", "执行成功") if success else result.get("error", "未知错误")
        logger.info(f"[工具回调] 工具执行结果: {tool_result}")

        # 获取原始对话的最后一条用户消息（触发工具调用的消息）
        session_messages = message_manager.get_messages(session_id)
        original_user_message = ""
        for msg in reversed(session_messages):
            if msg.get("role") == "user":
                original_user_message = msg.get("content", "")
                break

        # 构建包含工具结果的用户消息
        enhanced_message = f"{original_user_message}\n\n[工具执行结果]: {tool_result}"
        logger.info(f"[工具回调] 构建增强消息: {enhanced_message[:200]}...")

        # 构建对话风格提示词和消息
        system_prompt = build_system_prompt()
        messages = message_manager.build_conversation_messages(
            session_id=session_id, system_prompt=system_prompt, current_message=enhanced_message
        )
        # 追加附加知识到末尾
        supplement = build_context_supplement(include_skills=True, include_tool_instructions=True)
        messages.append({"role": "system", "content": supplement})

        logger.info("[工具回调] 开始生成工具后回复...")

        # 使用LLM服务基于原始对话和工具结果重新生成回复
        try:
            llm_service = get_llm_service()
            response_text = await llm_service.chat_with_context(messages, temperature=0.7)
            logger.info(f"[工具回调] 工具后回复生成成功，内容: {response_text[:200]}...")
        except Exception as e:
            logger.error(f"[工具回调] 调用LLM服务失败: {e}")
            response_text = f"处理工具结果时出错: {str(e)}"

        # 只保存AI回复到历史记录（用户消息已在正常对话流程中保存）
        message_manager.add_message(session_id, "assistant", response_text)
        logger.info("[工具回调] AI回复已保存到历史")

        # 保存对话日志到文件
        message_manager.save_conversation_log(original_user_message, response_text, dev_mode=False)
        logger.info("[工具回调] 对话日志已保存")

        # 通过UI通知接口将AI回复发送给UI
        logger.info("[工具回调] 开始发送AI回复到UI...")
        await _notify_ui_refresh(session_id, response_text)
        _hide_tool_status_in_ui()

        logger.info("[工具回调] 工具结果处理完成，回复已发送到UI")

        return {
            "success": True,
            "message": "工具结果已通过主AI处理并返回给UI",
            "response": response_text,
            "task_id": task_id,
            "session_id": session_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        _hide_tool_status_in_ui()
        logger.error(f"[工具回调] 工具结果回调处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.post("/tool_result")
async def tool_result(payload: Dict[str, Any]):
    """接收工具执行结果并显示在UI上"""
    try:
        session_id = payload.get("session_id")
        result = payload.get("result", "")
        notification_type = payload.get("type", "")
        ai_response = payload.get("ai_response", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"工具执行结果: {result}")

        # 如果是工具完成后的AI回复，存储到ClawdBot回复队列供前端轮询
        if notification_type == "tool_completed_with_ai_response" and ai_response:
            _clawdbot_replies.append(ai_response)
            logger.info(f"[UI] AI回复已存储到队列，长度: {len(ai_response)}")

        return {"success": True, "message": "工具结果已接收", "result": result, "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理工具结果失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@router.post("/save_tool_conversation")
async def save_tool_conversation(payload: Dict[str, Any]):
    """保存工具对话历史"""
    try:
        session_id = payload.get("session_id")
        user_message = payload.get("user_message", "")
        assistant_response = payload.get("assistant_response", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"[保存工具对话] 开始保存工具对话历史，会话: {session_id}")

        # 保存用户消息（工具执行结果）
        if user_message:
            message_manager.add_message(session_id, "user", user_message)

        # 保存AI回复
        if assistant_response:
            message_manager.add_message(session_id, "assistant", assistant_response)

        logger.info(f"[保存工具对话] 工具对话历史已保存，会话: {session_id}")

        return {"success": True, "message": "工具对话历史已保存", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[保存工具对话] 保存工具对话历史失败: {e}")
        raise HTTPException(500, f"保存失败: {str(e)}")


@router.post("/ui_notification")
async def ui_notification(payload: Dict[str, Any]):
    """UI通知接口 - 用于直接控制UI显示"""
    try:
        session_id = payload.get("session_id")
        action = payload.get("action", "")
        ai_response = payload.get("ai_response", "")
        status_text = payload.get("status_text", "")
        auto_hide_ms_raw = payload.get("auto_hide_ms", 0)

        try:
            auto_hide_ms = int(auto_hide_ms_raw)
        except (TypeError, ValueError):
            auto_hide_ms = 0

        logger.info(f"UI通知: {action}, 会话: {session_id}")

        # ── 不需要 session_id 的控制类动作 ──

        # 处理 Live2D 动作（动画表情）
        if action == "live2d_action":
            action_name = payload.get("action_name", "")
            if action_name:
                _live2d_actions.append(action_name)
                logger.info(f"[UI通知] Live2D 动作已入队: {action_name}")
                return {"success": True, "message": f"Live2D 动作 {action_name} 已入队"}

        # 处理 Live2D 开关（naga_control 运行时暂停/恢复）
        if action == "live2d_toggle":
            enabled = payload.get("enabled", True)
            logger.info(f"[UI通知] Live2D 开关: {'显示' if enabled else '隐藏'}")
            return {"success": True, "message": f"Live2D {'已恢复' if enabled else '已暂停'}"}

        if action == "hide_tool_status":
            _hide_tool_status_in_ui()
            return {"success": True, "message": "工具状态已隐藏"}

        # 处理音乐控制
        if action == "music_control":
            music_action = payload.get("music_action", "play")
            cmd: Dict[str, Any] = {"action": music_action}
            track = payload.get("track")
            if track:
                cmd["track"] = track
            _music_commands.append(cmd)
            logger.info(f"[UI通知] 音乐指令已入队: {cmd}")
            return {"success": True, "message": f"音乐指令 {music_action} 已入队"}

        # 处理通用通知（naga_control send_notification）
        if action == "show_notification":
            msg = payload.get("message", "")
            ntype = payload.get("type", "info")
            logger.info(f"[UI通知] 通知: [{ntype}] {msg}")
            return {"success": True, "message": "通知已接收"}

        if action == "show_mcp_result":
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise HTTPException(400, "results 必须是数组")
            result_blocks = _build_tool_result_blocks([r for r in results if isinstance(r, dict)])
            if result_blocks:
                _clawdbot_replies.append(result_blocks)
                logger.info(f"[UI通知] MCP结果已存储到队列，数量: {len(results)}")
                return {"success": True, "message": "MCP结果已存储"}
            return {"success": True, "message": "MCP结果为空"}

        # ── 以下动作需要 session_id ──

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        # 处理显示工具AI回复的动作
        if action == "show_tool_ai_response" and ai_response:
            _clawdbot_replies.append(ai_response)
            logger.info(f"[UI通知] 工具AI回复已存储到队列，长度: {len(ai_response)}")
            return {"success": True, "message": "AI回复已存储"}

        # 处理显示 AgentServer 回复的动作
        if action == "show_clawdbot_response" and ai_response:
            _clawdbot_replies.append(ai_response)
            logger.info(f"[UI通知] AgentServer 回复已存储到队列，长度: {len(ai_response)}")
            return {"success": True, "message": "AgentServer 回复已存储"}

        if action == "show_tool_status" and status_text:
            _emit_tool_status_to_ui(status_text, auto_hide_ms)
            return {"success": True, "message": "工具状态已显示"}

        return {"success": True, "message": "UI通知已处理"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理UI通知失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


# ============ Proactive Vision Integration ============


@router.post("/proactive_message")
async def receive_proactive_message(payload: Dict[str, Any]):
    """
    接收来自ProactiveVision的主动消息

    请求体:
    - message: 主动消息内容
    - source: 消息来源（如"ProactiveVision:游戏关卡提醒"）
    - timestamp: 触发时间戳

    Returns:
        处理状态
    """
    try:
        message = payload.get("message", "")
        source = payload.get("source", "ProactiveVision")
        timestamp = payload.get("timestamp", time.time())
        session_id = payload.get("session_id")

        if not message:
            raise HTTPException(400, "message 不能为空")

        logger.info(f"[ProactiveMessage] 收到主动消息: {message[:50]}... (来源: {source})")

        if not session_id:
            logger.warning("[ProactiveMessage] 未指定 session_id，将自动选择最近活跃会话")
            recent_session_ids = [
                sid for sid, session in message_manager.sessions.items()
                if session.get("messages") and not session.get("temporary")
            ]
            if recent_session_ids:
                recent_session_ids.sort(
                    key=lambda sid: message_manager.sessions[sid].get("last_activity", ""),
                    reverse=True,
                )
                session_id = recent_session_ids[0]
            else:
                session_id = message_manager.create_session()

        # 构建通知数据
        notification_data = {
            "type": "proactive_message",
            "content": message,
            "source": source,
            "timestamp": timestamp,
            "session_id": session_id,
        }

        # 确保会话存在再写入消息
        message_manager.create_session(session_id)

        ws_manager = get_websocket_manager()

        # 持久化到当前会话
        message_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=f"[主动提醒 - {source}]\n{message}",
        )

        pushed = await ws_manager.send_proactive_message(message, source, session_id=session_id)

        logger.info(f"[ProactiveMessage] 主动消息已处理: {session_id}, pushed={pushed}")

        return {
            "status": "ok",
            "message": "主动消息已接收",
            "session_id": session_id,
            "data": notification_data,
            "pushed": pushed,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ProactiveMessage] 处理主动消息失败: {e}", exc_info=True)
        raise HTTPException(500, f"处理失败: {e}")


# ============ WebSocket 实时通信 ============


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str = None):
    """
    WebSocket连接端点

    参数:
    - session_id: 可选，绑定到特定会话

    用法:
    - 前端: const ws = new WebSocket('ws://localhost:8000/ws?session_id=xxx')
    - 接收主动消息、实时通知等
    """
    from apiserver.websocket_manager import get_websocket_manager

    ws_manager = get_websocket_manager()
    await ws_manager.connect(websocket, session_id)

    try:
        while True:
            # 接收客户端消息（心跳包等）
            data = await websocket.receive_text()

            # 可以处理客户端发来的消息
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] 客户端断开连接: session={session_id}")
    except Exception as e:
        logger.error(f"[WebSocket] 连接异常: {e}")
    finally:
        await ws_manager.disconnect(websocket, session_id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """获取WebSocket连接统计"""
    from apiserver.websocket_manager import get_websocket_manager

    ws_manager = get_websocket_manager()
    stats = ws_manager.get_stats()

    return {
        "success": True,
        "stats": stats,
    }


@router.post("/ws/broadcast")
async def websocket_broadcast(payload: Dict[str, Any]):
    """
    通过WebSocket广播消息（内部接口）

    请求体:
    - type: 消息类型
    - content: 消息内容
    - source: 消息来源
    - timestamp: 时间戳
    """
    from apiserver.websocket_manager import get_websocket_manager

    ws_manager = get_websocket_manager()
    sent_count = await ws_manager.broadcast(payload)

    return {
        "success": True,
        "sent_count": sent_count,
        "message": f"已推送到{sent_count}个WebSocket连接",
    }
