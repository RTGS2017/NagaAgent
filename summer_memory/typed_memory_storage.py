#!/usr/bin/env python3
"""
分类型存储系统
为不同类型的记忆提供专门的存储策略和查询接口
"""

import json
import os
import time
import logging
from typing import List, Dict, Any, Optional, Set
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict

# 添加项目根目录到路径
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型枚举"""
    FACT = "fact"           # 事实记忆：客观事实、知识
    PROCESS = "process"     # 过程记忆：行为、操作、流程
    EMOTION = "emotion"     # 情感记忆：情感、态度、偏好
    META = "meta"          # 元记忆：关于记忆的记忆、反思


class StoragePriority(Enum):
    """存储优先级枚举"""
    HIGH_PRIORITY = "high_priority"      # 高优先级：快速访问
    STANDARD = "standard"                # 标准：平衡性能
    COMPRESSED = "compressed"            # 压缩：节省空间
    TEMPORARY = "temporary"              # 临时：短期存储


@dataclass
class StorageConfig:
    """存储配置"""
    file_path: str
    max_size: int           # 最大存储数量
    retention_days: int    # 保留天数
    compression_enabled: bool
    priority: StoragePriority


class TypedMemoryStorage:
    """分类型存储管理器"""
    
    def __init__(self, base_path: str = "logs/knowledge_graph"):
        self.base_path = base_path
        self.storage_configs = self._init_storage_configs()
        self.memory_indices = defaultdict(dict)  # 记忆索引
        
        # 确保目录存在
        os.makedirs(base_path, exist_ok=True)
        
        # 初始化存储文件
        self._init_storage_files()
    
    def _init_storage_configs(self) -> Dict[MemoryType, StorageConfig]:
        """初始化各类型记忆的存储配置"""
        return {
            MemoryType.FACT: StorageConfig(
                file_path=f"{self.base_path}/fact_memories.json",
                max_size=10000,
                retention_days=365,    # 事实记忆保留1年
                compression_enabled=False,
                priority=StoragePriority.STANDARD
            ),
            MemoryType.PROCESS: StorageConfig(
                file_path=f"{self.base_path}/process_memories.json",
                max_size=5000,
                retention_days=90,     # 过程记忆保留3个月
                compression_enabled=True,
                priority=StoragePriority.COMPRESSED
            ),
            MemoryType.EMOTION: StorageConfig(
                file_path=f"{self.base_path}/emotion_memories.json",
                max_size=3000,
                retention_days=180,    # 情感记忆保留6个月
                compression_enabled=False,
                priority=StoragePriority.HIGH_PRIORITY
            ),
            MemoryType.META: StorageConfig(
                file_path=f"{self.base_path}/meta_memories.json",
                max_size=2000,
                retention_days=730,    # 元记忆保留2年
                compression_enabled=False,
                priority=StoragePriority.STANDARD
            )
        }
    
    def _init_storage_files(self):
        """初始化存储文件"""
        for memory_type, config in self.storage_configs.items():
            if not os.path.exists(config.file_path):
                with open(config.file_path, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False, indent=2)
    
    def _load_memories(self, memory_type: MemoryType) -> List[Dict[str, Any]]:
        """加载指定类型的记忆"""
        config = self.storage_configs[memory_type]
        try:
            with open(config.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def _save_memories(self, memory_type: MemoryType, memories: List[Dict[str, Any]]):
        """保存指定类型的记忆"""
        config = self.storage_configs[memory_type]
        
        # 应用保留策略
        memories = self._apply_retention_policy(memories, config.retention_days)
        
        # 应用大小限制
        if len(memories) > config.max_size:
            memories = self._apply_size_limit(memories, config.max_size)
        
        with open(config.file_path, 'w', encoding='utf-8') as f:
            json.dump(memories, f, ensure_ascii=False, indent=2)
    
    def _apply_retention_policy(self, memories: List[Dict[str, Any]], retention_days: int) -> List[Dict[str, Any]]:
        """应用保留策略"""
        if retention_days <= 0:
            return memories
        
        current_time = time.time()
        cutoff_time = current_time - (retention_days * 24 * 3600)
        
        return [m for m in memories if m.get("timestamp", current_time) >= cutoff_time]
    
    def _apply_size_limit(self, memories: List[Dict[str, Any]], max_size: int) -> List[Dict[str, Any]]:
        """应用大小限制"""
        if len(memories) <= max_size:
            return memories
        
        # 按重要性排序，保留最重要的记忆
        sorted_memories = sorted(memories, 
                               key=lambda x: x.get("importance_score", 0.5), 
                               reverse=True)
        
        return sorted_memories[:max_size]
    
    def store_memory(self, quintuple: Dict[str, Any]) -> bool:
        """存储记忆到对应的类型存储中"""
        try:
            memory_type_str = quintuple.get("memory_type", "fact")
            memory_type = MemoryType(memory_type_str)
            
            # 加载现有记忆
            memories = self._load_memories(memory_type)
            
            # 检查是否已存在相同记忆
            memory_key = self._get_memory_key(quintuple)
            if memory_key in self.memory_indices[memory_type]:
                # 更新现有记忆
                existing_index = self.memory_indices[memory_type][memory_key]
                memories[existing_index] = quintuple
            else:
                # 添加新记忆
                memories.append(quintuple)
                self.memory_indices[memory_type][memory_key] = len(memories) - 1
            
            # 保存记忆
            self._save_memories(memory_type, memories)
            
            logger.info(f"存储 {memory_type.value} 记忆: {quintuple['subject']} -{quintuple['predicate']}- {quintuple['object']}")
            return True
            
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            return False
    
    def _get_memory_key(self, quintuple: Dict[str, Any]) -> str:
        """获取记忆的唯一标识"""
        return f"{quintuple['subject']}|{quintuple['predicate']}|{quintuple['object']}"
    
    def get_memories_by_type(self, memory_type: MemoryType, 
                           limit: Optional[int] = None,
                           min_importance: float = 0.0) -> List[Dict[str, Any]]:
        """获取指定类型的记忆"""
        memories = self._load_memories(memory_type)
        
        # 过滤重要性
        filtered_memories = [m for m in memories if m.get("importance_score", 0.5) >= min_importance]
        
        # 按重要性排序
        sorted_memories = sorted(filtered_memories, 
                               key=lambda x: x.get("importance_score", 0.5), 
                               reverse=True)
        
        # 应用限制
        if limit:
            sorted_memories = sorted_memories[:limit]
        
        return sorted_memories
    
    def get_memories_by_types(self, memory_types: List[MemoryType], 
                            limit: Optional[int] = None,
                            min_importance: float = 0.0) -> List[Dict[str, Any]]:
        """获取多个类型的记忆"""
        all_memories = []
        for memory_type in memory_types:
            memories = self.get_memories_by_type(memory_type, min_importance=min_importance)
            all_memories.extend(memories)
        
        # 按重要性排序
        sorted_memories = sorted(all_memories, 
                               key=lambda x: x.get("importance_score", 0.5), 
                               reverse=True)
        
        # 应用限制
        if limit:
            sorted_memories = sorted_memories[:limit]
        
        return sorted_memories
    
    def search_memories(self, keywords: List[str], 
                       memory_types: Optional[List[MemoryType]] = None,
                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """搜索记忆"""
        if memory_types is None:
            memory_types = list(MemoryType)
        
        results = []
        for memory_type in memory_types:
            memories = self._load_memories(memory_type)
            
            for memory in memories:
                # 检查关键词匹配
                matched = False
                for keyword in keywords:
                    if (keyword in memory.get("subject", "") or
                        keyword in memory.get("predicate", "") or
                        keyword in memory.get("object", "") or
                        keyword in memory.get("subject_type", "") or
                        keyword in memory.get("object_type", "")):
                        matched = True
                        break
                
                if matched:
                    results.append(memory)
        
        # 按重要性排序
        sorted_results = sorted(results, 
                               key=lambda x: x.get("importance_score", 0.5), 
                               reverse=True)
        
        # 应用限制
        if limit:
            sorted_results = sorted_results[:limit]
        
        return sorted_results
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        stats = {
            "total_memories": 0,
            "by_type": {},
            "storage_usage": {},
            "retention_stats": {}
        }
        
        for memory_type in MemoryType:
            memories = self._load_memories(memory_type)
            config = self.storage_configs[memory_type]
            
            type_stats = {
                "count": len(memories),
                "avg_importance": sum(m.get("importance_score", 0.5) for m in memories) / len(memories) if memories else 0,
                "max_importance": max(m.get("importance_score", 0.5) for m in memories) if memories else 0,
                "min_importance": min(m.get("importance_score", 0.5) for m in memories) if memories else 0,
                "retention_days": config.retention_days,
                "max_size": config.max_size,
                "usage_ratio": len(memories) / config.max_size if config.max_size > 0 else 0
            }
            
            stats["by_type"][memory_type.value] = type_stats
            stats["total_memories"] += len(memories)
        
        return stats
    
    def cleanup_old_memories(self):
        """清理过期记忆"""
        cleaned_count = 0
        
        for memory_type in MemoryType:
            memories = self._load_memories(memory_type)
            config = self.storage_configs[memory_type]
            
            original_count = len(memories)
            cleaned_memories = self._apply_retention_policy(memories, config.retention_days)
            
            if len(cleaned_memories) < original_count:
                self._save_memories(memory_type, cleaned_memories)
                cleaned_count += original_count - len(cleaned_memories)
                
                logger.info(f"清理 {memory_type.value} 记忆: {original_count} -> {len(cleaned_memories)}")
        
        return cleaned_count
    
    def get_recent_memories(self, memory_type: MemoryType, hours: int = 24) -> List[Dict[str, Any]]:
        """获取最近的记忆"""
        memories = self._load_memories(memory_type)
        current_time = time.time()
        cutoff_time = current_time - (hours * 3600)
        
        recent_memories = [m for m in memories if m.get("timestamp", current_time) >= cutoff_time]
        
        # 按时间戳排序
        return sorted(recent_memories, key=lambda x: x.get("timestamp", 0), reverse=True)
    
    def get_memories_by_session(self, session_id: str, 
                               memory_types: Optional[List[MemoryType]] = None) -> List[Dict[str, Any]]:
        """获取指定会话的记忆"""
        if memory_types is None:
            memory_types = list(MemoryType)
        
        session_memories = []
        for memory_type in memory_types:
            memories = self._load_memories(memory_type)
            session_memories.extend([m for m in memories if m.get("session_id") == session_id])
        
        # 按时间戳排序
        return sorted(session_memories, key=lambda x: x.get("timestamp", 0), reverse=True)
    
    def export_memories(self, memory_types: Optional[List[MemoryType]] = None, 
                       output_file: str = None) -> str:
        """导出记忆"""
        if memory_types is None:
            memory_types = list(MemoryType)
        
        exported_data = {}
        for memory_type in memory_types:
            memories = self._load_memories(memory_type)
            exported_data[memory_type.value] = memories
        
        if output_file is None:
            output_file = f"{self.base_path}/exported_memories_{int(time.time())}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(exported_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"导出记忆到: {output_file}")
        return output_file
    
    def import_memories(self, import_file: str, merge_strategy: str = "merge") -> bool:
        """导入记忆"""
        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                imported_data = json.load(f)
            
            imported_count = 0
            for memory_type_str, memories in imported_data.items():
                try:
                    memory_type = MemoryType(memory_type_str)
                    existing_memories = self._load_memories(memory_type)
                    
                    if merge_strategy == "merge":
                        # 合并记忆，去重
                        existing_keys = set(self._get_memory_key(m) for m in existing_memories)
                        new_memories = [m for m in memories if self._get_memory_key(m) not in existing_keys]
                        existing_memories.extend(new_memories)
                    elif merge_strategy == "replace":
                        # 替换现有记忆
                        existing_memories = memories
                    else:
                        logger.warning(f"未知的合并策略: {merge_strategy}")
                        continue
                    
                    self._save_memories(memory_type, existing_memories)
                    imported_count += len(memories)
                    
                except ValueError:
                    logger.warning(f"未知的记忆类型: {memory_type_str}")
                    continue
            
            logger.info(f"导入记忆: {imported_count} 个")
            return True
            
        except Exception as e:
            logger.error(f"导入记忆失败: {e}")
            return False


# 全局分类型存储管理器实例
typed_memory_storage = TypedMemoryStorage()