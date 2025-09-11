# device_switch.py # 设备开关控制MCP工具
import json
import logging
import sys
import os
import time
import threading
from typing import Optional, Dict, Any
from fastmcp import FastMCP

logger = logging.getLogger('DeviceSwitch')

# Windows 控制台 UTF-8 编码修复
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

class MQTTJsonStandardizer:
    """MQTT JSON标准化工具类，确保发送的JSON只包含ASCII字符"""
    
    @staticmethod
    def standardize_device_control(device1: int, device2: int, device3: int) -> str:
        """
        标准化设备控制JSON格式
        返回标准ASCII JSON字符串，确保物联网设备能正确解析
        """
        payload = {
            "device1": int(device1),
            "device2": int(device2), 
            "device3": int(device3),
            "timestamp": int(time.time()),
        }
        
        # 强制使用ASCII编码，移除空格，使用紧凑格式
        return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    
    @staticmethod
    def standardize_status_query() -> str:
        """标准化状态查询JSON格式"""
        payload = {
            "cmd": "status",
            "timestamp": int(time.time()),
            "ver": "1.0"
        }
        return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    
    @staticmethod
    def standardize_heartbeat() -> str:
        """标准化心跳包JSON格式"""
        payload = {
            "cmd": "heartbeat",
            "timestamp": int(time.time()),
            "ver": "1.0"
        }
        return json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
    
    @staticmethod
    def validate_json_format(json_str: str) -> bool:
        """验证JSON格式是否符合标准"""
        try:
            # 尝试解析JSON
            data = json.loads(json_str)
            
            # 检查必要字段
            required_fields = ['cmd', 'timestamp', 'ver']
            for field in required_fields:
                if field not in data:
                    return False
            
            # 检查时间戳是否为整数
            if not isinstance(data['timestamp'], int):
                return False
                
            return True
        except (json.JSONDecodeError, TypeError):
            return False

# 从config模块读取MQTT配置
def load_mqtt_config():
    """从config模块加载MQTT配置"""
    try:
        # 添加项目根目录到路径，以便导入config
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        from system.config import config
        
        # 检查是否启用物联网通讯
        if not config.mqtt.enabled:
            logger.info("物联网通讯功能未启用，跳过初始化")
            return None
            
        return {
            'broker': config.mqtt.broker,
            'port': config.mqtt.port,
            'topic': config.mqtt.topic,
            'client_id': config.mqtt.client_id,
            'username': config.mqtt.username,
            'password': config.mqtt.password
        }
    except ImportError:
        # 兼容旧版本，从config.json读取MQTT配置
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            mqtt_config = config_data.get('mqtt', {})
            
            # 检查是否启用物联网通讯
            if not mqtt_config.get('enabled', False):
                logger.info("物联网通讯功能未启用，跳过初始化")
                return None
            
            return {
                'broker': mqtt_config.get('broker', 'broker.emqx.io'),
                'port': mqtt_config.get('port', 1883),
                'topic': mqtt_config.get('topic', 'device/switch'),
                'client_id': mqtt_config.get('client_id', 'mcp_mqtt_tool'),
                'username': mqtt_config.get('username', ''),
                'password': mqtt_config.get('password', '')
            }
        except Exception as e:
            logger.warning(f"无法加载MQTT配置: {e}")
            return None
    except Exception as e:
        logger.warning(f"无法加载MQTT配置: {e}")
        return None

# 加载MQTT配置
mqtt_config = load_mqtt_config()

# 只有在MQTT配置存在且启用时才导入MQTT相关模块
if mqtt_config:
    try:
        import paho.mqtt.client as mqtt
        MQTT_AVAILABLE = True
    except ImportError:
        logger.warning("paho-mqtt库未安装，物联网通讯功能不可用")
        MQTT_AVAILABLE = False
        mqtt = None
else:
    MQTT_AVAILABLE = False
    mqtt = None

mcp = FastMCP("DeviceSwitch")

class DeviceSwitchManager:
    """设备开关管理器"""
    def __init__(self):
        if not mqtt_config or not MQTT_AVAILABLE:
            self.available = False
            logger.warning("物联网通讯功能不可用，设备开关控制将无法工作")
            return
            
        self.available = True
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_config['client_id'])
        self.connected = False
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.last_message = None
        self._lock = threading.Lock()
        
        # 自动重连设置
        self.reconnect_enabled = True
        self.reconnect_attempt = 0
        self.max_reconnect_attempts = 5  # 改为5次重连
        self.reconnect_delay = 1
        self.max_reconnect_delay = 60
        self.reconnect_thread = None
        self.should_reconnect = False
        
        # 设置用户名密码（如果有）
        if mqtt_config['username'] or mqtt_config['password']:
            self.client.username_pw_set(mqtt_config['username'], mqtt_config['password'])
        
        # 初始化时自动连接物联网通讯（如果配置完整）
        self._init_connection()

    def _init_connection(self):
        """初始化时自动连接物联网通讯"""
        try:
            # 检查物联网通讯配置是否完整
            if not mqtt_config:
                logger.warning("物联网通讯配置缺失，跳过初始化连接")
                return
            
            # 检查必要的配置项
            required_configs = ['broker', 'port', 'topic', 'client_id']
            missing_configs = [config for config in required_configs if not mqtt_config.get(config)]
            
            if missing_configs:
                logger.warning(f"物联网通讯配置不完整，缺少: {missing_configs}，跳过初始化连接")
                return
            
            logger.info("物联网通讯配置完整，开始初始化连接...")
            
            # 尝试连接
            if self.connect():
                logger.info("✅ 物联网模块初始化连接成功")
            else:
                logger.warning("⚠️ 物联网模块初始化连接失败，将在使用时重试")
                
        except Exception as e:
            logger.error(f"物联网模块初始化连接异常: {e}")

    def _on_connect(self, client, userdata, flags, rc, properties=None, *args):
        if rc == 0:
            self.connected = True
            self.reconnect_attempt = 0
            self.reconnect_delay = 1
            logger.info(f"已连接到物联网服务器 {client._host}:{client._port}")
            # 订阅主题以接收设备状态反馈
            client.subscribe(f"{mqtt_config['topic']}/status")
        else:
            self.connected = False
            logger.error(f"物联网模块连接失败，错误代码: {rc}")
            if self.reconnect_enabled:
                self._start_reconnect()

    def _on_disconnect(self, client, userdata, rc, reasonCode=None, properties=None, *args):
        """断开连接回调"""
        self.connected = False
        logger.warning(f"物联网模块连接断开，错误代码: {rc}")
        
        if rc != 0 and self.reconnect_enabled:
            self._start_reconnect()

    def _on_message(self, client, userdata, msg, *args):
        """接收设备状态反馈"""
        try:
            if isinstance(msg.payload, bytes):
                try:
                    payload = msg.payload.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        payload = msg.payload.decode('gbk')
                    except UnicodeDecodeError:
                        payload = msg.payload.decode('latin-1')
            else:
                payload = str(msg.payload)
            
            self.last_message = {
                "topic": msg.topic,
                "payload": payload,
                "timestamp": time.time()
            }
            logger.info(f"收到设备状态: {payload}")
        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    def _start_reconnect(self):
        """启动自动重连"""
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            return
            
        self.should_reconnect = True
        self.reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self.reconnect_thread.start()
        logger.info("启动物联网模块自动重连线程")

    def _reconnect_loop(self):
        """重连循环"""
        while self.should_reconnect and self.reconnect_attempt < self.max_reconnect_attempts:
            try:
                logger.info(f"物联网模块尝试重连 ({self.reconnect_attempt + 1}/{self.max_reconnect_attempts})，延迟 {self.reconnect_delay} 秒")
                time.sleep(self.reconnect_delay)
                
                self.client.reconnect()
                
                for _ in range(10):
                    if self.connected:
                        logger.info("物联网模块重连成功")
                        self.reconnect_attempt = 0  # 重置重连计数器
                        self.reconnect_delay = 1  # 重置延迟时间
                        return
                    time.sleep(0.5)
                
                self.reconnect_attempt += 1
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                
            except Exception as e:
                logger.error(f"物联网模块重连失败: {e}")
                self.reconnect_attempt += 1
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
        
        if self.reconnect_attempt >= self.max_reconnect_attempts:
            logger.error("物联网模块达到最大重连次数，停止重连")
            self.should_reconnect = False

    def stop_reconnect(self):
        """停止自动重连"""
        self.should_reconnect = False
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=1)

    def connect(self):
        """连接到MQTT服务器"""
        if not self.available:
            return False
            
        if not self.connected:
            try:
                # 阿里云IoT Hub特殊处理
                if 'iothub.aliyuncs.com' in mqtt_config['broker']:
                    # 阿里云IoT Hub使用用户名密码认证
                    if mqtt_config.get('username') and mqtt_config.get('password'):
                        self.client.username_pw_set(mqtt_config['username'], mqtt_config['password'])
                        logger.info("使用阿里云IoT Hub用户名密码认证")
                    else:
                        logger.warning("阿里云IoT Hub需要用户名和密码认证")
                else:
                    # 其他MQTT服务器使用用户名密码认证
                    if mqtt_config.get('username'):
                        self.client.username_pw_set(mqtt_config['username'], mqtt_config.get('password', ''))
                
                self.client.connect(mqtt_config['broker'], mqtt_config['port'], 60)
                self.client.loop_start()
                
                for _ in range(10):
                    if self.connected:
                        return True
                    time.sleep(0.5)
                
                if not self.connected and self.reconnect_enabled:
                    logger.warning("初始连接失败，启动自动重连")
                    self._start_reconnect()
                
                return False
            except Exception as e:
                logger.error(f"物联网模块连接失败: {e}")
                if self.reconnect_enabled:
                    self._start_reconnect()
                return False
        return True

    def switch_devices(self, device1: int, device2: int, device3: int):
        """控制三个设备的开关"""
        if not self.available:
            return False, "物联网模块功能不可用"
            
        with self._lock:
            # 检查是否已连接，如果未连接则尝试连接（保底方案）
            if not self.connected:
                logger.info("物联网模块未连接，尝试连接...")
                if not self.connect():
                    return False, "物联网模块连接失败"
            else:
                logger.debug("物联网模块已连接，跳过连接步骤")
            
            try:
                # 使用标准化工具创建JSON
                payload_str = MQTTJsonStandardizer.standardize_device_control(device1, device2, device3)
                payload_bytes = payload_str.encode('ascii')
                
                # 记录发送的标准化JSON
                logger.info(f"发送标准化物联网消息: {payload_str}")
                
                result = self.client.publish(mqtt_config['topic'], payload_bytes)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"已发送设备控制命令: device1={device1}, device2={device2}, device3={device3}")
                    return True, "命令已发送"
                else:
                    return False, f"发送失败，错误代码: {result.rc}"
                    
            except Exception as e:
                logger.error(f"发送设备控制命令失败: {e}")
                return False, f"发送失败: {str(e)}"

    def get_last_status(self):
        """获取最后收到的设备状态"""
        if not self.available:
            return None
            
        if self.last_message:
            return self.last_message
        return None

    def cleanup(self):
        """清理资源"""
        if not self.available:
            return
            
        try:
            self.stop_reconnect()
            
            if self.connected:
                self.client.disconnect()
                self.client.loop_stop()
                self.connected = False
                logger.info("物联网模块连接已断开")
                
        except Exception as e:
            logger.error(f"清理物联网模块连接时出错: {e}")

    def get_connection_status(self):
        """获取连接状态信息"""
        if not self.available:
            return {
                "available": False,
                "connected": False,
                "reconnect_enabled": False,
                "reconnect_attempt": 0
            }
            
        return {
            "available": True,
            "connected": self.connected,
            "reconnect_enabled": self.reconnect_enabled,
            "reconnect_attempt": self.reconnect_attempt,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "reconnect_delay": self.reconnect_delay
        }

# 全局设备管理器实例
device_manager = DeviceSwitchManager()

@mcp.tool()
def switch_devices(device1: int, device2: int, device3: int) -> dict:
    """控制三个设备的开关"""
    try:
        if not device_manager.available:
            return {
                "success": False,
                "message": "物联网模块功能未启用或配置缺失",
                "data": {"device1": device1, "device2": device2, "device3": device3}
            }
        
        if device1 not in [0, 1] or device2 not in [0, 1] or device3 not in [0, 1]:
            return {
                "success": False,
                "message": "设备状态必须是0（关闭）或1（开启）",
                "data": {"device1": device1, "device2": device2, "device3": device3}
            }
        
        success, message = device_manager.switch_devices(device1, device2, device3)
        
        return {
            "success": success,
            "message": message,
            "data": {
                "device1": device1,
                "device2": device2,
                "device3": device3,
                "payload": {"device1": device1, "device2": device2, "device3": device3}
            }
        }
        
    except Exception as e:
        logger.error(f"设备控制失败: {e}")
        return {
            "success": False,
            "message": f"设备控制异常: {str(e)}",
            "data": {"device1": device1, "device2": device2, "device3": device3}
        }

@mcp.tool()
def get_device_status() -> dict:
    """获取设备状态信息"""
    try:
        if not device_manager.available:
            return {
                "success": False,
                "message": "物联网模块功能未启用或配置缺失",
                "data": {}
            }
            
        status = device_manager.get_last_status()
        
        if status:
            return {
                "success": True,
                "message": "获取设备状态成功",
                "data": status
            }
        else:
            return {
                "success": False,
                "message": "暂无设备状态信息",
                "data": {}
            }
            
    except Exception as e:
        logger.error(f"获取设备状态失败: {e}")
        return {
            "success": False,
            "message": f"获取设备状态异常: {str(e)}",
            "data": {}
        }

@mcp.tool()
def connect_mqtt(broker: str = None, port: int = None) -> dict:
    """连接到MQTT服务器"""
    try:
        if not device_manager.available:
            return {
                "success": False,
                "message": "物联网模块功能未启用或配置缺失",
                "data": {}
            }
        
        if broker or port:
            global mqtt_config
            if broker:
                mqtt_config['broker'] = broker
            if port:
                mqtt_config['port'] = port
            
        success = device_manager.connect()
        
        if success:
            return {
                "success": True,
                "message": f"已连接到物联网服务器 {mqtt_config['broker']}:{mqtt_config['port']}",
                "data": {"broker": mqtt_config['broker'], "port": mqtt_config['port']}
            }
        else:
            return {
                "success": False,
                "message": f"连接物联网服务器失败 {mqtt_config['broker']}:{mqtt_config['port']}",
                "data": {"broker": mqtt_config['broker'], "port": mqtt_config['port']}
            }
            
    except Exception as e:
        logger.error(f"物联网模块连接异常: {e}")
        return {
            "success": False,
            "message": f"物联网模块连接异常: {str(e)}",
            "data": {}
        }

@mcp.tool()
def get_connection_status() -> dict:
    """获取MQTT连接状态信息"""
    try:
        status = device_manager.get_connection_status()
        
        return {
            "success": True,
            "message": "获取连接状态成功",
            "data": status
        }
        
    except Exception as e:
        logger.error(f"获取连接状态失败: {e}")
        return {
            "success": False,
            "message": f"获取连接状态异常: {str(e)}",
            "data": {}
        }

@mcp.tool()
def stop_reconnect() -> dict:
    """停止自动重连"""
    try:
        device_manager.stop_reconnect()
        
        return {
            "success": True,
            "message": "已停止自动重连",
            "data": {}
        }
        
    except Exception as e:
        logger.error(f"停止重连失败: {e}")
        return {
            "success": False,
            "message": f"停止重连异常: {str(e)}",
            "data": {}
        }

# 注册程序退出时的清理函数
import atexit
atexit.register(device_manager.cleanup)

if __name__ == "__main__":
    mcp.run(transport="stdio") 