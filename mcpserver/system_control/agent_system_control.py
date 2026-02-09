from system.config import config  # 统一变量管理 #
from nagaagent_core.vendors.agents import Agent  # 统一代理 #
import json
import subprocess
try:
    import screen_brightness_control as sbc  # 屏幕亮度调节 #
except ImportError:
    sbc = None
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # 直接依赖 #
    from ctypes import cast, POINTER  # 标准库 #
    from comtypes import CLSCTX_ALL  # 直接依赖 #
    import comtypes as comtypes  # COM组件初始化 #
except ImportError:
    AudioUtilities = None

class SystemControlAgent(Agent):
    """系统控制Agent #"""
    name = "SystemControlAgent"  # Agent名称 #
    instructions = "系统控制：执行指令、亮度、音量调节"  # 角色描述 #
    def __init__(self):
        super().__init__(
            name=self.name,
            instructions=self.instructions,
            tools=[],
            model=config.api.model
        )

    async def handle_handoff(self, data: dict) -> str:
        # 使用tool_name参数，与LLM生成的工具调用格式匹配
        action = data.get("tool_name")
        if not action:
            return json.dumps({"status": "error", "message": "缺少tool_name参数", "data": {}}, ensure_ascii=False)
            
        if action == "command":
            command = data.get("command")
            cwd = data.get("cwd", ".")
            
            if not command:
                return json.dumps({"status": "error", "message": "缺少command参数", "data": {}}, ensure_ascii=False)
            
            try:
                # 执行系统指令
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                return json.dumps({
                    "status": "success", 
                    "message": f"指令执行完成，返回码: {result.returncode}", 
                    "data": {
                        "returncode": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr
                    }
                }, ensure_ascii=False)
                
            except subprocess.TimeoutExpired:
                return json.dumps({"status": "error", "message": "指令执行超时", "data": {}}, ensure_ascii=False)
            except Exception as e:
                return json.dumps({"status": "error", "message": f"指令执行失败: {e}", "data": {}}, ensure_ascii=False)
                
        elif action == "brightness":
            value = int(data.get("value", 50))
            if sbc:
                sbc.set_brightness(value)
                return json.dumps(
                    {"status": "success", "message": f"亮度已设置为{value}", "data": {"brightness": value}},
                    ensure_ascii=False)
            else:
                return json.dumps(
                    {"status": "error", "message": "未安装screen_brightness_control库，无法调节亮度", "data": {}},
                    ensure_ascii=False)
                
        elif action == "volume":
            value = int(data.get("value", 50))
            if AudioUtilities:
                try:
                    comtypes.CoInitialize()  # 初始化COM组件 #
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = cast(interface, POINTER(IAudioEndpointVolume))
                    volume.SetMasterVolumeLevelScalar(value / 100, None)
                    return json.dumps(
                        {"status": "success", "message": f"音量已设置为{value}", "data": {"volume": value}},
                        ensure_ascii=False)
                except Exception as e:
                    return json.dumps(
                        {"status": "error", "message": f"音量设置失败: {e}", "data": {}},
                        ensure_ascii=False)
                finally:
                    comtypes.CoUninitialize()  # 清理COM组件 #
            else:
                return json.dumps(
                    {"status": "error", "message": "未安装pycaw库，无法调节音量", "data": {}},
                    ensure_ascii=False)
        else:
            return json.dumps({"status": "error", "message": f"未知操作: {action}", "data": {}}, ensure_ascii=False)


# 工厂函数，用于动态注册系统创建实例
def create_system_control_agent():
    """创建SystemControlAgent实例的工厂函数"""
    return SystemControlAgent()