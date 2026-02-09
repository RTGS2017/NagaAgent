#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Naga Skill Manager
基于 Claude Agent Skills 规范的技能管理器

技能采用分层加载架构：
- Level 1（元数据）：YAML 前置内容，始终加载到系统提示词
- Level 2（指令）：SKILL.md 主体，按需加载
- Level 3（资源）：附加文件和脚本，按需读取

目录结构：
skills/
├── skill-name/
│   ├── SKILL.md      # 主要指令（必需）
│   ├── REFERENCE.md  # 参考文档（可选）
│   └── scripts/      # 脚本目录（可选）
│       └── helper.py
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Skill 元数据（Level 1）"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    enabled: bool = True

    # 运行时信息
    path: Path = None
    loaded_at: datetime = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "enabled": self.enabled,
            "path": str(self.path) if self.path else None
        }


@dataclass
class Skill:
    """完整的 Skill 对象"""
    metadata: SkillMetadata
    instructions: str = ""  # Level 2: SKILL.md 主体内容
    resources: Dict[str, str] = field(default_factory=dict)  # Level 3: 附加文件

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def enabled(self) -> bool:
        return self.metadata.enabled


class SkillManager:
    """
    Naga Skill 管理器

    负责：
    - 扫描和加载 skills 目录
    - 解析 SKILL.md 文件的 YAML 前置内容
    - 生成系统提示词中的技能元数据部分
    - 按需加载技能指令和资源
    """

    # YAML 前置内容正则表达式
    FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)

    def __init__(self, skills_dir: Optional[Path] = None):
        """
        初始化 Skill 管理器

        Args:
            skills_dir: skills 目录路径，默认为项目根目录下的 skills/
        """
        if skills_dir is None:
            # 默认路径：项目根目录/skills
            project_root = Path(__file__).parent.parent
            skills_dir = project_root / "skills"

        self.skills_dir = Path(skills_dir)
        self._skills: Dict[str, Skill] = {}
        self._metadata_cache: Dict[str, SkillMetadata] = {}

        # 确保目录存在
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # 初始加载所有技能元数据
        self._scan_skills()

    def _scan_skills(self):
        """扫描 skills 目录，加载所有技能元数据（Level 1）"""
        if not self.skills_dir.exists():
            logger.warning(f"Skills 目录不存在: {self.skills_dir}")
            return

        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir() and not skill_path.name.startswith('.'):
                skill_file = skill_path / "SKILL.md"
                if skill_file.exists():
                    try:
                        metadata = self._parse_metadata(skill_file, skill_path)
                        if metadata:
                            self._metadata_cache[metadata.name] = metadata
                            logger.info(f"加载技能元数据: {metadata.name}")
                    except Exception as e:
                        logger.error(f"解析技能 {skill_path.name} 失败: {e}")

    def _parse_metadata(self, skill_file: Path, skill_path: Path) -> Optional[SkillMetadata]:
        """
        解析 SKILL.md 文件的 YAML 前置内容

        Args:
            skill_file: SKILL.md 文件路径
            skill_path: 技能目录路径

        Returns:
            SkillMetadata 对象
        """
        try:
            content = skill_file.read_text(encoding='utf-8')

            # 提取 YAML 前置内容
            match = self.FRONTMATTER_PATTERN.match(content)
            if not match:
                logger.warning(f"技能 {skill_path.name} 缺少 YAML 前置内容")
                return None

            yaml_content = match.group(1)
            data = yaml.safe_load(yaml_content)

            if not data:
                return None

            # 验证必需字段
            name = data.get('name', skill_path.name)
            description = data.get('description', '')

            if not description:
                logger.warning(f"技能 {name} 缺少 description 字段")

            return SkillMetadata(
                name=name,
                description=description,
                version=data.get('version', '1.0.0'),
                author=data.get('author', ''),
                tags=data.get('tags', []),
                enabled=data.get('enabled', True),
                path=skill_path,
                loaded_at=datetime.now()
            )

        except yaml.YAMLError as e:
            logger.error(f"YAML 解析错误 {skill_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"读取技能文件失败 {skill_file}: {e}")
            return None

    def _parse_instructions(self, skill_file: Path) -> str:
        """
        解析 SKILL.md 文件的指令内容（Level 2）

        Args:
            skill_file: SKILL.md 文件路径

        Returns:
            指令内容（不含 YAML 前置）
        """
        try:
            content = skill_file.read_text(encoding='utf-8')

            # 移除 YAML 前置内容
            match = self.FRONTMATTER_PATTERN.match(content)
            if match:
                return content[match.end():].strip()
            return content.strip()

        except Exception as e:
            logger.error(f"读取指令失败 {skill_file}: {e}")
            return ""

    # ============ 公共 API ============

    def get_all_metadata(self) -> List[SkillMetadata]:
        """获取所有技能元数据（用于系统提示词）"""
        return [m for m in self._metadata_cache.values() if m.enabled]

    def get_skill(self, name: str, load_instructions: bool = True) -> Optional[Skill]:
        """
        获取完整的技能对象

        Args:
            name: 技能名称
            load_instructions: 是否加载指令内容

        Returns:
            Skill 对象
        """
        # 检查缓存
        if name in self._skills:
            return self._skills[name]

        # 检查元数据
        metadata = self._metadata_cache.get(name)
        if not metadata:
            return None

        # 构建 Skill 对象
        skill = Skill(metadata=metadata)

        # 加载指令（Level 2）
        if load_instructions and metadata.path:
            skill_file = metadata.path / "SKILL.md"
            if skill_file.exists():
                skill.instructions = self._parse_instructions(skill_file)

        # 缓存
        self._skills[name] = skill
        return skill

    def load_resource(self, skill_name: str, resource_name: str) -> Optional[str]:
        """
        按需加载技能资源文件（Level 3）

        Args:
            skill_name: 技能名称
            resource_name: 资源文件名（如 REFERENCE.md）

        Returns:
            资源内容
        """
        metadata = self._metadata_cache.get(skill_name)
        if not metadata or not metadata.path:
            return None

        resource_path = metadata.path / resource_name
        if not resource_path.exists():
            return None

        try:
            return resource_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"读取资源失败 {resource_path}: {e}")
            return None

    def generate_skills_prompt(self) -> str:
        """
        生成系统提示词中的技能元数据部分

        Returns:
            格式化的技能列表，用于注入系统提示词
        """
        enabled_skills = self.get_all_metadata()

        if not enabled_skills:
            return ""

        lines = ["## 可用技能"]
        lines.append("")
        lines.append("以下是你可以使用的专业技能。当用户请求匹配某个技能的描述时，")
        lines.append("你应该调用该技能来处理任务。")
        lines.append("")

        for skill in enabled_skills:
            lines.append(f"### {skill.name}")
            lines.append(f"- **描述**: {skill.description}")
            if skill.tags:
                lines.append(f"- **标签**: {', '.join(skill.tags)}")
            lines.append("")

        lines.append("要使用技能，请调用 `load_skill(skill_name)` 工具加载完整指令。")

        return "\n".join(lines)

    def get_skill_instructions(self, name: str) -> Optional[str]:
        """
        获取技能的完整指令（用于 LLM 调用）

        Args:
            name: 技能名称

        Returns:
            技能指令内容
        """
        skill = self.get_skill(name)
        if skill:
            return skill.instructions
        return None

    def refresh(self):
        """刷新技能列表（重新扫描目录）"""
        self._skills.clear()
        self._metadata_cache.clear()
        self._scan_skills()

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有技能信息"""
        return [m.to_dict() for m in self._metadata_cache.values()]

    def enable_skill(self, name: str, enabled: bool = True) -> bool:
        """启用/禁用技能"""
        if name in self._metadata_cache:
            self._metadata_cache[name].enabled = enabled
            return True
        return False


# ============ 全局实例 ============

_skill_manager: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    """获取全局 Skill 管理器实例"""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


def get_skills_prompt() -> str:
    """便捷函数：获取技能提示词"""
    return get_skill_manager().generate_skills_prompt()


def load_skill(name: str) -> Optional[str]:
    """便捷函数：加载技能指令"""
    return get_skill_manager().get_skill_instructions(name)
