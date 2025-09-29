# mcp_registry.py # 动态扫描JSON元数据文件注册MCP服务
import json
import os
import importlib
import inspect
from pathlib import Path
import sys
from typing import Dict, Any, Optional, List

MCP_REGISTRY = {} # 全局MCP服务池
MANIFEST_CACHE = {} # 缓存manifest信息

def load_manifest_file(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """加载manifest文件"""
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"加载manifest文件失败 {manifest_path}: {e}\n")
        return None

def create_agent_instance(manifest: Dict[str, Any]) -> Optional[Any]:
    """根据manifest创建agent实例"""
    try:
        entry_point = manifest.get('entryPoint', {})
        module_name = entry_point.get('module')
        class_name = entry_point.get('class')
        
        if not module_name or not class_name:
            sys.stderr.write(f"manifest缺少entryPoint信息: {manifest.get('name', 'unknown')}\n")
            return None
            
        # 动态导入模块
        module = importlib.import_module(module_name)
        agent_class = getattr(module, class_name)
        
        # 创建实例
        instance = agent_class()
        return instance
        
    except Exception as e:
        sys.stderr.write(f"创建agent实例失败 {manifest.get('name', 'unknown')}: {e}\n")
        return None

def scan_and_register_mcp_agents(mcp_dir: str = 'mcpserver') -> list:
    """扫描目录中的JSON元数据文件，注册MCP类型的agent和Agent类型的agent"""
    d = Path(mcp_dir)
    registered_agents = []
    
    # 扫描所有agent-manifest.json文件
    for manifest_file in d.glob('**/agent-manifest.json'):
        try:
            # 加载manifest
            manifest = load_manifest_file(manifest_file)
            if not manifest:
                continue
                
            agent_type = manifest.get('agentType')
            agent_name = manifest.get('name')
            
            if not agent_name:
                sys.stderr.write(f"manifest缺少name字段: {manifest_file}\n")
                continue
            
            # 根据agentType进行分类处理
            if agent_type == 'mcp':
                # MCP类型：注册到MCP_REGISTRY
                MANIFEST_CACHE[agent_name] = manifest
                agent_instance = create_agent_instance(manifest)
                if agent_instance:
                    MCP_REGISTRY[agent_name] = agent_instance
                    registered_agents.append(agent_name)
                    
            elif agent_type == 'agent':
                # Agent类型：转交给AgentManager处理
                try:
                    from agentserver.core.agent_manager import get_agent_manager
                    agent_manager = get_agent_manager()
                    
                    # 从manifest构建Agent配置
                    agent_config = {
                        'model_id': manifest.get('modelId', 'deepseek-chat'),
                        'name': manifest.get('displayName', agent_name),
                        'base_name': agent_name,
                        'system_prompt': manifest.get('systemPrompt', f'You are a helpful AI assistant named {manifest.get("displayName", agent_name)}.'),
                        'max_output_tokens': manifest.get('maxOutputTokens', 8192),
                        'temperature': manifest.get('temperature', 0.7),
                        'description': manifest.get('description', f'Assistant {manifest.get("displayName", agent_name)}.'),
                        'model_provider': manifest.get('modelProvider', 'openai'),
                        'api_base_url': manifest.get('apiBaseUrl', ''),
                        'api_key': manifest.get('apiKey', '')
                    }
                    
                    # 注册到AgentManager
                    agent_manager._register_agent_from_manifest(agent_name, agent_config)
                    registered_agents.append(f"agent:{agent_name}")
                    sys.stderr.write(f"✅ 已注册Agent到AgentManager: {agent_name}\n")
                    
                except Exception as e:
                    sys.stderr.write(f"注册Agent到AgentManager失败 {agent_name}: {e}\n")
                    continue
                    
        except Exception as e:
            sys.stderr.write(f"处理manifest文件失败 {manifest_file}: {e}\n")
            continue
    
    return registered_agents

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
        "input_schema": manifest.get('inputSchema', {}),
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
            "input_schema": manifest.get('inputSchema', {})
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

# 执行自动注册
auto_register_mcp()

