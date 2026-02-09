#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 调度测试脚本
测试技能的加载、匹配和调度逻辑
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from system.skill_manager import get_skill_manager, load_skill
from system.config import build_system_prompt


def test_skill_loading():
    """测试技能加载"""
    print("=" * 60)
    print("测试 1: 技能加载")
    print("=" * 60)

    manager = get_skill_manager()
    manager.refresh()  # 刷新以加载新技能

    skills = manager.list_skills()
    print(f"\n已加载 {len(skills)} 个技能:\n")

    for skill in skills:
        status = "✓" if skill['enabled'] else "✗"
        print(f"  {status} {skill['name']}")
        print(f"      描述: {skill['description'][:60]}...")
        print(f"      标签: {', '.join(skill['tags'])}")
        print()


def test_skill_matching(user_input: str):
    """测试技能匹配"""
    print("=" * 60)
    print("测试 2: 技能匹配")
    print(f"用户输入: {user_input}")
    print("=" * 60)

    manager = get_skill_manager()

    # 简单的关键词匹配
    matched_skills = []
    input_lower = user_input.lower()

    for metadata in manager.get_all_metadata():
        # 检查描述中的关键词
        desc_lower = metadata.description.lower()
        tags = [t.lower() for t in metadata.tags]

        # 匹配规则
        score = 0

        # 标签匹配（高权重）
        for tag in tags:
            if tag in input_lower:
                score += 10

        # 描述关键词匹配
        keywords = ["搜索", "查询", "文件", "系统", "代码", "文档", "openclaw"]
        for kw in keywords:
            if kw in input_lower and kw in desc_lower:
                score += 5

        # 特定触发词
        triggers = {
            "web-search": ["搜索", "查一下", "最新", "新闻", "搜一搜"],
            "system-info": ["系统", "配置", "硬件", "内存", "cpu", "磁盘"],
            "file-manager": ["文件", "文件夹", "整理", "移动", "复制", "删除"],
            "code-review": ["代码", "审查", "review", "检查代码"],
            "document-writer": ["文档", "readme", "写文档", "编写"],
            "openclaw-control": ["openclaw", "open claw", "发送给oc"]
        }

        for trigger in triggers.get(metadata.name, []):
            if trigger in input_lower:
                score += 15

        if score > 0:
            matched_skills.append((metadata, score))

    # 按分数排序
    matched_skills.sort(key=lambda x: x[1], reverse=True)

    print("\n匹配结果:\n")
    if matched_skills:
        for metadata, score in matched_skills:
            print(f"  [{score:2d}分] {metadata.name}")
            print(f"        {metadata.description[:50]}...")

        best_match = matched_skills[0][0]
        print(f"\n最佳匹配: {best_match.name}")
        return best_match.name
    else:
        print("  未匹配到任何技能")
        return None


def test_skill_dispatch(skill_name: str):
    """测试技能调度（加载指令）"""
    print("=" * 60)
    print(f"测试 3: 调度技能 - {skill_name}")
    print("=" * 60)

    instructions = load_skill(skill_name)

    if instructions:
        print(f"\n技能指令已加载 ({len(instructions)} 字符):\n")
        print("-" * 40)
        print(instructions[:800])
        if len(instructions) > 800:
            print("...")
        print("-" * 40)
        return True
    else:
        print(f"\n错误: 无法加载技能 {skill_name}")
        return False


def test_system_prompt():
    """测试系统提示词生成"""
    print("=" * 60)
    print("测试 4: 系统提示词生成")
    print("=" * 60)

    prompt = build_system_prompt(include_skills=True)

    print(f"\n系统提示词长度: {len(prompt)} 字符")
    print("\n技能部分预览:")
    print("-" * 40)

    # 提取技能部分
    if "## 可用技能" in prompt:
        skills_section = prompt[prompt.index("## 可用技能"):]
        print(skills_section[:600])
        if len(skills_section) > 600:
            print("...")

    print("-" * 40)


def run_interactive_test():
    """交互式测试"""
    print("\n" + "=" * 60)
    print("交互式技能调度测试")
    print("输入用户问题，测试技能匹配和调度")
    print("输入 'q' 退出")
    print("=" * 60)

    test_inputs = [
        "帮我搜索一下最新的 Python 3.12 新特性",
        "我的电脑配置是什么？",
        "帮我整理一下下载文件夹",
        "审查一下这段代码",
        "帮我写一个 README 文档",
        "让 OpenClaw 帮我发一封邮件",
    ]

    print("\n示例测试:\n")
    for i, test_input in enumerate(test_inputs, 1):
        print(f"\n--- 测试 {i} ---")
        matched = test_skill_matching(test_input)
        if matched:
            print(f"→ 将调度技能: {matched}")
        print()


if __name__ == "__main__":
    # 运行所有测试
    test_skill_loading()
    print()

    test_system_prompt()
    print()

    # 测试匹配
    test_skill_matching("帮我搜索一下 Python 最新版本")
    print()

    # 测试调度
    test_skill_dispatch("web-search")
    print()

    # 交互式测试
    run_interactive_test()
