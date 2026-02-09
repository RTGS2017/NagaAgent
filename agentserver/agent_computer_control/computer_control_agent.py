"""
电脑控制主Agent - 协调各个组件，提供统一的电脑控制接口
"""

import logging
from typing import Dict, Any
import json

from .computer_use_adapter import ComputerUseAdapter
from .visual_analyzer import VisualAnalyzer
from .action_executor import ActionExecutor

# 配置日志
logger = logging.getLogger(__name__)

class ComputerControlAgent:
    """电脑控制主Agent，负责协调各个组件"""
    
    def __init__(self):
        """初始化电脑控制Agent"""
        self.adapter = ComputerUseAdapter()
        self.analyzer = VisualAnalyzer()
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
            elif action == "click_ai":
                return await self._handle_click_ai(target, parameters)
            elif action == "type":
                return await self._handle_type(target, parameters)
            elif action == "screenshot":
                return await self._handle_screenshot(target, parameters)
            elif action == "find_element":
                return await self._handle_find_element(target, parameters)
            elif action == "locate_ai":
                return await self._handle_locate_ai(target, parameters)
            elif action == "automate_task":
                return await self._handle_automate_task(target, parameters)
            elif action == "coordinate_info":
                return await self._handle_coordinate_info(target, parameters)
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
        """处理点击任务，支持AI定位和多种坐标格式"""
        try:
            # 检查是否使用AI定位
            use_ai_location = parameters.get("use_ai", False)
            ai_description = parameters.get("ai_description", target)
            
            if use_ai_location and ai_description:
                # 使用AI定位进行点击
                success = await self.adapter.click_with_ai_location(ai_description, parameters.get("button", "left"))
                
                if success:
                    return json.dumps({
                        "success": True,
                        "message": f"AI定位点击成功: {ai_description}",
                        "data": {"method": "ai_location", "target": ai_description}
                    }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "success": False,
                        "error": "AI定位失败",
                        "message": f"AI定位点击失败: {ai_description}"
                    }, ensure_ascii=False)
            else:
                # 使用传统方式执行点击
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
            # 直接调用电脑控制适配器执行自然语言指令
            exec_result = await self.adapter.run_instruction(target)
            success = bool(exec_result.get("success")) if isinstance(exec_result, dict) else False
            return json.dumps({
                "success": success,
                "message": "任务执行完成" if success else exec_result.get("error", "任务执行失败"),
                "data": exec_result
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
    
    async def _handle_click_ai(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理AI定位点击任务"""
        try:
            # 使用AI定位进行点击
            success = await self.adapter.click_with_ai_location(target, parameters.get("button", "left"))
            
            if success:
                return json.dumps({
                    "success": True,
                    "message": f"AI定位点击成功: {target}",
                    "data": {"method": "ai_location", "target": target}
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": "AI定位失败",
                    "message": f"AI定位点击失败: {target}"
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"AI定位点击失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_locate_ai(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理AI定位任务"""
        try:
            # 获取屏幕截图
            screenshot = await self.adapter.take_screenshot()
            if not screenshot:
                return json.dumps({
                    "success": False,
                    "error": "截图失败",
                    "message": "无法获取屏幕截图"
                }, ensure_ascii=False)
            
            # 使用AI定位元素
            location = await self.analyzer.locate_element_with_ai(
                target, 
                screenshot, 
                self.adapter.screen_width, 
                self.adapter.screen_height
            )
            
            if location:
                x, y = location
                return json.dumps({
                    "success": True,
                    "message": f"AI定位成功: {target}",
                    "data": {
                        "target": target,
                        "coordinates": {"x": x, "y": y},
                        "method": "ai_location"
                    }
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "success": False,
                    "error": "AI定位失败",
                    "message": f"无法定位元素: {target}"
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"AI定位失败: {str(e)}"
            }, ensure_ascii=False)
    
    async def _handle_coordinate_info(self, target: str, parameters: Dict[str, Any]) -> str:
        """处理坐标系统信息查询"""
        try:
            # 获取坐标系统信息
            coordinate_info = self.adapter.get_coordinate_info()
            
            return json.dumps({
                "success": True,
                "message": "坐标系统信息获取成功",
                "data": coordinate_info
            }, ensure_ascii=False)
            
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
                "message": f"获取坐标系统信息失败: {str(e)}"
            }, ensure_ascii=False)
    
    def get_status(self) -> Dict[str, Any]:
        """获取电脑控制状态"""
        return {
            "agent_name": "ComputerControlAgent",
            "version": "2.0.0",  # 升级版本号
            "status": "running",
            "capabilities": self.get_capabilities(),
            "components": {
                "adapter": "ComputerUseAdapter",
                "analyzer": "VisualAnalyzer", 
                "planner": "TaskPlanner",
                "executor": "ActionExecutor"
            },
            "upgrades": [
                "AI坐标定位",
                "坐标标准化系统",
                "多格式坐标支持",
                "智能元素定位"
            ]
        }
