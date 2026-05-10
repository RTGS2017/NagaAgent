"""OpenAI-compatible proxy for OpenClaw."""

from __future__ import annotations

import json
import logging
import time
from json import JSONDecodeError
from typing import Any, Dict, Iterable, List, Tuple
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apiserver import naga_auth

router = APIRouter()
logger = logging.getLogger(__name__)

NAGABUSINESS_URL = "http://62.234.131.204:30031/v1/chat/completions"


_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
_DEFAULT_API_KEY = "your-api-key-here"


def _is_user_configured_api() -> bool:
    """判断用户是否真正配置了自己的 API（非默认占位值）。"""
    try:
        from system.config import config as naga_config
        user_base = (getattr(naga_config.api, "base_url", "") or "").strip().rstrip("/")
        api_key = (getattr(naga_config.api, "api_key", "") or "").strip()
        if not user_base:
            return False
        if user_base == _DEFAULT_BASE_URL and (not api_key or api_key == _DEFAULT_API_KEY):
            return False
        return True
    except Exception:
        return False


def _get_upstream_url() -> str:
    """返回上游 URL：用户配置了就使用用户配置，否则走 NagaBusiness。"""
    try:
        from system.config import config as naga_config
        user_base = (getattr(naga_config.api, "base_url", "") or "").strip().rstrip("/")
        if user_base:
            if not _is_user_configured_api():
                return NAGABUSINESS_URL
            return f"{user_base}/chat/completions"
    except Exception:
        pass
    return NAGABUSINESS_URL

_TOOL_SECTION_BEGIN = "<|tool_calls_section_begin|>"
_TOOL_SECTION_END = "<|tool_calls_section_end|>"
_TOOL_CALL_BEGIN = "<|tool_call_begin|>functions."
_TOOL_CALL_ARG_BEGIN = "<|tool_call_argument_begin|>"
_TOOL_CALL_END = "<|tool_call_end|>"
_STREAM_HOLDBACK_CHARS = 48
_LAST_AUTH_INTERRUPT_AT = 0.0
_AUTH_INTERRUPT_DEBOUNCE_SECONDS = 5.0


async def _upstream_headers() -> Dict[str, str]:
    """返回上游请求头：用户配置了 API 则使用用户配置，否则用 NagaBusiness token。"""
    if _is_user_configured_api():
        try:
            from system.config import config as naga_config
            api_key = getattr(naga_config.api, "api_key", "") or ""
            if api_key:
                return {
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json, text/event-stream",
                }
        except Exception:
            pass
        return {"Accept": "application/json, text/event-stream"}

    token = naga_auth.get_access_token()
    if not token and naga_auth.has_refresh_token():
        try:
            await naga_auth.ensure_access_token()
        except Exception as exc:
            logger.error("openai_proxy ensure_access_token failed: %s", exc)
            await _interrupt_open_travel_sessions_for_auth_expired()
            raise HTTPException(status_code=401, detail="当前登录已失效，请重新登录") from exc
        token = naga_auth.get_access_token()

    if not token:
        await _interrupt_open_travel_sessions_for_auth_expired()
        raise HTTPException(status_code=401, detail="缺少当前登录态，无法调用模型服务")

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }


def _json_error(status_code: int, message: str, error_type: str = "upstream_error") -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type}},
    )


async def _interrupt_open_travel_sessions_for_auth_expired() -> None:
    """登录态过期时，将所有未完成探索挂起并通知 agent_server 取消协程。"""
    global _LAST_AUTH_INTERRUPT_AT
    now = time.monotonic()
    if now - _LAST_AUTH_INTERRUPT_AT < _AUTH_INTERRUPT_DEBOUNCE_SECONDS:
        return
    _LAST_AUTH_INTERRUPT_AT = now

    try:
        from apiserver.travel_service import interrupt_open_sessions
        from system.config import get_server_port

        interrupted_sessions = interrupt_open_sessions(reason="auth_expired")
        interrupted_session_ids = [session.session_id for session in interrupted_sessions]
        if not interrupted_session_ids:
            return

        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            await client.post(
                f"http://127.0.0.1:{get_server_port('agent_server')}/travel/interrupt",
                json={"reason": "auth_expired", "session_ids": interrupted_session_ids},
            )
        logger.warning(
            "openai_proxy auth expired -> interrupted %s travel sessions",
            len(interrupted_session_ids),
        )
    except Exception as exc:
        logger.warning("openai_proxy failed to interrupt travel sessions on auth expiry: %s", exc)


async def _refresh_upstream_token() -> str | None:
    if not naga_auth.has_refresh_token():
        return None
    try:
        refresh_result = await naga_auth.refresh()
    except Exception as exc:
        logger.warning("openai_proxy refresh after 401 failed: %s", exc)
        return None
    return refresh_result.get("access_token") or naga_auth.get_access_token()


async def _post_with_auth_retry(
    client: httpx.AsyncClient,
    *,
    json_body: Dict[str, Any],
    headers: Dict[str, str],
    url: str = "",
) -> httpx.Response:
    upstream_url = url or _get_upstream_url()
    resp = await client.post(upstream_url, json=json_body, headers=headers)
    if upstream_url != NAGABUSINESS_URL:
        return resp
    if resp.status_code != 401 or not naga_auth.is_authenticated():
        return resp

    new_token = await _refresh_upstream_token()
    if new_token:
        retry_headers = {**headers, "Authorization": f"Bearer {new_token}"}
        resp = await client.post(upstream_url, json=json_body, headers=retry_headers)
        if resp.status_code != 401:
            return resp

    await _interrupt_open_travel_sessions_for_auth_expired()
    return resp


async def _stream_with_auth_retry(
    client: httpx.AsyncClient,
    *,
    json_body: Dict[str, Any],
    headers: Dict[str, str],
    url: str = "",
):
    upstream_url = url or _get_upstream_url()
    stream_ctx = client.stream("POST", upstream_url, json=json_body, headers=headers)
    resp = await stream_ctx.__aenter__()
    if upstream_url != NAGABUSINESS_URL:
        return resp, stream_ctx
    if resp.status_code != 401 or not naga_auth.is_authenticated():
        return resp, stream_ctx

    text = await resp.aread()
    await stream_ctx.__aexit__(None, None, None)
    logger.info(
        "openai_proxy received 401 from upstream stream, attempting token refresh and retry: %r",
        text.decode("utf-8", errors="replace")[:300],
    )

    new_token = await _refresh_upstream_token()
    if new_token:
        retry_headers = {**headers, "Authorization": f"Bearer {new_token}"}
        retry_ctx = client.stream("POST", upstream_url, json=json_body, headers=retry_headers)
        retry_resp = await retry_ctx.__aenter__()
        if retry_resp.status_code != 401:
            return retry_resp, retry_ctx
        await _interrupt_open_travel_sessions_for_auth_expired()
        return retry_resp, retry_ctx

    await _interrupt_open_travel_sessions_for_auth_expired()
    retry_ctx = client.stream("POST", upstream_url, json=json_body, headers=headers)
    retry_resp = await retry_ctx.__aenter__()
    return retry_resp, retry_ctx


def _extract_message_payload(payload: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", [], None

    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        content = ""

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        tool_calls = []

    finish_reason = choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        finish_reason = str(finish_reason)

    return content, tool_calls, finish_reason


def _extract_stream_payload(events: Iterable[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]], str | None]:
    parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    finish_reason: str | None = None

    for payload in events:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        if isinstance(delta.get("content"), str):
            parts.append(delta["content"])
        delta_tool_calls = delta.get("tool_calls")
        if isinstance(delta_tool_calls, list) and delta_tool_calls:
            tool_calls = delta_tool_calls
        if isinstance(choice.get("finish_reason"), str):
            finish_reason = choice["finish_reason"]

    return "".join(parts), tool_calls, finish_reason


def _extract_special_tool_calls(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    if _TOOL_CALL_BEGIN not in text:
        return text, []

    decoder = json.JSONDecoder()
    tool_calls: List[Dict[str, Any]] = []
    clean_parts: List[str] = []
    cursor = 0

    while True:
        start = text.find(_TOOL_CALL_BEGIN, cursor)
        if start < 0:
            clean_parts.append(text[cursor:])
            break

        section_start = text.rfind(_TOOL_SECTION_BEGIN, cursor, start)
        clean_parts.append(text[cursor:section_start if section_start >= 0 else start])

        name_start = start + len(_TOOL_CALL_BEGIN)
        colon = text.find(":", name_start)
        arg_start = text.find(_TOOL_CALL_ARG_BEGIN, colon if colon >= 0 else name_start)
        if colon < 0 or arg_start < 0:
            clean_parts.append(text[start:])
            break

        tool_name = text[name_start:colon].strip()
        json_start = arg_start + len(_TOOL_CALL_ARG_BEGIN)

        try:
            arguments, consumed = decoder.raw_decode(text[json_start:])
        except JSONDecodeError:
            logger.warning("openai_proxy: 无法解析上游特殊工具调用 JSON，保留原始文本")
            clean_parts.append(text[start:])
            break

        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        tool_calls.append(
            {
                "id": f"call_{uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )

        end = text.find(_TOOL_CALL_END, json_start + consumed)
        if end < 0:
            cursor = json_start + consumed
        else:
            cursor = end + len(_TOOL_CALL_END)
            if text.startswith(_TOOL_SECTION_END, cursor):
                cursor += len(_TOOL_SECTION_END)

    clean_text = "".join(clean_parts).strip()
    return clean_text, tool_calls


def _extract_special_tool_calls_with_state(text: str) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Like _extract_special_tool_calls, but reports whether the payload is incomplete."""
    if _TOOL_CALL_BEGIN not in text:
        partial_markers = (
            _TOOL_SECTION_BEGIN,
            _TOOL_CALL_BEGIN,
            _TOOL_CALL_ARG_BEGIN,
            _TOOL_CALL_END,
            _TOOL_SECTION_END,
        )
        incomplete = any(marker.startswith(text) for marker in partial_markers if text)
        return text, [], incomplete

    decoder = json.JSONDecoder()
    tool_calls: List[Dict[str, Any]] = []
    clean_parts: List[str] = []
    cursor = 0

    while True:
        start = text.find(_TOOL_CALL_BEGIN, cursor)
        if start < 0:
            clean_parts.append(text[cursor:])
            break

        section_start = text.rfind(_TOOL_SECTION_BEGIN, cursor, start)
        clean_parts.append(text[cursor:section_start if section_start >= 0 else start])

        name_start = start + len(_TOOL_CALL_BEGIN)
        colon = text.find(":", name_start)
        arg_start = text.find(_TOOL_CALL_ARG_BEGIN, colon if colon >= 0 else name_start)
        if colon < 0 or arg_start < 0:
            return text, [], True

        tool_name = text[name_start:colon].strip()
        json_start = arg_start + len(_TOOL_CALL_ARG_BEGIN)

        try:
            arguments, consumed = decoder.raw_decode(text[json_start:])
        except JSONDecodeError:
            return text, [], True

        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        tool_calls.append(
            {
                "id": f"call_{uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )

        end = text.find(_TOOL_CALL_END, json_start + consumed)
        if end < 0:
            return text, [], True

        cursor = end + len(_TOOL_CALL_END)
        if text.startswith(_TOOL_SECTION_END, cursor):
            cursor += len(_TOOL_SECTION_END)

    clean_text = "".join(clean_parts).strip()
    return clean_text, tool_calls, False


def _iter_message_text_fragments(messages: Any) -> Iterable[str]:
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            yield content
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                yield text


def _looks_like_travel_request(body: Dict[str, Any]) -> bool:
    for text in _iter_message_text_fragments(body.get("messages")):
        if "NagaTravel" in text:
            return True
        if "长期网络探索任务" in text:
            return True
        if "请停止扩展探索，开始收束并输出最终旅行报告" in text:
            return True
    return False


async def _stream_normalized_non_stream_response(body: Dict[str, Any]):
    upstream_body = dict(body)
    upstream_body["stream"] = False
    payload = await _fetch_upstream_json(upstream_body)
    normalized = _normalize_non_stream_response(payload, upstream_body)
    model = normalized.get("model") or body.get("model") or "naga-proxy"
    run_id = normalized.get("id") or f"chatcmpl-{uuid4().hex}"
    content, tool_calls, _finish_reason = _extract_message_payload(normalized)
    for chunk in _iter_normalized_stream(
        content=content,
        tool_calls=tool_calls,
        model=str(model),
        run_id=str(run_id),
    ):
        yield chunk


async def _stream_buffered_with_fallback(body: Dict[str, Any]):
    events, model, run_id = await _fetch_upstream_stream_events(body)
    content, tool_calls, finish_reason = _extract_stream_payload(events)
    clean_text, special_tool_calls = _extract_special_tool_calls(content)
    normalized_tool_calls = tool_calls or special_tool_calls

    has_meaningful_stream = bool(events) and (
        bool(clean_text.strip())
        or bool(normalized_tool_calls)
        or bool(finish_reason)
    )

    if not has_meaningful_stream:
        logger.info("openai_proxy: upstream stream returned no usable content, falling back to non-stream normalization")
        async for chunk in _stream_normalized_non_stream_response(body):
            yield chunk
        return

    for chunk in _iter_normalized_stream(
        content=clean_text,
        tool_calls=normalized_tool_calls,
        model=str(model),
        run_id=str(run_id),
    ):
        yield chunk


def _normalize_non_stream_response(payload: Dict[str, Any], request_body: Dict[str, Any]) -> Dict[str, Any]:
    content, tool_calls, finish_reason = _extract_message_payload(payload)
    clean_text, special_tool_calls = _extract_special_tool_calls(content)

    if tool_calls:
        if special_tool_calls:
            logger.warning("openai_proxy: 上游同时返回标准 tool_calls 和特殊工具语法，优先使用标准 tool_calls")
        return payload

    if not special_tool_calls:
        return payload

    model = payload.get("model") or request_body.get("model") or "naga-proxy"
    choice: Dict[str, Any] = {
        "index": 0,
        "message": {
            "role": "assistant",
            "content": clean_text or "",
            "tool_calls": special_tool_calls,
        },
        "finish_reason": "tool_calls",
    }
    if isinstance(payload.get("choices"), list) and payload["choices"]:
        original_choice = payload["choices"][0] or {}
        if isinstance(original_choice.get("logprobs"), dict) or original_choice.get("logprobs") is None:
            choice["logprobs"] = original_choice.get("logprobs")

    return {
        "id": payload.get("id") or f"chatcmpl-{uuid4().hex}",
        "object": payload.get("object") or "chat.completion",
        "created": payload.get("created") or 0,
        "model": model,
        "choices": [choice],
        "usage": payload.get("usage"),
    }


def _iter_normalized_stream(
    *,
    content: str,
    tool_calls: List[Dict[str, Any]],
    model: str,
    run_id: str,
) -> Iterable[bytes]:
    created = 0

    def _chunk(choice: Dict[str, Any]) -> bytes:
        data = {
            "id": run_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [choice],
        }
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")

    yield _chunk({"index": 0, "delta": {"role": "assistant"}, "finish_reason": None})

    if content:
        yield _chunk({"index": 0, "delta": {"content": content}, "finish_reason": None})

    if tool_calls:
        for idx, tool_call in enumerate(tool_calls):
            function = tool_call.get("function") or {}
            yield _chunk(
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": idx,
                                "id": tool_call.get("id") or f"call_{uuid4().hex[:12]}",
                                "type": "function",
                                "function": {
                                    "name": function.get("name", ""),
                                    "arguments": function.get("arguments", "{}"),
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            )
        yield _chunk({"index": 0, "delta": {}, "finish_reason": "tool_calls"})
    else:
        yield _chunk({"index": 0, "delta": {}, "finish_reason": "stop"})

    yield b"data: [DONE]\n\n"


def _make_stream_chunk(
    *,
    choice: Dict[str, Any],
    model: str,
    run_id: str,
    created: int = 0,
) -> bytes:
    data = {
        "id": run_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [choice],
    }
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


async def _fetch_upstream_json(body: Dict[str, Any]) -> Dict[str, Any]:
    headers = await _upstream_headers()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await _post_with_auth_retry(client, json_body=body, headers=headers)

    if resp.status_code >= 400:
        snippet = (resp.text or "")[:500]
        logger.error("openai_proxy upstream error: status=%s body=%r", resp.status_code, snippet)
        raise HTTPException(status_code=resp.status_code, detail=snippet or "上游服务错误")

    try:
        return resp.json()
    except ValueError as exc:
        snippet = (resp.text or "")[:500]
        logger.error("openai_proxy upstream returned non-JSON: %s body=%r", exc, snippet)
        raise HTTPException(status_code=502, detail="上游返回了非 JSON 响应")


async def _fetch_upstream_stream_events(body: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, str]:
    events: List[Dict[str, Any]] = []
    model = body.get("model") or "naga-proxy"
    run_id = f"chatcmpl-{uuid4().hex}"
    headers = await _upstream_headers()

    async with httpx.AsyncClient(timeout=120) as client:
        resp, stream_ctx = await _stream_with_auth_retry(client, json_body=body, headers=headers)
        try:
            if resp.status_code >= 400:
                text = await resp.aread()
                snippet = text.decode("utf-8", errors="replace")[:500]
                logger.error("openai_proxy upstream stream error: status=%s body=%r", resp.status_code, snippet)
                raise HTTPException(status_code=resp.status_code, detail=snippet or "上游流式服务错误")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    payload = json.loads(data_str)
                except ValueError:
                    logger.warning("openai_proxy ignored invalid SSE payload: %r", data_str[:200])
                    continue
                events.append(payload)
                if isinstance(payload.get("model"), str) and payload["model"]:
                    model = payload["model"]
                if isinstance(payload.get("id"), str) and payload["id"]:
                    run_id = payload["id"]
        finally:
            await stream_ctx.__aexit__(None, None, None)

    return events, model, run_id


async def _stream_upstream_with_normalization(body: Dict[str, Any]):
    model = body.get("model") or "naga-proxy"
    run_id = f"chatcmpl-{uuid4().hex}"
    role_sent = False
    holdback = ""
    special_mode = False
    special_buffer = ""
    special_tool_calls: List[Dict[str, Any]] = []
    finished = False
    headers = await _upstream_headers()

    async with httpx.AsyncClient(timeout=120) as client:
        resp, stream_ctx = await _stream_with_auth_retry(client, json_body=body, headers=headers)
        try:
            if resp.status_code >= 400:
                text = await resp.aread()
                snippet = text.decode("utf-8", errors="replace")[:500]
                logger.error("openai_proxy upstream stream error: status=%s body=%r", resp.status_code, snippet)
                raise HTTPException(status_code=resp.status_code, detail=snippet or "上游流式服务错误")

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    break

                try:
                    payload = json.loads(data_str)
                except ValueError:
                    logger.warning("openai_proxy ignored invalid SSE payload: %r", data_str[:200])
                    continue

                if isinstance(payload.get("model"), str) and payload["model"]:
                    model = payload["model"]
                if isinstance(payload.get("id"), str) and payload["id"]:
                    run_id = payload["id"]

                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] or {}
                delta = choice.get("delta") or {}
                finish_reason = choice.get("finish_reason")
                delta_content = delta.get("content") if isinstance(delta.get("content"), str) else ""
                delta_tool_calls = delta.get("tool_calls") if isinstance(delta.get("tool_calls"), list) else []

                if not role_sent:
                    role_sent = True
                    yield _make_stream_chunk(
                        choice={"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
                        model=model,
                        run_id=run_id,
                    )

                if special_mode:
                    if delta_content:
                        special_buffer += delta_content
                    if delta_tool_calls:
                        special_tool_calls = delta_tool_calls
                    if isinstance(finish_reason, str):
                        clean_text, extracted_tool_calls = _extract_special_tool_calls(special_buffer)
                        normalized_tool_calls = special_tool_calls or extracted_tool_calls
                        if clean_text:
                            yield _make_stream_chunk(
                                choice={"index": 0, "delta": {"content": clean_text}, "finish_reason": None},
                                model=model,
                                run_id=run_id,
                            )
                        if normalized_tool_calls:
                            for idx, tool_call in enumerate(normalized_tool_calls):
                                function = tool_call.get("function") or {}
                                yield _make_stream_chunk(
                                    choice={
                                        "index": 0,
                                        "delta": {
                                            "tool_calls": [
                                                {
                                                    "index": idx,
                                                    "id": tool_call.get("id") or f"call_{uuid4().hex[:12]}",
                                                    "type": "function",
                                                    "function": {
                                                        "name": function.get("name", ""),
                                                        "arguments": function.get("arguments", "{}"),
                                                    },
                                                }
                                            ]
                                        },
                                        "finish_reason": None,
                                    },
                                    model=model,
                                    run_id=run_id,
                                )
                            yield _make_stream_chunk(
                                choice={"index": 0, "delta": {}, "finish_reason": "tool_calls"},
                                model=model,
                                run_id=run_id,
                            )
                        else:
                            yield _make_stream_chunk(
                                choice={"index": 0, "delta": {}, "finish_reason": "stop"},
                                model=model,
                                run_id=run_id,
                            )
                        finished = True
                        break
                    continue

                if delta_tool_calls:
                    if holdback:
                        yield _make_stream_chunk(
                            choice={"index": 0, "delta": {"content": holdback}, "finish_reason": None},
                            model=model,
                            run_id=run_id,
                        )
                        holdback = ""
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
                    if isinstance(finish_reason, str):
                        finished = True
                    continue

                if delta_content:
                    candidate = holdback + delta_content
                    clean_text, extracted_tool_calls, incomplete = _extract_special_tool_calls_with_state(
                        candidate
                    )
                    if extracted_tool_calls:
                        special_mode = True
                        special_buffer = candidate
                        special_tool_calls = extracted_tool_calls
                        continue
                    if incomplete:
                        if len(candidate) > 4096 and _TOOL_CALL_BEGIN not in candidate:
                            emit_text = candidate[:-_STREAM_HOLDBACK_CHARS]
                            holdback = candidate[-_STREAM_HOLDBACK_CHARS:]
                            if emit_text:
                                yield _make_stream_chunk(
                                    choice={"index": 0, "delta": {"content": emit_text}, "finish_reason": None},
                                    model=model,
                                    run_id=run_id,
                                )
                            continue
                        holdback = candidate
                        continue

                    if len(clean_text) > _STREAM_HOLDBACK_CHARS:
                        emit_text = clean_text[:-_STREAM_HOLDBACK_CHARS]
                        holdback = clean_text[-_STREAM_HOLDBACK_CHARS:]
                        if emit_text:
                            yield _make_stream_chunk(
                                choice={"index": 0, "delta": {"content": emit_text}, "finish_reason": None},
                                model=model,
                                run_id=run_id,
                            )
                    else:
                        holdback = clean_text

                if isinstance(finish_reason, str):
                    if holdback:
                        yield _make_stream_chunk(
                            choice={"index": 0, "delta": {"content": holdback}, "finish_reason": None},
                            model=model,
                            run_id=run_id,
                        )
                        holdback = ""
                    yield _make_stream_chunk(
                        choice={"index": 0, "delta": {}, "finish_reason": finish_reason},
                        model=model,
                        run_id=run_id,
                    )
                    finished = True
                    break
        finally:
            await stream_ctx.__aexit__(None, None, None)

    if not role_sent:
        yield _make_stream_chunk(
            choice={"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
            model=model,
            run_id=run_id,
        )

    if not finished:
        if special_mode:
            clean_text, extracted_tool_calls = _extract_special_tool_calls(special_buffer)
            normalized_tool_calls = special_tool_calls or extracted_tool_calls
            if clean_text:
                yield _make_stream_chunk(
                    choice={"index": 0, "delta": {"content": clean_text}, "finish_reason": None},
                    model=model,
                    run_id=run_id,
                )
            if normalized_tool_calls:
                for idx, tool_call in enumerate(normalized_tool_calls):
                    function = tool_call.get("function") or {}
                    yield _make_stream_chunk(
                        choice={
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": idx,
                                        "id": tool_call.get("id") or f"call_{uuid4().hex[:12]}",
                                        "type": "function",
                                        "function": {
                                            "name": function.get("name", ""),
                                            "arguments": function.get("arguments", "{}"),
                                        },
                                    }
                                ]
                            },
                            "finish_reason": None,
                        },
                        model=model,
                        run_id=run_id,
                    )
                yield _make_stream_chunk(
                    choice={"index": 0, "delta": {}, "finish_reason": "tool_calls"},
                    model=model,
                    run_id=run_id,
                )
            else:
                yield _make_stream_chunk(
                    choice={"index": 0, "delta": {}, "finish_reason": "stop"},
                    model=model,
                    run_id=run_id,
                )
        else:
            if holdback:
                yield _make_stream_chunk(
                    choice={"index": 0, "delta": {"content": holdback}, "finish_reason": None},
                    model=model,
                    run_id=run_id,
                )
            yield _make_stream_chunk(
                choice={"index": 0, "delta": {}, "finish_reason": "stop"},
                model=model,
                run_id=run_id,
            )

    yield b"data: [DONE]\n\n"


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Normalize upstream responses so OpenClaw always receives standard OpenAI tool-calls."""
    body = await request.json()

    if body.get("stream"):
        if _looks_like_travel_request(body):
            logger.info("openai_proxy: detected NagaTravel request, forcing non-stream upstream fallback")
            return StreamingResponse(
                _stream_normalized_non_stream_response(body),
                media_type="text/event-stream",
            )
        return StreamingResponse(
            _stream_buffered_with_fallback(body),
            media_type="text/event-stream",
        )

    payload = await _fetch_upstream_json(body)
    normalized = _normalize_non_stream_response(payload, body)
    return JSONResponse(content=normalized)
