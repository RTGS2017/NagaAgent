#!/usr/bin/env python3
"""
测试分类型存储系统的脚本
"""

import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, get_typed_memories, search_typed_memories, get_typed_memory_statistics
from summer_memory.typed_memory_storage import typed_memory_storage, MemoryType

def test_typed_memory_storage():
    """测试分类型存储功能"""
    print("=== 测试分类型存储系统 ===")
    
    # 创建不同类型的测试五元组
    test_quintuples = [
        # 事实记忆
        create_enhanced_quintuple(
            subject="北京",
            subject_type="地点",
            predicate="是",
            object="中国首都",
            object_type="概念",
            memory_type="fact",
            importance_score=0.9,
            session_id="typed_test_001"
        ),
        create_enhanced_quintuple(
            subject="Python",
            subject_type="语言",
            predicate="是",
            object="编程语言",
            object_type="概念",
            memory_type="fact",
            importance_score=0.8,
            session_id="typed_test_002"
        ),
        
        # 过程记忆
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="学习",
            object="编程",
            object_type="活动",
            memory_type="process",
            importance_score=0.7,
            session_id="typed_test_003"
        ),
        create_enhanced_quintuple(
            subject="系统",
            subject_type="系统",
            predicate="处理",
            object="数据",
            object_type="对象",
            memory_type="process",
            importance_score=0.6,
            session_id="typed_test_004"
        ),
        
        # 情感记忆
        create_enhanced_quintuple(
            subject="用户",
            subject_type="人物",
            predicate="喜欢",
            object="这个系统",
            object_type="系统",
            memory_type="emotion",
            importance_score=0.8,
            session_id="typed_test_005"
        ),
        create_enhanced_quintuple(
            subject="开发者",
            subject_type="人物",
            predicate="感到",
            object="满意",
            object_type="情感",
            memory_type="emotion",
            importance_score=0.7,
            session_id="typed_test_006"
        ),
        
        # 元记忆
        create_enhanced_quintuple(
            subject="关于记忆系统",
            subject_type="概念",
            predicate="是",
            object="重要的组件",
            object_type="概念",
            memory_type="meta",
            importance_score=0.9,
            session_id="typed_test_007"
        ),
        create_enhanced_quintuple(
            subject="这个测试",
            subject_type="活动",
            predicate="验证",
            object="存储功能",
            object_type="功能",
            memory_type="meta",
            importance_score=0.6,
            session_id="typed_test_008"
        )
    ]
    
    print("=== 存储测试数据 ===")
    for i, quintuple in enumerate(test_quintuples):
        print(f"  {i+1}. {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
        print(f"     类型: {quintuple['memory_type']}, 重要性: {quintuple['importance_score']:.3f}")
    
    # 存储五元组
    print("\n=== 存储到分类型系统 ===")
    success = store_quintuples(test_quintuples)
    print(f"存储结果: {success}")
    
    # 测试按类型获取记忆
    print("\n=== 测试按类型获取记忆 ===")
    
    for memory_type in MemoryType:
        print(f"\n{memory_type.value} 记忆:")
        memories = typed_memory_storage.get_memories_by_type(memory_type, limit=5)
        
        for i, memory in enumerate(memories):
            print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']}")
            print(f"     重要性: {memory['importance_score']:.3f}")
    
    # 测试获取多类型记忆
    print("\n=== 测试获取多类型记忆 ===")
    
    # 获取事实和情感记忆
    fact_emotion_memories = get_typed_memories(["fact", "emotion"], limit=10)
    print(f"事实和情感记忆数量: {len(fact_emotion_memories)}")
    for i, memory in enumerate(fact_emotion_memories[:3]):
        print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']} ({memory['memory_type']})")
    
    # 测试搜索功能
    print("\n=== 测试搜索功能 ===")
    
    search_results = search_typed_memories(["用户"], limit=5)
    print(f"搜索'用户'的结果: {len(search_results)} 个")
    for i, memory in enumerate(search_results):
        print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']} ({memory['memory_type']})")
    
    # 测试按重要性过滤
    print("\n=== 测试按重要性过滤 ===")
    
    high_importance_memories = get_typed_memories(min_importance=0.8, limit=10)
    print(f"高重要性记忆 (>=0.8): {len(high_importance_memories)} 个")
    for i, memory in enumerate(high_importance_memories):
        print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']} ({memory['importance_score']:.3f})")
    
    # 测试获取最近记忆
    print("\n=== 测试获取最近记忆 ===")
    
    recent_fact_memories = typed_memory_storage.get_recent_memories(MemoryType.FACT, hours=24)
    print(f"最近24小时的事实记忆: {len(recent_fact_memories)} 个")
    for i, memory in enumerate(recent_fact_memories[:3]):
        print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']}")
    
    # 测试按会话获取记忆
    print("\n=== 测试按会话获取记忆 ===")
    
    session_memories = typed_memory_storage.get_memories_by_session("typed_test_001")
    print(f"会话 typed_test_001 的记忆: {len(session_memories)} 个")
    for i, memory in enumerate(session_memories):
        print(f"  {i+1}. {memory['subject']} -{memory['predicate']}- {memory['object']} ({memory['memory_type']})")
    
    # 获取存储统计信息
    print("\n=== 存储统计信息 ===")
    
    stats = get_typed_memory_statistics()
    print(f"总记忆数量: {stats['total_memories']}")
    print("各类型统计:")
    for memory_type, type_stats in stats['by_type'].items():
        print(f"  {memory_type}:")
        print(f"    数量: {type_stats['count']}")
        print(f"    平均重要性: {type_stats['avg_importance']:.3f}")
        print(f"    使用率: {type_stats['usage_ratio']:.2%}")
        print(f"    保留天数: {type_stats['retention_days']}")
    
    # 测试导出功能
    print("\n=== 测试导出功能 ===")
    
    export_file = typed_memory_storage.export_memories([MemoryType.FACT, MemoryType.EMOTION])
    print(f"导出文件: {export_file}")
    
    # 测试清理功能
    print("\n=== 测试清理功能 ===")
    
    # 模拟一些过期数据
    old_time = time.time() - (400 * 24 * 3600)  # 400天前
    old_quintuple = create_enhanced_quintuple(
        subject="旧数据",
        subject_type="测试",
        predicate="过期",
        object="测试",
        object_type="测试",
        memory_type="process",  # 过程记忆只保留90天
        importance_score=0.1,
        session_id="old_test"
    )
    old_quintuple["timestamp"] = old_time
    typed_memory_storage.store_memory(old_quintuple)
    
    # 执行清理
    cleaned_count = typed_memory_storage.cleanup_old_memories()
    print(f"清理了 {cleaned_count} 个过期记忆")
    
    # 验证清理结果
    process_memories = typed_memory_storage.get_memories_by_type(MemoryType.PROCESS)
    print(f"清理后过程记忆数量: {len(process_memories)}")
    
    print("\n=== 分类型存储系统测试完成 ===")

if __name__ == "__main__":
    test_typed_memory_storage()