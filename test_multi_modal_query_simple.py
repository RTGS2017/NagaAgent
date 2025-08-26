#!/usr/bin/env python3
"""
简化的多模态查询系统测试
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples
from summer_memory.multi_modal_query_system import multi_modal_query_system, SearchMode, QueryScope, QueryOptions

def test_multi_modal_query_simple():
    """简化的多模态查询系统测试"""
    print("=== 测试多模态查询系统（简化版） ===")
    
    # 创建测试数据
    print("=== 创建测试数据 ===")
    
    test_quintuples = [
        create_enhanced_quintuple(
            subject="深度学习",
            subject_type="技术",
            predicate="是",
            object="机器学习的子领域",
            object_type="领域",
            memory_type="fact",
            importance_score=0.9,
            session_id="multimodal_simple_001"
        ),
        create_enhanced_quintuple(
            subject="神经网络",
            subject_type="技术",
            predicate="是",
            object="深度学习的核心",
            object_type="技术",
            memory_type="fact",
            importance_score=0.8,
            session_id="multimodal_simple_002"
        ),
        create_enhanced_quintuple(
            subject="研究者",
            subject_type="人物",
            predicate="训练",
            object="神经网络模型",
            object_type="模型",
            memory_type="process",
            importance_score=0.7,
            session_id="multimodal_simple_003"
        ),
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="喜欢",
            object="深度学习技术",
            object_type="技术",
            memory_type="emotion",
            importance_score=0.7,
            session_id="multimodal_simple_004"
        )
    ]
    
    # 存储测试数据
    store_quintuples(test_quintuples)
    print(f"存储了 {len(test_quintuples)} 个测试记忆")
    
    # 测试基本搜索功能
    print("\n=== 测试基本搜索功能 ===")
    
    test_queries = [
        "深度学习",
        "神经网络",
        "用户喜欢",
        "研究者训练"
    ]
    
    for query in test_queries:
        print(f"\n查询: '{query}'")
        
        # 使用默认选项搜索
        options = QueryOptions(
            search_modes=[SearchMode.KEYWORD],
            scope=QueryScope.FULL,
            max_results=5,
            min_relevance=0.3,
            time_window=None,
            memory_types=None
        )
        
        results = multi_modal_query_system.search(query, options)
        print(f"  找到 {len(results)} 个结果")
        
        for result in results:
            print(f"  - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
            print(f"    相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 测试高级搜索
    print("\n=== 测试高级搜索 ===")
    
    advanced_results = multi_modal_query_system.advanced_search(
        "深度学习技术",
        search_modes=[SearchMode.KEYWORD, SearchMode.SEMANTIC],
        max_results=10,
        min_relevance=0.4,
        time_window=None,
        memory_types=None
    )
    
    print(f"高级搜索结果:")
    print(f"  查询: {advanced_results['query']}")
    print(f"  总结果数: {advanced_results['analysis']['total_results']}")
    print(f"  平均相关性: {advanced_results['analysis']['average_relevance']:.3f}")
    print(f"  处理时间: {advanced_results['processing_time']:.3f}s")
    
    # 显示结果
    for i, result in enumerate(advanced_results['results'][:3]):
        print(f"  {i+1}. {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"     相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 测试统计信息
    print("\n=== 统计信息 ===")
    
    stats = multi_modal_query_system.get_search_statistics()
    print(f"总搜索次数: {stats.get('total_searches', 0)}")
    print(f"平均结果数: {stats.get('average_results', 0):.1f}")
    print(f"平均处理时间: {stats.get('average_time', 0):.3f}s")
    
    if 'search_modes' in stats:
        print("搜索模式使用分布:")
        for mode, count in stats['search_modes'].items():
            print(f"  {mode}: {count}")
    
    print("\n=== 多模态查询系统测试完成 ===")

if __name__ == "__main__":
    test_multi_modal_query_simple()