#!/usr/bin/env python3
"""
测试记忆重要程度路由系统的脚本
"""

import asyncio
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import extract_quintuples_async, create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, query_quintuples_by_keywords
from summer_memory.memory_importance_analyzer import memory_importance_analyzer

async def test_memory_importance_routing():
    """测试记忆重要程度路由功能"""
    print("=== 测试记忆重要程度路由系统 ===")
    
    # 测试文本，包含不同重要性的信息
    test_texts = [
        "张三和李四是好朋友，他们经常一起学习编程。",
        "张三在2023年获得了计算机科学学士学位，这是一个重要的学术成就。",
        "张三非常热爱编程，这是他的主要兴趣爱好。",
        "张三昨天买了一个新的键盘，用于编程工作。",
        "关于张三的编程学习过程，他掌握了Python和JavaScript。"
    ]
    
    print("=== 测试基础重要性分析 ===")
    basic_quintuples = []
    
    for i, text in enumerate(test_texts):
        print(f"\n处理文本 {i+1}: {text}")
        
        # 使用基础分析
        quintuples = await extract_quintuples_async(
            text, 
            session_id=f"importance_test_{i+1}", 
            context=text,
            use_advanced_analysis=False
        )
        
        basic_quintuples.extend(quintuples)
        
        print(f"提取到 {len(quintuples)} 个五元组:")
        for j, quintuple in enumerate(quintuples):
            print(f"  {j+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
            print(f"     重要性: {quintuple['importance_score']:.3f}")
            print(f"     类型: {quintuple['memory_type']}")
    
    print("\n=== 测试高级重要性分析 ===")
    advanced_quintuples = []
    
    # 选择一个文本进行高级分析
    test_text = "张三在2023年获得了计算机科学学士学位，这是一个重要的学术成就。"
    print(f"高级分析文本: {test_text}")
    
    advanced_quintuples = await extract_quintuples_async(
        test_text,
        session_id="advanced_test_001",
        context=test_text,
        use_advanced_analysis=True
    )
    
    print(f"高级分析提取到 {len(advanced_quintuples)} 个五元组:")
    for i, quintuple in enumerate(advanced_quintuples):
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
        print(f"     重要性: {quintuple['importance_score']:.3f}")
        print(f"     类型: {quintuple['memory_type']}")
        
        if "analysis_result" in quintuple:
            analysis = quintuple["analysis_result"]
            print(f"     级别: {analysis['importance_level']}")
            if analysis.get("factors"):
                factors = analysis["factors"]
                print(f"     事实重要性: {factors['factual_importance']:.3f}")
                print(f"     情感重要性: {factors['emotional_importance']:.3f}")
                print(f"     上下文重要性: {factors['contextual_importance']:.3f}")
    
    # 存储所有五元组
    print("\n=== 存储五元组 ===")
    all_quintuples = basic_quintuples + advanced_quintuples
    store_quintuples(all_quintuples)
    
    # 测试重要性过滤
    print("\n=== 测试重要性过滤 ===")
    all_stored_quintuples = query_quintuples_by_keywords(["张三"])
    
    # 高重要性记忆
    high_importance = [q for q in all_stored_quintuples if q.get("importance_score", 0) >= 0.7]
    print(f"高重要性记忆 (>=0.7): {len(high_importance)} 个")
    for q in high_importance:
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    # 中等重要性记忆
    medium_importance = [q for q in all_stored_quintuples if 0.4 <= q.get("importance_score", 0) < 0.7]
    print(f"中等重要性记忆 (0.4-0.7): {len(medium_importance)} 个")
    for q in medium_importance[:3]:  # 只显示前3个
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    # 按记忆类型分组
    print("\n=== 按记忆类型分组 ===")
    memory_types = {}
    for q in all_stored_quintuples:
        memory_type = q.get("memory_type", "fact")
        if memory_type not in memory_types:
            memory_types[memory_type] = []
        memory_types[memory_type].append(q)
    
    for memory_type, quintuples in memory_types.items():
        print(f"{memory_type} 记忆: {len(quintuples)} 个")
        avg_importance = sum(q.get("importance_score", 0.5) for q in quintuples) / len(quintuples)
        print(f"  平均重要性: {avg_importance:.3f}")
    
    # 测试记忆路由
    print("\n=== 测试记忆路由 ===")
    for quintuple in advanced_quintuples:
        if "analysis_result" in quintuple:
            analysis = quintuple["analysis_result"]
            route = memory_importance_analyzer.route_memory_by_importance(quintuple, analysis)
            print(f"记忆: {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
            print(f"  路由到: {route}")
            print(f"  重要性级别: {analysis['importance_level']}")
    
    # 获取重要性统计
    print("\n=== 重要性分析统计 ===")
    stats = memory_importance_analyzer.get_importance_statistics()
    print(f"总分析次数: {stats.get('total_analyses', 0)}")
    print(f"最近分析次数: {stats.get('recent_analyses', 0)}")
    print(f"平均分数: {stats.get('average_score', 0):.3f}")
    print(f"最高分数: {stats.get('max_score', 0):.3f}")
    print(f"最低分数: {stats.get('min_score', 0):.3f}")
    
    if "memory_type_distribution" in stats:
        print("记忆类型分布:")
        for memory_type, count in stats["memory_type_distribution"].items():
            print(f"  {memory_type}: {count}")
    
    if "analysis_methods" in stats:
        methods = stats["analysis_methods"]
        print(f"分析方法: LLM分析 {methods.get('llm_used', 0)} 次, 基础分析 {methods.get('basic_only', 0)} 次")
    
    print("\n=== 记忆重要程度路由系统测试完成 ===")

if __name__ == "__main__":
    asyncio.run(test_memory_importance_routing())