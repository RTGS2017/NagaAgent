import traceback
import json
import logging
import re
import sys
import os
import time
import asyncio
import uuid
from typing import List, Tuple, Dict, Any
from pydantic import BaseModel

# 添加项目根目录到路径，以便导入config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from system.config import config
from openai import OpenAI, AsyncOpenAI
from .json_utils import clean_and_parse_json

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
    timestamp: float = None
    session_id: str = None
    memory_type: str = "fact"  # fact, process, emotion, meta
    importance_score: float = 0.5


class QuintupleResponse(BaseModel):
    quintuples: List[Quintuple]


def create_enhanced_quintuple(subject: str, subject_type: str, predicate: str, 
                             object: str, object_type: str, 
                             memory_type: str = "fact", 
                             importance_score: float = 0.5,
                             session_id: str = None) -> Dict[str, Any]:
    """创建增强的五元组，包含时间戳和元数据"""
    current_time = time.time()
    if session_id is None:
        session_id = str(uuid.uuid4())
    
    return {
        "subject": subject,
        "subject_type": subject_type,
        "predicate": predicate,
        "object": object,
        "object_type": object_type,
        "timestamp": current_time,
        "session_id": session_id,
        "memory_type": memory_type,
        "importance_score": importance_score
    }


async def analyze_memory_importance_advanced(quintuple: Dict[str, Any], context: str = "", use_llm: bool = True):
    """使用高级分析器分析记忆重要程度"""
    from summer_memory.memory_importance_analyzer import memory_importance_analyzer
    
    return await memory_importance_analyzer.analyze_memory_importance(
        quintuple, context, use_llm
    )


def analyze_memory_importance(quintuple: Dict[str, Any], context: str = "") -> float:
    """分析记忆重要程度（简化版本）"""
    # 基础重要性分数
    base_score = 0.5
    
    # 根据实体类型调整重要性
    important_entities = {"人物", "组织", "事件"}
    if quintuple["subject_type"] in important_entities or quintuple["object_type"] in important_entities:
        base_score += 0.2
    
    # 根据关系类型调整重要性
    important_relations = {"是", "拥有", "完成", "开始", "结束", "创建", "发现"}
    if quintuple["predicate"] in important_relations:
        base_score += 0.2
    
    # 根据上下文长度调整重要性（更长的上下文可能包含更多信息）
    if len(context) > 100:
        base_score += 0.1
    
    # 确保分数在0-1之间
    return min(max(base_score, 0.0), 1.0)


async def extract_quintuples_async(text, session_id: str = None, context: str = "", use_advanced_analysis: bool = False):
    """异步版本的五元组提取"""
    # 首先尝试使用结构化输出
    basic_quintuples = await _extract_quintuples_async_structured(text)
    
    # 转换为增强五元组
    enhanced_quintuples = []
    for quintuple in basic_quintuples:
        subject, subject_type, predicate, object, object_type = quintuple
        
        # 创建临时五元组用于分析
        temp_quintuple = {
            "subject": subject,
            "subject_type": subject_type,
            "predicate": predicate,
            "object": object,
            "object_type": object_type
        }
        
        if use_advanced_analysis:
            # 使用高级重要性分析
            analysis_result = await analyze_memory_importance_advanced(temp_quintuple, context)
            importance_score = analysis_result["importance_score"]
            memory_type = analysis_result["memory_type"]
        else:
            # 使用基础重要性分析
            importance_score = analyze_memory_importance(temp_quintuple, context)
            memory_type = "fact"  # 默认为事实记忆
        
        # 创建增强五元组
        enhanced = create_enhanced_quintuple(
            subject, subject_type, predicate, object, object_type,
            memory_type=memory_type,
            importance_score=importance_score,
            session_id=session_id
        )
        
        # 如果使用了高级分析，添加分析结果
        if use_advanced_analysis:
            enhanced["analysis_result"] = analysis_result
        
        enhanced_quintuples.append(enhanced)
    
    return enhanced_quintuples


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
    max_retries = 1  # 减少重试次数，失败后立即回退

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
            # 立即回退到传统方法，不再重试
            break

    # 立即调用回退方法
    logger.info("结构化输出失败，立即回退到传统JSON解析方法")
    return await _extract_quintuples_async_fallback(text)


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
            
            # 使用统一的JSON清理和解析工具
            quintuples = clean_and_parse_json(content, expected_type=list, default=[])
            
            if quintuples:
                logger.info(f"传统方法成功，提取到 {len(quintuples)} 个五元组")
                return [tuple(t) for t in quintuples if len(t) == 5]
            else:
                logger.warning("传统方法JSON解析失败，尝试额外解析策略")
                # 尝试直接提取数组作为最后的策略
                if '[' in content and ']' in content:
                    try:
                        start = content.index('[')
                        end = content.rindex(']') + 1
                        array_content = content[start:end]
                        quintuples = json.loads(array_content)
                        if isinstance(quintuples, list):
                            logger.info(f"数组提取策略成功，提取到 {len(quintuples)} 个五元组")
                            return [tuple(t) for t in quintuples if len(t) == 5]
                    except:
                        pass

        except Exception as e:
            logger.error(f"传统方法提取失败: {str(e)}")
            if attempt < max_retries:
                await asyncio.sleep(1 + attempt)

    return []


def extract_quintuples(text, session_id: str = None, context: str = ""):
    """同步版本的五元组提取"""
    # 首先尝试使用结构化输出
    basic_quintuples = _extract_quintuples_structured(text)
    
    # 转换为增强五元组
    enhanced_quintuples = []
    for quintuple in basic_quintuples:
        subject, subject_type, predicate, object, object_type = quintuple
        
        # 分析记忆重要性
        temp_quintuple = {
            "subject": subject,
            "subject_type": subject_type,
            "predicate": predicate,
            "object": object,
            "object_type": object_type
        }
        importance_score = analyze_memory_importance(temp_quintuple, context)
        
        # 创建增强五元组
        enhanced = create_enhanced_quintuple(
            subject, subject_type, predicate, object, object_type,
            memory_type="fact",  # 默认为事实记忆
            importance_score=importance_score,
            session_id=session_id
        )
        enhanced_quintuples.append(enhanced)
    
    return enhanced_quintuples


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
    max_retries = 1  # 减少重试次数，失败后立即回退

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
            # 立即回退到传统方法，不再重试
            break

    # 立即调用回退方法
    logger.info("结构化输出失败，立即回退到传统JSON解析方法")
    return _extract_quintuples_fallback(text)


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
            
            # 使用统一的JSON清理和解析工具
            quintuples = clean_and_parse_json(content, expected_type=list, default=[])
            
            if quintuples:
                logger.info(f"传统方法成功，提取到 {len(quintuples)} 个五元组")
                return [tuple(t) for t in quintuples if len(t) == 5]
            else:
                logger.warning("传统方法JSON解析失败，尝试额外解析策略")
                # 尝试直接提取数组作为最后的策略
                if '[' in content and ']' in content:
                    try:
                        start = content.index('[')
                        end = content.rindex(']') + 1
                        array_content = content[start:end]
                        quintuples = json.loads(array_content)
                        if isinstance(quintuples, list):
                            logger.info(f"数组提取策略成功，提取到 {len(quintuples)} 个五元组")
                            return [tuple(t) for t in quintuples if len(t) == 5]
                    except:
                        pass

        except Exception as e:
            logger.error(f"传统方法提取失败: {str(e)}")
            if attempt < max_retries:
                time.sleep(1)

    return []