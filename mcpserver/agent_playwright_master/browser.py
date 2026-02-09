from typing import Callable
from system.config import *  # 配置参数统一管理 #
import asyncio
import nagaagent_core.vendors.html2text as html2text  # 用于HTML转Markdown #
from nagaagent_core.core import load_dotenv
from nagaagent_core.vendors.agents import Agent, AgentHooks, RunContextWrapper  # 统一代理 #
# 移除循环导入
# from .controller import BrowserAgent
# from .browser import ContentAgent
from system.config import config  # 使用新的配置系统

AD_SELECTORS = [
    'script', 'style', 'iframe', 'ins', '.ads', '[class*="ads"]', '[id*="ads"]',
    '.advertisement', '[class*="advertisement"]', '[id*="advertisement"]',
    '.banner', '[class*="banner"]', '[id*="banner"]',
    '.popup', '[class*="popup"]', '[id*="popup"]',
    'nav', 'aside', 'footer', '[aria-hidden="true"]'
]  # 广告选择器列表 #

class PlaywrightBrowser:
    """Playwright浏览器观察器，负责页面内容获取、变化监听与推送 #"""
    def __init__(self, page):
        self.page = page  # 当前页面实例 #
        self._subscribe_task = None  # 推送任务 #

    async def get_content(self, format: str = "markdown") -> str:
        """获取页面内容，支持markdown或html格式，自动去广告 #"""
        try:
            # 注入JS移除广告元素 #
            remove_ads_js = """
            (function() {
                const selectors = %s;
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
            })();
            """ % (AD_SELECTORS)
            await self.page.evaluate(remove_ads_js)  #
            html = await self.page.content()  #
            if format == "markdown":
                md = html2text.html2text(html)  # 转为Markdown #
                return md  #
            return html  #
        except Exception as e:
            return f'获取内容失败: {e}'  #

    async def get_title(self) -> str:
        """获取页面标题 #"""
        try:
            title = await self.page.title()  #
            return title  #
        except Exception as e:
            return f'获取标题失败: {e}'  #

    async def get_screenshot(self) -> bytes:
        """获取页面截图 #"""
        try:
            screenshot = await self.page.screenshot(full_page=False)  #
            return screenshot  #
        except Exception:
            return b''  #

    async def subscribe_page_change(self, callback: Callable[[str], None], interval: float = 2.0, format: str = "markdown"):
        """订阅页面内容变化，定时推送，支持格式切换 #"""
        async def _worker():
            last_content = None
            while True:
                try:
                    content = await self.get_content(format=format)  #
                    if content != last_content:
                        callback(content)  # 推送变化内容 #
                        last_content = content
                except Exception as e:
                    callback(f'推送内容失败: {e}')  #
                await asyncio.sleep(interval)  #
        if self._subscribe_task is None or self._subscribe_task.done():
            self._subscribe_task = asyncio.create_task(_worker())  # 启动推送任务 #

    def stop_subscribe(self):
        """停止推送任务 #"""
        if self._subscribe_task:
            self._subscribe_task.cancel()  #
            self._subscribe_task = None  #

    # 只保留监视相关功能 # 

class ContentAgentHooks(AgentHooks):
    async def on_start(self, context: RunContextWrapper, agent: Agent):
        print(f"[ContentAgent] 开始: {agent.name}")
    async def on_end(self, context: RunContextWrapper, agent: Agent, output):
        print(f"[ContentAgent] 结束: {agent.name}, 输出: {output}")

class ContentAgent:
    """ContentAgent类，实现handle_handoff方法以支持MCP调用 #"""
    name = "ContentAgent"
    
    def __init__(self):
        self.browser = None  # PlaywrightBrowser实例 #
    
    async def handle_handoff(self, task: dict) -> str:
        """处理MCP handoff请求，执行内容处理 #"""
        try:
            action = task.get("action", "")
            
            # 这里应该初始化PlaywrightBrowser并执行相应操作 #
            # 暂时返回模拟结果 #
            if action == "get_content":
                format_type = task.get("format", "markdown")
                return f"ContentAgent已获取页面内容，格式: {format_type}"
            elif action == "get_title":
                return "ContentAgent已获取页面标题"
            elif action == "get_screenshot":
                return "ContentAgent已获取页面截图"
            elif action == "subscribe_page_change":
                interval = task.get("interval", 2.0)
                return f"ContentAgent已订阅页面变化，间隔: {interval}秒"
            else:
                return f"ContentAgent不支持的操作: {action}"
                
        except Exception as e:
            return f"ContentAgent处理失败: {str(e)}"

load_dotenv()
# 从config中获取API配置
API_KEY = config.api.api_key
BASE_URL = config.api.base_url
MODEL_NAME = config.api.model

# 延迟创建ContentAgent实例，避免循环导入
def create_content_agent():
    """创建ContentAgent实例的工厂函数"""
    return Agent(
        name="ContentAgent",
        instructions="你负责对网页内容进行清洗、摘要、翻译等处理。",
        tools=[PlaywrightBrowser],
        hooks=ContentAgentHooks(),
        model=MODEL_NAME
    )

# 为了向后兼容，保留ContentAgent变量
ContentAgent = create_content_agent() 