#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Live2D模型管理器

提供模型的批量管理和配置功能
"""
import os
import json
import logging
from typing import Dict, List, Optional, Any
from .auto_configurator import Live2DAutoConfigurator

logger = logging.getLogger(__name__)


class Live2DModelManager:
    """Live2D模型管理器"""

    def __init__(self, models_root_dir: str = None):
        """
        初始化模型管理器

        Args:
            models_root_dir: 模型根目录，默认为 ui/live2d/live2d_models
        """
        if models_root_dir is None:
            models_root_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "live2d_models"
            )
        self.models_root_dir = models_root_dir
        self.configurator = Live2DAutoConfigurator()
        self.models_info = {}

    def scan_models(self) -> List[str]:
        """
        扫描所有可用的模型

        Returns:
            模型路径列表
        """
        models = []

        if not os.path.exists(self.models_root_dir):
            logger.warning(f"模型目录不存在: {self.models_root_dir}")
            return models

        # 扫描所有子目录
        for model_dir in os.listdir(self.models_root_dir):
            model_dir_path = os.path.join(self.models_root_dir, model_dir)

            if not os.path.isdir(model_dir_path):
                continue

            # 查找model3.json文件
            for file in os.listdir(model_dir_path):
                if file.endswith('.model3.json'):
                    model_path = os.path.join(model_dir_path, file)
                    models.append(model_path)
                    logger.debug(f"发现模型: {model_path}")

        logger.debug(f"共扫描到 {len(models)} 个模型")
        return models

    def configure_all_models(self, backup: bool = True) -> Dict[str, bool]:
        """
        配置所有模型

        Args:
            backup: 是否备份原始配置

        Returns:
            配置结果字典 {model_path: success}
        """
        results = {}
        models = self.scan_models()

        for model_path in models:
            logger.debug(f"正在配置模型: {model_path}")
            try:
                success = self.configurator.auto_configure_model(model_path, backup)
                results[model_path] = success

                if success:
                    logger.debug(f"✓ 模型配置成功: {os.path.basename(model_path)}")
                else:
                    logger.warning(f"✗ 模型配置失败: {os.path.basename(model_path)}")

            except Exception as e:
                logger.error(f"配置模型时出错 {model_path}: {e}")
                results[model_path] = False

        # 统计结果
        success_count = sum(1 for v in results.values() if v)
        logger.debug(f"配置完成: {success_count}/{len(models)} 个模型配置成功")

        return results

    def validate_all_models(self) -> Dict[str, Dict]:
        """
        验证所有模型的配置

        Returns:
            验证结果字典
        """
        results = {}
        models = self.scan_models()

        for model_path in models:
            validation = self.configurator.validate_configuration(model_path)
            results[model_path] = validation

            # 输出验证信息
            if validation['valid']:
                logger.debug(f"✓ {os.path.basename(model_path)}: "
                          f"{validation['configured_expressions']} 表情, "
                          f"{validation['configured_motions']} 动作")
            else:
                logger.warning(f"✗ {os.path.basename(model_path)}: "
                             f"{validation.get('error', validation.get('warning', '未知错误'))}")

            # 详细信息
            if validation['missing_files']:
                logger.warning(f"  缺失文件: {len(validation['missing_files'])} 个")
            if validation['unconfigured_files']:
                logger.warning(f"  未配置文件: {len(validation['unconfigured_files'])} 个")

        return results

    def get_model_summary(self) -> Dict[str, Any]:
        """
        获取所有模型的摘要信息

        Returns:
            模型摘要信息
        """
        summary = {
            'total_models': 0,
            'configured_models': 0,
            'models': []
        }

        models = self.scan_models()
        summary['total_models'] = len(models)

        for model_path in models:
            info = self.configurator.get_model_info(model_path)
            validation = self.configurator.validate_configuration(model_path)

            model_summary = {
                'name': os.path.basename(os.path.dirname(model_path)),
                'path': model_path,
                'expressions': len(info['expressions']),
                'motions': sum(info['motions'].values()),
                'configured': validation['valid'] and not validation['unconfigured_files'],
                'has_physics': info['has_physics'],
                'texture_count': info['texture_count']
            }

            summary['models'].append(model_summary)

            if model_summary['configured']:
                summary['configured_models'] += 1

        return summary

    def fix_model(self, model_path: str) -> bool:
        """
        修复单个模型的配置

        Args:
            model_path: 模型路径

        Returns:
            是否成功
        """
        logger.debug(f"开始修复模型: {model_path}")

        # 验证当前状态
        validation_before = self.configurator.validate_configuration(model_path)
        logger.debug(f"修复前: {validation_before['configured_expressions']} 表情, "
                   f"{validation_before['configured_motions']} 动作")

        # 执行自动配置
        success = self.configurator.auto_configure_model(model_path, backup=True)

        if success:
            # 验证修复后状态
            validation_after = self.configurator.validate_configuration(model_path)
            logger.debug(f"修复后: {validation_after['configured_expressions']} 表情, "
                       f"{validation_after['configured_motions']} 动作")

            # 检查改进
            exp_added = validation_after['configured_expressions'] - validation_before['configured_expressions']
            motion_added = validation_after['configured_motions'] - validation_before['configured_motions']

            if exp_added > 0 or motion_added > 0:
                logger.debug(f"✓ 成功添加: {exp_added} 个表情, {motion_added} 个动作")
            else:
                logger.debug("✓ 配置已是最新")

            return True
        else:
            logger.error("✗ 修复失败")
            return False


# 单例实例
_manager_instance = None

def get_manager(models_root_dir: str = None) -> Live2DModelManager:
    """
    获取模型管理器的单例实例

    Args:
        models_root_dir: 模型根目录

    Returns:
        模型管理器实例
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = Live2DModelManager(models_root_dir)
    return _manager_instance


__all__ = ['Live2DModelManager', 'get_manager']