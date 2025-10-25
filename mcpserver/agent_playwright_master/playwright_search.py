from playwright.async_api import Page
import asyncio
import sys
import re
import json
import urllib.parse
from typing import List, Dict, Any
from system.config import config

class SearchEngine:
    """搜索引擎适配器，支持多种搜索引擎"""
    
    @staticmethod
    def build_search_url(query: str, engine: str = "google") -> str:
        """
        构建搜索URL
        
        Args:
            query: 搜索关键词
            engine: 搜索引擎，支持 'google', 'bing', 'baidu'
            
        Returns:
            搜索URL
        """
        encoded_query = urllib.parse.quote(query)
        
        if engine.lower() == "google":
            return f"https://www.google.com/search?q={encoded_query}"
        elif engine.lower() == "bing":
            return f"https://www.bing.com/search?q={encoded_query}"
        elif engine.lower() == "baidu":
            return f"https://www.baidu.com/s?wd={encoded_query}"
        elif engine.lower() == "pubmed":
            return f"https://pubmed.ncbi.nlm.nih.gov/?term={encoded_query}"
        elif engine.lower() == "scholar":
            return f"https://scholar.google.com/scholar?q={encoded_query}"
        else:
            # 默认使用Google
            return f"https://www.google.com/search?q={encoded_query}"

    @staticmethod
    async def extract_search_results(page: Page, engine: str = "google") -> List[Dict[str, str]]:
        """
        从搜索结果页面提取搜索结果
        
        Args:
            page: Playwright页面对象
            engine: 搜索引擎
            
        Returns:
            搜索结果列表，每个结果包含标题、URL和摘要
        """
        results = []
        
        try:
            if engine.lower() == "google":
                # 提取Google搜索结果
                elements = await page.query_selector_all("div.g")
                for element in elements[:5]:  # 只取前5个结果
                    title_element = await element.query_selector("h3")
                    link_element = await element.query_selector("a")
                    snippet_element = await element.query_selector("div.VwiC3b")
                    
                    if title_element and link_element:
                        title = await title_element.inner_text()
                        href = await link_element.get_attribute("href")
                        snippet = ""
                        if snippet_element:
                            snippet = await snippet_element.inner_text()
                        
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": snippet
                        })
            
            elif engine.lower() == "bing":
                # 提取Bing搜索结果
                elements = await page.query_selector_all("li.b_algo")
                for element in elements[:5]:
                    title_element = await element.query_selector("h2 a")
                    snippet_element = await element.query_selector("div.b_caption p")
                    
                    if title_element:
                        title = await title_element.inner_text()
                        href = await title_element.get_attribute("href")
                        snippet = ""
                        if snippet_element:
                            snippet = await snippet_element.inner_text()
                        
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": snippet
                        })
            
            elif engine.lower() == "pubmed":
                # 提取PubMed搜索结果
                elements = await page.query_selector_all("article.full-docsum")
                for element in elements[:5]:
                    title_element = await element.query_selector("a.docsum-title")
                    link_element = await element.query_selector("a.docsum-title")
                    snippet_element = await element.query_selector("div.full-view-snippet")
                    
                    if title_element and link_element:
                        title = await title_element.inner_text()
                        href_rel = await link_element.get_attribute("href")
                        href = f"https://pubmed.ncbi.nlm.nih.gov{href_rel}" if href_rel.startswith("/") else href_rel
                        snippet = ""
                        if snippet_element:
                            snippet = await snippet_element.inner_text()
                        
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": snippet
                        })
            
            elif engine.lower() == "scholar":
                # 提取Google Scholar搜索结果
                elements = await page.query_selector_all("div.gs_ri")
                for element in elements[:5]:
                    title_element = await element.query_selector("h3 a")
                    snippet_element = await element.query_selector("div.gs_rs")
                    
                    if title_element:
                        title = await title_element.inner_text()
                        href = await title_element.get_attribute("href")
                        snippet = ""
                        if snippet_element:
                            snippet = await snippet_element.inner_text()
                        
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": snippet
                        })
            
            else:  # 默认尝试通用提取
                # 通用提取逻辑，尝试找到链接和相关文本
                link_elements = await page.query_selector_all("a[href^='http']")
                for link in link_elements[:10]:
                    href = await link.get_attribute("href")
                    if href and not href.startswith("javascript:"):
                        title = await link.inner_text() or href
                        results.append({
                            "title": title,
                            "url": href,
                            "snippet": ""
                        })
        
        except Exception as e:
            sys.stderr.write(f"提取搜索结果时出错: {str(e)}\n")
            import traceback
            traceback.print_exc(file=sys.stderr)
        
        return results

# ----------- Edge路径动态扫描函数 -----------
def get_edge_path():
    """动态获取Edge浏览器可执行文件路径，优先解析.lnk，找不到则遍历常见目录"""  # 右侧注释
    import os, platform
    if platform.system() != "Windows":
        return None  # 仅Windows下处理
    # 1. 解析.lnk
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
        except Exception as e:
            sys.stderr.write(f"Edge .lnk解析失败: {e}\n")
    # 2. 遍历常见目录
    for p in config.browser.edge_common_paths:
        if os.path.exists(p):
            return p
    raise RuntimeError("未检测到Microsoft Edge浏览器，请先安装Edge或检查.lnk路径！")
# ----------- END Edge路径动态扫描 -----------

async def search_web(query: str, engine: str = "google") -> Dict[str, Any]:
    """
    执行Web搜索并返回结果
    
    Args:
        query: 搜索关键词
        engine: 搜索引擎
        
    Returns:
        搜索结果字典
    """
    # 动态导入，避免循环引用
    from playwright.async_api import async_playwright
    
    # 尝试从config导入，如果失败则使用默认值
    try:
        from system.config import config
    except ImportError:
        PLAYWRIGHT_HEADLESS = True
    
    sys.stderr.write(f"执行Web搜索: query={query}, engine={engine}\n")
    
    try:
        # 构建搜索URL
        search_url = SearchEngine.build_search_url(query, engine)
        sys.stderr.write(f"搜索URL: {search_url}\n")
        
        # 启动浏览器
        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(headless=config.browser.playwright_headless, channel="msedge")  # 优先用官方Edge通道
        except Exception as e:
            sys.stderr.write(f"用channel方式启动Edge失败: {e}，尝试executable_path方式\n")
            edge_path = get_edge_path()
            browser = await playwright.chromium.launch(headless=config.browser.playwright_headless, executable_path=edge_path)
        page = await browser.new_page()
        
        # 访问搜索页面
        await page.goto(search_url, wait_until="networkidle")
        
        # 提取搜索结果
        results = await SearchEngine.extract_search_results(page, engine)
        
        # 获取页面标题和内容
        title = await page.title()
        content = await page.content()
        
        # 关闭浏览器
        await browser.close()
        await playwright.stop()
        
        # 返回结果
        return {
            "status": "ok",
            "message": "搜索成功",
            "data": {
                "query": query,
                "engine": engine,
                "url": search_url,
                "page_title": title,
                "results": results,
                "page_content_length": len(content)
            }
        }
    
    except Exception as e:
        sys.stderr.write(f"搜索执行失败: {str(e)}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)
        
        return {
            "status": "error",
            "message": f"搜索执行失败: {str(e)}",
            "data": {
                "query": query,
                "engine": engine
            }
        }
