"""
电脑控制适配器 - 基于博弈论的ComputerUseAdapter实现
提供鼠标键盘控制、屏幕截图、视觉分析等核心功能
"""

import io
import time
import platform
import logging
from typing import Dict, Any, Optional, Tuple
from nagaagent_core.vendors.pil import Image
import asyncio

# 尝试导入依赖包
try:
    import nagaagent_core.vendors.pyautogui as pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

try:
    from gui_agents.s2_5.agents.grounding import OSWorldACI
    from gui_agents.s2_5.agents.agent_s import AgentS2_5
    GUI_AGENTS_AVAILABLE = True
except ImportError:
    GUI_AGENTS_AVAILABLE = False
    OSWorldACI = None
    AgentS2_5 = None

# 配置日志
logger = logging.getLogger(__name__)

class ComputerUseAdapter:
    """电脑控制适配器，基于博弈论的实现"""
    
    def __init__(self):
        """初始化电脑控制适配器"""
        self.last_error: Optional[str] = None
        self.agent = None
        self.grounding_agent = None
        self.init_ok = False
        
        # 设置DPI感知（Windows）
        self._setup_dpi_awareness()
        
        # 初始化屏幕尺寸 - 基于博弈论的实现
        self.screen_width = 1920  # 默认值
        self.screen_height = 1080  # 默认值
        self.scaled_width = 1920
        self.scaled_height = 1080
        self.scale_x = 1.0
        self.scale_y = 1.0
        
        if PYAUTOGUI_AVAILABLE:
            try:
                # 动态获取实际屏幕尺寸
                self.screen_width, self.screen_height = pyautogui.size()
                logger.info(f"实际屏幕尺寸: {self.screen_width}x{self.screen_height}")
                
                # 计算缩放尺寸（参考博弈论的scale_screen_dimensions函数）
                self.scaled_width, self.scaled_height = self._scale_screen_dimensions(
                    self.screen_width, self.screen_height, max_dim_size=1920
                )
                
                # 计算缩放因子（逻辑坐标 -> 物理坐标）
                self.scale_x = self.screen_width / max(1, self.scaled_width)
                self.scale_y = self.screen_height / max(1, self.scaled_height)
                
            except Exception as e:
                logger.warning(f"获取屏幕尺寸失败: {e}")
                # 使用默认值
        
        # 初始化组件
        self._init_components()
    
    def _setup_dpi_awareness(self):
        """设置DPI感知，提高坐标精度"""
        try:
            if platform.system().lower() == "windows":
                import ctypes
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except Exception:
                    try:
                        ctypes.windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass
        except Exception:
            pass
    
    def _scale_screen_dimensions(self, width: int, height: int, max_dim_size: int = 1920) -> Tuple[int, int]:
        """缩放屏幕尺寸，基于博弈论的实现"""
        scale_factor = min(max_dim_size / width, max_dim_size / height)
        safe_width = int(width * scale_factor)
        safe_height = int(height * scale_factor)
        logger.info(f"屏幕缩放: {width}x{height} -> {safe_width}x{safe_height}, 缩放因子: {scale_factor:.2f}")
        return safe_width, safe_height
    
    def _init_components(self):
        """初始化核心组件"""
        try:
            if not PYAUTOGUI_AVAILABLE:
                self.last_error = "pyautogui未安装"
                logger.error("pyautogui未安装，电脑控制功能不可用")
                return
            
            if not GUI_AGENTS_AVAILABLE:
                self.last_error = "gui-agents未安装"
                logger.error("gui-agents未安装，高级功能不可用")
                return
            
            # 初始化GUI代理
            self._init_gui_agents()
            self.init_ok = True
            logger.info("电脑控制适配器初始化成功")
            
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"电脑控制适配器初始化失败: {e}")
    
    def _init_gui_agents(self):
        """初始化GUI代理"""
        try:
            # 这里可以添加GUI代理的初始化逻辑
            # 暂时使用基础功能
            logger.info("GUI代理初始化完成")
        except Exception as e:
            logger.warning(f"GUI代理初始化失败: {e}")
    
    def is_available(self) -> Dict[str, Any]:
        """检查电脑控制功能是否可用"""
        ok = True
        reasons = []
        
        if not PYAUTOGUI_AVAILABLE:
            ok = False
            reasons.append("pyautogui未安装")
        
        if not self.init_ok:
            ok = False
            msg = "电脑控制适配器未初始化"
            if self.last_error:
                msg += f": {self.last_error}"
            reasons.append(msg)
        
        return {
            "enabled": True,
            "ready": ok,
            "reasons": reasons,
            "screen_info": {
                "physical_size": f"{self.screen_width}x{self.screen_height}",
                "scaled_size": f"{self.scaled_width}x{self.scaled_height}",
                "scale_factors": f"x={self.scale_x:.2f}, y={self.scale_y:.2f}"
            },
            "platform": platform.system()
        }
    
    async def take_screenshot(self) -> Optional[bytes]:
        """截取屏幕截图"""
        if not PYAUTOGUI_AVAILABLE:
            return None
        
        try:
            screenshot = pyautogui.screenshot()
            # 基于博弈论的实现：将截图缩放到逻辑尺寸
            screenshot = screenshot.resize((self.scaled_width, self.scaled_height), Image.LANCZOS)
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.error(f"截取屏幕截图失败: {e}")
            return None
    
    def _scale_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        """缩放坐标，将逻辑坐标转换为物理坐标"""
        scaled_x = int(round(x * self.scale_x))
        scaled_y = int(round(y * self.scale_y))
        return scaled_x, scaled_y
    
    def _create_scaled_pyautogui(self):
        """创建缩放版本的pyautogui代理"""
        if not PYAUTOGUI_AVAILABLE:
            return None
        
        class _ScaledPyAutoGUI:
            """
            轻量级代理，将逻辑坐标空间缩放到物理屏幕坐标
            支持多种坐标格式
            """
            def __init__(self, backend, scale_x: float, scale_y: float):
                self._backend = backend
                self._scale_x = scale_x
                self._scale_y = scale_y

            def __getattr__(self, name):
                # 回退到所有其他属性/方法
                return getattr(self._backend, name)

            def _scale_xy_from_args(self, args, kwargs):
                """从参数中缩放x,y坐标，支持多种坐标格式"""
                # 处理 (x, y) 格式
                if len(args) >= 2 and isinstance(args[0], (int, float)) and isinstance(args[1], (int, float)):
                    x = int(round(args[0] * self._scale_x))
                    y = int(round(args[1] * self._scale_y))
                    args = (x, y) + tuple(args[2:])
                # 处理 ((x, y),) 格式
                elif len(args) >= 1 and isinstance(args[0], (tuple, list)) and len(args[0]) == 2:
                    x_raw, y_raw = args[0]
                    if isinstance(x_raw, (int, float)) and isinstance(y_raw, (int, float)):
                        x = int(round(x_raw * self._scale_x))
                        y = int(round(y_raw * self._scale_y))
                        args = ((x, y),) + tuple(args[1:])
                else:
                    # 处理kwargs格式
                    if 'x' in kwargs and 'y' in kwargs and isinstance(kwargs['x'], (int, float)) and isinstance(kwargs['y'], (int, float)):
                        kwargs = dict(kwargs)
                        kwargs['x'] = int(round(kwargs['x'] * self._scale_x))
                        kwargs['y'] = int(round(kwargs['y'] * self._scale_y))
                return args, kwargs

            # 包装的绝对坐标鼠标API - 自动坐标缩放
            def moveTo(self, *args, **kwargs):
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.moveTo(*args, **kwargs)

            def click(self, *args, **kwargs):
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.click(*args, **kwargs)

            def doubleClick(self, *args, **kwargs):
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.doubleClick(*args, **kwargs)

            def rightClick(self, *args, **kwargs):
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.rightClick(*args, **kwargs)

            def dragTo(self, *args, **kwargs):
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.dragTo(*args, **kwargs)
            
            def scroll(self, *args, **kwargs):
                """滚动操作也支持坐标缩放"""
                args, kwargs = self._scale_xy_from_args(args, kwargs)
                return self._backend.scroll(*args, **kwargs)
        
        return _ScaledPyAutoGUI(pyautogui, self.scale_x, self.scale_y)
    
    async def click(self, x: int, y: int, button: str = 'left') -> bool:
        """点击指定坐标"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        
        try:
            # 缩放坐标
            scaled_x, scaled_y = self._scale_coordinates(x, y)
            
            if button == 'left':
                pyautogui.click(scaled_x, scaled_y)
            elif button == 'right':
                pyautogui.rightClick(scaled_x, scaled_y)
            elif button == 'middle':
                pyautogui.middleClick(scaled_x, scaled_y)
            else:
                pyautogui.click(scaled_x, scaled_y)
            
            logger.info(f"点击坐标: 逻辑({x}, {y}) -> 物理({scaled_x}, {scaled_y}), 按钮: {button}")
            return True
        except Exception as e:
            logger.error(f"点击操作失败: {e}")
            return False
    
    async def type_text(self, text: str, interval: float = 0.1) -> bool:
        """输入文本"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        
        try:
            pyautogui.typewrite(text, interval=interval)
            logger.info(f"输入文本: {text}")
            return True
        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False
    
    async def press_key(self, key: str) -> bool:
        """按下指定按键"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        
        try:
            pyautogui.press(key)
            logger.info(f"按下按键: {key}")
            return True
        except Exception as e:
            logger.error(f"按键操作失败: {e}")
            return False
    
    async def scroll(self, x: int, y: int, clicks: int) -> bool:
        """滚动鼠标"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        
        try:
            # 缩放坐标
            scaled_x, scaled_y = self._scale_coordinates(x, y)
            pyautogui.scroll(clicks, scaled_x, scaled_y)
            logger.info(f"滚动: 逻辑({x}, {y}) -> 物理({scaled_x}, {scaled_y}), 滚动量: {clicks}")
            return True
        except Exception as e:
            logger.error(f"滚动操作失败: {e}")
            return False
    
    async def drag_to(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 1.0) -> bool:
        """拖拽操作"""
        if not PYAUTOGUI_AVAILABLE:
            return False
        
        try:
            # 缩放坐标
            scaled_start_x, scaled_start_y = self._scale_coordinates(start_x, start_y)
            scaled_end_x, scaled_end_y = self._scale_coordinates(end_x, end_y)
            
            pyautogui.dragTo(scaled_end_x, scaled_end_y, duration=duration)
            logger.info(f"拖拽: 逻辑({start_x}, {start_y})->({end_x}, {end_y}) -> 物理({scaled_start_x}, {scaled_start_y})->({scaled_end_x}, {scaled_end_y})")
            return True
        except Exception as e:
            logger.error(f"拖拽操作失败: {e}")
            return False
    
    async def find_element_by_text(self, text: str, screenshot: Optional[bytes] = None) -> Optional[Tuple[int, int]]:
        """通过文本查找元素位置"""
        # 这里可以集成OCR功能
        # 暂时返回None，后续实现
        logger.info(f"查找文本元素: {text}")
        return None
    
    async def find_element_by_image(self, image_path: str, screenshot: Optional[bytes] = None) -> Optional[Tuple[int, int]]:
        """通过图像查找元素位置"""
        # 这里可以集成图像匹配功能
        # 暂时返回None，后续实现
        logger.info(f"查找图像元素: {image_path}")
        return None
    
    async def execute_instruction(self, instruction: str) -> Dict[str, Any]:
        """执行电脑控制指令"""
        try:
            logger.info(f"执行指令: {instruction}")
            
            # 解析指令
            action = self._parse_instruction(instruction)
            
            if not action:
                return {
                    "success": False,
                    "error": "无法解析指令",
                    "instruction": instruction
                }
            
            # 执行动作
            result = await self._execute_action(action)
            
            return {
                "success": result,
                "instruction": instruction,
                "action": action
            }
            
        except Exception as e:
            logger.error(f"执行指令失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "instruction": instruction
            }
    
    async def run_instruction(self, instruction: str, max_iterations: int = 15) -> Dict[str, Any]:
        """执行自然语言指令"""
        if not self.init_ok:
            return {"success": False, "error": "电脑控制适配器未初始化"}
        
        try:
            obs = {}
            traj = "任务:\n" + instruction
            
            for iteration in range(max_iterations):
                logger.info(f"执行迭代 {iteration + 1}/{max_iterations}")
                
                # 获取屏幕截图
                screenshot = await self.take_screenshot()
                if not screenshot:
                    return {"success": False, "error": "无法获取屏幕截图"}
                
                obs["screenshot"] = screenshot
                
                # 这里应该调用AI模型来生成下一步动作
                # 暂时使用简单的模拟逻辑
                if iteration == 0:
                    # 模拟AI生成的代码
                    code = f"# 执行任务: {instruction}\nprint('任务开始执行')"
                else:
                    code = "print('任务完成')"
                
                logger.info(f"执行代码: {code}")
                
                # 检查任务完成条件
                if "完成" in code or "done" in code.lower():
                    logger.info("任务完成")
                    break
                
                if "等待" in code or "wait" in code.lower():
                    await asyncio.sleep(3)
                    continue
                
                if "下一步" in code or "next" in code.lower():
                    continue
                
                # 执行代码（注入缩放后的pyautogui）
                try:
                    exec_env = globals().copy()
                    if PYAUTOGUI_AVAILABLE and hasattr(self, 'scale_x') and hasattr(self, 'scale_y'):
                        scaled_pyautogui = self._create_scaled_pyautogui()
                        if scaled_pyautogui:
                            exec_env['pyautogui'] = scaled_pyautogui
                    
                    exec(code, exec_env, exec_env)
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"代码执行失败: {e}")
                    continue
                
                # 更新任务轨迹
                traj += f"\n\n迭代 {iteration + 1}:\n{code}"
            
            return {
                "success": True, 
                "message": "任务执行完成",
                "iterations": iteration + 1,
                "trajectory": traj
            }
            
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def normalize_coordinates(self, x: float, y: float, screen_width: int = None, screen_height: int = None) -> Tuple[int, int]:
        """
        坐标标准化
        将任意坐标转换为0-1000范围的标准化坐标
        """
        if screen_width is None:
            screen_width = self.screen_width
        if screen_height is None:
            screen_height = self.screen_height
        
        # 标准化到0-1000范围
        normalized_x = int(round(x / screen_width * 1000))
        normalized_y = int(round(y / screen_height * 1000))
        
        # 确保在有效范围内
        normalized_x = max(0, min(1000, normalized_x))
        normalized_y = max(0, min(1000, normalized_y))
        
        return normalized_x, normalized_y
    
    def denormalize_coordinates(self, normalized_x: int, normalized_y: int, 
                               screen_width: int = None, screen_height: int = None) -> Tuple[int, int]:
        """
        反标准化坐标，将0-1000范围的坐标转换为实际像素坐标
        坐标反标准化
        """
        if screen_width is None:
            screen_width = self.screen_width
        if screen_height is None:
            screen_height = self.screen_height
        
        # 从标准化坐标转换为实际像素坐标
        pixel_x = int(round(normalized_x / 1000.0 * screen_width))
        pixel_y = int(round(normalized_y / 1000.0 * screen_height))
        
        return pixel_x, pixel_y
    
    async def click_with_ai_location(self, target_description: str, button: str = 'left') -> bool:
        """
        使用AI定位进行点击
        支持自然语言描述目标元素
        """
        try:
            # 获取屏幕截图
            screenshot = await self.take_screenshot()
            if not screenshot:
                logger.error("无法获取屏幕截图")
                return False
            
            # 使用AI定位元素
            from .visual_analyzer import VisualAnalyzer
            analyzer = VisualAnalyzer()
            location = await analyzer.locate_element_with_ai(
                target_description, 
                screenshot, 
                self.screen_width, 
                self.screen_height
            )
            
            if location:
                x, y = location
                return await self.click(x, y, button)
            else:
                logger.error(f"AI定位失败: {target_description}")
                return False
                
        except Exception as e:
            logger.error(f"AI定位点击失败: {e}")
            return False
    
    def get_coordinate_info(self) -> Dict[str, Any]:
        """获取坐标系统信息"""
        return {
            "screen_size": f"{self.screen_width}x{self.screen_height}",
            "scaled_size": f"{self.scaled_width}x{self.scaled_height}",
            "scale_factors": f"x={self.scale_x:.2f}, y={self.scale_y:.2f}",
            "normalization_range": "0-1000",
            "platform": platform.system()
        }
    
    def _parse_instruction(self, instruction: str) -> Optional[Dict[str, Any]]:
        """解析指令"""
        instruction = instruction.lower().strip()
        
        # 简单的指令解析
        if "点击" in instruction or "click" in instruction:
            return {"action": "click", "instruction": instruction}
        elif "输入" in instruction or "type" in instruction:
            return {"action": "type", "instruction": instruction}
        elif "截图" in instruction or "screenshot" in instruction:
            return {"action": "screenshot", "instruction": instruction}
        elif "滚动" in instruction or "scroll" in instruction:
            return {"action": "scroll", "instruction": instruction}
        else:
            return {"action": "unknown", "instruction": instruction}
    
    async def _execute_action(self, action: Dict[str, Any]) -> bool:
        """执行具体动作"""
        action_type = action.get("action")
        instruction = action.get("instruction")
        
        if action_type == "click":
            # 这里需要更智能的坐标定位
            # 暂时使用屏幕中心
            x, y = self.screen_width // 2, self.screen_height // 2
            return await self.click(x, y)
        elif action_type == "type":
            # 这里需要提取要输入的文本
            # 暂时使用示例文本
            return await self.type_text("Hello World")
        elif action_type == "screenshot":
            screenshot = await self.take_screenshot()
            return screenshot is not None
        elif action_type == "scroll":
            # 这里需要更智能的滚动参数
            return await self.scroll(self.screen_width // 2, self.screen_height // 2, 3)
        else:
            logger.warning(f"未知动作类型: {action_type}")
            return False
