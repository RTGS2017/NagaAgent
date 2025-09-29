"""
视觉分析器 - 基于博弈论的视觉识别功能
提供OCR、图像匹配、元素定位等功能
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image
import io
import base64

# 配置日志
logger = logging.getLogger(__name__)

class VisualAnalyzer:
    """视觉分析器"""
    
    def __init__(self):
        """初始化视觉分析器"""
        self.ocr_available = False
        self.image_matching_available = False
        
        # 尝试导入OCR库
        try:
            import pytesseract
            self.ocr_available = True
            logger.info("OCR功能已启用")
        except ImportError:
            logger.warning("pytesseract未安装，OCR功能不可用")
        
        # 尝试导入图像匹配库
        try:
            import cv2
            import numpy as np
            self.cv2 = cv2
            self.np = np
            self.image_matching_available = True
            logger.info("图像匹配功能已启用")
        except ImportError:
            logger.warning("opencv-python未安装，图像匹配功能不可用")
    
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
            import pytesseract
            
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
    
    def is_available(self) -> Dict[str, Any]:
        """检查视觉分析器可用性"""
        return {
            "ocr_available": self.ocr_available,
            "image_matching_available": self.image_matching_available,
            "ready": self.ocr_available or self.image_matching_available
        }