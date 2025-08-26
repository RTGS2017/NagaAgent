#!/usr/bin/env python3
"""
时间轴管理系统
管理记忆的时间衰减、时间窗口查询等功能
"""

import time
import math
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TimeAxisManager:
    """时间轴管理器"""
    
    def __init__(self):
        self.time_decay_rate = 0.1  # 时间衰减率
        self.half_life = 30 * 24 * 3600  # 半衰期：30天（秒）
        
    def _get_timestamp_from_quintuple(self, quintuple: Dict[str, Any]) -> float:
        """从五元组中获取时间戳（支持新旧格式）"""
        # 优先使用 timestamp_raw（新格式）
        if "timestamp_raw" in quintuple:
            return quintuple["timestamp_raw"]
        # 如果 timestamp 是字符串（新格式），尝试解析
        elif isinstance(quintuple.get("timestamp"), str):
            try:
                # 尝试解析时间字符串
                time_str = quintuple["timestamp"]
                # 移除时区信息并解析
                if " " in time_str:
                    dt = datetime.strptime(time_str.split(" ")[0] + " " + time_str.split(" ")[1], "%Y-%m-%d %H:%M:%S")
                    return dt.timestamp()
            except:
                pass
        # 回退到当前时间
        return time.time()
    
    def calculate_time_decay_factor(self, timestamp: Union[float, str, Dict[str, Any]]) -> float:
        """计算时间衰减因子"""
        current_time = time.time()
        
        # 如果传入的是五元组字典
        if isinstance(timestamp, dict):
            timestamp = self._get_timestamp_from_quintuple(timestamp)
        # 如果是字符串，尝试解析
        elif isinstance(timestamp, str):
            try:
                dt = datetime.strptime(timestamp.split(" ")[0] + " " + timestamp.split(" ")[1], "%Y-%m-%d %H:%M:%S")
                timestamp = dt.timestamp()
            except:
                timestamp = current_time
        
        age = current_time - timestamp
        
        # 使用指数衰减公式
        decay_factor = math.exp(-age / self.half_life)
        return max(0.1, decay_factor)  # 最小衰减因子为0.1
    
    def apply_time_decay(self, quintuple: Dict[str, Any]) -> float:
        """应用时间衰减到五元组的重要性分数"""
        original_importance = quintuple.get("importance_score", 0.5)
        decay_factor = self.calculate_time_decay_factor(quintuple)
        
        # 计算衰减后的重要性分数
        decayed_importance = original_importance * decay_factor
        return decayed_importance
    
    def filter_by_time_window(self, quintuples: List[Dict[str, Any]], 
                            time_window: Optional[float] = None,
                            start_time: Optional[float] = None,
                            end_time: Optional[float] = None) -> List[Dict[str, Any]]:
        """根据时间窗口过滤五元组"""
        current_time = time.time()
        filtered_quintuples = []
        
        for quintuple in quintuples:
            # 使用新的时间戳获取方法
            quintuple_time = self._get_timestamp_from_quintuple(quintuple)
            
            # 时间窗口过滤（最近N秒）
            if time_window is not None:
                if current_time - quintuple_time > time_window:
                    continue
            
            # 开始时间过滤
            if start_time is not None:
                if quintuple_time < start_time:
                    continue
            
            # 结束时间过滤
            if end_time is not None:
                if quintuple_time > end_time:
                    continue
            
            filtered_quintuples.append(quintuple)
        
        return filtered_quintuples
    
    def get_quintuples_by_time_range(self, quintuples: List[Dict[str, Any]], 
                                   start_time: float, end_time: float) -> List[Dict[str, Any]]:
        """获取指定时间范围内的五元组"""
        return self.filter_by_time_window(quintuples, start_time=start_time, end_time=end_time)
    
    def get_recent_quintuples(self, quintuples: List[Dict[str, Any]], 
                            hours: int = 24) -> List[Dict[str, Any]]:
        """获取最近N小时内的五元组"""
        time_window = hours * 3600  # 转换为秒
        return self.filter_by_time_window(quintuples, time_window=time_window)
    
    def get_quintuples_by_date(self, quintuples: List[Dict[str, Any]], 
                              date: datetime) -> List[Dict[str, Any]]:
        """获取指定日期的五元组"""
        start_time = date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        end_time = (date + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        
        return self.filter_by_time_window(quintuples, start_time=start_time, end_time=end_time)
    
    def sort_by_time(self, quintuples: List[Dict[str, Any]], 
                    ascending: bool = False) -> List[Dict[str, Any]]:
        """按时间戳排序五元组"""
        return sorted(quintuples, key=self._get_timestamp_from_quintuple, reverse=not ascending)
    
    def get_memory_timeline(self, quintuples: List[Dict[str, Any]], 
                          time_window: Optional[float] = None) -> List[Dict[str, Any]]:
        """获取记忆时间线，包含时间衰减后的重要性分数"""
        filtered_quintuples = self.filter_by_time_window(quintuples, time_window)
        
        timeline = []
        for quintuple in filtered_quintuples:
            # 计算衰减后的重要性分数
            decayed_importance = self.apply_time_decay(quintuple)
            
            # 创建时间线条目
            timeline_entry = quintuple.copy()
            timeline_entry["decayed_importance"] = decayed_importance
            timeline_entry["age_hours"] = (time.time() - self._get_timestamp_from_quintuple(quintuple)) / 3600
            
            timeline.append(timeline_entry)
        
        # 按时间戳排序
        return self.sort_by_time(timeline, ascending=False)
    
    def analyze_temporal_patterns(self, quintuples: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析时间模式"""
        if not quintuples:
            return {}
        
        current_time = time.time()
        timestamps = [self._get_timestamp_from_quintuple(q) for q in quintuples]
        
        # 计算时间统计信息
        oldest_time = min(timestamps)
        newest_time = max(timestamps)
        time_span = newest_time - oldest_time
        
        # 计算时间分布
        time_buckets = {
            "last_hour": 0,
            "last_day": 0,
            "last_week": 0,
            "last_month": 0,
            "older": 0
        }
        
        for ts in timestamps:
            age = current_time - ts
            if age <= 3600:  # 1小时内
                time_buckets["last_hour"] += 1
            elif age <= 24 * 3600:  # 1天内
                time_buckets["last_day"] += 1
            elif age <= 7 * 24 * 3600:  # 1周内
                time_buckets["last_week"] += 1
            elif age <= 30 * 24 * 3600:  # 1月内
                time_buckets["last_month"] += 1
            else:
                time_buckets["older"] += 1
        
        return {
            "total_quintuples": len(quintuples),
            "time_span_hours": time_span / 3600,
            "oldest_timestamp": oldest_time,
            "newest_timestamp": newest_time,
            "time_distribution": time_buckets,
            "average_age_hours": sum(current_time - ts for ts in timestamps) / len(timestamps) / 3600
        }
    
    def format_timestamp(self, timestamp: float) -> str:
        """格式化时间戳为可读字符串"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def get_session_quintuples(self, quintuples: List[Dict[str, Any]], 
                             session_id: str) -> List[Dict[str, Any]]:
        """获取特定会话的五元组"""
        return [q for q in quintuples if q.get("session_id") == session_id]
    
    def merge_sessions(self, quintuples: List[Dict[str, Any]], 
                      session_ids: List[str]) -> List[Dict[str, Any]]:
        """合并多个会话的五元组"""
        result = []
        for session_id in session_ids:
            session_quintuples = self.get_session_quintuples(quintuples, session_id)
            result.extend(session_quintuples)
        return result


# 全局时间轴管理器实例
time_axis_manager = TimeAxisManager()