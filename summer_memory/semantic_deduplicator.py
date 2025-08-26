#!/usr/bin/env python3
"""
语义去重机制
基于语义相似度进行记忆去重和合并
"""

import re
import math
import logging
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict
import difflib

logger = logging.getLogger(__name__)


class SemanticDeduplicator:
    """语义去重器"""
    
    def __init__(self, similarity_threshold=0.8):
        self.similarity_threshold = similarity_threshold
        
    def normalize_text(self, text: str) -> str:
        """标准化文本"""
        # 转换为小写
        text = text.lower()
        # 移除标点符号
        text = re.sub(r'[^\w\s]', '', text)
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        """计算Jaccard相似度"""
        set1 = set(self.normalize_text(text1).split())
        set2 = set(self.normalize_text(text2).split())
        
        if not set1 and not set2:
            return 1.0
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def calculate_cosine_similarity(self, text1: str, text2: str) -> float:
        """计算余弦相似度（基于词频）"""
        def get_word_vector(text):
            words = self.normalize_text(text).split()
            vector = defaultdict(int)
            for word in words:
                vector[word] += 1
            return vector
        
        vec1 = get_word_vector(text1)
        vec2 = get_word_vector(text2)
        
        # 计算点积
        dot_product = sum(vec1[word] * vec2[word] for word in vec1 if word in vec2)
        
        # 计算向量长度
        magnitude1 = math.sqrt(sum(vec1[word] ** 2 for word in vec1))
        magnitude2 = math.sqrt(sum(vec2[word] ** 2 for word in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def calculate_string_similarity(self, text1: str, text2: str) -> float:
        """计算字符串相似度（使用difflib）"""
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def calculate_semantic_similarity(self, quintuple1: Dict[str, Any], quintuple2: Dict[str, Any]) -> float:
        """计算五元组的语义相似度"""
        # 计算各个组件的相似度
        subject_sim = self.calculate_string_similarity(quintuple1["subject"], quintuple2["subject"])
        subject_type_sim = self.calculate_string_similarity(quintuple1["subject_type"], quintuple2["subject_type"])
        predicate_sim = self.calculate_string_similarity(quintuple1["predicate"], quintuple2["predicate"])
        object_sim = self.calculate_string_similarity(quintuple1["object"], quintuple2["object"])
        object_type_sim = self.calculate_string_similarity(quintuple1["object_type"], quintuple2["object_type"])
        
        # 计算整体相似度（加权平均）
        weights = [0.3, 0.1, 0.3, 0.2, 0.1]  # subject, subject_type, predicate, object, object_type
        similarities = [subject_sim, subject_type_sim, predicate_sim, object_sim, object_type_sim]
        
        overall_similarity = sum(w * s for w, s in zip(weights, similarities))
        return overall_similarity
    
    def are_semantically_similar(self, quintuple1: Dict[str, Any], quintuple2: Dict[str, Any]) -> bool:
        """判断两个五元组是否语义相似"""
        similarity = self.calculate_semantic_similarity(quintuple1, quintuple2)
        return similarity >= self.similarity_threshold
    
    def find_similar_quintuples(self, target_quintuple: Dict[str, Any], 
                               quintuples: List[Dict[str, Any]]) -> List[Tuple[int, float]]:
        """查找与目标五元组相似的其他五元组"""
        similar_pairs = []
        
        for i, quintuple in enumerate(quintuples):
            if quintuple is not target_quintuple:
                similarity = self.calculate_semantic_similarity(target_quintuple, quintuple)
                if similarity >= self.similarity_threshold:
                    similar_pairs.append((i, similarity))
        
        # 按相似度降序排序
        similar_pairs.sort(key=lambda x: x[1], reverse=True)
        return similar_pairs
    
    def deduplicate_quintuples(self, quintuples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对五元组进行语义去重"""
        if not quintuples:
            return []
        
        unique_quintuples = []
        processed_indices = set()
        
        for i, quintuple in enumerate(quintuples):
            if i in processed_indices:
                continue
            
            # 查找相似的五元组
            similar_pairs = self.find_similar_quintuples(quintuple, quintuples)
            
            if similar_pairs:
                # 找到相似的五元组，进行合并
                similar_indices = [i] + [pair[0] for pair in similar_pairs]
                processed_indices.update(similar_indices)
                
                # 合并相似的五元组
                merged_quintuple = self.merge_similar_quintuples([quintuples[j] for j in similar_indices])
                unique_quintuples.append(merged_quintuple)
            else:
                # 没有相似的五元组，直接添加
                processed_indices.add(i)
                unique_quintuples.append(quintuple)
        
        return unique_quintuples
    
    def merge_similar_quintuples(self, similar_quintuples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并相似的五元组"""
        if not similar_quintuples:
            return {}
        
        if len(similar_quintuples) == 1:
            return similar_quintuples[0]
        
        # 使用最新的五元组作为基础
        base_quintuple = max(similar_quintuples, key=lambda x: x.get("timestamp", 0))
        
        # 合并逻辑
        merged = base_quintuple.copy()
        
        # 更新重要性分数（取最大值）
        max_importance = max(q.get("importance_score", 0.5) for q in similar_quintuples)
        merged["importance_score"] = max_importance
        
        # 合并会话ID
        session_ids = set(q.get("session_id", "") for q in similar_quintuples)
        merged["session_ids"] = list(session_ids)
        
        # 记录合并信息
        merged["merged_from"] = len(similar_quintuples)
        merged["merge_timestamp"] = max(q.get("timestamp", 0) for q in similar_quintuples)
        
        return merged
    
    def group_by_similarity(self, quintuples: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """将五元组按相似度分组"""
        if not quintuples:
            return []
        
        groups = []
        processed_indices = set()
        
        for i, quintuple in enumerate(quintuples):
            if i in processed_indices:
                continue
            
            # 创建新组
            group = [quintuple]
            processed_indices.add(i)
            
            # 查找相似的五元组
            for j, other_quintuple in enumerate(quintuples):
                if j != i and j not in processed_indices:
                    if self.are_semantically_similar(quintuple, other_quintuple):
                        group.append(other_quintuple)
                        processed_indices.add(j)
            
            groups.append(group)
        
        return groups
    
    def analyze_similarity_patterns(self, quintuples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析相似度模式"""
        if len(quintuples) < 2:
            return {"total_quintuples": len(quintuples), "similarity_groups": 0}
        
        similarity_groups = self.group_by_similarity(quintuples)
        
        # 统计组大小分布
        group_sizes = [len(group) for group in similarity_groups]
        
        return {
            "total_quintuples": len(quintuples),
            "similarity_groups": len(similarity_groups),
            "unique_quintuples": len([g for g in similarity_groups if len(g) == 1]),
            "duplicate_groups": len([g for g in similarity_groups if len(g) > 1]),
            "max_group_size": max(group_sizes) if group_sizes else 0,
            "average_group_size": sum(group_sizes) / len(group_sizes) if group_sizes else 0,
            "deduplication_ratio": (len(quintuples) - len(similarity_groups)) / len(quintuples)
        }
    
    def get_quintuple_signature(self, quintuple: Dict[str, Any]) -> str:
        """获取五元组的签名（用于快速比较）"""
        normalized_subject = self.normalize_text(quintuple["subject"])
        normalized_predicate = self.normalize_text(quintuple["predicate"])
        normalized_object = self.normalize_text(quintuple["object"])
        
        return f"{normalized_subject}|{normalized_predicate}|{normalized_object}"
    
    def fast_deduplicate(self, quintuples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """快速去重（基于精确匹配）"""
        seen_signatures = set()
        unique_quintuples = []
        
        for quintuple in quintuples:
            signature = self.get_quintuple_signature(quintuple)
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                unique_quintuples.append(quintuple)
        
        return unique_quintuples
    
    def smart_deduplicate(self, quintuples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """智能去重（先快速去重，再语义去重）"""
        # 第一步：快速去重
        fast_deduplicated = self.fast_deduplicate(quintuples)
        
        # 第二步：语义去重
        semantically_deduplicated = self.deduplicate_quintuples(fast_deduplicated)
        
        logger.info(f"智能去重: {len(quintuples)} -> {len(fast_deduplicated)} -> {len(semantically_deduplicated)}")
        
        return semantically_deduplicated


# 全局语义去重器实例
semantic_deduplicator = SemanticDeduplicator()