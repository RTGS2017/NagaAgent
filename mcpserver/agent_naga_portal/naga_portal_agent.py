"""NagaPortal MCP Agent #"""
import json  # JSON #
import httpx  # HTTP客户端 #
import webbrowser  # 浏览器 #
from typing import Any, Dict, Optional  # 类型 #
from .portal_login_manager import get_cookies, get_user_id  # 登录管理器 #

class NagaPortalAgent:
    """娜迦官网API Agent(简化版) #"""

    name = "NagaPortalAgent"  # 名称 #
    instructions = "与娜迦官网API交互，支持充值等操作"  # 描述 #

    def __init__(self):  # 初始化 #
        self.base_url = "https://naga.furina.chat"  # 基础URL #

    async def handle_handoff(self, data: dict) -> str:  # 统一入口 #
        tool = data.get("tool_name")  # 工具名 #
        try:
            # 支持新旧工具名兼容
            if tool in ["naga_recharge", "充值"]:
                amount = data.get("amount")  # 充值金额 #
                payment_type = data.get("payment_type", "wxpay")  # 支付方式，默认微信支付 #
                if not amount:
                    return json.dumps({"success": False, "status": "invalid_args", "message": "缺少amount参数", "data": {}}, ensure_ascii=False)  # 校验 #
                
                # 验证支付方式 #
                if payment_type not in ["wxpay", "alipay"]:
                    return json.dumps({"success": False, "status": "invalid_args", "message": "payment_type只能是wxpay或alipay", "data": {}}, ensure_ascii=False)  # 校验 #
                
                # 直接使用httpx进行API调用 #
                result = await self._simple_recharge(amount, payment_type)  # 充值 #
                return json.dumps(result, ensure_ascii=False)  # 返回 #

            elif tool in ["naga_redeem_code", "兑换码"]:
                key = data.get("key")  # 兑换码 #
                if not key:
                    return json.dumps({"success": False, "status": "invalid_args", "message": "缺少key参数", "data": {}}, ensure_ascii=False)  # 校验 #
                
                # 直接使用httpx进行API调用 #
                result = await self._simple_redeem_code(key)  # 兑换码 #
                return json.dumps(result, ensure_ascii=False)  # 返回 #

            elif tool in ["naga_balance", "查询余额"]:
                # 直接使用httpx进行API调用 #
                result = await self._simple_balance()  # 余额查询 #
                return json.dumps(result, ensure_ascii=False)  # 返回 #

            elif tool in ["naga_apply_token", "申请令牌"]:
                name = data.get("name")  # 令牌名称 #
                group = data.get("group")  # 模型组 #
                unlimited_quota = data.get("unlimited_quota", True)  # 是否无限制额度 #
                
                # 智能申请API令牌（自动获取模型列表并处理） #
                result = await self._smart_apply_api_token(name, group, unlimited_quota)  # 智能申请 #
                return json.dumps(result, ensure_ascii=False)  # 返回 #

            elif tool in ["naga_get_tokens", "查看令牌"]:
                # 获取已配置的API令牌列表 #
                result = await self._get_api_tokens()  # 获取令牌列表 #
                return json.dumps(result, ensure_ascii=False)  # 返回 #

            return json.dumps({"success": False, "status": "unknown_tool", "message": f"未知工具: {tool}", "data": {}}, ensure_ascii=False)  # 未知 #
        except Exception as e:
            return json.dumps({"success": False, "status": "exception", "message": str(e), "data": {}}, ensure_ascii=False)  # 异常 #

    async def _prepare_request_context(self, need_connection_test: bool = False) -> Dict[str, Any]:  # 准备请求上下文 #
        """准备请求上下文（Cookie、用户ID、Headers等） #"""
        # 获取cookie和用户ID #
        cookies = get_cookies()  # 获取cookie #
        user_id = get_user_id()  # 获取用户ID #
        
        if not cookies:
            return {"success": False, "status": "no_cookies", "message": "未找到登录Cookie，请先登录", "data": {}}  # 无cookie #
        
        # 构建请求参数 #
        headers = {}
        if user_id:
            headers["user-id"] = str(user_id)  # 设置用户ID #
        
        # 如果需要连接测试 #
        if need_connection_test:
            test_result = await self.test_connection()  # 测试连接 #
            if not test_result.get("success"):
                return {
                    "success": False, 
                    "status": "cookie_invalid", 
                    "message": f"Cookie可能已过期或无效: {test_result.get('message', '未知错误')}", 
                    "data": {"test_result": test_result}
                }  # Cookie无效 #
        
        return {
            "success": True,
            "cookies": cookies,
            "headers": headers,
            "user_id": user_id
        }  # 返回上下文 #

    async def test_connection(self) -> Dict[str, Any]:  # 测试连接 #
        """测试与服务器的连接是否有效 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=False)  # 测试连接本身不需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 发送简单的GET请求测试连接 #
            result = await self._make_request("GET", f"{self.base_url}/api/user/self", None, context)  # 发送请求 #
            
            if result.get("success"):
                return {
                    "success": True,
                    "status": "connection_ok",
                    "message": "连接正常"
                }  # 连接正常 #
            else:
                return {
                    "success": False,
                    "status": "connection_failed",
                    "message": result.get("error", "连接失败")
                }  # 连接失败 #
                
        except Exception as e:
            return {
                "success": False,
                "status": "connection_error",
                "message": str(e)
            }  # 连接异常 #

    async def _make_request(self, method: str, url: str, payload: Dict[str, Any] = None, context: Dict[str, Any] = None) -> Dict[str, Any]:  # 发送请求 #
        """发送HTTP请求的通用方法 #"""
        try:
            # 打印调试信息 #
            print(f"🍪 使用Cookie: {context['cookies']}")  # 调试信息 #
            print(f"📋 Headers: {context['headers']}")  # 调试信息 #
            if payload:
                print(f"📦 Payload: {payload}")  # 调试信息 #
            print(f"🌐 请求URL: {url}")  # 调试信息 #
            
            # 发送请求 #
            async with httpx.AsyncClient(timeout=10.0) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=context['headers'], cookies=context['cookies'])  # GET请求 #
                else:
                    response = await client.post(url, json=payload, headers=context['headers'], cookies=context['cookies'])  # POST请求 #
                
                print(f"📋 响应状态: {response.status_code}")  # 调试信息 #
                print(f"📋 响应内容: {response.text}")  # 调试信息 #
                
                if response.status_code == 200:
                    try:
                        response_data = response.json()
                        return {
                            "success": True,
                            "status_code": response.status_code,
                            "data": response_data,
                            "raw_text": response.text
                        }  # 返回成功 #
                    except json.JSONDecodeError:
                        return {
                            "success": True,
                            "status_code": response.status_code,
                            "data": None,
                            "raw_text": response.text
                        }  # 返回原始文本 #
                else:
                    return {
                        "success": False,
                        "status_code": response.status_code,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }  # 返回错误 #
                    
        except Exception as e:
            return {"success": False, "error": str(e)}  # 返回异常 #

    async def _simple_recharge(self, amount: str, payment_type: str) -> Dict[str, Any]:  # 简化充值 #
        """直接使用httpx进行充值请求 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=False)  # 充值不需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 构建请求载荷 #
            payload = {
                "amount": int(float(amount)),  # 金额（整数格式） #
                "paymentMethod": payment_type,  # 支付方式 #
                "package": None  # 包信息 #
            }  # 载荷 #
            
            # 发送请求 #
            result = await self._make_request("POST", f"{self.base_url}/api/user/pay", payload, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": True,
                    "status": "request_sent",
                    "message": "充值请求已发送，请检查响应内容",
                    "data": {
                        "amount": amount,
                        "payment_type": payment_type,
                        "response": result.get("raw_text", "")
                    }
                }  # 返回请求信息 #
            
            payment_url = response_data.get("url", "")
            
            if payment_url:
                # 自动打开支付页面（使用POST数据） #
                opened = False  # 是否成功打开 #
                
                # 从响应中提取支付数据 #
                payment_data = response_data.get("data", {})  # 支付数据 #
                
                # 方法1: 使用POST方式提交数据到支付页面 #
                try:
                    # 创建临时HTML文件，包含自动提交的表单 #
                    import tempfile  # 临时文件 #
                    import os  # 操作系统 #
                    
                    # 生成临时HTML文件 #
                    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>正在跳转到支付页面...</title>
</head>
<body>
    <h2>正在跳转到支付页面，请稍候...</h2>
    <form id="paymentForm" method="post" action="{payment_url}">
"""
                    
                    # 添加所有支付参数 #
                    for key, value in payment_data.items():
                        html_content += f'        <input type="hidden" name="{key}" value="{value}">\n'
                    
                    html_content += """
    </form>
    <script>
        // 自动提交表单
        document.getElementById('paymentForm').submit();
    </script>
</body>
</html>
"""
                    
                    # 创建临时HTML文件 #
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                        f.write(html_content)
                        temp_html_path = f.name
                    
                    # 打开临时HTML文件 #
                    webbrowser.open(f"file://{temp_html_path}")  # 打开本地HTML文件 #
                    print(f"🌐 已自动打开支付页面（带数据）: {payment_url}")  # 调试信息 #
                    opened = True  # 标记成功 #
                    
                    # 延迟删除临时文件 #
                    import threading  # 线程 #
                    def delete_temp_file():
                        import time  # 时间 #
                        time.sleep(5)  # 等待5秒 #
                        try:
                            os.unlink(temp_html_path)  # 删除临时文件 #
                        except:
                            pass  # 忽略删除错误 #
                    
                    threading.Thread(target=delete_temp_file, daemon=True).start()  # 启动删除线程 #
                    
                except Exception as e:
                    print(f"❌ POST方式打开失败: {e}")  # 调试信息 #
                
                # 方法2: 如果POST方式失败，尝试直接打开URL #
                if not opened:
                    try:
                        webbrowser.open(payment_url)  # 直接打开支付页面 #
                        print(f"🌐 已直接打开支付页面: {payment_url}")  # 调试信息 #
                        opened = True  # 标记成功 #
                    except Exception as e:
                        print(f"❌ webbrowser打开失败: {e}")  # 调试信息 #
                
                # 方法3: 如果都失败了，提供手动链接和支付数据 #
                if not opened:
                    print("⚠️ 无法自动打开支付页面")  # 调试信息 #
                    print(f"📋 请手动访问: {payment_url}")  # 调试信息 #
                    print(f"📦 支付数据: {payment_data}")  # 调试信息 #
                
                return {
                    "success": True,
                    "status": "payment_ready",
                    "message": f"充值请求成功，{'已自动打开支付页面' if opened else '请手动访问支付页面'}，请完成支付",
                    "data": {
                        "payment_url": payment_url,
                        "amount": amount,
                        "payment_type": payment_type,
                        "original_response": response_data,
                        "auto_opened": opened
                    }
                }  # 返回支付信息 #
            else:
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
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _simple_redeem_code(self, key: str) -> Dict[str, Any]:  # 简化兑换码 #
        """直接使用httpx进行兑换码请求 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=True)  # 兑换码需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 构建请求载荷 #
            payload = {
                "key": key  # 兑换码 #
            }  # 载荷 #
            
            # 发送请求 #
            result = await self._make_request("POST", f"{self.base_url}/api/user/topup", payload, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": True,
                    "status": "request_sent",
                    "message": "兑换码请求已发送，请检查响应内容",
                    "data": {
                        "key": key,
                        "response": result.get("raw_text", "")
                    }
                }  # 返回请求信息 #
            
            # 检查兑换结果 #
            if response_data.get("success") or response_data.get("message") == "success":
                return {
                    "success": True,
                    "status": "redeem_success",
                    "message": "兑换码使用成功！",
                    "data": {
                        "key": key,
                        "response": response_data
                    }
                }  # 返回成功信息 #
            else:
                # 兑换失败 #
                error_msg = response_data.get("message", "兑换失败")
                return {
                    "success": False,
                    "status": "redeem_failed",
                    "message": f"兑换码使用失败: {error_msg}",
                    "data": {
                        "key": key,
                        "response": response_data
                    }
                }  # 返回失败信息 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _simple_balance(self) -> Dict[str, Any]:  # 简化余额查询 #
        """直接使用httpx进行余额查询 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=True)  # 余额查询需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 发送请求 #
            result = await self._make_request("GET", f"{self.base_url}/api/user/self", None, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": False,
                    "status": "parse_error",
                    "message": "响应解析失败",
                    "data": {
                        "response": result.get("raw_text", "")
                    }
                }  # 返回解析错误 #
            
            # 检查请求是否成功 #
            if response_data.get("success"):
                user_data = response_data.get("data", {})  # 用户数据 #
                quota = user_data.get("quota", 0)  # 额度 #
                used_quota = user_data.get("used_quota", 0)  # 已使用额度 #
                
                # 额度换算为余额（25500000对应51，换算比例：500000） #
                conversion_rate = 500000  # 换算比例 #
                balance = quota / conversion_rate  # 余额 #
                used_balance = used_quota / conversion_rate  # 已使用余额 #
                remaining_balance = balance - used_balance  # 剩余余额 #
                
                return {
                    "success": True,
                    "status": "balance_success",
                    "message": f"余额查询成功，当前余额：{round(remaining_balance, 2)}元",
                    "data": {}
                }  # 返回余额信息 #
            else:
                # 查询失败 #
                error_msg = response_data.get("message", "查询失败")
                return {
                    "success": False,
                    "status": "query_failed",
                    "message": f"余额查询失败: {error_msg}",
                    "data": {
                        "response": response_data
                    }
                }  # 返回失败信息 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _smart_apply_api_token(self, name: str = None, group: str = None, unlimited_quota: bool = True) -> Dict[str, Any]:  # 智能申请API令牌 #
        """智能申请API令牌，自动获取模型列表并处理申请流程 #"""
        try:
            # 第一步：获取可用模型列表 #
            models_result = await self._get_available_models()  # 获取模型列表 #
            
            if not models_result.get("success"):
                return {
                    "success": False,
                    "status": "models_failed",
                    "message": f"获取模型列表失败: {models_result.get('message', '未知错误')}",
                    "data": {
                        "models_result": models_result
                    }
                }  # 返回错误 #
            
            models_list = models_result.get("data", {}).get("models", [])  # 模型列表 #
            
            # 如果没有提供参数，返回模型列表供LLM选择 #
            if not name or not group:
                return {
                    "success": True,
                    "status": "models_ready",
                    "message": f"请从以下 {len(models_list)} 个可用模型中选择要申请的模型",
                    "data": {
                        "available_models": models_list,
                        "total_count": len(models_list),
                        "application_format": {
                            "tool_name": "naga_apply_token",
                            "name": "令牌名称（必填）",
                            "group": "模型组名（必填，从上述列表中选择）",
                            "unlimited_quota": "是否无限制额度（可选，默认true）"
                        },
                        "example": {
                            "tool_name": "naga_apply_token",
                            "name": "my_deepseek_token",
                            "group": "deepseek",
                            "unlimited_quota": True
                        }
                    }
                }  # 返回模型列表 #
            
            # 验证模型组是否有效 #
            valid_groups = [model["group"] for model in models_list]  # 有效模型组 #
            if group not in valid_groups:
                return {
                    "success": False,
                    "status": "invalid_group",
                    "message": f"无效的模型组 '{group}'，请从以下有效模型组中选择: {', '.join(valid_groups)}",
                    "data": {
                        "available_models": models_list,
                        "provided_group": group,
                        "valid_groups": valid_groups
                    }
                }  # 返回错误 #
            
            # 第二步：申请API令牌 #
            apply_result = await self._apply_api_token(name, group, unlimited_quota)  # 申请令牌 #
            
            if not apply_result.get("success"):
                return apply_result  # 返回申请错误 #
            
            # 第三步：获取最新的令牌列表 #
            tokens_result = await self._get_api_tokens()  # 获取令牌列表 #
            
            # 构建最终返回结果 #
            final_result = {
                "success": True,
                "status": "apply_complete",
                "message": f"API令牌申请成功！令牌名称: {name}, 模型组: {group}",
                "data": {
                    "application_info": {
                        "name": name,
                        "group": group,
                        "unlimited_quota": unlimited_quota
                    },
                    "application_result": apply_result.get("data", {}),
                    "current_tokens": tokens_result.get("data", {}).get("tokens", []) if tokens_result.get("success") else [],
                    "total_tokens": tokens_result.get("data", {}).get("total_count", 0) if tokens_result.get("success") else 0
                }
            }  # 最终结果 #
            
            return final_result  # 返回完整结果 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _get_available_models(self) -> Dict[str, Any]:  # 获取可用模型 #
        """获取可申请的模型列表 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=True)  # 需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 发送请求 #
            result = await self._make_request("GET", f"{self.base_url}/api/user/self/groups", None, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": False,
                    "status": "parse_error",
                    "message": "响应解析失败",
                    "data": {
                        "response": result.get("raw_text", "")
                    }
                }  # 返回解析错误 #
            
            # 检查请求是否成功 #
            if response_data.get("success"):
                models_data = response_data.get("data", {})  # 模型数据 #
                
                # 格式化模型列表 #
                models_list = []
                for group_name, model_info in models_data.items():
                    models_list.append({
                        "group": group_name,  # 模型组名 #
                        "description": model_info.get("desc", ""),  # 描述 #
                        "ratio": model_info.get("ratio", 0)  # 汇率 #
                    })  # 模型信息 #
                
                return {
                    "success": True,
                    "status": "models_success",
                    "message": f"成功获取到 {len(models_list)} 个可用模型",
                    "data": {
                        "models": models_list,
                        "total_count": len(models_list),
                        "original_response": response_data
                    }
                }  # 返回模型列表 #
            else:
                # 查询失败 #
                error_msg = response_data.get("message", "查询失败")
                return {
                    "success": False,
                    "status": "query_failed",
                    "message": f"获取模型列表失败: {error_msg}",
                    "data": {
                        "response": response_data
                    }
                }  # 返回失败信息 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _apply_api_token(self, name: str, group: str, unlimited_quota: bool = True) -> Dict[str, Any]:  # 申请API令牌 #
        """申请新的API令牌 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=True)  # 需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 构建请求载荷 #
            payload = {
                "name": name,  # 令牌名称 #
                "remain_quota": 500000,  # 剩余额度 #
                "expired_time": -1,  # 过期时间（-1表示永不过期） #
                "unlimited_quota": unlimited_quota,  # 是否无限制额度 #
                "model_limits_enabled": False,  # 模型限制 #
                "model_limits": "",  # 模型限制列表 #
                "allow_ips": "",  # 允许的IP #
                "group": group,  # 模型组 #
                "mj_proxy_method": "site",  # MJ代理方法 #
                "mj_custom_proxy_url": "",  # MJ自定义代理URL #
                "mj_mode": "",  # MJ模式 #
                "rate_limit_enabled": False,  # 速率限制 #
                "rate_limit_window": 10,  # 速率限制窗口 #
                "rate_limit_requests": 900,  # 速率限制请求数 #
                "rate_limit_error_message": ""  # 速率限制错误消息 #
            }  # 载荷 #
            
            # 发送请求 #
            result = await self._make_request("POST", f"{self.base_url}/api/token/", payload, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": False,
                    "status": "parse_error",
                    "message": "响应解析失败",
                    "data": {
                        "response": result.get("raw_text", "")
                    }
                }  # 返回解析错误 #
            
            # 检查申请是否成功 #
            if response_data.get("success"):
                return {
                    "success": True,
                    "status": "apply_success",
                    "message": f"API令牌申请成功！令牌名称: {name}, 模型组: {group}",
                    "data": {
                        "name": name,
                        "group": group,
                        "unlimited_quota": unlimited_quota,
                        "original_response": response_data
                    }
                }  # 返回成功信息 #
            else:
                # 申请失败 #
                error_msg = response_data.get("message", "申请失败")
                return {
                    "success": False,
                    "status": "apply_failed",
                    "message": f"API令牌申请失败: {error_msg}",
                    "data": {
                        "name": name,
                        "group": group,
                        "response": response_data
                    }
                }  # 返回失败信息 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def _get_api_tokens(self) -> Dict[str, Any]:  # 获取API令牌列表 #
        """获取已配置的API令牌列表 #"""
        try:
            # 准备请求上下文 #
            context = await self._prepare_request_context(need_connection_test=True)  # 需要连接测试 #
            if not context.get("success"):
                return context  # 返回错误 #
            
            # 发送请求 #
            result = await self._make_request("GET", f"{self.base_url}/api/token/?p=0&size=10", None, context)  # 发送请求 #
            
            if not result.get("success"):
                return {
                    "success": False,
                    "status": "http_error",
                    "message": result.get("error", "请求失败"),
                    "data": {}
                }  # 返回错误 #
            
            # 处理响应 #
            response_data = result.get("data")
            if not response_data:
                return {
                    "success": False,
                    "status": "parse_error",
                    "message": "响应解析失败",
                    "data": {
                        "response": result.get("raw_text", "")
                    }
                }  # 返回解析错误 #
            
            # 检查请求是否成功 #
            if response_data.get("success"):
                tokens_data = response_data.get("data", [])  # 令牌数据 #
                
                # 格式化令牌列表 #
                tokens_list = []
                for token_info in tokens_data:
                    tokens_list.append({
                        "id": token_info.get("id"),  # 令牌ID #
                        "name": token_info.get("name", ""),  # 令牌名称 #
                        "key": token_info.get("key", ""),  # API密钥 #
                        "group": token_info.get("group", ""),  # 模型组 #
                        "unlimited_quota": token_info.get("unlimited_quota", False),  # 是否无限制额度 #
                        "remain_quota": token_info.get("remain_quota", 0),  # 剩余额度 #
                        "used_quota": token_info.get("used_quota", 0),  # 已使用额度 #
                        "status": token_info.get("status", 0),  # 状态 #
                        "created_time": token_info.get("created_time", 0),  # 创建时间 #
                        "accessed_time": token_info.get("accessed_time", 0)  # 访问时间 #
                    })  # 令牌信息 #
                
                return {
                    "success": True,
                    "status": "tokens_success",
                    "message": f"成功获取到 {len(tokens_list)} 个API令牌",
                    "data": {
                        "tokens": tokens_list,
                        "total_count": len(tokens_list),
                        "original_response": response_data
                    }
                }  # 返回令牌列表 #
            else:
                # 查询失败 #
                error_msg = response_data.get("message", "查询失败")
                return {
                    "success": False,
                    "status": "query_failed",
                    "message": f"获取API令牌列表失败: {error_msg}",
                    "data": {
                        "response": response_data
                    }
                }  # 返回失败信息 #
                    
        except Exception as e:
            return {"success": False, "status": "network_error", "message": str(e), "data": {}}  # 异常 #

    async def close(self):  # 关闭资源 #
        """关闭资源 #"""
        pass  # 简化版本无需关闭 #


# 工厂方法 #
def create_naga_portal_agent(config_dict: Optional[Dict[str, Any]] = None) -> NagaPortalAgent:
    return NagaPortalAgent()  # 返回实例 #


# 配置校验 #
def validate_agent_config(config_dict: Dict[str, Any]) -> bool:
    return True  # 预留校验，基础骨架总是通过 #


# 依赖 #
def get_agent_dependencies():
    return [
        "httpx>=0.28.1"  # HTTP客户端 #
    ]  # 依赖列表 #


