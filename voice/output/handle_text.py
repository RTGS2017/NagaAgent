import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
import re
import emoji

def prepare_tts_input_with_context(text: str) -> str:
    """
    清洗Markdown文本并为部分元素添加上下文提示，适用于TTS输入，保留段落分隔。

    参数：
        text (str): 原始Markdown或其他格式的文本。

    返回：
        str: 适合TTS输入的清洗后文本。
    """

    # 移除所有表情符号
    text = emoji.replace_emoji(text, replace='')

    # 为标题添加上下文提示
    def header_replacer(match):
        level = len(match.group(1))  # 统计#数量，判断标题级别
        header_text = match.group(2).strip()
        if level == 1:
            return f"Title — {header_text}\n"  # 一级标题
        elif level == 2:
            return f"Section — {header_text}\n"  # 二级标题
        else:
            return f"Subsection — {header_text}\n"  # 三级及以下标题

    text = re.sub(r"^(#{1,6})\s+(.*)", header_replacer, text, flags=re.MULTILINE)

    # 链接提示（目前注释，后续可用）
    # text = re.sub(r"\[([^\]]+)\]\((https?:\/\/[^\)]+)\)", r"\1 (link: \2)", text)

    # 移除链接，仅保留文本
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 移除多行代码块并加描述
    text = re.sub(r"```([\s\S]+?)```", r"(code block omitted)", text)

    # 行内代码加描述
    text = re.sub(r"`([^`]+)`", r"code snippet: \1", text)

    # 移除粗体/斜体符号，保留内容
    text = re.sub(r"(\*\*|__|\*|_)", '', text)

    # 移除图片语法，保留alt文本
    text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"Image: \1", text)

    # 移除HTML标签
    text = re.sub(r"</?[^>]+(>|$)", '', text)

    # 规范段落换行
    text = re.sub(r"\n{2,}", '\n\n', text)  # 保证段落分隔一致

    # 行内多空格合并
    text = re.sub(r" {2,}", ' ', text)

    # 去除首尾空白
    text = text.strip()

    return text
