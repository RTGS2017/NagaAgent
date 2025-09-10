#!/usr/bin/env python3
"""
智能记忆分析提取引擎
根据查询需求动态选择记忆提取策略
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, Counter
import re
from datetime import datetime

# 添加项目根目录到路径
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from system.config import config
from openai import OpenAI, AsyncOpenAI

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


class QueryType(Enum):
    """查询类型枚举"""
    FACTUAL = "factual"           # 事实查询
    TEMPORAL = "temporal"         # 时间查询
    RELATIONAL = "relational"     # 关系查询
    EMOTIONAL = "emotional"       # 情感查询
    PROCEDURAL = "procedural"     # 过程查询
    META = "meta"                # 元查询
    COMPREHENSIVE = "comprehensive"  # 综合查询


class ExtractionStrategy(Enum):
    """提取策略枚举"""
    KEYWORD_BASED = "keyword_based"        # 基于关键词
    SEMANTIC_SEARCH = "semantic_search"      # 语义搜索
    TIME_BASED = "time_based"               # 基于时间
    IMPORTANCE_BASED = "importance_based"    # 基于重要性
    TYPE_BASED = "type_based"               # 基于类型
    HYBRID = "hybrid"                       # 混合策略


@dataclass
class QueryAnalysis:
    """查询分析结果"""
    query_type: QueryType
    keywords: List[str]
    entities: List[str]
    time_constraints: Optional[Dict[str, Any]]
    importance_threshold: float
    memory_types: List[str]
    extraction_strategy: ExtractionStrategy
    confidence: float


@dataclass
class ExtractionResult:
    """提取结果"""
    quintuples: List[Dict[str, Any]]
    relevance_scores: List[float]
    extraction_metadata: Dict[str, Any]
    processing_time: float


class IntelligentMemoryExtractor:
    """智能记忆提取引擎"""
    
    def __init__(self):
        self.client = client
        self.async_client = async_client
        self.query_history = []
        self.performance_metrics = defaultdict(list)
        
        # 查询模式识别
        self.temporal_patterns = [
            r"最近|今天|昨天|明天|前天|后天|上周|下周|上个月|下个月|去年|今年",
            r"\d+小时前|\d+天前|\d+周前|\d+月前|\d+年前",
            r"\d{4}年|\d{1,2}月|\d{1,2}日"
        ]
        
        self.importance_patterns = [
            r"重要|关键|核心|主要|首要|必要",
            r"详细|具体|全面|完整",
            r"简单|大概|基本|一般"
        ]
        
        self.emotional_patterns = [
            r"喜欢|讨厌|爱|恨|开心|难过|愤怒|害怕|满意|失望",
            r"感觉|觉得|认为|以为|想|希望"
        ]
    
    def _get_timestamp_value(self, quintuple: Dict[str, Any]) -> float:
        """获取五元组的时间戳值（支持新旧格式）"""
        # 优先使用 timestamp_raw（新格式）
        if "timestamp_raw" in quintuple:
            return quintuple["timestamp_raw"]
        # 如果 timestamp 是字符串（新格式），尝试解析
        elif isinstance(quintuple.get("timestamp"), str):
            try:
                time_str = quintuple["timestamp"]
                if " " in time_str:
                    dt = datetime.strptime(time_str.split(" ")[0] + " " + time_str.split(" ")[1], "%Y-%m-%d %H:%M:%S")
                    return dt.timestamp()
            except:
                pass
        # 回退到当前时间
        return time.time()
    
    async def analyze_query(self, query: str, context: str = "") -> QueryAnalysis:
        """分析查询，确定提取策略"""
        # 基础分析
        keywords = self._extract_keywords(query)
        entities = self._extract_entities(query)
        time_constraints = self._extract_time_constraints(query)
        importance_threshold = self._extract_importance_threshold(query)
        memory_types = self._infer_memory_types(query)
        query_type = self._classify_query_type(query)
        extraction_strategy = self._determine_extraction_strategy(query_type, keywords, time_constraints)
        
        # 计算置信度
        confidence = self._calculate_analysis_confidence(
            query_type, keywords, entities, time_constraints
        )
        
        analysis = QueryAnalysis(
            query_type=query_type,
            keywords=keywords,
            entities=entities,
            time_constraints=time_constraints,
            importance_threshold=importance_threshold,
            memory_types=memory_types,
            extraction_strategy=extraction_strategy,
            confidence=confidence
        )
        
        # 记录查询历史
        self.query_history.append({
            "timestamp": time.time(),
            "query": query,
            "analysis": analysis,
            "context": context
        })
        
        return analysis
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 移除标点符号和停用词
        query_clean = re.sub(r'[^\w\s]', '', query.lower())
        
        # 简单的停用词列表
        stop_words = {"的", "了", "是", "在", "有", "和", "与", "或", "但", "如果", "因为", "所以", "这个", "那个"}
        
        # 分词和过滤
        words = [word for word in query_clean.split() if word not in stop_words and len(word) > 1]
        
        return list(set(words))  # 去重
    
    def _extract_entities(self, query: str) -> List[str]:
        """提取实体（简化版本）"""
        # 这里使用简单的规则，实际应用中可以使用NER模型
        entities = []
        
        # 匹配中文人名（简化）
        name_pattern = r'[一-龯]{2,4}'
        names = re.findall(name_pattern, query)
        entities.extend(names)
        
        # 匹配专有名词（大写开头的词）
        proper_nouns = re.findall(r'\b[A-Z][a-z]+\b', query)
        entities.extend(proper_nouns)
        
        return list(set(entities))
    
    def _extract_time_constraints(self, query: str) -> Optional[Dict[str, Any]]:
        """提取时间约束"""
        for pattern in self.temporal_patterns:
            if re.search(pattern, query):
                # 简化的时间解析
                if "最近" in query:
                    return {"type": "recent", "value": 24}  # 默认24小时
                elif "今天" in query:
                    return {"type": "today"}
                elif "昨天" in query:
                    return {"type": "yesterday"}
                elif "小时前" in query:
                    match = re.search(r'(\d+)小时前', query)
                    if match:
                        return {"type": "hours_ago", "value": int(match.group(1))}
        
        return None
    
    def _extract_importance_threshold(self, query: str) -> float:
        """提取重要性阈值"""
        for pattern in self.importance_patterns:
            if re.search(pattern, query):
                if "重要" in query or "关键" in query or "核心" in query:
                    return 0.8
                elif "详细" in query or "具体" in query or "全面" in query:
                    return 0.6
                elif "简单" in query or "大概" in query or "基本" in query:
                    return 0.3
        
        return 0.5  # 默认阈值
    
    def _infer_memory_types(self, query: str) -> List[str]:
        """推断记忆类型"""
        memory_types = ["fact"]  # 默认包含事实记忆
        
        for pattern in self.emotional_patterns:
            if re.search(pattern, query):
                memory_types.append("emotion")
        
        if any(word in query for word in ["如何", "怎么", "步骤", "过程", "方法"]):
            memory_types.append("process")
        
        if any(word in query for word in ["关于", "是什么", "为什么", "解释"]):
            memory_types.append("meta")
        
        return list(set(memory_types))
    
    def _classify_query_type(self, query: str) -> QueryType:
        """分类查询类型"""
        query_lower = query.lower()
        
        # 时间查询
        if any(pattern in query_lower for pattern in ["什么时候", "何时", "多久", "最近", "今天", "昨天"]):
            return QueryType.TEMPORAL
        
        # 情感查询
        if any(pattern in query_lower for pattern in ["感觉", "喜欢", "讨厌", "开心", "难过"]):
            return QueryType.EMOTIONAL
        
        # 过程查询
        if any(pattern in query_lower for pattern in ["如何", "怎么", "步骤", "过程", "方法"]):
            return QueryType.PROCEDURAL
        
        # 元查询
        if any(pattern in query_lower for pattern in ["关于", "是什么", "为什么", "解释", "总结"]):
            return QueryType.META
        
        # 关系查询
        if any(pattern in query_lower for pattern in ["关系", "联系", "关联", "和", "与"]):
            return QueryType.RELATIONAL
        
        # 默认为事实查询
        return QueryType.FACTUAL
    
    def _determine_extraction_strategy(self, query_type: QueryType, keywords: List[str], 
                                     time_constraints: Optional[Dict[str, Any]]) -> ExtractionStrategy:
        """确定提取策略"""
        if query_type == QueryType.TEMPORAL:
            return ExtractionStrategy.TIME_BASED
        elif query_type == QueryType.EMOTIONAL:
            return ExtractionStrategy.TYPE_BASED
        elif query_type == QueryType.PROCEDURAL:
            return ExtractionStrategy.TYPE_BASED
        elif time_constraints:
            return ExtractionStrategy.HYBRID
        elif len(keywords) <= 2:
            return ExtractionStrategy.SEMANTIC_SEARCH
        else:
            return ExtractionStrategy.KEYWORD_BASED
    
    def _calculate_analysis_confidence(self, query_type: QueryType, keywords: List[str], 
                                   entities: List[str], time_constraints: Optional[Dict[str, Any]]) -> float:
        """计算分析置信度"""
        confidence = 0.5  # 基础置信度
        
        # 基于关键词数量
        if len(keywords) >= 2:
            confidence += 0.2
        
        # 基于实体识别
        if entities:
            confidence += 0.2
        
        # 基于时间约束
        if time_constraints:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    async def extract_memories(self, query: str, context: str = "", 
                            max_results: int = 10) -> ExtractionResult:
        """智能提取记忆"""
        start_time = time.time()
        
        # 分析查询
        analysis = await self.analyze_query(query, context)
        
        logger.info(f"查询分析结果: {analysis.query_type.value}, 策略: {analysis.extraction_strategy.value}")
        
        # 根据策略提取记忆
        if analysis.extraction_strategy == ExtractionStrategy.KEYWORD_BASED:
            quintuples = await self._extract_keyword_based(analysis)
        elif analysis.extraction_strategy == ExtractionStrategy.SEMANTIC_SEARCH:
            quintuples = await self._extract_semantic_search(analysis)
        elif analysis.extraction_strategy == ExtractionStrategy.TIME_BASED:
            quintuples = await self._extract_time_based(analysis)
        elif analysis.extraction_strategy == ExtractionStrategy.IMPORTANCE_BASED:
            quintuples = await self._extract_importance_based(analysis)
        elif analysis.extraction_strategy == ExtractionStrategy.TYPE_BASED:
            quintuples = await self._extract_type_based(analysis)
        elif analysis.extraction_strategy == ExtractionStrategy.HYBRID:
            quintuples = await self._extract_hybrid(analysis)
        else:
            quintuples = []
        
        # 计算相关性分数
        relevance_scores = self._calculate_relevance_scores(quintuples, analysis)
        
        # 排序和限制结果
        sorted_results = sorted(zip(quintuples, relevance_scores), 
                               key=lambda x: x[1], reverse=True)
        
        final_quintuples = [q for q, score in sorted_results[:max_results]]
        final_scores = [score for q, score in sorted_results[:max_results]]
        
        processing_time = time.time() - start_time
        
        # 记录性能指标
        self.performance_metrics[analysis.extraction_strategy.value].append(processing_time)
        
        result = ExtractionResult(
            quintuples=final_quintuples,
            relevance_scores=final_scores,
            extraction_metadata={
                "query_analysis": analysis,
                "total_found": len(quintuples),
                "returned": len(final_quintuples),
                "strategy_used": analysis.extraction_strategy.value
            },
            processing_time=processing_time
        )
        
        logger.info(f"提取完成: 找到 {len(quintuples)} 个，返回 {len(final_quintuples)} 个，耗时 {processing_time:.3f}s")
        
        return result
    
    async def _extract_keyword_based(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """基于关键词提取"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        quintuples = query_quintuples_by_keywords(
            analysis.keywords,
            memory_types=analysis.memory_types,
            importance_threshold=analysis.importance_threshold
        )
        
        return quintuples
    
    async def _extract_semantic_search(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """语义搜索提取"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        # 扩展搜索词
        expanded_keywords = self._expand_keywords_semantically(analysis.keywords)
        
        all_quintuples = []
        for keyword in expanded_keywords:
            quintuples = query_quintuples_by_keywords(
                [keyword],
                memory_types=analysis.memory_types,
                importance_threshold=analysis.importance_threshold
            )
            all_quintuples.extend(quintuples)
        
        # 去重
        unique_quintuples = self._deduplicate_quintuples(all_quintuples)
        
        return unique_quintuples
    
    async def _extract_time_based(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """基于时间提取"""
        from summer_memory.quintuple_graph import get_memory_timeline
        
        time_window = None
        if analysis.time_constraints:
            if analysis.time_constraints["type"] == "recent":
                time_window = analysis.time_constraints.get("value", 24) * 3600
            elif analysis.time_constraints["type"] == "hours_ago":
                time_window = analysis.time_constraints.get("value", 24) * 3600
        
        timeline = get_memory_timeline(
            keywords=analysis.keywords,
            memory_types=analysis.memory_types,
            time_window=time_window
        )
        
        return timeline
    
    async def _extract_importance_based(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """基于重要性提取"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        quintuples = query_quintuples_by_keywords(
            analysis.keywords,
            memory_types=analysis.memory_types,
            importance_threshold=analysis.importance_threshold
        )
        
        # 按重要性排序
        sorted_quintuples = sorted(quintuples, 
                                 key=lambda x: x.get("importance_score", 0.5), 
                                 reverse=True)
        
        return sorted_quintuples
    
    async def _extract_type_based(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """基于类型提取"""
        from summer_memory.quintuple_graph import get_typed_memories
        
        quintuples = get_typed_memories(
            memory_types=analysis.memory_types,
            min_importance=analysis.importance_threshold
        )
        
        return quintuples
    
    async def _extract_hybrid(self, analysis: QueryAnalysis) -> List[Dict[str, Any]]:
        """混合策略提取"""
        # 结合多种策略
        keyword_results = await self._extract_keyword_based(analysis)
        type_results = await self._extract_type_based(analysis)
        
        # 合并结果
        all_quintuples = keyword_results + type_results
        
        # 去重
        unique_quintuples = self._deduplicate_quintuples(all_quintuples)
        
        return unique_quintuples
    
    def _expand_keywords_semantically(self, keywords: List[str]) -> List[str]:
        """语义扩展关键词"""
        # 简化的同义词扩展
        synonyms = {
            "学习": ["学习", "研究", "掌握", "了解"],
            "工作": ["工作", "上班", "职业", "事业"],
            "喜欢": ["喜欢", "爱好", "热爱", "感兴趣"],
            "重要": ["重要", "关键", "核心", "主要"]
        }
        
        expanded = keywords.copy()
        for keyword in keywords:
            if keyword in synonyms:
                expanded.extend(synonyms[keyword])
        
        return list(set(expanded))
    
    def _deduplicate_quintuples(self, quintuples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重五元组"""
        seen = set()
        unique_quintuples = []
        
        for quintuple in quintuples:
            key = (quintuple["subject"], quintuple["predicate"], quintuple["object"])
            if key not in seen:
                seen.add(key)
                unique_quintuples.append(quintuple)
        
        return unique_quintuples
    
    def _calculate_relevance_scores(self, quintuples: List[Dict[str, Any]], 
                                  analysis: QueryAnalysis) -> List[float]:
        """计算相关性分数"""
        scores = []
        
        for quintuple in quintuples:
            score = 0.0
            
            # 关键词匹配分数
            keyword_matches = sum(1 for keyword in analysis.keywords 
                               if keyword in quintuple["subject"] or 
                                  keyword in quintuple["predicate"] or 
                                  keyword in quintuple["object"])
            score += (keyword_matches / len(analysis.keywords)) * 0.4
            
            # 重要性分数
            importance = quintuple.get("importance_score", 0.5)
            score += importance * 0.3
            
            # 时间衰减分数
            if analysis.time_constraints:
                age = time.time() - self._get_timestamp_value(quintuple)
                time_decay = max(0.1, 1.0 - (age / (30 * 24 * 3600)))  # 30天衰减
                score += time_decay * 0.3
            
            scores.append(min(score, 1.0))
        
        return scores
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        metrics = {}
        for strategy, times in self.performance_metrics.items():
            if times:
                metrics[strategy] = {
                    "count": len(times),
                    "average_time": sum(times) / len(times),
                    "min_time": min(times),
                    "max_time": max(times)
                }
        
        return metrics
    
    def get_query_statistics(self) -> Dict[str, Any]:
        """获取查询统计"""
        if not self.query_history:
            return {}
        
        query_types = Counter(q["analysis"].query_type.value for q in self.query_history)
        strategies = Counter(q["analysis"].extraction_strategy.value for q in self.query_history)
        
        return {
            "total_queries": len(self.query_history),
            "query_types": dict(query_types),
            "strategies_used": dict(strategies),
            "average_confidence": sum(q["analysis"].confidence for q in self.query_history) / len(self.query_history)
        }


# 全局智能提取引擎实例
intelligent_memory_extractor = IntelligentMemoryExtractor()