"""
任务规划器 - 基于博弈论的智能任务分解和规划
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# 配置日志
logger = logging.getLogger(__name__)

class TaskType(Enum):
    """任务类型"""
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    FIND_ELEMENT = "find_element"
    AUTOMATE = "automate"
    COMPLEX = "complex"

@dataclass
class TaskStep:
    """任务步骤"""
    step_id: str
    action: str
    target: str
    parameters: Dict[str, Any]
    description: str
    dependencies: List[str] = None
    timeout: int = 30
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

class TaskPlanner:
    """任务规划器"""
    
    def __init__(self):
        """初始化任务规划器"""
        self.step_templates = {
            "click": {
                "action": "click",
                "description": "点击指定位置",
                "required_params": ["x", "y"],
                "optional_params": ["button", "duration"]
            },
            "type": {
                "action": "type",
                "description": "输入文本",
                "required_params": ["text"],
                "optional_params": ["interval", "clear_first"]
            },
            "screenshot": {
                "action": "screenshot",
                "description": "截取屏幕截图",
                "required_params": [],
                "optional_params": ["region"]
            },
            "find_element": {
                "action": "find_element",
                "description": "查找屏幕元素",
                "required_params": ["text"],
                "optional_params": ["timeout", "retry_count"]
            },
            "wait": {
                "action": "wait",
                "description": "等待指定时间",
                "required_params": ["duration"],
                "optional_params": []
            },
            "scroll": {
                "action": "scroll",
                "description": "滚动页面",
                "required_params": ["direction"],
                "optional_params": ["amount", "speed"]
            }
        }
        
        logger.info("任务规划器初始化完成")
    
    async def plan_task(self, instruction: str) -> List[TaskStep]:
        """规划任务步骤"""
        try:
            logger.info(f"开始规划任务: {instruction}")
            
            # 分析任务类型
            task_type = self._analyze_task_type(instruction)
            logger.info(f"任务类型: {task_type}")
            
            # 根据任务类型生成步骤
            if task_type == TaskType.CLICK:
                steps = await self._plan_click_task(instruction)
            elif task_type == TaskType.TYPE:
                steps = await self._plan_type_task(instruction)
            elif task_type == TaskType.SCREENSHOT:
                steps = await self._plan_screenshot_task(instruction)
            elif task_type == TaskType.FIND_ELEMENT:
                steps = await self._plan_find_element_task(instruction)
            elif task_type == TaskType.AUTOMATE:
                steps = await self._plan_automate_task(instruction)
            else:
                steps = await self._plan_complex_task(instruction)
            
            logger.info(f"任务规划完成，生成 {len(steps)} 个步骤")
            return steps
            
        except Exception as e:
            logger.error(f"任务规划失败: {e}")
            return []
    
    def _analyze_task_type(self, instruction: str) -> TaskType:
        """分析任务类型"""
        instruction_lower = instruction.lower()
        
        if any(keyword in instruction_lower for keyword in ["点击", "click", "按", "press"]):
            return TaskType.CLICK
        elif any(keyword in instruction_lower for keyword in ["输入", "type", "打字", "输入文本"]):
            return TaskType.TYPE
        elif any(keyword in instruction_lower for keyword in ["截图", "screenshot", "截屏"]):
            return TaskType.SCREENSHOT
        elif any(keyword in instruction_lower for keyword in ["查找", "find", "找到", "定位"]):
            return TaskType.FIND_ELEMENT
        elif any(keyword in instruction_lower for keyword in ["自动化", "automate", "执行", "运行"]):
            return TaskType.AUTOMATE
        else:
            return TaskType.COMPLEX
    
    async def _plan_click_task(self, instruction: str) -> List[TaskStep]:
        """规划点击任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取当前屏幕状态"
        ))
        
        # 步骤2: 查找目标元素
        steps.append(TaskStep(
            step_id="find_target",
            action="find_element",
            target=instruction,
            parameters={"text": instruction, "timeout": 10},
            description=f"查找目标元素: {instruction}",
            dependencies=["screenshot_1"]
        ))
        
        # 步骤3: 执行点击
        steps.append(TaskStep(
            step_id="click_target",
            action="click",
            target="目标位置",
            parameters={"x": 0, "y": 0, "button": "left"},
            description="点击目标元素",
            dependencies=["find_target"]
        ))
        
        return steps
    
    async def _plan_type_task(self, instruction: str) -> List[TaskStep]:
        """规划输入任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取当前屏幕状态"
        ))
        
        # 步骤2: 查找输入框
        steps.append(TaskStep(
            step_id="find_input",
            action="find_element",
            target="输入框",
            parameters={"text": "输入", "timeout": 10},
            description="查找输入框",
            dependencies=["screenshot_1"]
        ))
        
        # 步骤3: 点击输入框
        steps.append(TaskStep(
            step_id="click_input",
            action="click",
            target="输入框",
            parameters={"x": 0, "y": 0},
            description="点击输入框",
            dependencies=["find_input"]
        ))
        
        # 步骤4: 输入文本
        steps.append(TaskStep(
            step_id="type_text",
            action="type",
            target="文本输入",
            parameters={"text": instruction, "clear_first": True},
            description=f"输入文本: {instruction}",
            dependencies=["click_input"]
        ))
        
        return steps
    
    async def _plan_screenshot_task(self, instruction: str) -> List[TaskStep]:
        """规划截图任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取屏幕截图"
        ))
        
        return steps
    
    async def _plan_find_element_task(self, instruction: str) -> List[TaskStep]:
        """规划查找元素任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取当前屏幕状态"
        ))
        
        # 步骤2: 查找目标元素
        steps.append(TaskStep(
            step_id="find_element",
            action="find_element",
            target=instruction,
            parameters={"text": instruction, "timeout": 10},
            description=f"查找元素: {instruction}",
            dependencies=["screenshot_1"]
        ))
        
        return steps
    
    async def _plan_automate_task(self, instruction: str) -> List[TaskStep]:
        """规划自动化任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取当前屏幕状态"
        ))
        
        # 步骤2: 分析任务需求
        steps.append(TaskStep(
            step_id="analyze_task",
            action="analyze",
            target=instruction,
            parameters={"instruction": instruction},
            description="分析任务需求",
            dependencies=["screenshot_1"]
        ))
        
        # 步骤3: 执行任务
        steps.append(TaskStep(
            step_id="execute_task",
            action="automate",
            target=instruction,
            parameters={"instruction": instruction},
            description=f"执行自动化任务: {instruction}",
            dependencies=["analyze_task"]
        ))
        
        return steps
    
    async def _plan_complex_task(self, instruction: str) -> List[TaskStep]:
        """规划复杂任务"""
        steps = []
        
        # 步骤1: 截取屏幕截图
        steps.append(TaskStep(
            step_id="screenshot_1",
            action="screenshot",
            target="当前屏幕",
            parameters={},
            description="截取当前屏幕状态"
        ))
        
        # 步骤2: 分析任务
        steps.append(TaskStep(
            step_id="analyze_complex",
            action="analyze",
            target=instruction,
            parameters={"instruction": instruction, "complex": True},
            description="分析复杂任务",
            dependencies=["screenshot_1"]
        ))
        
        # 步骤3: 分解子任务
        steps.append(TaskStep(
            step_id="decompose",
            action="decompose",
            target=instruction,
            parameters={"instruction": instruction},
            description="分解任务为子步骤",
            dependencies=["analyze_complex"]
        ))
        
        # 步骤4: 执行子任务
        steps.append(TaskStep(
            step_id="execute_subtasks",
            action="execute_subtasks",
            target=instruction,
            parameters={"instruction": instruction},
            description="执行子任务",
            dependencies=["decompose"]
        ))
        
        return steps
    
    async def optimize_steps(self, steps: List[TaskStep]) -> List[TaskStep]:
        """优化任务步骤"""
        try:
            logger.info(f"开始优化 {len(steps)} 个步骤")
            
            optimized_steps = []
            
            for step in steps:
                # 检查步骤是否必要
                if self._is_step_necessary(step, optimized_steps):
                    optimized_steps.append(step)
                else:
                    logger.info(f"跳过不必要的步骤: {step.step_id}")
            
            # 重新分配步骤ID
            for i, step in enumerate(optimized_steps):
                step.step_id = f"step_{i+1}"
            
            logger.info(f"步骤优化完成: {len(optimized_steps)} 个步骤")
            return optimized_steps
            
        except Exception as e:
            logger.error(f"步骤优化失败: {e}")
            return steps
    
    def _is_step_necessary(self, step: TaskStep, existing_steps: List[TaskStep]) -> bool:
        """检查步骤是否必要"""
        # 简单的必要性检查逻辑
        if step.action == "screenshot":
            # 如果已经有截图步骤，可能不需要重复
            for existing in existing_steps:
                if existing.action == "screenshot":
                    return False
        
        return True
    
    def get_step_template(self, action: str) -> Optional[Dict[str, Any]]:
        """获取步骤模板"""
        return self.step_templates.get(action)
    
    def validate_step(self, step: TaskStep) -> Dict[str, Any]:
        """验证步骤"""
        template = self.get_step_template(step.action)
        if not template:
            return {
                "valid": False,
                "error": f"未知的动作类型: {step.action}"
            }
        
        # 检查必需参数
        required_params = template.get("required_params", [])
        for param in required_params:
            if param not in step.parameters:
                return {
                    "valid": False,
                    "error": f"缺少必需参数: {param}"
                }
        
        return {"valid": True}