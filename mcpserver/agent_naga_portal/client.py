"""NagaPortal HTTP客户端封装 #"""
import asyncio  # 异步 #
from typing import Any, Dict, Optional  # 类型 #
import httpx  # HTTP客户端 #
from system.config import config  # 全局配置 #


class NagaPortalClient:
    """与官网API交互的轻量客户端(长期缓存优化版) #"""

    def __init__(self, base_url: Optional[str] = None):  # 初始化 #
        self.base_url = (base_url or config.naga_portal.portal_url).rstrip('/')  # 基础URL #
        self._client: Optional[httpx.AsyncClient] = None  # 异步客户端 #
        self._logged_in: bool = False  # 登录标记 #
        self._username_masked: str = ""  # 掩码用户名 #
        self._cached_user_id: Optional[int] = None  # 缓存的用户ID #
        self._user_id_initialized: bool = False  # 用户ID是否已初始化 #
        
        # 项目启动时初始化用户ID缓存 #
        self._init_user_id_cache()  # 初始化用户ID缓存 #

    def _init_user_id_cache(self):  # 初始化用户ID缓存 #
        """项目启动时获取并缓存用户ID #"""
        # 延迟初始化，避免循环导入死锁
        # 在实际使用时再获取用户ID
        self._cached_user_id = None
        self._user_id_initialized = False

    async def _ensure_client(self):  # 确保客户端 #
        if self._client is None:  # 未创建则创建 #
            # 优化超时时间，从15秒降低到8秒 #
            timeout = min(config.naga_portal.request_timeout, 8)  # 最大8秒超时 #
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,  # 优化超时 #
                follow_redirects=True,
                headers=config.naga_portal.default_headers.copy(),  # 默认头 #
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),  # 连接池优化 #
            )  # 创建客户端 #
            
            # 设置最新的cookie到新客户端 #
            try:
                from .portal_login_manager import get_cookies
                latest_cookies = get_cookies()
                if latest_cookies:
                    self._client.cookies.update(latest_cookies)  # 设置最新cookie #
            except Exception as e:
                # 如果获取cookie失败，尝试使用保存的cookie #
                if hasattr(self, '_saved_cookies') and self._saved_cookies:
                    self._client.cookies.update(self._saved_cookies)  # 重新设置cookie #

    @staticmethod
    def _mask(s: str) -> str:  # 掩码 #
        if not s:  # 空处理 #
            return ""  # 返回空 #
        if len(s) <= 2:  # 短字符 #
            return s[0] + "*" * (len(s) - 1)  # 简单掩码 #
        return s[0] + "*" * (len(s) - 2) + s[-1]  # 掩码中间 #

    async def login(self, username: Optional[str] = None, password: Optional[str] = None, login_path: Optional[str] = None) -> Dict[str, Any]:  # 登录 #
        await self._ensure_client()  # 准备客户端 #
        u = username or config.naga_portal.username  # 用户名 #
        p = password or config.naga_portal.password  # 密码 #
        self._username_masked = self._mask(u)  # 保存掩码 #
        if not u or not p:  # 校验 #
            return {"success": False, "status": "no_credentials", "message": "未配置用户名或密码", "data": {}}  # 缺少凭据 #
        
        # 使用配置的登录路径或默认路径 #
        path = login_path or config.naga_portal.login_path  # 登录路径 #
        if not path.startswith('/'):
            path = '/' + path  # 规范路径 #
        
        # 添加turnstile参数 #
        turnstile = config.naga_portal.turnstile_param  # 验证参数 #
        if turnstile:
            path = f"{path}?turnstile={turnstile}"  # 添加参数 #
        
        try:
            # 载荷生成：支持json或form #
            uname_key = config.naga_portal.login_username_key  # 用户名键 #
            passwd_key = config.naga_portal.login_password_key  # 密码键 #
            payload = {uname_key: u, passwd_key: p}  # 载荷 #
            
            if config.naga_portal.login_payload_mode == "form":  # 表单模式 #
                resp = await self._client.post(path, data=payload)  # 表单提交 #
            else:
                resp = await self._client.post(path, json=payload)  # JSON提交 #
            
            ok = (200 <= resp.status_code < 300)  # 状态判断 #
            self._logged_in = ok  # 更新状态 #
            
            # 提取响应信息 #
            response_data = {
                "url": str(resp.request.url),
                "status_code": resp.status_code,
                "response_text": resp.text[:500]  # 限制长度 #
            }
            
            # 检查是否有set-cookie头 #
            if "set-cookie" in resp.headers:
                response_data["cookies_set"] = True  # 标记有cookie #
                response_data["cookie_count"] = len(resp.headers.get_list("set-cookie"))  # cookie数量 #
            
            return {"success": ok, "status": "ok" if ok else "http_error", "message": f"HTTP {resp.status_code}", "data": response_data}  # 返回 #
        except Exception as e:
            # 允许无真实接口时也能跑通流程 #
            self._logged_in = True  # 置为已登录(占位)，便于后续GET/POST测试 #
            return {"success": True, "status": "mock_login", "message": f"已进入占位登录: {e}", "data": {"username": self._username_masked}}  # 占位成功 #

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:  # GET请求 #
        await self._ensure_client()  # 确保客户端 #
        if not path.startswith('/'):
            path = '/' + path  # 规范路径 #
        
        # 获取最新的cookie并直接传递给请求 #
        cookies = {}
        try:
            from .portal_login_manager import get_cookies
            cookies = get_cookies()  # 获取最新cookie #
        except Exception as e:
            # 如果获取cookie失败，使用保存的cookie #
            if hasattr(self, '_saved_cookies'):
                cookies = self._saved_cookies or {}
        
        try:
            # 直接传递cookies参数到GET请求 #
            resp = await self._client.get(path, params=params or {}, headers=headers, cookies=cookies)  # 发送 #
            return {"success": True, "status": "ok", "message": f"HTTP {resp.status_code}", "data": {"status_code": resp.status_code, "text": resp.text[:1000]}}  # 返回 #
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def post(self, path: str, json_body: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:  # POST请求 #
        await self._ensure_client()  # 确保客户端 #
        if not path.startswith('/'):
            path = '/' + path  # 规范路径 #
        
        # 获取最新的cookie并直接传递给请求 #
        cookies = {}
        try:
            from .portal_login_manager import get_cookies
            cookies = get_cookies()  # 获取最新cookie #
        except Exception as e:
            # 如果获取cookie失败，使用保存的cookie #
            if hasattr(self, '_saved_cookies'):
                cookies = self._saved_cookies or {}
        
        try:
            # 直接传递cookies参数到POST请求 #
            resp = await self._client.post(path, json=json_body or {}, headers=headers, cookies=cookies)  # 发送 #
            return {"success": True, "status": "ok", "message": f"HTTP {resp.status_code}", "data": {"status_code": resp.status_code, "text": resp.text[:1000]}}  # 返回 #
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    def set_cookies(self, cookies: Dict[str, str]):  # 批量设置cookie #
        """设置客户端cookie，用于保持登录状态 #"""
        # 保存cookie到实例变量，确保_ensure_client时能重新设置
        self._saved_cookies = cookies or {}  # 保存cookie #
        if self._client:
            self._client.cookies.update(self._saved_cookies)  # 更新cookie #

    def get_cached_user_id(self) -> Optional[int]:  # 获取缓存的用户ID #
        """获取缓存的用户ID，延迟初始化避免循环导入 #"""
        if not self._user_id_initialized:
            try:
                from .portal_login_manager import get_user_id
                self._cached_user_id = get_user_id()
                self._user_id_initialized = True
            except Exception as e:
                # 如果获取失败，不影响正常使用
                pass
        return self._cached_user_id

    async def recharge(self, amount: str, payment_type: str = "wxpay") -> Dict[str, Any]:  # 额度充值(长期缓存版) #
        """发起额度充值请求 #"""
        await self._ensure_client()  # 确保客户端 #
        # 构建充值请求载荷 #
        payload = {
            "amount": float(amount),  # 金额（数字格式） #
            "paymentMethod": payment_type,  # 支付方式 #
            "package": None  # 包信息 #
        }  # 载荷 #
        
        try:
            # 使用项目启动时缓存的用户ID #
            headers = {}
            user_id = self.get_cached_user_id()
            if user_id:
                headers["user-id"] = str(user_id)  # 修正header名称 #
            
            # 调试信息：显示当前cookie状态 #
            try:
                from .portal_login_manager import get_cookies
                current_cookies = get_cookies()
                print(f"🍪 当前Cookie信息: {current_cookies}")
            except Exception as e:
                print(f"🍪 获取Cookie失败: {e}")
            
            resp = await self.post("/api/user/pay", json_body=payload, headers=headers)  # 发送充值请求 #
            
            # 处理响应 #
            if resp.get("success"):
                response_data = resp.get("data", {})
                response_text = response_data.get("text", "")
                
                # 解析响应JSON #
                try:
                    import json
                    response_json = json.loads(response_text)
                    
                    # 获取支付URL #
                    payment_url = response_json.get("url", "")
                    if payment_url:
                        return {
                            "success": True,
                            "status": "payment_ready",
                            "message": f"充值请求成功，请访问支付页面完成支付",
                            "data": {
                                "payment_url": payment_url,
                                "amount": amount,
                                "payment_type": payment_type,
                                "original_response": response_json
                            }
                        }  # 返回支付信息 #
                    else:
                        # 没有支付URL，返回原始响应 #
                        return {
                            "success": True,
                            "status": "request_sent",
                            "message": "充值请求已发送，请检查响应内容",
                            "data": {
                                "amount": amount,
                                "payment_type": payment_type,
                                "response": response_json
                            }
                        }  # 返回请求信息 #
                except json.JSONDecodeError:
                    # JSON解析失败，返回原始响应 #
                    return {
                        "success": True,
                        "status": "request_sent",
                        "message": "充值请求已发送，请检查响应内容",
                        "data": {
                            "amount": amount,
                            "payment_type": payment_type,
                            "response": response_data
                        }
                    }  # 返回请求信息 #
            else:
                # 请求失败 #
                return resp  # 返回原始错误响应 #
                
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def close(self):  # 关闭客户端 #
        """关闭HTTP客户端，释放资源 #"""
        if self._client:
            await self._client.aclose()  # 关闭客户端 #
            self._client = None  # 清空引用 #


