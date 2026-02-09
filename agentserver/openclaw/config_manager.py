#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenClaw 配置管理器
安全地修改 ~/.openclaw/openclaw.json 配置文件
只允许修改白名单中的字段
"""

import json
import secrets
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConfigUpdateResult:
    """配置更新结果"""
    success: bool
    message: str
    field: str
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "field": self.field,
            "old_value": self.old_value,
            "new_value": self.new_value
        }


class OpenClawConfigManager:
    """
    OpenClaw 配置管理器

    安全地管理 ~/.openclaw/openclaw.json 配置
    只允许修改白名单中的字段，防止误操作
    """

    OPENCLAW_DIR = Path.home() / ".openclaw"
    OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"

    # ============ 白名单配置 ============
    # 只有这些字段可以被 Naga 修改

    # 可直接修改的字段（完整路径）
    ALLOWED_FIELDS: Set[str] = {
        # 模型配置
        "agents.defaults.model.primary",
        "agents.defaults.model.fallbacks",

        # Hooks 配置
        "hooks.enabled",
        "hooks.token",

        # Skills 配置
        "skills.entries",

        # 消息配置
        "messages.ackReactionScope",

        # 工具配置
        "tools.allow",
        "tools.deny",

        # Agent 并发
        "agents.defaults.maxConcurrent",
        "agents.defaults.subagents.maxConcurrent",
    }

    # 禁止修改的字段（安全敏感）
    FORBIDDEN_FIELDS: Set[str] = {
        "gateway.auth.token",
        "gateway.auth.password",
        "auth.profiles",
    }

    # 可添加/修改的模型别名
    ALLOWED_MODEL_ALIAS_PATTERN = "agents.defaults.models.*"

    def __init__(self):
        self._config: Optional[Dict[str, Any]] = None
        self._load_config()

    def _load_config(self) -> bool:
        """加载配置文件"""
        if not self.OPENCLAW_CONFIG.exists():
            logger.warning("OpenClaw 配置文件不存在")
            return False

        try:
            with open(self.OPENCLAW_CONFIG, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            return True
        except Exception as e:
            logger.error(f"加载 OpenClaw 配置失败: {e}")
            return False

    def _save_config(self) -> bool:
        """保存配置文件"""
        if self._config is None:
            return False

        try:
            # 先备份
            if self.OPENCLAW_CONFIG.exists():
                backup_path = self.OPENCLAW_CONFIG.with_suffix('.json.bak')
                self.OPENCLAW_CONFIG.rename(backup_path)

            # 写入新配置
            with open(self.OPENCLAW_CONFIG, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

            # 更新 meta
            self._update_meta()

            return True
        except Exception as e:
            logger.error(f"保存 OpenClaw 配置失败: {e}")
            return False

    def _update_meta(self):
        """更新元信息"""
        if self._config is None:
            return

        if "meta" not in self._config:
            self._config["meta"] = {}

        self._config["meta"]["lastTouchedAt"] = datetime.now().isoformat()
        self._config["meta"]["lastTouchedBy"] = "naga"

    def _is_field_allowed(self, field_path: str) -> bool:
        """检查字段是否允许修改"""
        # 检查禁止列表
        for forbidden in self.FORBIDDEN_FIELDS:
            if field_path.startswith(forbidden):
                return False

        # 检查允许列表
        if field_path in self.ALLOWED_FIELDS:
            return True

        # 检查模型别名模式
        if field_path.startswith("agents.defaults.models."):
            return True

        # 检查 skills.entries 下的字段
        if field_path.startswith("skills.entries."):
            return True

        return False

    def _get_nested_value(self, path: str) -> Any:
        """获取嵌套字段值"""
        if self._config is None:
            return None

        keys = path.split('.')
        current = self._config

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current

    def _set_nested_value(self, path: str, value: Any) -> bool:
        """设置嵌套字段值"""
        if self._config is None:
            return False

        keys = path.split('.')
        current = self._config

        # 导航到父级
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # 设置值
        current[keys[-1]] = value
        return True

    # ============ 公共 API ============

    def get(self, field_path: str) -> Any:
        """
        获取配置值

        Args:
            field_path: 字段路径，如 "agents.defaults.model.primary"

        Returns:
            字段值
        """
        self._load_config()
        return self._get_nested_value(field_path)

    def set(self, field_path: str, value: Any) -> ConfigUpdateResult:
        """
        设置配置值（只允许白名单字段）

        Args:
            field_path: 字段路径
            value: 新值

        Returns:
            ConfigUpdateResult 对象
        """
        # 检查权限
        if not self._is_field_allowed(field_path):
            return ConfigUpdateResult(
                success=False,
                message=f"字段 '{field_path}' 不允许修改",
                field=field_path
            )

        # 加载最新配置
        self._load_config()

        # 获取旧值
        old_value = self._get_nested_value(field_path)

        # 设置新值
        if not self._set_nested_value(field_path, value):
            return ConfigUpdateResult(
                success=False,
                message="设置字段值失败",
                field=field_path
            )

        # 保存
        if not self._save_config():
            return ConfigUpdateResult(
                success=False,
                message="保存配置文件失败",
                field=field_path
            )

        logger.info(f"OpenClaw 配置已更新: {field_path} = {value}")

        return ConfigUpdateResult(
            success=True,
            message=f"配置已更新: {field_path}",
            field=field_path,
            old_value=old_value,
            new_value=value
        )

    # ============ 便捷方法 ============

    def set_primary_model(self, model: str) -> ConfigUpdateResult:
        """
        设置默认模型

        Args:
            model: 模型标识符，如 "zai/glm-4.7", "anthropic/claude-sonnet"

        Returns:
            ConfigUpdateResult
        """
        return self.set("agents.defaults.model.primary", model)

    def add_model_alias(self, model: str, alias: str) -> ConfigUpdateResult:
        """
        添加模型别名

        Args:
            model: 模型标识符
            alias: 别名

        Returns:
            ConfigUpdateResult
        """
        field_path = f"agents.defaults.models.{model}"
        return self.set(field_path, {"alias": alias})

    def set_hooks_enabled(self, enabled: bool) -> ConfigUpdateResult:
        """启用/禁用 Hooks"""
        return self.set("hooks.enabled", enabled)

    def set_hooks_token(self, token: str) -> ConfigUpdateResult:
        """设置 Hooks token"""
        return self.set("hooks.token", token)

    def generate_hooks_token(self) -> str:
        """生成随机 Hooks token"""
        return secrets.token_hex(24)

    def enable_skill(self, skill_name: str, enabled: bool = True) -> ConfigUpdateResult:
        """
        启用/禁用 Skill

        Args:
            skill_name: Skill 名称
            enabled: 是否启用

        Returns:
            ConfigUpdateResult
        """
        field_path = f"skills.entries.{skill_name}"
        return self.set(field_path, {"enabled": enabled})

    def set_max_concurrent(self, value: int) -> ConfigUpdateResult:
        """设置最大并发数"""
        if value < 1 or value > 16:
            return ConfigUpdateResult(
                success=False,
                message="并发数必须在 1-16 之间",
                field="agents.defaults.maxConcurrent"
            )
        return self.set("agents.defaults.maxConcurrent", value)

    # ============ 批量操作 ============

    def batch_update(self, updates: Dict[str, Any]) -> List[ConfigUpdateResult]:
        """
        批量更新配置

        Args:
            updates: {字段路径: 新值} 字典

        Returns:
            ConfigUpdateResult 列表
        """
        results = []
        for field_path, value in updates.items():
            result = self.set(field_path, value)
            results.append(result)
        return results

    # ============ 配置模板 ============

    def apply_naga_integration_template(self, hooks_token: Optional[str] = None) -> List[ConfigUpdateResult]:
        """
        应用 Naga 集成配置模板

        设置 Naga 与 OpenClaw 通信所需的最小配置

        Args:
            hooks_token: Hooks token，不传则自动生成

        Returns:
            ConfigUpdateResult 列表
        """
        if hooks_token is None:
            hooks_token = self.generate_hooks_token()

        updates = {
            "hooks.enabled": True,
            "hooks.token": hooks_token,
        }

        return self.batch_update(updates)

    def get_current_config_summary(self) -> Dict[str, Any]:
        """
        获取当前配置摘要（只返回安全信息）

        Returns:
            配置摘要
        """
        self._load_config()

        if self._config is None:
            return {"error": "配置未加载"}

        return {
            "primary_model": self._get_nested_value("agents.defaults.model.primary"),
            "hooks_enabled": self._get_nested_value("hooks.enabled"),
            "hooks_token_set": bool(self._get_nested_value("hooks.token")),
            "gateway_port": self._get_nested_value("gateway.port"),
            "workspace": self._get_nested_value("agents.defaults.workspace"),
            "max_concurrent": self._get_nested_value("agents.defaults.maxConcurrent"),
        }


# 全局配置管理器实例
_config_manager: Optional[OpenClawConfigManager] = None


def get_openclaw_config_manager() -> OpenClawConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = OpenClawConfigManager()
    return _config_manager
