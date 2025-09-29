#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Server配置文件
"""

# Agent Server配置
AGENT_SERVER_HOST = "0.0.0.0"
AGENT_SERVER_PORT = 8001

# 任务配置
MAX_CONCURRENT_TASKS = 10
TASK_TIMEOUT = 300  # 5分钟

# 意图分析配置
INTENT_ANALYSIS_ENABLED = True
INTENT_ANALYSIS_TIMEOUT = 30  # 30秒

# 任务去重配置
DEDUP_ENABLED = True
DEDUP_SIMILARITY_THRESHOLD = 0.8

# 日志配置
LOG_LEVEL = "INFO"
LOG_FILE = "logs/agent_server.log"
