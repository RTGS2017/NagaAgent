#!/usr/bin/env python3
"""
NagaAgent API服务器
提供RESTful API接口访问NagaAgent功能
"""

import asyncio
import json
import sys
import traceback
import os
import logging
import uuid
import time
import threading
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, AsyncGenerator, Any

# 在导入其他模块前先设置HTTP库日志级别
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

# 创建logger实例
logger = logging.getLogger(__name__)

from nagaagent_core.api import uvicorn
from nagaagent_core.api import FastAPI, HTTPException, Request, UploadFile, File, Form
from nagaagent_core.api import CORSMiddleware
from nagaagent_core.api import StreamingResponse
from nagaagent_core.api import StaticFiles
from pydantic import BaseModel
from nagaagent_core.core import aiohttp
import shutil
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 流式文本处理模块（仅用于TTS）
from .message_manager import message_manager  # 导入统一的消息管理器

from .llm_service import get_llm_service  # 导入LLM服务

# 导入配置系统
try:
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.config import get_prompt  # 导入提示词仓库
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.config import get_prompt  # 导入提示词仓库
from ui.utils.response_util import extract_message  # 导入消息提取工具

# 对话核心功能已集成到apiserver

# 统一后台意图分析触发函数 - 已整合到message_manager
def _trigger_background_analysis(session_id: str):
    """统一触发后台意图分析 - 委托给message_manager"""
    message_manager.trigger_background_analysis(session_id)

# 统一保存对话与日志函数 - 已整合到message_manager
def _save_conversation_and_logs(session_id: str, user_message: str, assistant_response: str):
    """统一保存对话历史与日志 - 委托给message_manager"""
    message_manager.save_conversation_and_logs(session_id, user_message, assistant_response)

# 回调工厂类已移除 - 功能已整合到streaming_tool_extractor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        print("[INFO] 正在初始化API服务器...")
        # 对话核心功能已集成到apiserver
        print("[SUCCESS] API服务器初始化完成")
        yield
    except Exception as e:
        print(f"[ERROR] API服务器初始化失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 正在清理资源...")
        # MCP服务现在由mcpserver独立管理，无需清理

# 创建FastAPI应用
app = FastAPI(
    title="NagaAgent API",
    description="智能对话助手API服务",
    version="4.0.0",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 请求模型
class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: Optional[str] = None
    use_self_game: bool = False
    disable_tts: bool = False  # V17: 支持禁用服务器端TTS
    return_audio: bool = False  # V19: 支持返回音频URL供客户端播放
    skip_intent_analysis: bool = False  # 新增：跳过意图分析

class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    status: str = "success"



class SystemInfoResponse(BaseModel):
    version: str
    status: str
    available_services: List[str]
    api_key_configured: bool

class FileUploadResponse(BaseModel):
    filename: str
    file_path: str
    file_size: int
    file_type: str
    upload_time: str
    status: str = "success"
    message: str = "文件上传成功"

class DocumentProcessRequest(BaseModel):
    file_path: str
    action: str = "read"  # read, analyze, summarize
    session_id: Optional[str] = None


# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """API根路径"""
    return {
        "name": "NagaAgent API",
        "version": "4.0.0",
        "status": "running",
        "docs": "/docs",
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "agent_ready": True,
        "timestamp": str(asyncio.get_event_loop().time())
    }

@app.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    """获取系统信息"""
    
    return SystemInfoResponse(
        version="4.0.0",
        status="running",
        available_services=[],  # MCP服务现在由mcpserver独立管理
        api_key_configured=bool(config.api.api_key and config.api.api_key != "sk-placeholder-key-not-set")
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """普通对话接口 - 仅处理纯文本对话"""
    
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    try:
        # 分支: 启用博弈论流程（非流式，返回聚合文本）
        if request.use_self_game:
            # 配置项控制：失败时可跳过回退到普通对话 #
            skip_on_error = getattr(getattr(config, 'game', None), 'skip_on_error', True)  # 兼容无配置情况 #
            enabled = getattr(getattr(config, 'game', None), 'enabled', False)  # 控制总开关 #
            if enabled:
                try:
                    # 延迟导入以避免启动时循环依赖 #
                    from game.naga_game_system import NagaGameSystem  # 博弈系统入口 #
                    from game.core.models.config import GameConfig  # 博弈系统配置 #
                    # 创建系统并执行用户问题处理 #
                    system = NagaGameSystem(GameConfig())
                    system_response = await system.process_user_question(
                        user_question=request.message,
                        user_id=request.session_id or "api_user"
                    )
                    return ChatResponse(
                        response=system_response.content,
                        session_id=request.session_id,
                        status="success"
                    )
                except Exception as e:
                    print(f"[WARNING] 博弈论流程失败，将{ '回退到普通对话' if skip_on_error else '返回错误' }: {e}")  # 运行时警告 #
                    if not skip_on_error:
                        raise HTTPException(status_code=500, detail=f"博弈论流程失败: {str(e)}")
                    # 否则继续走普通对话流程 #
            # 若未启用或被配置跳过，则直接回退到普通对话分支 #

        # 获取或创建会话ID
        session_id = message_manager.create_session(request.session_id)
        
        # 构建系统提示词（只使用对话风格提示词）
        system_prompt = get_prompt("conversation_style_prompt")
        
        # 使用消息管理器构建完整的对话消息（纯聊天，不触发工具）
        messages = message_manager.build_conversation_messages(
            session_id=session_id,
            system_prompt=system_prompt,
            current_message=request.message
        )
        
        # 使用整合后的LLM服务
        llm_service = get_llm_service()
        response_text = await llm_service.chat_with_context(messages, config.api.temperature)
        
        # 处理完成
        # 统一保存对话历史与日志
        _save_conversation_and_logs(session_id, request.message, response_text)

        # 在用户消息保存到历史后触发后台意图分析（除非明确跳过）
        if not request.skip_intent_analysis:
            _trigger_background_analysis(session_id=session_id)

        return ChatResponse(
            response=extract_message(response_text) if response_text else response_text,
            session_id=session_id,
            status="success"
        )
    except Exception as e:
        print(f"对话处理错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 - 流式文本处理交给streaming_tool_extractor用于TTS"""
    
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    async def generate_response() -> AsyncGenerator[str, None]:
        complete_text = ""  # V19: 用于累积完整文本以生成音频
        try:
            # 获取或创建会话ID
            session_id = message_manager.create_session(request.session_id)
            
            # 发送会话ID信息
            yield f"data: session_id: {session_id}\n\n"
            
            # 注意：这里不触发后台分析，将在对话保存后触发
            
            # 构建系统提示词（只使用对话风格提示词）
            system_prompt = get_prompt("conversation_style_prompt")
            
            # 使用消息管理器构建完整的对话消息
            messages = message_manager.build_conversation_messages(
                session_id=session_id,
                system_prompt=system_prompt,
                current_message=request.message
            )

            # 初始化语音集成（根据voice_mode和return_audio决定）
            # V19: 如果客户端请求返回音频，则在服务器端生成
            voice_integration = None

            # V19: 混合模式下，如果请求return_audio，则在服务器生成音频
            # 修复双音频问题：return_audio时不启用实时TTS，只在最后生成完整音频
            should_enable_tts = (
                config.system.voice_enabled
                and not request.return_audio  # 修复：return_audio时不启用实时TTS
                and config.voice_realtime.voice_mode != "hybrid"
                and not request.disable_tts  # 兼容旧版本的disable_tts
            )

            if should_enable_tts:
                try:
                    from voice.output.voice_integration import get_voice_integration
                    voice_integration = get_voice_integration()
                    logger.info(f"[API Server] 实时语音集成已启用 (return_audio={request.return_audio}, voice_mode={config.voice_realtime.voice_mode})")
                except Exception as e:
                    print(f"语音集成初始化失败: {e}")
            else:
                if request.return_audio:
                    logger.info("[API Server] return_audio模式，将在最后生成完整音频")
                elif config.voice_realtime.voice_mode == "hybrid" and not request.return_audio:
                    logger.info("[API Server] 混合模式下且未请求音频，不处理TTS")
                elif request.disable_tts:
                    logger.info("[API Server] 客户端禁用了TTS (disable_tts=True)")

            # 初始化流式文本切割器（仅用于TTS处理）
            # 始终创建tool_extractor以累积文本内容，确保日志保存
            tool_extractor = None
            try:
                from .streaming_tool_extractor import StreamingToolCallExtractor
                tool_extractor = StreamingToolCallExtractor()
                # 只有在需要实时TTS且不是return_audio模式时，才设置voice_integration
                if voice_integration and not request.return_audio:
                    tool_extractor.set_callbacks(
                        on_text_chunk=None,  # 不需要回调，直接处理TTS
                        voice_integration=voice_integration
                    )
            except Exception as e:
                print(f"流式文本切割器初始化失败: {e}")
            
            # 使用整合后的流式处理
            llm_service = get_llm_service()
            async for chunk in llm_service.stream_chat_with_context(messages, config.api.temperature):
                # V19: 如果需要返回音频，累积文本
                if request.return_audio and chunk.startswith("data: "):
                    try:
                        import base64
                        data_str = chunk[6:].strip()
                        if data_str != '[DONE]':
                            decoded = base64.b64decode(data_str).decode('utf-8')
                            complete_text += decoded
                    except Exception:
                        pass
                
                # 立即发送到流式文本切割器进行TTS处理（不阻塞文本流）
                if tool_extractor and chunk.startswith("data: "):
                    try:
                        import base64
                        data_str = chunk[6:].strip()
                        if data_str != '[DONE]':
                            decoded = base64.b64decode(data_str).decode('utf-8')
                            # 同步处理文本累积，不阻塞文本流
                            tool_extractor.complete_text += decoded
                    except Exception as e:
                        logger.error(f"[API Server] 流式文本切割器处理错误: {e}")
                
                yield chunk
            
            # 处理完成

            # V19: 如果请求返回音频，在这里生成并返回音频URL
            if request.return_audio and complete_text:
                try:
                    logger.info(f"[API Server V19] 生成音频，文本长度: {len(complete_text)}")

                    # 使用服务器端的TTS生成音频
                    from voice.tts_wrapper import generate_speech_safe
                    import tempfile
                    import uuid

                    # 生成音频文件
                    tts_voice = config.voice_realtime.tts_voice or "zh-CN-XiaoyiNeural"
                    audio_file = generate_speech_safe(
                        text=complete_text,
                        voice=tts_voice,
                        response_format="mp3",
                        speed=1.0
                    )

                    # 直接使用voice/output播放音频，不再返回给客户端
                    try:
                        from voice.output.voice_integration import get_voice_integration
                        voice_integration = get_voice_integration()
                        voice_integration.receive_audio_url(audio_file)
                        logger.info(f"[API Server V19] 音频已直接播放: {audio_file}")
                    except Exception as e:
                        logger.error(f"[API Server V19] 音频播放失败: {e}")
                        # 如果播放失败，仍然返回给客户端作为备选
                        yield f"data: audio_url: {audio_file}\n\n"

                except Exception as e:
                    logger.error(f"[API Server V19] 音频生成失败: {e}")
                    # traceback已经在文件顶部导入，直接使用
                    print(f"[API Server V19] 详细错误信息:")
                    traceback.print_exc()

            # 完成流式文本切割器处理（非return_audio模式，不阻塞）
            if tool_extractor and not request.return_audio:
                try:
                    # 同步处理完成，不阻塞文本流返回
                    # tool_extractor.finish_processing() 是异步方法，这里不需要调用
                    pass
                except Exception as e:
                    print(f"流式文本切割器完成处理错误: {e}")
            
            # 完成语音处理
            if voice_integration and not request.return_audio:  # V19: return_audio模式不需要这里的处理
                try:
                    threading.Thread(
                        target=voice_integration.finish_processing,
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"语音集成完成处理错误: {e}")

            # 流式处理完成后，获取完整文本用于保存
            complete_response = ""
            if tool_extractor:
                try:
                    # 获取完整文本内容
                    complete_response = tool_extractor.get_complete_text()
                except Exception as e:
                    print(f"获取完整响应文本失败: {e}")
            elif request.return_audio:
                # V19: 如果是return_audio模式，使用累积的文本
                complete_response = complete_text
            
            # 统一保存对话历史与日志
            _save_conversation_and_logs(session_id, request.message, complete_response)

            # 在用户消息保存到历史后触发后台意图分析（除非明确跳过）
            if not request.skip_intent_analysis:
                _trigger_background_analysis(session_id)

            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"流式对话处理错误: {e}")
            # 使用顶部导入的traceback
            traceback.print_exc()
            yield f"data: 错误: {str(e)}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )


@app.get("/memory/stats")
async def get_memory_stats():
    """获取记忆统计信息"""
    
    try:
        # 记忆系统现在由main.py直接管理
        try:
            from summer_memory.memory_manager import memory_manager
            if memory_manager and memory_manager.enabled:
                stats = memory_manager.get_memory_stats()
                return {
                    "status": "success",
                    "memory_stats": stats
                }
            else:
                return {
                    "status": "success",
                    "memory_stats": {"enabled": False, "message": "记忆系统未启用"}
                }
        except ImportError:
            return {
                "status": "success",
                "memory_stats": {"enabled": False, "message": "记忆系统模块未找到"}
            }
    except Exception as e:
        print(f"获取记忆统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取记忆统计失败: {str(e)}")

@app.get("/sessions")
async def get_sessions():
    """获取所有会话信息 - 委托给message_manager"""
    try:
        return message_manager.get_all_sessions_api()
    except Exception as e:
        print(f"获取会话信息错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话的详细信息 - 委托给message_manager"""
    try:
        return message_manager.get_session_detail_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        print(f"获取会话详情错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话 - 委托给message_manager"""
    try:
        return message_manager.delete_session_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        print(f"删除会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sessions")
async def clear_all_sessions():
    """清空所有会话 - 委托给message_manager"""
    try:
        return message_manager.clear_all_sessions_api()
    except Exception as e:
        print(f"清空会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# 文档处理功能已整合到 ui/controller/tool_document.py

# 新增：日志解析相关API接口
@app.get("/logs/context/statistics")
async def get_log_context_statistics(days: int = 7):
    """获取日志上下文统计信息"""
    try:
        statistics = message_manager.get_context_statistics(days)
        return {
            "status": "success",
            "statistics": statistics
        }
    except Exception as e:
        print(f"获取日志上下文统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

@app.get("/logs/context/load")
async def load_log_context(days: int = 3, max_messages: int = None):
    """加载日志上下文"""
    try:
        messages = message_manager.load_recent_context(days=days, max_messages=max_messages)
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "days": days
        }
    except Exception as e:
        print(f"加载日志上下文错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"加载上下文失败: {str(e)}")

@app.post("/tool_notification")
async def tool_notification(payload: Dict[str, Any]):
    """接收工具调用状态通知，只显示工具调用状态，不显示结果"""
    try:
        session_id = payload.get("session_id")
        tool_calls = payload.get("tool_calls", [])
        message = payload.get("message", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        # 记录工具调用状态（不处理结果，结果由tool_result_callback处理）
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool_name", "未知工具")
            service_name = tool_call.get("service_name", "未知服务")
            status = tool_call.get("status", "starting")
            logger.info(f"工具调用状态: {tool_name} ({service_name}) - {status}")

        # 这里可以添加WebSocket通知UI的逻辑，让UI显示工具调用状态
        # 目前先记录日志，UI可以通过其他方式获取工具调用状态

        return {
            "success": True,
            "message": "工具调用状态通知已接收",
            "tool_calls": tool_calls,
            "display_message": message
        }

    except Exception as e:
        logger.error(f"工具调用通知处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")

@app.post("/tool_result_callback")
async def tool_result_callback(payload: Dict[str, Any]):
    """接收MCP工具执行结果回调，让主AI基于原始对话和工具结果重新生成回复"""
    try:
        session_id = payload.get("session_id")
        task_id = payload.get("task_id")
        result = payload.get("result", {})
        success = payload.get("success", False)

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"[工具回调] 开始处理工具回调，会话: {session_id}, 任务ID: {task_id}")
        logger.info(f"[工具回调] 回调内容: {result}")

        # 获取工具执行结果
        tool_result = result.get('result', '执行成功') if success else result.get('error', '未知错误')
        logger.info(f"[工具回调] 工具执行结果: {tool_result}")

        # 获取原始对话的最后一条用户消息（触发工具调用的消息）
        session_messages = message_manager.get_messages(session_id)
        original_user_message = ""
        for msg in reversed(session_messages):
            if msg.get('role') == 'user':
                original_user_message = msg.get('content', '')
                break

        # 构建包含工具结果的用户消息
        enhanced_message = f"{original_user_message}\n\n[工具执行结果]: {tool_result}"
        logger.info(f"[工具回调] 构建增强消息: {enhanced_message[:200]}...")

        # 构建对话风格提示词和消息
        system_prompt = get_prompt("conversation_style_prompt")
        messages = message_manager.build_conversation_messages(
            session_id=session_id,
            system_prompt=system_prompt,
            current_message=enhanced_message
        )

        logger.info(f"[工具回调] 开始生成工具后回复...")

        # 使用LLM服务基于原始对话和工具结果重新生成回复
        try:
            llm_service = get_llm_service()
            response_text = await llm_service.chat_with_context(messages, temperature=0.7)
            logger.info(f"[工具回调] 工具后回复生成成功，内容: {response_text[:200]}...")
        except Exception as e:
            logger.error(f"[工具回调] 调用LLM服务失败: {e}")
            response_text = f"处理工具结果时出错: {str(e)}"

        # 保存AI回复到历史
        message_manager.add_message(session_id, "assistant", response_text)
        logger.info(f"[工具回调] AI回复已保存到历史")

        # 通过UI通知接口将AI回复发送给UI
        logger.info(f"[工具回调] 开始发送AI回复到UI...")
        await _notify_ui_refresh(session_id, response_text)

        logger.info(f"[工具回调] 工具结果处理完成，回复已发送到UI")

        return {
            "success": True,
            "message": "工具结果已通过主AI处理并返回给UI",
            "response": response_text,
            "task_id": task_id,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"[工具回调] 工具结果回调处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")

@app.post("/tool_result")
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

        # 如果是工具完成后的AI回复，通过信号机制通知UI线程显示
        if notification_type == "tool_completed_with_ai_response" and ai_response:
            try:
                # 使用Qt信号机制在主线程中安全地更新UI
                from ui.controller.tool_chat import chat

                # 直接发射信号，确保在主线程中执行
                chat.tool_ai_response_received.emit(ai_response)
                logger.info(f"[UI] 已通过信号机制通知UI显示AI回复，长度: {len(ai_response)}")
            except Exception as e:
                logger.error(f"[UI] 调用UI控制器显示AI回复失败: {e}")

        return {
            "success": True,
            "message": "工具结果已接收",
            "result": result,
            "session_id": session_id
        }

    except Exception as e:
        logger.error(f"处理工具结果失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


@app.post("/ui_notification")
async def ui_notification(payload: Dict[str, Any]):
    """UI通知接口 - 用于直接控制UI显示"""
    try:
        session_id = payload.get("session_id")
        action = payload.get("action", "")
        ai_response = payload.get("ai_response", "")

        if not session_id:
            raise HTTPException(400, "缺少session_id")

        logger.info(f"UI通知: {action}, 会话: {session_id}")

        # 处理显示工具AI回复的动作
        if action == "show_tool_ai_response" and ai_response:
            try:
                from ui.controller.tool_chat import chat

                # 直接发射信号，确保在主线程中执行
                chat.tool_ai_response_received.emit(ai_response)
                logger.info(f"[UI通知] 已通过信号机制显示工具AI回复，长度: {len(ai_response)}")
                return {
                    "success": True,
                    "message": "AI回复已显示"
                }
            except Exception as e:
                logger.error(f"[UI通知] 显示工具AI回复失败: {e}")
                raise HTTPException(500, f"显示AI回复失败: {str(e)}")

        return {
            "success": True,
            "message": "UI通知已处理"
        }

    except Exception as e:
        logger.error(f"处理UI通知失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")


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
            "use_self_game": False,
            "disable_tts": False,
            "return_audio": False,
            "skip_intent_analysis": True  # 关键：跳过意图分析
        }

        # 调用现有的流式对话接口
        api_url = f"http://localhost:8000/chat/stream"

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
                    logger.info(f"[UI发送] 成功显示到UI")
                else:
                    logger.error(f"[UI发送] 调用流式对话接口失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI发送] 触发聊天流式响应失败: {e}")


async def _notify_ui_refresh(session_id: str, response_text: str):
    """通知UI刷新会话历史"""
    try:
        import httpx

        # 通过UI通知接口直接显示AI回复
        ui_notification_payload = {
            "session_id": session_id,
            "action": "show_tool_ai_response",
            "ai_response": response_text
        }

        api_url = f"http://localhost:8000/ui_notification"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(api_url, json=ui_notification_payload)
            if response.status_code == 200:
                logger.info(f"[UI通知] AI回复显示通知发送成功: {session_id}")
            else:
                logger.error(f"[UI通知] AI回复显示通知失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[UI通知] 通知UI刷新失败: {e}")




async def _send_ai_response_directly(session_id: str, response_text: str):
    """直接发送AI回复到UI"""
    try:
        import httpx

        # 使用非流式接口发送AI回复
        chat_request = {
            "message": f"[工具结果] {response_text}",  # 添加标记让UI知道这是工具结果
            "stream": False,
            "session_id": session_id,
            "use_self_game": False,
            "disable_tts": False,
            "return_audio": False,
            "skip_intent_analysis": True
        }

        api_url = f"http://localhost:8000/chat"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=chat_request)
            if response.status_code == 200:
                logger.info(f"[直接发送] AI回复已通过非流式接口发送到UI: {session_id}")
            else:
                logger.error(f"[直接发送] 非流式接口发送失败: {response.status_code}")

    except Exception as e:
        logger.error(f"[直接发送] 直接发送AI回复失败: {e}")


# 工具执行结果已通过LLM总结并保存到对话历史中
# UI可以通过查询历史获取工具执行结果

