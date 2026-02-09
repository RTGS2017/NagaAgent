#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视觉识别Agent - 提供屏幕截图、AI图像分析、OCR识别功能
"""

import json
import logging
from typing import Dict, Any

from nagaagent_core.vendors.agents import Agent, ComputerTool
from .vision_tools import VisionTools

logger = logging.getLogger(__name__)


class VisionAgent(Agent):
    """视觉识别Agent - 提供屏幕截图、AI图像分析、OCR识别功能"""
    
    def __init__(self):
        """初始化视觉识别Agent"""
        self._tool = VisionTools()
        super().__init__(
            name="Vision Agent",
            instructions="视觉识别智能体，提供屏幕截图、AI图像分析和OCR文字识别功能",
            tools=[ComputerTool(self._tool)],
            model="vision-use-preview"
        )
        logger.info("✅ VisionAgent初始化完成")
    
    async def handle_handoff(self, task: Dict[str, Any]) -> str:
        """处理handoff请求 - 视觉识别工具调用入口
        
        参数:
            task: 包含tool_name和其他参数的字典
        
        返回:
            JSON格式的处理结果
        """
        try:
            # 获取工具名称
            tool_name = task.get("tool_name")
            if not tool_name:
                return json.dumps({
                    "status": "error",
                    "message": "缺少tool_name参数",
                    "data": {}
                }, ensure_ascii=False)
            
            # 仅保留一键流水线工具
            if tool_name in ["vision_pipeline"]:
                result = await self._handle_vision_pipeline(task)
            else:
                result = {
                    "status": "error",
                    "message": f"未知的工具名称: {tool_name}",
                    "data": {}
                }
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"视觉识别处理失败: {e}")
            return json.dumps({
                "status": "error",
                "message": f"处理失败: {str(e)}",
                "data": {}
            }, ensure_ascii=False)
    
    async def _handle_vision_pipeline(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """一键视觉识别流水线：截图 → 视觉分析 → (可选)OCR"""
        try:
            user_content = task.get("user_content", "分析当前屏幕的内容")
            with_ocr = bool(task.get("with_ocr", False))
            filename = task.get("filename", "imgs/screen_opencv.png")
            bbox = task.get("bbox")
            lang = task.get("lang", "chi_sim")

            if not user_content:
                return {
                    "status": "error",
                    "message": "缺少user_content参数",
                    "data": {}
                }

            pipeline_result = self._tool.vision_pipeline(
                user_content=user_content,
                with_ocr=with_ocr,
                filename=filename,
                bbox=bbox,
                lang=lang,
            )

            return pipeline_result

        except Exception as e:
            return {
                "status": "error",
                "message": f"视觉识别流水线失败: {str(e)}",
                "data": {}
            }

