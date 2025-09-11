"""
漫画服务核心模块
统一管理下载和搜索功能
"""

import logging
from typing import Dict, Any, List
from pathlib import Path

# 导入JMComic相关模块
try:
    from .jmcomic import download_album, create_option_by_str
    from .jmcomic.jm_config import JmModuleConfig, JmMagicConstants
    from .jmcomic.jm_option import JmOption
    from .jmcomic.jm_downloader import JmDownloader
    from .jmcomic.jm_entity import JmAlbumDetail, JmSearchPage
    from .jmcomic.jm_exception import JmcomicException
except ImportError:
    try:
        from jmcomic import download_album, create_option_by_str
        from jmcomic.jm_config import JmModuleConfig, JmMagicConstants
        from jmcomic.jm_option import JmOption
        from jmcomic.jm_downloader import JmDownloader
        from jmcomic.jm_entity import JmAlbumDetail, JmSearchPage
        from jmcomic.jm_exception import JmcomicException
    except ImportError as e:
        logging.error(f"Failed to import jmcomic modules: {e}")
        raise


class ComicService:
    """漫画服务核心类 - 统一管理下载和搜索功能"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._client = None  # 缓存客户端实例
    
    def get_desktop_path(self) -> str:
        """获取桌面路径"""
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                return str(desktop)
            return str(Path.cwd())
        except Exception as e:
            self.logger.warning(f"Failed to get desktop path: {e}")
            return str(Path.cwd())
    
    def get_client(self):
        """获取客户端实例，使用缓存"""
        if self._client is None:
            option = self.create_simple_option()
            self._client = option.build_jm_client()
        return self._client
    
    def create_simple_option(self) -> JmOption:
        """创建简化的配置选项"""
        desktop_path = self.get_desktop_path()
        
        option_dict = {
            'version': '2.1',
            'log': True,
            'dir_rule': {
                'rule': 'Bd_Pname',  # 使用本子名称作为文件夹名
                'base_dir': desktop_path,  # 保存到桌面
            },
            'download': {
                'cache': True,
                'image': {
                    'decode': True,
                    'suffix': None,  # 保持原始格式
                },
                'threading': {
                    'image': 10,  # 图片下载线程数
                    'photo': 3,   # 章节下载线程数
                },
            },
            'client': {
                'cache': None,
                'domain': [],
                'postman': {
                    'type': 'curl_cffi',
                    'meta_data': {
                        'impersonate': 'chrome',
                        'headers': None,
                        'proxies': None,
                    }
                },
                'impl': 'api',  # 使用API客户端
                'retry_times': 3,
            },
            'plugins': {
                'valid': 'log',
            },
        }
        
        return JmOption.construct(option_dict)
    
    # ==================== 下载功能 ====================
    
    def download_comic(self, album_id: str) -> Dict[str, Any]:
        """
        下载漫画
        
        Args:
            album_id: 漫画ID
            
        Returns:
            下载结果字典
        """
        try:
            self.logger.info(f"开始下载漫画: {album_id}")
            
            # 创建下载配置
            option = self.create_simple_option()
            
            # 开始下载
            album, downloader_result = download_album(
                album_id, 
                option=option, 
                downloader=JmDownloader,
                check_exception=True
            )
            
            # 获取下载结果
            result = {
                'success': True,
                'album_id': album_id,
                'album_title': album.title if album else None,
                'album_author': album.author if album else None,
                'download_path': option.decide_image_save_dir(album[0]) if album and len(album) > 0 else None,
                'message': f"漫画 {album_id} 下载完成"
            }
            
            self.logger.info(f"漫画 {album_id} 下载成功")
            return result
            
        except JmcomicException as e:
            error_msg = f"下载漫画 {album_id} 失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'album_id': album_id,
                'error': str(e),
                'message': error_msg
            }
        except Exception as e:
            error_msg = f"下载漫画 {album_id} 时发生未知错误: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'album_id': album_id,
                'error': str(e),
                'message': error_msg
            }
    
    # ==================== 搜索功能 ====================
    
    def search_comic_by_name(self, comic_name: str, page: int = 1) -> Dict[str, Any]:
        """
        按漫画名搜索
        
        Args:
            comic_name: 漫画名称
            page: 页码，默认第1页
            
        Returns:
            搜索结果字典
        """
        try:
            client = self.get_client()
            
            # 使用站内搜索，main_tag=0表示全部搜索
            search_page = client.search(
                search_query=comic_name,
                page=page,
                main_tag=0,  # 0=全部搜索
                order_by=JmMagicConstants.ORDER_BY_LATEST,  # 按最新时间排序
                time=JmMagicConstants.TIME_ALL,  # 全部时间
                category=JmMagicConstants.CATEGORY_ALL,  # 全部分类
                sub_category=None
            )
            
            return self._format_search_result(search_page, f"漫画名: {comic_name}")
            
        except Exception as e:
            self.logger.error(f"搜索漫画名失败: {e}")
            return {
                'success': False,
                'message': f'搜索失败: {str(e)}',
                'query': comic_name,
                'type': 'comic_name'
            }
    
    def search_comic_by_author(self, author_name: str, page: int = 1) -> Dict[str, Any]:
        """
        按作者名搜索
        
        Args:
            author_name: 作者名称
            page: 页码，默认第1页
            
        Returns:
            搜索结果字典
        """
        try:
            client = self.get_client()
            
            # 使用作者搜索，main_tag=2表示作者搜索
            search_page = client.search(
                search_query=author_name,
                page=page,
                main_tag=2,  # 2=作者搜索
                order_by=JmMagicConstants.ORDER_BY_LATEST,  # 按最新时间排序
                time=JmMagicConstants.TIME_ALL,  # 全部时间
                category=JmMagicConstants.CATEGORY_ALL,  # 全部分类
                sub_category=None
            )
            
            return self._format_search_result(search_page, f"作者: {author_name}")
            
        except Exception as e:
            self.logger.error(f"搜索作者失败: {e}")
            return {
                'success': False,
                'message': f'搜索失败: {str(e)}',
                'query': author_name,
                'type': 'author'
            }
    
    def get_comic_detail(self, comic_id: str) -> Dict[str, Any]:
        """
        获取漫画详情
        
        Args:
            comic_id: 漫画ID
            
        Returns:
            漫画详情字典
        """
        try:
            client = self.get_client()
            album_detail = client.get_album_detail(comic_id)
            
            return {
                'success': True,
                'comic': {
                    'id': album_detail.album_id,
                    'title': album_detail.name,
                    'author': album_detail.author,
                    'tags': album_detail.tags,
                    'description': album_detail.description,
                    'page_count': album_detail.page_count,
                    'pub_date': album_detail.pub_date,
                    'update_date': album_detail.update_date,
                    'likes': album_detail.likes,
                    'views': album_detail.views,
                    'comment_count': album_detail.comment_count,
                    'episode_count': len(album_detail.episode_list),
                    'url': f"https://18comic.vip/album/{comic_id}/"
                }
            }
            
        except Exception as e:
            self.logger.error(f"获取漫画详情失败: {e}")
            return {
                'success': False,
                'message': f'获取漫画详情失败: {str(e)}',
                'comic_id': comic_id
            }
    
    def _format_search_result(self, search_page: JmSearchPage, query_info: str) -> Dict[str, Any]:
        """
        格式化搜索结果
        
        Args:
            search_page: 搜索结果页面
            query_info: 查询信息
            
        Returns:
            格式化的搜索结果
        """
        try:
            # 提取搜索结果
            comics = []
            for album_id, album_info in search_page.content:
                comic_info = {
                    'id': album_id,
                    'title': album_info.get('name', ''),
                    'tags': album_info.get('tags', []),
                    'url': f"https://18comic.vip/album/{album_id}/"  # 生成访问链接
                }
                comics.append(comic_info)
            
            return {
                'success': True,
                'query_info': query_info,
                'total': search_page.total,
                'page': search_page.page_count,
                'current_page': 1,  # 当前页
                'comics': comics,
                'message': f'找到 {len(comics)} 个结果，共 {search_page.total} 个'
            }
            
        except Exception as e:
            self.logger.error(f"格式化搜索结果失败: {e}")
            return {
                'success': False,
                'message': f'处理搜索结果失败: {str(e)}',
                'comics': []
            }


# 创建全局服务实例
comic_service = ComicService()


# 便捷函数
def download_comic(album_id: str) -> Dict[str, Any]:
    """下载漫画的便捷函数"""
    return comic_service.download_comic(album_id)


def search_comic_by_name(comic_name: str, page: int = 1) -> Dict[str, Any]:
    """按漫画名搜索的便捷函数"""
    return comic_service.search_comic_by_name(comic_name, page)


def search_comic_by_author(author_name: str, page: int = 1) -> Dict[str, Any]:
    """按作者名搜索的便捷函数"""
    return comic_service.search_comic_by_author(author_name, page)


def get_comic_detail(comic_id: str) -> Dict[str, Any]:
    """获取漫画详情的便捷函数"""
    return comic_service.get_comic_detail(comic_id)


# MCP工厂函数
def validate_agent_config(config: Dict[str, Any]) -> bool:
    """
    验证Agent配置
    
    Args:
        config: 配置字典
        
    Returns:
        配置是否有效
    """
    try:
        # 检查必需的配置项
        required_configs = [
            'COMIC_DOWNLOADER_HOST',
            'COMIC_DOWNLOADER_PORT',
            'COMIC_DOWNLOADER_PATH',
            'COMIC_DOWNLOADER_MAX_CONCURRENT'
        ]
        
        for config_key in required_configs:
            if config_key not in config:
                logging.warning(f"缺少配置项: {config_key}")
        
        logging.info("ComicService配置验证通过")
        return True
        
    except Exception as e:
        logging.error(f"ComicService配置验证失败: {e}")
        return False


def get_agent_dependencies() -> List[str]:
    """
    获取Agent依赖列表
    
    Returns:
        依赖包列表
    """
    return [
        'fastapi>=0.104.0',
        'uvicorn>=0.24.0',
        'pydantic>=2.0.0',
        'requests>=2.31.0',
        'pathlib2>=2.3.7',
        'commonx>=0.6.38',
        'curl-cffi',
        'pillow',
        'pycryptodome',
        'pyyaml',
        'psutil',
        'zhconv'
    ]
