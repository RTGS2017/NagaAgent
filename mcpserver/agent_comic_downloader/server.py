"""
Comic Downloader MCP Server
提供HTTP API接口的MCP服务器
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

try:
    from .comic_service import download_comic, search_comic_by_name, search_comic_by_author, get_comic_detail
except ImportError:
    from comic_service import download_comic, search_comic_by_name, search_comic_by_author, get_comic_detail

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="Comic Downloader MCP Server",
    description="A simplified comic downloader that downloads comics to desktop",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class DownloadRequest(BaseModel):
    album_id: str


class SearchComicRequest(BaseModel):
    comic_name: str
    page: int = 1

class SearchAuthorRequest(BaseModel):
    author_name: str
    page: int = 1

# 响应模型
class DownloadResponse(BaseModel):
    success: bool
    album_id: str
    message: str
    album_title: Optional[str] = None
    album_author: Optional[str] = None
    download_path: Optional[str] = None
    error: Optional[str] = None


class SearchResponse(BaseModel):
    success: bool
    query_info: Optional[str] = None
    total: Optional[int] = None
    page: Optional[int] = None
    current_page: Optional[int] = None
    comics: List[Dict[str, Any]] = []
    message: str
    error: Optional[str] = None

class DetailResponse(BaseModel):
    success: bool
    comic: Optional[Dict[str, Any]] = None
    message: str
    error: Optional[str] = None

# API路由
@app.post("/download", response_model=DownloadResponse)
async def download_comic(request: DownloadRequest):
    """
    下载漫画
    
    Args:
        request: 包含漫画ID的请求
        
    Returns:
        下载结果
    """
    try:
        logger.info(f"收到下载请求: {request.album_id}")
        result = download_comic(request.album_id)
        
        return DownloadResponse(
            success=result.get('success', False),
            album_id=request.album_id,
            message=result.get('message', ''),
            album_title=result.get('result', {}).get('album_title'),
            album_author=result.get('result', {}).get('album_author'),
            download_path=result.get('result', {}).get('download_path'),
            error=result.get('error')
        )
        
    except Exception as e:
        logger.error(f"下载漫画时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/comic", response_model=SearchResponse)
async def search_comic(request: SearchComicRequest):
    """
    搜索漫画
    
    Args:
        request: 包含漫画名称和页码的请求
        
    Returns:
        搜索结果
    """
    try:
        logger.info(f"搜索漫画: {request.comic_name}, 页码: {request.page}")
        result = search_comic_by_name(request.comic_name, request.page)
        
        return SearchResponse(
            success=result.get('success', False),
            query_info=result.get('query_info'),
            total=result.get('total'),
            page=result.get('page'),
            current_page=result.get('current_page'),
            comics=result.get('comics', []),
            message=result.get('message', ''),
            error=result.get('error')
        )
        
    except Exception as e:
        logger.error(f"搜索漫画时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/author", response_model=SearchResponse)
async def search_author(request: SearchAuthorRequest):
    """
    搜索作者
    
    Args:
        request: 包含作者名称和页码的请求
        
    Returns:
        搜索结果
    """
    try:
        logger.info(f"搜索作者: {request.author_name}, 页码: {request.page}")
        result = search_comic_by_author(request.author_name, request.page)
        
        return SearchResponse(
            success=result.get('success', False),
            query_info=result.get('query_info'),
            total=result.get('total'),
            page=result.get('page'),
            current_page=result.get('current_page'),
            comics=result.get('comics', []),
            message=result.get('message', ''),
            error=result.get('error')
        )
        
    except Exception as e:
        logger.error(f"搜索作者时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/detail/{comic_id}", response_model=DetailResponse)
async def get_comic_detail_api(comic_id: str):
    """
    获取漫画详情
    
    Args:
        comic_id: 漫画ID
        
    Returns:
        漫画详情
    """
    try:
        logger.info(f"获取漫画详情: {comic_id}")
        result = get_comic_detail(comic_id)
        
        return DetailResponse(
            success=result.get('success', False),
            comic=result.get('comic'),
            message=result.get('message', ''),
            error=result.get('error')
        )
        
    except Exception as e:
        logger.error(f"获取漫画详情时发生错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """
    健康检查
    
    Returns:
        服务状态
    """
    return {"status": "healthy", "service": "comic_downloader"}

@app.get("/")
async def root():
    """
    根路径
    
    Returns:
        服务信息
    """
    return {
        "service": "Comic Downloader MCP Server",
        "version": "1.0.0",
        "description": "A simplified comic downloader that downloads comics to desktop",
        "endpoints": {
            "download": "POST /download",
            "search_comic": "POST /search/comic",
            "search_author": "POST /search/author",
            "comic_detail": "GET /detail/{comic_id}",
            "health": "GET /health"
        }
    }

def start_server(host: str = "localhost", port: int = 8080):
    """
    启动服务器
    
    Args:
        host: 主机地址
        port: 端口号
    """
    logger.info(f"启动Comic Downloader MCP服务器: http://{host}:{port}")
    uvicorn.run(
        app, 
        host=host, 
        port=port,
        ws_ping_interval=None,
        ws_ping_timeout=None
    )

if __name__ == "__main__":
    start_server() 