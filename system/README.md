# NagaAgent 系统环境检测器

## 🎯 功能概述

更新后的系统环境检测器现在支持：

- ✅ **自动环境配置**：首次运行时自动创建Python 3.11虚拟环境
- ✅ **智能依赖管理**：依赖由 requirements.txt 统一管理，从虚拟环境引入
- ✅ **全面环境检测**：检测Python版本、虚拟环境、依赖包、系统资源等
- ✅ **修复建议**：提供详细的问题修复指导

## 🚀 使用方法

### 1. 首次运行自动配置
```bash
# 自动检测并配置环境（推荐首次使用）
python system/system_checker.py --auto-setup
```

### 2. 常规环境检测
```bash
# 完整环境检测
python system/system_checker.py

# 强制重新检测（忽略缓存）
python system/system_checker.py --force

# 快速检测（仅核心项）
python system/system_checker.py --quick
```

### 3. 在代码中使用
```python
from system.system_checker import SystemChecker, run_system_check

# 创建检测器实例
checker = SystemChecker()

# 运行完整检测（支持自动配置）
success = run_system_check(auto_setup=True)

# 手动检测
results = checker.check_all()
```

## 🔧 自动配置功能

### 首次运行流程：
1. **检测Python 3.11**：自动查找系统中的Python 3.11
2. **下载Python 3.11**：如果未找到，自动下载并安装（仅Windows）
3. **创建虚拟环境**：使用Python 3.11创建`venv`目录
4. **安装依赖**：`pip install -r requirements.txt`

### 镜像源配置：
- 清华大学镜像：`https://pypi.tuna.tsinghua.edu.cn/simple/`
- 阿里云镜像：`https://mirrors.aliyun.com/pypi/simple/`
- 豆瓣镜像：`https://pypi.douban.com/simple/`
- 官方源：`https://pypi.org/simple/`

## 📋 检测项目

### 核心检测：
- ✅ Python版本（推荐3.11+）
- ✅ 虚拟环境状态
- ✅ 核心依赖包（与 requirements.txt 一致：fastapi, openai 等）
- ✅ 配置文件完整性

### 可选检测：
- 🔍 可选依赖包（音频、视觉、网络等）
- 🔍 系统资源（内存、CPU、磁盘）
- 🔍 端口可用性
- 🔍 Neo4j连接
- 🔍 环境变量

## 🛠️ 修复建议

检测器会自动提供修复建议：

### Python版本问题：
```bash
# 推荐使用Python 3.11
py -3.11 -m venv venv
```

### 虚拟环境问题：
```bash
# 激活虚拟环境
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

### 依赖安装问题：
```bash
pip install -r requirements.txt
# 或使用镜像: pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt
```

## 📁 目录结构

```
NagaAgent3.1/
├── system/
│   ├── system_checker.py    # 系统检测器
│   └── README.md            # 使用说明
├── venv/                    # 虚拟环境（自动创建）
├── requirements.txt         # 依赖文件
├── config.json             # 配置文件
└── pyproject.toml          # 项目配置
```

## 🔄 更新日志

### v2.0.0 (2025-01-XX)
- ✅ 新增自动环境配置功能
- ✅ 支持Python 3.11自动下载和安装
- ✅ 集成镜像源加速安装
- ✅ 更新依赖检测逻辑（基于 requirements.txt）
- ✅ 优化错误提示和修复建议
- ✅ 支持首次运行自动配置
- ✅ 移除GPU检测功能（不需要）
- ✅ 修复编码问题，支持中文环境

### v1.0.0 (2025-10-04)
- ✅ 基础环境检测功能
- ✅ 依赖包检测
- ✅ 系统资源检测
- ✅ 配置文件检测

## 💡 使用建议

1. **首次使用**：运行 `python system/system_checker.py --auto-setup`
2. **日常检测**：运行 `python system/system_checker.py`
3. **问题排查**：运行 `python system/system_checker.py --force`
4. **快速检查**：运行 `python system/system_checker.py --quick`

## 🐛 故障排除

### 常见问题：

1. **Python 3.11未找到**
   - 自动下载功能仅支持Windows
   - Linux/Mac请手动安装Python 3.11

2. **网络连接问题**
   - 检测器会自动尝试多个镜像源
   - 如果所有镜像源都失败，会尝试官方源

3. **权限问题**
   - 确保有足够的文件读写权限
   - Windows可能需要管理员权限

4. **虚拟环境问题**
   - 确保虚拟环境路径正确
   - 检查Python解释器路径

## 📞 技术支持

如果遇到问题，请：
1. 运行 `python system/system_checker.py --force` 获取详细错误信息
2. 检查系统资源是否充足
3. 确认网络连接正常
4. 查看修复建议并按照指导操作
