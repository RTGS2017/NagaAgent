# NagaAgent 4.0

![NagaAgent Logo](https://img.shields.io/badge/NagaAgent-4.0-blue?style=for-the-badge&logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)

![Star History](https://img.shields.io/github/stars/Xxiii8322766509/NagaAgent?style=social)![Forks](https://img.shields.io/github/forks/Xxiii8322766509/NagaAgent?style=social)![Issues](https://img.shields.io/github/issues/Xxiii8322766509/NagaAgent)![Pull Requests](https://img.shields.io/github/issues-pr/Xxiii8322766509/NagaAgent)
![UI 预览](ui/img/README.jpg)
---

→[教程视频及免配置一键运行整合包获取链接](https://www.pylindex.top/naga)←
---

## 简介

NagaAgent 是一个功能丰富的智能对话助手系统，具有以下特色：

### 核心功能
- **智能对话系统**：支持流式对话和工具调用循环
- **多Agent协作**：基于博弈论的智能任务调度
- **知识图谱记忆**：GRAG系统支持长期记忆和智能检索
- **完整语音交互**：实时语音输入输出处理
- **现代化的界面**：PyQt5 GUI + Live2D虚拟形象
- **系统托盘集成**：后台运行和快捷操作

###  技术架构
- **多服务并行**：API服务器(8000)、Agent服务器(8001)、MCP服务器(8003)、TTS服务器(5048)
- **模块化设计**：各服务独立运行，支持热插拔
- **快配置驱动**：实时配置热更新，无需重启
- **多平台支持**：Windows、macOS、Linux

###  技术栈
- Python 3.11 + PyQt5 + FastAPI
- Neo4j图数据库 + GRAG知识图谱
- MCP (Model Context Protocol) 工具调用
- OpenAI兼容API + 多种LLM服务商支持  

---

## 非一键包部署运行教程

### 环境要求
- Python 3.11（你总不能连这东西都不会安装以及配置吧？）
- 可选：uv工具（加速依赖安装）

### 快速开始
#### 安装必备软件（Windows）
- Git
```bash
#Win11可直接通过以下命令安装Git
winget install Git.Git
#Linux
sudo apt-get install git
#Mac
brew install git
```

- UV（可选）
```bash
#通过python安装uv（win）
pip install uv
#Mac与Linux请从github发布页自行安装
```
#### 克隆代码
新建文件夹到任意路径（最好不要有中文）
然后在此文件夹内右击打开cmd
运行以下命令
```bash
git clone https://github.com/Xxiii8322766509/NagaAgent.git
```
克隆完成后在NagaAgent根目录下打开cmd（推荐powershall）
#### 1. 初始化项目
```bash
# 使用 setup.py 自动初始化
python setup.py

# 或使用 setup.sh (Linux/macOS)
./setup.sh

# 或使用 setup.bat (Windows)
setup.bat
```

初始化脚本会自动：
- 检测Python版本
- 创建虚拟环境
- 安装依赖包
- 复制配置文件模板
- 打开配置文件供编辑

##### 手动进行
```bash
# 无uv
python -m venv .venv
# linux/Mac OS
source .venv/bin/activate
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt

# 使用uv
uv sync
```

#### 2. 配置API密钥
编辑 `config.json` 文件，配置您的LLM API信息：
```json
{
  "api": {
    "api_key": "你的api_key",
    "base_url": "模型服务商OPENAI API端点",
    "model": "模型名称"
  }
}
```

#### 3. 启动应用
注意：请在虚拟环境中运行Naga以保证稳定（如果您未安装uv）
```bash
# 使用启动脚本
./start.sh          # Linux/macOS
start.bat           # Windows


# 或直接运行
# linux/Mac OS
source .venv/bin/activate
# Windows
.\.venv\Scripts\activate
python main.py
# uv（无需虚拟环境）
uv run main.py
```
如何检测自己是否在虚拟环境？
在命令行前有（.venv）即可
### 可选配置

#### 启用知识图谱记忆
在您的 `config.json` 中配置Neo4j数据库：
```json
{
  "grag": {
    "enabled": true,
    "neo4j_uri": "neo4j://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_password": "your-password"
  }
}
```

#### 启用语音功能
```json
{
  "system": {
    "voice_enabled": true
  },
  "tts": {
    "port": 5048
  }
}
```

### 以下可以解决您可能遗漏的方面

#### 常见问题
1. **Python版本不兼容**：确保使用Python 3.11
2. **端口被占用**：检查8000、8001、8003、5048等端口是否可用，或更改为其他端口
3. **依赖安装失败**：尝试使用uv工具重新安装
4. **Neo4j连接失败**：确保Neo4j服务正在运行
5. **如果还有其他问题，请来到交流群询问，请附上log**

#### 系统检测
```bash
# 运行系统环境检测
python main.py --check-env

# 快速检测
python main.py --quick-check
```

---

## 许可证

[Nagaagent License](LICENSE)

## 贡献

欢迎提交Issue和Pull Request！

### 构建
```bash
python build.py
```

<div align="center">

---

**⭐ 如果这个项目对您有帮助，请考虑给我们一个 Star！**

</div>
