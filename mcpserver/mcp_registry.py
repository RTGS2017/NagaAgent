# mcp_registry.py # 动态扫描JSON元数据文件注册MCP服务
import sys
from typing import Dict, Any, Optional, List

# 从稳定模块导入MCP管理功能
from nagaagent_core.stable.mcp import (
    scan_and_register_mcp_agents,
    MCP_REGISTRY,
    MANIFEST_CACHE
)

def get_service_info(service_name: str) -> Optional[Dict[str, Any]]:
    """获取指定服务的详细信息
    
    Args:
        service_name: 服务名称
        
    Returns:
        Optional[Dict[str, Any]]: 服务信息，包含manifest和实例信息
    """
    if service_name not in MCP_REGISTRY:
        return None
        
    manifest = MANIFEST_CACHE.get(service_name, {})
    instance = MCP_REGISTRY[service_name]
    
    return {
        "name": service_name,
        "manifest": manifest,
        "instance": instance,
        "description": manifest.get('description', ''),
        "display_name": manifest.get('displayName', service_name),
        "version": manifest.get('version', '1.0.0'),
        "capabilities": manifest.get('capabilities', {}),
        "available_tools": get_available_tools(service_name)
    }

def get_available_tools(service_name: str) -> List[Dict[str, Any]]:
    """获取指定服务可用的工具列表
    
    Args:
        service_name: 服务名称
        
    Returns:
        List[Dict[str, Any]]: 工具列表
    """
    if service_name not in MANIFEST_CACHE:
        return []
        
    manifest = MANIFEST_CACHE[service_name]
    capabilities = manifest.get('capabilities', {})
    invocation_commands = capabilities.get('invocationCommands', [])
    
    tools = []
    for cmd in invocation_commands:
        tools.append({
            "name": cmd.get('command', ''),
            "description": cmd.get('description', ''),
            "example": cmd.get('example', ''),
        })
    
    return tools

def get_all_services_info() -> Dict[str, Any]:
    """获取所有已注册服务的详细信息
    
    Returns:
        Dict[str, Any]: 所有服务信息
    """
    services_info = {}
    for service_name in MCP_REGISTRY.keys():
        service_info = get_service_info(service_name)
        if service_info:
            services_info[service_name] = service_info
    
    return services_info

def query_services_by_capability(capability: str) -> List[str]:
    """根据能力查询服务
    
    Args:
        capability: 能力关键词
        
    Returns:
        List[str]: 匹配的服务名称列表
    """
    matching_services = []
    
    for service_name, manifest in MANIFEST_CACHE.items():
        description = manifest.get('description', '').lower()
        display_name = manifest.get('displayName', '').lower()
        
        if capability.lower() in description or capability.lower() in display_name:
            matching_services.append(service_name)
    
    return matching_services

def get_service_statistics() -> Dict[str, Any]:
    """获取服务统计信息
    
    Returns:
        Dict[str, Any]: 统计信息
    """
    total_services = len(MCP_REGISTRY)
    total_tools = sum(len(get_available_tools(name)) for name in MCP_REGISTRY.keys())
    
    return {
        "total_services": total_services,
        "total_tools": total_tools,
        "registered_services": list(MCP_REGISTRY.keys()),
        "last_update": "动态更新"
    }

# 自动扫描并注册
def auto_register_mcp():
    """自动注册所有MCP服务"""
    registered = scan_and_register_mcp_agents()
    sys.stderr.write(f"MCP注册完成，共注册 {len(registered)} 个服务: {registered}\n")
    return registered

# 延迟自动注册，避免循环导入死锁
# auto_register_mcp()  # 注释掉立即执行，改为在需要时调用

