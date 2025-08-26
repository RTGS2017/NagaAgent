import traceback
import json
import logging
import re
import sys
import os
import time
import asyncio
from typing import List, Tuple
from pydantic import BaseModel

# 添加项目根目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from system.config import config
from openai import OpenAI, AsyncOpenAI

# 初始化OpenAI客户端
client = OpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

async_client = AsyncOpenAI(
    api_key=config.api.api_key,
    base_url=config.api.base_url
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# 定义五元组的Pydantic模型
class Quintuple(BaseModel):
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: str


class QuintupleResponse(BaseModel):
    quintuples: List[Quintuple]


async def extract_quintuples_async(text):
    """异步版本的五元组提取"""
    # 首先尝试使用结构化输出
    return await _extract_quintuples_async_structured(text)


async def _extract_quintuples_async_structured(text):
    """使用结构化输出的异步五元组提取"""
    system_prompt = """
你是一个专业的中文文本信息抽取专家。你的任务是从给定的中文文本中抽取五元组关系。
五元组格式为：(主体, 主体类型, 动作, 客体, 客体类型)。

类型包括但不限于：人物、地点、组织、物品、概念、时间、事件、活动等。

例如：
输入：小明在公园里踢足球。
应该提取出：
- 主体：小明，类型：人物，动作：踢，客体：足球，类型：物品
- 主体：小明，类型：人物，动作：在，客体：公园，类型：地点

请仔细分析文本，提取所有可以识别出的五元组关系。
"""

    # 重试机制配置
    max_retries = 3

    for attempt in range(max_retries + 1):
        logger.info(f"尝试使用结构化输出提取五元组 (第{attempt + 1}次)")

        try:
            # 尝试使用结构化输出
            completion = await async_client.beta.chat.completions.parse(
                model=config.api.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请从以下文本中提取五元组：\n\n{text}"}
                ],
                response_format=QuintupleResponse,
                max_tokens=config.api.max_tokens,
                temperature=0.3,
                timeout=600 + (attempt * 20)
            )

            # 解析结果
            result = completion.choices[0].message.parsed
            quintuples = []
            
            for q in result.quintuples:
                quintuples.append((
                    q.subject, q.subject_type, 
                    q.predicate, q.object, q.object_type
                ))
            
            logger.info(f"结构化输出成功，提取到 {len(quintuples)} 个五元组")
            return quintuples

        except Exception as e:
            logger.warning(f"结构化输出失败: {str(e)}")
            logger.info("结构化输出失败，立即回退到传统JSON解析方法")
            return await _extract_quintuples_async_fallback(text)

    return []


async def _extract_quintuples_async_fallback(text):
    """传统JSON解析的异步五元组提取（回退方案）"""
    prompt = f"""
从以下中文文本中抽取五元组（主语-主语类型-谓语-宾语-宾语类型）关系，以 JSON 数组格式返回。

类型包括但不限于：人物、地点、组织、物品、概念、时间、事件、活动等。

例如：
输入：小明在公园里踢足球。
输出：[["小明", "人物", "踢", "足球", "物品"], ["小明", "人物", "在", "公园", "地点"]]

请从文本中提取所有可以识别出的五元组：
{text}

除了JSON数据，请不要输出任何其他数据，例如：```、```json、以下是我提取的数据：。
"""

    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            response = await async_client.chat.completions.create(
                model=config.api.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=config.api.max_tokens,
                temperature=0.3,
                timeout=600 + (attempt * 20)
            )
            
            content = response.choices[0].message.content.strip()
            
            # 尝试解析JSON
            try:
                quintuples = json.loads(content)
                logger.info(f"传统方法成功，提取到 {len(quintuples)} 个五元组")
                return [tuple(t) for t in quintuples if len(t) == 5]
            except json.JSONDecodeError:
                logger.error(f"JSON解析失败，原始内容: {content[:200]}")
                # 尝试直接提取数组
                if '[' in content and ']' in content:
                    start = content.index('[')
                    end = content.rindex(']') + 1
                    quintuples = json.loads(content[start:end])
                    return [tuple(t) for t in quintuples if len(t) == 5]
                raise

        except Exception as e:
            logger.error(f"传统方法提取失败: {str(e)}")
            if attempt < max_retries:
                await asyncio.sleep(1 + attempt)

    return []


def extract_quintuples(text):
    """同步版本的五元组提取"""
    # 首先尝试使用结构化输出
    return _extract_quintuples_structured(text)


def _extract_quintuples_structured(text):
    """使用结构化输出的同步五元组提取"""
    system_prompt = """
你是一个专业的中文文本信息抽取专家。你的任务是从给定的中文文本中抽取五元组关系。
五元组格式为：(主体, 主体类型, 动作, 客体, 客体类型)。

类型包括但不限于：人物、地点、组织、物品、概念、时间、事件、活动等。

例如：
输入：小明在公园里踢足球。
应该提取出：
- 主体：小明，类型：人物，动作：踢，客体：足球，类型：物品
- 主体：小明，类型：人物，动作：在，客体：公园，类型：地点

请仔细分析文本，提取所有可以识别出的五元组关系。
"""

    # 重试机制配置
    max_retries = 3

    for attempt in range(max_retries + 1):
        logger.info(f"尝试使用结构化输出提取五元组 (第{attempt + 1}次)")

        try:
            # 尝试使用结构化输出
            completion = client.beta.chat.completions.parse(
                model=config.api.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请从以下文本中提取五元组：\n\n{text}"}
                ],
                response_format=QuintupleResponse,
                max_tokens=config.api.max_tokens,
                temperature=0.3,
                timeout=600 + (attempt * 20)
            )

            # 解析结果
            result = completion.choices[0].message.parsed
            quintuples = []
            
            for q in result.quintuples:
                quintuples.append((
                    q.subject, q.subject_type, 
                    q.predicate, q.object, q.object_type
                ))
            
            logger.info(f"结构化输出成功，提取到 {len(quintuples)} 个五元组")
            return quintuples

        except Exception as e:
            logger.warning(f"结构化输出失败: {str(e)}")
            logger.info("结构化输出失败，立即回退到传统JSON解析方法")
            return _extract_quintuples_fallback(text)

    return []


def _extract_quintuples_fallback(text):
    """传统JSON解析的同步五元组提取（回退方案）"""
    prompt = f"""
从以下中文文本中抽取五元组（主语-主语类型-谓语-宾语-宾语类型）关系，以 JSON 数组格式返回。

类型包括但不限于：人物、地点、组织、物品、概念、时间、事件、活动等。

例如：
输入：小明在公园里踢足球。
输出：[["小明", "人物", "踢", "足球", "物品"], ["小明", "人物", "在", "公园", "地点"]]

请从文本中提取所有可以识别出的五元组：
{text}

除了JSON数据，请不要输出任何其他数据，例如：```、```json、以下是我提取的数据：。
"""

    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=config.api.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=config.api.max_tokens,
                temperature=0.5,
                timeout=600 + (attempt * 20)
            )

            content = response.choices[0].message.content.strip()
            
            # 尝试解析JSON
            try:
                quintuples = json.loads(content)
                logger.info(f"传统方法成功，提取到 {len(quintuples)} 个五元组")
                return [tuple(t) for t in quintuples if len(t) == 5]
            except json.JSONDecodeError:
                logger.error(f"JSON解析失败，原始内容: {content[:200]}")
                # 尝试直接提取数组
                if '[' in content and ']' in content:
                    start = content.index('[')
                    end = content.rindex(']') + 1
                    quintuples = json.loads(content[start:end])
                    return [tuple(t) for t in quintuples if len(t) == 5]
                raise

        except Exception as e:
            logger.error(f"传统方法提取失败: {str(e)}")
            if attempt < max_retries:
                time.sleep(1)

    return []