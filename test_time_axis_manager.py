#!/usr/bin/env python3
"""
测试时间轴管理系统的脚本
"""

import sys
import os
import time
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, get_memory_timeline, get_recent_quintuples, analyze_temporal_patterns
from summer_memory.time_axis_manager import time_axis_manager

def test_time_axis_manager():
    """测试时间轴管理功能"""
    print("=== 测试时间轴管理系统 ===")
    
    # 创建一些测试五元组，包含不同时间戳
    test_quintuples = []
    
    # 创建当前时间的五元组
    current_quintuple = create_enhanced_quintuple(
        subject="当前用户",
        subject_type="人物",
        predicate="测试",
        object="时间轴系统",
        object_type="系统",
        memory_type="fact",
        importance_score=0.8,
        session_id="time_test_001"
    )
    test_quintuples.append(current_quintuple)
    
    # 创建1小时前的五元组
    past_time = time.time() - 3600  # 1小时前
    past_quintuple = create_enhanced_quintuple(
        subject="过去用户",
        subject_type="人物",
        predicate="使用",
        object="旧版本",
        object_type="系统",
        memory_type="fact",
        importance_score=0.6,
        session_id="time_test_002"
    )
    past_quintuple["timestamp"] = past_time
    test_quintuples.append(past_quintuple)
    
    # 创建2天前的五元组
    older_time = time.time() - 2 * 24 * 3600  # 2天前
    older_quintuple = create_enhanced_quintuple(
        subject="早期用户",
        subject_type="人物",
        predicate="体验",
        object="原型系统",
        object_type="系统",
        memory_type="fact",
        importance_score=0.9,
        session_id="time_test_003"
    )
    older_quintuple["timestamp"] = older_time
    test_quintuples.append(older_quintuple)
    
    # 存储测试五元组
    print("存储测试五元组...")
    store_quintuples(test_quintuples)
    
    # 测试时间衰减
    print("\n=== 测试时间衰减 ===")
    for i, quintuple in enumerate(test_quintuples):
        decay_factor = time_axis_manager.calculate_time_decay_factor(quintuple["timestamp"])
        decayed_importance = time_axis_manager.apply_time_decay(quintuple)
        age_hours = (time.time() - quintuple["timestamp"]) / 3600
        
        print(f"  五元组 {i+1}:")
        print(f"    主体: {quintuple['subject']}")
        print(f"    原始重要性: {quintuple['importance_score']:.2f}")
        print(f"    年龄: {age_hours:.1f} 小时")
        print(f"    衰减因子: {decay_factor:.3f}")
        print(f"    衰减后重要性: {decayed_importance:.3f}")
    
    # 测试时间窗口查询
    print("\n=== 测试时间窗口查询 ===")
    
    # 获取最近24小时的五元组
    recent_quintuples = get_recent_quintuples(hours=24)
    print(f"最近24小时内的五元组数量: {len(recent_quintuples)}")
    
    # 获取最近3天的五元组
    recent_3days = get_recent_quintuples(hours=72)
    print(f"最近3天内的五元组数量: {len(recent_3days)}")
    
    # 测试记忆时间线
    print("\n=== 测试记忆时间线 ===")
    timeline = get_memory_timeline()
    print(f"记忆时间线包含 {len(timeline)} 个条目")
    for i, entry in enumerate(timeline[:3]):  # 只显示前3个
        print(f"  {i+1}. {entry['subject']} -{entry['predicate']}- {entry['object']}")
        print(f"     时间: {time_axis_manager.format_timestamp(entry['timestamp'])}")
        print(f"     衰减后重要性: {entry['decayed_importance']:.3f}")
    
    # 测试时间模式分析
    print("\n=== 测试时间模式分析 ===")
    patterns = analyze_temporal_patterns()
    print(f"总五元组数量: {patterns['total_quintuples']}")
    print(f"时间跨度: {patterns['time_span_hours']:.1f} 小时")
    print(f"平均年龄: {patterns['average_age_hours']:.1f} 小时")
    print("时间分布:")
    for period, count in patterns['time_distribution'].items():
        print(f"  {period}: {count}")
    
    # 测试会话管理
    print("\n=== 测试会话管理 ===")
    session_quintuples = time_axis_manager.get_session_quintuples(test_quintuples, "time_test_001")
    print(f"会话 time_test_001 的五元组数量: {len(session_quintuples)}")
    
    # 测试会话合并
    merged_sessions = time_axis_manager.merge_sessions(test_quintuples, ["time_test_001", "time_test_002"])
    print(f"合并会话后的五元组数量: {len(merged_sessions)}")
    
    print("\n=== 时间轴管理系统测试完成 ===")

if __name__ == "__main__":
    test_time_axis_manager()