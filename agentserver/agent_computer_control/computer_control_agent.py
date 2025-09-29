"""
电脑控制主Agent - 协调各个组件，提供统一的电脑控制接口
"""

import asyncio
import logging
from typing import Dict, Any, Optional
import json

from .computer_use_adapter import ComputerUseAdapter
from .visual_analyzer import VisualAnalyzer
from .task_planner import TaskPlanner, TaskStep
from .action_executor import ActionExecutor, ActionResult

# 配置日志
logger = logging.getLogger(__name__)

class ComputerControlAgent:
    """电脑控制主Agent，负责协调各个组件"""
    
    def __init__(self):
        """初始化电脑控制Agent"""
        self.adapter = ComputerUseAdapter()
        self.analyzer = VisualAnalyzer()
        self.planner = TaskPlanner()
        self.executor = ActionExecutor(
            computer_adapter=self.adapter,
            visual_analyzer=self.analyzer
        )
        
        logger.info("电脑控制Agent初始化完成")
    
    async def handle_handoff(self, task: dict) -> str:
        """处理电脑控制任务"""
        try:
            logger.info(f"收到电脑控制任务: {task}")
            
            # 解析任务参数
            action = task.get("action", "")
            target = task.get("target", "")
            parameters = task.get("parameters", {})
            
            # 根据动作类型处理
            if action == "click":
                return await self._handle_click(target, parameters)
            elif action == "type":
                return await self._handle_type(target, parameters)
            elif action == "screenshot":
                return await self._handle_screenshot(target, parameters)
            elif action == "find_element":
                return await self._handle_find_element(target, parameters)
            elif action == "automate_task":
                return await self._handle_automate_task(target, parameters)
            else:
                return await self._handle_generic_task(action, target, parameters)
                
        except Exception as e:
            logger.error(f"处理电脑控制任务失败: {e}")
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"任务处理失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_click(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理点击任务"""
        try:
            # 构建点击动作
            action = {
                "action": "click",
                "target": target,
                "parameters": parameters
            }
            
            # 执行点击
            result = await self.executor.execute_action(action)
            
            if result.success:
                return json.dumps({
                    "success": True,
                    "message": f"成功点击: {target}",
                    "data": result.data
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"点击操作失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_type(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理输入任务"""
        try:
            # 构建输入动作
            action = {
                "action": "type",
                "target": target,
                "parameters": parameters
            }
            
            # 执行输入
            result = await self.executor.execute_action(action)
            
            if result.success:
                return json.dumps({
                    "success": True,
                    "message": f"成功输入: {target}",
                    "data": result.data
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"输入操作失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_screenshot(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理截图任务"""
        try:
            # 构建截图动作
            action = {
                "action": "screenshot",
                "target": target,
                "parameters": parameters
            }
            
            # 执行截图
            result = await self.executor.execute_action(action)
            
            if result.success:
                return json.dumps({
                    "success": True,
                    "message": f"截图成功: {target}",
                    "data": result.data
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"截图操作失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_find_element(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理元素查找任务"""
        try:
            # 构建查找动作
            action = {
                "action": "find_element",
                "target": target,
                "parameters": parameters
            }
            
            # 执行查找
            result = await self.executor.execute_action(action)
            
            if result.success:
                return json.dumps({
                    "success": True,
                    "message": f"找到元素: {target}",
                    "data": result.data
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"元素查找失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_automate_task(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理自动化任务"""
        try:
            logger.info(f"开始自动化任务: {target}")
            
            # 规划任务步骤
            steps = await self.planner.plan_task(target)
            if not steps:
                return json.dumps({
                    "success": False,
                    "error": "任务规划失败",
                    "message": "无法规划任务步骤"
                }, ensure_ascii=False)
            
            # 优化步骤
            optimized_steps = await self.planner.optimize_steps(steps)
            
            # 执行步骤序列
            results = await self.executor.execute_step_sequence(optimized_steps)
            
            # 统计结果
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            
            return json.dumps({
                "success": success_count > 0,
                "message": f"自动化任务完成: {success_count}/{total_count} 步骤成功",
                "data": {
                    "total_steps": total_count,
                    "successful_steps": success_count,
                    "failed_steps": total_count - success_count,
                    "results": [
                        {
                            "success": r.success,
                            "message": r.message,
                            "error": r.error
                        } for r in results
                    ]
                }
            }, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"自动化任务失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_generic_task(self, action: str, target: str, parameters: Dict[str, Any]) -> str:
        """处理通用任务"""
        try:
            # 构建通用动作
            action_dict = {
                "action": action,
                "target": target,
                "parameters": parameters
            }
            
            # 执行动作
            result = await self.executor.execute_action(action_dict)
            
            if result.success:
                return json.dumps({
                    "success": True,
                    "message": f"任务执行成功: {action} - {target}",
                    "data": result.data
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.error,
                    "message": result.message
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"通用任务执行失败: {str(e)}"
            }, ensure_ascii=False)
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取电脑控制能力"""
        return {
            "enabled": True,
            "adapter": self.adapter.is_available(),
            "analyzer": self.analyzer.is_available(),
            "planner": self.planner.is_available(),
            "executor": self.executor.is_available(),
            "capabilities": [
                "鼠标点击",
                "键盘输入",
                "屏幕截图",
                "元素查找",
                "任务自动化",
                "视觉分析"
            ]
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取电脑控制状态"""
        return {
            "agent_name": "ComputerControlAgent",
            "version": "1.0.0",
            "status": "running",
            "capabilities": self.get_capabilities(),
            "components": {
                "adapter": "ComputerUseAdapter",
                "analyzer": "VisualAnalyzer", 
                "planner": "TaskPlanner",
                "executor": "ActionExecutor"
            }
        }
