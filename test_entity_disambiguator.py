#!/usr/bin/env python3
"""
测试实体消歧系统的脚本
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.entity_disambiguator import entity_disambiguator

def test_entity_disambiguator():
    """测试实体消歧系统"""
    print("=== 测试实体消歧系统 ===")
    
    # 测试创建和消歧实体
    print("\n=== 测试实体创建和消歧 ===")
    
    # 创建第一个"张三"
    entity1 = entity_disambiguator.disambiguate_entity(
        name="张三",
        entity_type="人物",
        context="在北京大学学习计算机科学",
        description="北京大学的学生",
        confidence=0.8
    )
    print(f"创建实体1: {entity1.canonical_name} (ID: {entity1.entity_id})")
    
    # 创建第二个"张三"（不同上下文）
    entity2 = entity_disambiguator.disambiguate_entity(
        name="张三",
        entity_type="人物",
        context="在上海的软件公司工作",
        description="软件工程师",
        confidence=0.9
    )
    print(f"创建实体2: {entity2.canonical_name} (ID: {entity2.entity_id})")
    
    # 测试相同实体（应该合并）
    entity3 = entity_disambiguator.disambiguate_entity(
        name="张三",
        entity_type="人物",
        context="在北京大学学习计算机科学",  # 相同上下文
        description="正在学习深度学习",
        confidence=0.7
    )
    print(f"创建/合并实体3: {entity3.canonical_name} (ID: {entity3.entity_id})")
    
    # 验证是否正确消歧
    print(f"\n实体1 ID: {entity1.entity_id}")
    print(f"实体2 ID: {entity2.entity_id}")
    print(f"实体3 ID: {entity3.entity_id}")
    print(f"实体1和实体3是否相同: {entity1.entity_id == entity3.entity_id}")
    
    # 测试添加别名
    print("\n=== 测试别名功能 ===")
    entity_disambiguator.add_alias(entity1.entity_id, "小张")
    entity_disambiguator.add_alias(entity2.entity_id, "张工程师")
    
    # 测试查找功能
    print("\n=== 测试查找功能 ===")
    
    # 通过名称查找
    zhangsan_entities = entity_disambiguator.find_entities_by_name("张三")
    print(f"通过'张三'找到 {len(zhangsan_entities)} 个实体")
    for entity in zhangsan_entities:
        print(f"  - {entity.canonical_name} (ID: {entity.entity_id})")
        print(f"    类型: {entity.attributes.entity_type}")
        print(f"    频率: {entity.attributes.frequency}")
        print(f"    置信度: {entity.attributes.confidence}")
    
    # 通过别名查找
    xiaozhang_entities = entity_disambiguator.find_entities_by_name("小张")
    print(f"通过'小张'找到 {len(xiaozhang_entities)} 个实体")
    for entity in xiaozhang_entities:
        print(f"  - {entity.canonical_name} (ID: {entity.entity_id})")
    
    # 通过上下文查找
    beijing_entities = entity_disambiguator.find_entities_by_context("北京大学")
    print(f"通过'北京大学'上下文找到 {len(beijing_entities)} 个实体")
    for entity in beijing_entities:
        print(f"  - {entity.canonical_name} (ID: {entity.entity_id})")
    
    # 测试实体关系
    print("\n=== 测试实体关系 ===")
    
    # 创建相关实体
    beijing_entity = entity_disambiguator.disambiguate_entity(
        name="北京大学",
        entity_type="组织",
        context="中国著名的高等学府",
        description="综合性大学",
        confidence=0.95
    )
    
    computer_entity = entity_disambiguator.disambiguate_entity(
        name="计算机科学",
        entity_type="学科",
        context="热门的技术学科",
        description="研究计算和信息处理",
        confidence=0.9
    )
    
    # 建立关系
    entity_disambiguator.relate_entities(entity1.entity_id, beijing_entity.entity_id)
    entity_disambiguator.relate_entities(entity1.entity_id, computer_entity.entity_id)
    
    print(f"建立关系:")
    print(f"  {entity1.canonical_name} <-> {beijing_entity.canonical_name}")
    print(f"  {entity1.canonical_name} <-> {computer_entity.canonical_name}")
    
    # 验证关系
    print(f"实体1的相关实体数量: {len(entity1.related_entities)}")
    for related_id in entity1.related_entities:
        related_entity = entity_disambiguator.get_entity(related_id)
        if related_entity:
            print(f"  - {related_entity.canonical_name}")
    
    # 测试统计信息
    print("\n=== 统计信息 ===")
    
    stats = entity_disambiguator.get_entity_statistics()
    print(f"总实体数量: {stats['total_entities']}")
    print("实体类型分布:")
    for entity_type, count in stats['type_distribution'].items():
        print(f"  {entity_type}: {count}")
    
    print("别名统计:")
    alias_stats = stats['alias_stats']
    print(f"  有别名的实体: {alias_stats['entities_with_aliases']}")
    print(f"  平均别名数: {alias_stats['average_aliases']:.2f}")
    
    print("频率统计:")
    freq_stats = stats['frequency_stats']
    print(f"  平均频率: {freq_stats['average_frequency']:.2f}")
    print(f"  高频实体: {freq_stats['high_frequency_entities']}")
    
    # 测试清理功能
    print("\n=== 测试清理功能 ===")
    
    # 创建一个低质量实体
    low_quality_entity = entity_disambiguator.disambiguate_entity(
        name="临时实体",
        entity_type="测试",
        context="测试用的临时实体",
        description="低质量测试实体",
        confidence=0.2
    )
    
    print(f"创建低质量实体: {low_quality_entity.canonical_name}")
    
    # 清理前统计
    before_stats = entity_disambiguator.get_entity_statistics()
    print(f"清理前实体总数: {before_stats['total_entities']}")
    
    # 执行清理
    cleaned_count = entity_disambiguator.cleanup_entities(min_frequency=1, min_confidence=0.5)
    print(f"清理了 {cleaned_count} 个实体")
    
    # 清理后统计
    after_stats = entity_disambiguator.get_entity_statistics()
    print(f"清理后实体总数: {after_stats['total_entities']}")
    
    # 测试导出功能
    print("\n=== 测试导出功能 ===")
    
    export_file = entity_disambiguator.export_entities()
    print(f"导出实体数据到: {export_file}")
    
    print("\n=== 实体消歧系统测试完成 ===")

if __name__ == "__main__":
    test_entity_disambiguator()