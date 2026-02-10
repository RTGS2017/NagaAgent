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
            api_key=config.api.api_key,  # type: ignore[arg-type]
            temperature=0,
        )

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        lines = []
        for m in messages[-config.api.max_history_rounds :]:
            role = m.get("role", "user")
            # 修复：使用content字段而不是text字段
            content = m.get("content", "")
            # 清理文本，移除可能导致格式化问题的字符
            content = content.replace("{", "{{").replace("}", "}}")
            lines.append(f"{role}: {content}")
        conversation = "\n".join(lines)

        available_tools = ""
        return get_prompt(
            "conversation_analyzer_prompt",
            conversation=conversation,
            available_tools=available_tools,
        )

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
            resp = self.llm.invoke(
                [
                    {"role": "system", "content": "你是精确的任务意图提取器与MCP调用规划器。"},
                    {"role": "user", "content": prompt},
                ]
            )

            raw_content: Any = getattr(resp, "content", "")
            if isinstance(raw_content, str):
                text = raw_content.strip()
            else:
                # 兼容LangChain对多模态/分段内容的返回类型
                text = str(raw_content).strip()
            logger.info(f"[ConversationAnalyzer] LLM响应完成，响应长度: {len(text)}")
            logger.info(f"[ConversationAnalyzer] LLM原始响应内容: {text}")

            # 解析非标准JSON格式
            tool_calls = self._parse_non_standard_json(text)

            if tool_calls:
                logger.info(f"[ConversationAnalyzer] 非标准JSON解析成功，发现 {len(tool_calls)} 个工具调用")
                return {
                    "tasks": [],
                    "reason": f"非标准JSON解析成功，发现 {len(tool_calls)} 个工具调用",
                    "tool_calls": tool_calls,
                }
            else:
                logger.info("[ConversationAnalyzer] 未发现工具调用")
                return None

        except Exception as e:
            logger.error(f"[ConversationAnalyzer] 非标准JSON解析失败: {e}")
            return None

    def _parse_non_standard_json(self, text: str) -> List[Dict[str, Any]]:
        """解析非标准JSON格式。

        兼容场景：
        - LLM输出全角括号/标点（如｛｝），导致下游解析器无法识别
        - LLM输出在JSON前后夹杂少量说明文字
        """

        normalized_text = self._normalize_fullwidth_json_chars(text)

        # 优先使用核心库解析器（如果可用）
        try:
            from system.parsing import parse_non_standard_json

            tool_calls = parse_non_standard_json(normalized_text)
            if tool_calls:
                return tool_calls
        except Exception as e:
            logger.debug(f"parse_non_standard_json不可用或解析失败，尝试回退解析: {e}")

        # 回退：从文本中提取一个或多个JSON对象并解析
        return self._fallback_extract_json_objects(normalized_text)

    @staticmethod
    def _normalize_fullwidth_json_chars(text: str) -> str:
        """将常见全角JSON相关字符归一化为ASCII。

        仅做保守替换，避免影响普通文本内容。
        """
        if not text:
            return text

        translation_table = str.maketrans(
            {
                "｛": "{",
                "｝": "}",
                "：": ":",
                "，": ",",
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
            }
        )
        return text.translate(translation_table)

    def _fallback_extract_json_objects(self, text: str) -> List[Dict[str, Any]]:
        """从文本中提取JSON对象（支持多个），并用json5/json解析。

        返回值统一为List[Dict]；无法解析时返回空列表。
        """

        def _loads(s: str) -> Any:
            try:
                import json5 as _json5

                return _json5.loads(s)
            except Exception:
                import json as _json

                return _json.loads(s)

        objects: List[Dict[str, Any]] = []
        start: Optional[int] = None
        depth = 0

        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        candidate = text[start : i + 1].strip()
                        start = None

                        # 跳过空对象（表示“无任务”）
                        if candidate in ("{}", "{ }"):
                            continue

                        try:
                            parsed = _loads(candidate)
                        except Exception:
                            continue

                        if isinstance(parsed, dict):
                            objects.append(parsed)
                        elif isinstance(parsed, list):
                            for item in parsed:
                                if isinstance(item, dict):
                                    objects.append(item)

        # 只保留形如工具调用的对象（避免误解析到无关JSON）
        filtered: List[Dict[str, Any]] = []
        for obj in objects:
            agent_type = obj.get("agentType")
            if isinstance(agent_type, str) and agent_type:
                filtered.append(obj)

        return filtered


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

        await self._notify_ui_tool_status(
            session_id=session_id,
            message="正在检测工具调用",
            stage="detecting",
            auto_hide_ms=0,
        )

        try:
            logger.info(f"[博弈论] 开始异步意图分析，消息数量: {len(messages)}")
            loop = asyncio.get_running_loop()
            # Offload sync LLM call to threadpool to avoid blocking event loop
            logger.info("[博弈论] 在线程池中执行LLM分析...")

            # 添加异步超时机制
            try:
                analysis = await asyncio.wait_for(
                    loop.run_in_executor(None, self.analyzer.analyze, messages),
                    timeout=60.0,  # 60秒超时
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

            tasks = analysis.get("tasks", []) if isinstance(analysis, dict) else []
            tool_calls = analysis.get("tool_calls", []) if isinstance(analysis, dict) else []

            if not tasks and not tool_calls:
                await self._notify_ui_tool_status(
                    session_id=session_id,
                    message="未检测到工具调用",
                    stage="none",
                    auto_hide_ms=1200,
                )
                return {"has_tasks": False, "reason": "未发现可执行任务", "tasks": [], "priority": "low"}

            logger.info(
                f"[博弈论] 分析会话 {analysis_session_id} 发现 {len(tasks)} 个任务和 {len(tool_calls)} 个工具调用"
            )

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
                "priority": "medium",  # 可以根据任务数量或类型调整优先级
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
            # 批量发送通知（减少HTTP请求次数）
            notification_payload = {
                "session_id": session_id,
                "tool_calls": [
                    {
                        "tool_name": tool_call.get("tool_name", "未知工具"),
                        "service_name": tool_call.get("service_name", "未知服务"),
                        "status": "starting",
                    }
                    for tool_call in tool_calls
                ],
                "stage": "executing",
                "auto_hide_ms": 0,
                "message": f"检测到{len(tool_calls)}个工具调用，执行中",
            }

            from system.config import get_server_port

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"http://localhost:{get_server_port('api_server')}/tool_notification", json=notification_payload
                )

        except Exception as e:
            logger.error(f"批量通知UI工具调用失败: {e}")

    async def _notify_ui_tool_status(self, session_id: str, message: str, stage: str, auto_hide_ms: int) -> None:
        """通知UI显示工具调用相关状态"""
        try:
            import httpx

            from system.config import get_server_port

            notification_payload = {
                "session_id": session_id,
                "tool_calls": [],
                "stage": stage,
                "auto_hide_ms": auto_hide_ms,
                "message": message,
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"http://localhost:{get_server_port('api_server')}/tool_notification",
                    json=notification_payload,
                )
        except Exception as e:
            logger.error(f"通知UI工具状态失败: {e}")

    async def _dispatch_tool_calls(
        self, tool_calls: List[Dict[str, Any]], session_id: str, analysis_session_id: Optional[str] = None
    ):
        """将工具调用分发到OpenClaw"""
        try:
            openclaw_calls = [tc for tc in tool_calls if tc.get("agentType") == "openclaw"]

            if openclaw_calls:
                await self._send_to_openclaw(openclaw_calls, session_id, analysis_session_id)

        except Exception as e:
            logger.error(f"工具调用分发失败: {e}")

    async def _send_to_openclaw(
        self, openclaw_calls: List[Dict[str, Any]], session_id: str, analysis_session_id: Optional[str] = None
    ):
        """发送OpenClaw任务到agentserver的OpenClaw端点

        使用 POST /hooks/agent 端点
        文档: https://docs.openclaw.ai/automation/webhook
        """
        try:
            import httpx

            from system.config import get_server_port

            for call in openclaw_calls:
                task_type = call.get("task_type", "message")
                message = call.get("message", "")

                if not message:
                    logger.warning(f"[博弈论] OpenClaw任务缺少message字段，跳过: {call}")
                    continue

                # HTTP 超时需要比 OpenClaw 的 timeoutSeconds 更长
                openclaw_timeout = 120
                async with httpx.AsyncClient(timeout=openclaw_timeout + 30) as client:
                    # 所有任务类型都通过 /openclaw/send 发送
                    # OpenClaw Agent 会自行处理消息内容
                    payload = {
                        "message": message,
                        "session_key": call.get("session_key", f"naga_{session_id}"),
                        "name": "Naga",  # hook 名称标识
                        "wake_mode": "now",
                        "timeout_seconds": openclaw_timeout,  # 同步等待结果
                    }

                    # 如果是定时任务或提醒，在消息中包含调度信息
                    if task_type == "cron" and call.get("schedule"):
                        payload["message"] = f"[定时任务 cron: {call.get('schedule')}] {message}"
                    elif task_type == "reminder" and call.get("at"):
                        payload["message"] = f"[提醒 在 {call.get('at')} 后] {message}"

                    response = await client.post(
                        f"http://localhost:{get_server_port('agent_server')}/openclaw/send", json=payload
                    )

                    if response.status_code == 200:
                        result = response.json()
                        replies = result.get("replies", [])
                        task_status = result.get("task", {}).get("status", "unknown")
                        logger.info(
                            f"[博弈论] OpenClaw {task_type} 任务完成: status={task_status}, replies={len(replies)}条"
                        )

                        if replies:
                            for i, r in enumerate(replies):
                                logger.info(
                                    f"[博弈论] 发送第{i + 1}/{len(replies)}条回复到UI: {r[:50] if r else 'empty'}..."
                                )
                                await self._notify_ui_clawdbot_reply(session_id, r)
                    else:
                        logger.error(f"[博弈论] OpenClaw任务发送失败: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"[博弈论] 发送OpenClaw任务失败: {e}")

    async def _notify_ui_clawdbot_reply(self, session_id: str, reply: str):
        """将 ClawdBot 回复发送到 UI 显示"""
        try:
            import httpx

            from system.config import get_server_port

            payload = {
                "session_id": session_id,
                "action": "show_clawdbot_response",
                "ai_response": reply,
            }

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"http://localhost:{get_server_port('api_server')}/ui_notification",
                    json=payload,
                )
                if response.status_code == 200:
                    logger.info(f"[博弈论] ClawdBot 回复已发送到 UI: {reply[:80]}...")
                else:
                    logger.error(f"[博弈论] ClawdBot 回复发送失败: {response.status_code}")

        except Exception as e:
            logger.error(f"[博弈论] 发送 ClawdBot 回复到 UI 失败: {e}")


# 全局分析器实例
_background_analyzer = None


def get_background_analyzer() -> BackgroundAnalyzer:
    """获取全局后台分析器实例"""
    global _background_analyzer
    if _background_analyzer is None:
        _background_analyzer = BackgroundAnalyzer()
    return _background_analyzer
