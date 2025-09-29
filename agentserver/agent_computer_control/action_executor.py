"""
动作执行器 - 执行具体的鼠标键盘操作
提供安全、可靠的动作执行功能
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

# 配置日志
logger = logging.getLogger(__name__)

class ActionType(Enum):
    """动作类型枚举"""
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    SCROLL = "scroll"
    DRAG = "drag"
    WAIT = "wait"
    FIND_ELEMENT = "find_element"
    ANALYZE = "analyze"

@dataclass
class ActionResult:
    """动作执行结果"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class ActionExecutor:
    """动作执行器，执行具体的鼠标键盘操作"""
    
    def __init__(self, computer_adapter=None, visual_analyzer=None):
        """初始化动作执行器"""
        self.computer_adapter = computer_adapter
        self.visual_analyzer = visual_analyzer
        self.execution_history = []
        self.safety_mode = True
        self.max_retry_count = 3
    
    async def execute_action(self, action: Dict[str, Any]) -> ActionResult:
        """执行具体动作"""
        try:
            action_type = action.get("action", "").lower()
            target = action.get("target", "")
            parameters = action.get("parameters", {})
            
            logger.info(f"执行动作: {action_type}, 目标: {target}")
            
            # 安全检查
            if self.safety_mode and not self._is_safe_action(action_type, target):
                return ActionResult(
                    success=False,
                    message="动作被安全模式阻止",
                    error="不安全动作"
                )
            
            # 根据动作类型执行
            if action_type == ActionType.CLICK.value:
                return await self._execute_click(target, parameters)
            elif action_type == ActionType.TYPE.value:
                return await self._execute_type(target, parameters)
            elif action_type == ActionType.SCREENSHOT.value:
                return await self._execute_screenshot(target, parameters)
            elif action_type == ActionType.SCROLL.value:
                return await self._execute_scroll(target, parameters)
            elif action_type == ActionType.DRAG.value:
                return await self._execute_drag(target, parameters)
            elif action_type == ActionType.WAIT.value:
                return await self._execute_wait(target, parameters)
            elif action_type == ActionType.FIND_ELEMENT.value:
                return await self._execute_find_element(target, parameters)
            elif action_type == ActionType.ANALYZE.value:
                return await self._execute_analyze(target, parameters)
            else:
                return ActionResult(
                    success=False,
                    message=f"未知动作类型: {action_type}",
                    error="未知动作类型"
                )
                
        except Exception as e:
            logger.error(f"动作执行失败: {e}")
            return ActionResult(
                success=False,
                message=f"动作执行异常: {str(e)}",
                error=str(e)
            )
        finally:
            # 记录执行历史
            self.execution_history.append({
                "action": action,
                "timestamp": asyncio.get_event_loop().time()
            })
    
    async def _execute_click(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行点击动作"""
        try:
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            # 获取坐标
            x = parameters.get("x")
            y = parameters.get("y")
            button = parameters.get("button", "left")
            
            if x is None or y is None:
                # 需要先定位元素
                if self.visual_analyzer:
                    screenshot = await self.computer_adapter.take_screenshot()
                    location = await self.visual_analyzer.locate_element(target, screenshot)
                    if location:
                        x, y = location
                    else:
                        return ActionResult(
                            success=False,
                            message=f"无法定位目标: {target}",
                            error="元素定位失败"
                        )
                else:
                    return ActionResult(
                        success=False,
                        message="需要坐标或视觉分析器",
                        error="缺少必要参数"
                    )
            
            # 执行点击
            success = await self.computer_adapter.click(x, y, button)
            
            if success:
                return ActionResult(
                    success=True,
                    message=f"成功点击: ({x}, {y})",
                    data={"x": x, "y": y, "button": button}
                )
            else:
                return ActionResult(
                    success=False,
                    message="点击操作失败",
                    error="点击失败"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"点击执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_type(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行输入动作"""
        try:
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            text = parameters.get("text", target)
            interval = parameters.get("interval", 0.1)
            
            # 执行输入
            success = await self.computer_adapter.type_text(text, interval)
            
            if success:
                return ActionResult(
                    success=True,
                    message=f"成功输入文本: {text}",
                    data={"text": text, "interval": interval}
                )
            else:
                return ActionResult(
                    success=False,
                    message="文本输入失败",
                    error="输入失败"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"输入执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_screenshot(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行截图动作"""
        try:
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            # 执行截图
            screenshot = await self.computer_adapter.take_screenshot()
            
            if screenshot:
                return ActionResult(
                    success=True,
                    message="截图成功",
                    data={"screenshot_size": len(screenshot)}
                )
            else:
                return ActionResult(
                    success=False,
                    message="截图失败",
                    error="截图失败"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"截图执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_scroll(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行滚动动作"""
        try:
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            x = parameters.get("x", 0)
            y = parameters.get("y", 0)
            clicks = parameters.get("clicks", 3)
            
            # 执行滚动
            success = await self.computer_adapter.scroll(x, y, clicks)
            
            if success:
                return ActionResult(
                    success=True,
                    message=f"成功滚动: ({x}, {y}), 滚动量: {clicks}",
                    data={"x": x, "y": y, "clicks": clicks}
                )
            else:
                return ActionResult(
                    success=False,
                    message="滚动操作失败",
                    error="滚动失败"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"滚动执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_drag(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行拖拽动作"""
        try:
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            start_x = parameters.get("start_x", 0)
            start_y = parameters.get("start_y", 0)
            end_x = parameters.get("end_x", 100)
            end_y = parameters.get("end_y", 100)
            duration = parameters.get("duration", 1.0)
            
            # 执行拖拽
            success = await self.computer_adapter.drag_to(start_x, start_y, end_x, end_y, duration)
            
            if success:
                return ActionResult(
                    success=True,
                    message=f"成功拖拽: ({start_x}, {start_y}) -> ({end_x}, {end_y})",
                    data={"start": (start_x, start_y), "end": (end_x, end_y), "duration": duration}
                )
            else:
                return ActionResult(
                    success=False,
                    message="拖拽操作失败",
                    error="拖拽失败"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"拖拽执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_wait(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行等待动作"""
        try:
            duration = parameters.get("duration", 1.0)
            
            # 执行等待
            await asyncio.sleep(duration)
            
            return ActionResult(
                success=True,
                message=f"等待完成: {duration}秒",
                data={"duration": duration}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"等待执行失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_find_element(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行元素查找动作"""
        try:
            if not self.visual_analyzer:
                return ActionResult(
                    success=False,
                    message="视觉分析器未初始化",
                    error="分析器未初始化"
                )
            
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            # 先截图
            screenshot = await self.computer_adapter.take_screenshot()
            if not screenshot:
                return ActionResult(
                    success=False,
                    message="截图失败",
                    error="截图失败"
                )
            
            # 查找元素
            location = await self.visual_analyzer.locate_element(target, screenshot)
            
            if location:
                return ActionResult(
                    success=True,
                    message=f"找到元素: {target} at {location}",
                    data={"location": location, "target": target}
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"未找到元素: {target}",
                    error="元素未找到"
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"元素查找失败: {str(e)}",
                error=str(e)
            )
    
    async def _execute_analyze(self, target: str, parameters: Dict[str, Any]) -> ActionResult:
        """执行分析动作"""
        try:
            if not self.visual_analyzer:
                return ActionResult(
                    success=False,
                    message="视觉分析器未初始化",
                    error="分析器未初始化"
                )
            
            if not self.computer_adapter:
                return ActionResult(
                    success=False,
                    message="电脑控制适配器未初始化",
                    error="适配器未初始化"
                )
            
            # 先截图
            screenshot = await self.computer_adapter.take_screenshot()
            if not screenshot:
                return ActionResult(
                    success=False,
                    message="截图失败",
                    error="截图失败"
                )
            
            # 分析屏幕
            analysis = await self.visual_analyzer.analyze_screen(screenshot)
            
            if analysis.get("success"):
                return ActionResult(
                    success=True,
                    message="屏幕分析完成",
                    data=analysis
                )
            else:
                return ActionResult(
                    success=False,
                    message="屏幕分析失败",
                    error=analysis.get("error", "分析失败")
                )
                
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"屏幕分析失败: {str(e)}",
                error=str(e)
            )
    
    def _is_safe_action(self, action_type: str, target: str) -> bool:
        """检查动作是否安全"""
        # 危险动作列表
        dangerous_actions = ["delete", "remove", "uninstall", "format", "shutdown", "restart"]
        dangerous_targets = ["系统", "system", "注册表", "registry", "管理员", "admin"]
        
        # 检查动作类型
        if any(danger in action_type.lower() for danger in dangerous_actions):
            return False
        
        # 检查目标
        if any(danger in target.lower() for danger in dangerous_targets):
            return False
        
        return True
    
    async def execute_step_sequence(self, steps: list) -> List[ActionResult]:
        """执行步骤序列"""
        results = []
        
        for i, step in enumerate(steps):
            logger.info(f"执行步骤 {i+1}/{len(steps)}: {step.get('action', 'unknown')}")
            
            # 检查依赖
            if not self._check_dependencies(step, results):
                results.append(ActionResult(
                    success=False,
                    message=f"步骤 {i+1} 依赖检查失败",
                    error="依赖检查失败"
                ))
                continue
            
            # 执行步骤
            result = await self.execute_action(step)
            results.append(result)
            
            # 如果步骤失败，可以选择继续或停止
            if not result.success:
                logger.warning(f"步骤 {i+1} 执行失败: {result.message}")
                # 这里可以选择继续执行或停止
                # break  # 停止执行
                continue  # 继续执行
        
        return results
    
    def _check_dependencies(self, step: dict, previous_results: List[ActionResult]) -> bool:
        """检查步骤依赖"""
        dependencies = step.get("dependencies", [])
        
        for dep in dependencies:
            # 查找依赖的步骤结果
            dep_result = None
            for result in previous_results:
                if hasattr(result, 'step_id') and result.step_id == dep:
                    dep_result = result
                    break
            
            if not dep_result or not dep_result.success:
                return False
        
        return True
    
    def is_available(self) -> Dict[str, Any]:
        """检查动作执行功能是否可用"""
        return {
            "enabled": True,
            "ready": self.computer_adapter is not None,
            "safety_mode": self.safety_mode,
            "max_retry_count": self.max_retry_count,
            "execution_history_count": len(self.execution_history)
        }
