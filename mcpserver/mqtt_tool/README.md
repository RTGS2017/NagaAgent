# MQTT设备开关控制工具

## 概述

MQTT设备开关控制工具是一个基于MCP（Model Context Protocol）的智能设备控制系统，支持通过MQTT协议远程控制两个设备的开关状态。适用于智能家居、物联网设备管理等场景。

## 功能特性

- ✅ **双设备控制**: 支持同时控制两个独立设备
- ✅ **MQTT通信**: 基于标准MQTT协议，支持多种MQTT服务器
- ✅ **自动重连**: 智能自动重连机制，支持指数退避算法
- ✅ **编码处理**: 自动处理UTF-8/GBK/Latin-1编码转换
- ✅ **状态反馈**: 实时接收设备状态反馈
- ✅ **配置管理**: 通过config.json统一管理配置
- ✅ **错误处理**: 完善的错误处理和日志记录
- ✅ **中文友好**: 完全支持中文界面和提示

## 文件结构

```
mqtt_tool/
├── device_switch.py          # MCP设备开关控制工具
├── test_device_switch.py     # 功能测试脚本
├── test_complete_system.py   # 完整系统测试
├── demo_reconnect.py         # 重连功能演示
├── README.md                 # 使用说明
└── requirements.txt          # 依赖包列表
```

## 快速开始

### 1. 安装依赖

```bash
pip install paho-mqtt mcp
```

### 2. 配置MQTT

在`config.json`中配置MQTT参数：

```json
{
  "mqtt": {
    "enabled": true,
    "broker": "broker.emqx.io",
    "port": 1883,
    "topic": "device/switch",
    "client_id": "mcp_device_switch",
    "username": "",
    "password": ""
  }
}
```

### 3. 测试功能

运行测试脚本验证功能：

```bash
cd mqtt_tool
python test_device_switch.py
```

### 4. 使用MCP工具

通过MCP调用设备控制功能：

```python
# 开启设备1，关闭设备2
result = switch_devices(1, 0)

# 关闭设备1，开启设备2  
result = switch_devices(0, 1)

# 关闭所有设备
result = switch_devices(0, 0)
```

## 配置说明

### MQTT配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | false | 是否启用MQTT功能 |
| `broker` | string | broker.emqx.io | MQTT服务器地址 |
| `port` | integer | 1883 | MQTT服务器端口 |
| `topic` | string | device/switch | MQTT主题 |
| `client_id` | string | mcp_device_switch | 客户端ID |
| `username` | string | "" | 用户名（可选） |
| `password` | string | "" | 密码（可选） |

### 支持的MQTT服务器

- **公共测试服务器**: broker.emqx.io (推荐用于测试)
- **本地服务器**: localhost 或 127.0.0.1
- **云服务器**: 阿里云、腾讯云等MQTT服务

## 设备端配置

### 硬件要求

- 支持MQTT的设备（ESP32、Arduino、树莓派等）
- 2个继电器模块（或GPIO控制设备）
- 1个状态指示LED

### 消息格式

设备端需要订阅`device/switch`主题，并发布状态反馈到`device/switch/status`主题。

### 控制消息格式

```json
{
  "device1": 0,      // 设备1状态：0=关闭，1=开启
  "device2": 1,      // 设备2状态：0=关闭，1=开启
  "timestamp": 1234567890.123
}
```

### 状态反馈格式

```json
{
  "device1": 0,      // 设备1当前状态
  "device2": 1,      // 设备2当前状态
  "timestamp": 1234567890.123
}
```

## 消息格式

### 控制消息格式

```json
{
  "device1": 0,      // 设备1状态：0=关闭，1=开启
  "device2": 1,      // 设备2状态：0=关闭，1=开启
  "timestamp": 1234567890.123
}
```

### 状态反馈格式

```json
{
  "device1": 0,      // 设备1当前状态
  "device2": 1,      // 设备2当前状态
  "timestamp": 1234567890.123
}
```

## API接口

### switch_devices(device1, device2)

控制两个设备的开关状态。

**参数:**
- `device1` (int): 设备1状态，0=关闭，1=开启
- `device2` (int): 设备2状态，0=关闭，1=开启

**返回:**
```json
{
  "success": true,
  "message": "命令已发送",
  "data": {
    "device1": 1,
    "device2": 0,
    "payload": {"device1": 1, "device2": 0}
  }
}
```

### get_device_status()

获取设备状态信息。

**返回:**
```json
{
  "success": true,
  "message": "获取设备状态成功",
  "data": {
    "topic": "device/switch/status",
    "payload": "{\"device1\":0,\"device2\":1,\"timestamp\":1234567890.123}",
    "timestamp": 1234567890.123
  }
}
```

### connect_mqtt(broker, port)

连接到MQTT服务器。

**参数:**
- `broker` (str, 可选): MQTT服务器地址
- `port` (int, 可选): MQTT服务器端口

**返回:**
```json
{
  "success": true,
  "message": "已连接到MQTT服务器 broker.emqx.io:1883",
  "data": {
    "broker": "broker.emqx.io",
    "port": 1883
  }
}
```

### get_connection_status()

获取MQTT连接状态信息。

**返回:**
```json
{
  "success": true,
  "message": "获取连接状态成功",
  "data": {
    "available": true,
    "connected": true,
    "reconnect_enabled": true,
    "reconnect_attempt": 0,
    "max_reconnect_attempts": 10,
    "reconnect_delay": 1
  }
}
```

### stop_reconnect()

停止自动重连功能。

**返回:**
```json
{
  "success": true,
  "message": "已停止自动重连",
  "data": {}
}
```

## 故障排除

### 常见问题

1. **MQTT连接失败**
   - 检查网络连接
   - 验证MQTT服务器地址和端口
   - 确认防火墙设置
   - 系统会自动尝试重连，最多10次

2. **设备无响应**
   - 检查ESP32是否正常连接WiFi
   - 验证MQTT主题配置
   - 查看ESP32串口输出
   - 使用`get_connection_status()`检查连接状态

3. **配置加载失败**
   - 检查config.json格式是否正确
   - 确认MQTT功能已启用
   - 验证配置文件路径

4. **编码问题**
   - 系统自动处理UTF-8/GBK/Latin-1编码转换
   - 如果仍有编码问题，检查消息内容格式

5. **自动重连问题**
   - 使用`get_connection_status()`查看重连状态
   - 使用`stop_reconnect()`停止自动重连
   - 重连延迟会从1秒逐渐增加到60秒

### 调试方法

1. **启用详细日志**
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **检查MQTT连接状态**
   ```python
   from mqtt_tool.device_switch import device_manager
   print(f"MQTT可用: {device_manager.available}")
   print(f"连接状态: {device_manager.connected}")
   ```

3. **测试MQTT服务器**
   ```bash
   # 使用mosquitto_pub测试
   mosquitto_pub -h broker.emqx.io -t "device/switch" -m '{"device1":1,"device2":0}'
   ```

## 扩展功能

### 添加更多设备

修改ESP32代码中的设备数量：

```python
# 添加更多设备引脚
DEVICE3_PIN = 19
device3_relay = machine.Pin(DEVICE3_PIN, machine.Pin.OUT)

# 扩展消息处理
if "device3" in data:
    device_states["device3"] = int(data["device3"])
    control_device(device3_relay, device_states["device3"])
```

### 自定义MQTT主题

在config.json中修改主题：

```json
{
  "mqtt": {
    "topic": "myhome/devices"
  }
}
```

### 添加认证

配置MQTT用户名和密码：

```json
{
  "mqtt": {
    "username": "your_username",
    "password": "your_password"
  }
}
```

## 安全注意事项

1. **网络安全**: 在生产环境中使用加密的MQTT连接（TLS/SSL）
2. **认证**: 配置MQTT用户名和密码
3. **访问控制**: 限制MQTT主题的访问权限
4. **设备安全**: 确保ESP32代码的安全性

## 更新日志

### v1.0.0 (2024-01-01)
- 初始版本发布
- 支持双设备控制
- 基于MCP协议
- 完整的错误处理

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 联系方式

如有问题或建议，请通过以下方式联系：
- 提交GitHub Issue
- 发送邮件至项目维护者 