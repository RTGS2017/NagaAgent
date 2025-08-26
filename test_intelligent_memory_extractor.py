#!/usr/bin/env python3
"""
测试智能记忆分析提取引擎的脚本
"""

import asyncio
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples
from summer_memory.intelligent_memory_extractor import intelligent_memory_extractor

async def test_intelligent_memory_extractor():
    """测试智能记忆提取引擎"""
    print("=== 测试智能记忆分析提取引擎 ===")
    
    # 首先创建一些测试数据
    print("=== 创建测试数据 ===")
    
    test_quintuples = [
        # 事实记忆
        create_enhanced_quintuple(
            subject="人工智能",
            subject_type="技术",
            predicate="是",
            object="计算机科学分支",
            object_type="学科",
            memory_type="fact",
            importance_score=0.9,
            session_id="intelligent_test_001"
        ),
        create_enhanced_quintuple(
            subject="机器学习",
            subject_type="技术",
            predicate="是",
            object="人工智能子领域",
            object_type="领域",
            memory_type="fact",
            importance_score=0.8,
            session_id="intelligent_test_002"
        ),
        
        # 过程记忆
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="学习",
            object="Python编程",
            object_type="技能",
            memory_type="process",
            importance_score=0.7,
            session_id="intelligent_test_003"
        ),
        create_enhanced_quintuple(
            subject="开发者",
            subject_type="人物",
            predicate="开发",
            object="记忆系统",
            object_type="系统",
            memory_type="process",
            importance_score=0.8,
            session_id="intelligent_test_004"
        ),
        
        # 情感记忆
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="喜欢",
            object="这个系统",
            object_type="系统",
            memory_type="emotion",
            importance_score=0.7,
            session_id="intelligent_test_005"
        ),
        create_enhanced_quintuple(
            subject="开发者",
            subject_type="人物",
            predicate="感到",
            object="满意",
            object_type="情感",
            memory_type="emotion",
            importance_score=0.6,
            session_id="intelligent_test_006"
        ),
        
        # 元记忆
        create_enhanced_quintuple(
            subject="关于记忆系统",
            subject_type="概念",
            predicate="是",
            object="重要的组件",
            object_type="概念",
            memory_type="meta",
            importance_score=0.8,
            session_id="intelligent_test_007"
        )
    ]
    
    # 存储测试数据
    store_quintuples(test_quintuples)
    print(f"存储了 {len(test_quintuples)} 个测试记忆")
    
    # 测试不同类型的查询
    test_queries = [
        "人工智能是什么？",  # 事实查询
        "用户喜欢什么？",    # 情感查询
        "最近的学习过程？", # 时间+过程查询
        "如何开发系统？",   # 过程查询
        "关于记忆系统的信息", # 元查询
        "重要的事实有哪些？", # 重要性查询
        "用户和开发者的关系？", # 关系查询
    ]
    
    print("\n=== 测试查询分析 ===")
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n查询 {i}: {query}")
        
        # 分析查询
        analysis = await intelligent_memory_extractor.analyze_query(query)
        
        print(f"  查询类型: {analysis.query_type.value}")
        print(f"  关键词: {analysis.keywords}")
        print(f"  实体: {analysis.entities}")
        print(f"  记忆类型: {analysis.memory_types}")
        print(f"  重要性阈值: {analysis.importance_threshold}")
        print(f"  提取策略: {analysis.extraction_strategy.value}")
        print(f"  置信度: {analysis.confidence:.3f}")
        
        if analysis.time_constraints:
            print(f"  时间约束: {analysis.time_constraints}")
    
    print("\n=== 测试记忆提取 ===")
    
    extraction_results = []
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n提取查询 {i}: {query}")
        
        # 提取记忆
        result = await intelligent_memory_extractor.extract_memories(query, max_results=5)
        extraction_results.append(result)
        
        print(f"  找到 {len(result.quintuples)} 个相关记忆")
        print(f"  处理时间: {result.processing_time:.3f}s")
        print(f"  使用策略: {result.extraction_metadata['strategy_used']}")
        
        # 显示结果
        for j, (quintuple, score) in enumerate(zip(result.quintuples, result.relevance_scores)):
            print(f"    {j+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
            print(f"       类型: {quintuple['memory_type']}, 相关性: {score:.3f}")
    
    # 测试性能指标
    print("\n=== 性能指标 ===")
    
    performance_metrics = intelligent_memory_extractor.get_performance_metrics()
    print("各策略性能:")
    for strategy, metrics in performance_metrics.items():
        print(f"  {strategy}:")
        print(f"    调用次数: {metrics['count']}")
        print(f"    平均时间: {metrics['average_time']:.3f}s")
        print(f"    最快: {metrics['min_time']:.3f}s")
        print(f"    最慢: {metrics['max_time']:.3f}s")
    
    # 测试查询统计
    print("\n=== 查询统计 ===")
    
    query_stats = intelligent_memory_extractor.get_query_statistics()
    print(f"总查询数: {query_stats['total_queries']}")
    print(f"平均置信度: {query_stats['average_confidence']:.3f}")
    print("查询类型分布:")
    for query_type, count in query_stats['query_types'].items():
        print(f"  {query_type}: {count}")
    
    print("策略使用分布:")
    for strategy, count in query_stats['strategies_used'].items():
        print(f"  {strategy}: {count}")
    
    # 测试复杂的综合查询
    print("\n=== 测试综合查询 ===")
    
    complex_query = "请告诉我关于人工智能的重要事实，以及用户最近的情感状态，这些都是系统开发过程中的关键信息"
    
    print(f"综合查询: {complex_query}")
    
    complex_result = await intelligent_memory_extractor.extract_memories(complex_query, max_results=10)
    
    print(f"找到 {len(complex_result.quintuples)} 个相关记忆")
    print(f"处理时间: {complex_result.processing_time:.3f}s")
    
    # 按类型分组显示结果
    by_type = {}
    for quintuple, score in zip(complex_result.quintuples, complex_result.relevance_scores):
        memory_type = quintuple['memory_type']
        if memory_type not in by_type:
            by_type[memory_type] = []
        by_type[memory_type].append((quintuple, score))
    
    for memory_type, items in by_type.items():
        print(f"\n{memory_type} 记忆 ({len(items)} 个):")
        for quintuple, score in items:
            print(f"  - {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']} (相关性: {score:.3f})")
    
    print("\n=== 智能记忆分析提取引擎测试完成 ===")

if __name__ == "__main__":
    asyncio.run(test_intelligent_memory_extractor())