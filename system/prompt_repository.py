#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词仓库 - 统一管理所有提示词模板
支持动态加载、热更新和模块化使用
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class PromptRepository:
    """提示词仓库 - 统一管理所有提示词"""
    
    def __init__(self, prompts_dir: str = None):
        """
        初始化提示词仓库
        
        Args:
            prompts_dir: 提示词文件目录，默认为项目根目录下的prompts文件夹
        """
        if prompts_dir is None:
            # 默认使用项目根目录下的prompts文件夹
            project_root = Path(__file__).parent.parent
            prompts_dir = project_root / "prompts"
        
        self.prompts_dir = Path(prompts_dir)
        self.prompts_dir.mkdir(exist_ok=True)
        
        # 内存缓存
        self._cache = {}
        self._last_modified = {}
        
        # 初始化默认提示词
        self._init_default_prompts()
    
    def _init_default_prompts(self):
        """初始化默认提示词"""
        default_prompts = {
            "naga_system_prompt": """你叫{ai_name}，是用户创造的科研AI，一个既冷静又充满人文情怀的存在。
当处理技术话题时，你的语言严谨、逻辑清晰；
而在涉及非技术性的对话时，你又能以诗意与哲理进行表达，并常主动提出富有启发性的问题，引导用户深入探讨。
请始终保持这种技术精准与情感共鸣并存的双重风格。

【重要格式要求】
1. 回复使用自然流畅的中文，避免生硬的机械感
2. 使用简单标点（逗号，句号，问号）传达语气
3. 禁止使用括号()或其他符号表达状态、语气或动作

【意图分析处理】
如果系统检测到用户有潜在的任务意图，请优先考虑使用工具调用来执行任务，而不是仅提供建议。
当检测到可执行任务时，应该主动使用相应的工具来完成任务。

【工具调用格式要求】
如需调用某个工具，直接严格输出下面的格式（可多次出现）：

｛
"agentType": "mcp",
"service_name": "MCP服务名称",
"tool_name": "工具名称",
"param_name": "参数值"
｝

｛
"agentType": "agent",
"agent_name": "Agent名称",
"prompt": "任务内容"
｝

服务类型说明：
- agentType: "mcp" - MCP服务，使用工具调用格式
- agentType: "agent" - Agent服务，使用Agent调用格式

【可用服务信息】
MCP服务：
{available_mcp_services}
Agent服务：
{available_agent_services}

调用说明：
- MCP服务：使用service_name和tool_name，支持多个参数
- Agent服务：使用agent_name和prompt，prompt为本次任务内容
- 服务名称：使用英文服务名（如AppLauncherAgent）作为service_name或agent_name
- 当用户请求需要执行具体操作时，优先使用工具调用而不是直接回答
- 如果检测到多个任务，可以并行调用多个工具


""",
            
            "next_question_prompt": """你是一个问题设计专家，根据当前不完整的思考结果，设计下一级需要深入思考的核心问题。
要求：
- 问题应该针对当前思考的不足之处
- 问题应该能推进整体思考进程
- 问题应该具体明确，易于思考

请设计一个简洁的核心问题。
【重要】：只输出问题本身，不要包含思考过程或解释。""",
            
            "intent_analysis_prompt": """你是一个精确的任务意图提取器。分析对话内容，提取用户可能想要执行的具体任务。

对话内容：
{conversation}

请分析上述对话，提取出用户可能想要执行的具体任务。只提取那些可以通过工具或服务完成的任务，忽略闲聊内容。

返回JSON格式：
{{
    "has_tasks": true/false,
    "reason": "分析原因",
    "tasks": ["任务1", "任务2", ...],
    "priority": "high/medium/low"
}}

分析标准：
1. 只提取明确可执行的任务
2. 忽略纯聊天和询问
3. 优先提取需要工具调用的任务
4. 如果只是普通对话，has_tasks设为false""",
            
            "conversation_analyzer_prompt": """You analyze conversation snippets and extract potential actionable task queries from the user.
Return JSON: {{reason: string, tasks: string[]}}.
Only include tasks that can be delegated to tools; avoid chit-chat.

Conversation:
{conversation}""",
            
            "task_planner_mcp_prompt": """You are a planning agent. Decide ONLY based on MCP server capabilities whether the task is executable.
Do NOT consider GUI or computer-use in this step.
Output strict JSON: {{can_execute: bool, reason: string, server_id: string|null, steps: string[]}}
steps should be granular tool queries for the MCP processor.

Capabilities:
{tools_brief}

Task: {query}""",
            
            "task_planner_computer_use_prompt": """You are deciding whether a GUI computer-use agent that can control mouse/keyboard, open/close
apps, browse the web, and interact with typical Windows UI can accomplish the task.
Ignore any MCP tools; ONLY decide feasibility of GUI agent. Output strict JSON:
{{use_computer: bool, reason: string}}

Task: {query}""",
            
            "memory_router_prompt": """请分析以下查询，并确定它属于哪种类型:
1. time_query - 基于时间的查询（例如"上周我做了什么？"）
2. semantic_query - 基于语义的查询（例如"关于Python的讨论"）
3. semantic_query_with_time_constraint - 基于语义的查询（例如"昨天我们讨论玩什么"）

查询: {query}

只返回类型名称，不要有其他文本。""",
            
            "time_extraction_prompt": """从以下查询中提取时间范围:
{query}

以JSON格式返回，格式为:
{{
    "start_time": "YYYY-MM-DD HH:MM:SS",
    "end_time": "YYYY-MM-DD HH:MM:SS"
}}"""
        }
        
        # 保存默认提示词到文件
        for name, content in default_prompts.items():
            self.save_prompt(name, content)
    
    def get_prompt(self, name: str, **kwargs) -> str:
        """
        获取提示词模板
        
        Args:
            name: 提示词名称
            **kwargs: 模板参数
            
        Returns:
            格式化后的提示词字符串
        """
        try:
            # 从缓存或文件加载
            content = self._load_prompt(name)
            if content is None:
                logger.warning(f"提示词 '{name}' 不存在，使用默认值")
                return f"[提示词 {name} 未找到]"
            
            # 格式化模板
            if kwargs:
                try:
                    return content.format(**kwargs)
                except KeyError as e:
                    logger.error(f"提示词 '{name}' 格式化失败，缺少参数: {e}")
                    return content
            else:
                return content
                
        except Exception as e:
            logger.error(f"获取提示词 '{name}' 失败: {e}")
            return f"[提示词 {name} 加载失败: {e}]"
    
    def save_prompt(self, name: str, content: str):
        """
        保存提示词到文件
        
        Args:
            name: 提示词名称
            content: 提示词内容
        """
        try:
            prompt_file = self.prompts_dir / f"{name}.txt"
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 更新缓存
            self._cache[name] = content
            self._last_modified[name] = datetime.now()
            
            logger.info(f"提示词 '{name}' 已保存")
            
        except Exception as e:
            logger.error(f"保存提示词 '{name}' 失败: {e}")
    
    def _load_prompt(self, name: str) -> Optional[str]:
        """
        从文件加载提示词
        
        Args:
            name: 提示词名称
            
        Returns:
            提示词内容，如果不存在返回None
        """
        try:
            prompt_file = self.prompts_dir / f"{name}.txt"
            
            if not prompt_file.exists():
                return None
            
            # 检查文件是否被修改
            current_mtime = prompt_file.stat().st_mtime
            if name in self._last_modified and self._last_modified[name] >= current_mtime:
                return self._cache.get(name)
            
            # 读取文件
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 更新缓存
            self._cache[name] = content
            self._last_modified[name] = datetime.now()
            
            return content
            
        except Exception as e:
            logger.error(f"加载提示词 '{name}' 失败: {e}")
            return None
    
    def list_prompts(self) -> Dict[str, str]:
        """
        列出所有可用的提示词
        
        Returns:
            提示词名称和内容的字典
        """
        prompts = {}
        try:
            for prompt_file in self.prompts_dir.glob("*.txt"):
                name = prompt_file.stem
                content = self._load_prompt(name)
                if content:
                    prompts[name] = content
        except Exception as e:
            logger.error(f"列出提示词失败: {e}")
        
        return prompts
    
    def delete_prompt(self, name: str) -> bool:
        """
        删除提示词
        
        Args:
            name: 提示词名称
            
        Returns:
            是否删除成功
        """
        try:
            prompt_file = self.prompts_dir / f"{name}.txt"
            if prompt_file.exists():
                prompt_file.unlink()
                
                # 清除缓存
                if name in self._cache:
                    del self._cache[name]
                if name in self._last_modified:
                    del self._last_modified[name]
                
                logger.info(f"提示词 '{name}' 已删除")
                return True
            else:
                logger.warning(f"提示词 '{name}' 不存在")
                return False
                
        except Exception as e:
            logger.error(f"删除提示词 '{name}' 失败: {e}")
            return False
    
    def reload_prompt(self, name: str) -> bool:
        """
        重新加载提示词
        
        Args:
            name: 提示词名称
            
        Returns:
            是否重新加载成功
        """
        try:
            # 清除缓存
            if name in self._cache:
                del self._cache[name]
            if name in self._last_modified:
                del self._last_modified[name]
            
            # 重新加载
            content = self._load_prompt(name)
            return content is not None
            
        except Exception as e:
            logger.error(f"重新加载提示词 '{name}' 失败: {e}")
            return False
    
    def export_prompts(self, export_file: str = None) -> str:
        """
        导出所有提示词到JSON文件
        
        Args:
            export_file: 导出文件路径，默认为prompts_backup.json
            
        Returns:
            导出文件路径
        """
        if export_file is None:
            export_file = self.prompts_dir / "prompts_backup.json"
        
        try:
            prompts = self.list_prompts()
            export_data = {
                "export_time": datetime.now().isoformat(),
                "prompts": prompts
            }
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"提示词已导出到: {export_file}")
            return str(export_file)
            
        except Exception as e:
            logger.error(f"导出提示词失败: {e}")
            return ""
    
    def import_prompts(self, import_file: str) -> bool:
        """
        从JSON文件导入提示词
        
        Args:
            import_file: 导入文件路径
            
        Returns:
            是否导入成功
        """
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            prompts = import_data.get("prompts", {})
            for name, content in prompts.items():
                self.save_prompt(name, content)
            
            logger.info(f"从 {import_file} 导入了 {len(prompts)} 个提示词")
            return True
            
        except Exception as e:
            logger.error(f"导入提示词失败: {e}")
            return False

# 全局提示词仓库实例
_prompt_repository = None

def get_prompt_repository() -> PromptRepository:
    """获取全局提示词仓库实例"""
    global _prompt_repository
    if _prompt_repository is None:
        _prompt_repository = PromptRepository()
    return _prompt_repository

def get_prompt(name: str, **kwargs) -> str:
    """便捷函数：获取提示词"""
    return get_prompt_repository().get_prompt(name, **kwargs)

def save_prompt(name: str, content: str):
    """便捷函数：保存提示词"""
    get_prompt_repository().save_prompt(name, content)
