"""非标准 JSON 解析，支持中文括号与标准 JSON"""

import re
import json
from typing import List, Dict, Any


def parse_non_standard_json(text: str) -> List[Dict[str, Any]]:
    tool_calls = []
    try:
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
    if not tool_calls:
        pattern = r'｛([^｝]*)｝'
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                json_str = "{" + match + "}"
                tool_call = {}
                lines = json_str.split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line and not line.startswith('{') and not line.startswith('}'):
                        if '"' in line:
                            key_match = re.search(r'"([^"]*)"\s*:\s*"([^"]*)"', line)
                            if key_match:
                                tool_call[key_match.group(1)] = key_match.group(2)
                        else:
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                key = parts[0].strip().strip('"')
                                value = parts[1].strip().strip('"')
                                tool_call[key] = value
                if validate_tool_call(tool_call):
                    tool_calls.append(tool_call)
            except Exception:
                continue
    return tool_calls


def validate_tool_call(tool_call: Dict[str, Any]) -> bool:
    if not isinstance(tool_call, dict):
        return False
    if tool_call.get("agentType") == "openclaw":
        return bool(tool_call.get("message") or tool_call.get("task_type"))
    return bool(tool_call.get("agentType"))


def extract_json_blocks(text: str) -> List[str]:
    json_blocks = []
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_blocks.extend(re.findall(json_pattern, text, re.DOTALL))
    chinese_pattern = r'｛[^｝]*｝'
    json_blocks.extend(re.findall(chinese_pattern, text, re.DOTALL))
    return json_blocks


def normalize_json_format(text: str) -> str:
    return text.replace('｛', '{').replace('｝', '}')

