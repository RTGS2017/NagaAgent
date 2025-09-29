#!/usr/bin/env python3
"""
NagaAgent API服务器
提供RESTful API接口访问NagaAgent功能
"""

import asyncio
import json
import sys
import traceback
import re
import os
import logging
import uuid
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, AsyncGenerator, Any

# 在导入其他模块前先设置HTTP库日志级别
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

from nagaagent_core.api import uvicorn
from nagaagent_core.api import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File, Form
from nagaagent_core.api import CORSMiddleware
from nagaagent_core.api import StreamingResponse, JSONResponse, HTMLResponse
from nagaagent_core.api import WebSocket, WebSocketDisconnect
from nagaagent_core.api import StaticFiles
from nagaagent_core.vendors.pydantic import BaseModel
from nagaagent_core.core import aiohttp
import shutil
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 工具调用模块（仅用于流式接口）
from .message_manager import message_manager  # 导入统一的消息管理器
from .prompt_logger import prompt_logger  # 导入prompt日志记录器

# 导入配置系统
try:
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.prompt_repository import get_prompt  # 导入提示词仓库
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.config import config, AI_NAME  # 使用新的配置系统
    from system.prompt_repository import get_prompt  # 导入提示词仓库
from ui.response_utils import extract_message  # 导入消息提取工具

# 全局NagaAgent实例 - 延迟导入避免循环依赖
naga_agent = None

# 回调工厂类 - 统一管理重复的回调函数
class CallbackFactory:
    """回调函数工厂类 - 消除重复定义"""
    
    @staticmethod
    def create_text_chunk_callback(pure_text_content_ref, is_streaming=False):
        """创建文本块回调函数"""
        def on_text_chunk(text: str, chunk_type: str):
            """处理文本块 - 累积纯文本内容"""
            if chunk_type == "chunk":
                pure_text_content_ref[0] += text
                if is_streaming:
                    return f"data: {text}\n\n"
            return None
        return on_text_chunk
    
    @staticmethod
    def create_sentence_callback(is_streaming=False):
        """创建句子回调函数"""
        def on_sentence(sentence: str, sentence_type: str):
            """处理完整句子"""
            if sentence_type == "sentence":
                if is_streaming:
                    return f"data: [SENTENCE] {sentence}\n\n"
            return None
        return on_sentence
    
    @staticmethod
    def create_tool_call_callback(is_streaming=False):
        """创建工具调用回调函数"""
        def on_tool_call(tool_call: str, tool_type: str):
            """处理工具调用 - 不累积到纯文本"""
            if tool_type == "tool_call":
                if is_streaming:
                    return f"data: [TOOL_CALL] 正在执行工具调用...\n\n"
            return None
        return on_tool_call
    
    @staticmethod
    def create_tool_result_callback(is_streaming=False):
        """创建工具结果回调函数"""
        def on_tool_result(result: str, result_type: str):
            """处理工具结果 - 不累积到纯文本"""
            if result_type == "tool_start":
                if is_streaming:
                    return f"data: [TOOL_START] {result}\n\n"
            elif result_type == "tool_result":
                if is_streaming:
                    return f"data: [TOOL_RESULT] {result}\n\n"
            elif result_type == "tool_error":
                if is_streaming:
                    return f"data: [TOOL_ERROR] {result}\n\n"
            return None
        return on_tool_result
    
    @classmethod
    def create_callbacks(cls, pure_text_content_ref, is_streaming=False):
        """创建完整的回调函数集合"""
        return {
            'on_text_chunk': cls.create_text_chunk_callback(pure_text_content_ref, is_streaming),
            'on_sentence': cls.create_sentence_callback(is_streaming),
            'on_tool_call': cls.create_tool_call_callback(is_streaming),
            'on_tool_result': cls.create_tool_result_callback(is_streaming)
        }

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                # 移除断开的连接
                self.active_connections.remove(connection)

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global naga_agent
    try:
        print("[INFO] 正在初始化NagaAgent...")
        # 延迟导入避免循环依赖
        from system.conversation_core import NagaConversation
        naga_agent = NagaConversation()  # 第四次初始化：API服务器启动时创建
        print("[SUCCESS] NagaAgent初始化完成")
        yield
    except Exception as e:
        print(f"[ERROR] NagaAgent初始化失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 正在清理资源...")
        if naga_agent and hasattr(naga_agent, 'mcp'):
            try:
                await naga_agent.mcp.cleanup()
            except Exception as e:
                print(f"[WARNING] 清理MCP资源时出错: {e}")

# 创建FastAPI应用
app = FastAPI(
    title="NagaAgent API",
    description="智能对话助手API服务",
    version="3.0",
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

class ChatResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    status: str = "success"

class MCPRequest(BaseModel):
    service_name: str
    task: Dict
    session_id: Optional[str] = None

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

# WebSocket路由
@app.websocket("/ws/mcplog")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点 - 提供MCP实时通知"""
    await manager.connect(websocket)
    try:
        # 发送连接确认
        await manager.send_personal_message(
            json.dumps({
                "type": "connection_ack",
                "message": "WebSocket连接成功"
            }, ensure_ascii=False),
            websocket
        )
        
        # 保持连接
        while True:
            try:
                # 等待客户端消息（心跳检测）
                data = await websocket.receive_text()
                # 可以处理客户端发送的消息
                await manager.send_personal_message(
                    json.dumps({
                        "type": "pong",
                        "message": "收到心跳"
                    }, ensure_ascii=False),
                    websocket
                )
            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
    except Exception as e:
        print(f"WebSocket错误: {e}")
        manager.disconnect(websocket)

# API路由
@app.get("/", response_model=Dict[str, str])
async def root():
    """API根路径"""
    return {
        "name": "NagaAgent API",
        "version": "3.0",
        "status": "running",
        "docs": "/docs",
        "websocket": "/ws/mcplog"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "agent_ready": naga_agent is not None,
        "timestamp": str(asyncio.get_event_loop().time())
    }

@app.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    """获取系统信息"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    return SystemInfoResponse(
        version="3.0",
        status="running",
        available_services=naga_agent.mcp.list_mcps(),
        api_key_configured=bool(config.api.api_key and config.api.api_key != "sk-placeholder-key-not-set")
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """对话接口 - 统一使用流式处理，支持工具调用"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
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
        
        # 构建系统提示词
        available_services = naga_agent.mcp.get_available_services_filtered()
        services_text = naga_agent._format_services_for_prompt(available_services)
        system_prompt = get_prompt("naga_system_prompt", ai_name=AI_NAME, **services_text)
        
        # 使用消息管理器构建完整的对话消息
        messages = message_manager.build_conversation_messages(
            session_id=session_id,
            system_prompt=system_prompt,
            current_message=request.message
        )
        
        # 导入流式工具调用提取器
        from .streaming_tool_extractor import StreamingToolCallExtractor
        tool_extractor = StreamingToolCallExtractor(naga_agent.mcp)
        
        # 用于累积纯文本内容（不包含工具调用）
        pure_text_content = [""]  # 使用列表引用，便于在回调中修改
        
        # 使用回调工厂创建回调函数
        callbacks = CallbackFactory.create_callbacks(pure_text_content, is_streaming=False)
        
        # 设置回调
        tool_extractor.set_callbacks(**callbacks)
        
        # 调用LLM API - 流式模式
        async with aiohttp.ClientSession() as session:
            # 保存prompt日志
            prompt_logger.log_prompt(session_id, messages, api_status="sending")
            
            async with session.post(
                f"{config.api.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.api.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": config.api.model,
                    "messages": messages,
                    "temperature": config.api.temperature,
                    "max_tokens": config.api.max_tokens,
                    "stream": True
                }
            ) as resp:
                if resp.status != 200:
                    # 保存失败的prompt日志
                    prompt_logger.log_prompt(session_id, messages, api_status="failed")
                    error_detail = f"LLM API调用失败 (状态码: {resp.status})"
                    if resp.status == 401:
                        error_detail = "LLM API认证失败，请检查API密钥"
                    elif resp.status == 403:
                        error_detail = "LLM API访问被拒绝，请检查权限"
                    elif resp.status == 429:
                        error_detail = "LLM API请求过于频繁，请稍后重试"
                    elif resp.status >= 500:
                        error_detail = f"LLM API服务器错误 (状态码: {resp.status})"
                    raise HTTPException(status_code=resp.status, detail=error_detail)
                
                # 处理流式响应
                async for line in resp.content:
                    line_str = line.decode('utf-8').strip()
                    if line_str.startswith('data: '):
                        data_str = line_str[6:]
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    content = delta['content']
                                    # 使用流式工具调用提取器处理内容
                                    await tool_extractor.process_text_chunk(content)
                        except json.JSONDecodeError:
                            continue
        
        # 完成处理
        await tool_extractor.finish_processing()
        
        # 保存对话历史到消息管理器（使用纯文本内容）
        message_manager.add_message(session_id, "user", request.message)
        message_manager.add_message(session_id, "assistant", pure_text_content[0])
        
        # 保存成功的prompt日志
        prompt_logger.log_prompt(session_id, messages, {"content": pure_text_content[0]}, api_status="success")
        
        # 异步触发后台意图分析 - 基于博弈论的背景分析机制
        try:
            from agentserver.task_scheduler import get_task_scheduler
            task_scheduler = get_task_scheduler()
            
            # 获取最近对话历史
            recent_messages = message_manager.get_recent_messages(session_id, count=6)
            
            # 异步执行后台分析，不阻塞主流程
            asyncio.create_task(task_scheduler.schedule_background_analysis(session_id, recent_messages))
        except Exception as e:
            # 后台分析失败不影响主对话
            print(f"后台意图分析触发失败: {e}")
        
        return ChatResponse(
            response=extract_message(pure_text_content[0]) if pure_text_content[0] else pure_text_content[0],
            session_id=session_id,
            status="success"
        )
    except Exception as e:
        print(f"对话处理错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话接口 - 支持流式工具调用提取"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    
    async def generate_response() -> AsyncGenerator[str, None]:
        try:
            # 获取或创建会话ID
            session_id = message_manager.create_session(request.session_id)
            
            # 发送会话ID信息
            yield f"data: session_id: {session_id}\n\n"
            
            # 构建系统提示词
            available_services = naga_agent.mcp.get_available_services_filtered()
            services_text = naga_agent._format_services_for_prompt(available_services)
            system_prompt = get_prompt("naga_system_prompt", ai_name=AI_NAME, **services_text)
            
            # 使用消息管理器构建完整的对话消息
            messages = message_manager.build_conversation_messages(
                session_id=session_id,
                system_prompt=system_prompt,
                current_message=request.message
            )
            
            # 导入流式工具调用提取器
            from .streaming_tool_extractor import StreamingToolCallExtractor
            tool_extractor = StreamingToolCallExtractor(naga_agent.mcp)
            
            # 用于累积纯文本内容（不包含工具调用）
            pure_text_content = [""]  # 使用列表引用，便于在回调中修改
            
            # 初始化语音集成（如果启用）
            voice_integration = None
            if config.system.voice_enabled:
                try:
                    from voice.output.voice_integration import get_voice_integration
                    voice_integration = get_voice_integration()
                except Exception as e:
                    print(f"语音集成初始化失败: {e}")
            
            # 使用回调工厂创建回调函数
            callbacks = CallbackFactory.create_callbacks(pure_text_content, is_streaming=True)
            
            # 设置回调
            tool_extractor.set_callbacks(
                **callbacks,
                voice_integration=voice_integration
            )
            
            # 定义LLM调用函数 - 支持真正的流式输出
            async def call_llm_stream(messages: List[Dict]) -> AsyncGenerator[str, None]:
                """调用LLM API - 流式模式"""
                async with aiohttp.ClientSession() as session:
                    # 保存prompt日志
                    prompt_logger.log_prompt(session_id, messages, api_status="sending")
                    
                    async with session.post(
                        f"{config.api.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {config.api.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": config.api.model,
                            "messages": messages,
                            "temperature": config.api.temperature,
                            "max_tokens": config.api.max_tokens,
                            "stream": True  # 启用真正的流式输出
                        }
                    ) as resp:
                        if resp.status != 200:
                            # 保存失败的prompt日志
                            prompt_logger.log_prompt(session_id, messages, api_status="failed")
                            error_detail = f"LLM API调用失败 (状态码: {resp.status})"
                            if resp.status == 401:
                                error_detail = "LLM API认证失败，请检查API密钥"
                            elif resp.status == 403:
                                error_detail = "LLM API访问被拒绝，请检查权限"
                            elif resp.status == 429:
                                error_detail = "LLM API请求过于频繁，请稍后重试"
                            elif resp.status >= 500:
                                error_detail = f"LLM API服务器错误 (状态码: {resp.status})"
                            raise HTTPException(status_code=resp.status, detail=error_detail)
                        
                        # 处理流式响应
                        async for line in resp.content:
                            line_str = line.decode('utf-8').strip()
                            if line_str.startswith('data: '):
                                data_str = line_str[6:]
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data = json.loads(data_str)
                                    if 'choices' in data and len(data['choices']) > 0:
                                        delta = data['choices'][0].get('delta', {})
                                        if 'content' in delta:
                                            content = delta['content']
                                            # 使用流式工具调用提取器处理内容
                                            results = await tool_extractor.process_text_chunk(content)
                                            if results:
                                                for result in results:
                                                    yield result
                                            
                                except json.JSONDecodeError:
                                    continue
            
            # 处理流式响应
            async for chunk in call_llm_stream(messages):
                yield chunk
            
            # 完成处理
            final_results = await tool_extractor.finish_processing()
            if final_results:
                for result in final_results:
                    yield result
            
            # 检查是否需要继续流式输出（工具调用执行后）
            # 这里可以添加逻辑来处理工具调用执行后的继续流式输出
            # 例如：如果工具调用执行完成，可以继续调用LLM获取后续内容
            
            # 完成语音处理
            if voice_integration:
                try:
                    import threading
                    threading.Thread(
                        target=voice_integration.finish_processing,
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"语音集成完成处理错误: {e}")
            
            # 保存对话历史到消息管理器（使用纯文本内容）
            message_manager.add_message(session_id, "user", request.message)
            message_manager.add_message(session_id, "assistant", pure_text_content[0])
            
            # 保存成功的prompt日志
            prompt_logger.log_prompt(session_id, messages, {"content": pure_text_content[0]}, api_status="success")
            
            # 异步触发后台意图分析 - 基于博弈论的背景分析机制
            try:
                from agentserver.task_scheduler import get_task_scheduler
                task_scheduler = get_task_scheduler()
                
                # 获取最近对话历史
                recent_messages = message_manager.get_recent_messages(session_id, count=6)
                
                # 异步执行后台分析，不阻塞主流程
                asyncio.create_task(task_scheduler.schedule_background_analysis(session_id, recent_messages))
            except Exception as e:
                # 后台分析失败不影响主对话
                print(f"后台意图分析触发失败: {e}")
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"流式对话处理错误: {e}")
            traceback.print_exc()
            yield f"data: 错误: {str(e)}\n\n"
    
    return StreamingResponse(
        generate_response(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

@app.post("/mcp/handoff")
async def mcp_handoff(request: MCPRequest):
    """MCP服务调用接口"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 获取或创建会话ID
        session_id = message_manager.get_or_create_session(request.session_id)
        
        # 直接调用MCP handoff
        result = await naga_agent.mcp.handoff(
            service_name=request.service_name,
            task=request.task
        )
        
        return {
            "status": "success",
            "result": result,
            "session_id": session_id  # 使用生成的会话ID
        }
    except Exception as e:
        print(f"MCP handoff错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"handoff失败: {str(e)}")

@app.get("/mcp/services")
async def get_mcp_services():
    """获取可用的MCP服务列表"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 使用动态服务池查询
        services = naga_agent.mcp.get_available_services()
        statistics = naga_agent.mcp.get_service_statistics()
        
        return {
            "status": "success",
            "services": services,
            "statistics": statistics,
            "count": len(services)
        }
    except Exception as e:
        print(f"获取MCP服务列表错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取服务列表失败: {str(e)}")

@app.get("/mcp/services/{service_name}")
async def get_mcp_service_detail(service_name: str):
    """获取指定MCP服务的详细信息"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 使用动态服务池查询
        service_info = naga_agent.mcp.query_service_by_name(service_name)
        if not service_info:
            raise HTTPException(status_code=404, detail=f"服务 {service_name} 不存在")
        
        return {
            "status": "success",
            "service": service_info
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取MCP服务详情错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取服务详情失败: {str(e)}")

@app.get("/mcp/services/search/{capability}")
async def search_mcp_services(capability: str):
    """根据能力关键词搜索MCP服务"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 使用动态服务池查询
        matching_services = naga_agent.mcp.query_services_by_capability(capability)
        
        return {
            "status": "success",
            "capability": capability,
            "services": matching_services,
            "count": len(matching_services)
        }
    except Exception as e:
        print(f"搜索MCP服务错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"搜索服务失败: {str(e)}")

@app.get("/mcp/services/{service_name}/tools")
async def get_mcp_service_tools(service_name: str):
    """获取指定MCP服务的可用工具列表"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 使用动态服务池查询
        tools = naga_agent.mcp.get_service_tools(service_name)
        
        return {
            "status": "success",
            "service_name": service_name,
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        print(f"获取MCP服务工具列表错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {str(e)}")

@app.get("/mcp/statistics")
async def get_mcp_statistics():
    """获取MCP服务统计信息"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        # 使用动态服务池查询
        statistics = naga_agent.mcp.get_service_statistics()
        
        return {
            "status": "success",
            "statistics": statistics
        }
    except Exception as e:
        print(f"获取MCP统计信息错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

@app.post("/system/devmode")
async def toggle_devmode():
    """切换开发者模式"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    try:
        naga_agent.dev_mode = not naga_agent.dev_mode
        return {
            "status": "success",
            "dev_mode": naga_agent.dev_mode,
            "message": f"开发者模式已{'启用' if naga_agent.dev_mode else '禁用'}"
        }
    except Exception as e:
        print(f"切换开发者模式错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"切换开发者模式失败: {str(e)}")

@app.get("/memory/stats")
async def get_memory_stats():
    """获取记忆统计信息"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        if hasattr(naga_agent, 'memory_manager') and naga_agent.memory_manager:
            stats = naga_agent.memory_manager.get_memory_stats()
            return {
                "status": "success",
                "memory_stats": stats
            }
        else:
            return {
                "status": "success",
                "memory_stats": {"enabled": False, "message": "记忆系统未启用"}
            }
    except Exception as e:
        print(f"获取记忆统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取记忆统计失败: {str(e)}")

@app.get("/sessions")
async def get_sessions():
    """获取所有会话信息"""
    try:
        # 清理过期会话
        message_manager.cleanup_old_sessions()
        
        # 获取所有会话信息
        sessions_info = message_manager.get_all_sessions_info()
        
        return {
            "status": "success",
            "sessions": sessions_info,
            "total_sessions": len(sessions_info)
        }
    except Exception as e:
        print(f"获取会话信息错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取会话信息失败: {str(e)}")

@app.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话的详细信息"""
    try:
        session_info = message_manager.get_session_info(session_id)
        if not session_info:
            raise HTTPException(status_code=404, detail="会话不存在")
        
        return {
            "status": "success",
            "session_id": session_id,
            "session_info": session_info,
            "messages": message_manager.get_messages(session_id),
            "conversation_rounds": session_info["conversation_rounds"]
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取会话详情错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取会话详情失败: {str(e)}")

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话"""
    try:
        success = message_manager.delete_session(session_id)
        if success:
            return {
                "status": "success",
                "message": f"会话 {session_id} 已删除"
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except HTTPException:
        raise
    except Exception as e:
        print(f"删除会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")

@app.delete("/sessions")
async def clear_all_sessions():
    """清空所有会话"""
    try:
        count = message_manager.clear_all_sessions()
        return {
            "status": "success",
            "message": f"已清空 {count} 个会话"
        }
    except Exception as e:
        print(f"清空会话错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"清空会话失败: {str(e)}")

# 文件上传和文档处理接口
@app.post("/upload/document", response_model=FileUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    description: str = Form(None)
):
    """上传文档文件"""
    try:
        # 创建上传目录
        upload_dir = Path("uploaded_documents")
        upload_dir.mkdir(exist_ok=True)
        
        # 检查文件类型
        allowed_extensions = {".docx", ".doc", ".txt", ".pdf", ".md"}
        file_extension = Path(file.filename).suffix.lower()
        
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件类型: {file_extension}。支持的类型: {', '.join(allowed_extensions)}"
            )
        
        # 生成唯一文件名
        import time
        timestamp = str(int(time.time()))
        safe_filename = f"{timestamp}_{file.filename}"
        file_path = upload_dir / safe_filename
        
        # 保存文件
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 获取文件信息
        file_size = file_path.stat().st_size
        upload_time = time.strftime("%Y-%m-%d %H:%M:%S")
        
        return FileUploadResponse(
            filename=file.filename,
            file_path=str(file_path),
            file_size=file_size,
            file_type=file_extension,
            upload_time=upload_time,
            message=f"文件 '{file.filename}' 上传成功"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")

@app.post("/document/process")
async def process_document(request: DocumentProcessRequest):
    """处理上传的文档"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent未初始化")
    
    try:
        file_path = Path(request.file_path)
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {request.file_path}")
        
        # 根据文件类型和操作类型处理文档
        if file_path.suffix.lower() == ".docx":
            # 使用Word MCP服务处理
            mcp_request = {
                "service_name": "office_word_mcp",
                "task": {
                    "tool_name": "get_document_text",
                    "filename": str(file_path)
                }
            }
            
            # 调用MCP服务
            result = await naga_agent.mcp.handoff(mcp_request["service_name"], mcp_request["task"])
            
            if request.action == "read":
                return {
                    "status": "success",
                    "action": "read",
                    "file_path": request.file_path,
                    "content": result,
                    "message": "文档内容读取成功"
                }
            elif request.action == "analyze":
                # 让NAGA分析文档内容
                analysis_prompt = f"请分析以下文档内容，提供结构化的分析报告：\n\n{result}"
                analysis_result = await naga_agent.get_response(analysis_prompt)
                
                return {
                    "status": "success",
                    "action": "analyze",
                    "file_path": request.file_path,
                    "analysis": analysis_result,
                    "message": "文档分析完成"
                }
            elif request.action == "summarize":
                # 让NAGA总结文档内容
                summary_prompt = f"请总结以下文档内容，提供简洁的摘要：\n\n{result}"
                summary_result = await naga_agent.get_response(summary_prompt)
                
                return {
                    "status": "success",
                    "action": "summarize",
                    "file_path": request.file_path,
                    "summary": summary_result,
                    "message": "文档总结完成"
                }
        else:
            # 处理其他文件类型
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if request.action == "read":
                return {
                    "status": "success",
                    "action": "read",
                    "file_path": request.file_path,
                    "content": content,
                    "message": "文档内容读取成功"
                }
            elif request.action == "analyze":
                analysis_prompt = f"请分析以下文档内容，提供结构化的分析报告：\n\n{content}"
                analysis_result = await naga_agent.get_response(analysis_prompt)
                
                return {
                    "status": "success",
                    "action": "analyze",
                    "file_path": request.file_path,
                    "analysis": analysis_result,
                    "message": "文档分析完成"
                }
            elif request.action == "summarize":
                summary_prompt = f"请总结以下文档内容，提供简洁的摘要：\n\n{content}"
                summary_result = await naga_agent.get_response(summary_prompt)
                
                return {
                    "status": "success",
                    "action": "summarize",
                    "file_path": request.file_path,
                    "summary": summary_result,
                    "message": "文档总结完成"
                }
        
    except Exception as e:
        print(f"文档处理错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")

@app.get("/documents/list")
async def list_uploaded_documents():
    """获取已上传的文档列表"""
    try:
        upload_dir = Path("uploaded_documents")
        if not upload_dir.exists():
            return {
                "status": "success",
                "documents": [],
                "total": 0
            }
        
        documents = []
        for file_path in upload_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                documents.append({
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "file_size": stat.st_size,
                    "file_type": file_path.suffix.lower(),
                    "upload_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                })
        
        # 按上传时间排序
        documents.sort(key=lambda x: x["upload_time"], reverse=True)
        
        return {
            "status": "success",
            "documents": documents,
            "total": len(documents)
        }
        
    except Exception as e:
        print(f"获取文档列表错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取文档列表失败: {str(e)}")

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

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态 - 基于博弈论的任务管理功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        task_status = await task_scheduler.get_task_status(task_id)
        if not task_status:
            raise HTTPException(status_code=404, detail="任务未找到")
        
        return task_status
    except Exception as e:
        print(f"获取任务状态错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.get("/tasks")
async def list_tasks():
    """获取任务列表 - 基于博弈论的任务管理功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        running_tasks = await task_scheduler.get_running_tasks()
        return {
            "status": "success",
            "tasks": running_tasks,
            "count": len(running_tasks)
        }
    except Exception as e:
        print(f"获取任务列表错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.get("/computer-use/status")
async def get_computer_use_status():
    """获取电脑控制状态 - 基于博弈论的电脑控制管理功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        status = task_scheduler.get_computer_use_status()
        return {
            "status": "success",
            "computer_use": status
        }
    except Exception as e:
        print(f"获取电脑控制状态错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.post("/computer-use/schedule")
async def schedule_computer_use_task(request: Dict[str, Any]):
    """调度电脑控制任务 - 基于博弈论的computer_use调度功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        import uuid
        
        task_scheduler = get_task_scheduler()
        
        task_id = str(uuid.uuid4())
        instruction = request.get("instruction", "")
        screenshot = request.get("screenshot")
        session_id = request.get("session_id")
        
        if not instruction:
            raise HTTPException(status_code=400, detail="缺少instruction参数")
        
        await task_scheduler.schedule_computer_use_task(task_id, instruction, screenshot, session_id)
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": "电脑控制任务已调度"
        }
    except Exception as e:
        print(f"调度电脑控制任务错误: {e}")
        raise HTTPException(status_code=500, detail=f"调度失败: {str(e)}")

@app.get("/capabilities")
async def get_capabilities():
    """获取能力列表 - 基于博弈论的能力管理功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        capabilities = await task_scheduler.refresh_capabilities()
        return {
            "status": "success",
            "capabilities": capabilities
        }
    except Exception as e:
        print(f"获取能力列表错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.get("/mcp/availability")
async def get_mcp_availability():
    """获取MCP可用性 - 基于博弈论的能力检查功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        availability = task_scheduler.get_mcp_availability()
        return availability
    except Exception as e:
        print(f"获取MCP可用性错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.get("/computer-use/availability")
async def get_computer_use_availability():
    """获取电脑控制可用性 - 基于博弈论的能力检查功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        availability = task_scheduler.get_computer_use_availability()
        return availability
    except Exception as e:
        print(f"获取电脑控制可用性错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

@app.post("/agent/flags")
async def set_agent_flags(request: Dict[str, Any]):
    """设置代理标志 - 基于博弈论的策略控制功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        flags = {
            "mcp_enabled": request.get("mcp_enabled"),
            "computer_use_enabled": request.get("computer_use_enabled")
        }
        
        # 过滤掉None值
        flags = {k: v for k, v in flags.items() if v is not None}
        
        if flags:
            task_scheduler.set_agent_flags(flags)
        
        current_flags = task_scheduler.get_agent_flags()
        return {
            "status": "success",
            "agent_flags": current_flags
        }
    except Exception as e:
        print(f"设置代理标志错误: {e}")
        raise HTTPException(status_code=500, detail=f"设置失败: {str(e)}")

@app.get("/agent/flags")
async def get_agent_flags():
    """获取代理标志 - 基于博弈论的策略查询功能"""
    try:
        from agentserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        
        flags = task_scheduler.get_agent_flags()
        return {
            "status": "success",
            "agent_flags": flags
        }
    except Exception as e:
        print(f"获取代理标志错误: {e}")
        raise HTTPException(status_code=500, detail=f"获取失败: {str(e)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="NagaAgent API服务器")
    parser.add_argument("--host", default="127.0.0.1", help="服务器主机地址")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    parser.add_argument("--reload", action="store_true", help="开启自动重载")
    
    args = parser.parse_args()
    
    print(f"🚀 启动NagaAgent API服务器...")
    print(f"📍 地址: http://{args.host}:{args.port}")
    print(f"📚 文档: http://{args.host}:{args.port}/docs")
    print(f"🔄 自动重载: {'开启' if args.reload else '关闭'}")
    
    uvicorn.run(
        "api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        ws_ping_interval=None,
        ws_ping_timeout=None
    ) 