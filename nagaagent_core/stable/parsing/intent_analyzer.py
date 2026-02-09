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
            
            # 分类工具调用
            mcp_calls = []
            agent_calls = []
            
            for tool_call in tool_calls:
                if tool_call.get("agentType") == "mcp":
                    mcp_calls.append(tool_call)
                elif tool_call.get("agentType") == "agent":
                    agent_calls.append(tool_call)
            
            return {
                "has_tasks": len(tool_calls) > 0,
                "tool_calls": tool_calls,
                "mcp_calls": mcp_calls,
                "agent_calls": agent_calls,
                "total_count": len(tool_calls)
            }
            
        except Exception as e:
            return {
                "has_tasks": False,
                "error": str(e),
                "tool_calls": [],
                "mcp_calls": [],
                "agent_calls": [],
                "total_count": 0
            }
    
    def extract_mcp_tools(self, conversation: str) -> List[Dict[str, Any]]:
        """提取MCP工具调用
        
        Args:
            conversation: 对话内容
            
        Returns:
            MCP工具调用列表
        """
        analysis = self.analyze_conversation(conversation)
        return analysis.get("mcp_calls", [])
    
    def extract_agent_tasks(self, conversation: str) -> List[Dict[str, Any]]:
        """提取Agent任务调用
        
        Args:
            conversation: 对话内容
            
        Returns:
            Agent任务调用列表
        """
        analysis = self.analyze_conversation(conversation)
        return analysis.get("agent_calls", [])
    
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
            "mcp_count": 0,
            "agent_count": 0,
            "services": set(),
            "tools": set()
        }
        
        for tool_call in tool_calls:
            agent_type = tool_call.get("agentType", "")
            service_name = tool_call.get("service_name", "")
            tool_name = tool_call.get("tool_name", "")
            
            if agent_type == "mcp":
                summary["mcp_count"] += 1
            elif agent_type == "agent":
                summary["agent_count"] += 1
            
            if service_name:
                summary["services"].add(service_name)
            if tool_name:
                summary["tools"].add(tool_name)
        
        # 转换set为list以便JSON序列化
        summary["services"] = list(summary["services"])
        summary["tools"] = list(summary["tools"])
        
        return summary
