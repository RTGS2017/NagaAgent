"""
MCP工具调用接口
提供与LLM交互的工具函数
"""

import logging
from typing import Any, Dict, List

try:
    from .comic_service import download_comic, search_comic_by_name, search_comic_by_author, get_comic_detail
except ImportError:
    from comic_service import download_comic, search_comic_by_name, search_comic_by_author, get_comic_detail

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 工具函数映射
TOOLS = {
    '下载漫画': {
        'name': '下载漫画',
        'description': '下载指定ID的漫画到桌面',
        'parameters': {
            'type': 'object',
            'properties': {
                'album_id': {
                    'type': 'string',
                    'description': '漫画的ID号'
                }
            },
            'required': ['album_id']
        }
    },
    '搜索漫画': {
        'name': '搜索漫画',
        'description': '按漫画名称搜索漫画，返回搜索结果列表',
        'parameters': {
            'type': 'object',
            'properties': {
                'comic_name': {
                    'type': 'string',
                    'description': '要搜索的漫画名称'
                },
                'page': {
                    'type': 'integer',
                    'description': '页码，默认为1',
                    'default': 1
                }
            },
            'required': ['comic_name']
        }
    },
    '搜索作者': {
        'name': '搜索作者',
        'description': '按作者名称搜索漫画，返回该作者的所有作品',
        'parameters': {
            'type': 'object',
            'properties': {
                'author_name': {
                    'type': 'string',
                    'description': '要搜索的作者名称'
                },
                'page': {
                    'type': 'integer',
                    'description': '页码，默认为1',
                    'default': 1
                }
            },
            'required': ['author_name']
        }
    },
    '获取漫画详情': {
        'name': '获取漫画详情',
        'description': '根据漫画ID获取详细的漫画信息',
        'parameters': {
            'type': 'object',
            'properties': {
                'comic_id': {
                    'type': 'string',
                    'description': '漫画的ID号'
                }
            },
            'required': ['comic_id']
        }
    }
}

def get_tools() -> List[Dict[str, Any]]:
    """
    获取所有可用工具
    
    Returns:
        工具列表
    """
    return list(TOOLS.values())

def call_tool(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    调用工具
    
    Args:
        tool_name: 工具名称
        parameters: 工具参数
        
    Returns:
        工具执行结果
    """
    try:
        if tool_name == '下载漫画':
            return download_comic(parameters['album_id'])
        elif tool_name == '搜索漫画':
            page = parameters.get('page', 1)
            return search_comic_by_name(parameters['comic_name'], page)
        elif tool_name == '搜索作者':
            page = parameters.get('page', 1)
            return search_comic_by_author(parameters['author_name'], page)
        elif tool_name == '获取漫画详情':
            return get_comic_detail(parameters['comic_id'])
        else:
            return {
                'error': f'未知工具: {tool_name}',
                'message': f'工具 {tool_name} 不存在'
            }
    except Exception as e:
        logger.error(f"调用工具 {tool_name} 时发生错误: {e}")
        return {
            'error': str(e),
            'message': f'工具调用失败: {str(e)}'
        } 