"""NagaPortal自动登录管理器 #"""
import logging  # 日志 #
from typing import Optional, Dict, Any  # 类型 #
from .client import NagaPortalClient  # 客户端 #
from system.config import config  # 配置 #

logger = logging.getLogger("NagaPortalLoginManager")

class NagaPortalLoginManager:
    """娜迦官网自动登录管理器 #"""
    
    def __init__(self):  # 初始化 #
        self.client: Optional[NagaPortalClient] = None  # 客户端 #
        self._cookies: Dict[str, str] = {}  # Cookie存储 #
        self._is_logged_in: bool = False  # 登录状态 #
        self._login_error: Optional[str] = None  # 登录错误 #
        self._user_id: Optional[int] = None  # 用户ID #
        
    async def auto_login(self) -> Dict[str, Any]:  # 自动登录 #
        """自动登录娜迦官网 #"""
        try:
            # 检查配置 #
            if not config.naga_portal.username or not config.naga_portal.password:  # 检查配置 #
                error_msg = "未配置娜迦官网用户名或密码，请在config.json中设置naga_portal.username和password"  # 错误消息 #
                self._is_logged_in = False  # 设置状态 #
                self._login_error = error_msg  # 设置错误 #
                return {
                    "success": False,
                    "status": "no_credentials",
                    "message": error_msg,
                    "data": {}
                }  # 返回 #
            
            # 创建客户端 #
            self.client = NagaPortalClient()  # 客户端 #
            
            # 执行登录 #
            result = await self.client.login()  # 登录 #
            
            if result['success']:  # 成功 #
                self._is_logged_in = True  # 设置登录状态 #
                self._login_error = None  # 清除错误 #
                
                # 提取cookie信息 #
                data = result.get('data', {})  # 数据 #
                if 'cookies_set' in data:  # 有cookie #
                    cookie_count = data.get('cookie_count', 0)  # cookie数量 #
                    
                    # 保存cookie到管理器 #
                    if hasattr(self.client, '_client') and self.client._client:  # 有客户端 #
                        try:
                            # 从httpx客户端获取cookie
                            cookies = dict(self.client._client.cookies)  # 获取cookie #
                            if cookies:
                                self._cookies = cookies  # 保存cookie #
                                
                                # 尝试从响应中提取用户ID
                                try:
                                    import json
                                    response_text = data.get('response_text', '')
                                    if response_text:
                                        response_data = json.loads(response_text)
                                        if response_data.get('success') and 'data' in response_data:
                                            user_id = response_data['data'].get('id')
                                            if user_id:
                                                self._user_id = user_id  # 保存用户ID #
                                except Exception:
                                    # 静默处理异常 #
                                    pass
                            else:
                                # 如果没有cookie，尝试从响应头中解析
                                # 这里可以添加从响应头解析cookie的逻辑
                                pass
                        except Exception:
                            # 静默处理异常 #
                            pass
                
                return {
                    "success": True,
                    "status": "logged_in",
                    "message": "娜迦官网自动登录成功",
                    "data": {
                        "cookie_count": data.get('cookie_count', 0),
                        "cookies": list(self._cookies.keys())
                    }
                }  # 返回 #
            else:  # 失败 #
                error_msg = result.get('message', '未知错误')  # 错误消息 #
                self._is_logged_in = False  # 设置状态 #
                self._login_error = error_msg  # 设置错误 #
                
                return {
                    "success": False,
                    "status": "login_failed",
                    "message": f"娜迦官网登录失败: {error_msg}",
                    "data": {}
                }  # 返回 #
                
        except Exception as e:  # 异常 #
            error_msg = str(e)  # 错误消息 #
            self._is_logged_in = False  # 设置状态 #
            self._login_error = error_msg  # 设置错误 #
            
            return {
                "success": False,
                "status": "exception",
                "message": f"自动登录异常: {str(e)}",
                "data": {}
            }  # 返回 #
    
    def get_cookies(self) -> Dict[str, str]:  # 获取cookie #
        """获取当前保存的cookie #"""
        return self._cookies.copy()  # 返回副本 #
    
    def set_cookies(self, cookies: Dict[str, str]) -> None:  # 设置cookie #
        """设置cookie #"""
        if cookies:
            self._cookies.update(cookies)  # 更新cookie #
            logger.debug(f"已设置 {len(cookies)} 个Cookie: {list(cookies.keys())}")  # 调试日志 #
    
    def get_user_id(self) -> Optional[int]:  # 获取用户ID #
        """获取用户ID #"""
        return self._user_id  # 返回用户ID #
    
    def set_user_id(self, user_id: int) -> None:  # 设置用户ID #
        """设置用户ID #"""
        self._user_id = user_id  # 设置用户ID #
    
    def is_logged_in(self) -> bool:  # 检查是否已登录 #
        """检查是否已登录 #"""
        return self._is_logged_in  # 返回状态 #
    
    def get_login_error(self) -> Optional[str]:  # 获取登录错误 #
        """获取登录错误信息 #"""
        return self._login_error  # 返回错误 #
    
    def get_status(self) -> Dict[str, Any]:  # 获取状态 #
        """获取登录管理器状态 #"""
        return {
            "is_logged_in": self._is_logged_in,
            "login_error": self._login_error,
            "cookie_count": len(self._cookies),
            "cookies": list(self._cookies.keys()) if self._cookies else [],
            "user_id": self._user_id
        }  # 返回状态 #

# 全局登录管理器实例 #
_portal_login_manager: Optional[NagaPortalLoginManager] = None

def get_portal_login_manager() -> NagaPortalLoginManager:  # 获取管理器 #
    """获取全局NagaPortal登录管理器实例 #"""
    global _portal_login_manager
    if _portal_login_manager is None:  # 未初始化 #
        _portal_login_manager = NagaPortalLoginManager()  # 创建实例 #
    return _portal_login_manager  # 返回 #

async def auto_login_naga_portal() -> Dict[str, Any]:  # 自动登录 #
    """自动登录娜迦官网的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    return await manager.auto_login()  # 自动登录 #

# 便捷函数 #
def get_cookies() -> Dict[str, str]:  # 获取cookie #
    """获取cookie的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    return manager.get_cookies()  # 获取cookie #

def set_cookies(cookies: Dict[str, str]) -> None:  # 设置cookie #
    """设置cookie的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    manager.set_cookies(cookies)  # 设置cookie #

def get_user_id() -> Optional[int]:  # 获取用户ID #
    """获取用户ID的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    return manager.get_user_id()  # 获取用户ID #

def set_user_id(user_id: int) -> None:  # 设置用户ID #
    """设置用户ID的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    manager.set_user_id(user_id)  # 设置用户ID #

def is_logged_in() -> bool:  # 检查登录状态 #
    """检查登录状态的便捷函数 #"""
    manager = get_portal_login_manager()  # 获取管理器 #
    return manager.is_logged_in()  # 检查状态 #
