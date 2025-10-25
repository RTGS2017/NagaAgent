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
        
        # 获取可用的MCP工具信息，注入到意图识别中
        try:
            from mcpserver.mcp_registry import get_all_services_info
            services_info = get_all_services_info()
            
            # 构建工具信息摘要
            tools_summary = []
            for name, info in services_info.items():
                display_name = info.get("display_name", name)
                description = info.get("description", "")
                tools = [t.get("name") for t in info.get("available_tools", [])]
                
                if tools:
                    tools_summary.append(f"- {display_name}: {description} (工具: {', '.join(tools)})")
                else:
                    tools_summary.append(f"- {display_name}: {description}")
            
            if tools_summary:
                available_tools = "\n".join(tools_summary)
                # 将工具信息注入到对话分析提示词中
                return get_prompt("conversation_analyzer_prompt",
                                conversation=conversation,
                                available_tools=available_tools)
        except Exception as e:
            logger.debug(f"获取MCP工具信息失败: {e}")
        
        return get_prompt("conversation_analyzer_prompt", conversation=conversation)

    def analyze(self, messages: List[Dict[str, str]]):
        logger.info(f"[ConversationAnalyzer] 开始分析对话，消息数量: {len(messages)}")
        prompt = self._build_prompt(messages)
        logger.info(f"[ConversationAnalyzer] 构建提示词完成，长度: {len(prompt)}")

        # 重试机制：每个方法最多重试2次
        max_retries = 2

        # 方法1：结构化输出 + JSON解析
        for attempt in range(max_retries):
            logger.info(f"[ConversationAnalyzer] 方法1第{attempt + 1}次尝试")
            result = self._analyze_with_json_parsing(prompt)
            if result and result.get("tool_calls"):
                return result

        # 方法2：JSON模式
        for attempt in range(max_retries):
            logger.info(f"[ConversationAnalyzer] 方法2第{attempt + 1}次尝试")
            result = self._analyze_with_json_mode(prompt)
            if result and result.get("tool_calls"):
                return result

        # 方法3：普通解析
        for attempt in range(max_retries):
            logger.info(f"[ConversationAnalyzer] 方法3第{attempt + 1}次尝试")
            result = self._analyze_with_regex(prompt)
            if result and result.get("tool_calls"):
                return result

        # 所有方法都失败
        logger.error("[ConversationAnalyzer] 所有解析方法都失败")
        return {"tasks": [], "reason": "所有解析方法都失败", "raw": "", "tool_calls": []}

    def _analyze_with_json_parsing(self, prompt: str) -> Optional[Dict]:
        """方法1：结构化输出 + JSON解析"""
        logger.info("[ConversationAnalyzer] 尝试方法1：结构化输出 + JSON解析")
        try:
            import asyncio
            import threading

            # 添加超时机制
            def run_llm_with_timeout():
                try:
                    return self.llm.invoke([
                        {"role": "system", "content": "你是精确的任务意图提取器与MCP调用规划器。"},
                        {"role": "user", "content": prompt},
                    ])
                except Exception as e:
                    raise e

            # 在线程中运行LLM调用，设置30秒超时
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_llm_with_timeout)
                try:
                    resp = future.result(timeout=30)  # 30秒超时
                    text = resp.content.strip()
                    logger.info(f"[ConversationAnalyzer] LLM响应完成，响应长度: {len(text)}")
                    logger.info(f"[ConversationAnalyzer] LLM原始响应内容: {text}")

                    # 尝试解析JSON - 处理可能包含代码块的情况
                    import json
                    import re

                    # 尝试直接解析
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        # 如果直接解析失败，尝试提取JSON代码块
                        json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1)
                            try:
                                data = json.loads(json_str)
                            except json.JSONDecodeError as e:
                                logger.warning(f"[ConversationAnalyzer] JSON代码块解析失败: {e}")
                                return None
                        else:
                            # 如果没有代码块标记，尝试直接查找JSON对象
                            json_match = re.search(r'\{.*\}', text, re.DOTALL)
                            if json_match:
                                json_str = json_match.group(0)
                                try:
                                    data = json.loads(json_str)
                                except json.JSONDecodeError as e:
                                    logger.warning(f"[ConversationAnalyzer] JSON对象解析失败: {e}")
                                    return None
                            else:
                                logger.warning(f"[ConversationAnalyzer] 未找到有效的JSON内容")
                                return None
                    tools = data.get("tools", [])

                    # 转换格式
                    tool_calls = []
                    for tool in tools:
                        tool_call = {
                            "agentType": tool.get("agentType"),
                            "service_name": tool.get("service_name"),
                            "tool_name": tool.get("tool_name")
                        }
                        # 合并args参数
                        args = tool.get("args", {})
                        tool_call.update(args)
                        tool_calls.append(tool_call)

                    logger.info(f"[ConversationAnalyzer] JSON解析成功，发现 {len(tool_calls)} 个工具调用")
                    return {
                        "tasks": [],
                        "reason": f"JSON解析成功，发现 {len(tool_calls)} 个工具调用",
                        "tool_calls": tool_calls
                    }

                except json.JSONDecodeError as e:
                    logger.warning(f"[ConversationAnalyzer] JSON解析失败: {e}")
                    return None
                except concurrent.futures.TimeoutError:
                    logger.error("[ConversationAnalyzer] LLM调用超时（30秒）")
                    return None

        except Exception as e:
            logger.error(f"[ConversationAnalyzer] 方法1失败: {e}")
            return None

    def _analyze_with_json_mode(self, prompt: str) -> Optional[Dict]:
        """方法2：JSON模式"""
        logger.info("[ConversationAnalyzer] 尝试方法2：JSON模式")
        try:
            # 使用JSON模式调用
            from openai import OpenAI
            client = OpenAI(
                api_key=config.api.api_key,
                base_url=config.api.base_url,
            )

            response = client.chat.completions.create(
                model=config.api.model,
                messages=[
                    {"role": "system", "content": "你是精确的任务意图提取器与MCP调用规划器。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"}
            )

            text = response.choices[0].message.content
            logger.info(f"[ConversationAnalyzer] JSON模式响应完成，响应长度: {len(text)}")
            logger.info(f"[ConversationAnalyzer] JSON模式原始响应内容: {text}")

            # 解析JSON - 处理可能包含代码块的情况
            import json
            import re

            # 尝试直接解析
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试提取JSON代码块
                json_match = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[ConversationAnalyzer] JSON代码块解析失败: {e}")
                        return None
                else:
                    # 如果没有代码块标记，尝试直接查找JSON对象
                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        try:
                            data = json.loads(json_str)
                        except json.JSONDecodeError as e:
                            logger.warning(f"[ConversationAnalyzer] JSON对象解析失败: {e}")
                            return None
                    else:
                        logger.warning(f"[ConversationAnalyzer] 未找到有效的JSON内容")
                        return None
            tools = data.get("tools", [])

            # 转换格式
            tool_calls = []
            for tool in tools:
                tool_call = {
                    "agentType": tool.get("agentType"),
                    "service_name": tool.get("service_name"),
                    "tool_name": tool.get("tool_name")
                }
                # 合并args参数
                args = tool.get("args", {})
                tool_call.update(args)
                tool_calls.append(tool_call)

            logger.info(f"[ConversationAnalyzer] JSON模式解析成功，发现 {len(tool_calls)} 个工具调用")
            return {
                "tasks": [],
                "reason": f"JSON模式解析成功，发现 {len(tool_calls)} 个工具调用",
                "tool_calls": tool_calls
            }

        except Exception as e:
            logger.error(f"[ConversationAnalyzer] 方法2失败: {e}")
            return None

    def _analyze_with_regex(self, prompt: str) -> Optional[Dict]:
        """方法3：正则表达式解析"""
        logger.info("[ConversationAnalyzer] 尝试方法3：正则表达式解析")
        try:
            import asyncio
            import threading

            # 添加超时机制
            def run_llm_with_timeout():
                try:
                    return self.llm.invoke([
                        {"role": "system", "content": "你是精确的任务意图提取器与MCP调用规划器。"},
                        {"role": "user", "content": prompt},
                    ])
                except Exception as e:
                    raise e

            # 在线程中运行LLM调用，设置30秒超时
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_llm_with_timeout)
                try:
                    resp = future.result(timeout=30)  # 30秒超时
                    text = resp.content.strip()
                    logger.info(f"[ConversationAnalyzer] LLM响应完成，响应长度: {len(text)}")
                    logger.info(f"[ConversationAnalyzer] 正则模式原始响应内容: {text}")

                    import re
                    import json
                    tool_calls: List[Dict[str, Any]] = []

                    # 第一步：检测并去除代码块，尝试使用json库直接解析
                    processed_text = text

                    # 检测是否有代码块格式
                    code_block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', processed_text)
                    if code_block_match:
                        # 去除代码块，只保留JSON内容
                        processed_text = code_block_match.group(1)
                        logger.info(f"[ConversationAnalyzer] 检测到代码块，提取JSON内容")

                    # 尝试使用json库直接解析处理后的文本
                    try:
                        data = json.loads(processed_text)
                        tools = data.get("tools", [])

                        for tool in tools:
                            tool_call = {
                                "agentType": tool.get("agentType"),
                                "service_name": tool.get("service_name"),
                                "tool_name": tool.get("tool_name")
                            }
                            # 合并args参数
                            args = tool.get("args", {})
                            tool_call.update(args)
                            tool_calls.append(tool_call)

                        logger.info(f"[ConversationAnalyzer] JSON库解析成功，发现 {len(tool_calls)} 个工具调用")

                    except json.JSONDecodeError:
                        # 第二步：如果json库解析失败，使用正则表达式再次尝试
                        logger.info("[ConversationAnalyzer] JSON库解析失败，使用正则表达式解析")

                        # 查找所有JSON块
                        json_blocks = re.findall(r'\{[\s\S]*?\}', text)
                        logger.info(f"[ConversationAnalyzer] 找到 {len(json_blocks)} 个JSON块")

                        for json_block in json_blocks:
                            try:
                                data = json.loads(json_block)
                                tools = data.get("tools", [])

                                for tool in tools:
                                    tool_call = {
                                        "agentType": tool.get("agentType"),
                                        "service_name": tool.get("service_name"),
                                        "tool_name": tool.get("tool_name")
                                    }
                                    # 合并args参数
                                    args = tool.get("args", {})
                                    tool_call.update(args)
                                    tool_calls.append(tool_call)
                            except json.JSONDecodeError:
                                continue

                    logger.info(f"[ConversationAnalyzer] 正则解析成功，发现 {len(tool_calls)} 个工具调用")
                    return {
                        "tasks": [],
                        "reason": f"正则解析成功，发现 {len(tool_calls)} 个工具调用",
                        "tool_calls": tool_calls
                    }

                except concurrent.futures.TimeoutError:
                    logger.error("[ConversationAnalyzer] LLM调用超时（30秒）")
                    return None

        except Exception as e:
            logger.error(f"[ConversationAnalyzer] 方法3失败: {e}")
            return None


class BackgroundAnalyzer:
    """后台分析器 - 管理异步意图分析"""
    
    def __init__(self):
        self.analyzer = ConversationAnalyzer()
        self.running_analyses = {}
    
    async def analyze_intent_async(self, messages: List[Dict[str, str]], session_id: str):
        """异步意图分析 - 基于博弈论的背景分析机制"""
        # 创建独立的意图分析会话
        analysis_session_id = f"analysis_{session_id}_{int(time.time())}"
        logger.info(f"[博弈论] 创建独立分析会话: {analysis_session_id}")
        
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
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "http://localhost:8000/tool_notification",
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
            
            # 构建MCP服务器请求
            mcp_payload = {
                "query": f"批量MCP工具调用 ({len(mcp_calls)} 个)",
                "tool_calls": mcp_calls,
                "session_id": session_id,
                "request_id": str(uuid.uuid4()),
                "callback_url": "http://localhost:8000/tool_result_callback"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:8003/schedule",
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
        """发送Agent任务到agentserver"""
        try:
            import httpx
            import uuid
            
            # 构建agentserver请求
            agent_payload = {
                "messages": [
                    {"role": "user", "content": f"执行Agent任务: {agent_call.get('instruction', '')}"}
                    for agent_call in agent_calls
                ],
                "session_id": session_id
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "http://localhost:8002/analyze_and_execute",
                    json=agent_payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"[博弈论] 分析会话 {analysis_session_id or 'unknown'} Agent任务调度成功: {result.get('status', 'unknown')}")
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
