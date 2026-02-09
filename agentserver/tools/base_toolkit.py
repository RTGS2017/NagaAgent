#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础工具包类 - 适配agentserver架构
"""

import logging
from collections.abc import Callable
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ToolkitConfig:
    """工具包配置类"""
    
    def __init__(self, config: Dict[str, Any] = None, name: str = None):
        self.config = config or {}
        self.name = name or self.__class__.__name__
        self.mode = "builtin"
        self.activated_tools = None


class AsyncBaseToolkit:
    """工具包基类 - 适配agentserver架构"""

    def __init__(self, config: ToolkitConfig | dict | None = None):
        if not isinstance(config, ToolkitConfig):
            config = config or {}
            config = ToolkitConfig(config=config, name=self.__class__.__name__)

        self.config: ToolkitConfig = config
        self._tools_map: dict[str, Callable] = None

    @property
    def tools_map(self) -> dict[str, Callable]:
        """懒加载工具映射 - 收集通过@register_tool注册的工具"""
        if self._tools_map is None:
            self._tools_map = {}
            # 遍历类方法，找到带有@register_tool装饰器的方法
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if callable(attr) and getattr(attr, "_is_tool", False):
                    self._tools_map[attr._tool_name] = attr
        return self._tools_map

    def get_tools_map_func(self) -> dict[str, Callable]:
        """获取工具映射，根据配置过滤激活的工具"""
        if self.config.activated_tools:
            assert all(tool_name in self.tools_map for tool_name in self.config.activated_tools), (
                f"错误配置激活工具: {self.config.activated_tools}! 可用工具: {self.tools_map.keys()}"
            )
            tools_map = {tool_name: self.tools_map[tool_name] for tool_name in self.config.activated_tools}
        else:
            tools_map = self.tools_map
        return tools_map

    def get_tools_list(self) -> list[Dict[str, Any]]:
        """获取工具列表 - 适配agentserver格式"""
        tools_map = self.get_tools_map_func()
        tools = []
        for tool_name, tool_func in tools_map.items():
            tools.append({
                "name": tool_name,
                "function": tool_func,
                "description": tool_func.__doc__ or f"工具: {tool_name}"
            })
        return tools

    async def call_tool(self, name: str, arguments: dict) -> str:
        """通过名称调用工具"""
        tools_map = self.get_tools_map_func()
        if name not in tools_map:
            raise ValueError(f"工具 {name} 未找到")
        tool = tools_map[name]
        return await tool(**arguments)


def register_tool(name: str = None):
    """装饰器：将方法注册为工具
    
    用法:
        @register_tool  # 使用方法名
        @register_tool()  # 使用方法名  
        @register_tool("custom_name")  # 使用自定义名称
        
    参数:
        name (str, optional): 工具名称
    """

    def decorator(func: Callable):
        if isinstance(name, str):
            tool_name = name
        else:
            tool_name = func.__name__
        func._is_tool = True
        func._tool_name = tool_name
        return func

    if callable(name):
        return decorator(name)
    return decorator
