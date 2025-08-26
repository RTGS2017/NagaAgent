#!/usr/bin/env python3
"""
实体消歧系统
为实体创建唯一标识，解决同名实体混淆问题
"""

import json
import logging
import time
import hashlib
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, Counter
import re

# 添加项目根目录到路径
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)


@dataclass
class EntityAttributes:
    """实体属性"""
    name: str
    entity_type: str
    description: str = ""
    aliases: List[str] = None
    context: List[str] = None
    first_seen: float = None
    last_seen: float = None
    frequency: int = 0
    confidence: float = 0.0
    
    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []
        if self.context is None:
            self.context = []
        if self.first_seen is None:
            self.first_seen = time.time()
        if self.last_seen is None:
            self.last_seen = time.time()


@dataclass
class EntityIdentity:
    """实体身份"""
    entity_id: str
    canonical_name: str
    attributes: EntityAttributes
    related_entities: Set[str] = None
    
    def __post_init__(self):
        if self.related_entities is None:
            self.related_entities = set()


class EntityDisambiguator:
    """实体消歧器"""
    
    def __init__(self, storage_path: str = "logs/knowledge_graph"):
        self.storage_path = storage_path
        self.entities: Dict[str, EntityIdentity] = {}
        self.name_index: Dict[str, Set[str]] = defaultdict(set)
        self.alias_index: Dict[str, Set[str]] = defaultdict(set)
        self.context_index: Dict[str, Set[str]] = defaultdict(set)
        
        # 确保目录存在
        os.makedirs(storage_path, exist_ok=True)
        
        # 加载现有实体数据
        self._load_entities()
    
    def _load_entities(self):
        """加载实体数据"""
        entity_file = f"{self.storage_path}/entities.json"
        try:
            with open(entity_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            for entity_id, entity_data in data.items():
                attributes = EntityAttributes(**entity_data['attributes'])
                related_entities = set(entity_data.get('related_entities', []))
                
                entity = EntityIdentity(
                    entity_id=entity_id,
                    canonical_name=entity_data['canonical_name'],
                    attributes=attributes,
                    related_entities=related_entities
                )
                
                self.entities[entity_id] = entity
                
                # 重建索引
                self._index_entity(entity)
                
            logger.info(f"加载了 {len(self.entities)} 个实体")
            
        except FileNotFoundError:
            logger.info("实体文件不存在，将创建新的实体数据库")
        except Exception as e:
            logger.error(f"加载实体数据失败: {e}")
    
    def _save_entities(self):
        """保存实体数据"""
        entity_file = f"{self.storage_path}/entities.json"
        
        data = {}
        for entity_id, entity in self.entities.items():
            data[entity_id] = {
                'canonical_name': entity.canonical_name,
                'attributes': asdict(entity.attributes),
                'related_entities': list(entity.related_entities)
            }
        
        try:
            with open(entity_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"保存了 {len(self.entities)} 个实体")
        except Exception as e:
            logger.error(f"保存实体数据失败: {e}")
    
    def _index_entity(self, entity: EntityIdentity):
        """为实体建立索引"""
        # 名称索引
        self.name_index[entity.canonical_name.lower()].add(entity.entity_id)
        
        # 别名索引
        for alias in entity.attributes.aliases:
            self.alias_index[alias.lower()].add(entity.entity_id)
        
        # 上下文索引
        for context in entity.attributes.context:
            words = re.findall(r'\w+', context.lower())
            for word in words:
                if len(word) > 2:  # 忽略太短的词
                    self.context_index[word].add(entity.entity_id)
    
    def _generate_entity_id(self, name: str, entity_type: str, context: str = "") -> str:
        """生成实体ID"""
        # 基于名称、类型和上下文生成唯一ID
        content = f"{name}|{entity_type}|{context}"
        hash_value = hashlib.md5(content.encode('utf-8')).hexdigest()
        return f"entity_{hash_value[:12]}"
    
    def _calculate_similarity(self, name1: str, name2: str, type1: str, type2: str, context1: str = "", context2: str = "") -> float:
        """计算实体相似度"""
        score = 0.0
        
        # 名称相似度
        if name1.lower() == name2.lower():
            score += 0.5
        elif name1.lower() in name2.lower() or name2.lower() in name1.lower():
            score += 0.3
        
        # 类型相似度
        if type1 == type2:
            score += 0.3
        
        # 上下文相似度
        if context1 and context2:
            context_words1 = set(re.findall(r'\w+', context1.lower()))
            context_words2 = set(re.findall(r'\w+', context2.lower()))
            
            if context_words1 and context_words2:
                intersection = context_words1 & context_words2
                union = context_words1 | context_words2
                jaccard = len(intersection) / len(union)
                score += jaccard * 0.2
        
        return min(score, 1.0)
    
    def disambiguate_entity(self, name: str, entity_type: str, context: str = "", 
                          description: str = "", confidence: float = 0.5) -> EntityIdentity:
        """消歧实体"""
        # 查找候选实体
        candidates = self._find_candidate_entities(name, entity_type, context)
        
        if candidates:
            # 找到最相似的候选
            best_candidate = max(candidates, key=lambda x: x[1])
            candidate_entity, similarity_score = best_candidate
            
            if similarity_score >= 0.7:  # 高相似度阈值
                # 更新现有实体
                self._update_entity(candidate_entity, context, description, confidence)
                return candidate_entity
        
        # 创建新实体
        return self._create_entity(name, entity_type, context, description, confidence)
    
    def _find_candidate_entities(self, name: str, entity_type: str, context: str) -> List[Tuple[EntityIdentity, float]]:
        """查找候选实体"""
        candidates = []
        
        # 通过名称查找
        name_lower = name.lower()
        if name_lower in self.name_index:
            for entity_id in self.name_index[name_lower]:
                entity = self.entities[entity_id]
                similarity = self._calculate_similarity(
                    name, entity.canonical_name,
                    entity_type, entity.attributes.entity_type,
                    context, " ".join(entity.attributes.context)
                )
                candidates.append((entity, similarity))
        
        # 通过上下文查找
        context_words = set(re.findall(r'\w+', context.lower()))
        for word in context_words:
            if len(word) > 2 and word in self.context_index:
                for entity_id in self.context_index[word]:
                    if entity_id not in [c[0].entity_id for c in candidates]:  # 避免重复
                        entity = self.entities[entity_id]
                        similarity = self._calculate_similarity(
                            name, entity.canonical_name,
                            entity_type, entity.attributes.entity_type,
                            context, " ".join(entity.attributes.context)
                        )
                        if similarity >= 0.3:  # 最低相似度阈值
                            candidates.append((entity, similarity))
        
        return candidates
    
    def _create_entity(self, name: str, entity_type: str, context: str, 
                      description: str, confidence: float) -> EntityIdentity:
        """创建新实体"""
        entity_id = self._generate_entity_id(name, entity_type, context)
        
        attributes = EntityAttributes(
            name=name,
            entity_type=entity_type,
            description=description,
            context=[context] if context else [],
            confidence=confidence
        )
        
        entity = EntityIdentity(
            entity_id=entity_id,
            canonical_name=name,
            attributes=attributes
        )
        
        self.entities[entity_id] = entity
        self._index_entity(entity)
        self._save_entities()
        
        logger.info(f"创建新实体: {name} ({entity_type}) - ID: {entity_id}")
        return entity
    
    def _update_entity(self, entity: EntityIdentity, context: str, description: str, confidence: float):
        """更新实体信息"""
        # 更新属性
        if context and context not in entity.attributes.context:
            entity.attributes.context.append(context)
        
        if description and description != entity.attributes.description:
            entity.attributes.description = description
        
        entity.attributes.frequency += 1
        entity.attributes.last_seen = time.time()
        entity.attributes.confidence = max(entity.attributes.confidence, confidence)
        
        # 重建索引
        self.name_index[entity.canonical_name.lower()].add(entity.entity_id)
        
        self._save_entities()
        
        logger.debug(f"更新实体: {entity.canonical_name} - 频率: {entity.attributes.frequency}")
    
    def add_alias(self, entity_id: str, alias: str):
        """为实体添加别名"""
        if entity_id in self.entities:
            entity = self.entities[entity_id]
            if alias not in entity.attributes.aliases:
                entity.attributes.aliases.append(alias)
                self.alias_index[alias.lower()].add(entity_id)
                self._save_entities()
                logger.info(f"为实体 {entity.canonical_name} 添加别名: {alias}")
    
    def relate_entities(self, entity_id1: str, entity_id2: str):
        """建立实体关系"""
        if entity_id1 in self.entities and entity_id2 in self.entities:
            self.entities[entity_id1].related_entities.add(entity_id2)
            self.entities[entity_id2].related_entities.add(entity_id1)
            self._save_entities()
            logger.info(f"建立实体关系: {entity_id1} <-> {entity_id2}")
    
    def get_entity(self, entity_id: str) -> Optional[EntityIdentity]:
        """获取实体"""
        return self.entities.get(entity_id)
    
    def find_entities_by_name(self, name: str) -> List[EntityIdentity]:
        """通过名称查找实体"""
        name_lower = name.lower()
        entity_ids = self.name_index.get(name_lower, set())
        
        # 也检查别名
        if name_lower in self.alias_index:
            entity_ids.update(self.alias_index[name_lower])
        
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]
    
    def find_entities_by_context(self, context: str) -> List[EntityIdentity]:
        """通过上下文查找实体"""
        context_words = set(re.findall(r'\w+', context.lower()))
        entity_ids = set()
        
        for word in context_words:
            if len(word) > 2 and word in self.context_index:
                entity_ids.update(self.context_index[word])
        
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]
    
    def get_entity_statistics(self) -> Dict[str, Any]:
        """获取实体统计信息"""
        if not self.entities:
            return {"total_entities": 0}
        
        # 统计实体类型分布
        type_counts = Counter(entity.attributes.entity_type for entity in self.entities.values())
        
        # 统计别名使用情况
        alias_counts = [len(entity.attributes.aliases) for entity in self.entities.values()]
        
        # 统计频率分布
        frequencies = [entity.attributes.frequency for entity in self.entities.values()]
        
        # 统计置信度分布
        confidences = [entity.attributes.confidence for entity in self.entities.values()]
        
        return {
            "total_entities": len(self.entities),
            "type_distribution": dict(type_counts),
            "alias_stats": {
                "entities_with_aliases": sum(1 for count in alias_counts if count > 0),
                "average_aliases": sum(alias_counts) / len(alias_counts) if alias_counts else 0,
                "max_aliases": max(alias_counts) if alias_counts else 0
            },
            "frequency_stats": {
                "average_frequency": sum(frequencies) / len(frequencies) if frequencies else 0,
                "max_frequency": max(frequencies) if frequencies else 0,
                "high_frequency_entities": sum(1 for f in frequencies if f > 10)
            },
            "confidence_stats": {
                "average_confidence": sum(confidences) / len(confidences) if confidences else 0,
                "high_confidence_entities": sum(1 for c in confidences if c > 0.8)
            }
        }
    
    def cleanup_entities(self, min_frequency: int = 1, min_confidence: float = 0.3):
        """清理低质量实体"""
        entities_to_remove = []
        
        for entity_id, entity in self.entities.items():
            if (entity.attributes.frequency < min_frequency or 
                entity.attributes.confidence < min_confidence):
                entities_to_remove.append(entity_id)
        
        for entity_id in entities_to_remove:
            del self.entities[entity_id]
            # 从索引中移除
            entity = self.entities[entity_id]
            self.name_index[entity.canonical_name.lower()].discard(entity_id)
            for alias in entity.attributes.aliases:
                self.alias_index[alias.lower()].discard(entity_id)
        
        if entities_to_remove:
            self._save_entities()
            logger.info(f"清理了 {len(entities_to_remove)} 个低质量实体")
        
        return len(entities_to_remove)
    
    def export_entities(self, output_file: str = None) -> str:
        """导出实体数据"""
        if output_file is None:
            output_file = f"{self.storage_path}/entities_export_{int(time.time())}.json"
        
        data = {}
        for entity_id, entity in self.entities.items():
            data[entity_id] = {
                'canonical_name': entity.canonical_name,
                'attributes': asdict(entity.attributes),
                'related_entities': list(entity.related_entities)
            }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"导出实体数据到: {output_file}")
        return output_file


# 全局实体消歧器实例
entity_disambiguator = EntityDisambiguator()