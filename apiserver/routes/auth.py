"""NagaCAS 认证 + TTS/ASR 代理路由"""

import logging
import struct

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, JSONResponse

from apiserver import naga_auth
from apiserver.telemetry import emit_telemetry
from system.config import get_character_voice, get_config
from system.config_manager import update_config

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ NagaCAS 认证端点 ============


@router.post("/auth/login")
async def auth_login(body: dict):
    """NagaCAS 登录"""
    username = body.get("username", "")
    password = body.get("password", "")
    captcha_id = body.get("captcha_id", "")
    captcha_answer = body.get("captcha_answer", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    try:
        result = await naga_auth.login(username, password, captcha_id, captcha_answer)
        emit_telemetry(
            "login_success",
            {
                "username_length": len(username),
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        return result
    except Exception as e:
        import httpx
        status = 401
        detail = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
        logger.error(f"登录失败 [{status}]: {detail}")
        emit_telemetry(
            "login_fail",
            {
                "status_code": status,
                "error": detail,
                "username_length": len(username),
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        raise HTTPException(status_code=status, detail=detail)


@router.get("/auth/me")
async def auth_me(request: Request):
    """获取当前用户信息（优先使用服务端 token，其次从请求头恢复）"""
    token = naga_auth.get_access_token()
    if not token:
        # 尝试从 Authorization 头恢复会话
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    user = await naga_auth.get_me(token)
    if not user:
        raise HTTPException(status_code=401, detail="token 已失效")
    # 恢复服务端认证状态
    naga_auth.restore_token(token)
    # 返回后端实际使用的 token，供前端同步
    # （后端 ensure_access_token 启动时可能已刷新，前端持有的旧 token 已过期但请求走了后端 token 未触发 401）
    return {"user": user, "memory_url": naga_auth.NAGA_MEMORY_URL, "access_token": token}


@router.post("/auth/logout")
async def auth_logout():
    """登出"""
    interrupted_session_ids: list[str] = []
    try:
        from apiserver.travel_service import interrupt_open_sessions

        interrupted_sessions = interrupt_open_sessions(reason="logout")
        interrupted_session_ids = [session.session_id for session in interrupted_sessions]
    except Exception as e:
        logger.warning(f"logout 时标记探索中断失败（可忽略）: {e}")

    if interrupted_session_ids:
        try:
            import httpx
            from system.config import get_server_port

            port = get_server_port("agent_server")
            async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
                await client.post(
                    f"http://127.0.0.1:{port}/travel/interrupt",
                    json={"reason": "logout", "session_ids": interrupted_session_ids},
                )
        except Exception as e:
            logger.warning(f"logout 时通知 agent_server 中断探索失败（可忽略）: {e}")
    naga_auth.logout()
    return {"success": True, "interrupted_sessions": interrupted_session_ids}


@router.post("/auth/register")
async def auth_register(body: dict):
    """NagaBusiness 注册"""
    username = body.get("username", "")
    email = body.get("email", "")
    password = body.get("password", "")
    verification_code = body.get("verification_code", "")
    if not username or not email or not password or not verification_code:
        raise HTTPException(status_code=400, detail="用户名、邮箱、密码和验证码不能为空")
    try:
        result = await naga_auth.register(username, email, password, verification_code)
        emit_telemetry(
            "register_success",
            {
                "username_length": len(username),
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
            },
            source="apiserver",
        )
        return {"success": True, **result}
    except Exception as e:
        import httpx
        status = 500
        detail = f"注册失败: {str(e)}"
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
        logger.error(f"注册失败 [{status}]: {detail}")
        emit_telemetry(
            "register_fail",
            {
                "status_code": status,
                "error": detail,
                "username_length": len(username),
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
            },
            source="apiserver",
        )
        raise HTTPException(status_code=status, detail=detail)


@router.get("/auth/captcha")
async def auth_captcha(format: str = ""):
    """获取验证码（图像优先，兼容旧版算术题）"""
    try:
        result = await naga_auth.get_captcha(format)
        return result
    except Exception as e:
        logger.error(f"获取验证码失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取验证码失败: {str(e)}")


@router.post("/auth/send-verification")
async def auth_send_verification(body: dict):
    """发送邮箱验证码"""
    email = body.get("email", "")
    username = body.get("username", "")
    captcha_id = body.get("captcha_id", "")
    captcha_answer = body.get("captcha_answer", "")
    if not email or not username:
        raise HTTPException(status_code=400, detail="邮箱和用户名不能为空")
    try:
        await naga_auth.send_verification(email, username, captcha_id, captcha_answer)
        emit_telemetry(
            "register_verification_sent",
            {
                "username_length": len(username),
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        return {"success": True, "message": "验证码已发送"}
    except Exception as e:
        import httpx
        status = 500
        detail = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
        logger.error(f"发送验证码失败 [{status}]: {detail}")
        emit_telemetry(
            "register_verification_fail",
            {
                "status_code": status,
                "error": detail,
                "username_length": len(username),
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        raise HTTPException(status_code=status, detail=detail)


@router.post("/auth/send-qq-verification")
async def auth_send_qq_verification(body: dict, request: Request):
    """向 QQ 邮箱发送验证码，使用当前登录用户身份。"""
    email = str(body.get("email", "")).strip()
    captcha_id = str(body.get("captcha_id", "")).strip()
    captcha_answer = str(body.get("captcha_answer", "")).strip()
    if not email:
        raise HTTPException(status_code=400, detail="邮箱不能为空")

    token = naga_auth.get_access_token()
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            naga_auth.restore_token(token)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录后再发送 QQ 邮箱验证码")

    user = naga_auth.get_user_info() or await naga_auth.get_me(token)
    if not user:
        raise HTTPException(status_code=401, detail="当前登录态无有效用户，请重新登录后再试")

    try:
        await naga_auth.send_qq_verification(email, token, captcha_id, captcha_answer)
        emit_telemetry(
            "qq_notification_verification_sent",
            {
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
                "username_length": len(str(user.get("username") or "")),
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        return {"success": True, "message": f"验证码已发送到 {email}"}
    except Exception as e:
        import httpx

        status = 500
        detail = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
        logger.error(f"发送 QQ 邮箱验证码失败 [{status}]: {detail}")
        emit_telemetry(
            "qq_notification_verification_fail",
            {
                "status_code": status,
                "error": detail,
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
                "has_captcha": bool(captcha_id),
            },
            source="apiserver",
        )
        raise HTTPException(status_code=status, detail=detail)




@router.post("/auth/qq-email")
async def auth_bind_qq_email(body: dict, request: Request):
    """提交 QQ 邮箱绑定。"""
    email = str(body.get("qq_email", "")).strip()
    verification_code = str(body.get("verification_code", "")).strip()
    if not email:
        raise HTTPException(status_code=400, detail="qq_email 不能为空")
    if not verification_code:
        raise HTTPException(status_code=400, detail="verification_code 不能为空")

    token = naga_auth.get_access_token()
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            naga_auth.restore_token(token)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录后再提交 QQ 邮箱绑定")

    user = naga_auth.get_user_info() or await naga_auth.get_me(token)
    if not user:
        raise HTTPException(status_code=401, detail="当前登录态无有效用户，请重新登录后再试")

    try:
        result = await naga_auth.bind_qq_email(email, verification_code, token)
        update_config({
            "notifications": {
                "qq": {
                    "binding_target": email,
                    "user_qq": email.split("@", 1)[0] if "@qq.com" in email.lower() else "",
                    "qq_email": email,
                    "email_verification_code": "",
                    "binding_verified": True,
                    "binding_verified_email": email,
                },
            },
        })
        emit_telemetry(
            "qq_notification_bound",
            {
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
                "username_length": len(str(user.get("username") or "")),
            },
            source="apiserver",
        )
        return result
    except Exception as e:
        import httpx

        status = 500
        detail = str(e)
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
        logger.error(f"提交 QQ 邮箱绑定失败 [{status}]: {detail}")
        emit_telemetry(
            "qq_notification_bind_fail",
            {
                "status_code": status,
                "error": detail,
                "email_domain": email.split("@", 1)[1] if "@" in email else "",
            },
            source="apiserver",
        )
        raise HTTPException(status_code=status, detail=detail)


@router.get("/auth/qq-email")
async def auth_get_qq_email_binding(request: Request):
    """获取当前账号 QQ 邮箱绑定状态。"""
    token = naga_auth.get_access_token()
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            naga_auth.restore_token(token)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录后再查询 QQ 邮箱绑定")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{naga_auth.BUSINESS_URL}/api/auth/qq-email",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                logger.error(f"NagaBusiness qq-email 查询返回 {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        if isinstance(e, httpx.HTTPStatusError):
            status = e.response.status_code
            try:
                err_data = e.response.json()
                detail = err_data.get("message", e.response.text)
            except Exception:
                detail = e.response.text
            raise HTTPException(status_code=status, detail=detail)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auth/refresh")
async def auth_refresh(request: Request):
    """刷新 token（后端管理 refresh_token，兼容接受 body 中的 refresh_token 用于迁移/非浏览器客户端）"""
    rt_override = None
    try:
        body = await request.json()
        rt_override = body.get("refresh_token") if isinstance(body, dict) else None
    except Exception:
        pass
    try:
        result = await naga_auth.refresh(rt_override)
        return result
    except Exception as e:
        logger.error(f"刷新 token 失败: {e}")
        raise HTTPException(status_code=401, detail=f"刷新失败: {str(e)}")


# ============ TTS 代理（解决前端跨域问题） ============

_GATEWAY_TTS_MODEL = "default"
_GATEWAY_TTS_FALLBACK_VOICE = "Cherry"
_REFRESHED_TOKEN_HEADER = "X-Naga-Access-Token"
_AUDIO_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/flac",
    "audio/mp4",
    "audio/aac",
}


def _ensure_wav_header(audio_data: bytes, declared_content_type: str = "") -> tuple[bytes, str]:
    """检查音频数据是否有有效容器头部，若是 raw PCM 则包装为 WAV 格式（浏览器可播放）"""
    if len(audio_data) < 4:
        return audio_data, "audio/mpeg"

    header = audio_data[:4]
    if header[:3] == b'ID3':                          # MP3 with ID3 tag
        return audio_data, "audio/mpeg"
    if header[0] == 0xFF and header[1] & 0xE0 == 0xE0:  # MP3 frame sync
        return audio_data, "audio/mpeg"
    if header == b'RIFF':                              # WAV
        return audio_data, "audio/wav"
    if header == b'OggS':                              # OGG
        return audio_data, "audio/ogg"
    if header == b'fLaC':                              # FLAC
        return audio_data, "audio/flac"
    if len(audio_data) >= 8 and audio_data[4:8] == b"ftyp":  # MP4/M4A
        return audio_data, "audio/mp4"

    media_type = declared_content_type.split(";", 1)[0].strip().lower()
    if media_type in _AUDIO_CONTENT_TYPES:
        return audio_data, "audio/mpeg" if media_type == "audio/mp3" else media_type

    # 无法识别的格式 → 假定 raw PCM，包装为 WAV (24kHz, 16-bit, mono)
    sample_rate = 24000
    bits_per_sample = 16
    num_channels = 1
    data_size = len(audio_data)
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8

    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size,
    )
    logger.info(f"[TTS] raw PCM detected ({data_size} bytes), wrapped as WAV (24kHz/16bit/mono)")
    return wav_header + audio_data, "audio/wav"


@router.post("/tts/speech")
async def tts_speech_proxy(request: Request) -> Response:
    """代理前端 TTS 请求到 NagaBusiness，避免浏览器 CORS 限制"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict) or not str(body.get("input") or "").strip():
        raise HTTPException(status_code=400, detail="TTS input 不能为空")

    config = get_config()
    use_gateway = naga_auth.should_use_model_gateway()
    refreshed_access_token: str | None = None
    if use_gateway:
        # 已登录 → 代理到 NagaBusiness
        tts_url = naga_auth.NAGA_MODEL_URL + "/audio/speech"
        body["model"] = _GATEWAY_TTS_MODEL
        body["voice"] = get_character_voice() or body.get("voice") or _GATEWAY_TTS_FALLBACK_VOICE
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {naga_auth.get_access_token()}",
        }
    else:
        # 未登录 → 转发到本地 edge-tts
        tts_url = f"http://127.0.0.1:{config.tts.port}/v1/audio/speech"
        body["voice"] = body.get("voice") or config.tts.default_voice
        body["response_format"] = body.get("response_format") or config.tts.default_format
        body["speed"] = body.get("speed") or config.tts.default_speed
        headers = {"Content-Type": "application/json"}
        if config.tts.require_api_key and config.tts.api_key:
            headers["Authorization"] = f"Bearer {config.tts.api_key}"

    try:
        async with httpx.AsyncClient(timeout=30, trust_env=use_gateway) as client:
            resp = await client.post(tts_url, json=body, headers=headers)
            if use_gateway and resp.status_code == 401 and naga_auth.has_refresh_token():
                await naga_auth.refresh()
                refreshed_access_token = naga_auth.get_access_token()
                headers["Authorization"] = f"Bearer {refreshed_access_token}"
                resp = await client.post(tts_url, json=body, headers=headers)
        if resp.status_code != 200:
            logger.error("TTS 代理失败: status=%s url=%s", resp.status_code, tts_url)
            raise HTTPException(status_code=resp.status_code, detail="TTS service error")
        # 检查音频格式，raw PCM 自动包装为 WAV
        audio_data, content_type = _ensure_wav_header(
            resp.content,
            resp.headers.get("content-type", ""),
        )
        response = Response(content=audio_data, media_type=content_type)
        if refreshed_access_token:
            response.headers[_REFRESHED_TOKEN_HEADER] = refreshed_access_token
            response.headers["Access-Control-Expose-Headers"] = _REFRESHED_TOKEN_HEADER
        return response
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="TTS service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS 代理异常: {e}")
        raise HTTPException(status_code=502, detail=f"TTS proxy error: {str(e)}")


@router.post("/asr/transcribe")
async def asr_transcribe_proxy(request: Request):
    """代理前端 ASR 请求到 NagaBusiness /v1/audio/transcriptions"""
    import httpx

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=400, detail="Content-Type must be multipart/form-data")

    # 优先从请求头获取 token，其次使用后端已同步的认证状态
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    if not token and naga_auth.is_authenticated():
        token = naga_auth.get_access_token()
    if not token:
        raise HTTPException(status_code=401, detail="未登录，ASR 服务需要登录后使用")
    upstream_auth = f"Bearer {token}"

    # 解析 multipart 表单
    form = await request.form()
    audio_file = form.get("file")
    if not audio_file:
        raise HTTPException(status_code=400, detail="缺少 file 字段")

    # 构建转发请求
    asr_url = naga_auth.NAGA_MODEL_URL + "/audio/transcriptions"
    files = {"file": (audio_file.filename or "recording.webm", await audio_file.read(), audio_file.content_type or "audio/webm")}
    data = {}
    for key in ("model", "language", "prompt", "response_format", "temperature"):
        val = form.get(key)
        if val is not None:
            data[key] = val
    if "model" not in data:
        data["model"] = "default"
    if "language" not in data:
        data["language"] = "zh"

    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            resp = await client.post(asr_url, files=files, data=data, headers={"Authorization": upstream_auth})
        if resp.status_code != 200:
            detail = resp.text[:200] if resp.text else "ASR service error"
            logger.error(f"ASR 代理失败: {resp.status_code} url={asr_url} detail={detail}")
            raise HTTPException(status_code=resp.status_code, detail=detail)
        return JSONResponse(content=resp.json())
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="ASR service timeout")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR 代理异常: {e}")
        raise HTTPException(status_code=502, detail=f"ASR proxy error: {str(e)}")
