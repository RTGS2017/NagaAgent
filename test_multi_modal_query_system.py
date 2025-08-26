#!/usr/bin/env python3
"""
测试多模态查询系统的脚本
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples
from summer_memory.multi_modal_query_system import multi_modal_query_system, SearchMode, QueryScope, QueryOptions

def test_multi_modal_query_system():
    """测试多模态查询系统"""
    print("=== 测试多模态查询系统 ===")
    
    # 创建测试数据
    print("=== 创建测试数据 ===")
    
    test_quintuples = [
        # 事实记忆
        create_enhanced_quintuple(
            subject="深度学习",
            subject_type="技术",
            predicate="是",
            object="机器学习的子领域",
            object_type="领域",
            memory_type="fact",
            importance_score=0.9,
            session_id="multimodal_test_001"
        ),
        create_enhanced_quintuple(
            subject="神经网络",
            subject_type="技术",
            predicate="是",
            object="深度学习的核心",
            object_type="技术",
            memory_type="fact",
            importance_score=0.8,
            session_id="multimodal_test_002"
        ),
        
        # 过程记忆
        create_enhanced_quintuple(
            subject="研究者",
            subject_type="人物",
            predicate="训练",
            object="神经网络模型",
            object_type="模型",
            memory_type="process",
            importance_score=0.7,
            session_id="multimodal_test_003"
        ),
        create_enhanced_quintuple(
            subject="工程师",
            subject_type="人物",
            predicate="开发",
            object="AI应用",
            object_type="应用",
            memory_type="process",
            importance_score=0.8,
            session_id="multimodal_test_004"
        ),
        
        # 情感记忆
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="喜欢",
            object="深度学习技术",
            object_type="技术",
            memory_type="emotion",
            importance_score=0.7,
            session_id="multimodal_test_005"
        ),
        create_enhanced_quintuple(
            subject="开发者",
            subject_type="人物",
            predicate="感到",
            object="兴奋",
            object_type="情感",
            memory_type="emotion",
            importance_score=0.6,
            session_id="multimodal_test_006"
        ),
        
        # 元记忆
        create_enhanced_quintuple(
            subject="关于AI系统",
            subject_type="概念",
            predicate="是",
            object="未来技术",
            object_type="概念",
            memory_type="meta",
            importance_score=0.8,
            session_id="multimodal_test_007"
        )
    ]
    
    # 存储测试数据
    store_quintuples(test_quintuples)
    print(f"存储了 {len(test_quintuples)} 个测试记忆")
    
    # 测试不同搜索模式
    print("\n=== 测试不同搜索模式 ===")
    
    test_query = "深度学习神经网络"
    
    # 1. 关键词搜索
    print(f"\n1. 关键词搜索: '{test_query}'")
    keyword_options = QueryOptions(
        search_modes=[SearchMode.KEYWORD],
        scope=QueryScope.FULL,
        max_results=5,
        min_relevance=0.3,
        time_window=None,
        memory_types=None
    )
    
    keyword_results = multi_modal_query_system.search(test_query, keyword_options)
    print(f"   找到 {len(keyword_results)} 个结果")
    for result in keyword_results:
        print(f"   - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"     相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 2. 语义搜索
    print(f"\n2. 语义搜索: '{test_query}'")
    semantic_options = QueryOptions(
        search_modes=[SearchMode.SEMANTIC],
        scope=QueryScope.FULL,
        max_results=5,
        min_relevance=0.3
    )
    
    semantic_results = multi_modal_query_system.search(test_query, semantic_options)
    print(f"   找到 {len(semantic_results)} 个结果")
    for result in semantic_results:
        print(f"   - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"     相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 3. 混合搜索
    print(f"\n3. 混合搜索: '{test_query}'")
    hybrid_options = QueryOptions(
        search_modes=[SearchMode.KEYWORD, SearchMode.SEMANTIC],
        scope=QueryScope.FULL,
        max_results=5,
        min_relevance=0.3
    )
    
    hybrid_results = multi_modal_query_system.search(test_query, hybrid_options)
    print(f"   找到 {len(hybrid_results)} 个结果")
    for result in hybrid_results:
        print(f"   - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"     相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 测试不同查询范围
    print("\n=== 测试不同查询范围 ===")
    
    scope_query = "用户喜欢什么"
    
    for scope in [QueryScope.SUBJECT, QueryScope.PREDICATE, QueryScope.OBJECT, QueryScope.FULL]:
        print(f"\n查询范围: {scope.value}")
        scope_options = QueryOptions(
            search_modes=[SearchMode.KEYWORD],
            scope=scope,
            max_results=5,
            min_relevance=0.3
        )
        
        scope_results = multi_modal_query_system.search(scope_query, scope_options)
        print(f"   找到 {len(scope_results)} 个结果")
        for result in scope_results[:2]:  # 只显示前2个
            print(f"   - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
    
    # 测试高级搜索功能
    print("\n=== 测试高级搜索功能 ===")
    
    advanced_results = multi_modal_query_system.advanced_search(
        "AI技术学习过程",
        search_modes=[SearchMode.KEYWORD, SearchMode.SEMANTIC, SearchMode.HYBRID],
        max_results=10,
        min_relevance=0.4,
        memory_types=["fact", "process"],
        time_window=24 * 3600  # 24小时
    )
    
    print(f"高级搜索结果:")
    print(f"  查询: {advanced_results['query']}")
    print(f"  总结果数: {advanced_results['analysis']['total_results']}")
    print(f"  平均相关性: {advanced_results['analysis']['average_relevance']:.3f}")
    print(f"  使用的搜索模式: {advanced_results['analysis']['search_modes_used']}")
    print(f"  处理时间: {advanced_results['processing_time']:.3f}s")
    
    print("  结果分布:")
    for memory_type, count in advanced_results['analysis']['results_by_type'].items():
        print(f"    {memory_type}: {count}")
    
    for search_mode, count in advanced_results['analysis']['results_by_mode'].items():
        print(f"    {search_mode}: {count}")
    
    # 显示前几个结果
    print("  前3个结果:")
    for i, result in enumerate(advanced_results['results'][:3]):
        print(f"    {i+1}. {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"       相关性: {result.relevance_score:.3f}, 模式: {result.search_mode}")
    
    # 测试模糊搜索
    print("\n=== 测试模糊搜索 ===")
    
    fuzzy_query = "深学习"  # 故意缺少"度"字
    fuzzy_options = QueryOptions(
        search_modes=[SearchMode.FUZZY],
        scope=QueryScope.FULL,
        max_results=5,
        min_relevance=0.3,
        fuzzy_threshold=0.6
    )
    
    fuzzy_results = multi_modal_query_system.search(fuzzy_query, fuzzy_options)
    print(f"模糊搜索 '{fuzzy_query}' 结果:")
    print(f"  找到 {len(fuzzy_results)} 个结果")
    for result in fuzzy_results:
        print(f"  - {result.quintuple['subject']} -{result.quintuple['predicate']}- {result.quintuple['object']}")
        print(f"    相关性: {result.relevance_score:.3f}")
    
    # 测试性能统计
    print("\n=== 性能统计 ===")
    
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
    test_multi_modal_query_system()