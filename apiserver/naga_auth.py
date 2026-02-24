"""
NagaBusiness 认证模块
对接 NagaBusiness 统一网关，管理用户登录态
采用双 Token 架构：access_token (30min) + refresh_token (7天)
refresh_token 由后端全权管理，前端仅持有 access_token
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# NagaBusiness 统一网关地址（对外唯一暴露的服务）
BUSINESS_URL = "http://62.234.131.204:30031"
# 兼容旧代码，LLM 调用也走 NagaBusiness（需含 /v1 前缀供 LiteLLM 拼接 /chat/completions）
NAGA_MODEL_URL = BUSINESS_URL + "/v1"
# NagaMemory 远程记忆服务地址（NebulaGraph 后端）
NAGA_MEMORY_URL = f"{BUSINESS_URL}/api/memory"

# refresh_token 持久化文件（7 天有效，需跨进程重启保留）
_TOKEN_FILE = Path(__file__).parent.parent / "logs" / ".auth_session"

# 模块级认证状态（单用户场景）
_access_token: Optional[str] = None
_refresh_token: Optional[str] = None
_user_info: Optional[dict] = None
_refresh_lock = asyncio.Lock()
_last_refresh_at: float = 0.0          # 上次 refresh 成功的 monotonic 时间戳
_REFRESH_GRACE_PERIOD: float = 10.0    # 刷新后的保护窗口（秒），防止旧 token 覆盖


# ── refresh_token 持久化 ─────────────────────────

def _save_refresh_token():
    """将 refresh_token 持久化到文件，供 App 重启后恢复 7 天登录态"""
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps({"refresh_token": _refresh_token}))
    except Exception as e:
        logger.warning(f"保存 refresh_token 失败: {e}")


def _load_refresh_token():
    """启动时从文件恢复 refresh_token"""
    global _refresh_token
    if not _TOKEN_FILE.exists():
        return
    try:
        data = json.loads(_TOKEN_FILE.read_text())
        _refresh_token = data.get("refresh_token")
        if _refresh_token:
            logger.info("从文件恢复 refresh_token 成功")
    except Exception as e:
        logger.warning(f"加载 refresh_token 失败: {e}")


def _clear_refresh_token():
    """清除持久化的 refresh_token"""
    global _refresh_token
    _refresh_token = None
    try:
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
    except Exception as e:
        logger.warning(f"删除 refresh_token 文件失败: {e}")


def _extract_refresh_token(resp: httpx.Response) -> Optional[str]:
    """从 NagaBusiness 响应的 Set-Cookie 中提取 refresh_token"""
    token = resp.cookies.get("refresh_token")
    if token:
        return token
    # 向后兼容：body 中可能仍有 refresh_token
    try:
        data = resp.json()
        return data.get("refresh_token") or data.get("refreshToken")
    except Exception:
        return None


# 模块加载时恢复 refresh_token
_load_refresh_token()


# ── API 方法 ─────────────────────────────────────

async def get_captcha() -> dict:
    """获取验证码（数学计算题）"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{BUSINESS_URL}/api/auth/captcha")
        resp.raise_for_status()
        return resp.json()


async def login(username: str, password: str, captcha_id: str = "", captcha_answer: str = "") -> dict:
    """通过 NagaBusiness 登录，返回 access_token 和用户信息
    refresh_token 由后端管理，不返回给前端
    """
    global _access_token, _refresh_token, _user_info
    payload: dict = {"username": username, "password": password}
    if captcha_id and captcha_answer:
        payload["captcha_id"] = captcha_id
        payload["captcha_answer"] = captcha_answer
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{BUSINESS_URL}/api/auth/login", json=payload)
        if resp.status_code != 200:
            logger.error(f"NagaBusiness login 返回 {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        data = resp.json()

    _access_token = data.get("access_token") or data.get("accessToken")
    if not _access_token:
        raise ValueError("登录响应中缺少 access_token")

    # 从 Set-Cookie 或 body 提取 refresh_token，由后端持久化管理
    rt = _extract_refresh_token(resp)
    if rt:
        _refresh_token = rt
        _save_refresh_token()
        logger.info("登录成功，refresh_token 已持久化")
    else:
        logger.warning("登录成功，但未获取到 refresh_token（Set-Cookie 和 body 均无）")

    # 登录成功后获取用户信息；若 /auth/me 不可用，从 login 响应中回退
    me = await get_me(_access_token)
    if me:
        _user_info = me
    else:
        _user_info = {"username": username}

    # 不返回 refresh_token 给前端
    return {
        "success": True,
        "user": _user_info,
        "access_token": _access_token,
        "memory_url": NAGA_MEMORY_URL,
    }


async def get_me(token: Optional[str] = None) -> Optional[dict]:
    """通过 token 获取当前用户信息"""
    t = token or _access_token
    if not t:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{BUSINESS_URL}/api/auth/me", headers={"Authorization": f"Bearer {t}"})
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception as e:
        logger.warning(f"获取用户信息失败: {e}")
        return None


async def refresh(refresh_token_override: Optional[str] = None) -> dict:
    """使用 refresh_token 刷新 access_token
    优先使用传入的 token，否则使用后端持久化的 token
    采用兼容模式：在 body 中传 refresh_token（非浏览器客户端）
    使用 asyncio.Lock 防止并发刷新导致 token 轮换冲突
    """
    global _access_token, _refresh_token, _last_refresh_at
    async with _refresh_lock:
        token = refresh_token_override or _refresh_token
        source = "override" if refresh_token_override else ("file" if _refresh_token else "none")
        if not token:
            logger.error(f"refresh 失败: 无可用 refresh_token (stored={_refresh_token is not None}, file={_TOKEN_FILE.exists()})")
            raise ValueError("无可用的 refresh_token，请重新登录")

        logger.info(f"尝试刷新 token (source={source}, token_prefix={token[:20]}...)")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{BUSINESS_URL}/api/auth/refresh", json={"refresh_token": token})
            resp.raise_for_status()
            data = resp.json()

        _access_token = data.get("access_token") or data.get("accessToken")
        _last_refresh_at = time.monotonic()
        logger.info(f"token 刷新成功, new_access_token_prefix={_access_token[:20] if _access_token else 'None'}...")

        # 提取新的 refresh_token（Token 轮换：旧 token 立即作废）
        new_rt = _extract_refresh_token(resp)
        if new_rt:
            _refresh_token = new_rt
            _save_refresh_token()

        return {"access_token": _access_token}


def logout():
    """清除本地认证状态和持久化文件"""
    global _access_token, _user_info
    _access_token = None
    _user_info = None
    _clear_refresh_token()


def is_authenticated() -> bool:
    return _access_token is not None


def has_refresh_token() -> bool:
    """检查是否持有可用的 refresh_token（供前端判断是否值得尝试刷新）"""
    return _refresh_token is not None


def restore_token(token: str):
    """从前端传入的 token 同步到服务端认证状态
    刷新保护窗口内跳过同步，防止前端旧轮询请求覆盖后端刚刷新的新 token
    """
    global _access_token
    if not token:
        return
    # 刷新保护窗口：刚刷新完的 token 不能被前端旧请求覆盖
    if _last_refresh_at and (time.monotonic() - _last_refresh_at < _REFRESH_GRACE_PERIOD):
        if token != _access_token:
            logger.debug("restore_token 跳过：处于刷新保护窗口内，忽略旧 token")
            return
    _access_token = token


def get_access_token() -> Optional[str]:
    return _access_token


def get_user_info() -> Optional[dict]:
    return _user_info


async def register(username: str, email: str, password: str, verification_code: str) -> dict:
    """通过 NagaBusiness 注册新用户"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{BUSINESS_URL}/api/auth/register",
            json={"username": username, "email": email, "password": password, "verification_code": verification_code},
        )
        resp.raise_for_status()
        return resp.json()


async def send_verification(email: str, username: str, captcha_id: str = "", captcha_answer: str = "") -> dict:
    """发送邮箱验证码"""
    payload: dict = {"email": email, "username": username}
    if captcha_id and captcha_answer:
        payload["captcha_id"] = captcha_id
        payload["captcha_answer"] = captcha_answer
    logger.info(f"send_verification payload: {payload}")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{BUSINESS_URL}/api/auth/send-verification",
            json=payload,
        )
        if resp.status_code != 200:
            logger.error(f"NagaBusiness send-verification 返回 {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()
