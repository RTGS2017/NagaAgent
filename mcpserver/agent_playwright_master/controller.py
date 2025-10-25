from playwright.async_api import async_playwright, Page
import asyncio, re, json
from typing import Any, Dict, List
from system.config import config  # 使用新的配置系统
import os
from nagaagent_core.core import load_dotenv
from nagaagent_core.vendors.agents import Agent, AgentHooks, RunContextWrapper  # 统一代理 #
# 移除循环导入，延迟导入
# from .browser import PlaywrightBrowser

load_dotenv()
# 从config中获取API配置
API_KEY = config.api.api_key
BASE_URL = config.api.base_url
MODEL_NAME = config.api.model

class PlaywrightController:
    """Playwright控制器，负责页面操作、自动化流程等 #"""
    def __init__(self, page):
        self.page = page  # 当前页面实例 #

    async def open_url(self, url: str, timeout: int = 30000, wait_until: str = 'domcontentloaded') -> str:
        """打开指定URL #"""
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)  # 跳转到目标URL #
            return 'ok'  #
        except Exception as e:
            return f'打开URL失败: {e}'  #

    async def click(self, selector: str) -> str:
        """点击指定元素 #"""
        try:
            await self.page.click(selector)  #
            return 'ok'  #
        except Exception as e:
            return f'点击失败: {e}'  #

    async def type(self, selector: str, text: str) -> str:
        """在指定元素输入文本 #"""
        try:
            await self.page.fill(selector, text)  #
            return 'ok'  #
        except Exception as e:
            return f'输入失败: {e}'  #

    async def search_github(self, query: str, engine: str = "github") -> Dict[str, Any]:
        """自动化在GitHub搜索并提取结果 #"""
        search_url = f"https://github.com/search?q={query}"
        await self.open_url(search_url)
        await asyncio.sleep(2)
        # 提取搜索结果（示例：只取前5个仓库）
        repos = []
        repo_elements = await self.page.query_selector_all('ul.repo-list li')
        for el in repo_elements[:5]:
            title_el = await el.query_selector('a.v-align-middle')
            desc_el = await el.query_selector('p.mb-1')
            url = await title_el.get_attribute('href') if title_el else ''
            title = await title_el.inner_text() if title_el else ''
            desc = await desc_el.inner_text() if desc_el else ''
            repos.append({"title": title, "url": f"https://github.com{url}", "desc": desc})
        return {"status": "ok", "results": repos}

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        """滚动页面 #"""
        try:
            if direction == "down":
                await self.page.evaluate(f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await self.page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "top":
                await self.page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return 'ok'
        except Exception as e:
            return f'滚动失败: {e}'

    async def wait_for_element(self, selector: str, timeout: int = 10000) -> str:
        """等待元素出现 #"""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return 'ok'
        except Exception as e:
            return f'等待元素失败: {e}'

    async def get_element_text(self, selector: str) -> str:
        """获取元素文本内容 #"""
        try:
            element = await self.page.query_selector(selector)
            if element:
                return await element.inner_text()
            return '元素未找到'
        except Exception as e:
            return f'获取文本失败: {e}'

    async def take_screenshot(self, path: str = None) -> str:
        """截图 #"""
        try:
            if path:
                await self.page.screenshot(path=path)
            else:
                screenshot = await self.page.screenshot()
                return f"截图完成，大小: {len(screenshot)} bytes"
            return '截图完成'
        except Exception as e:
            return f'截图失败: {e}'

class BrowserAgentHooks(AgentHooks):
    async def on_start(self, context: RunContextWrapper, agent: Agent):
        print(f"[BrowserAgent] 开始: {agent.name}")
    async def on_end(self, context: RunContextWrapper, agent: Agent, output):
        print(f"[BrowserAgent] 结束: {agent.name}, 输出: {output}")

class BrowserAgent:
    """BrowserAgent类，实现handle_handoff方法以支持MCP调用 #"""
    name = "BrowserAgent"
    
    def __init__(self):
        self.controller = None  # PlaywrightController实例 #
    
    async def handle_handoff(self, task: dict) -> str:
        """处理MCP handoff请求，执行页面操作 #"""
        try:
            action = task.get("action", "")
            
            # 这里应该初始化PlaywrightController并执行相应操作 #
            # 暂时返回模拟结果 #
            if action == "open":
                url = task.get("url", "")
                return f"BrowserAgent已打开URL: {url}"
            elif action == "click":
                selector = task.get("selector", "")
                return f"BrowserAgent已点击元素: {selector}"
            elif action == "type":
                selector = task.get("selector", "")
                text = task.get("text", "")
                return f"BrowserAgent已在{selector}输入: {text}"
            elif action == "scroll":
                direction = task.get("direction", "down")
                return f"BrowserAgent已滚动页面: {direction}"
            elif action == "take_screenshot":
                return "BrowserAgent已截图"
            elif action == "search_github":
                query = task.get("query", "")
                return f"BrowserAgent已在GitHub搜索: {query}"
            else:
                return f"BrowserAgent不支持的操作: {action}"
                
        except Exception as e:
            return f"BrowserAgent处理失败: {str(e)}"

# 延迟创建BrowserAgent实例，避免循环导入
def create_browser_agent():
    """创建BrowserAgent实例的工厂函数"""
    return Agent(
        name="BrowserAgent",
        instructions="你负责网页自动化操作，如打开、点击、输入、滚动、截图等。",
        tools=[PlaywrightController],
        hooks=BrowserAgentHooks(),
        model=MODEL_NAME
    )

# 为了向后兼容，保留BrowserAgent变量
BrowserAgent = create_browser_agent() 