import json
from typing import Optional
from dataclasses import dataclass


@dataclass
class ExtractedResponse:
    """提取的响应结构，包含内容和可选的推理过程"""
    content: str
    reasoning_content: Optional[str] = None


def extract_message(response: str) -> str:
    """
    解析后端返回的json字符串，优先取data.content，其次message，否则原样返回
    支持递归解析嵌套JSON和多步数组，自动用\n分隔多条消息
    :param response: 后端返回的json字符串
    :return: message内容（若解析失败则原样返回）
    """
    result = extract_message_with_reasoning(response)
    return result.content


def extract_message_with_reasoning(response: str) -> ExtractedResponse:
    """
    解析后端返回的json字符串，同时提取 content 和 reasoning_content
    :param response: 后端返回的json字符串
    :return: ExtractedResponse 包含 content 和 reasoning_content
    """
    if not isinstance(response, str):
        return ExtractedResponse(content=str(response))

    # 先尝试直接解析
    try:
        data = json.loads(response)
        # 如果是数组，递归拼接所有消息
        if isinstance(data, list):
            contents = []
            reasonings = []
            for item in data:
                result = _recursive_extract_with_reasoning(item)
                if result.content:
                    contents.append(result.content)
                if result.reasoning_content:
                    reasonings.append(result.reasoning_content)
            return ExtractedResponse(
                content='\n'.join(contents),
                reasoning_content='\n'.join(reasonings) if reasonings else None
            )
        result = _recursive_extract_with_reasoning(data)
        # 如果解析出了内容或推理内容，返回结果
        if result.content or result.reasoning_content:
            return result
    except:
        pass

    # 如果失败，尝试查找JSON子串
    try:
        # 查找可能的JSON起始位置
        start_pos = response.find('{')
        if start_pos >= 0:
            # 从第一个{开始尝试解析
            json_part = response[start_pos:]
            data = json.loads(json_part)
            if isinstance(data, list):
                contents = []
                reasonings = []
                for item in data:
                    result = _recursive_extract_with_reasoning(item)
                    if result.content:
                        contents.append(result.content)
                    if result.reasoning_content:
                        reasonings.append(result.reasoning_content)
                return ExtractedResponse(
                    content='\n'.join(contents),
                    reasoning_content='\n'.join(reasonings) if reasonings else None
                )
            result = _recursive_extract_with_reasoning(data)
            # 如果解析出了内容或推理内容，返回结果
            if result.content or result.reasoning_content:
                return result
    except:
        pass

    return ExtractedResponse(content=response)


def _recursive_extract_with_reasoning(data) -> ExtractedResponse:
    """递归提取消息内容和推理内容"""
    if isinstance(data, dict):
        content = None
        reasoning_content = None

        # 检查是否是新的流式格式 {"type": "content"|"reasoning", "text": "..."}
        if "type" in data and "text" in data:
            chunk_type = data.get("type")
            text = data.get("text", "")
            if chunk_type == "reasoning":
                return ExtractedResponse(content="", reasoning_content=text)
            else:
                return ExtractedResponse(content=text)

        # 提取 reasoning_content（如果存在）
        if "reasoning_content" in data:
            reasoning_content = data["reasoning_content"]
            if isinstance(reasoning_content, str):
                reasoning_content = reasoning_content.strip()

        # 优先级：data.content > message > content > text > value > response
        for key in ['data', 'message', 'content', 'text', 'value', 'response']:
            if key in data:
                value = data[key]
                if isinstance(value, dict):
                    # 递归处理嵌套字典
                    nested_result = _recursive_extract_with_reasoning(value)
                    if nested_result.content:
                        return ExtractedResponse(
                            content=nested_result.content,
                            reasoning_content=reasoning_content or nested_result.reasoning_content
                        )
                elif isinstance(value, str) and value.strip():
                    # 检查是否还是JSON格式
                    try:
                        nested_data = json.loads(value)
                        nested_result = _recursive_extract_with_reasoning(nested_data)
                        if nested_result.content:
                            return ExtractedResponse(
                                content=nested_result.content,
                                reasoning_content=reasoning_content or nested_result.reasoning_content
                            )
                    except:
                        pass
                    content = value.strip()
                    break
                elif value is not None:
                    content = str(value).strip()
                    break

        # 如果没有找到标准字段，返回第一个字符串值
        if not content:
            for value in data.values():
                if isinstance(value, str) and value.strip():
                    content = value.strip()
                    break

        return ExtractedResponse(content=content or "", reasoning_content=reasoning_content)
    elif isinstance(data, str):
        return ExtractedResponse(content=data.strip())

    return ExtractedResponse(content="")


def _recursive_extract(data) -> str:
    """递归提取消息内容（保持向后兼容）"""
    result = _recursive_extract_with_reasoning(data)
    return result.content
