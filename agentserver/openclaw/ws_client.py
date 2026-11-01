#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw Gateway WebSocket 客户端。

只实现当前 Naga 需要的最小闭环：
1. 完成 Gateway 的 connect.challenge / connect 握手
2. 调用 chat.send
3. 接收 chat / agent 事件
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger("openclaw.ws_client")

PROTOCOL_VERSION = 3


class OpenClawWSClient:
    """最小可用的 Gateway WebSocket 客户端。"""

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:20789",
        token: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
    ):
        self.gateway_url = gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        self.token = token
        self.on_event = on_event
        self.ws: Optional[WebSocketClientProtocol] = None
        self.pending: Dict[str, asyncio.Future] = {}
        self.connected = False
        self._recv_task: Optional[asyncio.Task] = None
        self._instance_id = str(uuid.uuid4())
        self._closing = False

    async def connect(self) -> bool:
        """建立 WebSocket 连接并完成 Gateway 握手。"""
        try:
            self.ws = await websockets.connect(
                self.gateway_url,
                max_size=25 * 1024 * 1024,
                ping_interval=None,
            )

            challenge = await self._recv_frame()
            if challenge.get("type") != "event" or challenge.get("event") != "connect.challenge":
                logger.error(f"WebSocket 握手失败，未收到 connect.challenge: {challenge}")
                return False

            nonce = str((challenge.get("payload") or {}).get("nonce") or "").strip()
            if not nonce:
                logger.error("WebSocket 握手失败，challenge nonce 为空")
                return False

            params: Dict[str, Any] = {
                "minProtocol": PROTOCOL_VERSION,
                "maxProtocol": PROTOCOL_VERSION,
                "client": {
                    "id": "gateway-client",
                    "displayName": "openclaw-tui",
                    "version": "5.1.1",
                    "platform": sys.platform,
                    "mode": "ui",
                    "instanceId": self._instance_id,
                },
                "caps": ["tool-events"],
                "scopes": ["operator.write", "operator.admin"],
            }
            if self.token:
                params["auth"] = {"token": self.token}

            req_id = str(uuid.uuid4())
            await self._send_frame({
                "type": "req",
                "id": req_id,
                "method": "connect",
                "params": params,
            })

            response = await asyncio.wait_for(self._recv_frame(), timeout=10)
            if response.get("type") != "res" or str(response.get("id") or "").strip() != req_id:
                logger.error(f"WebSocket connect 响应异常: {response}")
                await self.close()
                return False
            if not response.get("ok"):
                logger.error(f"WebSocket connect 被拒绝: {response}")
                await self.close()
                return False

            payload = response.get("payload") if isinstance(response, dict) else None
            if not isinstance(payload, dict) or payload.get("type") != "hello-ok":
                logger.error(f"WebSocket connect 响应异常: {response}")
                await self.close()
                return False

            self.connected = True
            self._recv_task = asyncio.create_task(self._recv_loop(), name="openclaw-ws-recv")
            logger.info("WebSocket 已连接到 OpenClaw Gateway")
            return True
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            await self.close()
            return False

    async def _send_frame(self, frame: Dict[str, Any]) -> None:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        await self.ws.send(json.dumps(frame, ensure_ascii=False))

    async def _recv_frame(self) -> Dict[str, Any]:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        data = await self.ws.recv()
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return json.loads(data)

    async def _dispatch_event(self, event_frame: Dict[str, Any]) -> None:
        if not self.on_event:
            return
        result = self.on_event(event_frame)
        if inspect.isawaitable(result):
            await result

    async def _recv_loop(self) -> None:
        try:
            while self.ws:
                frame = await self._recv_frame()
                frame_type = frame.get("type")
                if frame_type == "res":
                    req_id = str(frame.get("id") or "").strip()
                    future = self.pending.pop(req_id, None)
                    if not future:
                        continue
                    if frame.get("ok"):
                        future.set_result(frame)
                    else:
                        future.set_exception(Exception(((frame.get("error") or {}).get("message")) or "unknown error"))
                elif frame_type == "event":
                    await self._dispatch_event(frame)
        except Exception as e:
            if not self._closing:
                logger.error(f"WebSocket 接收循环异常: {e}")
        finally:
            self.connected = False
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("gateway closed"))
            self.pending.clear()

    async def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.ws or not self.connected:
            raise RuntimeError("gateway not connected")
        req_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = future
        await self._send_frame({
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params or {},
        })
        return await future

    async def chat_send(
        self,
        *,
        message: str,
        session_key: str,
        timeout_ms: Optional[int] = None,
        thinking: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "sessionKey": session_key,
            "message": message,
            "idempotencyKey": str(uuid.uuid4()),
        }
        if timeout_ms is not None:
            payload["timeoutMs"] = timeout_ms
        if thinking:
            payload["thinking"] = thinking
        response = await self.request("chat.send", payload)
        return (response.get("payload") if isinstance(response, dict) else {}) or {}

    async def chat_inject(
        self,
        *,
        session_key: str,
        message: str,
        label: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "sessionKey": session_key,
            "message": message,
        }
        if label:
            payload["label"] = label
        response = await self.request("chat.inject", payload)
        return (response.get("payload") if isinstance(response, dict) else {}) or {}

    async def close(self) -> None:
        self._closing = True
        self.connected = False
        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._recv_task
            self._recv_task = None
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close()
            self.ws = None
        self._closing = False


import contextlib
