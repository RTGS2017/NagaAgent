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
        
        # 并行触发后台意图分析 - 在对话开始时就分析用户意图
        _trigger_background_analysis(session_id=session_id)
        
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
            
            # 并行触发后台意图分析 - 在流式响应开始时就分析用户意图
            _trigger_background_analysis(session_id)
            
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
        tool_name = payload.get("tool_name", "未知工具")
        service_name = payload.get("service_name", "未知服务")
        status = payload.get("status", "starting")
        message = payload.get("message", f"🔧 正在执行工具: {tool_name}")
        
        if not session_id:
            raise HTTPException(400, "缺少session_id")
        
        # 记录工具调用状态（不处理结果，结果由tool_result_callback处理）
        logger.info(f"工具调用状态: {tool_name} ({service_name}) - {status}")
        
        # 这里可以添加WebSocket通知UI的逻辑，让UI显示工具调用状态
        # 目前先记录日志，UI可以通过其他方式获取工具调用状态
        
        return {
            "success": True,
            "message": "工具调用状态通知已接收",
            "tool_name": tool_name,
            "service_name": service_name,
            "status": status,
            "display_message": message
        }
        
    except Exception as e:
        logger.error(f"工具调用通知处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")

@app.post("/tool_result_callback")
async def tool_result_callback(payload: Dict[str, Any]):
    """接收MCP工具执行结果回调，通过普通对话流程返回给UI"""
    try:
        session_id = payload.get("session_id")
        task_id = payload.get("task_id")
        result = payload.get("result", {})
        success = payload.get("success", False)
        
        if not session_id:
            raise HTTPException(400, "缺少session_id")
        
        # 构建工具结果消息
        if success and result:
            tool_result_message = f"工具执行完成：{result.get('result', '执行成功')}"
        else:
            error_msg = result.get('error', '未知错误')
            tool_result_message = f"工具执行失败：{error_msg}"
        
        # 构建对话风格提示词和消息
        system_prompt = get_prompt("conversation_style_prompt")
        messages = message_manager.build_conversation_messages(
            session_id=session_id,
            system_prompt=system_prompt,
            current_message=tool_result_message
        )
        
        # 使用LLM服务进行总结
        try:
            llm_service = get_llm_service()
            response_text = await llm_service.chat_with_context(messages, temperature=0.7)
        except Exception as e:
            logger.error(f"调用LLM服务失败: {e}")
            response_text = f"处理工具结果时出错: {str(e)}"
        
        # 保存到历史
        message_manager.add_message(session_id, "user", tool_result_message)
        message_manager.add_message(session_id, "assistant", response_text)
        
        # 通过普通对话流程返回给UI（包括TTS）
        # 直接调用现有的流式对话接口，复用完整的TTS和UI响应逻辑
        await _trigger_chat_stream(session_id, response_text)
        
        return {
            "success": True,
            "message": "工具结果已通过LLM总结并返回给UI",
            "response": response_text,
            "task_id": task_id,
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"工具结果回调处理失败: {e}")
        raise HTTPException(500, f"处理失败: {str(e)}")

async def _trigger_chat_stream(session_id: str, response_text: str):
    """触发聊天流式响应 - 直接调用现有的chat_stream接口"""
    try:
        # 直接调用现有的流式对话接口，复用完整的TTS和UI响应逻辑
        import httpx
        
        # 构建请求数据
        chat_request = {
            "message": f"工具执行结果：{response_text}",
            "stream": True,
            "session_id": session_id,
            "use_self_game": False,
            "disable_tts": False,
            "return_audio": False
        }
        
        # 调用现有的流式对话接口
        api_url = f"http://localhost:8001/chat/stream"
        
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", api_url, json=chat_request) as response:
                if response.status_code == 200:
                    # 处理流式响应，包括TTS切割
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            # 这里可以进一步处理流式响应
                            # 或者直接让UI处理流式响应
                            pass
                    
                    logger.info(f"工具结果已通过流式对话接口发送给UI: {session_id}")
                else:
                    logger.error(f"调用流式对话接口失败: {response.status_code}")
        
    except Exception as e:
        logger.error(f"触发聊天流式响应失败: {e}")

# 工具执行结果已通过LLM总结并保存到对话历史中
# UI可以通过查询历史获取工具执行结果

