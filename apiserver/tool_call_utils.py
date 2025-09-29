#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具调用工具模块 - 独立的工具调用解析和执行逻辑
避免循环依赖，提供统一的工具调用接口
"""

import re
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger("ToolCallUtils")

def parse_tool_calls(content: str) -> list:
    """解析JSON格式工具调用，支持MCP和Agent两种类型"""
    tool_calls = []
    # 支持中英文括号的正则表达式
    pattern = r'[｛{]([\s\S]*?)[｝}]'
    matches = re.finditer(pattern, content)
    for match in matches:
        try:
            # 将中文括号替换为英文括号
            json_content = "{" + match.group(1).strip() + "}"
            
            # 处理尾随逗号问题
            # 移除对象末尾的尾随逗号
            json_content = re.sub(r',(\s*[}\]])', r'\1', json_content)
            
            tool_args = json.loads(json_content)
            
            agent_type = tool_args.get('agentType', 'mcp').lower()
            if agent_type == 'agent':
                agent_name = tool_args.get('agent_name')
                prompt = tool_args.get('prompt')
                if agent_name and prompt:
                    tool_call = {
                        'name': 'agent_call',
                        'args': {
                            'agentType': 'agent',
                            'agent_name': agent_name,
                            'prompt': prompt
                        }
                    }
                    tool_calls.append(tool_call)
            else:
                tool_name = tool_args.get('tool_name')
                if tool_name:
                    if 'service_name' in tool_args:
                        tool_call = {
                            'name': tool_name,
                            'args': tool_args
                        }
                        tool_calls.append(tool_call)
                    else:
                        service_name = tool_name
                        tool_args['service_name'] = service_name
                        tool_args['agentType'] = 'mcp'
                        tool_call = {
                            'name': tool_name,
                            'args': tool_args
                        }
                        tool_calls.append(tool_call)
        except json.JSONDecodeError:
            continue
    return tool_calls

async def execute_tool_calls(tool_calls: list, mcp_manager) -> str:
    """执行工具调用"""
    results = []
    for i, tool_call in enumerate(tool_calls):
        try:
            print(f"[DEBUG] 开始执行工具调用{i+1}: {tool_call['name']}")
            
            tool_name = tool_call['name']
            args = tool_call['args']
            agent_type = args.get('agentType', 'mcp').lower()
            
            print(f"[DEBUG] 工具类型: {agent_type}, 参数: {args}")
            
            if agent_type == 'agent':
                try:
                    from agentserver.core.agent_manager import get_agent_manager
                    agent_manager = get_agent_manager()
                    
                    agent_name = args.get('agent_name')
                    prompt = args.get('prompt')
                    
                    print(f"[DEBUG] Agent调用: {agent_name}, prompt: {prompt}")
                    
                    if not agent_name or not prompt:
                        result = "Agent调用失败: 缺少agent_name或prompt参数"
                    else:
                        result = await agent_manager.call_agent(agent_name, prompt)
                        if result.get("status") == "success":
                            result = result.get("result", "")
                        else:
                            result = f"Agent调用失败: {result.get('error', '未知错误')}"
                            
                except Exception as e:
                    result = f"Agent调用失败: {str(e)}"
                    
            else:
                service_name = args.get('service_name')
                actual_tool_name = args.get('tool_name', tool_name)
                tool_args = {k: v for k, v in args.items() 
                           if k not in ['service_name', 'agentType']}
                
                print(f"[DEBUG] MCP调用: service={service_name}, tool={actual_tool_name}, args={tool_args}")
                
                if not service_name:
                    result = "MCP服务调用失败: 缺少service_name参数"
                else:
                    result = await mcp_manager.unified_call(
                    service_name=service_name,
                    tool_name=actual_tool_name,
                    args=tool_args
                )
            
            print(f"[DEBUG] 工具调用{i+1}执行结果: {result}")
            results.append(f"来自工具 \"{tool_name}\" 的结果:\n{result}")
        except Exception as e:
            error_result = f"执行工具 {tool_call['name']} 时发生错误：{str(e)}"
            print(f"[DEBUG] 工具调用{i+1}执行异常: {error_result}")
            results.append(error_result)
    return "\n\n---\n\n".join(results)

async def tool_call_loop(messages: List[Dict], mcp_manager, llm_caller, is_streaming: bool = False, max_recursion: int = None, tool_calls_queue=None, callback_manager=None) -> Dict:
    """工具调用循环主流程 - 仅支持非流式处理（流式处理已移至StreamingToolCallExtractor）"""
    if max_recursion is None:
        max_recursion = 5
    
    recursion_depth = 0
    current_messages = messages.copy()
    current_ai_content = ''
    
    while recursion_depth < max_recursion:
        try:
            # 非流式模式：调用LLM获取完整内容
            if hasattr(llm_caller, '__code__') and llm_caller.__code__.co_argcount > 1:
                resp = await llm_caller(current_messages, use_stream=is_streaming)
            else:
                resp = await llm_caller(current_messages)
            
            current_ai_content = resp.get('content', '')
            
            print(f"[DEBUG] 第{recursion_depth + 1}轮LLM回复:")
            print(f"[DEBUG] 回复内容: {current_ai_content}")
            
            tool_calls = parse_tool_calls(current_ai_content)
            print(f"[DEBUG] 解析到工具调用数量: {len(tool_calls)}")
            
            if not tool_calls:
                print(f"[DEBUG] 无工具调用，退出循环")
                break
            
            # 执行工具调用
            for i, tool_call in enumerate(tool_calls):
                print(f"[DEBUG] 工具调用{i+1}: {tool_call}")
            
            tool_results = await execute_tool_calls(tool_calls, mcp_manager)
            
            # 工具调用执行完成，将结果传递给LLM继续处理
            current_messages.append({'role': 'assistant', 'content': current_ai_content})
            current_messages.append({'role': 'user', 'content': tool_results})
            recursion_depth += 1
        except Exception as e:
            print(f"工具调用循环错误: {e}")
            break
    
    return {
        'content': current_ai_content,
        'recursion_depth': recursion_depth,
        'messages': current_messages,
        'has_tool_results': False
    }

async def execute_single_tool_call(tool_call: dict, mcp_manager) -> str:
    """执行单个工具调用"""
    try:
        tool_name = tool_call['name']
        args = tool_call['args']
        agent_type = args.get('agentType', 'mcp').lower()
        
        if agent_type == 'agent':
            # Agent调用
            try:
                from agentserver.core.agent_manager import get_agent_manager
                agent_manager = get_agent_manager()
                
                agent_name = args.get('agent_name')
                prompt = args.get('prompt')
                
                if not agent_name or not prompt:
                    return "Agent调用失败: 缺少agent_name或prompt参数"
                
                result = await agent_manager.call_agent(agent_name, prompt)
                if result.get("status") == "success":
                    return result.get("result", "")
                else:
                    return f"Agent调用失败: {result.get('error', '未知错误')}"
                    
            except Exception as e:
                return f"Agent调用失败: {str(e)}"
                
        else:
            # MCP调用
            service_name = args.get('service_name')
            actual_tool_name = args.get('tool_name', tool_name)
            tool_args = {k: v for k, v in args.items() 
                       if k not in ['service_name', 'agentType']}
            
            if not service_name:
                return "MCP服务调用失败: 缺少service_name参数"
            
            result = await mcp_manager.unified_call(
                service_name=service_name,
                tool_name=actual_tool_name,
                args=tool_args
            )
            
            return f"来自工具 \"{tool_name}\" 的结果:\n{result}"
            
    except Exception as e:
        return f"执行工具 {tool_call['name']} 时发生错误：{str(e)}" 