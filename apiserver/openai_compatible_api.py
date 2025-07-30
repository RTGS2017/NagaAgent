#!/usr/bin/env python3
"""
OpenAI-compatible API for NagaAgent
Implements the OpenAI Chat Completions API specification
"""

import asyncio
import json
import os
import sys
import traceback
import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, AsyncGenerator, Union
from pydantic import BaseModel, Field

# Set logging levels for HTTP libraries
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import configuration system
from config import config
from ui.response_utils import extract_message

# Global NagaAgent instance - initialized during app lifespan
naga_agent = None

class ChatMessage(BaseModel):
    """OpenAI Chat Message format"""
    role: str
    content: Union[str, List[Dict]]

class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completion Request"""
    model: str = Field(default="naga-agent")
    messages: List[ChatMessage]
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[Union[str, List[str]]] = None
    presence_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: Optional[float] = Field(default=0.0, ge=-2.0, le=2.0)
    user: Optional[str] = None

class ChatCompletionChoice(BaseModel):
    """OpenAI Chat Completion Choice"""
    index: int
    message: ChatMessage
    finish_reason: Optional[str]

class ChatCompletionUsage(BaseModel):
    """OpenAI Chat Completion Usage"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    """OpenAI Chat Completion Response"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None

class ChatCompletionChunkChoice(BaseModel):
    """OpenAI Chat Completion Chunk Choice"""
    index: int
    delta: ChatMessage
    finish_reason: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    """OpenAI Chat Completion Chunk"""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global naga_agent
    try:
        print("[INFO] Initializing NagaAgent...")
        # Delayed import to avoid circular dependencies
        from conversation_core import NagaConversation
        naga_agent = NagaConversation()
        print("[SUCCESS] NagaAgent initialized")
        yield
    except Exception as e:
        print(f"[ERROR] NagaAgent initialization failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] Cleaning up resources...")
        if naga_agent and hasattr(naga_agent, 'mcp'):
            try:
                await naga_agent.mcp.cleanup()
            except Exception as e:
                print(f"[WARNING] Error cleaning up MCP resources: {e}")

# Create FastAPI application
app = FastAPI(
    title="NagaAgent OpenAI-Compatible API",
    description="OpenAI-compatible API for NagaAgent",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/v1/docs",
    redoc_url="/v1/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/v1/models")
async def list_models():
    """List available models"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent not initialized")
    
    return {
        "object": "list",
        "data": [
            {
                "id": config.api.model,
                "object": "model",
                "created": 0,
                "owned_by": "naga-agent"
            }
        ]
    }

@app.post("/v1/chat/completions", response_model=Union[ChatCompletionResponse, ChatCompletionChunk])
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint"""
    if not naga_agent:
        raise HTTPException(status_code=503, detail="NagaAgent not initialized")
    
    # Validate request
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages are required")
    
    # Extract user message (last user message)
    user_message = None
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break
    
    if not user_message:
        raise HTTPException(status_code=400, detail="No user message found")
    
    # Handle streaming response
    if request.stream:
        return EventSourceResponse(
            stream_response(user_message, request),
            media_type="text/event-stream"
        )
    
    # Handle non-streaming response
    return await generate_response(user_message, request)

async def stream_response(user_message: str, request: ChatCompletionRequest) -> AsyncGenerator[Dict, None]:
    """Stream response chunks"""
    try:
        # Process with NagaAgent
        response_chunks = []
        async for chunk in naga_agent.process(user_message):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                speaker, content = chunk
                if speaker == "娜迦":
                    content_str = str(content)
                    response_chunks.append(content_str)
                    
                    # Create and yield chunk
                    chunk_data = ChatCompletionChunk(
                        id="naga-agent-chunk",
                        created=int(asyncio.get_event_loop().time()),
                        model=request.model,
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatMessage(role="assistant", content=content_str)
                            )
                        ]
                    )
                    yield {"data": chunk_data.json()}
            else:
                content_str = str(chunk)
                response_chunks.append(content_str)
                
                # Create and yield chunk
                chunk_data = ChatCompletionChunk(
                    id="naga-agent-chunk",
                    created=int(asyncio.get_event_loop().time()),
                    model=request.model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatMessage(role="assistant", content=content_str)
                        )
                    ]
                )
                yield {"data": chunk_data.json()}
        
        # Send finish chunk
        finish_chunk = ChatCompletionChunk(
            id="naga-agent-chunk",
            created=int(asyncio.get_event_loop().time()),
            model=request.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=ChatMessage(role="", content=""),
                    finish_reason="stop"
                )
            ]
        )
        yield {"data": finish_chunk.json()}
        yield {"data": "[DONE]"}
        
    except Exception as e:
        print(f"Streaming error: {e}")
        traceback.print_exc()
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "server_error",
                "param": None,
                "code": 500
            }
        }
        yield {"data": json.dumps(error_chunk)}

async def generate_response(user_message: str, request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Generate complete response"""
    try:
        # Process with NagaAgent
        response_chunks = []
        async for chunk in naga_agent.process(user_message):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                speaker, content = chunk
                if speaker == "娜迦":
                    response_chunks.append(str(content))
            else:
                response_chunks.append(str(chunk))
        
        full_response = "".join(response_chunks)
        
        # Extract message using UI utility
        extracted_message = extract_message(full_response)
        
        # Create response
        response = ChatCompletionResponse(
            id="naga-agent-response",
            created=int(asyncio.get_event_loop().time()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=extracted_message),
                    finish_reason="stop"
                )
            ]
        )
        
        return response
        
    except Exception as e:
        print(f"Generation error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_ready": naga_agent is not None,
        "model": config.api.model
    }

# Root endpoint
@app.get("/")
async def root():
    """API root"""
    return {
        "name": "NagaAgent OpenAI-Compatible API",
        "version": "1.0.0",
        "docs": "/v1/docs"
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="NagaAgent OpenAI-Compatible API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Server host address")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    print(f"🚀 Starting NagaAgent OpenAI-Compatible API Server...")
    print(f"📍 Address: http://{args.host}:{args.port}")
    print(f"📚 Docs: http://{args.host}:{args.port}/v1/docs")
    print(f"🔄 Auto-reload: {'enabled' if args.reload else 'disabled'}")
    
    uvicorn.run(
        "openai_compatible_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )