#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent管理器 - 独立的Agent注册和调用系统
支持从配置文件动态加载Agent定义，提供统一的调用接口
"""

import os
import json
import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AgentManager")

# 屏蔽HTTP库的DEBUG日志
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

@dataclass
class AgentConfig:
    """Agent配置类"""
    id: str  # 模型ID
    name: str  # Agent名称（中文名）
    base_name: str  # 基础名称（英文）
    system_prompt: str  # 系统提示词
    max_output_tokens: int = 40000  # 最大输出token数
    temperature: float = 0.7  # 温度参数
    description: str = ""  # 描述信息
    model_provider: str = "openai"  # 模型提供商
    api_base_url: str = ""  # API基础URL
    api_key: str = ""  # API密钥

@dataclass
class AgentSession:
    """Agent会话类"""
    timestamp: float = field(default_factory=time.time)
    history: List[Dict[str, str]] = field(default_factory=list)
    session_id: str = "default_user_session"

class AgentManager:
    """Agent管理器 - 增强版，支持任务规划和多智能体协作"""
    
    def __init__(self, config_dir: str = None):
        """
        初始化Agent管理器
        
        Args:
            config_dir: Agent配置文件目录（可选，MCP架构下通常不需要）
        """
        self.config_dir = Path(config_dir) if config_dir else None
        self.agents: Dict[str, AgentConfig] = {}
        self.agent_sessions: Dict[str, Dict[str, AgentSession]] = {}
        
        # 任务规划相关 - 现在通过apiserver的task_scheduler处理
        # self.task_planner = None  # 删除重复功能
        # self.task_executor = None  # 删除重复功能
        
        # 从配置文件读取最大历史轮数
        try:
            from system.config import config, AI_NAME
            self.max_history_rounds = config.api.max_history_rounds
        except ImportError:
            self.max_history_rounds = 10  # 默认值
            logger.warning("无法导入配置，使用默认历史轮数设置")
        self.context_ttl_hours = 24  # 上下文TTL（小时）
        self.debug_mode = True
        
        # 只在指定了config_dir时才创建目录和加载配置
        if self.config_dir:
            # 确保配置目录存在
            self.config_dir.mkdir(exist_ok=True)
            # 加载Agent配置
            self._load_agent_configs()
        else:
            logger.info("AgentManager使用MCP架构，跳过外部配置文件加载")
        
        # 启动定期清理任务（只在事件循环中启动）
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._periodic_cleanup())
        except RuntimeError:
            # 没有运行的事件循环，跳过定期清理任务
            pass
        
        # 任务规划器现在通过apiserver的task_scheduler处理
        # self._init_task_planner()  # 删除重复功能
        
        logger.info(f"AgentManager初始化完成，已加载 {len(self.agents)} 个Agent")
    
    def _load_agent_configs(self):
        """从配置文件加载Agent定义"""
        # 检查config_dir是否存在
        if not self.config_dir:
            logger.info("未指定配置文件目录，跳过Agent配置加载")
            return
            
        # 扫描配置文件目录
        config_files = list(self.config_dir.glob("*.json"))
        
        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                
                # 解析Agent配置
                for agent_key, agent_data in config_data.items():
                    if self._validate_agent_config(agent_data):
                        agent_config = AgentConfig(
                            id=agent_data.get('model_id', ''),
                            name=agent_data.get('name', agent_key),
                            base_name=agent_data.get('base_name', agent_key),
                            system_prompt=agent_data.get('system_prompt', f'You are a helpful AI assistant named {agent_data.get("name", agent_key)}.'),
                            max_output_tokens=agent_data.get('max_output_tokens', 40000),
                            temperature=agent_data.get('temperature', 0.7),
                            description=agent_data.get('description', f'Assistant {agent_data.get("name", agent_key)}.'),
                            model_provider=agent_data.get('model_provider', 'openai'),
                            api_base_url=agent_data.get('api_base_url', ''),
                            api_key=agent_data.get('api_key', '')
                        )
                        
                        self.agents[agent_key] = agent_config
                        logger.info(f"已加载Agent: {agent_key} ({agent_config.name})")
                
            except Exception as e:
                logger.error(f"加载配置文件 {config_file} 失败: {e}")
    
    def _validate_agent_config(self, config: Dict[str, Any]) -> bool:
        """验证Agent配置"""
        required_fields = ['model_id', 'name']
        for field in required_fields:
            if field not in config or not config[field]:
                logger.warning(f"Agent配置缺少必需字段: {field}")
                return False
        return True
    
    def get_agent_session_history(self, agent_name: str, session_id: str = 'default_user_session') -> List[Dict[str, str]]:
        """获取Agent会话历史"""
        if agent_name not in self.agent_sessions:
            self.agent_sessions[agent_name] = {}
        
        agent_sessions = self.agent_sessions[agent_name]
        if session_id not in agent_sessions or self._is_context_expired(agent_sessions[session_id].timestamp):
            agent_sessions[session_id] = AgentSession(session_id=session_id)
        
        return agent_sessions[session_id].history
    
    def update_agent_session_history(self, agent_name: str, user_message: str, assistant_message: str, session_id: str = 'default_user_session'):
        """更新Agent会话历史"""
        if agent_name not in self.agent_sessions:
            self.agent_sessions[agent_name] = {}
        
        agent_sessions = self.agent_sessions[agent_name]
        if session_id not in agent_sessions or self._is_context_expired(agent_sessions[session_id].timestamp):
            agent_sessions[session_id] = AgentSession(session_id=session_id)
        
        session_data = agent_sessions[session_id]
        session_data.history.extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message}
        ])
        session_data.timestamp = time.time()
        
        # 限制历史消息数量
        max_messages = self.max_history_rounds * 2
        if len(session_data.history) > max_messages:
            session_data.history = session_data.history[-max_messages:]
    
    def _is_context_expired(self, timestamp: float) -> bool:
        """检查上下文是否过期"""
        return (time.time() - timestamp) > (self.context_ttl_hours * 3600)
    
    async def _periodic_cleanup(self):
        """定期清理过期的会话上下文"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时清理一次
                
                if self.debug_mode:
                    logger.debug("执行定期上下文清理...")
                
                for agent_name, sessions in list(self.agent_sessions.items()):
                    for session_id, session_data in list(sessions.items()):
                        if self._is_context_expired(session_data.timestamp):
                            sessions.pop(session_id, None)
                            if self.debug_mode:
                                logger.debug(f"清理过期上下文: {agent_name}, session {session_id}")
                    
                    if not sessions:
                        self.agent_sessions.pop(agent_name, None)
                        
            except Exception as e:
                logger.error(f"定期清理任务出错: {e}")
    
    def _replace_placeholders(self, text: str, agent_config: AgentConfig) -> str:
        """替换提示词中的占位符，支持Agent配置和环境变量"""
        if not text:
            return ""
        
        processed_text = str(text)
        
        # Agent配置相关的占位符替换
        if agent_config:
            # 基础Agent信息
            processed_text = processed_text.replace("{{AgentName}}", agent_config.name)
            processed_text = processed_text.replace("{{MaidName}}", agent_config.name)
            processed_text = processed_text.replace("{{BaseName}}", agent_config.base_name)
            processed_text = processed_text.replace("{{Description}}", agent_config.description)
            processed_text = processed_text.replace("{{ModelId}}", agent_config.id)
            
            # 配置参数
            processed_text = processed_text.replace("{{Temperature}}", str(agent_config.temperature))
            processed_text = processed_text.replace("{{MaxTokens}}", str(agent_config.max_output_tokens))
            processed_text = processed_text.replace("{{ModelProvider}}", agent_config.model_provider)
        
        # 环境变量占位符替换
        import os
        import re
        
        # 匹配 {{ENV_VAR_NAME}} 格式的环境变量
        env_pattern = r'\{\{([A-Z_][A-Z0-9_]*)\}\}'
        for match in re.finditer(env_pattern, processed_text):
            env_var_name = match.group(1)
            env_value = os.getenv(env_var_name, '')
            processed_text = processed_text.replace(f"{{{{{env_var_name}}}}}", env_value)
        
        # 时间相关占位符
        from datetime import datetime
        now = datetime.now()
        processed_text = processed_text.replace("{{CurrentTime}}", now.strftime("%H:%M:%S"))
        processed_text = processed_text.replace("{{CurrentDate}}", now.strftime("%Y-%m-%d"))
        processed_text = processed_text.replace("{{CurrentDateTime}}", now.strftime("%Y-%m-%d %H:%M:%S"))
        
        return processed_text
    
    def _build_system_message(self, agent_config: AgentConfig) -> Dict[str, str]:
        """构建系统消息，包含Agent的身份、行为、风格等"""
        # 处理系统提示词中的占位符
        processed_system_prompt = self._replace_placeholders(agent_config.system_prompt, agent_config)
        
        return {
            "role": "system",
            "content": processed_system_prompt
        }
    
    def _build_user_message(self, prompt: str, agent_config: AgentConfig) -> Dict[str, str]:
        """构建用户消息，处理用户输入"""
        # 处理用户提示词中的占位符
        processed_prompt = self._replace_placeholders(prompt, agent_config)
        
        return {
            "role": "user",
            "content": processed_prompt
        }
    
    def _build_assistant_message(self, content: str) -> Dict[str, str]:
        """构建助手消息"""
        return {
            "role": "assistant",
            "content": content
        }
    
    def _validate_messages(self, messages: List[Dict[str, str]]) -> bool:
        """验证消息序列的有效性"""
        if not messages:
            return False
        
        # 检查消息格式
        for msg in messages:
            if not isinstance(msg, dict):
                return False
            if 'role' not in msg or 'content' not in msg:
                return False
            if msg['role'] not in ['system', 'user', 'assistant']:
                return False
            if not isinstance(msg['content'], str):
                return False
        
        # 检查系统消息是否在开头
        if messages[0]['role'] != 'system':
            return False
        
        return True

    async def call_agent(self, agent_name: str, prompt: str, session_id: str = None) -> Dict[str, Any]:
        """
        调用指定的Agent
        
        Args:
            agent_name: Agent名称
            prompt: 用户提示词
            session_id: 会话ID
            
        Returns:
            Dict[str, Any]: 调用结果
        """
        # 检查Agent是否存在
        if agent_name not in self.agents:
            available_agents = list(self.agents.keys())
            error_msg = f"请求的Agent '{agent_name}' 未找到或未正确配置。"
            if available_agents:
                error_msg += f" 当前已加载的Agent有: {', '.join(available_agents)}。"
            else:
                error_msg += " 当前没有加载任何Agent。请检查配置文件。"
            error_msg += " 请确认您请求的Agent名称是否准确。"
            
            logger.error(f"Agent调用失败: {error_msg}")
            return {"status": "error", "error": error_msg}
        
        agent_config = self.agents[agent_name]
        
        # 生成会话ID
        if not session_id:
            session_id = f"agent_{agent_config.base_name}_default_user_session"
        
        try:
            # 获取会话历史
            history = self.get_agent_session_history(agent_name, session_id)
            
            # 构建完整的消息序列
            messages = []
            
            # 1. 系统消息：设定Agent的身份、行为、风格等
            system_message = self._build_system_message(agent_config)
            messages.append(system_message)
            
            # 2. 历史消息：保留多轮对话的上下文
            messages.extend(history)
            
            # 3. 当前用户输入：本次要处理的任务内容
            user_message = self._build_user_message(prompt, agent_config)
            messages.append(user_message)
            
            # 验证消息序列
            if not self._validate_messages(messages):
                return {"status": "error", "error": "消息序列格式无效"}
            
            # 记录调试信息
            if self.debug_mode:
                logger.debug(f"Agent调用消息序列:")
                for i, msg in enumerate(messages):
                    logger.debug(f"  [{i}] {msg['role']}: {msg['content'][:100]}...")
            
            # 调用LLM API
            response = await self._call_llm_api(agent_config, messages)
            
            if response.get("status") == "success":
                assistant_response = response.get("result", "")
                
                # 更新会话历史
                self.update_agent_session_history(
                    agent_name, user_message['content'], assistant_response, session_id
                )
                
                return {"status": "success", "result": assistant_response}
            else:
                return response
                
        except Exception as e:
            error_msg = f"调用Agent '{agent_name}' 时发生错误: {str(e)}"
            logger.error(f"Agent调用异常: {error_msg}")
            return {"status": "error", "error": error_msg}
    
    async def _call_llm_api(self, agent_config: AgentConfig, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """调用LLM API，使用Agent配置中的参数"""
        try:
            # 使用新版本的OpenAI API
            from openai import AsyncOpenAI
            
            # 记录调试信息
            if self.debug_mode:
                logger.debug(f"调用LLM API - Agent: {agent_config.name}")
                logger.debug(f"  模型: {agent_config.id}")
                logger.debug(f"  提供商: {agent_config.model_provider}")
                logger.debug(f"  API URL: {agent_config.api_base_url}")
                logger.debug(f"  温度: {agent_config.temperature}")
                logger.debug(f"  最大Token: {agent_config.max_output_tokens}")
                logger.debug(f"  消息数量: {len(messages)}")
            
            # 验证必要的配置参数
            if not agent_config.id:
                return {"status": "error", "error": "Agent配置缺少模型ID"}
            
            if not agent_config.api_key:
                return {"status": "error", "error": "Agent配置缺少API密钥"}
            
            # 创建客户端，使用Agent配置中的参数
            client = AsyncOpenAI(
                api_key=agent_config.api_key,
                base_url=agent_config.api_base_url or "https://api.deepseek.com/v1"
            )
            
            # 准备API调用参数
            api_params = {
                "model": agent_config.id,
                "messages": messages,
                "max_tokens": agent_config.max_output_tokens,
                "temperature": agent_config.temperature,
                "stream": False
            }
            
            # 记录API调用参数（调试模式）
            if self.debug_mode:
                logger.debug(f"API调用参数: {api_params}")
            
            # 调用API
            response = await client.chat.completions.create(**api_params)
            
            # 提取响应内容
            assistant_content = response.choices[0].message.content
            
            # 记录响应信息（调试模式）
            if self.debug_mode:
                usage = response.usage
                logger.debug(f"API响应成功:")
                logger.debug(f"  使用Token: {usage.prompt_tokens} (输入) + {usage.completion_tokens} (输出) = {usage.total_tokens} (总计)")
                logger.debug(f"  响应长度: {len(assistant_content)} 字符")
            
            return {"status": "success", "result": assistant_content}
            
        except Exception as e:
            error_msg = f"LLM API调用失败: {str(e)}"
            logger.error(f"Agent '{agent_config.name}' API调用失败: {error_msg}")
            
            # 记录详细的错误信息（调试模式）
            if self.debug_mode:
                import traceback
                logger.debug(f"详细错误信息:")
                logger.debug(traceback.format_exc())
            
            return {"status": "error", "error": error_msg}
    
    def get_available_agents(self) -> List[Dict[str, Any]]:
        """获取所有可用的Agent列表"""
        return [
            {
                "name": agent_config.name,
                "base_name": agent_config.base_name,
                "description": agent_config.description,
                "model_id": agent_config.id,
                "temperature": agent_config.temperature,
                "max_output_tokens": agent_config.max_output_tokens
            }
            for agent_config in self.agents.values()
        ]
    
    def get_agent_info(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """获取指定Agent的详细信息"""
        if agent_name not in self.agents:
            return None
        
        agent_config = self.agents[agent_name]
        return {
            "name": agent_config.name,
            "base_name": agent_config.base_name,
            "description": agent_config.description,
            "model_id": agent_config.id,
            "temperature": agent_config.temperature,
            "max_output_tokens": agent_config.max_output_tokens,
            "system_prompt": agent_config.system_prompt,
            "model_provider": agent_config.model_provider
        }
    
    def reload_configs(self):
        """重新加载Agent配置"""
        self.agents.clear()
        self._load_agent_configs()
        logger.info("Agent配置已重新加载")
    
    def _register_agent_from_manifest(self, agent_name: str, agent_config: Dict[str, Any]):
        """从manifest注册Agent
        
        Args:
            agent_name: Agent名称
            agent_config: Agent配置字典
        """
        try:
            # 验证配置
            if not self._validate_agent_config(agent_config):
                logger.warning(f"Agent配置验证失败: {agent_name}")
                return False
            
            # 创建AgentConfig对象
            agent_config_obj = AgentConfig(
                id=agent_config.get('model_id', ''),
                name=agent_config.get('name', agent_name),
                base_name=agent_config.get('base_name', agent_name),
                system_prompt=agent_config.get('system_prompt', f'You are a helpful AI assistant named {agent_config.get("name", agent_name)}.'),
                max_output_tokens=agent_config.get('max_output_tokens', 8192),
                temperature=agent_config.get('temperature', 0.7),
                description=agent_config.get('description', f'Assistant {agent_config.get("name", agent_name)}.'),
                model_provider=agent_config.get('model_provider', 'openai'),
                api_base_url=agent_config.get('api_base_url', ''),
                api_key=agent_config.get('api_key', '')
            )
            
            # 注册到agents字典
            self.agents[agent_name] = agent_config_obj
            logger.info(f"已从manifest注册Agent: {agent_name} ({agent_config_obj.name})")
            return True
            
        except Exception as e:
            logger.error(f"从manifest注册Agent失败 {agent_name}: {e}")
            return False
    
    async def call_agent_by_action(self, agent_name: str, action_args: Dict[str, Any]) -> str:
        """根据动作调用Agent
        
        Args:
            agent_name: Agent名称
            action_args: 动作参数，包含action和具体参数
            
        Returns:
            str: Agent执行结果
        """
        try:
            # 检查Agent是否存在
            if agent_name not in self.agents:
                return f"Agent '{agent_name}' 未找到或未正确配置"
            
            agent_config = self.agents[agent_name]
            action = action_args.get('action', '')
            
            # 构建用户提示词
            user_prompt = self._build_action_prompt(action, action_args)
            
            # 调用Agent
            result = await self.call_agent(agent_name, user_prompt)
            
            if result.get("status") == "success":
                return result.get("result", "")
            else:
                return f"Agent调用失败: {result.get('error', '未知错误')}"
                
        except Exception as e:
            logger.error(f"Agent动作调用失败 {agent_name}: {e}")
            return f"Agent动作调用异常: {str(e)}"
    
    def _build_action_prompt(self, action: str, action_args: Dict[str, Any]) -> str:
        """构建动作提示词
        
        Args:
            action: 动作名称
            action_args: 动作参数
            
        Returns:
            str: 构建的提示词
        """
        # 移除不需要的参数
        clean_args = {k: v for k, v in action_args.items() 
                     if k not in ['service_name', 'action']}
        
        # 构建提示词
        if clean_args:
            args_str = ", ".join([f"{k}: {v}" for k, v in clean_args.items()])
            return f"请执行动作 '{action}'，参数: {args_str}"
        else:
            return f"请执行动作 '{action}'"
    
    # 删除重复的任务规划器初始化方法
    # 现在通过apiserver的task_scheduler处理任务规划
    
    async def process_intelligent_task(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        智能任务处理 - 核心方法，通过apiserver的task_scheduler处理
        
        Args:
            query: 用户查询
            context: 上下文信息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        try:
            # 通过apiserver的task_scheduler处理智能任务
            from apiserver.task_scheduler import get_task_scheduler
            task_scheduler = get_task_scheduler()
            
            # 创建任务并调度
            import uuid
            task_id = str(uuid.uuid4())
            
            # 注册任务到调度器
            task_scheduler.task_registry[task_id] = {
                "id": task_id,
                "type": "processor",
                "status": "queued",
                "params": {"query": query},
                "context": context
            }
            
            # 调度并行执行
            tasks = [{
                "type": "processor",
                "params": {"query": query},
                "session_id": context.get("session_id") if context else None
            }]
            
            results = await task_scheduler.schedule_parallel_execution(tasks)
            
            if results and len(results) > 0:
                result = results[0]
                return {
                    "status": "success" if result.get("success") else "error",
                    "result": result.get("result"),
                    "error": result.get("error"),
                    "task_id": task_id
                }
            else:
                return {
                    "status": "error",
                    "error": "任务调度失败"
                }
            
        except Exception as e:
            logger.error(f"智能任务处理失败: {e}")
            # 降级到传统Agent调用
            return await self.call_agent("default", query)

# 全局Agent管理器实例
_AGENT_MANAGER = None

def get_agent_manager() -> AgentManager:
    """获取全局Agent管理器实例"""
    global _AGENT_MANAGER
    if _AGENT_MANAGER is None:
        _AGENT_MANAGER = AgentManager()
    return _AGENT_MANAGER

# 便捷函数
async def call_agent(agent_name: str, prompt: str, session_id: str = None) -> Dict[str, Any]:
    """便捷的Agent调用函数"""
    manager = get_agent_manager()
    return await manager.call_agent(agent_name, prompt, session_id)

def list_agents() -> List[Dict[str, Any]]:
    """便捷的Agent列表获取函数"""
    manager = get_agent_manager()
    return manager.get_available_agents()

def get_agent_info(agent_name: str) -> Optional[Dict[str, Any]]:
    """便捷的Agent信息获取函数"""
    manager = get_agent_manager()
    return manager.get_agent_info(agent_name)

# 智能任务处理函数 - 通过apiserver处理
async def process_intelligent_task(query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """便捷的智能任务处理函数 - 通过apiserver的task_scheduler处理"""
    manager = get_agent_manager()
    return await manager.process_intelligent_task(query, context)

# 任务管理函数 - 通过apiserver的task_scheduler处理
async def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """便捷的任务状态获取函数 - 通过apiserver处理"""
    try:
        from apiserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        return await task_scheduler.get_task_status(task_id)
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        return None

async def get_task_list(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """便捷的任务列表获取函数 - 通过apiserver处理"""
    try:
        from apiserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        return await task_scheduler.get_running_tasks()
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        return []

async def get_execution_stats() -> Dict[str, Any]:
    """便捷的执行统计获取函数 - 通过apiserver处理"""
    try:
        from apiserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        return {
            "total_tasks": len(task_scheduler.task_registry),
            "running_tasks": len([t for t in task_scheduler.task_registry.values() if t.get("status") == "running"]),
            "queued_tasks": len([t for t in task_scheduler.task_registry.values() if t.get("status") == "queued"])
        }
    except Exception as e:
        logger.error(f"获取执行统计失败: {e}")
        return {}

async def cancel_task(task_id: str) -> bool:
    """便捷的任务取消函数 - 通过apiserver处理"""
    try:
        from apiserver.task_scheduler import get_task_scheduler
        task_scheduler = get_task_scheduler()
        if task_id in task_scheduler.task_registry:
            task_scheduler.task_registry[task_id]["status"] = "cancelled"
            return True
        return False
    except Exception as e:
        logger.error(f"取消任务失败: {e}")
        return False
