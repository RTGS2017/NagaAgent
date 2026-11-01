import asyncio
import json
import os
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import httpx
from fastapi import HTTPException

from apiserver import naga_auth
from apiserver.api_server import app as api_app
from apiserver.agentic_tool_loop import _execute_local_tool, format_tool_result_for_display
from apiserver.routes import extensions as extensions_routes
from apiserver.routes import openai_proxy
from apiserver.routes import tools as tools_routes
from apiserver.routes.system import _sanitize_system_config_payload
from apiserver.routes.tools import _build_tool_result_blocks
from agentserver.agent_server import app as agent_app
from agentserver.openclaw.openclaw_client import OpenClawConfig
from system import config as system_config


class _ApiSettings:
    def __init__(self, use_gateway: bool) -> None:
        self.use_gateway = use_gateway


class _Settings:
    def __init__(self, use_gateway: bool) -> None:
        self.api = _ApiSettings(use_gateway)


class _ProxyApiSettings:
    base_url = "https://api.deepseek.com/v1"
    api_key = "sk-placeholder-key-not-set"


class _ProxySettings:
    api = _ProxyApiSettings()


class _EmptyCharacterSystemSettings:
    active_character = ""


class _SystemRouteSettings:
    system = _EmptyCharacterSystemSettings()

    class api_server:
        port = 8000


class _BridgeApiSettings:
    model = "deepseek-chat"
    max_tokens = 4096


class _BridgeOnlineSearchSettings:
    search_api_key = "brave-key"


class _BridgeFeishuSettings:
    enabled = True
    app_id = "cli_a"
    app_secret = "secret"
    dm_policy = "open"
    group_policy = "allowlist"
    allow_from = ["ou_1"]
    doc_owner_open_id = "ou_owner"


class _BridgeOpenClawSettings:
    gateway_port = 28888
    feishu = _BridgeFeishuSettings()


class _BridgeSettings:
    api = _BridgeApiSettings()
    online_search = _BridgeOnlineSearchSettings()
    openclaw = _BridgeOpenClawSettings()


class _FakeQqEmailAsyncClient:
    responses: list[httpx.Response] = []
    requests: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self) -> "_FakeQqEmailAsyncClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        self.__class__.requests.append({"url": url, "headers": headers or {}})
        if not self.__class__.responses:
            raise AssertionError("未配置 fake qq-email 响应")
        return self.__class__.responses.pop(0)


def _httpx_json_response(status_code: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "https://business.example.test/api/auth/qq-email"),
    )


class ConfigAndToolTests(unittest.TestCase):
    def setUp(self) -> None:
        tools_routes._tool_status_store["current"] = {"message": "", "visible": False}
        tools_routes._clawdbot_replies.clear()
        tools_routes._live2d_actions.clear()
        tools_routes._music_commands.clear()
        _FakeQqEmailAsyncClient.responses = []
        _FakeQqEmailAsyncClient.requests = []

    def test_fastapi_routes_do_not_shadow_duplicates(self) -> None:
        for app in (api_app, agent_app):
            seen: dict[tuple[str, str], list[str]] = {}
            for route in app.routes:
                path = getattr(route, "path", "")
                methods = getattr(route, "methods", set()) or set()
                endpoint = getattr(route, "endpoint", None)
                endpoint_name = getattr(endpoint, "__name__", repr(endpoint))
                for method in methods:
                    if method in {"HEAD", "OPTIONS"}:
                        continue
                    seen.setdefault((method, path), []).append(endpoint_name)

            duplicates = {
                f"{method} {path}": endpoints
                for (method, path), endpoints in seen.items()
                if len(endpoints) > 1
            }
            self.assertEqual(duplicates, {})

    def test_bootstrap_config_from_project_example(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            runtime_config = tmp_path / "runtime" / "config.json"
            example_config = tmp_path / "project" / "config.json.example"
            example_config.parent.mkdir(parents=True)
            example_config.write_text('{"api": {"model": "demo-model"}}', encoding="utf-8")

            with (
                patch.object(system_config, "IS_PACKAGED", False),
                patch.object(
                    system_config,
                    "_get_project_config_template_paths",
                    lambda _path: [runtime_config.with_name("config.json.example"), example_config],
                ),
            ):
                system_config.bootstrap_config_from_example(str(runtime_config))

            self.assertTrue(runtime_config.exists())
            loaded = json.loads(runtime_config.read_text(encoding="utf-8"))
            self.assertEqual(loaded["api"]["model"], "demo-model")

    def test_config_path_prefers_local_config_over_user_data(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app_dir = tmp_path / "app"
            user_dir = tmp_path / "user"
            app_dir.mkdir()
            user_dir.mkdir()
            local_config = app_dir / "config.json"
            user_config = user_dir / "config.json"
            local_config.write_text('{"api": {"model": "local-model"}}', encoding="utf-8")
            user_config.write_text('{"api": {"model": "user-model"}}', encoding="utf-8")

            with (
                patch.object(system_config, "IS_PACKAGED", False),
                patch.object(system_config, "_get_app_dir", lambda: app_dir),
                patch.object(system_config, "_get_user_data_dir", lambda: user_dir),
            ):
                self.assertEqual(Path(system_config.get_config_path()), local_config)

    def test_config_path_falls_back_to_user_data_when_local_config_missing(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app_dir = tmp_path / "app"
            user_dir = tmp_path / "user"
            app_dir.mkdir()

            with (
                patch.object(system_config, "IS_PACKAGED", False),
                patch.object(system_config, "_get_app_dir", lambda: app_dir),
                patch.object(system_config, "_get_user_data_dir", lambda: user_dir),
            ):
                self.assertEqual(Path(system_config.get_config_path()), user_dir / "config.json")
                self.assertTrue(user_dir.exists())

    def test_config_manager_updates_effective_local_config(self) -> None:
        from system import config_manager as system_config_manager

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app_dir = tmp_path / "app"
            user_dir = tmp_path / "user"
            app_dir.mkdir()
            user_dir.mkdir()
            local_config = app_dir / "config.json"
            user_config = user_dir / "config.json"
            local_config.write_text('{"api": {"model": "local-model"}}', encoding="utf-8")
            user_config.write_text('{"api": {"model": "user-model"}}', encoding="utf-8")
            reloads: list[str] = []

            with (
                patch.object(system_config, "IS_PACKAGED", False),
                patch.object(system_config, "_get_app_dir", lambda: app_dir),
                patch.object(system_config, "_get_user_data_dir", lambda: user_dir),
                patch.object(system_config_manager, "hot_reload_config", lambda: reloads.append("reload")),
            ):
                success = system_config_manager.update_config({"api": {"model": "updated-local-model"}})

            self.assertTrue(success)
            self.assertEqual(json.loads(local_config.read_text(encoding="utf-8"))["api"]["model"], "updated-local-model")
            self.assertEqual(json.loads(user_config.read_text(encoding="utf-8"))["api"]["model"], "user-model")
            self.assertEqual(reloads, ["reload"])

    def test_sync_source_config_skips_when_local_config_is_effective(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            app_dir = tmp_path / "app"
            user_dir = tmp_path / "user"
            app_dir.mkdir()
            user_dir.mkdir()
            local_config = app_dir / "config.json"
            local_config.write_text('{"api": {"model": "local-model"}}', encoding="utf-8")

            with (
                patch.object(system_config, "IS_PACKAGED", False),
                patch.object(system_config, "_get_app_dir", lambda: app_dir),
                patch.object(system_config, "_get_user_data_dir", lambda: user_dir),
            ):
                self.assertFalse(system_config.sync_source_config_to_runtime())

            self.assertFalse((user_dir / "config.json").exists())

    def test_should_use_model_gateway_respects_config(self) -> None:
        with (
            patch.object(naga_auth, "is_authenticated", lambda: False),
            patch("system.config.get_config", lambda: _Settings(use_gateway=True)),
        ):
            self.assertFalse(naga_auth.should_use_model_gateway())

        with (
            patch.object(naga_auth, "is_authenticated", lambda: True),
            patch("system.config.get_config", lambda: _Settings(use_gateway=False)),
        ):
            self.assertFalse(naga_auth.should_use_model_gateway())

        with (
            patch.object(naga_auth, "is_authenticated", lambda: True),
            patch("system.config.get_config", lambda: _Settings(use_gateway=True)),
        ):
            self.assertTrue(naga_auth.should_use_model_gateway())

    def test_format_tool_result_for_display_unwraps_common_json_payload(self) -> None:
        raw = json.dumps(
            {
                "status": "success",
                "message": "ok",
                "data": {"items": [{"title": "结果", "url": "https://example.test"}]},
            },
            ensure_ascii=False,
        )

        self.assertEqual(
            format_tool_result_for_display(raw),
            {"items": [{"title": "结果", "url": "https://example.test"}]},
        )

    def test_build_tool_result_blocks_for_mcp_callback(self) -> None:
        blocks = _build_tool_result_blocks(
            [
                {
                    "service_name": "weather",
                    "tool_name": "today",
                    "status": "ok",
                    "result": {"city": "上海", "temperature": 26},
                }
            ]
        )

        self.assertIn("```tool-result", blocks)
        self.assertIn("✅ weather: today", blocks)
        self.assertIn('"city": "上海"', blocks)

    def test_local_file_tools_execute_against_temp_workspace(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "note.txt"

            write_result = asyncio.run(
                _execute_local_tool(
                    {"agentType": "tool", "tool": "write"},
                    "write",
                    {"file_path": str(target), "content": "alpha\nbeta\n"},
                )
            )
            self.assertEqual(write_result["status"], "success")

            read_result = asyncio.run(
                _execute_local_tool(
                    {"agentType": "tool", "tool": "read"},
                    "read",
                    {"file_path": str(target)},
                )
            )
            self.assertEqual(read_result["result"], "alpha\nbeta\n")

            edit_result = asyncio.run(
                _execute_local_tool(
                    {"agentType": "tool", "tool": "edit"},
                    "edit",
                    {"file_path": str(target), "old_string": "beta", "new_string": "gamma"},
                )
            )
            self.assertEqual(edit_result["status"], "success")

            grep_result = asyncio.run(
                _execute_local_tool(
                    {"agentType": "tool", "tool": "grep"},
                    "grep",
                    {"path": str(target), "pattern": "gamma"},
                )
            )
            self.assertEqual(grep_result["status"], "success")
            self.assertIn("gamma", grep_result["result"])

    def test_api_server_lightweight_smoke_routes(self) -> None:
        async def _run_smoke() -> None:
            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch.object(naga_auth, "get_access_token", lambda: None):
                    auth_response = await client.get("/auth/me")
                self.assertEqual(auth_response.status_code, 401)
                self.assertEqual(auth_response.json()["detail"], "未登录")

                health_response = await client.get("/health")
                self.assertEqual(health_response.status_code, 200)
                self.assertEqual(health_response.json()["status"], "healthy")

                tool_status_response = await client.get("/tool_status")
                self.assertEqual(tool_status_response.status_code, 200)
                self.assertEqual(tool_status_response.json(), {"message": "", "visible": False})

                config_response = await client.get("/system/config")
                self.assertEqual(config_response.status_code, 200)
                self.assertEqual(config_response.json()["status"], "success")

                with (
                    patch.object(naga_auth, "should_use_model_gateway", lambda: False),
                    patch("system.config.config", _ProxySettings()),
                ):
                    completion_response = await client.post(
                        "/v1/chat/completions",
                        json={
                            "model": "deepseek-chat",
                            "messages": [{"role": "user", "content": "ping"}],
                        },
                    )
                self.assertEqual(completion_response.status_code, 400)
                self.assertIn("未配置本地模型 API", completion_response.json()["detail"])

        asyncio.run(_run_smoke())

    def test_auth_routes_restore_header_token_and_bind_qq_email(self) -> None:
        async def _run_request() -> None:
            restored_tokens: list[str] = []
            sent_verifications: list[dict[str, str]] = []
            updated_payloads: list[dict[str, Any]] = []

            async def _fake_get_me(token: str) -> dict[str, Any]:
                return {"username": f"user-{token}"}

            async def _fake_send_qq_verification(
                email: str,
                token: str,
                captcha_id: str = "",
                captcha_answer: str = "",
            ) -> dict[str, Any]:
                sent_verifications.append(
                    {
                        "email": email,
                        "token": token,
                        "captcha_id": captcha_id,
                        "captcha_answer": captcha_answer,
                    }
                )
                return {"success": True}

            async def _fake_bind_qq_email(
                email: str,
                verification_code: str,
                token: str,
            ) -> dict[str, Any]:
                return {
                    "ok": True,
                    "binding": {
                        "qqEmail": email,
                        "verificationCode": verification_code,
                        "token": token,
                    },
                }

            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch.object(naga_auth, "get_access_token", lambda: None):
                    login_response = await client.post("/auth/login", json={"username": "", "password": ""})
                    send_unauthenticated = await client.post(
                        "/auth/send-qq-verification",
                        json={"email": "10000@qq.com"},
                    )

                with (
                    patch.object(naga_auth, "get_access_token", lambda: None),
                    patch.object(naga_auth, "restore_token", lambda token: restored_tokens.append(token)),
                    patch.object(naga_auth, "get_me", _fake_get_me),
                    patch.object(naga_auth, "get_user_info", lambda: None),
                    patch.object(naga_auth, "send_qq_verification", _fake_send_qq_verification),
                    patch.object(naga_auth, "bind_qq_email", _fake_bind_qq_email),
                    patch("apiserver.routes.auth.update_config", lambda payload: updated_payloads.append(payload)),
                ):
                    me_response = await client.get(
                        "/auth/me",
                        headers={"Authorization": "Bearer header-token"},
                    )
                    send_response = await client.post(
                        "/auth/send-qq-verification",
                        json={
                            "email": "10000@qq.com",
                            "captcha_id": "cap-1",
                            "captcha_answer": "42",
                        },
                        headers={"Authorization": "Bearer qq-token"},
                    )
                    bind_response = await client.post(
                        "/auth/qq-email",
                        json={"qq_email": "10000@qq.com", "verification_code": "654321"},
                        headers={"Authorization": "Bearer bind-token"},
                    )

            self.assertEqual(login_response.status_code, 400)
            self.assertEqual(login_response.json()["detail"], "用户名和密码不能为空")
            self.assertEqual(send_unauthenticated.status_code, 401)

            self.assertEqual(me_response.status_code, 200)
            self.assertEqual(me_response.json()["user"]["username"], "user-header-token")
            self.assertIn("header-token", restored_tokens)

            self.assertEqual(send_response.status_code, 200)
            self.assertEqual(send_response.json()["success"], True)
            self.assertIn(
                {
                    "email": "10000@qq.com",
                    "token": "qq-token",
                    "captcha_id": "cap-1",
                    "captcha_answer": "42",
                },
                sent_verifications,
            )

            self.assertEqual(bind_response.status_code, 200)
            self.assertEqual(bind_response.json()["ok"], True)
            self.assertEqual(updated_payloads[-1]["notifications"]["qq"]["qq_email"], "10000@qq.com")
            self.assertEqual(updated_payloads[-1]["notifications"]["qq"]["user_qq"], "10000")
            self.assertTrue(updated_payloads[-1]["notifications"]["qq"]["binding_verified"])

        asyncio.run(_run_request())

    def test_auth_qq_email_get_maps_upstream_response_and_errors(self) -> None:
        async def _run_request() -> None:
            success_payload = {
                "ok": True,
                "qqEmail": "10000@qq.com",
                "qqNumber": "10000",
            }
            _FakeQqEmailAsyncClient.responses = [
                _httpx_json_response(200, success_payload),
                _httpx_json_response(409, {"message": "未绑定"}),
            ]

            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with (
                    patch.object(naga_auth, "get_access_token", lambda: None),
                    patch.object(naga_auth, "restore_token", lambda _token: None),
                    patch("apiserver.routes.auth.httpx.AsyncClient", _FakeQqEmailAsyncClient),
                ):
                    success_response = await client.get(
                        "/auth/qq-email",
                        headers={"Authorization": "Bearer query-token"},
                    )
                    error_response = await client.get(
                        "/auth/qq-email",
                        headers={"Authorization": "Bearer query-token"},
                    )

            self.assertEqual(success_response.status_code, 200)
            self.assertEqual(success_response.json(), success_payload)
            self.assertEqual(error_response.status_code, 409)
            self.assertEqual(error_response.json()["detail"], "未绑定")
            self.assertEqual(len(_FakeQqEmailAsyncClient.requests), 2)
            self.assertEqual(
                _FakeQqEmailAsyncClient.requests[0]["headers"]["Authorization"],
                "Bearer query-token",
            )

        asyncio.run(_run_request())

    def test_tool_notification_and_ui_polling_routes(self) -> None:
        async def _run_request() -> None:
            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                missing_session = await client.post(
                    "/tool_notification",
                    json={"stage": "executing"},
                )
                show_status = await client.post(
                    "/tool_notification",
                    json={
                        "session_id": "session-1",
                        "stage": "executing",
                        "tool_calls": [{"service_name": "weather", "tool_name": "today", "status": "ok"}],
                    },
                )
                visible_status = await client.get("/tool_status")
                hide_status = await client.post(
                    "/tool_notification",
                    json={"session_id": "session-1", "stage": "hide"},
                )
                hidden_status = await client.get("/tool_status")

                mcp_result = await client.post(
                    "/ui_notification",
                    json={
                        "action": "show_mcp_result",
                        "results": [
                            {
                                "service_name": "weather",
                                "tool_name": "today",
                                "status": "ok",
                                "result": {"city": "上海"},
                            }
                        ],
                    },
                )
                first_replies = await client.get("/clawdbot/replies")
                empty_replies = await client.get("/clawdbot/replies")

                live2d_response = await client.post(
                    "/ui_notification",
                    json={"action": "live2d_action", "action_name": "wave"},
                )
                live2d_actions = await client.get("/live2d/actions")
                live2d_empty = await client.get("/live2d/actions")

                music_response = await client.post(
                    "/ui_notification",
                    json={"action": "music_control", "music_action": "play", "track": "theme"},
                )
                music_commands = await client.get("/music/commands")
                music_empty = await client.get("/music/commands")

                tool_result = await client.post(
                    "/tool_result",
                    json={
                        "session_id": "session-1",
                        "type": "tool_completed_with_ai_response",
                        "ai_response": "工具回复",
                        "result": "ok",
                    },
                )
                tool_result_replies = await client.get("/clawdbot/replies")

            self.assertEqual(missing_session.status_code, 400)
            self.assertEqual(missing_session.json()["detail"], "缺少session_id")
            self.assertEqual(show_status.status_code, 200)
            self.assertTrue(show_status.json()["success"])
            self.assertEqual(visible_status.json()["visible"], True)
            self.assertIn("执行中", visible_status.json()["message"])
            self.assertEqual(hide_status.status_code, 200)
            self.assertEqual(hidden_status.json(), {"message": "", "visible": False})

            self.assertEqual(mcp_result.status_code, 200)
            self.assertEqual(first_replies.status_code, 200)
            self.assertIn("```tool-result", first_replies.json()["replies"][0])
            self.assertIn("上海", first_replies.json()["replies"][0])
            self.assertEqual(empty_replies.json(), {"replies": []})

            self.assertEqual(live2d_response.status_code, 200)
            self.assertEqual(live2d_actions.json(), {"actions": ["wave"]})
            self.assertEqual(live2d_empty.json(), {"actions": []})

            self.assertEqual(music_response.status_code, 200)
            self.assertEqual(music_commands.json(), {"commands": [{"action": "play", "track": "theme"}]})
            self.assertEqual(music_empty.json(), {"commands": []})

            self.assertEqual(tool_result.status_code, 200)
            self.assertEqual(tool_result_replies.json(), {"replies": ["工具回复"]})

        asyncio.run(_run_request())

    def test_queue_push_direct_and_active_conversation_paths(self) -> None:
        async def _run_request() -> None:
            class _FakeMessageQueue:
                def __init__(self) -> None:
                    self.active = False
                    self.pushed: list[tuple[str, str, dict[str, Any]]] = []
                    self.ephemeral: list[tuple[str, dict[str, Any]]] = []

                def is_conversation_active(self) -> bool:
                    return self.active

                def push(self, content: str, source: str, metadata: dict[str, Any]) -> None:
                    self.pushed.append((content, source, metadata))

                def set_ephemeral_screen(self, content: str, metadata: dict[str, Any]) -> None:
                    self.ephemeral.append((content, metadata))

            fake_queue = _FakeMessageQueue()
            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with patch("apiserver.message_queue.get_message_queue", lambda: fake_queue):
                    empty_response = await client.post("/queue/push", json={"content": ""})
                    heartbeat_response = await client.post(
                        "/queue/push",
                        json={"source": "heartbeat", "content": "心跳"},
                    )
                    heartbeat_replies = await client.get("/clawdbot/replies")
                    screen_response = await client.post(
                        "/queue/push",
                        json={
                            "source": "screen_monitor",
                            "content": "屏幕内容",
                            "metadata": {"window": "demo"},
                        },
                    )
                    fake_queue.active = True
                    queued_response = await client.post(
                        "/queue/push",
                        json={
                            "source": "user",
                            "content": "补充信息",
                            "metadata": {"priority": "high"},
                        },
                    )

            self.assertEqual(empty_response.json(), {"status": "empty"})
            self.assertEqual(heartbeat_response.json(), {"status": "direct"})
            self.assertEqual(heartbeat_replies.json(), {"replies": ["心跳"]})
            self.assertEqual(screen_response.json(), {"status": "direct"})
            self.assertEqual(fake_queue.ephemeral, [("屏幕内容", {"window": "demo"})])
            self.assertEqual(queued_response.json(), {"status": "queued"})
            self.assertEqual(fake_queue.pushed, [("补充信息", "user", {"priority": "high"})])

        asyncio.run(_run_request())

    def test_system_config_route_sanitizes_dynamic_live2d_source(self) -> None:
        async def _run_request() -> None:
            payload: dict[str, Any] = {
                "web_live2d": {
                    "custom_models": [{"id": "custom-1"}],
                    "model": {
                        "source": "http://localhost:8000/custom-live2d/custom-1/avatar/avatar.model3.json",
                        "x": 0.5,
                    },
                }
            }
            captured_payload: dict[str, Any] = {}

            def _capture_update_config(next_payload: dict[str, Any]) -> bool:
                captured_payload.update(next_payload)
                return True

            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with (
                    patch("apiserver.routes.system.update_config", _capture_update_config),
                    patch("apiserver.routes.system.get_config_snapshot", lambda: {}),
                ):
                    response = await client.post("/system/config", json=payload)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "success")
            self.assertNotIn("custom_models", captured_payload["web_live2d"])
            self.assertNotIn("source", captured_payload["web_live2d"]["model"])
            self.assertIn("custom_models", payload["web_live2d"])
            self.assertIn("source", payload["web_live2d"]["model"])

        asyncio.run(_run_request())

    def test_system_config_route_normalizes_legacy_service_keys(self) -> None:
        async def _run_request() -> None:
            captured_payload: dict[str, Any] = {}

            def _capture_update_config(next_payload: dict[str, Any]) -> bool:
                captured_payload.update(next_payload)
                return True

            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with (
                    patch(
                        "apiserver.routes.system.get_config_snapshot",
                        lambda: {
                            "agentserver": {"enabled": True, "port": 8101},
                            "mcpserver": {"enabled": True, "port": 8103},
                        },
                    ),
                    patch("apiserver.routes.system.get_config", lambda: _SystemRouteSettings()),
                ):
                    get_response = await client.get("/system/config")

                with (
                    patch("apiserver.routes.system.update_config", _capture_update_config),
                    patch("apiserver.routes.system.get_config_snapshot", lambda: {}),
                ):
                    post_response = await client.post(
                        "/system/config",
                        json={
                            "agentserver": {"enabled": True, "port": 8201},
                            "mcpserver": {"enabled": True, "port": 8203},
                        },
                    )

            self.assertEqual(get_response.status_code, 200)
            config = get_response.json()["config"]
            self.assertNotIn("agentserver", config)
            self.assertNotIn("mcpserver", config)
            self.assertEqual(config["agent_server"]["port"], 8101)
            self.assertEqual(config["mcp_server"]["port"], 8103)

            self.assertEqual(post_response.status_code, 200)
            self.assertNotIn("agentserver", captured_payload)
            self.assertNotIn("mcpserver", captured_payload)
            self.assertEqual(captured_payload["agent_server"]["port"], 8201)
            self.assertEqual(captured_payload["mcp_server"]["port"], 8203)

        asyncio.run(_run_request())

    def test_travel_browser_settings_route_persists_and_syncs_agent_visibility(self) -> None:
        async def _run_request() -> None:
            with TemporaryDirectory() as tmp_dir:
                from apiserver import travel_service

                travel_dir = Path(tmp_dir)
                with patch.object(travel_service, "TRAVEL_DIR", travel_dir):
                    session = travel_service.create_session(
                        agent_id="agent-1",
                        browser_visible=False,
                        browser_keep_open=False,
                        browser_idle_timeout_seconds=45,
                    )
                    session.openclaw_session_key = "travel:agent-1:test"
                    session.status = travel_service.TravelStatus.RUNNING
                    travel_service.save_session(session)

                    agent_calls: list[dict[str, Any]] = []

                    async def _capture_agent_call(
                        method: str,
                        path: str,
                        **kwargs: Any,
                    ) -> dict[str, Any]:
                        agent_calls.append({"method": method, "path": path, **kwargs})
                        return {"status": "success"}

                    transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
                    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                        with patch("apiserver.routes.extensions._call_agentserver", _capture_agent_call):
                            response = await client.post(
                                f"/travel/sessions/{session.session_id}/browser",
                                json={
                                    "browser_visible": True,
                                    "browser_keep_open": True,
                                    "browser_idle_timeout_seconds": 12,
                                },
                            )

                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["status"], "success")
                    self.assertTrue(body["session"]["browser_visible"])
                    self.assertTrue(body["session"]["browser_keep_open"])
                    self.assertEqual(body["session"]["browser_idle_timeout_seconds"], 30)

                    reloaded = travel_service.load_session(session.session_id)
                    self.assertTrue(reloaded.browser_visible)
                    self.assertTrue(reloaded.browser_keep_open)
                    self.assertEqual(reloaded.browser_idle_timeout_seconds, 30)

                    policy = json.loads((travel_dir / "browser-policies.json").read_text(encoding="utf-8"))
                    self.assertTrue(policy["travel:agent-1:test"]["visible"])
                    self.assertTrue(policy["travel:agent-1:test"]["keepOpen"])
                    self.assertEqual(policy["travel:agent-1:test"]["idleTimeoutSeconds"], 30)

                    self.assertEqual(len(agent_calls), 1)
                    self.assertEqual(agent_calls[0]["method"], "POST")
                    self.assertEqual(agent_calls[0]["path"], "/travel/browser-settings")
                    self.assertEqual(
                        agent_calls[0]["json_body"],
                        {"session_id": session.session_id, "browser_visible": True},
                    )

        asyncio.run(_run_request())

    def test_skill_write_rejects_path_traversal_names(self) -> None:
        traversal_names = [
            "../escape",
            "..\\escape",
            "..",
            "/tmp/escape",
            "C:\\Temp\\escape",
            "\\\\server\\share\\escape",
            "nested/skill",
            "nested\\skill",
        ]

        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "skills"
            for name in traversal_names:
                with self.subTest(name=name):
                    with self.assertRaises(HTTPException):
                        extensions_routes._write_skill_file_to_dir(base_dir, name, "poc")

            skill_path = extensions_routes._write_skill_file_to_dir(base_dir, "safe-skill_1", "ok")
            self.assertEqual(skill_path, base_dir.resolve() / "safe-skill_1" / "SKILL.md")
            self.assertEqual(skill_path.read_text(encoding="utf-8"), "ok")

    def test_skill_delete_and_read_reject_path_traversal_names(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir)
            public_dir = data_dir / "skills" / "public"
            public_dir.mkdir(parents=True)
            (public_dir / "safe").mkdir()
            (public_dir / "safe" / "SKILL.md").write_text("content", encoding="utf-8")

            outside_dir = data_dir / "outside"
            outside_dir.mkdir()
            marker = outside_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with (
                patch.object(extensions_routes, "NAGA_PUBLIC_SKILLS_DIR", public_dir),
                patch.object(extensions_routes, "NAGA_CACHE_SKILLS_DIR", data_dir / "skills" / "cache"),
                patch.object(extensions_routes, "OPENCLAW_SKILLS_DIR", data_dir / "openclaw" / "skills"),
                patch.object(extensions_routes, "NAGA_AGENTS_DIR", data_dir / "agents"),
            ):
                with self.assertRaises(HTTPException):
                    extensions_routes._delete_skill_from_scope("../outside", "public")
                with self.assertRaises(HTTPException):
                    extensions_routes._read_skill_content_from_scope("../outside", "public")

                self.assertTrue(marker.exists())
                self.assertEqual(extensions_routes._read_skill_content_from_scope("safe", "public"), "content")
                deleted_path = extensions_routes._delete_skill_from_scope("safe", "public")
                self.assertEqual(deleted_path, public_dir.resolve() / "safe")
                self.assertFalse(deleted_path.exists())

    def test_openai_proxy_uses_local_api_when_gateway_disabled(self) -> None:
        class _ProxyApiSettings:
            base_url = "https://local.example/v1"
            api_key = "sk-local"

        class _ProxySettings:
            api = _ProxyApiSettings()

        with (
            patch.object(naga_auth, "should_use_model_gateway", lambda: False),
            patch("system.config.config", _ProxySettings()),
        ):
            self.assertEqual(
                openai_proxy._get_upstream_url(),
                "https://local.example/v1/chat/completions",
            )

    def test_openai_proxy_rejects_default_placeholder_api_when_gateway_disabled(self) -> None:
        class _ProxyApiSettings:
            base_url = "https://api.deepseek.com/v1"
            api_key = "sk-placeholder-key-not-set"

        class _ProxySettings:
            api = _ProxyApiSettings()

        with (
            patch.object(naga_auth, "should_use_model_gateway", lambda: False),
            patch("system.config.config", _ProxySettings()),
        ):
            self.assertFalse(openai_proxy._is_user_configured_api())

    def test_openai_proxy_rejects_placeholder_api_on_custom_base_url(self) -> None:
        class _ProxyApiSettings:
            base_url = "https://local.example/v1"
            api_key = "your-api-key-here"

        class _ProxySettings:
            api = _ProxyApiSettings()

        with (
            patch.object(naga_auth, "should_use_model_gateway", lambda: False),
            patch("system.config.config", _ProxySettings()),
        ):
            self.assertFalse(openai_proxy._is_user_configured_api())

    def test_sanitize_system_config_payload_preserves_existing_real_api_key(self) -> None:
        payload: dict[str, Any] = {
            "api": {
                "api_key": "your-api-key-here",
                "base_url": "https://api.deepseek.com/v1",
            }
        }
        current_config: dict[str, Any] = {
            "api": {
                "api_key": "sk-real-user-key",
                "base_url": "https://api.deepseek.com/v1",
            }
        }

        sanitized = _sanitize_system_config_payload(payload, current_config)

        self.assertEqual(sanitized["api"]["api_key"], "sk-real-user-key")
        self.assertEqual(payload["api"]["api_key"], "your-api-key-here")

    def test_system_config_route_does_not_overwrite_real_api_key_with_placeholder(self) -> None:
        async def _run_request() -> None:
            captured_payload: dict[str, Any] = {}

            def _capture_update_config(next_payload: dict[str, Any]) -> bool:
                captured_payload.update(next_payload)
                return True

            current_config: dict[str, Any] = {
                "api": {
                    "api_key": "sk-real-user-key",
                    "base_url": "https://api.deepseek.com/v1",
                }
            }
            payload: dict[str, Any] = {
                "api": {
                    "api_key": "sk-placeholder-key-not-set",
                    "base_url": "https://api.deepseek.com/v1",
                }
            }

            transport = httpx.ASGITransport(app=api_app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                with (
                    patch("apiserver.routes.system.update_config", _capture_update_config),
                    patch("apiserver.routes.system.get_config_snapshot", lambda: current_config),
                ):
                    response = await client.post("/system/config", json=payload)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(captured_payload["api"]["api_key"], "sk-real-user-key")

        asyncio.run(_run_request())

    def test_sanitize_system_config_payload_removes_dynamic_live2d_source_without_mutating_input(self) -> None:
        payload: dict[str, Any] = {
            "web_live2d": {
                "custom_model_id": "custom-1",
                "custom_models": [{"id": "custom-1"}],
                "model": {
                    "source": "http://localhost:8000/custom-live2d/custom-1/avatar/avatar.model3.json",
                    "x": 0.5,
                },
            }
        }

        sanitized = _sanitize_system_config_payload(payload)

        self.assertNotIn("custom_models", sanitized["web_live2d"])
        self.assertNotIn("source", sanitized["web_live2d"]["model"])
        self.assertIn("custom_models", payload["web_live2d"])
        self.assertIn("source", payload["web_live2d"]["model"])

    def test_sanitize_system_config_payload_removes_127001_and_naga_char_dynamic_sources(self) -> None:
        for source in (
            "http://127.0.0.1:8000/characters/%E5%A8%9C/test.model3.json",
            "naga-char://娜杰日达/NagaTest2/NagaTest2.model3.json",
        ):
            payload: dict[str, Any] = {"web_live2d": {"model": {"source": source}}}
            sanitized = _sanitize_system_config_payload(payload)
            self.assertNotIn("source", sanitized["web_live2d"]["model"])

    def test_sanitize_system_config_payload_keeps_user_live2d_source(self) -> None:
        payload: dict[str, Any] = {
            "web_live2d": {
                "model": {
                    "source": "https://cdn.example.test/avatar.model3.json",
                },
            }
        }

        sanitized = _sanitize_system_config_payload(payload)

        self.assertEqual(
            sanitized["web_live2d"]["model"]["source"],
            "https://cdn.example.test/avatar.model3.json",
        )

    def test_voice_realtime_import_does_not_require_qwen_optional_dependency(self) -> None:
        import voice.input.voice_realtime as voice_realtime

        self.assertTrue(voice_realtime.VoiceClientFactory.is_provider_available("qwen"))
        self.assertTrue(voice_realtime.VoiceClientFactory.is_provider_available("openai"))
        self.assertTrue(voice_realtime.VoiceClientFactory.is_provider_available("local"))

    def test_openclaw_config_normalizes_hooks_path_and_uses_hooks_token(self) -> None:
        cfg = OpenClawConfig(
            gateway_url="http://127.0.0.1:20789",
            gateway_token="gateway-token",
            hooks_token="hooks-token",
            hooks_path="hooks/",
        )

        self.assertEqual(cfg.hooks_path, "/hooks")
        self.assertEqual(cfg.get_hooks_agent_url(), "http://127.0.0.1:20789/hooks/agent")
        self.assertEqual(cfg.get_gateway_headers()["Authorization"], "Bearer gateway-token")
        self.assertEqual(cfg.get_hooks_headers()["Authorization"], "Bearer hooks-token")

    def test_openclaw_bridge_creates_and_injects_runtime_config(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            config_path = tmp_path / "openclaw.json"
            state_dir = tmp_path / "state"
            old_config_path = os.environ.get("OPENCLAW_CONFIG_PATH")
            old_state_dir = os.environ.get("OPENCLAW_STATE_DIR")
            os.environ["OPENCLAW_CONFIG_PATH"] = str(config_path)
            os.environ["OPENCLAW_STATE_DIR"] = str(state_dir)
            try:
                from agentserver.openclaw import llm_config_bridge

                with patch.object(llm_config_bridge, "_get_gateway_port", lambda: 28888):
                    self.assertTrue(llm_config_bridge.ensure_openclaw_config())

                created = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(created["gateway"]["port"], 28888)
                self.assertEqual(created["gateway"]["mode"], "local")
                self.assertEqual(created["hooks"]["path"], "/hooks")
                self.assertTrue(created["hooks"]["allowRequestSessionKey"])

                with (
                    patch("system.config.config", _BridgeSettings()),
                    patch("system.config.get_server_port", lambda _name: 8123),
                    patch("system.config.get_data_dir", lambda: tmp_path / "naga-data"),
                    patch.object(llm_config_bridge, "_get_gateway_port", lambda: 28888),
                ):
                    self.assertTrue(llm_config_bridge.inject_naga_llm_config())

                injected = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(injected["gateway"]["port"], 28888)
                self.assertEqual(injected["gateway"]["mode"], "local")
                self.assertEqual(injected["hooks"]["path"], "/hooks")
                self.assertTrue(injected["hooks"]["allowRequestSessionKey"])
                self.assertEqual(injected["agents"]["defaults"]["model"]["primary"], "deepseek/deepseek-chat")
                self.assertEqual(
                    injected["models"]["providers"]["deepseek"]["baseUrl"],
                    "http://127.0.0.1:8123/v1",
                )
                self.assertEqual(injected["tools"]["web"]["search"]["apiKey"], "naga-search-proxy")
                self.assertEqual(injected["env"]["BRAVE_API_KEY"], "naga-search-proxy")
                self.assertEqual(injected["channels"]["feishu"]["appId"], "cli_a")
                auth_profiles = json.loads(
                    (config_path.parent / "agents" / "main" / "agent" / "auth-profiles.json").read_text(
                        encoding="utf-8",
                    )
                )
                self.assertIn("deepseek:default", auth_profiles)
            finally:
                if old_config_path is None:
                    os.environ.pop("OPENCLAW_CONFIG_PATH", None)
                else:
                    os.environ["OPENCLAW_CONFIG_PATH"] = old_config_path
                if old_state_dir is None:
                    os.environ.pop("OPENCLAW_STATE_DIR", None)
                else:
                    os.environ["OPENCLAW_STATE_DIR"] = old_state_dir


class McpFuncNameSanitizeTests(unittest.TestCase):
    """验证 MCP function name 的 sanitize 与还原。

    OpenAI 要求 tools[*].function.name 匹配 ^[a-zA-Z0-9_-]+$，
    而 MCP 的 service_name/command 可能含中文等非法字符，
    需在生成时 sanitize、在解析时无损还原。
    """

    _PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    def setUp(self) -> None:
        from apiserver.tool_schemas import invalidate_schema_cache

        invalidate_schema_cache()

    def test_make_func_name_is_openai_compliant_and_roundtrips(self) -> None:
        from apiserver.tool_schemas import _make_mcp_func_name, resolve_mcp_func_name

        cases = [
            ("app_launcher", "获取应用列表"),
            ("app_launcher", "启动应用"),
            ("天气时间Agent", "query"),
            ("svc with space", "do/it:now"),
        ]
        for service_name, command in cases:
            with self.subTest(service=service_name, command=command):
                func_name = _make_mcp_func_name(service_name, command)
                self.assertRegex(func_name, self._PATTERN)
                self.assertEqual(
                    resolve_mcp_func_name(func_name), (service_name, command)
                )

    def test_pure_ascii_keeps_legacy_naming(self) -> None:
        from apiserver.tool_schemas import _make_mcp_func_name

        # 纯 ASCII 名称保持原有命名约定，确保向后兼容
        self.assertEqual(
            _make_mcp_func_name("weather_time", "today_weather"),
            "mcp__weather_time__today_weather",
        )

    def test_make_func_name_is_deterministic(self) -> None:
        from apiserver.tool_schemas import _make_mcp_func_name

        first = _make_mcp_func_name("app_launcher", "获取应用列表")
        second = _make_mcp_func_name("app_launcher", "获取应用列表")
        self.assertEqual(first, second)

    def test_distinct_inputs_produce_distinct_names(self) -> None:
        from apiserver.tool_schemas import _make_mcp_func_name

        a = _make_mcp_func_name("app_launcher", "获取应用列表")
        b = _make_mcp_func_name("app_launcher", "启动应用")
        self.assertNotEqual(a, b)

    def test_resolve_unknown_returns_none(self) -> None:
        from apiserver.tool_schemas import resolve_mcp_func_name

        self.assertIsNone(resolve_mcp_func_name("mcp__never__registered"))

    def test_invalidate_keeps_mapping(self) -> None:
        # _mcp_name_map 是 _make_mcp_func_name 的确定性缓存，刻意不随 schema
        # 缓存清空，以免 MCP 注册变更打断「生成→解析」之间的还原能力。
        from apiserver.tool_schemas import (
            _make_mcp_func_name,
            invalidate_schema_cache,
            resolve_mcp_func_name,
        )

        func_name = _make_mcp_func_name("天气时间Agent", "query")
        self.assertIsNotNone(resolve_mcp_func_name(func_name))
        invalidate_schema_cache()
        self.assertEqual(
            resolve_mcp_func_name(func_name), ("天气时间Agent", "query")
        )

    def test_convert_native_to_dispatch_restores_original_names(self) -> None:
        from apiserver.tool_schemas import _make_mcp_func_name
        from apiserver.agentic_tool_loop import _convert_native_to_dispatch

        func_name = _make_mcp_func_name("app_launcher", "获取应用列表")
        native = [
            {
                "name": func_name,
                "arguments": json.dumps({"keyword": "微信"}),
                "id": "call_1",
            }
        ]
        dispatch = _convert_native_to_dispatch(native)[0]
        self.assertEqual(dispatch["agentType"], "mcp")
        self.assertEqual(dispatch["service_name"], "app_launcher")
        self.assertEqual(dispatch["tool_name"], "获取应用列表")
        self.assertEqual(dispatch["keyword"], "微信")

    def test_convert_native_to_dispatch_falls_back_to_split(self) -> None:
        # 未经登记的纯 ASCII 名称仍能通过 split 还原
        from apiserver.agentic_tool_loop import _convert_native_to_dispatch

        native = [
            {"name": "mcp__weather_time__today_weather", "arguments": "{}", "id": "c2"}
        ]
        dispatch = _convert_native_to_dispatch(native)[0]
        self.assertEqual(dispatch["service_name"], "weather_time")
        self.assertEqual(dispatch["tool_name"], "today_weather")

    def test_native_assistant_message_keeps_reasoning_for_tool_history(self) -> None:
        from apiserver.agentic_tool_loop import _build_native_assistant_message

        message = _build_native_assistant_message(
            "我来查一下",
            [
                {
                    "_tool_call_id": "call_1",
                    "_original_name": "tool__search",
                    "_original_args": "{\"q\":\"naga\"}",
                }
            ],
            "先判断需要搜索。",
        )

        self.assertEqual(message["reasoning_content"], "先判断需要搜索。")
        self.assertEqual(message["tool_calls"][0]["id"], "call_1")

    def test_llm_message_preparation_replays_reasoning_only_for_deepseek_tool_calls(self) -> None:
        from apiserver.llm_service import LLMService

        service = LLMService.__new__(LLMService)
        messages: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "需要调用工具。",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "tool__search", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "普通回复",
                "reasoning_content": "普通思考不应回传。",
            },
        ]

        deepseek_messages = service._prepare_messages_for_model(
            messages,
            "deepseek/deepseek-v3.2",
            "https://api.deepseek.com/v1",
            "deepseek",
        )
        reasoner_messages = service._prepare_messages_for_model(
            messages,
            "deepseek/deepseek-reasoner",
            "https://api.deepseek.com/v1",
            "deepseek",
        )

        self.assertIn("reasoning_content", deepseek_messages[0])
        self.assertNotIn("reasoning_content", deepseek_messages[1])
        self.assertNotIn("reasoning_content", reasoner_messages[0])

    def test_stream_chat_returns_visible_error_after_empty_stream_retries(self) -> None:
        from apiserver.llm_service import LLMService

        class _LlmApiSettings:
            api_key = "sk-real-user-key"
            base_url = "https://api.deepseek.com/v1"
            model = "deepseek-v3.2"
            provider = "deepseek"
            use_gateway = False
            api_format = "openai"
            temperature = 0.7
            max_tokens = 10000

        class _LlmSettings:
            api = _LlmApiSettings()

        class _EmptyDelta:
            content: None = None
            reasoning_content: None = None
            tool_calls: None = None

        class _EmptyChoice:
            delta = _EmptyDelta()
            finish_reason = "stop"

        class _EmptyChunk:
            choices = [_EmptyChoice()]

        class _EmptyStream:
            def __init__(self) -> None:
                self._sent = False

            def __aiter__(self) -> "_EmptyStream":
                return self

            async def __anext__(self) -> _EmptyChunk:
                if self._sent:
                    raise StopAsyncIteration
                self._sent = True
                return _EmptyChunk()

        async def _run_stream() -> None:
            service = LLMService.__new__(LLMService)
            service._initialized = True
            attempts = 0

            async def _fake_acompletion(**_kwargs: Any) -> _EmptyStream:
                nonlocal attempts
                attempts += 1
                return _EmptyStream()

            events: list[str] = []
            with (
                patch("apiserver.llm_service.get_config", lambda: _LlmSettings()),
                patch("apiserver.llm_service.naga_auth.should_use_model_gateway", lambda: False),
                patch("apiserver.llm_service.acompletion", _fake_acompletion),
            ):
                async for event in service.stream_chat_with_context([{"role": "user", "content": "你好"}]):
                    events.append(event)

            self.assertEqual(attempts, 3)
            self.assertTrue(any("模型服务返回空响应" in event for event in events))

        asyncio.run(_run_stream())


if __name__ == "__main__":
    unittest.main()
