import json
import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from system.config import config

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False

class Crawl4aiAgent:
    
    name = "Crawl4aiAgent"
    instructions = "使用Crawl4AI解析网页内容，返回结构化的Markdown格式给AI"
    
    def __init__(self):
        if not CRAWL4AI_AVAILABLE:
            print("[WARN] Crawl4AI未安装，请运行: pip install crawl4ai")
            
        # 配置参数
        self.headless = True
        self.timeout = 30000
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.viewport_width = 1280
        self.viewport_height = 720
        self.max_chars = 4096  # 默认获取前4096个字符
        
        # 从配置中读取设置
        self._load_config()
        
        print(f"[OK] Crawl4aiAgent初始化完成，Headless: {self.headless}, Timeout: {self.timeout}ms")
    
    def _load_config(self):
        """从配置中加载设置"""
        try:
            # 1: 从全局config对象读取
            if hasattr(config, 'crawl4ai'):
                crawl4ai_config = config.crawl4ai
                if hasattr(crawl4ai_config, 'headless'):
                    self.headless = bool(crawl4ai_config.headless)
                if hasattr(crawl4ai_config, 'timeout'):
                    self.timeout = int(crawl4ai_config.timeout)
                if hasattr(crawl4ai_config, 'user_agent'):
                    self.user_agent = str(crawl4ai_config.user_agent)
                if hasattr(crawl4ai_config, 'viewport_width'):
                    self.viewport_width = int(crawl4ai_config.viewport_width)
                if hasattr(crawl4ai_config, 'viewport_height'):
                    self.viewport_height = int(crawl4ai_config.viewport_height)
                if hasattr(crawl4ai_config, 'max_chars'):
                    self.max_chars = int(crawl4ai_config.max_chars)
        except Exception as e:
            print(f"[WARN] 从全局配置读取Crawl4AI配置时出错: {e}")
            
        # 2: 从config.json文件读取
        try:
            config_path = Path(__file__).parent.parent.parent / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                if 'crawl4ai' in config_data:
                    crawl4ai_config = config_data['crawl4ai']
                    if 'headless' in crawl4ai_config:
                        self.headless = bool(crawl4ai_config['headless'])
                    if 'timeout' in crawl4ai_config:
                        self.timeout = int(crawl4ai_config['timeout'])
                    if 'user_agent' in crawl4ai_config:
                        self.user_agent = str(crawl4ai_config['user_agent'])
                    if 'viewport_width' in crawl4ai_config:
                        self.viewport_width = int(crawl4ai_config['viewport_width'])
                    if 'viewport_height' in crawl4ai_config:
                        self.viewport_height = int(crawl4ai_config['viewport_height'])
                    if 'max_chars' in crawl4ai_config:
                        self.max_chars = int(crawl4ai_config['max_chars'])
        except Exception as e:
            print(f"[WARN] 从config.json文件读取Crawl4AI配置时出错: {e}")
    
    async def crawl_page(self, url: str, css_selector: Optional[str] = None, 
                       wait_for: Optional[str] = None, javascript_enabled: bool = True,
                       screenshot: bool = False, max_chars: Optional[int] = None) -> Dict[str, Any]:
        """使用Crawl4AI解析网页"""
        if not CRAWL4AI_AVAILABLE:
            return {
                "success": False,
                "error": "Crawl4AI未安装，请运行: pip install crawl4ai"
            }
        
        try:
            # 使用传入的max_chars或默认值
            char_limit = max_chars if max_chars is not None else self.max_chars
            
            # 创建浏览器配置
            browser_config = BrowserConfig(
                headless=self.headless,
                user_agent=self.user_agent,
                viewport_width=self.viewport_width,
                viewport_height=self.viewport_height
            )
            
            # 创建爬取配置
            run_config = CrawlerRunConfig(
                word_count_threshold=1,
                css_selector=css_selector if css_selector else None,
                wait_for=wait_for if wait_for else None,
                screenshot=screenshot,
                cache_mode="bypass"  # 不使用缓存，获取最新内容
            )
            
            # 创建爬虫实例
            async with AsyncWebCrawler(config=browser_config) as crawler:
                # 执行爬取
                result = await crawler.arun(url=url, config=run_config)
                
                if result.success:
                    # 构建返回数据
                    metadata = {
                        "url": result.url,
                        "title": getattr(result, 'title', ''),
                        "description": getattr(result, 'description', ''),
                        "media_count": len(getattr(result, 'media', [])),
                        "links_count": len(getattr(result, 'links', [])),
                        "screenshot_path": getattr(result, 'screenshot_path', None)
                    }
                    
                    # 格式化Markdown内容
                    markdown_content = self._format_markdown(result)
                    
                    # 限制字符数
                    if char_limit > 0 and len(markdown_content) > char_limit:
                        markdown_content = markdown_content[:char_limit] + "\n\n...（内容已截断，仅显示前" + str(char_limit) + "个字符）"
                    
                    return {
                        "success": True,
                        "data": markdown_content,
                        "metadata": metadata,
                        "raw_markdown": result.markdown
                    }
                else:
                    return {
                        "success": False,
                        "error": f"爬取失败: {result.error_message if hasattr(result, 'error_message') else '未知错误'}"
                    }
                    
        except Exception as e:
            return {
                "success": False,
                "error": f"解析过程中发生错误: {str(e)}"
            }
    
    def _format_markdown(self, result) -> str:
        """格式化Markdown内容，添加AI友好的结构"""
        markdown_content = f"# 网页解析结果\n\n"
        markdown_content += f"**URL**: {result.url}\n\n"
        
        # 添加标题
        if hasattr(result, 'title') and result.title:
            markdown_content += f"**标题**: {result.title}\n\n"
        
        # 添加描述
        if hasattr(result, 'description') and result.description:
            markdown_content += f"**描述**: {result.description}\n\n"
        
        # 添加分隔线
        markdown_content += "---\n\n"
        
        # 添加主要内容
        if result.markdown:
            markdown_content += "## 内容\n\n"
            markdown_content += result.markdown
        
        # 添加媒体信息
        if hasattr(result, 'media') and result.media:
            media_list = result.media if isinstance(result.media, list) else list(result.media)
            markdown_content += "\n## 媒体文件\n\n"
            markdown_content += f"共发现 {len(media_list)} 个媒体文件\n\n"
            for i, media in enumerate(media_list[:5], 1):  # 只显示前5个
                if isinstance(media, dict):
                    media_type = media.get('type', 'unknown')
                    src = media.get('src', '')
                    alt = media.get('alt', '')
                    markdown_content += f"{i}. **类型**: {media_type}, **来源**: {src}"
                    if alt:
                        markdown_content += f", **描述**: {alt}"
                elif isinstance(media, str):
                    markdown_content += f"{i}. {media}"
                else:
                    markdown_content += f"{i}. {str(media)}"
                markdown_content += "\n"
        
        # 添加链接信息
        if hasattr(result, 'links') and result.links:
            links_list = result.links if isinstance(result.links, list) else list(result.links)
            markdown_content += "\n## 链接\n\n"
            markdown_content += f"共发现 {len(links_list)} 个链接\n\n"
            for i, link in enumerate(links_list[:5], 1):  # 只显示前5个
                if isinstance(link, dict):
                    href = link.get('href', '')
                    text = link.get('text', '')
                    markdown_content += f"{i}. [{text}]({href})\n"
                elif isinstance(link, str):
                    markdown_content += f"{i}. {link}\n"
                else:
                    markdown_content += f"{i}. {str(link)}\n"
        
        return markdown_content
    
    async def handle_handoff(self, data: dict) -> str:
        """处理解析请求"""
        try:
            tool_name = data.get("tool_name", "").lower()
            
            if tool_name == "网页解析":
                url = data.get("url")
                if not url:
                    return json.dumps({
                        "status": "error",
                        "message": "解析需要指定URL（url参数）",
                        "data": {}
                    }, ensure_ascii=False)
                
                # 获取可选参数
                css_selector = data.get("css_selector")
                wait_for = data.get("wait_for")
                javascript_enabled = data.get("javascript_enabled", True)
                screenshot = data.get("screenshot", False)
                max_chars = data.get("max_chars")
                if max_chars is not None:
                    try:
                        max_chars = int(max_chars)
                    except (ValueError, TypeError):
                        return json.dumps({
                            "status": "error",
                            "message": f"无效的max_chars参数: '{max_chars}'，必须是一个有效的整数。",
                            "data": {}
                        }, ensure_ascii=False)
                
                # 执行解析
                crawl_result = await self.crawl_page(
                    url=url,
                    css_selector=css_selector,
                    wait_for=wait_for,
                    javascript_enabled=javascript_enabled,
                    screenshot=screenshot,
                    max_chars=max_chars
                )
                
                if crawl_result["success"]:
                    return json.dumps({
                        "status": "ok",
                        "message": "网页解析完成",
                        "data": crawl_result["data"],
                        "metadata": crawl_result.get("metadata", {}),
                        "raw_markdown": crawl_result.get("raw_markdown", "")
                    }, ensure_ascii=False)
                else:
                    return json.dumps({
                        "status": "error",
                        "message": f"解析失败: {crawl_result['error']}",
                        "data": {}
                    }, ensure_ascii=False)
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"不支持的操作: {tool_name}，支持的操作：网页解析",
                    "data": {}
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"Crawl4AI Agent处理异常: {str(e)}",
                "data": {}
            }, ensure_ascii=False)


def create_crawl4ai_agent():
    """创建Crawl4aiAgent实例"""
    return Crawl4aiAgent()


def validate_agent_config():
    """验证Agent配置"""
    try:
        if not CRAWL4AI_AVAILABLE:
            return False, "Crawl4AI未安装，请运行: pip install crawl4ai"
        
        # 检查基本配置
        try:
            # 可以在这里添加更多的配置验证逻辑
            pass
        except Exception as e:
            return False, f"配置验证失败: {str(e)}"
        
        return True, "配置验证通过"
    except Exception as e:
        return False, f"配置验证失败: {str(e)}"


def get_agent_dependencies():
    """获取Agent依赖"""
    dependencies = ["json", "os", "asyncio", "pathlib"]
    if CRAWL4AI_AVAILABLE:
        dependencies.extend(["crawl4ai"])
    return dependencies