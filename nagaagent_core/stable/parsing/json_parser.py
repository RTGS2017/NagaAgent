"""JSON格式解析器

提供稳定的非标准JSON格式解析功能，支持中文括号和标准JSON格式
"""

import re
import json
from typing import List, Dict, Any


def parse_non_standard_json(text: str) -> List[Dict[str, Any]]:
    """解析非标准JSON格式 - 处理中文括号和标准JSON
    
    Args:
        text: 包含JSON格式的文本
        
    Returns:
        解析出的工具调用列表
    """
    tool_calls = []
    
    # 方法1：尝试解析标准JSON格式
    try:
        # 查找标准JSON块
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        json_matches = re.findall(json_pattern, text, re.DOTALL)
        
        for json_str in json_matches:
            try:
                tool_call = json.loads(json_str)
                if validate_tool_call(tool_call):
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    
    # 方法2：如果标准JSON解析失败，尝试中文括号格式
    if not tool_calls:
        # 查找所有非标准JSON块（使用中文括号）
        pattern = r'｛([^｝]*)｝'
        matches = re.findall(pattern, text, re.DOTALL)
        
        for match in matches:
            try:
                # 将中文括号替换为标准JSON格式
                json_str = "{" + match + "}"
                
                # 解析为字典
                tool_call = {}
                lines = json_str.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if ':' in line and not line.startswith('{') and not line.startswith('}'):
                        # 提取键值对
                        if '"' in line:
                            # 处理带引号的键值对
                            key_match = re.search(r'"([^"]*)"\s*:\s*"([^"]*)"', line)
                            if key_match:
                                key = key_match.group(1)
                                value = key_match.group(2)
                                tool_call[key] = value
                        else:
                            # 处理简单键值对
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                key = parts[0].strip().strip('"')
                                value = parts[1].strip().strip('"')
                                tool_call[key] = value
                
                # 验证必要的字段
                if validate_tool_call(tool_call):
                    tool_calls.append(tool_call)
                    
            except Exception:
                continue
    
    return tool_calls


def validate_tool_call(tool_call: Dict[str, Any]) -> bool:
    """验证工具调用是否包含必要字段
    
    Args:
        tool_call: 工具调用字典
        
    Returns:
        验证通过返回True，否则返回False
    """
    if not isinstance(tool_call, dict):
        return False
    
    # 检查必要字段 - 只需要 agentType 和 message
    if tool_call.get("agentType") == "openclaw":
        return bool(tool_call.get("message") or tool_call.get("task_type"))
    return bool(tool_call.get("agentType"))


def extract_json_blocks(text: str) -> List[str]:
    """从文本中提取所有JSON块
    
    Args:
        text: 输入文本
        
    Returns:
        JSON块字符串列表
    """
    json_blocks = []
    
    # 标准JSON块
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, text, re.DOTALL)
    json_blocks.extend(json_matches)
    
    # 中文括号JSON块
    chinese_pattern = r'｛[^｝]*｝'
    chinese_matches = re.findall(chinese_pattern, text, re.DOTALL)
    json_blocks.extend(chinese_matches)
    
    return json_blocks


def normalize_json_format(text: str) -> str:
    """将中文括号格式的JSON转换为标准格式
    
    Args:
        text: 包含中文括号的文本
        
    Returns:
        转换后的标准JSON格式文本
    """
    # 替换中文括号为标准括号
    normalized = text.replace('｛', '{').replace('｝', '}')
    return normalized
