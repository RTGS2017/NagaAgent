"""
JSON内容清理工具 - 提升记忆系统的健壮性
"""

import json
import re
import logging
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)

def clean_json_content(content: str) -> str:
    """清理JSON内容，去除代码框标记和其他干扰
    
    Args:
        content: 原始内容字符串
        
    Returns:
        清理后的JSON字符串
    """
    if not content or not isinstance(content, str):
        return content
    
    # 去除代码框标记
    content = re.sub(r'```json\s*', '', content)
    content = re.sub(r'```\s*', '', content)
    content = re.sub(r'```\s*$', '', content)
    
    # 去除其他可能的标记
    content = re.sub(r'^```.*?\n', '', content, flags=re.MULTILINE)
    content = re.sub(r'\n```.*?$', '', content, flags=re.MULTILINE)
    
    # 去除markdown标题和列表标记
    content = re.sub(r'^#+\s*', '', content, flags=re.MULTILINE)
    content = re.sub(r'^[\*\-\+]\s*', '', content, flags=re.MULTILINE)
    
    # 去除前后空白
    content = content.strip()
    
    return content

def safe_json_loads(content: str, expected_type: type = None) -> Any:
    """安全地解析JSON内容
    
    Args:
        content: 要解析的内容
        expected_type: 期望的数据类型（可选）
        
    Returns:
        解析后的数据，如果失败则返回None
    """
    if not content or not isinstance(content, str):
        return None
    
    original_content = content
    cleaned_content = clean_json_content(content)
    
    try:
        data = json.loads(cleaned_content)
        
        # 验证数据类型
        if expected_type and not isinstance(data, expected_type):
            logger.warning(f"JSON解析成功但类型不匹配: 期望 {expected_type}, 实际 {type(data)}")
            return None
            
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        logger.error(f"原始内容: {original_content[:200]}")
        logger.error(f"清理后内容: {cleaned_content[:200]}")
        
        # 尝试额外的清理策略
        return try_extra_parsing_strategies(original_content, expected_type)
    
    except Exception as e:
        logger.error(f"JSON解析异常: {e}")
        return None

def try_extra_parsing_strategies(content: str, expected_type: type = None) -> Any:
    """尝试额外的解析策略"""
    
    # 策略1: 提取第一个JSON对象
    try:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            if expected_type is None or isinstance(data, expected_type):
                return data
    except:
        pass
    
    # 策略2: 提取第一个JSON数组
    try:
        array_match = re.search(r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]', content)
        if array_match:
            data = json.loads(array_match.group())
            if expected_type is None or isinstance(data, expected_type):
                return data
    except:
        pass
    
    # 策略3: 尝试修复常见的JSON格式问题
    try:
        # 替换单引号为双引号
        fixed_content = content.replace("'", '"')
        # 修复尾随逗号
        fixed_content = re.sub(r',(\s*[}\]])', r'\1', fixed_content)
        
        data = json.loads(fixed_content)
        if expected_type is None or isinstance(data, expected_type):
            return data
    except:
        pass
    
    return None

def clean_and_parse_json(content: str, expected_type: type = None, default: Any = None) -> Any:
    """清理并解析JSON内容的统一接口
    
    Args:
        content: 原始内容
        expected_type: 期望的数据类型
        default: 解析失败时的默认值
        
    Returns:
        解析后的数据或默认值
    """
    result = safe_json_loads(content, expected_type)
    return result if result is not None else default