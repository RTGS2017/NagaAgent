#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live2D渲染器（精简版）
负责Live2D模型的加载和渲染
"""

import os
import sys
import logging
import json
import glob
from typing import Optional, Callable, Dict, List, Any
from enum import Enum
from .auto_configurator import Live2DAutoConfigurator

logger = logging.getLogger("live2d.renderer")

# 尝试导入Live2D模块 - 避免与本地目录冲突
LIVE2D_AVAILABLE = False
live2d = None

try:
    import sys
    import os

    # 保存当前路径
    original_path = sys.path.copy()

    # 临时移除当前目录和父目录，避免导入本地的live2d目录
    current_dir = os.path.dirname(os.path.abspath(__file__))  # ui/live2d
    parent_dir = os.path.dirname(current_dir)  # ui
    grandparent_dir = os.path.dirname(parent_dir)  # NagaAgent

    # 创建需要临时移除的路径列表
    paths_to_remove = [
        current_dir,
        parent_dir,
        grandparent_dir,
        os.getcwd(),
        '.',
        ''
    ]

    # 临时移除这些路径
    temp_sys_path = [p for p in sys.path if p not in paths_to_remove]
    sys.path = temp_sys_path

    # 现在导入系统的live2d包（不会找到本地的ui/live2d）
    import live2d.v3 as live2d_v3
    live2d = live2d_v3
    LIVE2D_AVAILABLE = True
    logger.debug("Live2D模块加载成功")

    # 恢复原始路径
    sys.path = original_path

except ImportError as e:
    # 恢复路径（如果导入失败）
    if 'original_path' in locals():
        sys.path = original_path
    LIVE2D_AVAILABLE = False
    logger.warning(f"Live2D模块未安装: {e}")


class RendererState(Enum):
    """渲染器状态"""
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    MODEL_LOADED = "model_loaded"
    ERROR = "error"


class Live2DRenderer:
    """Live2D渲染器（精简版）"""

    def __init__(self, scale_factor: float = 1.0):
        """初始化渲染器"""
        self.model = None
        self.state = RendererState.UNINITIALIZED
        self.model_path = None
        self.width = 100
        self.height = 200
        self.scale_factor = scale_factor
        self.loaded_expressions = {}  # 初始化表情映射表

        # 加载emoji映射配置
        self.emoji_mapping = self._load_emoji_mapping()

        # 错误处理相关
        self._update_errors = 0
        self._draw_errors = 0
        self._max_errors_before_reset = 10

    def initialize(self) -> bool:
        """初始化Live2D"""
        if not LIVE2D_AVAILABLE:
            logger.error("Live2D模块不可用")
            self.state = RendererState.ERROR
            return False

        try:
            live2d.init()
            live2d.glewInit()
            self.state = RendererState.INITIALIZED
            logger.debug("Live2D渲染器初始化成功")
            return True

        except Exception as e:
            logger.error(f"Live2D初始化失败: {e}")
            self.state = RendererState.ERROR
            return False

    def load_model(self, model_path: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """加载Live2D模型 - 带自动配置功能"""
        if not LIVE2D_AVAILABLE or self.state == RendererState.UNINITIALIZED:
            logger.error("渲染器未初始化")
            return False

        model_path = os.path.normpath(model_path)
        if not os.path.exists(model_path):
            logger.error(f"模型文件不存在: {model_path}")
            return False

        try:
            if progress_callback:
                progress_callback(0.05)

            # 自动配置模型（如果需要）
            logger.debug("检查模型配置...")
            auto_config = Live2DAutoConfigurator()

            # 先验证配置
            validation = auto_config.validate_configuration(model_path)
            if validation['unconfigured_files']:
                logger.debug(f"发现 {len(validation['unconfigured_files'])} 个未配置的文件，开始自动配置...")
                if auto_config.auto_configure_model(model_path, backup=True):
                    logger.debug("模型自动配置成功")
                    # 重新验证
                    validation = auto_config.validate_configuration(model_path)
                    logger.debug(f"配置后状态: {validation['configured_expressions']} 个表情, {validation['configured_motions']} 个动作")
                else:
                    logger.warning("自动配置失败，继续使用现有配置")
            else:
                logger.debug(f"模型配置完整: {validation['configured_expressions']} 个表情, {validation['configured_motions']} 个动作")

            if progress_callback:
                progress_callback(0.1)

            self.model = live2d.LAppModel()

            if progress_callback:
                progress_callback(0.3)

            # 加载模型配置（包含自动配置的表情和动作）
            self.model.LoadModelJson(model_path)

            if progress_callback:
                progress_callback(0.6)

            # 加载动作文件
            model_dir = os.path.dirname(model_path)
            self._load_motions(model_dir)

            # 加载表情文件
            self._load_expressions(model_dir)

            # 应用缩放
            scaled_width = int(self.width * self.scale_factor)
            scaled_height = int(self.height * self.scale_factor)
            self.model.Resize(scaled_width, scaled_height)

            # 基本设置
            self.model.SetAutoBlinkEnable(False)
            self.model.SetAutoBreathEnable(True)

            # 尝试关闭水印
            try:
                self.model.SetParameterValue("ParamWatermarkOFF", 1.0)
            except:
                pass

            if progress_callback:
                progress_callback(1.0)

            self.model_path = model_path
            self.state = RendererState.MODEL_LOADED
            logger.debug(f"模型加载成功: {model_path}")
            return True

        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            self.model = None
            self.state = RendererState.INITIALIZED
            return False

    def _load_motions(self, model_dir: str):
        """加载动作文件"""
        motion_dir = os.path.join(model_dir, "Motions")
        if not os.path.exists(motion_dir):
            return

        motion_files = glob.glob(os.path.join(motion_dir, "*.motion3.json"))
        for motion_file in motion_files:
            try:
                motion_name = os.path.basename(motion_file).replace(".motion3.json", "")
                # 尝试注册动作到模型
                # 注意：live2d-py可能需要通过model3.json配置来加载动作
                logger.debug(f"发现动作文件: {motion_name} - {motion_file}")
            except Exception as e:
                logger.debug(f"动作文件处理失败 {motion_file}: {e}")

    def _load_expressions(self, model_dir: str):
        """从模型配置中获取已加载的表情"""
        self.loaded_expressions = {}

        # 尝试从模型获取已加载的表情
        try:
            if hasattr(self.model, 'GetExpressionIds'):
                loaded_ids = self.model.GetExpressionIds()
                if loaded_ids:
                    self.loaded_expressions = {exp_id: exp_id for exp_id in loaded_ids}
                    logger.debug(f"从模型获取到 {len(self.loaded_expressions)} 个表情")
                    return
        except Exception as e:
            logger.debug(f"无法从模型获取表情: {e}")

        # 如果无法从模型获取，扫描表情目录
        self._scan_expression_dir(model_dir)

    def _scan_expression_dir(self, model_dir: str):
        """扫描表情目录并记录表情文件"""
        expression_dir = os.path.join(model_dir, "Expressions")
        if not os.path.exists(expression_dir):
            return

        expression_files = glob.glob(os.path.join(expression_dir, "*.exp3.json"))
        for exp_file in expression_files:
            exp_name = os.path.basename(exp_file).replace(".exp3.json", "")
            self.loaded_expressions[exp_name] = exp_name

        if expression_files:
            logger.debug(f"从目录扫描到 {len(self.loaded_expressions)} 个表情")

    def _handle_operation_error(self, error_counter_name: str, error: Exception, operation_name: str):
        """通用的操作错误处理"""
        counter = getattr(self, error_counter_name)
        counter += 1
        setattr(self, error_counter_name, counter)

        if counter < 3:
            logger.error(f"模型{operation_name}失败: {error}")
        elif counter == 3:
            logger.warning(f"模型{operation_name}持续失败，后续错误将静默处理")

        # 检查是否需要重置模型
        if counter >= self._max_errors_before_reset:
            logger.error(f"模型{operation_name}错误过多，尝试重置状态")
            self._reset_model_state()

    def update(self):
        """更新模型状态"""
        if not self.has_model():
            return

        try:
            self.model.Update()
            self._update_errors = 0
        except Exception as e:
            self._handle_operation_error('_update_errors', e, '更新')

    def draw(self):
        """绘制模型"""
        if not self.has_model():
            return

        try:
            live2d.clearBuffer()
            self.model.Draw()
            self._draw_errors = 0
        except Exception as e:
            self._handle_operation_error('_draw_errors', e, '绘制')

    def _reset_model_state(self):
        """重置模型状态"""
        try:
            if self.model_path and self.state == RendererState.MODEL_LOADED:
                logger.debug("正在重置模型状态...")
                # 保存当前路径
                path = self.model_path
                # 清理现有模型
                if self.model:
                    self.model = None
                # 重新加载模型
                self.load_model(path)
                # 重置错误计数
                self._update_errors = 0
                self._draw_errors = 0
                logger.debug("模型状态重置完成")
        except Exception as e:
            logger.error(f"模型状态重置失败: {e}")
            self.state = RendererState.ERROR

    def resize(self, width: int, height: int):
        """调整模型大小"""
        if width <= 0 or height <= 0:
            return

        self.width = width
        self.height = height

        if self.has_model():
            try:
                scaled_width = int(width * self.scale_factor)
                scaled_height = int(height * self.scale_factor)
                self.model.Resize(scaled_width, scaled_height)
            except Exception as e:
                logger.error(f"调整大小失败: {e}")

    def set_scale_factor(self, scale_factor: float):
        """设置缩放因子"""
        if scale_factor <= 0:
            return

        self.scale_factor = scale_factor
        self.resize(self.width, self.height)

    def set_parameter(self, param_id: str, value: float, validate: bool = False):
        """设置模型参数 - 带错误保护"""
        if not self.has_model():
            return

        try:
            # 参数值范围限制
            value = max(-10.0, min(10.0, value))
            self.model.SetParameterValue(param_id, value)
        except Exception as e:
            # 静默处理参数设置错误，避免日志泛滥
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"设置参数失败 {param_id}: {e}")

    def get_parameter(self, param_id: str) -> float:
        """获取模型参数"""
        if not self.has_model():
            return 0.0

        try:
            return self.model.GetParameterValue(param_id)
        except:
            return 0.0

    def trigger_motion(self, group: str, index: int = 0, priority: int = 3):
        """触发动作"""
        if not self.has_model():
            return

        try:
            self.model.StartMotion(group, index, priority)
        except Exception as e:
            logger.debug(f"触发动作失败 {group}: {e}")

    def trigger_expression(self, expression_id: str):
        """触发表情"""
        if not self.has_model():
            return

        # 检查表情是否存在
        if expression_id not in self.loaded_expressions:
            logger.debug(f"表情 '{expression_id}' 不存在")
            return

        try:
            self.model.SetExpression(expression_id)
            logger.debug(f"触发表情: '{expression_id}'")
        except Exception as e:
            logger.error(f"触发表情异常 '{expression_id}': {e}")

    def cleanup(self):
        """清理资源"""
        try:
            if self.model:
                self.model = None
                logger.debug("模型资源已清理")

            self.state = RendererState.UNINITIALIZED
            self.model_path = None

        except Exception as e:
            logger.error(f"资源清理失败: {e}")

    def is_available(self) -> bool:
        """检查是否可用"""
        return LIVE2D_AVAILABLE and self.state != RendererState.UNINITIALIZED

    def has_model(self) -> bool:
        """检查是否已加载模型"""
        return self.model is not None and self.state == RendererState.MODEL_LOADED

    def get_error_reason(self) -> str:
        """获取错误原因"""
        if not LIVE2D_AVAILABLE:
            return "Live2D模块未安装"
        if self.state == RendererState.UNINITIALIZED:
            return "渲染器未初始化"
        if self.state == RendererState.ERROR:
            return "渲染器错误"
        if not self.has_model():
            return "模型未加载"
        return ""

    def _load_emoji_mapping(self) -> Dict[str, Any]:
        """加载emoji映射配置"""
        try:
            emoji_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'emoji_mapping.json')
            if os.path.exists(emoji_file):
                with open(emoji_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.debug(f"Emoji映射文件不存在: {emoji_file}")
        except Exception as e:
            logger.debug(f"加载emoji映射失败: {e}")

        # 返回默认映射
        return {
            "motion_emoji_map": {"default": "🎭"},
            "expression_emoji_map": {"default": "😀"},
            "custom_model_emoji": {}
        }

    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            'model_path': self.model_path,
            'width': self.width,
            'height': self.height,
            'scale_factor': self.scale_factor,
            'state': self.state.value,
            'model_loaded': self.has_model()
        }

    def _get_emoji(self, name: str, type: str, default_emoji: str) -> str:
        """获取动作或表情对应的emoji"""
        if not self.model_path:
            return default_emoji

        # 获取当前模型的自定义映射
        model_name = os.path.basename(os.path.dirname(self.model_path))
        custom_mapping = self.emoji_mapping.get("custom_model_emoji", {}).get(model_name, {}).get(f"{type}s", {})

        # 优先使用模型特定的映射
        if name in custom_mapping:
            return custom_mapping[name]

        # 然后使用通用映射
        emoji_map = self.emoji_mapping.get(f"{type}_emoji_map", {})

        # 尝试完全匹配
        if name in emoji_map:
            return emoji_map[name]

        # 尝试部分匹配
        name_lower = name.lower()
        for key, emoji in emoji_map.items():
            if key.lower() in name_lower:
                return emoji

        # 返回默认图标
        return emoji_map.get("default", default_emoji)

    def _get_emoji_for_motion(self, motion_name: str) -> str:
        """获取动作对应的emoji"""
        return self._get_emoji(motion_name, "motion", "🎭")

    def _get_emoji_for_expression(self, exp_name: str) -> str:
        """获取表情对应的emoji"""
        return self._get_emoji(exp_name, "expression", "😀")

    def detect_model_actions(self) -> Dict[str, List[Dict[str, str]]]:
        """从model3.json和目录扫描检测模型定义的动作和表情"""
        if not self.model_path:
            return {"motions": [], "expressions": []}

        result = {"motions": [], "expressions": []}
        model_dir = os.path.dirname(self.model_path)

        # 首先尝试从model3.json读取
        try:
            # 读取model3.json
            with open(self.model_path, 'r', encoding='utf-8') as f:
                model_config = json.load(f)

            # 解析Motions
            if "FileReferences" in model_config and "Motions" in model_config["FileReferences"]:
                motions_dict = model_config["FileReferences"]["Motions"]
                for motion_group, motion_list in motions_dict.items():
                    display_name = motion_group.replace("_", " ").title()

                    # 使用新的emoji获取方法
                    emoji = self._get_emoji_for_motion(motion_group)

                    result["motions"].append({
                        "name": motion_group,
                        "display": display_name,
                        "icon": emoji,
                        "group": motion_group
                    })

            # 解析Expressions - 从model3.json
            expressions_from_config = []
            if "FileReferences" in model_config and "Expressions" in model_config["FileReferences"]:
                expressions = model_config["FileReferences"]["Expressions"]
                for exp in expressions:
                    exp_name = exp.get("Name", "")
                    expressions_from_config.append(exp_name)

        except Exception as e:
            logger.debug(f"解析model3.json失败: {e}")

        # 然后扫描目录中的所有表情文件（补充model3.json中可能遗漏的）
        expression_dir = os.path.join(model_dir, "Expressions")
        if os.path.exists(expression_dir):
            expression_files = glob.glob(os.path.join(expression_dir, "*.exp3.json"))
            all_expressions = set()

            for exp_file in expression_files:
                exp_name = os.path.basename(exp_file).replace(".exp3.json", "")
                all_expressions.add(exp_name)

            # 为每个表情创建条目
            for exp_name in sorted(all_expressions):
                # 处理显示名称
                display_name = exp_name.replace("【", "").replace("】", " ").replace("_", " ")

                # 使用新的emoji获取方法
                emoji = self._get_emoji_for_expression(exp_name)

                result["expressions"].append({
                    "name": exp_name,
                    "display": display_name,
                    "icon": emoji
                })

        logger.debug(f"从model3.json和目录扫描检测到动作: {len(result['motions'])}个, 表情: {len(result['expressions'])}个")
        return result
