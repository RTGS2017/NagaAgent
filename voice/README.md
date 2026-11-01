# NagaAgent 语音服务 🗣️

基于 Edge TTS 与 NagaModel 网关的 OpenAI 兼容语音合成服务。当前桌面端由前端按句排队，经 API Server 的 `/tts/speech` 代理合成，并使用浏览器音频能力串行播放 MP3 或 WAV。

## 🚀 核心功能特性

### 基础TTS功能
- **OpenAI兼容接口**：`/v1/audio/speech`，请求结构和行为与OpenAI类似
- **支持多种语音**：将OpenAI语音（alloy, echo, fable, onyx, nova, shimmer）映射到`edge-tts`语音
- **多音频格式**：本地接口支持 mp3、opus、aac、flac、wav 等格式；桌面会话固定请求浏览器兼容的 mp3
- **可调节语速**：使用 `tts.default_speed` 控制语速
- **可选直接指定edge-tts语音**：既可用OpenAI语音映射，也可直接指定任意edge-tts语音
- **网关与本地回退**：启用 NagaModel 网关时使用角色绑定声线，未启用时使用本地 Edge TTS

### 🎯 渐进式 TTS 播放
- **智能分句**：流式回复遇到中英文句末标点时立即进入待播队列
- **工具调用清理**：收到 `content_clean` 后停止原始片段，并使用清理后的自然语言重建语音队列
- **严格串行**：每句音频播放结束后再合成和播放下一句，避免后一句中断前一句
- **格式兼容**：MP3 保持原容器；网关返回 raw PCM 时由代理包装为 WAV
- **会话覆盖**：主会话、Naga Core 干员和 OpenClaw 干员共用同一套语音开关和队列

### 🔄 架构优化
- **避免重复处理**：移除voice模块中的复杂标点符号分割算法
- **统一设置源**：设置页“语音合成模型”开关与聊天输入栏扬声器按钮都写入 `system.voice_enabled`
- **依赖 API Server**：浏览器只请求同源 `/tts/speech`，由后端选择 NagaModel 或本地 Edge TTS
- **前后端分工**：后端负责合成和媒体类型归一化，前端负责分句、队列及播放状态

## 📋 快速开始

### 前置条件

- **Python 3.11**：项目要求 Python 3.11
- **依赖包**：推荐在项目根目录运行 `uv sync`
- **ffmpeg**（可选）：音频格式转换需要，只用mp3可不装

### 配置说明

语音服务配置在 `config.json` 文件的 `tts` 部分：

```json
{
  "system": {
    "voice_enabled": true  // 启用语音功能
  },
  "tts": {
    "api_key": "your_api_key_here",
    "port": 5048,
    "default_voice": "zh-CN-XiaoxiaoNeural",
    "default_format": "mp3",
    "default_speed": 1.0,
    "default_language": "zh-CN",
    "remove_filter": false,
    "expand_api": true,
    "require_api_key": false
  }
}
```

### 启动方式

#### 方式1：通过NagaAgent主程序自动启动
```bash
python main.py
```
主程序会自动启动语音服务。

#### 方式2：独立启动语音服务
```bash
# 启动HTTP服务器
python voice/output/start_voice_service.py

# 检查依赖
python voice/output/start_voice_service.py --check-deps

# 自定义端口
python voice/output/start_voice_service.py --port 8080
```

#### 方式3：直接启动服务器
```bash
# HTTP服务器
python voice/output/server.py
```

## 🎵 流式TTS播放功能

### 处理流程
1. **对话流到达前端** → `MessageView` 接收 `content` / `content_clean` / `round_end`
2. **智能分句** → `TtsSentenceBuffer` 输出完整句子并保留未结束尾部
3. **TTS 代理** → 前端调用 API Server `/tts/speech`
4. **引擎选择** → 登录且启用网关时走 NagaModel，否则走本地 `127.0.0.1:5048`
5. **格式归一化** → 后端保留 MP3/WAV 容器，必要时把 raw PCM 包装为 WAV
6. **串行播放** → 前端等待当前句播放完成，再处理下一句

### 智能分句算法
```python
def _check_and_queue_sentences(self):
    """检查并加入句子队列 - 简化版本，依赖apiserver的预处理"""
    if not self.text_buffer:
        return
        
    # 简单的句子结束检测（apiserver已经处理过复杂的标点分割）
    sentence_endings = ["。", "！", "？", "；", ".", "!", "?", ";"]
    
    for ending in sentence_endings:
        if ending in self.text_buffer:
            # 找到句子结束位置
            end_pos = self.text_buffer.find(ending) + 1
            sentence = self.text_buffer[:end_pos]
            
            # 检查句子是否有效
            if sentence.strip():
                # 加入句子队列
                self.sentence_queue.put(sentence)
                # 启动音频合成线程...
```

### 使用方法

#### 基本使用
```python
from voice.output.voice_integration import get_voice_integration

# 获取语音集成实例
voice_integration = get_voice_integration()

# 播放完整文本
voice_integration.receive_final_text("你好，这是一个测试。")

# 播放文本片段（支持智能分句）
voice_integration.receive_text_chunk("这是一个很长的文本，")
voice_integration.receive_text_chunk("它会被自动分割成多个句子进行播放。")
```

#### 流式处理
```python
# 流式文本输入
voice_integration.receive_text_chunk("开始生成回复...")
voice_integration.receive_text_chunk("正在处理您的问题。")
voice_integration.receive_text_chunk("这是最终的答案。")

# 完成处理
voice_integration.finish_processing()
```

## 🔧 服务状态检查

### 测试TTS功能
```bash
curl -X POST http://127.0.0.1:5048/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "input": "你好，这是一段语音测试。",
    "voice": "zh-CN-XiaoxiaoNeural",
    "response_format": "mp3",
    "speed": 1.0
  }' \
  --output test_speech.mp3
```

通过 API Server 测试与桌面端相同的代理链路：

```bash
curl -X POST http://127.0.0.1:8000/tts/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"代理链路测试。","voice":"zh-CN-XiaoxiaoNeural","response_format":"mp3","speed":1.0}' \
  --output test_proxy_speech.mp3
```

## 📁 文件存储结构

```
logs/audio_temp/
├── tts_audio_[时间戳]_[索引].mp3  # 音频文件命名格式
├── README.md                      # 目录说明文件
└── ...                           # 其他音频文件
```

## ⚙️ 配置参数说明

### 关键配置项
- `voice_enabled`: 是否启用语音功能
- `port`: TTS服务端口
- `default_voice`: 默认语音
- `default_format`: 音频格式（mp3, wav, opus等）
- `default_speed`: 播放速度（0.1-3.0）
- `remove_filter`: 是否移除文本过滤器

### 分句配置
- **句子结束标点**：`[。？！；\.\?\!\;]`
- **最小句子长度**：5个字符
- **短句合并**：长度≤5且不包含引号的句子会被合并
- **最大缓冲区**：50个文本片段

### 并发配置
- **最大并发任务数**：3个
- **信号量控制**：防止过多并发请求
- **超时设置**：30秒

## 🚀 性能优势

### 实时响应
- apiserver实时处理LLM流式输出
- 工具调用检测和文本分流实时进行
- voice模块实时接收普通文本并生成音频
- 音频生成和播放并行处理

### 内存效率
- 直接播放内存中的音频数据
- 减少临时文件创建和删除
- 降低磁盘I/O开销

### 用户体验
- 语音播放与文本显示同步
- 工具调用不影响普通文本的语音播放
- 不阻塞前端界面响应

## 🔧 故障排除

### 常见问题
1. **TTS 服务未启动**：确认主程序日志中 5048 端口已就绪，或运行 `python voice/output/start_voice_service.py`
2. **语音功能被禁用**：设置页开关和聊天栏扬声器按钮现在共用 `system.voice_enabled`
3. **只有音乐和启动播报**：检查 `/tts/speech` 是否返回 200；这两类静态音频不经过 TTS 服务
4. **登录模式无声**：检查 NagaModel 登录状态、积分与后端 TTS 代理日志；401 会自动刷新并重试一次
5. **本地模式无声**：确认 Edge TTS 所需网络可用，且 `tts.default_voice` 是有效声线

### 音频播放失败排查
1. 使用上方两个 `curl` 命令分别验证本地合成服务和 API 代理。

2. 检查音频设备：
   - Windows：检查系统音量
   - macOS：检查音频输出设备
   - Linux：检查音频驱动

3. 查看日志：
   ```bash
   tail -f ~/.naga/logs/nagaagent.log
   ```

## 📝 更新日志

### 5.1.4（2026-07-15）- 桌面会话 TTS 修复
- 设置页与聊天栏语音开关统一为 `system.voice_enabled`
- `content_clean` 改为使用清理后的正文重建队列，不再丢失日常对话
- 主会话、Naga Core 与 OpenClaw 干员会话统一接入 TTS
- 播放队列等待当前音频结束，按响应媒体类型兼容 MP3 与 WAV

### v3.1.0 - 流式TTS重构
- ✅ 参考的流式TTS实现
- ✅ 标点符号分割算法优化
- ✅ 括号计数避免错误分割
- ✅ 内存中直接播放音频数据
- ✅ 工具调用分流处理
- ✅ 与apiserver完美集成
- ✅ 异步处理不阻塞前端

### v3.0.2 - 并发音频合成
- ✅ 新增并发音频合成功能
- ✅ 本地文件存储管理
- ✅ 按顺序播放音频文件
- ✅ 自动文件清理机制
- ✅ 调试模式支持

### v3.0.1 - pygame播放
- ✅ 新增pygame后台直接播放
- ✅ 智能分句功能
- ✅ 并发播放支持
- ✅ 移除系统播放器依赖
- ✅ 简化播放逻辑

### v3.0.0 - 基础功能
- 🔄 系统播放器播放
- 🔄 临时文件创建
- 🔄 基础TTS功能

## 🎙️ 语音示例

[试听语音样例及全部Edge TTS语音](https://tts.travisvn.com/)

## 🎤 语音输入服务

### 概述
语音输入服务是 NagaAgent 的独立语音识别模块，基于 MoeChat 的 Silero VAD 技术和本地 FunASR 引擎，提供高质量的语音转文本功能。

### 核心特性
- **本地麦克风采集**：实时音频采集与处理
- **Silero VAD 端点检测**：准确的语音活动检测
- **本地 FunASR 识别**：基于 ModelScope 的离线语音识别
- **HTTP REST API**：OpenAI 兼容的转写接口
- **WebSocket 实时识别**：实时 VAD + ASR 推送
- **设备管理**：自动检测和选择音频设备

### 快速启动
```bash
# 安装依赖
pip install -r voice/input/requirements.txt

# 启动服务
python voice/input/start_input_service.py

# 检查依赖
python voice/input/start_input_service.py --check-deps
```

### 主要接口
- `POST /v1/audio/transcriptions` - 文件转写
- `POST /v1/audio/transcriptions_b64` - Base64 转写
- `GET /devices` - 音频设备列表
- `POST /control/listen/start|stop` - 本地监听控制
- `ws://127.0.0.1:5060/v1/audio/asr_ws` - 实时识别

### 详细文档
更多信息请参考：[voice/input/README.md](input/README.md)

## 📄 许可证

本项目采用GNU GPL v3.0协议，仅限个人用途。如需企业或非个人用途，请联系 tts@travisvn.com
