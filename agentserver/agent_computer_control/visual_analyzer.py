"""
视觉分析器 - 基于博弈论的视觉识别功能
提供OCR、图像匹配、元素定位、AI坐标定位等功能
AI坐标定位算法升级
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
import sys
if 'nagaagent_core.vendors.pil' in sys.modules:
    del sys.modules['nagaagent_core.vendors.pil']
from PIL import Image
import io
import base64
import re
import json

# 配置日志
logger = logging.getLogger(__name__)

class VisualAnalyzer:
    """视觉分析器"""
    
    def __init__(self):
        """初始化视觉分析器"""
        self.ocr_available = False
        self.image_matching_available = False
        self.ai_coordinate_available = False
        
        # 尝试导入OCR库
        try:
            import nagaagent_core.vendors.pytesseract as pytesseract
            self.ocr_available = True
            logger.info("OCR功能已启用")
        except ImportError:
            logger.warning("pytesseract未安装，OCR功能不可用")
        
        # 尝试导入图像匹配库
        try:
            import nagaagent_core.vendors.cv2 as cv2
            import numpy as np
            self.cv2 = cv2
            self.np = np
            self.image_matching_available = True
            logger.info("图像匹配功能已启用")
        except ImportError:
            logger.warning("opencv-python未安装，图像匹配功能不可用")
        
        # 尝试导入AI坐标定位库
        try:
            from langchain_openai import ChatOpenAI
            self.ai_coordinate_available = True
            logger.info("AI坐标定位功能已启用")
        except ImportError:
            logger.warning("langchain-openai未安装，AI坐标定位功能不可用")
    
    async def analyze_screenshot(self, screenshot: bytes) -> Dict[str, Any]:
        """分析屏幕截图"""
        try:
            # 加载图像
            image = Image.open(io.BytesIO(screenshot))
            
            analysis_result = {
                "image_size": image.size,
                "mode": image.mode,
                "ocr_text": [],
                "elements": [],
                "analysis_time": None
            }
            
            # OCR文本识别
            if self.ocr_available:
                ocr_result = await self._extract_text_from_image(image)
                analysis_result["ocr_text"] = ocr_result
            
            # 元素检测
            elements = await self._detect_elements(image)
            analysis_result["elements"] = elements
            
            logger.info(f"屏幕分析完成: 识别到 {len(analysis_result['ocr_text'])} 个文本, {len(elements)} 个元素")
            return analysis_result
            
        except Exception as e:
            logger.error(f"屏幕分析失败: {e}")
            return {
                "error": str(e),
                "image_size": None,
                "ocr_text": [],
                "elements": []
            }
    
    async def _extract_text_from_image(self, image: Image.Image) -> List[Dict[str, Any]]:
        """从图像中提取文本"""
        if not self.ocr_available:
            return []
        
        try:
            import nagaagent_core.vendors.pytesseract as pytesseract
            
            # 使用OCR提取文本和位置信息
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            text_elements = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if text:  # 只处理非空文本
                    text_elements.append({
                        "text": text,
                        "confidence": data['conf'][i],
                        "bbox": {
                            "x": data['left'][i],
                            "y": data['top'][i],
                            "width": data['width'][i],
                            "height": data['height'][i]
                        }
                    })
            
            return text_elements
            
        except Exception as e:
            logger.error(f"OCR文本提取失败: {e}")
            return []
    
    async def _detect_elements(self, image: Image.Image) -> List[Dict[str, Any]]:
        """检测图像中的元素"""
        if not self.image_matching_available:
            return []
        
        try:
            # 转换为OpenCV格式
            cv_image = self.cv2.cvtColor(self.np.array(image), self.cv2.COLOR_RGB2BGR)
            
            # 检测边缘
            gray = self.cv2.cvtColor(cv_image, self.cv2.COLOR_BGR2GRAY)
            edges = self.cv2.Canny(gray, 50, 150)
            
            # 查找轮廓
            contours, _ = self.cv2.findContours(edges, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE)
            
            elements = []
            for contour in contours:
                # 计算边界框
                x, y, w, h = self.cv2.boundingRect(contour)
                
                # 过滤太小的元素
                if w > 10 and h > 10:
                    elements.append({
                        "type": "contour",
                        "bbox": {"x": x, "y": y, "width": w, "height": h},
                        "area": w * h
                    })
            
            return elements
            
        except Exception as e:
            logger.error(f"元素检测失败: {e}")
            return []
    
    async def find_text_element(self, screenshot: bytes, target_text: str) -> Optional[Tuple[int, int]]:
        """查找包含指定文本的元素位置"""
        try:
            analysis = await self.analyze_screenshot(screenshot)
            
            for text_element in analysis.get("ocr_text", []):
                if target_text.lower() in text_element["text"].lower():
                    bbox = text_element["bbox"]
                    # 返回中心坐标
                    center_x = bbox["x"] + bbox["width"] // 2
                    center_y = bbox["y"] + bbox["height"] // 2
                    return (center_x, center_y)
            
            return None
            
        except Exception as e:
            logger.error(f"查找文本元素失败: {e}")
            return None
    
    async def find_image_element(self, screenshot: bytes, template_path: str) -> Optional[Tuple[int, int]]:
        """查找图像模板匹配的元素位置"""
        if not self.image_matching_available:
            return None
        
        try:
            # 加载模板图像
            template = self.cv2.imread(template_path)
            if template is None:
                logger.error(f"无法加载模板图像: {template_path}")
                return None
            
            # 加载屏幕截图
            screen_image = Image.open(io.BytesIO(screenshot))
            screen_cv = self.cv2.cvtColor(self.np.array(screen_image), self.cv2.COLOR_RGB2BGR)
            
            # 模板匹配
            result = self.cv2.matchTemplate(screen_cv, template, self.cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = self.cv2.minMaxLoc(result)
            
            # 如果匹配度足够高
            if max_val > 0.8:
                # 返回模板中心位置
                center_x = max_loc[0] + template.shape[1] // 2
                center_y = max_loc[1] + template.shape[0] // 2
                return (center_x, center_y)
            
            return None
            
        except Exception as e:
            logger.error(f"图像匹配失败: {e}")
            return None
    
    async def get_screen_info(self, screenshot: bytes) -> Dict[str, Any]:
        """获取屏幕信息"""
        try:
            image = Image.open(io.BytesIO(screenshot))
            
            return {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
                "size_bytes": len(screenshot)
            }
            
        except Exception as e:
            logger.error(f"获取屏幕信息失败: {e}")
            return {
                "error": str(e),
                "width": 0,
                "height": 0
            }
    
    async def locate_element_with_ai(self, target_description: str, screenshot: bytes, 
                                   screen_width: int = 1920, screen_height: int = 1080) -> Optional[Tuple[int, int]]:
        """
        使用AI定位屏幕元素
        支持自然语言描述定位界面元素
        """
        if not self.ai_coordinate_available:
            logger.warning("AI坐标定位功能不可用")
            return None
        
        try:
            from langchain_openai import ChatOpenAI
            # 统一从系统配置读取视觉LLM参数
            from system.config import config
            cc = getattr(config, 'computer_control', None)
            model = getattr(cc, 'model', None) or config.api.model
            base_url = getattr(cc, 'model_url', None) or config.api.base_url
            api_key = getattr(cc, 'api_key', None) or config.api.api_key
            
            # 初始化LLM
            llm = ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=0
            )
            
            # 将截图转换为base64
            screenshot_b64 = base64.b64encode(screenshot).decode('utf-8')
            
            # 构建AI定位提示词
            prompt = f"""
            请分析屏幕截图并定位目标元素: "{target_description}"
            
            请按以下格式输出坐标：
            1. 如果可能，输出边界框 [x1, y1, x2, y2]，坐标范围0-1000
            2. 如果边界框不合适，输出精确坐标 x,y
            3. 不要包含任何解释文字，只输出坐标
            
            屏幕尺寸: {screen_width}x{screen_height}
            """
            
            # 调用AI模型进行坐标定位
            response = llm.invoke([
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                    ]
                }
            ])
            
            # 解析AI返回的坐标
            coordinates = self._parse_ai_coordinates(response.content, screen_width, screen_height)
            
            if coordinates:
                logger.info(f"AI定位成功: {target_description} -> {coordinates}")
                return coordinates
            else:
                logger.warning(f"AI定位失败: {target_description}")
                return None
                
        except Exception as e:
            logger.error(f"AI坐标定位失败: {e}")
            return None
    
    def _parse_ai_coordinates(self, response: str, screen_width: int, screen_height: int) -> Optional[Tuple[int, int]]:
        """
        解析AI返回的坐标
        支持边界框和精确坐标两种格式
        """
        try:
            # 清理响应文本
            response = response.strip()
            
            # 尝试解析边界框格式 [x1, y1, x2, y2]
            bbox_match = re.search(r'\[([0-9.,\s]+)\]', response)
            if bbox_match:
                coords_str = bbox_match.group(1)
                numbers = re.findall(r'-?\d+\.?\d*', coords_str)
                if len(numbers) >= 4:
                    x1, y1, x2, y2 = [float(n) for n in numbers[:4]]
                    # 检查是否在0-1000范围内（标准化坐标）
                    if max(x1, y1, x2, y2) <= 1000:
                        # 计算中心点并转换为实际像素坐标
                        center_x = (x1 + x2) / 2.0
                        center_y = (y1 + y2) / 2.0
                        pixel_x = int(round(center_x / 1000.0 * screen_width))
                        pixel_y = int(round(center_y / 1000.0 * screen_height))
                        return (pixel_x, pixel_y)
                    else:
                        # 直接使用像素坐标
                        center_x = (x1 + x2) / 2
                        center_y = (y1 + y2) / 2
                        return (int(center_x), int(center_y))
            
            # 尝试解析精确坐标格式 x,y
            coord_match = re.search(r'(\d+\.?\d*)\s*,\s*(\d+\.?\d*)', response)
            if coord_match:
                x, y = float(coord_match.group(1)), float(coord_match.group(2))
                # 检查是否在0-1000范围内（标准化坐标）
                if x <= 1000 and y <= 1000:
                    pixel_x = int(round(x / 1000.0 * screen_width))
                    pixel_y = int(round(y / 1000.0 * screen_height))
                    return (pixel_x, pixel_y)
                else:
                    # 直接使用像素坐标
                    return (int(x), int(y))
            
            # 尝试解析数字列表
            numbers = [int(float(x)) for x in re.findall(r'-?\d+\.?\d*', response)]
            if len(numbers) >= 2:
                x, y = numbers[0], numbers[1]
                if x <= 1000 and y <= 1000:
                    pixel_x = int(round(x / 1000.0 * screen_width))
                    pixel_y = int(round(y / 1000.0 * screen_height))
                    return (pixel_x, pixel_y)
                else:
                    return (x, y)
            
            return None
            
        except Exception as e:
            logger.error(f"坐标解析失败: {e}")
            return None
    
    async def locate_element(self, target: str, screenshot: bytes) -> Optional[Tuple[int, int]]:
        """
        智能元素定位，优先使用AI定位，回退到传统方法
        多层次定位策略
        """
        try:
            # 首先尝试AI定位
            if self.ai_coordinate_available:
                ai_result = await self.locate_element_with_ai(target, screenshot)
                if ai_result:
                    return ai_result
            
            # 回退到文本定位
            if self.ocr_available:
                text_result = await self.find_text_element(screenshot, target)
                if text_result:
                    return text_result
            
            # 回退到图像匹配（如果target是图像路径）
            if self.image_matching_available and target.endswith(('.png', '.jpg', '.jpeg')):
                image_result = await self.find_image_element(screenshot, target)
                if image_result:
                    return image_result
            
            logger.warning(f"无法定位元素: {target}")
            return None
            
        except Exception as e:
            logger.error(f"元素定位失败: {e}")
            return None
    
    def is_available(self) -> Dict[str, Any]:
        """检查视觉分析器可用性"""
        return {
            "ocr_available": self.ocr_available,
            "image_matching_available": self.image_matching_available,
            "ai_coordinate_available": self.ai_coordinate_available,
            "ready": self.ocr_available or self.image_matching_available or self.ai_coordinate_available
        }