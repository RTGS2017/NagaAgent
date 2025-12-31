#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后台意图分析器 - 基于博弈论的对话分析机制
分析对话片段，提取潜在任务意图
"""

import asyncio
import time
from typing import Dict, Any, List, Optional
from system.config import config, logger
from langchain_openai import ChatOpenAI

from system.config import get_prompt

class ConversationAnalyzer:
    """
    对话分析器模块：分析语音对话轮次以推断潜在任务意图
    输入是跨服务器的文本转录片段；输出是零个或多个标准化的任务查询
    """
    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.api.model,
            base_url=config.api.base_url,
            api_key=config.api.api_key,
            temperature=0
        )

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        lines = []
        for m in messages[-config.api.max_history_rounds:]:
            role = m.get('role', 'user')
            # 修复：使用content字段而不是text字段
            content = m.get('content', '')
            # 清理文本，移除可能导致格式化问题的字符
            content = content.replace('{', '{{').replace('}', '}}')
            lines.append(f"{role}: {content}")
        conversation = "\n".join(lines)
        
        # 获取可用的工具信息（MCP服务 + agentserver工具包），注入到意图识别中
        try:
            tools_summary = []
            
            # 1. 获取 MCP 服务工具信息
            try:
                from nagaagent_core.stable.mcp import get_registered_services, get_service_info
                registered_services = get_registered_services()
                services_info = {name: get_service_info(name) for name in registered_services}
                
                for name, info in services_info.items():
                    if info:
                        display_name = info.get("displayName", name)
                        description = info.get("description", "")
                        capabilities = info.get("capabilities", {})
                        
                        # 提取工具名称 - 从invocationCommands中提取
                        tools = []
                        invocation_commands = capabilities.get('invocationCommands', [])
                        for cmd in invocation_commands:
                            tool_name = cmd.get('command', '')
                            if tool_name:
                                tools.append(tool_name)

                        if tools:
                            tools_summary.append(f"- [MCP] {display_name}: {description} (工具: {', '.join(tools)})")
                        else:
                            tools_summary.append(f"- [MCP] {display_name}: {description}")
            except Exception as e:
                logger.debug(f"获取MCP工具信息失败: {e}")
            
            # 2. 获取 agentserver 工具包信息
            try:
                from agentserver.toolkit_manager import toolkit_manager
                toolkits = toolkit_manager.list_toolkits()
                
                for toolkit_name in toolkits:
                    toolkit_info = toolkit_manager.get_toolkit_info(toolkit_name)
                    if toolkit_info:
                        tools = toolkit_info.get("tools", [])
                        tool_names = [tool.get("name", "") for tool in tools if tool.get("name")]
                        
                        if tool_names:
                            tools_summary.append(f"- [Agent] {toolkit_name}: 工具包 (工具: {', '.join(tool_names)})")
                        else:
                            tools_summary.append(f"- [Agent] {toolkit_name}: 工具包")
            except Exception as e:
                logger.debug(f"获取agentserver工具包信息失败: {e}")
            
            if tools_summary:
                available_tools = "\n".join(tools_summary)
                # 将工具信息注入到对话分析提示词中
                return get_prompt("conversation_analyzer_prompt",
                                conversation=conversation,
                                available_tools=available_tools)
        except Exception as e:
            logger.debug(f"获取工具信息失败: {e}")
        
        return get_prompt("conversation_analyzer_prompt", conversation=conversation)

    def analyze(self, messages: List[Dict[str, str]]):
        logger.info(f"[ConversationAnalyzer] 开始分析对话，消息数量: {len(messages)}")
        prompt = self._build_prompt(messages)
        logger.info(f"[ConversationAnalyzer] 构建提示词完成，长度: {len(prompt)}")

        # 使用简化的非标准JSON解析
        result = self._analyze_with_non_standard_json(prompt)
        if result and result.get("tool_calls"):
            return result

        # 解析失败
        logger.info("[ConversationAnalyzer] 未发现可执行任务")
        return {"tasks": [], "reason": "未发现可执行任务", "raw": "", "tool_calls": []}

    def _analyze_with_non_standard_json(self, prompt: str) -> Optional[Dict]:
        """非标准JSON格式解析 - 直接调用LLM，避免嵌套线程池"""
        logger.info("[ConversationAnalyzer] 尝试非标准JSON格式解析")
        try:
            # 直接调用LLM，避免嵌套线程池
            resp = self.llm.invoke([
                {"role": "system", "content": "你是精确的任务意图提取器与MCP调用规划器。"},
                {"role": "user", "content": prompt},
            ])
            
            text = resp.content.strip()
            logger.info(f"[ConversationAnalyzer] LLM响应完成，响应长度: {len(text)}")
            logger.info(f"[ConversationAnalyzer] LLM原始响应内容: {text}")

            # 解析非标准JSON格式
            tool_calls = self._parse_non_standard_json(text)
            
            if tool_calls:
                logger.info(f"[ConversationAnalyzer] 非标准JSON解析成功，发现 {len(tool_calls)} 个工具调用")
                return {
                    "tasks": [],
                    "reason": f"非标准JSON解析成功，发现 {len(tool_calls)} 个工具调用",
                    "tool_calls": tool_calls
                }
            else:
                logger.info("[ConversationAnalyzer] 未发现工具调用")
                return None

        except Exception as e:
            logger.error(f"[ConversationAnalyzer] 非标准JSON解析失败: {e}")
            return None

    def _parse_non_standard_json(self, text: str) -> List[Dict[str, Any]]:
        """解析非标准JSON格式 - 处理中文括号和标准JSON"""
        from nagaagent_core.stable.parsing import parse_non_standard_json
        return parse_non_standard_json(text)


class BackgroundAnalyzer:
    """后台分析器 - 管理异步意图分析"""
    
    def __init__(self):
        self.analyzer = ConversationAnalyzer()
        self.running_analyses = {}
    
    async def analyze_intent_async(self, messages: List[Dict[str, str]], session_id: str):
        """异步意图分析 - 基于博弈论的背景分析机制"""
        # 检查是否已经有分析在进行中
        if session_id in self.running_analyses:
            logger.info(f"[博弈论] 会话 {session_id} 已有意图分析在进行中，跳过重复执行")
            return {"has_tasks": False, "reason": "已有分析在进行中", "tasks": [], "priority": "low"}
        
        # 创建独立的意图分析会话
        analysis_session_id = f"analysis_{session_id}_{int(time.time())}"
        logger.info(f"[博弈论] 创建独立分析会话: {analysis_session_id}")
        
        # 标记分析开始
        self.running_analyses[session_id] = analysis_session_id
        
        try:
            logger.info(f"[博弈论] 开始异步意图分析，消息数量: {len(messages)}")
            loop = asyncio.get_running_loop()
            # Offload sync LLM call to threadpool to avoid blocking event loop
            logger.info(f"[博弈论] 在线程池中执行LLM分析...")

            # 添加异步超时机制
            try:
                analysis = await asyncio.wait_for(
                    loop.run_in_executor(None, self.analyzer.analyze, messages),
                    timeout=60.0  # 60秒超时
                )
                logger.info(f"[博弈论] LLM分析完成，结果类型: {type(analysis)}")
            except asyncio.TimeoutError:
                logger.error("[博弈论] 意图分析超时（60秒）")
                return {"has_tasks": False, "reason": "意图分析超时", "tasks": [], "priority": "low"}

        except Exception as e:
            logger.error(f"[博弈论] 意图分析失败: {e}")
            import traceback
            logger.error(f"[博弈论] 详细错误信息: {traceback.format_exc()}")
            return {"has_tasks": False, "reason": f"分析失败: {e}", "tasks": [], "priority": "low"}
        
        try:
            import uuid as _uuid
            tasks = analysis.get("tasks", []) if isinstance(analysis, dict) else []
            tool_calls = analysis.get("tool_calls", []) if isinstance(analysis, dict) else []
            
            if not tasks and not tool_calls:
                return {"has_tasks": False, "reason": "未发现可执行任务", "tasks": [], "priority": "low"}
            
            logger.info(f"[博弈论] 分析会话 {analysis_session_id} 发现 {len(tasks)} 个任务和 {len(tool_calls)} 个工具调用")
            
            # 处理工具调用 - 根据agentType分发到不同服务器
            if tool_calls:
                # 通知UI工具调用开始
                await self._notify_ui_tool_calls(tool_calls, session_id)
                await self._dispatch_tool_calls(tool_calls, session_id, analysis_session_id)
            
            # 返回分析结果
            result = {
                "has_tasks": True,
                "reason": analysis.get("reason", "发现潜在任务"),
                "tasks": tasks,
                "tool_calls": tool_calls,
                "priority": "medium"  # 可以根据任务数量或类型调整优先级
            }
            
            # 记录任务详情
            for task in tasks:
                logger.info(f"发现任务: {task}")
            for tool_call in tool_calls:
                logger.info(f"发现工具调用: {tool_call}")
            
            return result
                
        except Exception as e:
            logger.error(f"任务处理失败: {e}")
            return {"has_tasks": False, "reason": f"处理失败: {e}", "tasks": [], "priority": "low"}
        finally:
            # 清除分析状态标记
            if session_id in self.running_analyses:
                del self.running_analyses[session_id]
                logger.info(f"[博弈论] 会话 {session_id} 分析状态已清除")

    async def _notify_ui_tool_calls(self, tool_calls: List[Dict[str, Any]], session_id: str):
        """批量通知UI工具调用开始 - 优化网络请求"""
        try:
            import httpx
            
            # 批量构建工具调用通知
            tool_names = [tool_call.get("tool_name", "未知工具") for tool_call in tool_calls]
            service_names = [tool_call.get("service_name", "未知服务") for tool_call in tool_calls]
            
            # 批量发送通知（减少HTTP请求次数）
            notification_payload = {
                "session_id": session_id,
                "tool_calls": [
                    {
                        "tool_name": tool_call.get("tool_name", "未知工具"),
                        "service_name": tool_call.get("service_name", "未知服务"),
                        "status": "starting"
                    }
                    for tool_call in tool_calls
                ],
                "message": f"🔧 正在执行 {len(tool_calls)} 个工具: {', '.join(tool_names)}"
            }
            
            from system.config import get_server_port
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"http://localhost:{get_server_port('api_server')}/tool_notification",
                    json=notification_payload
                )
                    
        except Exception as e:
            logger.error(f"批量通知UI工具调用失败: {e}")
    
    async def _dispatch_tool_calls(self, tool_calls: List[Dict[str, Any]], session_id: str, analysis_session_id: str = None):
        """根据agentType将工具调用分发到相应的服务器"""
        try:
            import httpx
            import uuid
            
            # 按agentType分组
            mcp_calls = []
            agent_calls = []
            
            for tool_call in tool_calls:
                agent_type = tool_call.get("agentType", "")
                if agent_type == "mcp":
                    mcp_calls.append(tool_call)
                elif agent_type == "agent":
                    agent_calls.append(tool_call)
            
            # 分发MCP任务到MCP服务器
            if mcp_calls:
                await self._send_to_mcp_server(mcp_calls, session_id, analysis_session_id)
            
            # 分发Agent任务到agentserver
            if agent_calls:
                await self._send_to_agent_server(agent_calls, session_id, analysis_session_id)
                
        except Exception as e:
            logger.error(f"工具调用分发失败: {e}")
    
    async def _send_to_mcp_server(self, mcp_calls: List[Dict[str, Any]], session_id: str, analysis_session_id: str = None):
        """发送MCP任务到MCP服务器"""
        try:
            import httpx
            import uuid
            
            from system.config import get_server_port
            # 构建MCP服务器请求
            mcp_payload = {
                "query": f"批量MCP工具调用 ({len(mcp_calls)} 个)",
                "tool_calls": mcp_calls,
                "session_id": session_id,
                "request_id": str(uuid.uuid4()),
                "callback_url": f"http://localhost:{get_server_port('api_server')}/tool_result_callback"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://localhost:{get_server_port('mcp_server')}/schedule",
                    json=mcp_payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"[博弈论] 分析会话 {analysis_session_id or 'unknown'} MCP任务调度成功: {result.get('task_id', 'unknown')}")
                else:
                    logger.error(f"[博弈论] MCP任务调度失败: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"[博弈论] 发送MCP任务失败: {e}")
    
    async def _send_to_agent_server(self, agent_calls: List[Dict[str, Any]], session_id: str, analysis_session_id: str = None):
        """发送Agent任务到agentserver - 应用与MCP服务器相同的会话管理逻辑"""
        try:
            import httpx
            import uuid
            
            from system.config import get_server_port
            # 构建agentserver请求 - 应用与MCP服务器相同的会话管理逻辑
            agent_payload = {
                "query": f"批量Agent任务执行 ({len(agent_calls)} 个)",
                "agent_calls": agent_calls,  # 传递完整的agent_calls信息
                "session_id": session_id,
                "analysis_session_id": analysis_session_id,  # 传递独立分析会话ID
                "request_id": str(uuid.uuid4()),  # 生成独立请求ID
                "callback_url": f"http://localhost:{get_server_port('api_server')}/agent_result_callback"  # 添加回调URL
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://localhost:{get_server_port('agent_server')}/schedule",  # 使用统一的schedule端点
                    json=agent_payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"[博弈论] 分析会话 {analysis_session_id or 'unknown'} Agent任务调度成功: {result.get('task_id', 'unknown')}")
                else:
                    logger.error(f"[博弈论] Agent任务调度失败: {response.status_code} - {response.text}")
                    
        except Exception as e:
            logger.error(f"[博弈论] 发送Agent任务失败: {e}")


# 全局分析器实例
_background_analyzer = None

def get_background_analyzer() -> BackgroundAnalyzer:
    """获取全局后台分析器实例"""
    global _background_analyzer
    if _background_analyzer is None:
        _background_analyzer = BackgroundAnalyzer()
    return _background_analyzer
