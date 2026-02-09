# agent_weather_time.py # 天气和时间查询Agent
import json # 导入json模块
from nagaagent_core.core import aiohttp # 异步HTTP请求
from nagaagent_core.vendors.agents import Agent, ComputerTool # 统一代理 #
from nagaagent_core.core import requests # 用于同步获取IP和城市
import re # 用于正则解析
from datetime import datetime # 用于日期处理

from mcpserver.agent_weather_time.city_codes import codes_map

IPIP_URL = "https://myip.ipip.net/" # 统一配置

class WeatherTimeTool:
    """天气和时间工具类"""
    def __init__(self):
        self._ip_info = None # 缓存IP信息
        self._local_ip = None # 本地IP
        self._local_city = None # 本地城市
        self._get_local_ip_and_city() # 初始化时获取本地IP和城市
        import asyncio
        try:
            # 使用新的API检查事件循环状态 # 右侧注释
            try:
                loop = asyncio.get_running_loop()
                # 有运行中的事件循环，创建异步任务
                asyncio.create_task(self._preload_ip_info())
            except RuntimeError:
                # 没有运行中的事件循环
                self._ip_info = None # 不再异步获取IP
        except Exception:
            self._ip_info = None

    def _get_local_ip_and_city(self):
        """同步获取本地IP和城市"""
        try:
            resp = requests.get(IPIP_URL, timeout=5)
            resp.encoding = 'utf-8'
            html = resp.text
            match = re.search(r"当前 IP：([\d\.]+)\s+来自于：(.+?)\s{2,}", html)
            if match:
                self._local_ip = match.group(1)
                self._local_city = match.group(2)
            else:
                self._local_ip = None
                self._local_city = None
        except Exception:
            self._local_ip = None
            self._local_city = None

    async def _preload_ip_info(self):
        pass # 兼容保留，不再异步获取IP

    async def get_weather(self, code):
        """调用itboy天气接口，返回实况天气+未来3天预报"""  # 右侧注释
        url = f'http://t.weather.itboy.net/api/weather/city/{code}'
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json(content_type=None)
                # 解析api请求并分解为今天, 3天, 15天

                body: dict = data['data']
                now = {}

                for k, v in body.items():
                    if k == 'forecast':
                        continue

                    now[k] = v  # 把forecast外的数据整合再一起

                now['weather'] = body['forecast'][0]

                return now, body['forecast'][:3], body['forecast']

    async def handle(self, action=None, ip=None, city=None, query=None, format=None, **kwargs):
        """统一处理入口，支持LLM传入city参数或自动识别本地城市"""  # 右侧注释
        # 优先使用LLM传入的city参数，如果没有则使用本地城市 # 右侧注释
        if city and city.strip():
            # LLM传入了city参数，直接使用
            city_str = city.strip()
            province, city_name = city_str, city_str
            # 尝试解析省市格式
            match = re.match(r"^([\u4e00-\u9fa5]+) ([\u4e00-\u9fa5]+)$", city_str)
            if match:
                province = match.group(1)
                city_name = match.group(2)
            else:
                parts = city_str.split()
                if len(parts) >= 2:
                    province = parts[-2]
                    city_name = parts[-1]
                else:
                    province = ''
                    city_name =''
        else:
            # LLM没有传入city参数，使用本地城市作为默认值
            city_str = getattr(self, '_local_city', '') or ''
            if city_str.startswith('中国'):
                city_str = city_str[2:].strip()
            province, city_name = city_str, city_str
            if city_str:
                match = re.match(r"^([\u4e00-\u9fa5]+) ([\u4e00-\u9fa5]+)$", city_str)
                if match:
                    province = match.group(1)
                    city_name = match.group(2)
                else:
                    parts = city_str.split()
                    if len(parts) >= 2:
                        province = parts[-2]
                        city_name = parts[-1]
                    else:
                        province = ''
                        city_name = ''

        # 查询城市代码
        city_code = codes_map[f'{province}{city_name}']

        if not city_code:
            return {'status': 'error', 'message': f'未找到城市编码或该城市不存在: {city_name}, 确保city格式为{{省 市}}, 如:湖北 武汉, 直辖市请重复两遍市名, 如:北京 北京'}

        now, d3, d15 = await self.get_weather(city_code)

        # 今日天气查询，只返回今日天气数据 # 右侧注释
        if action in ['today_weather', 'current_weather', 'today']:
            return {'city': city_name, 'response': now}

        # 未来天气查询，返回未来15天预报数据 # 右侧注释
        elif action in ['forecast_weather', 'future_weather', 'forecast', 'weather_forecast']:
            return {'city': city_name, 'response': d15}

        elif action in ['time', 'get_time', 'current_time']:
            # 时间查询
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return {
                'status': 'ok',
                'message': '当前系统时间',
                'data': {
                    'time': current_time,
                    'city': city_name,
                    'province': province
                }
            }
        else:
            return {'status': 'error', 'message': f'未知操作: {action}'}
class WeatherTimeAgent(Agent):
    """天气和时间Agent"""
    def __init__(self):
        self._tool = WeatherTimeTool() # 预加载
        super().__init__(
            name="WeatherTime Agent", # Agent名称
            instructions="天气和时间智能体", # 角色描述
            tools=[ComputerTool(self._tool)], # 注入工具
            model="weather-time-use-preview" # 使用统一模型
        )
        import sys
        ip_str = getattr(self._tool, '_local_ip', '未获取到IP')  # 直接用本地IP
        city_str = getattr(self._tool, '_local_city', '未知城市') # 获取本地城市
        sys.stderr.write(f'✅ WeatherTimeAgent初始化完成，登陆地址：{city_str}\n')

    async def handle_handoff(self, task: dict) -> str:
        try:
            # 只认tool_name参数
            action = task.get("tool_name")
            if not action:
                return json.dumps({"status": "error", "message": "缺少tool_name参数", "data": {}}, ensure_ascii=False)
            ip = task.get("ip")
            city = task.get("city")
            query = task.get("query")
            format = task.get("format")
            result = await self._tool.handle(action, ip, city, query, format)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e), "data": {}}, ensure_ascii=False)