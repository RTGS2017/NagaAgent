import asyncio
import json
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from apiserver.routes import system as system_routes
from apiserver.routes import auth as auth_routes
from apiserver.routes.auth import _ensure_wav_header
from system.config import VERSION


class _FakeTtsResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.content = b"\xff\xfb\x90\x64mp3-data"
        self.headers = {"content-type": "audio/mpeg"}


class _FakeTtsAsyncClient:
    requests: list[dict[str, Any]] = []
    responses: list[_FakeTtsResponse] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self) -> "_FakeTtsAsyncClient":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _FakeTtsResponse:
        self.__class__.requests.append({"url": url, "json": dict(json), "headers": dict(headers)})
        if self.__class__.responses:
            return self.__class__.responses.pop(0)
        return _FakeTtsResponse()


class _LocalTtsConfig:
    class tts:
        port = 5048
        default_voice = "zh-CN-XiaoxiaoNeural"
        default_format = "mp3"
        default_speed = 1.0
        require_api_key = True
        api_key = "local-tts-key"


def _build_json_request(payload: dict[str, Any]) -> Request:
    body = json.dumps(payload).encode("utf-8")

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/tts/speech", "headers": []}, receive)


class UpdateRouteTests(unittest.TestCase):
    def test_saved_config_cannot_override_runtime_version(self) -> None:
        payload = {"system": {"version": "0.0.1", "voice_enabled": True}}

        sanitized = system_routes._sanitize_system_config_payload(payload)

        self.assertEqual(sanitized["system"]["version"], VERSION)
        self.assertEqual(payload["system"]["version"], "0.0.1")

    def test_github_release_payload_selects_platform_installer(self) -> None:
        release: dict[str, Any] = {
            "tag_name": "v5.1.3",
            "name": "NagaAgent 5.1.3",
            "body": "Release notes",
            "html_url": "https://github.com/RTGS2017/NagaAgent/releases/tag/v5.1.3",
            "assets": [
                {
                    "name": "Naga.Agent.Setup.5.1.3.exe.blockmap",
                    "browser_download_url": "https://example.test/app.exe.blockmap",
                    "size": 10,
                },
                {
                    "name": "Naga.Agent.Setup.5.1.3.exe",
                    "browser_download_url": "https://example.test/app.exe",
                    "size": 1024,
                },
            ],
        }

        payload = system_routes._github_release_to_update_payload(release, "windows")

        self.assertEqual(payload["version"], "5.1.3")
        self.assertEqual(payload["download_url"], "https://example.test/app.exe")
        self.assertEqual(payload["file_size"], 1024)
        self.assertEqual(payload["source"], "github")

    def test_update_route_prefers_github(self) -> None:
        github_payload = {"version": "5.1.3", "source": "github"}
        github_fetch = AsyncMock(return_value=github_payload)
        business_fetch = AsyncMock(return_value={"version": "5.1.0", "source": "business"})

        with (
            patch.object(system_routes, "_fetch_github_latest_update", github_fetch),
            patch.object(system_routes, "_fetch_business_latest_update", business_fetch),
        ):
            result = asyncio.run(system_routes.proxy_update_check("windows"))

        self.assertEqual(result, github_payload)
        business_fetch.assert_not_awaited()

    def test_update_route_falls_back_to_business(self) -> None:
        business_payload = {"version": "5.1.0", "source": "business"}
        github_fetch = AsyncMock(side_effect=RuntimeError("GitHub unavailable"))
        business_fetch = AsyncMock(return_value=business_payload)

        with (
            patch.object(system_routes, "_fetch_github_latest_update", github_fetch),
            patch.object(system_routes, "_fetch_business_latest_update", business_fetch),
        ):
            result = asyncio.run(system_routes.proxy_update_check("windows"))

        self.assertEqual(result, business_payload)
        business_fetch.assert_awaited_once()

    def test_update_route_reports_failure_when_all_sources_fail(self) -> None:
        with (
            patch.object(
                system_routes,
                "_fetch_github_latest_update",
                AsyncMock(side_effect=RuntimeError("GitHub unavailable")),
            ),
            patch.object(
                system_routes,
                "_fetch_business_latest_update",
                AsyncMock(side_effect=RuntimeError("Business unavailable")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(system_routes.proxy_update_check("windows"))

        self.assertEqual(raised.exception.status_code, 502)


class TtsAudioFormatTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeTtsAsyncClient.requests = []
        _FakeTtsAsyncClient.responses = []

    def test_mp3_frame_without_id3_is_not_wrapped_as_pcm(self) -> None:
        audio_data = b"\xff\xfb\x90\x64" + b"mp3-data"

        normalized, content_type = _ensure_wav_header(audio_data)

        self.assertEqual(normalized, audio_data)
        self.assertEqual(content_type, "audio/mpeg")

    def test_declared_mp3_content_type_is_preserved(self) -> None:
        audio_data = b"mock-mp3-without-magic"

        normalized, content_type = _ensure_wav_header(audio_data, "audio/mpeg; charset=binary")

        self.assertEqual(normalized, audio_data)
        self.assertEqual(content_type, "audio/mpeg")

    def test_raw_pcm_is_wrapped_as_wav(self) -> None:
        raw_pcm = b"\x00\x01\x02\x03" * 10

        normalized, content_type = _ensure_wav_header(raw_pcm, "application/octet-stream")

        self.assertTrue(normalized.startswith(b"RIFF"))
        self.assertEqual(normalized[8:12], b"WAVE")
        self.assertEqual(normalized[44:], raw_pcm)
        self.assertEqual(content_type, "audio/wav")

    def test_gateway_proxy_uses_active_character_voice(self) -> None:
        request = _build_json_request({"input": "你好", "voice": "Cherry", "response_format": "mp3"})

        with (
            patch.object(auth_routes, "get_config", return_value=_LocalTtsConfig()),
            patch.object(auth_routes, "get_character_voice", return_value="Nadezhda"),
            patch.object(auth_routes.naga_auth, "should_use_model_gateway", return_value=True),
            patch.object(auth_routes.naga_auth, "get_access_token", return_value="access-token"),
            patch.object(auth_routes.httpx, "AsyncClient", _FakeTtsAsyncClient),
        ):
            response = asyncio.run(auth_routes.tts_speech_proxy(request))

        sent = _FakeTtsAsyncClient.requests[0]
        self.assertEqual(sent["json"]["voice"], "Nadezhda")
        self.assertEqual(sent["json"]["model"], "default")
        self.assertEqual(sent["headers"]["Authorization"], "Bearer access-token")
        self.assertEqual(response.media_type, "audio/mpeg")

    def test_local_proxy_uses_config_defaults_and_api_key(self) -> None:
        request = _build_json_request({"input": "你好"})

        with (
            patch.object(auth_routes, "get_config", return_value=_LocalTtsConfig()),
            patch.object(auth_routes.naga_auth, "should_use_model_gateway", return_value=False),
            patch.object(auth_routes.httpx, "AsyncClient", _FakeTtsAsyncClient),
        ):
            asyncio.run(auth_routes.tts_speech_proxy(request))

        sent = _FakeTtsAsyncClient.requests[0]
        self.assertEqual(sent["url"], "http://127.0.0.1:5048/v1/audio/speech")
        self.assertEqual(sent["json"]["voice"], "zh-CN-XiaoxiaoNeural")
        self.assertEqual(sent["json"]["response_format"], "mp3")
        self.assertEqual(sent["json"]["speed"], 1.0)
        self.assertEqual(sent["headers"]["Authorization"], "Bearer local-tts-key")

    def test_gateway_proxy_refreshes_expired_token_and_returns_new_token(self) -> None:
        request = _build_json_request({"input": "你好", "response_format": "mp3"})
        _FakeTtsAsyncClient.responses = [_FakeTtsResponse(401), _FakeTtsResponse(200)]
        refresh = AsyncMock(return_value={"access_token": "new-token"})

        with (
            patch.object(auth_routes, "get_config", return_value=_LocalTtsConfig()),
            patch.object(auth_routes, "get_character_voice", return_value="Nadezhda"),
            patch.object(auth_routes.naga_auth, "should_use_model_gateway", return_value=True),
            patch.object(auth_routes.naga_auth, "has_refresh_token", return_value=True),
            patch.object(auth_routes.naga_auth, "get_access_token", side_effect=["old-token", "new-token"]),
            patch.object(auth_routes.naga_auth, "refresh", refresh),
            patch.object(auth_routes.httpx, "AsyncClient", _FakeTtsAsyncClient),
        ):
            response = asyncio.run(auth_routes.tts_speech_proxy(request))

        self.assertEqual(len(_FakeTtsAsyncClient.requests), 2)
        self.assertEqual(_FakeTtsAsyncClient.requests[0]["headers"]["Authorization"], "Bearer old-token")
        self.assertEqual(_FakeTtsAsyncClient.requests[1]["headers"]["Authorization"], "Bearer new-token")
        self.assertEqual(response.headers["x-naga-access-token"], "new-token")
        self.assertEqual(response.headers["access-control-expose-headers"], "X-Naga-Access-Token")
        refresh.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
