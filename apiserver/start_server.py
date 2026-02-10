#!/usr/bin/env python3
"""
NagaAgent 服务启动脚本
支持启动API服务器和LLM服务
"""

import asyncio
import sys
import os
import argparse
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import uvicorn

async def start_api_server():
    """启动API服务器"""
    
    # 从环境变量获取配置，回退到config
    host = os.getenv("API_SERVER_HOST", "127.0.0.1")
    try:
        from system.config import get_server_port
        default_port = get_server_port("api_server")
    except ImportError:
        default_port = 8000
    port = int(os.getenv("API_SERVER_PORT", str(default_port)))
    reload = os.getenv("API_SERVER_RELOAD", "False").lower() == "true"
    
    print("启动NagaAgent API服务器...")
    print(f"地址: http://{host}:{port}")
    print(f"文档: http://{host}:{port}/docs")
    print(f"自动重载: {'开启' if reload else '关闭'}")
    
    # 启动服务器
    uvicorn.run(
        "apiserver.api_server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        ws_ping_interval=None,
        ws_ping_timeout=None
    )

async def start_llm_service():
    """启动LLM服务"""
    
    # 从环境变量获取配置，回退到config
    host = os.getenv("LLM_SERVICE_HOST", "127.0.0.1")
    try:
        from system.config import get_server_port
        default_port = get_server_port("agent_server")
    except ImportError:
        default_port = 8001
    port = int(os.getenv("LLM_SERVICE_PORT", str(default_port)))
    reload = os.getenv("LLM_SERVICE_RELOAD", "False").lower() == "true"
    
    print("启动LLM服务...")
    print(f"地址: http://{host}:{port}")
    print(f"文档: http://{host}:{port}/docs")
    print(f"自动重载: {'开启' if reload else '关闭'}")
    
    # 启动服务器
    uvicorn.run(
        "apiserver.llm_service:llm_app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        ws_ping_interval=None,
        ws_ping_timeout=None
    )

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="NagaAgent 服务启动器")
    parser.add_argument("service", choices=["api", "llm", "both"], 
                       help="要启动的服务: api(API服务器), llm(LLM服务), both(两个都启动)")
    
    args = parser.parse_args()
    
    if args.service == "api":
        await start_api_server()
    elif args.service == "llm":
        await start_llm_service()
    elif args.service == "both":
        print("启动所有服务...")
        print("注意: 同时启动多个服务需要不同的端口配置")
        try:
            from system.config import get_server_port
            api_port = get_server_port("api_server")
            agent_port = get_server_port("agent_server")
            print(f"API服务器: http://127.0.0.1:{api_port}")
            print(f"LLM服务: http://127.0.0.1:{agent_port}")
        except ImportError:
            print("API服务器: http://127.0.0.1:8000")
            print("LLM服务: http://127.0.0.1:8001")
        
        # 这里可以实现同时启动多个服务的逻辑
        # 目前先启动API服务器
        await start_api_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n收到停止信号，正在关闭服务...")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1) 