#!/usr/bin/env python3
"""
记忆重要程度路由系统
使用大模型分析记忆重要性，实现智能记忆路由
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# 添加项目根目录到路径，以便导入config
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from system.config import config
from openai import OpenAI, AsyncOpenAI
from .json_utils import clean_and_parse_json

# 初始化OpenAI客户端
client = OpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

async_client = AsyncOpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型枚举"""
    FACT = "fact"           # 事实记忆
    PROCESS = "process"     # 过程记忆
    EMOTION = "emotion"     # 情感记忆
    META = "meta"          # 元记忆


class ImportanceLevel(Enum):
    """重要性级别枚举"""
    CRITICAL = 1.0         # 关键
    HIGH = 0.8             # 高
    MEDIUM = 0.6           # 中等
    LOW = 0.4              # 低
    MINIMAL = 0.2          # 最小


@dataclass
class ImportanceFactors:
    """重要性因子"""
    factual_importance: float     # 事实重要性
    emotional_importance: float   # 情感重要性
    contextual_importance: float  # 上下文重要性
    frequency_importance: float   # 频率重要性
    uniqueness_importance: float # 独特性重要性


class MemoryImportanceAnalyzer:
    """记忆重要性分析器"""
    
    def __init__(self):
        self.client = client
        self.async_client = async_client
        self.importance_history = []  # 重要性分析历史
        
    def calculate_basic_importance(self, quintuple: Dict[str, Any], context: str = "") -> float:
        """计算基础重要性分数"""
        score = 0.5  # 基础分数
        
        # 基于实体类型的重要性
        important_entities = {"人物", "组织", "事件", "地点"}
        if (quintuple["subject_type"] in important_entities or 
            quintuple["object_type"] in important_entities):
            score += 0.2
        
        # 基于关系类型的重要性
        important_relations = {"是", "拥有", "完成", "开始", "结束", "创建", "发现", "结婚", "死亡"}
        if quintuple["predicate"] in important_relations:
            score += 0.2
        
        # 基于上下文长度的重要性
        if len(context) > 100:
            score += 0.1
        
        # 基于实体名称的重要性（专有名词通常更重要）
        if (quintuple["subject"][0].isupper() or 
            quintuple["object"][0].isupper()):
            score += 0.1
        
        return min(max(score, 0.0), 1.0)
    
    async def analyze_with_llm(self, quintuple: Dict[str, Any], context: str = "") -> ImportanceFactors:
        """使用大模型分析记忆重要性"""
        prompt = f"""
请分析以下五元组记忆的重要性，从多个维度进行评估：

五元组信息：
- 主体：{quintuple["subject"]} (类型：{quintuple["subject_type"]})
- 关系：{quintuple["predicate"]}
- 客体：{quintuple["object"]} (类型：{quintuple["object_type"]})

上下文信息：
{context}

请从以下5个维度评估重要性（0-1分）：
1. 事实重要性：这个记忆包含的事实信息有多重要？
2. 情感重要性：这个记忆涉及的情感投入有多深？
3. 上下文重要性：这个记忆对理解整体上下文有多重要？
4. 频率重要性：这种类型的记忆出现的频率如何？（罕见=高分）
5. 独特性重要性：这个记忆的内容有多独特？

请以JSON格式返回评估结果，格式如下：
{{
    "factual_importance": 数值,
    "emotional_importance": 数值,
    "contextual_importance": 数值,
    "frequency_importance": 数值,
    "uniqueness_importance": 数值,
    "reasoning": "简要说明评估理由"
}}
"""
        
        try:
            response = await self.async_client.chat.completions.create(
                model=config.api.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3,
                timeout=30
            )
            
            content = response.choices[0].message.content.strip()
            
            # 使用统一的JSON清理和解析工具
            result = clean_and_parse_json(content, expected_type=dict, default={})
            
            return ImportanceFactors(
                factual_importance=result.get("factual_importance", 0.5),
                emotional_importance=result.get("emotional_importance", 0.5),
                contextual_importance=result.get("contextual_importance", 0.5),
                frequency_importance=result.get("frequency_importance", 0.5),
                uniqueness_importance=result.get("uniqueness_importance", 0.5)
            )
            
        except Exception as e:
            logger.warning(f"大模型分析失败: {e}")
            # 返回默认值
            return ImportanceFactors(0.5, 0.5, 0.5, 0.5, 0.5)
    
    def calculate_composite_importance(self, factors: ImportanceFactors) -> float:
        """计算综合重要性分数"""
        # 权重配置
        weights = {
            "factual": 0.3,
            "emotional": 0.2,
            "contextual": 0.25,
            "frequency": 0.15,
            "uniqueness": 0.1
        }
        
        composite_score = (
            factors.factual_importance * weights["factual"] +
            factors.emotional_importance * weights["emotional"] +
            factors.contextual_importance * weights["contextual"] +
            factors.frequency_importance * weights["frequency"] +
            factors.uniqueness_importance * weights["uniqueness"]
        )
        
        return min(max(composite_score, 0.0), 1.0)
    
    def determine_memory_type(self, quintuple: Dict[str, Any], factors: ImportanceFactors) -> MemoryType:
        """确定记忆类型"""
        # 基于关系和实体类型判断
        emotional_predicates = {"喜欢", "讨厌", "爱", "恨", "开心", "难过", "愤怒", "害怕"}
        process_predicates = {"学习", "工作", "进行", "完成", "开始", "结束"}
        
        if quintuple["predicate"] in emotional_predicates:
            return MemoryType.EMOTION
        elif quintuple["predicate"] in process_predicates:
            return MemoryType.PROCESS
        elif (quintuple["subject_type"] == "概念" or 
              quintuple["object_type"] == "概念" or
              "关于" in quintuple["predicate"]):
            return MemoryType.META
        else:
            return MemoryType.FACT
    
    async def analyze_memory_importance(self, quintuple: Dict[str, Any], 
                                       context: str = "",
                                       use_llm: bool = True) -> Dict[str, Any]:
        """全面分析记忆重要性"""
        # 计算基础重要性
        basic_score = self.calculate_basic_importance(quintuple, context)
        
        factors = None
        composite_score = basic_score
        
        # 使用大模型进行深入分析
        if use_llm:
            try:
                factors = await self.analyze_with_llm(quintuple, context)
                composite_score = self.calculate_composite_importance(factors)
            except Exception as e:
                logger.warning(f"大模型分析失败，使用基础分数: {e}")
                factors = ImportanceFactors(0.5, 0.5, 0.5, 0.5, 0.5)
        
        # 确定记忆类型
        memory_type = self.determine_memory_type(quintuple, factors or ImportanceFactors(0.5, 0.5, 0.5, 0.5, 0.5))
        
        # 确定重要性级别
        importance_level = self.get_importance_level(composite_score)
        
        # 记录分析历史
        analysis_record = {
            "timestamp": time.time(),
            "quintuple": quintuple,
            "basic_score": basic_score,
            "composite_score": composite_score,
            "importance_level": importance_level.value,
            "memory_type": memory_type.value,
            "factors": factors.__dict__ if factors else None,
            "context_length": len(context)
        }
        self.importance_history.append(analysis_record)
        
        return {
            "importance_score": composite_score,
            "importance_level": importance_level.value,
            "memory_type": memory_type.value,
            "factors": factors.__dict__ if factors else None,
            "basic_score": basic_score,
            "analysis_timestamp": time.time()
        }
    
    def get_importance_level(self, score: float) -> ImportanceLevel:
        """根据分数获取重要性级别"""
        if score >= 0.9:
            return ImportanceLevel.CRITICAL
        elif score >= 0.7:
            return ImportanceLevel.HIGH
        elif score >= 0.5:
            return ImportanceLevel.MEDIUM
        elif score >= 0.3:
            return ImportanceLevel.LOW
        else:
            return ImportanceLevel.MINIMAL
    
    def route_memory_by_importance(self, quintuple: Dict[str, Any], 
                                 analysis_result: Dict[str, Any]) -> str:
        """根据重要性路由记忆"""
        importance_score = analysis_result["importance_score"]
        memory_type = analysis_result["memory_type"]
        
        # 路由策略
        if importance_score >= 0.8:
            return "high_priority_storage"  # 高优先级存储
        elif importance_score >= 0.6:
            return "standard_storage"       # 标准存储
        elif importance_score >= 0.4:
            return "compressed_storage"     # 压缩存储
        else:
            return "temporary_storage"      # 临时存储
    
    def get_importance_statistics(self) -> Dict[str, Any]:
        """获取重要性分析统计信息"""
        if not self.importance_history:
            return {}
        
        recent_analyses = self.importance_history[-100:]  # 最近100次分析
        
        scores = [analysis["composite_score"] for analysis in recent_analyses]
        memory_types = [analysis["memory_type"] for analysis in recent_analyses]
        
        # 统计各类型记忆的数量
        type_counts = {}
        for memory_type in memory_types:
            type_counts[memory_type] = type_counts.get(memory_type, 0) + 1
        
        return {
            "total_analyses": len(self.importance_history),
            "recent_analyses": len(recent_analyses),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "memory_type_distribution": type_counts,
            "analysis_methods": {
                "llm_used": sum(1 for a in recent_analyses if a["factors"] is not None),
                "basic_only": sum(1 for a in recent_analyses if a["factors"] is None)
            }
        }
    
    def filter_by_importance(self, quintuples: List[Dict[str, Any]], 
                           min_importance: float = 0.0,
                           max_importance: float = 1.0,
                           memory_types: List[str] = None) -> List[Dict[str, Any]]:
        """根据重要性过滤五元组"""
        filtered = []
        
        for quintuple in quintuples:
            importance = quintuple.get("importance_score", 0.5)
            
            # 检查重要性范围
            if not (min_importance <= importance <= max_importance):
                continue
            
            # 检查记忆类型
            if memory_types and quintuple.get("memory_type", "fact") not in memory_types:
                continue
            
            filtered.append(quintuple)
        
        return filtered
    
    def sort_by_importance(self, quintuples: List[Dict[str, Any]], 
                          descending: bool = True) -> List[Dict[str, Any]]:
        """按重要性排序五元组"""
        return sorted(quintuples, 
                    key=lambda x: x.get("importance_score", 0.5), 
                    reverse=descending)


# 全局重要性分析器实例
memory_importance_analyzer = MemoryImportanceAnalyzer()