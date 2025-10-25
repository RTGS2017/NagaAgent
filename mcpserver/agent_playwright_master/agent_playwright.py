# agent_playwright.py # 简化的浏览器Agent，只保留基本功能
import asyncio
import json
import sys
import os
import platform
from playwright.async_api import async_playwright
from nagaagent_core.vendors.agents import Agent  # 统一代理 #
from system.config import config

print = lambda *a, **k: sys.stderr.write('[print] ' + (' '.join(map(str, a))) + '\n')

class SimpleBrowserTool:
    """简化的浏览器工具类，只保留基本功能"""
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._is_initialized = False
        
    async def _check_browser_alive(self):
        """检查浏览器和页面是否仍然有效"""
        try:
            if not self._browser or not self._page:
                return False
            
            # 检查浏览器连接是否有效
            if self._browser.is_connected():
                # 尝试获取页面标题来验证页面是否有效
                await self._page.title()
                return True
            return False
        except Exception:
            return False
    
    async def _init_browser(self, force_reinit=False):
        """初始化浏览器"""
        # 如果强制重新初始化或检查发现连接断开，则重新初始化
        if force_reinit or not await self._check_browser_alive():
            # 先清理现有资源
            await self._cleanup_browser()
            
            try:
                self._playwright = await async_playwright().start()
                
                # 尝试使用Edge通道启动
                try:
                    self._browser = await self._playwright.chromium.launch(
                        headless=config.browser.playwright_headless,
                        channel="msedge"
                    )
                    print("✅ 使用Edge通道启动浏览器成功")
                except Exception as e:
                    print(f"Edge通道启动失败: {e}，尝试使用可执行文件路径")
                    # 尝试使用可执行文件路径
                    edge_path = self._get_edge_path()
                    if edge_path:
                        self._browser = await self._playwright.chromium.launch(
                            headless=config.browser.playwright_headless,
                            executable_path=edge_path
                        )
                        print(f"✅ 使用路径启动浏览器成功: {edge_path}")
                    else:
                        raise Exception("未找到Edge浏览器")
                        
                self._page = await self._browser.new_page()
                self._is_initialized = True
                print("✅ 浏览器初始化完成")
                
            except Exception as e:
                print(f"❌ 浏览器初始化失败: {e}")
                await self._cleanup_browser()
                raise
    
    async def _cleanup_browser(self):
        """清理浏览器资源"""
        try:
            if self._page:
                await self._page.close()
        except Exception:
            pass
        
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
            
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
            
        self._page = None
        self._browser = None
        self._playwright = None
        self._is_initialized = False
    
    def _get_edge_path(self):
        """获取Edge浏览器路径"""
        if platform.system() != "Windows":
            return None
            
        # 1. 尝试解析.lnk文件
        if os.path.exists(config.browser.edge_lnk_path):
            try:
                import pythoncom
                from win32com.shell import shell
                shortcut = pythoncom.CoCreateInstance(
                    shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink
                )
                shortcut.QueryInterface(shell.IID_IPersistFile).Load(config.browser.edge_lnk_path)
                exe = shortcut.GetPath(shell.SLGP_UNCPRIORITY)[0]
                if exe and os.path.exists(exe):
                    return exe
            except ImportError as e:
                print(f"win32com模块未安装，跳过.lnk文件解析: {e}")
            except Exception as e:
                print(f"解析.lnk文件失败: {e}")
        
        # 2. 尝试常见路径
        for path in config.browser.edge_common_paths:
            if os.path.exists(path):
                return path
                
        return None
    
    async def open_url(self, url: str, new_tab: bool = False) -> dict:
        """打开URL"""
        try:
            # 先检查并确保浏览器连接有效
            await self._init_browser()
            
            # 确保URL格式正确
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                
            if new_tab:
                # 新建标签页
                page = await self._browser.new_page()
            else:
                # 使用当前页面
                page = self._page
                
            # 打开URL - 如果失败可能是连接断开，尝试重新初始化
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            except Exception as goto_error:
                print(f"页面导航失败，尝试重新初始化浏览器: {goto_error}")
                # 强制重新初始化浏览器
                await self._init_browser(force_reinit=True)
                
                # 重新尝试打开URL
                if new_tab:
                    page = await self._browser.new_page()
                else:
                    page = self._page
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            # 获取页面信息
            title = await page.title()
            
            return {
                'status': 'ok',
                'message': f'成功打开网页: {title}',
                'data': {
                    'url': url,
                    'title': title,
                    'new_tab': new_tab
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'打开网页失败: {str(e)}',
                'data': {'url': url}
            }
    
    async def search_web(self, query: str, engine: str = 'google') -> dict:
        """搜索网页"""
        try:
            # 先检查并确保浏览器连接有效
            await self._init_browser()
            
            # 构建搜索URL
            if engine.lower() == 'google':
                search_url = f'https://www.google.com/search?q={query}'
            elif engine.lower() == 'bing':
                search_url = f'https://www.bing.com/search?q={query}'
            elif engine.lower() == 'baidu':
                search_url = f'https://www.baidu.com/s?wd={query}'
            else:
                search_url = f'https://www.google.com/search?q={query}'
                
            # 打开搜索页面 - 如果失败可能是连接断开，尝试重新初始化
            try:
                await self._page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            except Exception as goto_error:
                print(f"搜索页面导航失败，尝试重新初始化浏览器: {goto_error}")
                # 强制重新初始化浏览器
                await self._init_browser(force_reinit=True)
                await self._page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
                
            title = await self._page.title()
            
            return {
                'status': 'ok',
                'message': f'搜索完成: {title}',
                'data': {
                    'query': query,
                    'engine': engine,
                    'url': search_url,
                    'title': title
                }
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'搜索失败: {str(e)}',
                'data': {'query': query, 'engine': engine}
            }
    
    async def close(self):
        """关闭浏览器"""
        await self._cleanup_browser()
        print("✅ 浏览器已关闭")

class PlaywrightAgent(Agent):
    """简化的Playwright浏览器Agent"""
    
    def __init__(self):
        self._tool = SimpleBrowserTool()
        super().__init__(
            name="Playwright Browser Agent",
            instructions="使用Edge浏览器打开网页和搜索的智能体",
            tools=[],
            model="browser-use-preview"
        )
        print("✅ PlaywrightAgent初始化完成")
    
    async def handle_handoff(self, data: dict) -> str:
        """处理handoff请求，适配新的handoff机制"""
        try:
            # 使用tool_name参数
            tool_name = data.get("tool_name")
            if not tool_name:
                return json.dumps({
                    "status": "error", 
                    "message": "缺少tool_name参数", 
                    "data": {}
                }, ensure_ascii=False)
            
            if tool_name == "open":
                url = data.get("url")
                new_tab = data.get("new_tab", False)
                
                if not url:
                    return json.dumps({
                        "status": "error",
                        "message": "open操作需要url参数",
                        "data": {}
                    }, ensure_ascii=False)
                
                result = await self._tool.open_url(url, new_tab)
                return json.dumps(result, ensure_ascii=False)
                
            elif tool_name == "search":
                query = data.get("query")
                engine = data.get("engine", "google")
                
                if not query:
                    return json.dumps({
                        "status": "error",
                        "message": "search操作需要query参数",
                        "data": {}
                    }, ensure_ascii=False)
                
                result = await self._tool.search_web(query, engine)
                return json.dumps(result, ensure_ascii=False)
                
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"未知操作: {tool_name}",
                    "data": {}
                }, ensure_ascii=False)
                
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": str(e),
                "data": {}
            }, ensure_ascii=False)
    
    async def cleanup(self):
        """清理资源"""
        await self._tool.close()

# 工厂函数
def create_playwright_agent():
    """创建PlaywrightAgent实例"""
    return PlaywrightAgent()

def validate_agent_config(config):
    """验证Agent配置"""
    return True

def get_agent_dependencies():
    """获取Agent依赖"""
    return ["playwright"]

if __name__ == "__main__":
    print("playwright.py 进入MCP主循环")
    import asyncio
    from agents.mcp import MCPServerStdio
    
    async def _main():
        agent = PlaywrightAgent()
        server = MCPServerStdio(
            name="playwright",
            agent=agent
        )
        await server.serve()
        
    asyncio.run(_main()) 