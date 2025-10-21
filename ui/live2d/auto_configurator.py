#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Live2D模型自动配置工具

自动检测并配置Live2D模型的表情和动作，
确保model3.json文件包含所有可用的表情和动作定义
"""
import os
import json
import glob
import logging
from typing import Dict, List, Any, Optional
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


class Live2DAutoConfigurator:
    """Live2D模型自动配置器"""

    def __init__(self):
        """初始化配置器"""
        self.supported_expression_extensions = ['.exp3.json']
        self.supported_motion_extensions = ['.motion3.json']

    def auto_configure_model(self, model_path: str, backup: bool = True) -> bool:
        """
        自动配置Live2D模型

        Args:
            model_path: model3.json文件的路径
            backup: 是否备份原始配置文件

        Returns:
            是否成功配置
        """
        try:
            if not os.path.exists(model_path):
                logger.error(f"模型配置文件不存在: {model_path}")
                return False

            model_dir = os.path.dirname(model_path)
            logger.debug(f"开始自动配置模型: {model_path}")

            # 备份原始配置
            if backup:
                self._backup_config(model_path)

            # 读取现有配置
            with open(model_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 确保基本结构存在
            if 'FileReferences' not in config:
                config['FileReferences'] = {}

            # 自动配置表情
            expressions_updated = self._configure_expressions(config, model_dir)

            # 自动配置动作
            motions_updated = self._configure_motions(config, model_dir)

            # 如果有更新，保存配置
            if expressions_updated or motions_updated:
                with open(model_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent="\t")
                logger.debug(f"模型配置已更新: {model_path}")
                return True
            else:
                logger.debug("模型配置已是最新，无需更新")
                return True

        except Exception as e:
            logger.error(f"自动配置失败: {e}")
            return False

    def _backup_config(self, model_path: str):
        """备份配置文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{model_path}.backup_{timestamp}"
            shutil.copy2(model_path, backup_path)
            logger.debug(f"已备份配置文件到: {backup_path}")
        except Exception as e:
            logger.warning(f"备份配置文件失败: {e}")

    def _configure_expressions(self, config: Dict, model_dir: str) -> bool:
        """
        配置表情

        Returns:
            是否有更新
        """
        updated = False
        expression_dir = os.path.join(model_dir, "Expressions")

        # 另一种常见的目录名称
        if not os.path.exists(expression_dir):
            expression_dir = os.path.join(model_dir, "expressions")

        if not os.path.exists(expression_dir):
            logger.debug("未找到表情目录，跳过表情配置")
            return False

        # 扫描所有表情文件
        expression_files = []
        for ext in self.supported_expression_extensions:
            pattern = os.path.join(expression_dir, f"*{ext}")
            expression_files.extend(glob.glob(pattern))

        if not expression_files:
            logger.debug("未找到表情文件")
            return False

        logger.debug(f"找到 {len(expression_files)} 个表情文件")

        # 获取现有的表情配置
        existing_expressions = config['FileReferences'].get('Expressions', [])
        existing_names = {exp.get('Name') for exp in existing_expressions if isinstance(exp, dict)}

        # 构建新的表情列表
        new_expressions = []

        for exp_file in expression_files:
            exp_name = os.path.basename(exp_file)
            # 移除扩展名作为表情名称
            for ext in self.supported_expression_extensions:
                if exp_name.endswith(ext):
                    exp_name = exp_name[:-len(ext)]
                    break

            # 检查是否已存在
            if exp_name not in existing_names:
                # 计算相对路径
                relative_path = os.path.relpath(exp_file, model_dir).replace('\\', '/')
                new_expressions.append({
                    "Name": exp_name,
                    "File": relative_path
                })
                logger.debug(f"添加新表情: {exp_name} -> {relative_path}")
                updated = True

        # 合并现有和新的表情配置
        if updated:
            all_expressions = list(existing_expressions)
            all_expressions.extend(new_expressions)
            config['FileReferences']['Expressions'] = all_expressions
            logger.debug(f"表情配置已更新，共 {len(all_expressions)} 个表情")

        return updated

    def _configure_motions(self, config: Dict, model_dir: str) -> bool:
        """
        配置动作

        Returns:
            是否有更新
        """
        updated = False
        motion_dir = os.path.join(model_dir, "Motions")

        # 另一种常见的目录名称
        if not os.path.exists(motion_dir):
            motion_dir = os.path.join(model_dir, "motions")

        if not os.path.exists(motion_dir):
            logger.debug("未找到动作目录，跳过动作配置")
            return False

        # 扫描所有动作文件
        motion_files = []
        for ext in self.supported_motion_extensions:
            pattern = os.path.join(motion_dir, f"*{ext}")
            motion_files.extend(glob.glob(pattern))

        if not motion_files:
            logger.debug("未找到动作文件")
            return False

        logger.debug(f"找到 {len(motion_files)} 个动作文件")

        # 获取现有的动作配置
        existing_motions = config['FileReferences'].get('Motions', {})

        # 构建新的动作配置
        new_motions = {}

        for motion_file in motion_files:
            # 获取动作文件名
            motion_name = os.path.basename(motion_file)

            # 尝试从文件名推断动作组
            # 例如: idle_01.motion3.json -> group: idle
            # 或者: IDLE.motion3.json -> group: Idle
            group_name = None

            # 移除扩展名
            for ext in self.supported_motion_extensions:
                if motion_name.endswith(ext):
                    motion_name = motion_name[:-len(ext)]
                    break

            # 尝试识别动作组
            # 模式1: group_index (例如: idle_01)
            if '_' in motion_name:
                parts = motion_name.split('_')
                group_name = parts[0]
            # 模式2: 直接使用文件名作为组名 (例如: IDLE)
            else:
                group_name = motion_name

            # 标准化组名（首字母大写）
            if group_name:
                group_name = group_name.capitalize()

            # 计算相对路径
            relative_path = os.path.relpath(motion_file, model_dir).replace('\\', '/')

            # 添加到对应的组
            if group_name not in existing_motions:
                if group_name not in new_motions:
                    new_motions[group_name] = []
                    logger.debug(f"创建新动作组: {group_name}")

                new_motions[group_name].append({
                    "File": relative_path
                })
                logger.debug(f"添加动作到组 {group_name}: {relative_path}")
                updated = True
            else:
                # 检查这个文件是否已在现有配置中
                existing_files = {m.get('File') for m in existing_motions[group_name] if isinstance(m, dict)}
                if relative_path not in existing_files:
                    if group_name not in new_motions:
                        new_motions[group_name] = list(existing_motions[group_name])
                    new_motions[group_name].append({
                        "File": relative_path
                    })
                    logger.debug(f"添加动作到现有组 {group_name}: {relative_path}")
                    updated = True

        # 合并现有和新的动作配置
        if updated:
            all_motions = dict(existing_motions)
            all_motions.update(new_motions)
            config['FileReferences']['Motions'] = all_motions

            total_count = sum(len(files) for files in all_motions.values())
            logger.debug(f"动作配置已更新，共 {len(all_motions)} 个组，{total_count} 个动作")

        return updated

    def validate_configuration(self, model_path: str) -> Dict[str, Any]:
        """
        验证模型配置的完整性

        Returns:
            验证结果字典
        """
        result = {
            'valid': True,
            'missing_files': [],
            'unconfigured_files': [],
            'configured_expressions': 0,
            'configured_motions': 0,
            'total_expressions': 0,
            'total_motions': 0
        }

        try:
            if not os.path.exists(model_path):
                result['valid'] = False
                result['error'] = f"配置文件不存在: {model_path}"
                return result

            model_dir = os.path.dirname(model_path)

            # 读取配置
            with open(model_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 检查表情配置
            expressions = config.get('FileReferences', {}).get('Expressions', [])
            result['configured_expressions'] = len(expressions)

            # 验证表情文件是否存在
            for exp in expressions:
                exp_file = os.path.join(model_dir, exp.get('File', ''))
                if not os.path.exists(exp_file):
                    result['missing_files'].append(exp_file)
                    result['valid'] = False

            # 检查是否有未配置的表情文件
            expression_dirs = ['Expressions', 'expressions']
            for dir_name in expression_dirs:
                exp_dir = os.path.join(model_dir, dir_name)
                if os.path.exists(exp_dir):
                    all_exp_files = []
                    for ext in self.supported_expression_extensions:
                        all_exp_files.extend(glob.glob(os.path.join(exp_dir, f"*{ext}")))

                    result['total_expressions'] = len(all_exp_files)

                    configured_files = {os.path.join(model_dir, exp.get('File', ''))
                                      for exp in expressions if isinstance(exp, dict)}

                    for exp_file in all_exp_files:
                        if exp_file not in configured_files:
                            result['unconfigured_files'].append(exp_file)
                    break

            # 检查动作配置
            motions = config.get('FileReferences', {}).get('Motions', {})
            motion_count = sum(len(files) for files in motions.values())
            result['configured_motions'] = motion_count

            # 验证动作文件是否存在
            for group, files in motions.items():
                for motion in files:
                    motion_file = os.path.join(model_dir, motion.get('File', ''))
                    if not os.path.exists(motion_file):
                        result['missing_files'].append(motion_file)
                        result['valid'] = False

            # 检查是否有未配置的动作文件
            motion_dirs = ['Motions', 'motions']
            for dir_name in motion_dirs:
                motion_dir = os.path.join(model_dir, dir_name)
                if os.path.exists(motion_dir):
                    all_motion_files = []
                    for ext in self.supported_motion_extensions:
                        all_motion_files.extend(glob.glob(os.path.join(motion_dir, f"*{ext}")))

                    result['total_motions'] = len(all_motion_files)

                    configured_files = set()
                    for files in motions.values():
                        for motion in files:
                            if isinstance(motion, dict):
                                configured_files.add(os.path.join(model_dir, motion.get('File', '')))

                    for motion_file in all_motion_files:
                        if motion_file not in configured_files:
                            result['unconfigured_files'].append(motion_file)
                    break

            # 判断是否完全配置
            if result['unconfigured_files']:
                result['valid'] = False
                result['warning'] = f"有 {len(result['unconfigured_files'])} 个文件未配置"

            return result

        except Exception as e:
            result['valid'] = False
            result['error'] = str(e)
            return result

    def get_model_info(self, model_path: str) -> Dict[str, Any]:
        """
        获取模型的详细信息

        Returns:
            模型信息字典
        """
        info = {
            'model_path': model_path,
            'expressions': [],
            'motions': {},
            'has_physics': False,
            'has_display_info': False,
            'texture_count': 0
        }

        try:
            if not os.path.exists(model_path):
                info['error'] = "模型文件不存在"
                return info

            model_dir = os.path.dirname(model_path)

            # 读取配置
            with open(model_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 获取表情信息
            expressions = config.get('FileReferences', {}).get('Expressions', [])
            info['expressions'] = [exp.get('Name') for exp in expressions if isinstance(exp, dict)]

            # 获取动作信息
            motions = config.get('FileReferences', {}).get('Motions', {})
            info['motions'] = {group: len(files) for group, files in motions.items()}

            # 其他信息
            file_refs = config.get('FileReferences', {})
            info['has_physics'] = 'Physics' in file_refs
            info['has_display_info'] = 'DisplayInfo' in file_refs
            info['texture_count'] = len(file_refs.get('Textures', []))

            return info

        except Exception as e:
            info['error'] = str(e)
            return info


# 导出主要类
__all__ = ['Live2DAutoConfigurator']