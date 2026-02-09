#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视觉识别工具类 - 屏幕截图、AI图像分析、OCR识别
"""

import cv2
import numpy as np
import base64
import os
import logging
import subprocess
from PIL import ImageGrab
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)


class VisionTools:
    """视觉识别工具类"""
    
    def __init__(self):
        """初始化视觉识别工具"""
        self.imgs_dir = Path("imgs")
        self.imgs_dir.mkdir(exist_ok=True)
        # 默认全屏区域，每次启动刷新一次
        self.default_bbox = self._get_fullscreen_bbox()
        logger.info("视觉识别工具初始化完成")
    
    def refresh_fullscreen_bbox(self):
        """刷新默认全屏区域（可在需要时手动调用）"""
        self.default_bbox = self._get_fullscreen_bbox()
        return self.default_bbox
    
    def _get_fullscreen_bbox(self):
        """获取当前屏幕的全屏bbox"""
        try:
            grab = ImageGrab.grab()
            return grab.getbbox()  # (left, top, right, bottom)
        except Exception as e:
            logger.warning(f"获取全屏bbox失败: {e}")
            return None
    
    def capture_screen(self, filename: Optional[str] = None, bbox: Optional[List[int]] = None) -> str:
        """屏幕截图功能
        
        参数:
            filename: 保存的文件路径（可选，默认: imgs/screen_opencv.png）
            bbox: 截图区域 (left, top, right, bottom)（可选）
        
        返回:
            保存的文件路径
        """
        try:
            if filename is None:
                filename = str(self.imgs_dir / "screen_opencv.png")
            
            # 确保目录存在
            file_path = Path(filename)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 截取屏幕（未传bbox则使用当前全屏bbox，每次调用都会用最新的全屏尺寸）
            use_bbox = bbox if bbox else self._get_fullscreen_bbox()
            screenshot = ImageGrab.grab(bbox=use_bbox) if use_bbox else ImageGrab.grab()
            
            # 转换为numpy数组
            img_np = np.array(screenshot)
            
            # 转换颜色格式 (RGB -> BGR)
            frame = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            
            # 保存图像
            cv2.imwrite(str(file_path), frame)
            logger.info(f"截图已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"截图失败: {e}")
            raise Exception(f"截图失败: {str(e)}")
    
    def encode_image(self, image_path: str) -> str:
        """将图像编码为Base64格式
        
        参数:
            image_path: 图像文件路径
        
        返回:
            Base64编码的字符串
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"图像编码失败: {e}")
            raise Exception(f"图像编码失败: {str(e)}")
    
    def analyze_image(self, user_content: str, image_path: str = "imgs/screen_opencv.png") -> str:
        """AI图像分析功能
        
        参数:
            user_content: 用户关于图像的问题或分析要求
            image_path: 图像文件路径（可选，默认: imgs/screen_opencv.png）
        
        返回:
            AI分析结果文本
        """
        try:
            from openai import OpenAI
            from dotenv import load_dotenv
            
            load_dotenv()
            
            # 检查文件是否存在
            if not os.path.exists(image_path):
                return f"错误: 图像文件不存在: {image_path}"
            
            # Base64编码图像
            base64_image = self.encode_image(image_path)
            
            # 初始化OpenAI客户端（阿里云DashScope）
            api_key = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
            if not api_key:
                return "错误: 未配置ALIBABA_CLOUD_ACCESS_KEY_ID环境变量"
            
            client = OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            
            # 调用视觉理解模型
            completion = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_content
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
            )
            
            # 提取分析结果
            content = completion.choices[0].message.content
            logger.info(f"AI图像分析完成，结果长度: {len(content)}")
            return content
            
        except Exception as e:
            logger.error(f"AI图像分析失败: {e}")
            return f"AI图像分析失败: {str(e)}"
    
    def ocr_image(self, image_path: str, lang: str = "chi_sim") -> str:
        """OCR文字识别功能
        
        参数:
            image_path: 图像文件路径
            lang: 识别语言（默认: chi_sim，支持: chi_sim/eng/chi_sim+eng）
        
        返回:
            识别出的文字内容
        """
        try:
            import pytesseract
            import subprocess
            
            # 检查文件是否存在
            if not os.path.exists(image_path):
                return f"错误: 图像文件不存在: {image_path}"
            
            # 自动检测Tesseract路径
            tesseract_path = self._find_tesseract_path()
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            else:
                return "错误: 未找到Tesseract OCR安装。请先安装Tesseract OCR软件。"
            
            # 图像预处理
            processed = self._preprocess_image(image_path)
            
            # OCR识别
            from PIL import Image
            pil_img = Image.fromarray(processed)
            text = pytesseract.image_to_string(pil_img, lang=lang)
            
            result = text.strip()
            logger.info(f"OCR识别完成，识别文字长度: {len(result)}")
            return result if result else "未识别到文字内容"
            
        except ImportError:
            return "错误: 未安装pytesseract库，请运行: pip install pytesseract"
        except Exception as e:
            logger.error(f"OCR识别失败: {e}")
            return f"OCR识别失败: {str(e)}"

    def vision_pipeline(
        self,
        user_content: str,
        with_ocr: bool = False,
        filename: str = "imgs/screen_opencv.png",
        bbox: Optional[List[int]] = None,
        lang: str = "chi_sim",
    ) -> dict:
        """一键视觉识别流水线：截图 → 视觉分析 → (可选)OCR，返回结构化结果"""
        # 1) 截图
        screenshot_path = self.capture_screen(filename=filename, bbox=bbox)

        # 2) 视觉分析
        analysis = self.analyze_image(user_content, screenshot_path)

        # 3) 可选OCR
        ocr_text = None
        if with_ocr:
            ocr_text = self.ocr_image(screenshot_path, lang=lang)

        return {
            "status": "success",
            "message": "视觉识别流水线完成",
            "data": {
                "screenshot_path": screenshot_path,
                "analysis": analysis,
                "ocr_text": ocr_text,
                "user_content": user_content,
                "with_ocr": with_ocr,
                "bbox": bbox,
                "lang": lang,
            },
        }
    
    def _find_tesseract_path(self) -> Optional[str]:
        """自动检测Tesseract OCR路径"""
        common_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        
        # 检查常见路径
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        # 尝试通过命令查找
        try:
            if os.name == 'nt':  # Windows
                result = subprocess.run(['where', 'tesseract'], capture_output=True, text=True)
            else:  # Unix-like
                result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True)
            
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return None
    
    def _preprocess_image(self, img_path: str) -> np.ndarray:
        """图像预处理：灰度 → 二值化 → 去噪，提升OCR准确率"""
        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 二值化
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        # 中值滤波去噪
        denoise = cv2.medianBlur(binary, 3)
        return denoise

