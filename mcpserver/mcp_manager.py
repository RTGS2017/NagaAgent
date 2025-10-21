import asyncio
import logging
import inspect
from typing import Dict, Optional, List, Any, Callable, Awaitable, Generic, TypeVar, Union, cast
from contextlib import AsyncExitStack
import sys
from pydantic import BaseModel, TypeAdapter
from dataclasses import dataclass
import json
from datetime import datetime
import importlib,os,inspect # 自动注册相关
from pathlib import Path

from nagaagent_core.core import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcpserver.mcp_registry import MCP_REGISTRY # MCP服务注册表

from system.config import config, AI_NAME, logger

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if config.system.debug else getattr(logging, config.system.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 屏蔽HTTP库的DEBUG日志
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

_builtin_print=print
print=lambda *a,**k:sys.stderr.write('[print] '+(' '.join(map(str,a)))+'\n')

TContext = TypeVar("TContext")
THandoffInput = TypeVar("THandoffInput")

class HandoffError(Exception):
    """Handoff基础异常类"""
    pass

class ModelBehaviorError(HandoffError):
    """模型行为异常"""
    pass

class HandoffValidationError(HandoffError):
    """Handoff数据验证异常"""
    pass

class HandoffConnectionError(HandoffError):
    """Handoff连接异常"""
    pass

@dataclass
class HandoffInputData:
    """Handoff输入数据结构"""
    input_history: Union[str, tuple[Any, ...]] #历史输入
    pre_handoff_items: tuple[Any, ...] #handoff前的items
    new_items: tuple[Any, ...] #当前turn生成的items
    context: Optional[Dict[str, Any]] = None #上下文数据
    metadata: Optional[Dict[str, Any]] = None #元数据

    @classmethod
    def create(cls, 
        input_history: Any = None,
        pre_items: Any = None,
        new_items: Any = None,
        context: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None
    ) -> 'HandoffInputData':
        """创建HandoffInputData实例"""
        return cls(
            input_history=input_history if input_history is not None else (),
            pre_handoff_items=pre_items if pre_items is not None else (),
            new_items=new_items if new_items is not None else (),
            context=context,
            metadata=metadata
        )

def remove_tools_filter(messages: list) -> list:
    """移除工具调用的过滤器函数"""
    return [
        msg for msg in messages
        if not any(tool in str(msg) for tool in ["[tool]", "[handoff]"])
    ]

@dataclass
class Handoff(Generic[TContext]):
    """Handoff配置类"""
    tool_name: str
    tool_description: str
    input_json_schema: dict[str, Any]
    agent_name: str
    on_invoke_handoff: Callable[[Any, str], Awaitable[Any]]
    strict_json_schema: bool = True
    
    async def invoke(self, ctx: Any, input_json: Optional[str] = None) -> Any:
        """执行handoff调用"""
        if self.input_json_schema and not input_json:
            raise ModelBehaviorError("Handoff需要输入但未提供")
            
        try:
            if input_json:
                # 验证输入
                type_adapter = TypeAdapter(dict[str, Any])
                validated_input = type_adapter.validate_json(
                    input_json,
                    strict=self.strict_json_schema
                )
            else:
                validated_input = None
                
            # 验证回调函数签名
            sig = inspect.signature(self.on_invoke_handoff)
            if len(sig.parameters) != 2:
                raise HandoffValidationError(
                    "Handoff回调函数必须接受两个参数(context, input)"
                )
                
            return await self.on_invoke_handoff(ctx, validated_input)
        except Exception as e:
            if isinstance(e, HandoffError):
                raise
            raise HandoffError(f"Handoff执行失败: {str(e)}")

class MCPManager:
    """MCP服务管理器，负责管理所有MCP服务的连接和调用"""
    
    def __init__(self):
        """初始化MCP管理器"""
        self.services = {}
        self.tools_cache = {}
        self.exit_stack = AsyncExitStack()
        self.handoffs = {} # 服务对应的handoff对象
        self.handoff_filters = {} # 服务对应的handoff过滤器
        self.handoff_callbacks = {} # 服务对应的handoff回调
        self.logger = logging.getLogger("MCPManager")
        sys.stderr.write("MCPManager初始化\n")
        

        
    def register_handoff(
        self,
        service_name: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        agent_name: str,
        filters=None,
        strict_schema=False
    ):
        """注册handoff服务"""
        if service_name in self.services:
            sys.stderr.write(f"服务{service_name}已注册，跳过重复注册\n")
            return
        self.services[service_name] = {
            "tool_name": tool_name,
            "tool_description": tool_description,
            "input_schema": input_schema,
            "agent_name": agent_name,
            "filter_fn": remove_tools_filter,  # 使用函数而不是类实例
            "strict_schema": strict_schema
        }
        
    async def _default_handoff_callback(
        self,
        ctx: Any,
        input_json: Optional[str]
    ) -> Any:
        """默认的handoff回调处理"""
        return None
            
    async def handoff(
        self,
        service_name: str,
        task: dict,
        input_history: Any = None,
        pre_items: Any = None,
        new_items: Any = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """执行handoff"""
        try:
            # 通知handoff调用开始
            
            # 修复中文编码问题
            task_json = json.dumps(task, ensure_ascii=False)
            sys.stderr.write(f"执行handoff: service={service_name}, task={task_json}\n".encode('utf-8', errors='replace').decode('utf-8'))
            
            if service_name not in self.services:
                raise ValueError(f"未注册的服务: {service_name}")
                
            service = self.services[service_name]
            # 只打印服务配置中的安全字段
            safe_service_info = {
                "name": service.get("name", ""),
                "description": service.get("description", ""),
                "agent_name": service.get("agent_name", ""),
                "strict_schema": service.get("strict_schema", False)
            }
            safe_info_json = json.dumps(safe_service_info, ensure_ascii=False)
            sys.stderr.write(f"找到服务配置: {safe_info_json}\n".encode('utf-8', errors='replace').decode('utf-8'))
            
            # 简单验证必需字段
            if service["strict_schema"]:
                required_fields = service["input_schema"].get("required", [])
                for field in required_fields:
                    if field not in task:
                        raise ValueError(f"缺少必需字段: {field}")
                
            # 应用过滤器函数
            if "messages" in task and service["filter_fn"]:
                try:
                    task["messages"] = service["filter_fn"](task["messages"])
                except Exception as e:
                    sys.stderr.write(f"消息过滤失败: {e}\n".encode('utf-8', errors='replace').decode('utf-8'))
                    # 继续执行，使用原始消息
                
            # 创建代理实例
            from mcpserver.mcp_registry import MCP_REGISTRY # 统一注册中心
            agent_name = service["agent_name"]
            agent = MCP_REGISTRY.get(agent_name)
            if not agent:
                raise ValueError(f"找不到已注册的Agent实例: {agent_name}")
            sys.stderr.write(f"使用注册中心中的Agent实例: {agent_name}\n".encode('utf-8', errors='replace').decode('utf-8'))
            # 执行handoff
            sys.stderr.write("开始执行代理handoff\n".encode('utf-8', errors='replace').decode('utf-8'))
            result = await agent.handle_handoff(task)
            sys.stderr.write(f"代理handoff执行结果: {result}\n".encode('utf-8', errors='replace').decode('utf-8'))
            
            # 通知handoff调用成功
            
            return result
            
        except Exception as e:
            error_msg = f"Handoff执行失败: {str(e)}"
            sys.stderr.write(f"{error_msg}\n".encode('utf-8', errors='replace').decode('utf-8'))
            import traceback
            traceback.print_exc(file=sys.stderr)
            
            # 通知handoff调用失败
            
            return json.dumps({
                "status": "error",
                "message": error_msg
            }, ensure_ascii=False)
            
    async def connect_service(self, service_name: str) -> Optional[ClientSession]:
        """连接到指定的MCP服务
        
        Args:
            service_name: MCP服务名称
            
        Returns:
            Optional[ClientSession]: 成功返回会话对象，失败返回None
        """
        # 直接返回None，或根据MCP_REGISTRY判断服务是否存在
        if service_name not in MCP_REGISTRY:
            logger.warning(f"MCP服务 {service_name} 不存在")
            return None
            
        # 如果已连接，直接返回会话
        if service_name in self.services:
            return self.services[service_name]
            
        service_config = MCP_REGISTRY[service_name]
        command = "python" if service_config["type"] == "python" else "node"
        
        try:
            logger.info(f"正在连接MCP服务: {service_name}")
            server_params = StdioServerParameters(
                command=command,
                args=[service_config["script_path"]],
                env=None
            )
            
            # 创建服务连接
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport
            
            # 创建并初始化会话
            session = await self.exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            await session.initialize()
            
            # 缓存会话
            self.services[service_name] = session
            logger.info(f"MCP服务 {service_name} 连接成功")
            return session
            
        except Exception as e:
            logger.error(f"连接MCP服务 {service_name} 失败: {str(e)}")
            import traceback;traceback.print_exc(file=sys.stderr)
            return None
            
    async def get_service_tools(self, service_name: str) -> list:
        """获取指定MCP服务的可用工具列表
        
        Args:
            service_name: MCP服务名称
            
        Returns:
            list: 工具列表
        """
        # 检查缓存
        if service_name in self.tools_cache:
            return self.tools_cache[service_name]
            
        session = await self.connect_service(service_name)
        if not session:
            return []
            
        try:
            response = await session.list_tools()
            tools = response.tools
            # 缓存工具列表
            self.tools_cache[service_name] = tools
            return tools
        except Exception as e:
            logger.error(f"获取服务 {service_name} 的工具列表失败: {str(e)}")
            import traceback;traceback.print_exc(file=sys.stderr)
            return []
            
    async def call_service_tool(self, service_name: str, tool_name: str, args: dict):
        """调用指定MCP服务的工具
        
        Args:
            service_name: MCP服务名称
            tool_name: 工具名称
            args: 工具参数
            
        Returns:
            工具调用结果
        """
        session = await self.connect_service(service_name)
        if not session:
            return None
            
        try:
            logger.debug(f"调用工具: {service_name}.{tool_name} 参数: {args}")
            result = await session.call_tool(tool_name, args)
            logger.debug(f"工具调用结果: {result}")
            return result
        except Exception as e:
            logger.error(f"调用工具 {service_name}.{tool_name} 失败: {str(e)}")
            import traceback;traceback.print_exc(file=sys.stderr)
            return None

    async def unified_call(self, service_name: str, tool_name: str, args: dict):
        """简化的统一调用接口 - 只支持MCP服务
        
        Args:
            service_name: 服务名称
            tool_name: 工具名称
            args: 工具参数
            
        Returns:
            调用结果
        """
        try:
            # 只支持MCP服务调用（通过MCP_REGISTRY）
            if service_name in MCP_REGISTRY:
                agent = MCP_REGISTRY[service_name]
                if hasattr(agent, tool_name):
                    method = getattr(agent, tool_name)
                    if callable(method):
                        # 过滤掉元数据字段，只保留实际参数
                        filtered_args = {k: v for k, v in args.items() 
                                       if k not in ['tool_name', 'service_name', 'agentType']}
                        
                        logger.info(f"MCP调用: {service_name}.{tool_name} with filtered_args: {filtered_args}")
                        
                        # 调用方法
                        if asyncio.iscoroutinefunction(method):
                            result = await method(**filtered_args)
                        else:
                            result = method(**filtered_args)
                        
                        logger.info(f"MCP调用结果: {result}")
                        return result
                else:
                    logger.error(f"MCP服务 {service_name} 没有工具 {tool_name}")
                    return f"工具 {tool_name} 不存在于服务 {service_name}"
            else:
                logger.error(f"MCP服务 {service_name} 未注册")
                return f"服务 {service_name} 未注册"
            
        except Exception as e:
            logger.error(f"MCP调用失败 {service_name}.{tool_name}: {str(e)}")
            return f"调用失败: {str(e)}"
            
    def get_available_services(self) -> list:
        """获取所有可用的MCP服务列表
        
        Returns:
            list: 可用服务列表
        """
        from mcpserver.mcp_registry import get_all_services_info # 动态服务池查询
        services_info = get_all_services_info()
        
        return [
            {
                "name": name,
                "description": info.get('description', ''),
                "display_name": info.get('display_name', name),
                "version": info.get('version', '1.0.0'),
                "available_tools": info.get('available_tools', []),
                "id": name
            }
            for name, info in services_info.items()
        ]
            
    def get_available_services_filtered(self) -> dict:
        """获取过滤后的服务列表，分为MCP服务和Agent服务
        
        Returns:
            dict: 包含mcp_services和agent_services的服务列表
        """
        from mcpserver.mcp_registry import get_all_services_info, get_service_statistics # 动态服务池查询
        
        mcp_services = []
        agent_services = []
        
        # 从动态服务池获取所有已注册的MCP服务信息
        services_info = get_all_services_info()
        for name, info in services_info.items():
            service_info = {
                "name": name,
                "description": info.get('description', ''),
                "display_name": info.get('display_name', name),
                "version": info.get('version', '1.0.0'),
                "available_tools": info.get('available_tools', []),
                "id": name
            }
            # 动态服务池中的服务都是MCP类型，归类为mcp_services
            mcp_services.append(service_info)
        
        # 从handoff服务中获取Agent服务信息（这些是handoff配置）
        for service_name, service_config in self.services.items():
            agent_service_info = {
                "name": service_name,
                "description": service_config.get("tool_description", ""),
                "tool_name": service_config.get("tool_name", ""),
                "id": service_name
            }
            # handoff服务配置归类为agent_services
            agent_services.append(agent_service_info)
        
        return {
            "mcp_services": mcp_services,
            "agent_services": agent_services
        }
    
    def query_service_by_name(self, service_name: str) -> Optional[Dict[str, Any]]:
        """根据服务名称查询服务详细信息
        
        Args:
            service_name: 服务名称
            
        Returns:
            Optional[Dict[str, Any]]: 服务详细信息
        """
        from mcpserver.mcp_registry import get_service_info # 动态服务池查询
        return get_service_info(service_name)
    
    def query_services_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """根据能力关键词查询服务
        
        Args:
            capability: 能力关键词
            
        Returns:
            List[Dict[str, Any]]: 匹配的服务列表
        """
        from mcpserver.mcp_registry import query_services_by_capability, get_service_info # 动态服务池查询
        
        matching_service_names = query_services_by_capability(capability)
        matching_services = []
        
        for service_name in matching_service_names:
            service_info = get_service_info(service_name)
            if service_info:
                matching_services.append({
                    "name": service_name,
                    "description": service_info.get('description', ''),
                    "display_name": service_info.get('display_name', service_name),
                    "version": service_info.get('version', '1.0.0'),
                    "available_tools": service_info.get('available_tools', [])
                })
        
        return matching_services
    
    def get_service_statistics(self) -> Dict[str, Any]:
        """获取服务统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        from mcpserver.mcp_registry import get_service_statistics # 动态服务池查询
        return get_service_statistics()
    
    def get_service_tools(self, service_name: str) -> List[Dict[str, Any]]:
        """获取指定服务的可用工具列表
        
        Args:
            service_name: 服务名称
            
        Returns:
            List[Dict[str, Any]]: 工具列表
        """
        from mcpserver.mcp_registry import get_available_tools # 动态服务池查询
        return get_available_tools(service_name)
            
    def format_available_services(self) -> str:
        """格式化可用服务列表为字符串
        
        Returns:
            str: 格式化后的服务列表字符串
        """
        from mcpserver.mcp_registry import get_all_services_info # 动态服务池查询
        
        services_info = get_all_services_info()
        formatted_services = []
        
        for name, info in services_info.items():
            description = info.get('description', '')
            tools = info.get('available_tools', [])
            tool_names = [tool.get('name', '') for tool in tools]
            
            if description:
                formatted_services.append(f"- {name}: {description}")
                if tool_names:
                    formatted_services.append(f"  可用工具: {', '.join(tool_names)}")
            else:
                formatted_services.append(f"- {name}")
        
        return "\n".join(formatted_services)
            
    async def cleanup(self):
        """清理所有MCP服务连接"""
        logger.info("正在清理MCP服务连接...")
        try:
            await self.exit_stack.aclose()
            self.services.clear();self.tools_cache.clear()
            logger.info("MCP服务连接清理完成")
        except Exception as e:
            logger.error(f"清理MCP服务连接时出错: {str(e)}")
            import traceback;traceback.print_exc(file=sys.stderr)

    def get_mcp(self, name): return MCP_REGISTRY.get(name) # 获取MCP服务
    def list_mcps(self): return list(MCP_REGISTRY.keys()) # 列出所有MCP服务 

    def auto_register_services(self):
        """自动注册所有MCP服务和handoff"""
        try:
            # 新的动态注册系统已经自动扫描并注册了所有MCP服务
            # 不再需要手动注册handoff服务
            sys.stderr.write("✅ MCP服务已通过动态扫描自动注册完成\n")
        except Exception as e:
            sys.stderr.write(f"❌ 自动注册服务失败: {e}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)

_MCP_MANAGER=None
def get_mcp_manager():
    global _MCP_MANAGER
    if not _MCP_MANAGER:_MCP_MANAGER=MCPManager()
    return _MCP_MANAGER 