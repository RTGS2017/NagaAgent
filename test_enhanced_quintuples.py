#!/usr/bin/env python3
"""
测试增强五元组数据结构的脚本
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from summer_memory.quintuple_extractor import extract_quintuples, create_enhanced_quintuple
from summer_memory.quintuple_graph import store_quintuples, query_quintuples_by_keywords

def test_enhanced_quintuples():
    """测试增强五元组功能"""
    print("=== 测试增强五元组数据结构 ===")
    
    # 测试文本
    test_text = "小明在北京大学学习计算机科学，他喜欢编程和人工智能。"
    
    # 提取五元组
    print(f"测试文本: {test_text}")
    quintuples = extract_quintuples(test_text, session_id="test_session_001")
    
    print(f"提取到 {len(quintuples)} 个增强五元组:")
    for i, quintuple in enumerate(quintuples):
        print(f"  {i+1}. {quintuple}")
    
    # 存储五元组
    print("\n=== 测试存储功能 ===")
    success = store_quintuples(quintuples)
    print(f"存储结果: {success}")
    
    # 测试查询功能
    print("\n=== 测试查询功能 ===")
    keywords = ["小明", "北京大学"]
    results = query_quintuples_by_keywords(keywords)
    print(f"查询关键词 {keywords}，找到 {len(results)} 个结果:")
    for i, result in enumerate(results):
        print(f"  {i+1}. {result['subject']} -{result['predicate']}- {result['object']}")
        print(f"      时间戳: {result['timestamp']}")
        print(f"      会话ID: {result['session_id']}")
        print(f"      记忆类型: {result['memory_type']}")
        print(f"      重要性分数: {result['importance_score']}")
    
    # 测试创建增强五元组
    print("\n=== 测试手动创建增强五元组 ===")
    manual_quintuple = create_enhanced_quintuple(
        subject="测试用户",
        subject_type="人物",
        predicate="使用",
        object="增强记忆系统",
        object_type="系统",
        memory_type="fact",
        importance_score=0.8,
        session_id="manual_test"
    )
    print(f"手动创建的五元组: {manual_quintuple}")
    
    # 存储手动创建的五元组
    store_quintuples([manual_quintuple])
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_enhanced_quintuples()