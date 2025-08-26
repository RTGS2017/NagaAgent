#!/usr/bin/env python3
"""
测试语义去重机制的脚本
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, analyze_similarity_patterns, get_similarity_groups, deduplicate_existing_quintuples
from summer_memory.semantic_deduplicator import semantic_deduplicator

def test_semantic_deduplication():
    """测试语义去重功能"""
    print("=== 测试语义去重机制 ===")
    
    # 创建一些相似和重复的五元组用于测试
    test_quintuples = []
    
    # 创建完全相同的五元组
    identical_quintuple1 = create_enhanced_quintuple(
        subject="张三",
        subject_type="人物",
        predicate="喜欢",
        object="编程",
        object_type="活动",
        memory_type="fact",
        importance_score=0.7,
        session_id="dedup_test_001"
    )
    test_quintuples.append(identical_quintuple1)
    
    identical_quintuple2 = create_enhanced_quintuple(
        subject="张三",
        subject_type="人物",
        predicate="喜欢",
        object="编程",
        object_type="活动",
        memory_type="fact",
        importance_score=0.6,
        session_id="dedup_test_002"
    )
    test_quintuples.append(identical_quintuple2)
    
    # 创建语义相似但不完全相同的五元组
    similar_quintuple1 = create_enhanced_quintuple(
        subject="李四",
        subject_type="人物",
        predicate="热爱",
        object="写代码",
        object_type="活动",
        memory_type="fact",
        importance_score=0.8,
        session_id="dedup_test_003"
    )
    test_quintuples.append(similar_quintuple1)
    
    similar_quintuple2 = create_enhanced_quintuple(
        subject="李四",
        subject_type="人物",
        predicate="喜欢",
        object="编程",
        object_type="活动",
        memory_type="fact",
        importance_score=0.5,
        session_id="dedup_test_004"
    )
    test_quintuples.append(similar_quintuple2)
    
    # 创建不相似的五元组
    different_quintuple = create_enhanced_quintuple(
        subject="王五",
        subject_type="人物",
        predicate="学习",
        object="数学",
        object_type="学科",
        memory_type="fact",
        importance_score=0.9,
        session_id="dedup_test_005"
    )
    test_quintuples.append(different_quintuple)
    
    print(f"原始五元组数量: {len(test_quintuples)}")
    for i, quintuple in enumerate(test_quintuples):
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
    
    # 测试快速去重
    print("\n=== 测试快速去重 ===")
    fast_deduplicated = semantic_deduplicator.fast_deduplicate(test_quintuples)
    print(f"快速去重后数量: {len(fast_deduplicated)}")
    
    # 测试语义去重
    print("\n=== 测试语义去重 ===")
    semantically_deduplicated = semantic_deduplicator.deduplicate_quintuples(test_quintuples)
    print(f"语义去重后数量: {len(semantically_deduplicated)}")
    
    print("去重后的五元组:")
    for i, quintuple in enumerate(semantically_deduplicated):
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
        if "merged_from" in quintuple:
            print(f"     合并自: {quintuple['merged_from']} 个五元组")
        if "session_ids" in quintuple:
            print(f"     会话ID: {quintuple['session_ids']}")
    
    # 测试相似度计算
    print("\n=== 测试相似度计算 ===")
    similarity = semantic_deduplicator.calculate_semantic_similarity(identical_quintuple1, similar_quintuple1)
    print(f"相似度 (张三喜欢编程 vs 李四热爱写代码): {similarity:.3f}")
    
    similarity2 = semantic_deduplicator.calculate_semantic_similarity(identical_quintuple1, different_quintuple)
    print(f"相似度 (张三喜欢编程 vs 王五学习数学): {similarity2:.3f}")
    
    # 测试分组功能
    print("\n=== 测试相似度分组 ===")
    groups = semantic_deduplicator.group_by_similarity(test_quintuples)
    print(f"分组数量: {len(groups)}")
    for i, group in enumerate(groups):
        print(f"  组 {i+1} ({len(group)} 个五元组):")
        for quintuple in group:
            print(f"    - {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
    
    # 存储测试五元组到系统
    print("\n=== 测试系统集成 ===")
    store_quintuples(test_quintuples)
    
    # 分析系统的相似度模式
    print("\n=== 分析系统相似度模式 ===")
    patterns = analyze_similarity_patterns()
    print(f"系统统计:")
    print(f"  总五元组数量: {patterns['total_quintuples']}")
    print(f"  相似度分组: {patterns['similarity_groups']}")
    print(f"  唯一五元组: {patterns['unique_quintuples']}")
    print(f"  重复组: {patterns['duplicate_groups']}")
    print(f"  最大组大小: {patterns['max_group_size']}")
    print(f"  平均组大小: {patterns['average_group_size']:.2f}")
    print(f"  去重比例: {patterns['deduplication_ratio']:.2%}")
    
    # 获取系统的相似度分组
    print("\n=== 获取系统相似度分组 ===")
    system_groups = get_similarity_groups()
    print(f"系统分组数量: {len(system_groups)}")
    
    # 显示前几个分组
    for i, group in enumerate(system_groups[:3]):
        if len(group) > 1:  # 只显示有重复的组
            print(f"  重复组 {i+1} ({len(group)} 个五元组):")
            for quintuple in group:
                print(f"    - {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
    
    print("\n=== 语义去重机制测试完成 ===")

if __name__ == "__main__":
    test_semantic_deduplication()