#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
核心功能模块
包含MCP、OpenAI、环境变量、HTTP请求等核心功能
"""

# 重新导出核心依赖的功能
try:
    from mcp import ClientSession, StdioServerParameters  # 关键会话类型 #
    import mcp  # MCP模块 #
except ImportError:
    mcp = None  # type: ignore[assignment]
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
from openai import OpenAI, AsyncOpenAI  # OpenAI客户端 #
from dotenv import load_dotenv  # 环境变量加载 #
import requests  # HTTP请求 #
import aiohttp  # 异步HTTP #

__all__ = [
    "mcp",
    "OpenAI",
    "AsyncOpenAI",
    "load_dotenv",
    "requests",
    "aiohttp",
    "ClientSession",
    "StdioServerParameters",
]
