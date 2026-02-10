"""意图分析器

提供稳定的意图识别和分析功能
"""

from typing import List, Dict, Any
from .json_parser import parse_non_standard_json, validate_tool_call


class IntentAnalyzer:
    """意图分析器 - 分析对话中的工具调用意图"""
    
    def __init__(self):
        """初始化意图分析器"""
        pass
    
    def analyze_conversation(self, conversation: str) -> Dict[str, Any]:
        """分析对话内容，提取工具调用意图

        Args:
            conversation: 对话内容

        Returns:
            分析结果字典，包含工具调用列表
        """
        try:
            # 解析非标准JSON格式
            tool_calls = parse_non_standard_json(conversation)

            # 所有调用统一为openclaw
            openclaw_calls = []

            for tool_call in tool_calls:
                if tool_call.get("agentType") == "openclaw":
                    openclaw_calls.append(tool_call)

            return {
                "has_tasks": len(openclaw_calls) > 0,
                "tool_calls": openclaw_calls,
                "openclaw_calls": openclaw_calls,
                "total_count": len(openclaw_calls)
            }

        except Exception as e:
            return {
                "has_tasks": False,
                "error": str(e),
                "tool_calls": [],
                "openclaw_calls": [],
                "total_count": 0
            }
    
    def extract_openclaw_tasks(self, conversation: str) -> List[Dict[str, Any]]:
        """提取OpenClaw任务调用

        Args:
            conversation: 对话内容

        Returns:
            OpenClaw任务调用列表
        """
        analysis = self.analyze_conversation(conversation)
        return analysis.get("openclaw_calls", [])
    
    def validate_tool_call_format(self, tool_call: Dict[str, Any]) -> bool:
        """验证工具调用格式是否正确
        
        Args:
            tool_call: 工具调用字典
            
        Returns:
            格式正确返回True，否则返回False
        """
        return validate_tool_call(tool_call)
    
    def get_tool_call_summary(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """获取工具调用摘要信息

        Args:
            tool_calls: 工具调用列表

        Returns:
            摘要信息字典
        """
        summary = {
            "total": len(tool_calls),
            "openclaw_count": 0,
            "task_types": set(),
        }

        for tool_call in tool_calls:
            if tool_call.get("agentType") == "openclaw":
                summary["openclaw_count"] += 1
            task_type = tool_call.get("task_type", "")
            if task_type:
                summary["task_types"].add(task_type)

        summary["task_types"] = list(summary["task_types"])

        return summary
