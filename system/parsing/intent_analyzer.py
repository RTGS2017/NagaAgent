"""意图分析：从对话中识别工具调用意图"""

from typing import List, Dict, Any
from .json_parser import parse_non_standard_json, validate_tool_call


class IntentAnalyzer:
    def __init__(self):
        pass

    def analyze_conversation(self, conversation: str) -> Dict[str, Any]:
        try:
            tool_calls = parse_non_standard_json(conversation)
            openclaw_calls = [tc for tc in tool_calls if tc.get("agentType") == "openclaw"]
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
        return self.analyze_conversation(conversation).get("openclaw_calls", [])

    def validate_tool_call_format(self, tool_call: Dict[str, Any]) -> bool:
        return validate_tool_call(tool_call)

    def get_tool_call_summary(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {"total": len(tool_calls), "openclaw_count": 0, "task_types": set()}
        for tool_call in tool_calls:
            if tool_call.get("agentType") == "openclaw":
                summary["openclaw_count"] += 1
            if tool_call.get("task_type"):
                summary["task_types"].add(tool_call["task_type"])
        summary["task_types"] = list(summary["task_types"])
        return summary
