#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Server配置文件 - 重构版
提供客观、实用的配置管理
"""

from dataclasses import dataclass
from typing import Optional

# ============ 服务器配置 ============

# 从主配置读取端口
try:
    from system.config import get_server_port
    AGENT_SERVER_PORT = get_server_port("agent_server")
except ImportError:
    AGENT_SERVER_PORT = 8001  # 回退默认值

# ============ 任务调度器配置 ============

@dataclass
class TaskSchedulerConfig:
    """任务调度器配置"""
    # 记忆管理阈值
    max_steps: int = 15                    # 最大保存步骤数
    compression_threshold: int = 7          # 压缩触发阈值
    keep_last_steps: int = 4               # 压缩后保留的详细步骤数
    
    # 显示相关阈值
    key_facts_compression_limit: int = 5    # 压缩提示中的关键事实数量
    key_facts_summary_limit: int = 10       # 摘要中的关键事实数量
    compressed_memory_summary_limit: int = 3 # 任务摘要中的压缩记忆数量
    compressed_memory_global_limit: int = 2  # 全局摘要中的压缩记忆数量
    key_findings_display_limit: int = 3     # 关键发现显示数量
    failed_attempts_display_limit: int = 3  # 失败尝试显示数量
    
    # 输出长度限制
    output_summary_length: int = 256        # 关键事实中的输出摘要长度
    step_output_display_length: int = 512   # 步骤显示中的输出长度
    
    # 性能配置
    enable_auto_compression: bool = True    # 是否启用自动压缩
    compression_timeout: int = 30           # 压缩超时时间（秒）
    max_compression_retries: int = 3        # 最大压缩重试次数

# 默认任务调度器配置实例
DEFAULT_TASK_SCHEDULER_CONFIG = TaskSchedulerConfig()

# ============ OpenClaw 配置 ============

@dataclass
class OpenClawConfig:
    """OpenClaw 集成配置

    官方文档: https://docs.openclaw.ai/
    """
    # Gateway 连接 - 默认端口是 18789
    gateway_url: str = "http://localhost:18789"
    # 认证 token (对应 gateway.auth.token 或 gateway.auth.password)
    token: Optional[str] = None
    # 请求超时时间（秒）
    timeout: int = 120

    # 默认参数
    default_model: Optional[str] = None         # 默认模型
    default_channel: str = "last"               # 默认消息通道

    # 功能开关
    enabled: bool = True                        # 是否启用 OpenClaw 集成

# 默认 OpenClaw 配置实例
DEFAULT_OPENCLAW_CONFIG = OpenClawConfig()

# ============ 全局配置管理 ============

@dataclass
class AgentServerConfig:
    """Agent服务器全局配置"""
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = None

    # 子模块配置
    task_scheduler: TaskSchedulerConfig = None
    openclaw: OpenClawConfig = None

    # 日志配置
    log_level: str = "INFO"
    enable_debug_logs: bool = False

    def __post_init__(self):
        # 设置默认端口
        if self.port is None:
            self.port = AGENT_SERVER_PORT

        # 设置默认子配置
        if self.task_scheduler is None:
            self.task_scheduler = DEFAULT_TASK_SCHEDULER_CONFIG
        if self.openclaw is None:
            self.openclaw = DEFAULT_OPENCLAW_CONFIG

# 全局配置实例
config = AgentServerConfig()

# ============ 配置访问函数 ============

def get_task_scheduler_config() -> TaskSchedulerConfig:
    """获取任务调度器配置"""
    return config.task_scheduler

def get_openclaw_config() -> OpenClawConfig:
    """获取 OpenClaw 配置"""
    return config.openclaw

def update_config(**kwargs):
    """更新配置"""
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
        else:
            raise ValueError(f"未知配置项: {key}")

# ============ 向后兼容 ============

# 保持向后兼容的配置常量
AGENT_SERVER_HOST = config.host
AGENT_SERVER_PORT = config.port
