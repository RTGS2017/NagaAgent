# agent_mqtt_tool.py # 设备开关控制Agent，仅保留开关控制功能
import json
import time
from nagaagent_core.vendors.agents import Agent  # 统一代理 #

# 导入设备开关工具
try:
    from mqtt_tool.device_switch import device_manager, MQTTJsonStandardizer
except Exception as e:
    print(f"导入设备开关工具失败: {e}")

class AgentMqttTool(Agent):
    name = "agent_mqtt_tool"  # Agent名称
    instructions = "设备开关控制MCP Agent，仅支持通过物联网模块控制三个设备的开关状态"  # 角色描述
    def __init__(self):
        super().__init__(
            name=self.name,
            instructions=self.instructions,
            tools=[],
            model="device-switch-mcp"
        )
        print("✅ agent_mqtt_tool初始化完成")

    def _create_standardized_response(self, success: bool, message: str, data: dict) -> str:
        """创建标准化的响应JSON"""
        response = {
            "success": success,
            "message": message,
            "data": data,
            "timestamp": int(time.time()),
            "format": "standardized"
        }
        return json.dumps(response, ensure_ascii=True, separators=(',', ':'))

    async def handle_handoff(self, data: dict) -> str:
        """只处理设备启停控制命令"""
        try:
            tool_name = data.get("tool_name")
            if tool_name != "设备启停控制":
                return self._create_standardized_response(
                    False, 
                    "仅支持设备启停控制操作", 
                    {}
                )
            
            # 获取设备参数
            device1 = data.get("device1")
            device2 = data.get("device2")
            device3 = data.get("device3")
            
            # 检查参数是否存在
            if device1 is None or device2 is None or device3 is None:
                return self._create_standardized_response(
                    False,
                    "设备启停控制操作需要device1、device2和device3参数",
                    {"received_data": data}
                )
            
            # 验证参数类型和范围
            try:
                device1 = int(device1)
                device2 = int(device2)
                device3 = int(device3)
            except (ValueError, TypeError):
                return self._create_standardized_response(
                    False,
                    "设备状态必须是整数（0或1）",
                    {"received_data": data}
                )
            
            # 验证参数范围
            if device1 not in [0, 1] or device2 not in [0, 1] or device3 not in [0, 1]:
                return self._create_standardized_response(
                    False,
                    "设备状态必须是0（关闭）或1（开启）",
                    {"device1": device1, "device2": device2, "device3": device3}
                )
            
            # 调用设备开关工具
            success, message = device_manager.switch_devices(device1, device2, device3)
            
            # 创建标准化的响应数据
            response_data = {
                "device1": device1,
                "device2": device2,
                "device3": device3,
                "mqtt_payload": MQTTJsonStandardizer.standardize_device_control(device1, device2, device3)
            }
            
            return self._create_standardized_response(success, message, response_data)
            
        except Exception as e:
            return self._create_standardized_response(
                False,
                f"设备控制异常: {str(e)}",
                {}
            )

def create_mqtt_tool_agent():
    """创建agent_mqtt_tool实例"""
    return AgentMqttTool() 