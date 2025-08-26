#!/usr/bin/env python3
"""
测试记忆重要程度路由系统的简化版本
"""

import asyncio
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import extract_quintuples_async, create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, query_quintuples_by_keywords
from summer_memory.memory_importance_analyzer import memory_importance_analyzer

async def test_memory_importance_routing_simple():
    """测试记忆重要程度路由功能（简化版本）"""
    print("=== 测试记忆重要程度路由系统（简化版） ===")
    
    # 创建一些测试五元组，手动设置不同的重要性
    test_quintuples = [
        create_enhanced_quintuple(
            subject="张三",
            subject_type="人物",
            predicate="获得",
            object="计算机科学学士学位",
            object_type="成就",
            memory_type="fact",
            importance_score=0.9,  # 高重要性
            session_id="routing_test_001"
        ),
        create_enhanced_quintuple(
            subject="张三",
            subject_type="人物",
            predicate="喜欢",
            object="编程",
            object_type="活动",
            memory_type="emotion",
            importance_score=0.7,  # 中高重要性
            session_id="routing_test_002"
        ),
        create_enhanced_quintuple(
            subject="张三",
            subject_type="人物",
            predicate="购买",
            object="键盘",
            object_type="物品",
            memory_type="fact",
            importance_score=0.4,  # 中等重要性
            session_id="routing_test_003"
        ),
        create_enhanced_quintuple(
            subject="张三",
            subject_type="人物",
            predicate="看到",
            object="天空",
            object_type="自然",
            memory_type="fact",
            importance_score=0.2,  # 低重要性
            session_id="routing_test_004"
        ),
        create_enhanced_quintuple(
            subject="关于张三",
            subject_type="概念",
            predicate="是",
            object="程序员",
            object_type="职业",
            memory_type="meta",
            importance_score=0.6,  # 中等重要性
            session_id="routing_test_005"
        )
    ]
    
    print("=== 测试五元组 ===")
    for i, quintuple in enumerate(test_quintuples):
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
        print(f"     重要性: {quintuple['importance_score']:.3f}")
        print(f"     类型: {quintuple['memory_type']}")
        
        # 测试记忆路由
        route = memory_importance_analyzer.route_memory_by_importance(
            quintuple, 
            {"importance_score": quintuple['importance_score'], "memory_type": quintuple['memory_type']}
        )
        print(f"     路由到: {route}")
    
    # 存储五元组
    print("\n=== 存储五元组 ===")
    store_quintuples(test_quintuples)
    
    # 测试查询和过滤
    print("\n=== 测试重要性过滤 ===")
    all_quintuples = query_quintuples_by_keywords(["张三"])
    
    # 按重要性级别分组
    critical_quintuples = [q for q in all_quintuples if q.get("importance_score", 0) >= 0.9]
    high_quintuples = [q for q in all_quintuples if 0.7 <= q.get("importance_score", 0) < 0.9]
    medium_quintuples = [q for q in all_quintuples if 0.4 <= q.get("importance_score", 0) < 0.7]
    low_quintuples = [q for q in all_quintuples if q.get("importance_score", 0) < 0.4]
    
    print(f"关键记忆 (>=0.9): {len(critical_quintuples)} 个")
    for q in critical_quintuples:
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    print(f"高重要性记忆 (0.7-0.9): {len(high_quintuples)} 个")
    for q in high_quintuples:
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    print(f"中等重要性记忆 (0.4-0.7): {len(medium_quintuples)} 个")
    for q in medium_quintuples:
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    print(f"低重要性记忆 (<0.4): {len(low_quintuples)} 个")
    for q in low_quintuples:
        print(f"  - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    # 测试按重要性排序
    print("\n=== 测试按重要性排序 ===")
    sorted_quintuples = memory_importance_analyzer.sort_by_importance(all_quintuples)
    print("按重要性降序排序:")
    for i, quintuple in enumerate(sorted_quintuples[:5]):  # 显示前5个
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']} ({quintuple['importance_score']:.3f})")
    
    # 测试按记忆类型分组
    print("\n=== 按记忆类型分组 ===")
    memory_types = {}
    for q in all_quintuples:
        memory_type = q.get("memory_type", "fact")
        if memory_type not in memory_types:
            memory_types[memory_type] = []
        memory_types[memory_type].append(q)
    
    for memory_type, quintuples in memory_types.items():
        print(f"{memory_type} 记忆: {len(quintuples)} 个")
        avg_importance = sum(q.get("importance_score", 0.5) for q in quintuples) / len(quintuples)
        print(f"  平均重要性: {avg_importance:.3f}")
        for q in quintuples:
            print(f"    - {q['subject']} -{q['predicate']}- {q['object']} ({q['importance_score']:.3f})")
    
    # 测试基础重要性分析
    print("\n=== 测试基础重要性分析 ===")
    test_quintuple = {
        "subject": "测试用户",
        "subject_type": "人物",
        "predicate": "完成",
        "object": "重要项目",
        "object_type": "项目"
    }
    
    basic_score = memory_importance_analyzer.calculate_basic_importance(test_quintuple, "这是一个重要的项目完成")
    print(f"基础重要性分析分数: {basic_score:.3f}")
    
    # 测试重要性级别判断
    importance_level = memory_importance_analyzer.get_importance_level(basic_score)
    print(f"重要性级别: {importance_level.name} ({importance_level.value})")
    
    # 测试重要性统计
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
    
    print("\n=== 记忆重要程度路由系统测试完成 ===")

if __name__ == "__main__":
    asyncio.run(test_memory_importance_routing_simple())