#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 客户端适配器
用于与 OpenClaw Gateway 进行通信

官方文档: https://docs.openclaw.ai/

API 端点:
- POST /hooks/agent - 发送消息给 Agent
- POST /hooks/wake - 触发系统事件
- POST /tools/invoke - 直接调用工具
"""

import logging
import json
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OpenClawTaskEvent:
    """OpenClaw 任务事件（用于追踪中间过程）"""

    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    kind: str = "info"  # info, request, response, error, state
    message: str = ""
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "kind": self.kind,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class OpenClawTask:
    """OpenClaw 任务数据结构"""

    task_id: str
    message: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    session_key: Optional[str] = None
    run_id: Optional[str] = None  # OpenClaw 返回的 runId
    events: List[OpenClawTaskEvent] = field(default_factory=list)

    def add_event(self, kind: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.events.append(OpenClawTaskEvent(kind=kind, message=message, data=data))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "message": self.message,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class OpenClawSessionInfo:
    """OpenClaw 调度终端会话信息"""

    session_key: str
    created_at: str
    last_activity: str
    message_count: int = 0
    last_run_id: Optional[str] = None
    status: str = "active"  # active, idle, error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_key": self.session_key,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "last_run_id": self.last_run_id,
            "status": self.status,
        }


@dataclass
class OpenClawConfig:
    """OpenClaw 配置"""

    # OpenClaw Gateway 默认端口是 18789
    gateway_url: str = "http://127.0.0.1:18789"
    # Gateway 认证 token (对应 gateway.auth.token)
    gateway_token: Optional[str] = None
    # Hooks 认证 token (对应 hooks.token)
    hooks_token: Optional[str] = None
    # 请求超时时间（秒）
    timeout: int = 120
    # 默认参数
    default_model: Optional[str] = None
    default_channel: str = "last"

    # 兼容旧配置
    token: Optional[str] = None

    def __post_init__(self):
        # 如果只配置了 token，同时用于 gateway 和 hooks
        if self.token and not self.gateway_token:
            self.gateway_token = self.token
        if self.token and not self.hooks_token:
            self.hooks_token = self.token

    def get_gateway_headers(self) -> Dict[str, str]:
        """获取 Gateway 请求头"""
        headers = {"Content-Type": "application/json"}
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"
        return headers

    def get_hooks_headers(self) -> Dict[str, str]:
        """获取 Hooks 请求头"""
        headers = {"Content-Type": "application/json"}
        if self.hooks_token:
            headers["Authorization"] = f"Bearer {self.hooks_token}"
        return headers

    def get_headers(self) -> Dict[str, str]:
        """获取请求头（兼容旧代码）"""
        return self.get_gateway_headers()


class OpenClawClient:
    """
    OpenClaw 客户端

    基于官方文档实现:
    - https://docs.openclaw.ai/automation/webhook
    - https://docs.openclaw.ai/gateway/tools-invoke-http-api

    功能：
    1. 发送消息给 Agent (POST /hooks/agent)
    2. 触发系统事件 (POST /hooks/wake)
    3. 直接调用工具 (POST /tools/invoke)
    """

    def __init__(self, config: Optional[OpenClawConfig] = None):
        self.config = config or OpenClawConfig()
        self._tasks: Dict[str, OpenClawTask] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

        # 调度终端会话信息 - 首次调用时初始化，保持整个运行期间
        self._session_info: Optional[OpenClawSessionInfo] = None
        self._default_session_key: Optional[str] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端（懒加载，禁用代理确保 localhost 直连）"""
        if self._http_client is None or self._http_client.is_closed:
            # OpenClaw Gateway 运行在 localhost，必须绕过代理
            import os

            os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
            )
        return self._http_client

    async def close(self):
        """关闭客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def _emit_task_event(
        self, task: OpenClawTask, kind: str, message: str, data: Optional[Dict[str, Any]] = None
    ) -> None:
        try:
            task.add_event(kind=kind, message=message, data=data)
        except Exception:
            # 事件记录失败不影响主流程
            return

    # ============ 核心 API ============

    async def send_message(
        self,
        message: str,
        session_key: Optional[str] = None,
        name: Optional[str] = None,
        channel: Optional[str] = None,
        to: Optional[str] = None,
        model: Optional[str] = None,
        wake_mode: str = "now",
        deliver: bool = False,
        timeout_seconds: int = 1200,
        max_retries: int = 5,
        retry_interval: float = 3.0,
        task_id: Optional[str] = None,
    ) -> OpenClawTask:
        """
        发送消息给 OpenClaw Agent

        使用 POST /hooks/agent 端点
        文档: https://docs.openclaw.ai/automation/webhook

        Args:
            message: 消息内容 (必需)
            session_key: 会话标识，用于多轮对话
            name: hook 名称，用于会话摘要前缀 (如 "GitHub", "Naga")
            channel: 输出通道 (last, whatsapp, telegram, discord, slack 等)
            to: 接收者标识
            model: 模型覆盖 (如 "anthropic/claude-3-5-sonnet")
            wake_mode: 唤醒模式 ("now" 或 "next-heartbeat")
            deliver: 是否投递到通道
            timeout_seconds: 等待结果的超时时间（秒），0表示异步不等待
            max_retries: 最大重试次数，默认5次
            retry_interval: 重试间隔（秒），默认2秒

        Returns:
            OpenClawTask: 任务对象
        """
        import asyncio

        # 首次调用时初始化默认 session_key
        if self._default_session_key is None:
            self._default_session_key = f"naga:{uuid.uuid4().hex[:12]}"
            logger.info(f"[OpenClaw] 初始化调度终端会话: {self._default_session_key}")

        # 使用传入的 session_key 或默认的
        actual_session_key = session_key or self._default_session_key

        use_task_id = task_id or str(uuid.uuid4())
        task = OpenClawTask(task_id=use_task_id, message=message, session_key=actual_session_key)

        self._emit_task_event(
            task,
            kind="state",
            message="task_created",
            data={
                "gateway_url": self.config.gateway_url,
                "session_key": actual_session_key,
                "timeout_seconds": timeout_seconds,
            },
        )

        # 构建请求体
        payload: Dict[str, Any] = {"message": message}

        # 可选参数
        payload["sessionKey"] = actual_session_key
        if name:
            payload["name"] = name
        if channel:
            payload["channel"] = channel
        elif self.config.default_channel:
            payload["channel"] = self.config.default_channel
        if to:
            payload["to"] = to
        if model:
            payload["model"] = model
        elif self.config.default_model:
            payload["model"] = self.config.default_model
        if wake_mode:
            payload["wakeMode"] = wake_mode
        if deliver:
            payload["deliver"] = deliver
        # 设置超时时间，>0 表示同步等待结果
        if timeout_seconds > 0:
            payload["timeoutSeconds"] = timeout_seconds

        task.started_at = datetime.now().isoformat()
        task.status = TaskStatus.RUNNING

        # HTTP 超时需要比 OpenClaw 的 timeoutSeconds 更长
        http_timeout = max(timeout_seconds + 30, self.config.timeout)

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                client = await self._get_client()

                logger.info(
                    f"[OpenClaw] 发送消息到 /hooks/agent (尝试 {attempt}/{max_retries}): {message[:50]}... (timeout={timeout_seconds}s)"
                )

                self._emit_task_event(
                    task,
                    kind="request",
                    message="hooks_agent_request",
                    data={
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "url": f"{self.config.gateway_url}/hooks/agent",
                        "session_key": actual_session_key,
                        "deliver": deliver,
                        "wake_mode": wake_mode,
                        "timeout_seconds": timeout_seconds,
                    },
                )

                response = await client.post(
                    f"{self.config.gateway_url}/hooks/agent",
                    json=payload,
                    headers=self.config.get_hooks_headers(),
                    timeout=http_timeout,
                )

                self._emit_task_event(
                    task,
                    kind="response",
                    message="hooks_agent_response",
                    data={
                        "status_code": response.status_code,
                    },
                )

                # /hooks/agent 返回 200/202
                # 200 表示同步完成（含 reply），202 表示异步接受（需轮询获取回复）
                if response.status_code in (200, 202):
                    try:
                        result = response.json()
                        task.result = result if isinstance(result, dict) else {}
                        task.run_id = result.get("runId")

                        self._emit_task_event(
                            task,
                            kind="state",
                            message="hooks_agent_accepted",
                            data={
                                "run_id": task.run_id,
                                "status": result.get("status", "accepted"),
                            },
                        )

                        # 检查返回状态
                        status = result.get("status", "accepted")
                        if status == "ok" and result.get("reply"):
                            # 同步完成，包含 reply
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = datetime.now().isoformat()
                            reply = result.get("reply", "")
                            logger.info(
                                f"[OpenClaw] 任务同步完成: {task.task_id}, reply: {reply[:100] if reply else 'empty'}..."
                            )

                            self._emit_task_event(
                                task,
                                kind="state",
                                message="task_completed",
                                data={
                                    "run_id": task.run_id,
                                    "reply_preview": (reply[:200] if reply else ""),
                                },
                            )
                        else:
                            # 202 异步接受，需要轮询 sessions_history 获取回复
                            task.status = TaskStatus.RUNNING
                            logger.info(
                                f"[OpenClaw] 任务已接受(202): {task.task_id}, runId: {task.run_id}, 开始轮询回复..."
                            )

                            replies = await self._poll_for_reply(
                                actual_session_key,
                                timeout_seconds=timeout_seconds,
                            )
                            if replies:
                                task.status = TaskStatus.COMPLETED
                                task.completed_at = datetime.now().isoformat()
                                if task.result is None:
                                    task.result = {}
                                task.result["replies"] = replies
                                task.result["reply"] = replies[0] if len(replies) == 1 else "\n\n---\n\n".join(replies)
                                logger.info(f"[OpenClaw] 轮询获取{len(replies)}条回复成功")

                                self._emit_task_event(
                                    task,
                                    kind="state",
                                    message="task_completed",
                                    data={
                                        "run_id": task.run_id,
                                        "replies_count": len(replies),
                                        "reply_preview": (str(task.result.get("reply", ""))[:200]),
                                    },
                                )
                            else:
                                task.status = TaskStatus.COMPLETED
                                task.completed_at = datetime.now().isoformat()
                                logger.warning("[OpenClaw] 轮询超时，未获取到回复")
                    except Exception:
                        task.result = {"raw": response.text}
                        task.status = TaskStatus.RUNNING

                        self._emit_task_event(
                            task,
                            kind="error",
                            message="hooks_agent_parse_failed",
                            data={
                                "status_code": response.status_code,
                                "raw_preview": response.text[:500] if response.text else "",
                            },
                        )

                    # 更新会话信息
                    self._update_session_info(actual_session_key, task.run_id, "active")
                    # 成功，跳出重试循环
                    break
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    logger.warning(f"[OpenClaw] 消息发送失败 (尝试 {attempt}/{max_retries}): {last_error}")

                    self._emit_task_event(
                        task,
                        kind="error",
                        message="hooks_agent_http_error",
                        data={
                            "attempt": attempt,
                            "status_code": response.status_code,
                            "error_preview": response.text[:500] if response.text else "",
                        },
                    )

                    if attempt < max_retries:
                        logger.info(f"[OpenClaw] {retry_interval}秒后重试...")
                        await asyncio.sleep(retry_interval)
                    else:
                        # 最后一次尝试也失败了
                        task.status = TaskStatus.FAILED
                        task.error = last_error
                        logger.error(f"[OpenClaw] 消息发送失败，已达最大重试次数: {last_error}")
                        self._update_session_info(actual_session_key, None, "error")

                        self._emit_task_event(
                            task,
                            kind="state",
                            message="task_failed",
                            data={
                                "error": last_error,
                            },
                        )

            except Exception as e:
                last_error = str(e)
                logger.warning(f"[OpenClaw] 消息发送异常 (尝试 {attempt}/{max_retries}): {e}")

                self._emit_task_event(
                    task,
                    kind="error",
                    message="hooks_agent_exception",
                    data={
                        "attempt": attempt,
                        "error": last_error,
                    },
                )

                if attempt < max_retries:
                    logger.info(f"[OpenClaw] {retry_interval}秒后重试...")
                    await asyncio.sleep(retry_interval)
                else:
                    # 最后一次尝试也失败了
                    task.status = TaskStatus.FAILED
                    task.error = last_error
                    logger.error(f"[OpenClaw] 消息发送异常，已达最大重试次数: {e}")
                    if self._session_info:
                        self._session_info.status = "error"

                    self._emit_task_event(
                        task,
                        kind="state",
                        message="task_failed",
                        data={
                            "error": last_error,
                        },
                    )

        self._tasks[task.task_id] = task
        return task

    def _update_session_info(self, session_key: str, run_id: Optional[str], status: str):
        """更新调度终端会话信息"""
        now = datetime.now().isoformat()

        if self._session_info is None:
            # 首次创建会话信息
            self._session_info = OpenClawSessionInfo(
                session_key=session_key,
                created_at=now,
                last_activity=now,
                message_count=1,
                last_run_id=run_id,
                status=status,
            )
        else:
            # 更新现有会话信息
            self._session_info.last_activity = now
            self._session_info.message_count += 1
            if run_id:
                self._session_info.last_run_id = run_id
            self._session_info.status = status

    async def _poll_for_reply(
        self,
        session_key: str,
        timeout_seconds: int = 1200,
        poll_interval: float = 10.0,
        initial_delay: float = 5.0,
    ) -> List[str]:
        """
        轮询 sessions_history 获取 Agent 回复

        /hooks/agent 返回 202 后，通过 /tools/invoke 调用 sessions_history
        持续轮询收集所有 assistant 消息，直到消息不再增加或超时。

        Args:
            session_key: 会话标识
            timeout_seconds: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）
            initial_delay: 首次轮询前等待时间（秒）

        Returns:
            回复文本列表，超时返回收集到的所有消息
        """
        import asyncio
        import time

        await asyncio.sleep(initial_delay)

        start_time = time.time()
        all_replies: List[str] = []
        last_count = 0
        stable_count = 0

        while time.time() - start_time < timeout_seconds:
            attempt = int(time.time() - start_time)
            try:
                client = await self._get_client()

                response = await client.post(
                    f"{self.config.gateway_url}/tools/invoke",
                    json={
                        "tool": "sessions_history",
                        "args": {
                            "sessionKey": session_key,
                            "limit": 50,
                        },
                    },
                    headers=self.config.get_gateway_headers(),
                    timeout=15,
                )

                if response.status_code == 200:
                    data = response.json()
                    replies = self._extract_all_assistant_replies(data)
                    current_count = len(replies)

                    if current_count > last_count:
                        all_replies = replies
                        last_count = current_count
                        stable_count = 0
                        logger.info(
                            f"[OpenClaw] 轮询第{attempt}次: 发现{current_count}条assistant消息 (新增{current_count - last_count})"
                        )
                    else:
                        stable_count += 1
                        if stable_count >= 3 and current_count > 0:
                            logger.info(f"[OpenClaw] 消息已稳定{stable_count}次，共{current_count}条，结束轮询")
                            return replies

            except Exception as e:
                logger.warning(f"[OpenClaw] 轮询第{attempt}次异常: {e}")

            await asyncio.sleep(poll_interval)

        logger.warning(f"[OpenClaw] 轮询超时({timeout_seconds}s)，共收集{len(all_replies)}条消息")
        return all_replies

    @staticmethod
    def _extract_all_assistant_replies(data: Dict[str, Any]) -> List[str]:
        """
        从 sessions_history 返回值中提取所有 assistant 的文本回复
        """
        replies: List[str] = []
        try:
            result = data.get("result", {})
            details = result.get("details", {})
            messages = details.get("messages", [])

            if not messages:
                content = result.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "")
                    if isinstance(text, str) and text.strip():
                        try:
                            inner = json.loads(text)
                            messages = inner.get("messages", [])
                        except json.JSONDecodeError:
                            pass

            for msg in messages:
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", [])
                if isinstance(content, str):
                    if content.strip():
                        replies.append(content)
                elif isinstance(content, list):
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    text = "\n".join(text_parts)
                    if text.strip():
                        replies.append(text)
        except Exception:
            pass
        return replies

    async def wake(self, text: str, mode: str = "now") -> Dict[str, Any]:
        """
        触发系统事件

        使用 POST /hooks/wake 端点
        文档: https://docs.openclaw.ai/automation/webhook

        Args:
            text: 事件描述
            mode: 触发模式 ("now" 或 "next-heartbeat")

        Returns:
            响应结果
        """
        try:
            client = await self._get_client()

            payload = {"text": text, "mode": mode}

            logger.info(f"[OpenClaw] 触发系统事件: {text[:50]}...")

            response = await client.post(
                f"{self.config.gateway_url}/hooks/wake", json=payload, headers=self.config.get_hooks_headers()
            )

            if response.status_code == 200:
                logger.info("[OpenClaw] 系统事件触发成功")
                try:
                    return {"success": True, "result": response.json()}
                except Exception:
                    return {"success": True, "result": response.text}
            else:
                logger.error(f"[OpenClaw] 系统事件触发失败: {response.status_code}")
                return {"success": False, "error": response.text}

        except Exception as e:
            logger.error(f"[OpenClaw] 系统事件触发异常: {e}")
            return {"success": False, "error": str(e)}

    async def invoke_tool(
        self,
        tool: str,
        args: Optional[Dict[str, Any]] = None,
        action: Optional[str] = None,
        session_key: Optional[str] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        直接调用工具

        使用 POST /tools/invoke 端点
        文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api

        Args:
            tool: 工具名称 (必需)
            args: 工具参数
            action: 动作映射到工具参数
            session_key: 目标会话标识
            dry_run: 预留功能

        Returns:
            工具执行结果
        """
        try:
            client = await self._get_client()

            payload: Dict[str, Any] = {"tool": tool}

            if args:
                payload["args"] = args
            if action:
                payload["action"] = action
            if session_key:
                payload["sessionKey"] = session_key
            if dry_run:
                payload["dryRun"] = dry_run

            logger.info(f"[OpenClaw] 调用工具: {tool}")

            response = await client.post(
                f"{self.config.gateway_url}/tools/invoke", json=payload, headers=self.config.get_gateway_headers()
            )

            if response.status_code == 200:
                logger.info(f"[OpenClaw] 工具调用成功: {tool}")
                try:
                    return {"success": True, "result": response.json()}
                except Exception:
                    return {"success": True, "result": response.text}
            elif response.status_code == 400:
                logger.error(f"[OpenClaw] 工具调用错误: {response.text}")
                return {"success": False, "error": "invalid_request", "detail": response.text}
            elif response.status_code == 401:
                logger.error("[OpenClaw] 认证失败")
                return {"success": False, "error": "unauthorized"}
            elif response.status_code == 404:
                logger.error(f"[OpenClaw] 工具不可用: {tool}")
                return {"success": False, "error": "tool_not_found", "tool": tool}
            else:
                logger.error(f"[OpenClaw] 工具调用失败: {response.status_code}")
                return {"success": False, "error": response.text}

        except Exception as e:
            logger.error(f"[OpenClaw] 工具调用异常: {e}")
            return {"success": False, "error": str(e)}

    # ============ 任务管理 ============

    def get_task(self, task_id: str) -> Optional[OpenClawTask]:
        """获取本地缓存的任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> List[OpenClawTask]:
        """获取所有本地缓存的任务"""
        return list(self._tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> List[OpenClawTask]:
        """按状态获取任务"""
        return [t for t in self._tasks.values() if t.status == status]

    def clear_completed_tasks(self):
        """清理已完成的任务"""
        self._tasks = {
            k: v
            for k, v in self._tasks.items()
            if v.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        }

    # ============ 会话历史查询 ============

    async def get_sessions_history(
        self,
        session_key: Optional[str] = None,
        limit: int = 20,
        include_tools: bool = False,
    ) -> Dict[str, Any]:
        """
        获取会话历史消息

        使用 POST /tools/invoke 调用 sessions_history 工具

        Args:
            session_key: 会话标识，必须指定
            limit: 返回消息条数限制

        Returns:
            包含历史消息的结果
        """
        # 如果没有指定 session_key，尝试回退到默认会话
        actual_session_key = session_key or self._default_session_key
        if not actual_session_key:
            return {"success": True, "messages": [], "note": "no_session_key_available"}

        try:
            result = await self.invoke_tool(
                tool="sessions_history",
                args={
                    "sessionKey": actual_session_key,
                    "limit": limit,
                    "includeTools": include_tools,
                },
            )

            if result.get("success"):
                # 解析返回的消息
                raw_result = result.get("result", {})
                messages = self._parse_history_messages(raw_result)
                return {"success": True, "session_key": actual_session_key, "messages": messages, "raw": raw_result}
            else:
                return {"success": False, "error": result.get("error", "unknown"), "messages": []}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话历史失败: {e}")
            return {"success": False, "error": str(e), "messages": []}

    def _parse_history_messages(self, raw_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        解析 sessions_history 返回的消息格式

        OpenClaw 返回格式:
        {
          "ok": true,
          "result": {
            "content": [{"type": "text", "text": "{...json...}"}],
            "details": {"sessionKey": "...", "messages": [...]}
          }
        }
        """
        messages = []

        try:
            # 尝试从 result 中提取
            if isinstance(raw_result, dict):
                inner_result = raw_result.get("result", raw_result)

                # 优先从 details.messages 获取
                details = inner_result.get("details", {})
                msg_list = details.get("messages", [])
                if msg_list and isinstance(msg_list, list):
                    for msg in msg_list:
                        if isinstance(msg, dict):
                            messages.append(
                                {
                                    "role": msg.get("role", "unknown"),
                                    "content": msg.get("content", ""),
                                    "type": "message",
                                }
                            )
                    return messages

                # 备选：从 content[].text 解析 JSON
                content = inner_result.get("content", [])
                if content and isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text = item.get("text", "")
                            # 尝试解析 JSON
                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, dict):
                                    msg_list = parsed.get("messages", [])
                                    for msg in msg_list:
                                        if isinstance(msg, dict):
                                            messages.append(
                                                {
                                                    "role": msg.get("role", "unknown"),
                                                    "content": msg.get("content", ""),
                                                    "type": "message",
                                                }
                                            )
                            except json.JSONDecodeError:
                                # 不是 JSON，作为原始文本返回
                                if text.strip():
                                    messages.append({"role": "system", "content": text, "type": "raw"})

        except Exception as e:
            logger.warning(f"[OpenClaw] 解析历史消息失败: {e}")

        return messages

    async def get_session_status(self, session_key: Optional[str] = None) -> Dict[str, Any]:
        """
        获取当前会话状态

        使用 POST /tools/invoke 调用 sessions_list 工具获取会话信息

        Args:
            session_key: 会话标识（暂未使用，sessions_list 不需要此参数）

        Returns:
            会话状态信息
        """
        try:
            # sessions_list 不需要 sessionKey 参数，它列出所有会话
            result = await self.invoke_tool(tool="sessions_list")

            if result.get("success"):
                raw_result = result.get("result", {})
                # 提取状态文本
                inner_result = raw_result.get("result", {})
                content = inner_result.get("content", [])

                status_text = ""
                if content and isinstance(content, list) and len(content) > 0:
                    status_text = content[0].get("text", "")

                return {"success": True, "status_text": status_text, "raw": raw_result}
            else:
                return {"success": False, "error": result.get("error", "unknown"), "status_text": ""}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话状态失败: {e}")
            return {"success": False, "error": str(e), "status_text": ""}

    async def get_sessions_list(self) -> Dict[str, Any]:
        """
        获取所有会话列表

        使用 POST /tools/invoke 调用 sessions_list 工具

        Returns:
            会话列表
        """
        try:
            result = await self.invoke_tool(tool="sessions_list")

            if result.get("success"):
                return {
                    "success": True,
                    "sessions": result.get("result", {}),
                }
            else:
                return {"success": False, "error": result.get("error", "unknown"), "sessions": []}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话列表失败: {e}")
            return {"success": False, "error": str(e), "sessions": []}

    # ============ 会话信息 ============

    def get_session_info(self) -> Optional[Dict[str, Any]]:
        """
        获取当前调度终端会话信息

        Returns:
            会话信息字典，未交互时返回 None
        """
        if self._session_info is None:
            return None
        return self._session_info.to_dict()

    def has_session(self) -> bool:
        """检查是否已有活跃会话"""
        return self._session_info is not None

    def get_default_session_key(self) -> Optional[str]:
        """获取默认会话标识"""
        return self._default_session_key

    # ============ 健康检查 ============

    async def health_check(self) -> Dict[str, Any]:
        """
        检查 OpenClaw Gateway 健康状态

        Returns:
            健康状态信息
        """
        client = await self._get_client()

        try:
            # 尝试访问根路径或健康检查端点
            response = await client.get(
                f"{self.config.gateway_url}/", timeout=10, headers=self.config.get_gateway_headers()
            )

            if response.status_code == 200:
                return {"status": "healthy", "gateway_url": self.config.gateway_url}
            else:
                return {
                    "status": "unhealthy",
                    "gateway_url": self.config.gateway_url,
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {"status": "unreachable", "gateway_url": self.config.gateway_url, "error": str(e)}


# 全局客户端实例（懒加载）
_openclaw_client: Optional[OpenClawClient] = None


def get_openclaw_client(config: Optional[OpenClawConfig] = None) -> OpenClawClient:
    """获取全局 OpenClaw 客户端实例"""
    global _openclaw_client
    if _openclaw_client is None:
        _openclaw_client = OpenClawClient(config)
    return _openclaw_client


def set_openclaw_config(config: OpenClawConfig):
    """设置 OpenClaw 配置并重新创建客户端"""
    global _openclaw_client
    _openclaw_client = OpenClawClient(config)
