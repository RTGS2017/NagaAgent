#!/usr/bin/env python3
"""
多模态查询系统
集成关键词搜索、语义搜索、图搜索等多种查询方式
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
from collections import defaultdict
import re

# 添加项目根目录到路径
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """搜索模式枚举"""
    KEYWORD = "keyword"           # 关键词搜索
    SEMANTIC = "semantic"         # 语义搜索
    GRAPH = "graph"               # 图搜索
    HYBRID = "hybrid"             # 混合搜索
    FUZZY = "fuzzy"               # 模糊搜索


class QueryScope(Enum):
    """查询范围枚举"""
    SUBJECT = "subject"           # 仅主体
    PREDICATE = "predicate"       # 仅关系
    OBJECT = "object"             # 仅客体
    FULL = "full"                 # 全文


@dataclass
class SearchResult:
    """搜索结果"""
    quintuple: Dict[str, Any]
    relevance_score: float
    match_type: str
    search_mode: str
    rank: int


@dataclass
class QueryOptions:
    """查询选项"""
    search_modes: List[SearchMode]
    scope: QueryScope
    max_results: int
    min_relevance: float
    time_window: Optional[int]  # 时间窗口（秒）
    memory_types: Optional[List[str]]
    fuzzy_threshold: float = 0.7


class MultiModalQuerySystem:
    """多模态查询系统"""
    
    def __init__(self):
        self.search_history = []
        self.performance_stats = defaultdict(list)
        
        # 初始化各搜索模块
        self._init_search_modules()
    
    def _init_search_modules(self):
        """初始化搜索模块"""
        # 这里可以初始化向量搜索、图搜索等模块
        # 现在使用简化的实现
        pass
    
    def search(self, query: str, options: Optional[QueryOptions] = None) -> List[SearchResult]:
        """多模态搜索"""
        start_time = time.time()
        
        # 设置默认选项
        if options is None:
            options = QueryOptions(
                search_modes=[SearchMode.KEYWORD, SearchMode.SEMANTIC],
                scope=QueryScope.FULL,
                max_results=10,
                min_relevance=0.3,
                time_window=None,
                memory_types=None
            )
        
        # 执行多模态搜索
        all_results = []
        
        for search_mode in options.search_modes:
            mode_results = self._search_by_mode(query, search_mode, options)
            all_results.extend(mode_results)
        
        # 合并和排序结果
        final_results = self._merge_and_rank_results(all_results, options)
        
        # 记录性能统计
        processing_time = time.time() - start_time
        self.performance_stats["search_time"].append(processing_time)
        
        # 记录搜索历史
        self.search_history.append({
            "timestamp": time.time(),
            "query": query,
            "options": options,
            "results_count": len(final_results),
            "processing_time": processing_time
        })
        
        logger.info(f"多模态搜索完成: 找到 {len(final_results)} 个结果，耗时 {processing_time:.3f}s")
        
        return final_results
    
    def _search_by_mode(self, query: str, mode: SearchMode, options: QueryOptions) -> List[SearchResult]:
        """按指定模式搜索"""
        if mode == SearchMode.KEYWORD:
            return self._keyword_search(query, options)
        elif mode == SearchMode.SEMANTIC:
            return self._semantic_search(query, options)
        elif mode == SearchMode.GRAPH:
            return self._graph_search(query, options)
        elif mode == SearchMode.FUZZY:
            return self._fuzzy_search(query, options)
        elif mode == SearchMode.HYBRID:
            return self._hybrid_search(query, options)
        else:
            return []
    
    def _keyword_search(self, query: str, options: QueryOptions) -> List[SearchResult]:
        """关键词搜索"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        # 提取关键词
        keywords = self._extract_keywords(query)
        
        # 执行搜索
        quintuples = query_quintuples_by_keywords(
            keywords,
            memory_types=options.memory_types,
            importance_threshold=options.min_relevance,
            time_window=options.time_window
        )
        
        # 计算相关性分数
        results = []
        for quintuple in quintuples:
            score = self._calculate_keyword_relevance(quintuple, keywords)
            if score >= options.min_relevance:
                results.append(SearchResult(
                    quintuple=quintuple,
                    relevance_score=score,
                    match_type="keyword",
                    search_mode="keyword",
                    rank=0
                ))
        
        return results
    
    def _semantic_search(self, query: str, options: QueryOptions) -> List[SearchResult]:
        """语义搜索"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        # 语义扩展查询
        expanded_terms = self._semantic_expansion(query)
        
        all_results = []
        for term in expanded_terms:
            quintuples = query_quintuples_by_keywords(
                [term],
                memory_types=options.memory_types,
                importance_threshold=options.min_relevance,
                time_window=options.time_window
            )
            
            for quintuple in quintuples:
                score = self._calculate_semantic_relevance(quintuple, query)
                if score >= options.min_relevance:
                    all_results.append(SearchResult(
                        quintuple=quintuple,
                        relevance_score=score,
                        match_type="semantic",
                        search_mode="semantic",
                        rank=0
                    ))
        
        return all_results
    
    def _graph_search(self, query: str, options: QueryOptions) -> List[SearchResult]:
        """图搜索"""
        from summer_memory.quintuple_graph import query_graph_by_keywords
        
        # 提取实体
        entities = self._extract_entities(query)
        
        if not entities:
            return []
        
        # 在图数据库中搜索路径
        results = []
        for entity in entities:
            graph_results = query_graph_by_keywords(
                [entity],
                memory_types=options.memory_types,
                importance_threshold=options.min_relevance,
                time_window=options.time_window
            )
            
            for quintuple in graph_results:
                score = self._calculate_graph_relevance(quintuple, entities)
                if score >= options.min_relevance:
                    results.append(SearchResult(
                        quintuple=quintuple,
                        relevance_score=score,
                        match_type="graph",
                        search_mode="graph",
                        rank=0
                    ))
        
        return results
    
    def _fuzzy_search(self, query: str, options: QueryOptions) -> List[SearchResult]:
        """模糊搜索"""
        from summer_memory.quintuple_graph import query_quintuples_by_keywords
        
        # 使用通配符进行模糊搜索
        fuzzy_patterns = self._generate_fuzzy_patterns(query)
        
        all_results = []
        for pattern in fuzzy_patterns:
            try:
                quintuples = query_quintuples_by_keywords(
                    [pattern],
                    memory_types=options.memory_types,
                    importance_threshold=options.min_relevance * 0.8,  # 降低阈值
                    time_window=options.time_window
                )
                
                for quintuple in quintuples:
                    score = self._calculate_fuzzy_relevance(quintuple, query)
                    if score >= options.fuzzy_threshold:
                        all_results.append(SearchResult(
                            quintuple=quintuple,
                            relevance_score=score,
                            match_type="fuzzy",
                            search_mode="fuzzy",
                            rank=0
                        ))
            except Exception as e:
                logger.warning(f"模糊搜索失败: {e}")
                continue
        
        return all_results
    
    def _hybrid_search(self, query: str, options: QueryOptions) -> List[SearchResult]:
        """混合搜索"""
        # 结合多种搜索模式
        keyword_results = self._keyword_search(query, options)
        semantic_results = self._semantic_search(query, options)
        
        # 合并结果
        all_results = keyword_results + semantic_results
        
        # 去重并重新计算分数
        unique_results = self._deduplicate_search_results(all_results)
        
        return unique_results
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取
        query_clean = re.sub(r'[^\w\s\u4e00-\u9fff]', '', query.lower())
        
        # 基础停用词
        stop_words = {"的", "了", "是", "在", "有", "和", "与", "或", "但", "如果", "因为", "所以", "这个", "那个", "什么", "怎么", "如何"}
        
        words = [word for word in query_clean.split() if word not in stop_words and len(word) > 1]
        
        return list(set(words))
    
    def _semantic_expansion(self, query: str) -> List[str]:
        """语义扩展"""
        keywords = self._extract_keywords(query)
        
        # 简化的同义词扩展
        synonyms = {
            "学习": ["研究", "掌握", "了解", "学习"],
            "工作": ["上班", "职业", "事业", "工作"],
            "喜欢": ["爱好", "热爱", "感兴趣", "喜欢"],
            "重要": ["关键", "核心", "主要", "重要"],
            "系统": ["平台", "框架", "架构", "系统"]
        }
        
        expanded = keywords.copy()
        for keyword in keywords:
            if keyword in synonyms:
                expanded.extend(synonyms[keyword])
        
        return list(set(expanded))
    
    def _extract_entities(self, query: str) -> List[str]:
        """提取实体"""
        entities = []
        
        # 匹配中文实体
        chinese_entities = re.findall(r'[\u4e00-\u9fff]{2,}', query)
        entities.extend(chinese_entities)
        
        # 匹配英文实体
        english_entities = re.findall(r'\b[A-Z][a-z]+\b', query)
        entities.extend(english_entities)
        
        return list(set(entities))
    
    def _generate_fuzzy_patterns(self, query: str) -> List[str]:
        """生成模糊搜索模式"""
        keywords = self._extract_keywords(query)
        patterns = []
        
        for keyword in keywords:
            # 添加通配符模式
            if len(keyword) >= 2:
                patterns.append(f"*{keyword}*")
                patterns.append(f"{keyword}*")
                patterns.append(f"*{keyword}")
        
        return patterns
    
    def _calculate_keyword_relevance(self, quintuple: Dict[str, Any], keywords: List[str]) -> float:
        """计算关键词相关性"""
        score = 0.0
        searchable_text = f"{quintuple['subject']} {quintuple['predicate']} {quintuple['object']} {quintuple['subject_type']} {quintuple['object_type']}"
        searchable_text = searchable_text.lower()
        
        for keyword in keywords:
            if keyword.lower() in searchable_text:
                score += 1.0
        
        # 标准化分数
        max_score = len(keywords)
        if max_score > 0:
            score = score / max_score
        
        return score
    
    def _calculate_semantic_relevance(self, quintuple: Dict[str, Any], query: str) -> float:
        """计算语义相关性"""
        # 简化的语义相关性计算
        keywords = self._extract_keywords(query)
        return self._calculate_keyword_relevance(quintuple, keywords) * 0.8  # 略微降低权重
    
    def _calculate_graph_relevance(self, quintuple: Dict[str, Any], entities: List[str]) -> float:
        """计算图相关性"""
        score = 0.0
        
        for entity in entities:
            if entity in quintuple['subject'] or entity in quintuple['object']:
                score += 1.0
        
        return score / len(entities) if entities else 0.0
    
    def _calculate_fuzzy_relevance(self, quintuple: Dict[str, Any], query: str) -> float:
        """计算模糊相关性"""
        # 简化的模糊匹配
        searchable_text = f"{quintuple['subject']} {quintuple['predicate']} {quintuple['object']}"
        
        # 计算编辑距离的简化版本
        query_words = self._extract_keywords(query)
        match_count = 0
        
        for query_word in query_words:
            for text_word in searchable_text.split():
                if self._fuzzy_match(query_word, text_word):
                    match_count += 1
        
        return match_count / len(query_words) if query_words else 0.0
    
    def _fuzzy_match(self, word1: str, word2: str, threshold: float = 0.7) -> bool:
        """模糊匹配"""
        if word1 == word2:
            return True
        
        # 简化的相似度计算
        len1, len2 = len(word1), len(word2)
        max_len = max(len1, len2)
        
        if max_len == 0:
            return False
        
        # 计算公共字符比例
        common_chars = set(word1) & set(word2)
        similarity = len(common_chars) / max_len
        
        return similarity >= threshold
    
    def _merge_and_rank_results(self, results: List[SearchResult], options: QueryOptions) -> List[SearchResult]:
        """合并和排序结果"""
        # 去重
        unique_results = self._deduplicate_search_results(results)
        
        # 排序
        sorted_results = sorted(unique_results, key=lambda x: x.relevance_score, reverse=True)
        
        # 应用数量限制
        if options.max_results:
            sorted_results = sorted_results[:options.max_results]
        
        # 更新排名
        for i, result in enumerate(sorted_results):
            result.rank = i + 1
        
        return sorted_results
    
    def _deduplicate_search_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """去重搜索结果"""
        seen = set()
        unique_results = []
        
        for result in results:
            # 使用五元组内容作为唯一标识
            key = (result.quintuple['subject'], result.quintuple['predicate'], result.quintuple['object'])
            
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
            else:
                # 如果已存在，保留分数更高的结果
                for i, existing_result in enumerate(unique_results):
                    existing_key = (existing_result.quintuple['subject'], existing_result.quintuple['predicate'], existing_result.quintuple['object'])
                    if existing_key == key and result.relevance_score > existing_result.relevance_score:
                        unique_results[i] = result
                        break
        
        return unique_results
    
    def get_search_statistics(self) -> Dict[str, Any]:
        """获取搜索统计信息"""
        if not self.search_history:
            return {}
        
        total_searches = len(self.search_history)
        avg_results = sum(h['results_count'] for h in self.search_history) / total_searches
        avg_time = sum(h['processing_time'] for h in self.search_history) / total_searches
        
        # 按搜索模式统计
        mode_stats = defaultdict(int)
        for history in self.search_history:
            for mode in history['options'].search_modes:
                mode_stats[mode.value] += 1
        
        return {
            "total_searches": total_searches,
            "average_results": avg_results,
            "average_time": avg_time,
            "search_modes": dict(mode_stats)
        }
    
    def advanced_search(self, query: str, **kwargs) -> Dict[str, Any]:
        """高级搜索接口"""
        # 构建查询选项
        options = QueryOptions(
            search_modes=kwargs.get('search_modes', [SearchMode.KEYWORD, SearchMode.SEMANTIC]),
            scope=kwargs.get('scope', QueryScope.FULL),
            max_results=kwargs.get('max_results', 10),
            min_relevance=kwargs.get('min_relevance', 0.3),
            time_window=kwargs.get('time_window'),
            memory_types=kwargs.get('memory_types'),
            fuzzy_threshold=kwargs.get('fuzzy_threshold', 0.7)
        )
        
        # 执行搜索
        results = self.search(query, options)
        
        # 分析结果
        analysis = {
            "total_results": len(results),
            "average_relevance": sum(r.relevance_score for r in results) / len(results) if results else 0,
            "search_modes_used": [mode.value for mode in options.search_modes],
            "results_by_type": defaultdict(int),
            "results_by_mode": defaultdict(int)
        }
        
        for result in results:
            memory_type = result.quintuple.get('memory_type', 'fact')
            analysis['results_by_type'][memory_type] += 1
            analysis['results_by_mode'][result.search_mode] += 1
        
        return {
            "query": query,
            "options": options,
            "results": results,
            "analysis": analysis,
            "processing_time": self.search_history[-1]['processing_time'] if self.search_history else 0
        }


# 全局多模态查询系统实例
multi_modal_query_system = MultiModalQuerySystem()