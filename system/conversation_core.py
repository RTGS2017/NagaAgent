# 标准库导入
import asyncio
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime
from typing import List, Dict, Any

# 第三方库导入
from nagaagent_core.core import AsyncOpenAI

# 本地模块导入
from apiserver.tool_call_utils import tool_call_loop
from system.config import config, AI_NAME
from mcpserver.mcp_manager import get_mcp_manager
from system.background_analyzer import get_background_analyzer
from system.prompt_repository import get_prompt
# from thinking import TreeThinkingEngine
# from thinking.config import COMPLEX_KEYWORDS  # 已废弃，不再使用

# 配置日志系统
def setup_logging():
    """统一配置日志系统"""
    log_level = getattr(logging, config.system.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    
    # 设置第三方库日志级别
    for logger_name in ["httpcore.connection", "httpcore.http11", "httpx", "openai._base_client", "asyncio"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("NagaConversation")

# 全局状态管理
class SystemState:
    """系统状态管理器"""
    _tree_thinking_initialized = False
    _mcp_services_initialized = False
    _voice_enabled_logged = False
    _memory_initialized = False
    _persistent_context_initialized = False

# GRAG记忆系统导入
def init_memory_manager():
    """初始化GRAG记忆系统"""
    if not config.grag.enabled:
        return None
    
    try:
        from summer_memory.memory_manager import memory_manager
        print("[GRAG] ✅ 夏园记忆系统初始化成功")
        return memory_manager
    except Exception as e:
        logger.error(f"夏园记忆系统加载失败: {e}")
        return None

memory_manager = init_memory_manager()

# 工具函数
def now():
    """获取当前时间戳"""
    return time.strftime('%H:%M:%S:') + str(int(time.time() * 1000) % 10000)

_builtin_print = print
def print(*a, **k):
    """自定义打印函数"""
    return sys.stderr.write('[print] ' + (' '.join(map(str, a))) + '\n')

class NagaConversation: # 对话主类
    def __init__(self):
        self.mcp = get_mcp_manager()
        self.messages = []
        self.dev_mode = False
        self.async_client = AsyncOpenAI(api_key=config.api.api_key, base_url=config.api.base_url.rstrip('/') + '/')
        
        # 初始化意图分析器（使用新的Agent Server架构）
        self.agent_server_client = None
        self._init_agent_server_client()
        
        # 初始化MCP服务系统
        self._init_mcp_services()
        
        # 初始化GRAG记忆系统（只在首次初始化时显示日志）
        self.memory_manager = memory_manager
        if self.memory_manager and not SystemState._memory_initialized:
            logger.info("夏园记忆系统已初始化")
            SystemState._memory_initialized = True
        
        # 初始化持久化上下文（只在首次初始化时显示日志）
        if config.api.persistent_context and not SystemState._persistent_context_initialized:
            self._load_persistent_context()
            SystemState._persistent_context_initialized = True
        
        # 初始化语音处理系统
        self.voice = None
        if config.system.voice_enabled:
            try:
                # 语音功能已分为语音输入和输出两个独立模块
                # 语音输入：负责语音识别（ASR）和VAD
                # 语音输出：负责文本转语音（TTS）
                # 使用全局变量避免重复输出日志
                if not SystemState._voice_enabled_logged:
                    logger.info("语音功能已启用（语音输入+输出），由UI层管理")
                    SystemState._voice_enabled_logged = True
            except Exception as e:
                logger.warning(f"语音系统初始化失败: {e}")
                self.voice = None
        
        # 禁用树状思考系统
        self.tree_thinking = None
        # 注释掉树状思考系统初始化
        # if not SystemState._tree_thinking_initialized:
        #     try:
        #         self.tree_thinking = TreeThinkingEngine(api_client=self, memory_manager=self.memory_manager)
        #         print("[TreeThinkingEngine] ✅ 树状外置思考系统初始化成功")
        #         SystemState._tree_thinking_initialized = True
        #     except Exception as e:
        #         logger.warning(f"树状思考系统初始化失败: {e}")
        #         self.tree_thinking = None
        # else:
        #     # 如果子系统已经初始化过，创建新实例但不重新初始化子系统（静默处理）
        #     try:
        #         self.tree_thinking = TreeThinkingEngine(api_client=self, memory_manager=self.memory_manager)
        #     except Exception as e:
        #         logger.warning(f"树状思考系统实例创建失败: {e}")
        #         self.tree_thinking = None

        # self.loop = asyncio.get_event_loop()  # 已废弃，不再使用

    def _init_agent_server_client(self):
        """初始化Agent Server客户端"""
        try:
            import aiohttp
            self.agent_server_client = aiohttp.ClientSession()
            logger.info("Agent Server客户端初始化成功")
        except Exception as e:
            logger.warning(f"Agent Server客户端初始化失败: {e}")
            self.agent_server_client = None

    async def _call_agent_server_analyze(self, messages: List[Dict[str, str]], session_id: str) -> Dict[str, Any]:
        """调用Agent Server进行意图分析"""
        try:
            if not self.agent_server_client:
                return {"has_tasks": False, "reason": "Agent Server客户端未初始化", "tasks": [], "priority": "low"}
            
            # 调用Agent Server的意图分析接口
            url = "http://localhost:8001/analyze_and_plan"
            payload = {
                "messages": messages,
                "session_id": session_id
            }
            
            async with self.agent_server_client.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("success"):
                        # 返回分析结果（这里需要根据实际API调整）
                        return {
                            "has_tasks": True,
                            "reason": "Agent Server分析完成",
                            "tasks": [],  # 实际任务由Agent Server后台处理
                            "priority": "medium"
                        }
                    else:
                        return {"has_tasks": False, "reason": "Agent Server分析失败", "tasks": [], "priority": "low"}
                else:
                    logger.error(f"Agent Server调用失败: {response.status}")
                    return {"has_tasks": False, "reason": f"HTTP错误: {response.status}", "tasks": [], "priority": "low"}
                    
        except Exception as e:
            logger.error(f"调用Agent Server失败: {e}")
            return {"has_tasks": False, "reason": f"调用失败: {e}", "tasks": [], "priority": "low"}

    def _load_persistent_context(self):
        """从日志文件加载历史对话上下文"""
        if not config.api.context_parse_logs:
            return
            
        try:
            from apiserver.message_manager import message_manager
            
            # 计算最大消息数量
            max_messages = config.api.max_history_rounds * 2
            
            # 加载历史对话
            recent_messages = message_manager.load_recent_context(
                days=config.api.context_load_days,
                max_messages=max_messages
            )
            
            if recent_messages:
                self.messages = recent_messages
                logger.info(f"✅ 从日志文件加载了 {len(self.messages)} 条历史对话")
                
                # 显示统计信息
                try:
                    from apiserver.message_manager import parser
                    stats = parser.get_context_statistics(config.api.context_load_days)
                    logger.info(f"📊 上下文统计: {stats['total_files']}个文件, {stats['total_messages']}条消息")
                except ImportError:
                    logger.info("📊 上下文统计: 日志解析器不可用")
            else:
                logger.info("📝 未找到历史对话记录，将开始新的对话")
                
        except ImportError:
            logger.warning("⚠️ 日志解析器模块未找到，跳过持久化上下文加载")
        except Exception as e:
            logger.error(f"❌ 加载持久化上下文失败: {e}")
            # 失败时不影响正常使用，继续使用空上下文

    def _init_mcp_services(self):
        """初始化MCP服务系统（只在首次初始化时输出日志，后续静默）"""
        if SystemState._mcp_services_initialized:
            # 静默跳过，不输出任何日志
            return
        try:
            # 自动注册所有MCP服务和handoff
            self.mcp.auto_register_services()
            logger.info("MCP服务系统初始化完成")
            SystemState._mcp_services_initialized = True
            
            # 异步启动NagaPortal自动登录
            self._start_naga_portal_auto_login()
            
            # 异步启动物联网通讯连接状态检查
            self._start_mqtt_status_check()
        except Exception as e:
            logger.error(f"MCP服务系统初始化失败: {e}")
    
    def _start_naga_portal_auto_login(self):
        """启动NagaPortal自动登录（异步）"""
        try:
            # 检查是否配置了NagaPortal
            if not config.naga_portal.username or not config.naga_portal.password:
                return  # 静默跳过，不输出日志
            
            # 在新线程中异步执行登录
            def run_auto_login():
                try:
                    import sys
                    import os
                    # 添加项目根目录到Python路径
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    sys.path.insert(0, project_root)
                    
                    from mcpserver.agent_naga_portal.portal_login_manager import auto_login_naga_portal
                    
                    # 创建新的事件循环
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    try:
                        # 执行自动登录
                        result = loop.run_until_complete(auto_login_naga_portal())
                        
                        if result['success']:
                            # 登录成功，显示状态
                            print("✅ NagaPortal自动登录成功")
                            self._show_naga_portal_status()
                        else:
                            # 登录失败，显示错误
                            error_msg = result.get('message', '未知错误')
                            print(f"❌ NagaPortal自动登录失败: {error_msg}")
                            self._show_naga_portal_status()
                    finally:
                        loop.close()
                        
                except Exception as e:
                    # 登录异常，显示错误
                    print(f"❌ NagaPortal自动登录异常: {e}")
                    self._show_naga_portal_status()
            
            # 启动后台线程
            import threading
            login_thread = threading.Thread(target=run_auto_login, daemon=True)
            login_thread.start()
            
        except Exception as e:
            # 启动异常，显示错误
            print(f"❌ NagaPortal自动登录启动失败: {e}")
            self._show_naga_portal_status()

    def _show_naga_portal_status(self):
        """显示NagaPortal状态（登录完成后调用）"""
        try:
            from mcpserver.agent_naga_portal.portal_login_manager import get_portal_login_manager
            login_manager = get_portal_login_manager()
            status = login_manager.get_status()
            cookies = login_manager.get_cookies()
            
            print(f"🌐 NagaPortal状态:")
            print(f"   地址: {config.naga_portal.portal_url}")
            print(f"   用户: {config.naga_portal.username[:3]}***{config.naga_portal.username[-3:] if len(config.naga_portal.username) > 6 else '***'}")
            
            if cookies:
                print(f"🍪 Cookie信息 ({len(cookies)}个):")
                for name, value in cookies.items():
                    print(f"   {name}: {value}")
            else:
                print(f"🍪 Cookie: 未获取到")
            
            user_id = status.get('user_id')
            if user_id:
                print(f"👤 用户ID: {user_id}")
            else:
                print(f"👤 用户ID: 未获取到")
                
            # 显示登录状态
            if status.get('is_logged_in'):
                print(f"✅ 登录状态: 已登录")
            else:
                print(f"❌ 登录状态: 未登录")
                if status.get('login_error'):
                    print(f"   错误: {status.get('login_error')}")
                    
        except Exception as e:
            print(f"🍪 NagaPortal状态获取失败: {e}")
    
    def _start_mqtt_status_check(self):
        """启动物联网通讯连接并显示状态（异步）"""
        try:
            # 检查是否配置了物联网通讯
            if not config.mqtt.enabled:
                return  # 静默跳过，不输出日志
            
            # 在新线程中异步执行物联网通讯连接
            def run_mqtt_connection():
                try:
                    import sys
                    import os
                    import time
                    # 添加项目根目录到Python路径
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    sys.path.insert(0, project_root)
                    
                    try:
                        from mqtt_tool.device_switch import device_manager
                        
                        # 尝试连接物联网设备
                        if hasattr(device_manager, 'connect'):
                            success = device_manager.connect()
                            if success:
                                print("🔗 物联网通讯状态: 已连接")
                            else:
                                print("⚠️ 物联网通讯状态: 连接失败（将在使用时重试）")
                        else:
                            print("❌ 物联网通讯功能不可用")
                            
                    except Exception as e:
                        print(f"⚠️ 物联网通讯连接失败: {e}")
                        
                except Exception as e:
                    print(f"❌ 物联网通讯连接异常: {e}")
            
            # 启动后台线程
            import threading
            mqtt_thread = threading.Thread(target=run_mqtt_connection, daemon=True)
            mqtt_thread.start()
            
        except Exception as e:
            print(f"❌ 物联网通讯连接启动失败: {e}")
    
    def save_log(self, u, a):  # 保存对话日志
        if self.dev_mode:
            return  # 开发者模式不写日志
        d = datetime.now().strftime('%Y-%m-%d')
        t = datetime.now().strftime('%H:%M:%S')
        
        # 确保日志目录存在
        log_dir = str(config.system.log_dir)  # 统一为字符串路径 #
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            logger.info(f"已创建日志目录: {log_dir}")
        
        # 保存对话日志
        log_file = os.path.join(log_dir, f"{d}.log")  # 组合日志文件路径 #
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{t}] 用户: {u}\n")
                f.write(f"[{t}] {AI_NAME}: {a}\n")
                f.write("-" * 50 + "\n")
        except Exception as e:
            logger.error(f"保存日志失败: {e}")
    
    # 已废弃的方法 - 统一使用message_manager进行消息管理
    # def add_message(self, role: str, content: str):
    #     """添加消息到对话历史 - 已废弃，使用message_manager"""
    #     pass

    # async def _call_llm(self, messages: List[Dict], use_stream: bool = None) -> Dict:
    #     """调用LLM API - 已废弃，直接使用async_client"""
    #     pass

    # 工具调用循环相关方法 - 已废弃，使用流式工具调用提取器替代
    # def handle_llm_response(self, a, mcp):
    #     # 只保留普通文本流式输出逻辑 #
    #     async def text_stream():
    #         for line in a.splitlines():
    #             yield ("娜迦", line)
    #     return text_stream()

    def _format_services_for_prompt(self, available_services: dict, intent_analysis: dict = None) -> str:
        """格式化可用服务列表为prompt字符串，MCP服务和Agent服务分开，包含具体调用格式"""
        mcp_services = available_services.get("mcp_services", [])
        agent_services = available_services.get("agent_services", [])
        
        # 获取本地城市信息和当前时间
        local_city = "未知城市"
        current_time = ""
        try:
            # 从WeatherTimeAgent获取本地城市信息
            from mcpserver.agent_weather_time.agent_weather_time import WeatherTimeTool
            weather_tool = WeatherTimeTool()
            local_city = getattr(weather_tool, '_local_city', '未知城市') or '未知城市'
            
            # 获取当前时间
            from datetime import datetime
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            print(f"[DEBUG] 获取本地信息失败: {e}")
        
        # 格式化MCP服务列表，包含具体调用格式
        mcp_list = []
        for service in mcp_services:
            name = service.get("name", "")
            description = service.get("description", "")
            display_name = service.get("display_name", name)
            tools = service.get("available_tools", [])
            
            # 展示name+displayName
            if description:
                mcp_list.append(f"- {name}: {description}")
            else:
                mcp_list.append(f"- {name}")
            
            # 为每个工具显示具体调用格式
            if tools:
                for tool in tools:
                    tool_name = tool.get('name', '')
                    tool_desc = tool.get('description', '')
                    tool_example = tool.get('example', '')
                    
                    if tool_name and tool_example:
                        # 解析示例JSON，提取参数
                        try:
                            import json
                            example_data = json.loads(tool_example)
                            params = []
                            for key, value in example_data.items():
                                if key != 'tool_name':
                                    params.append(f"{key}: {value}")  # 不再需要对天气进行特殊处理
                            
                            # 构建调用格式
                            format_str = f"  {tool_name}: ｛\n"
                            format_str += f"    \"agentType\": \"mcp\",\n"
                            format_str += f"    \"service_name\": \"{name}\",\n"
                            format_str += f"    \"tool_name\": \"{tool_name}\",\n"
                            for param in params:
                                # 将中文参数名转换为英文
                                param_key, param_value = param.split(': ', 1)
                                format_str += f"    \"{param_key}\": \"{param_value}\",\n"
                            format_str += f"  ｝\n"
                            
                            mcp_list.append(format_str)
                        except:
                            # 如果JSON解析失败，使用简单格式
                            mcp_list.append(f"  {tool_name}: 使用tool_name参数调用")
        
        # 格式化Agent服务列表
        agent_list = []
        
        # 1. 添加handoff服务
        for service in agent_services:
            name = service.get("name", "")
            description = service.get("description", "")
            tool_name = service.get("tool_name", "agent")
            display_name = service.get("display_name", name)
            # 展示name+displayName
            if description:
                agent_list.append(f"- {name}(工具名: {tool_name}): {description}")
            else:
                agent_list.append(f"- {name}(工具名: {tool_name})")
        
        # 2. 直接从AgentManager获取已注册的Agent
        try:
            from agentserver.core.agent_manager import get_agent_manager
            agent_manager = get_agent_manager()
            agent_manager_agents = agent_manager.get_available_agents()
            
            for agent in agent_manager_agents:
                name = agent.get("name", "")
                base_name = agent.get("base_name", "")
                description = agent.get("description", "")
                
                # 展示格式：base_name: 描述
                if description:
                    agent_list.append(f"- {base_name}: {description}")
                else:
                    agent_list.append(f"- {base_name}")
                    
        except Exception as e:
            # 如果AgentManager不可用，静默处理
            pass
        
        # 添加本地信息说明
        local_info = f"\n\n【当前环境信息】\n- 本地城市: {local_city}\n- 当前时间: {current_time}\n\n【使用说明】\n- 天气/时间查询时，请使用上述本地城市信息作为city参数\n- 所有时间相关查询都基于当前系统时间"
        
        # 添加意图分析结果（如果有）
        intent_info = ""
        if intent_analysis and intent_analysis.get("has_tasks", False):
            tasks = intent_analysis.get("tasks", [])
            priority = intent_analysis.get("priority", "medium")
            reason = intent_analysis.get("reason", "")
            
            intent_info = f"\n\n【意图分析结果】\n- 检测到 {len(tasks)} 个潜在任务 (优先级: {priority})\n- 分析原因: {reason}\n"
            if tasks:
                intent_info += "- 建议优先处理的任务:\n"
                for i, task in enumerate(tasks, 1):
                    intent_info += f"  {i}. {task}\n"
            intent_info += "\n【重要】如果用户请求与上述任务相关，请优先使用工具调用来执行任务，而不是仅提供建议。"
        
        # 返回格式化的服务列表
        result = {
            "available_mcp_services": "\n".join(mcp_list) + local_info + intent_info if mcp_list else "无" + local_info + intent_info,
            "available_agent_services": "\n".join(agent_list) if agent_list else "无"
        }
        
        return result

    async def process(self, u, is_voice_input=False):  # 添加is_voice_input参数
        try:
            # 开发者模式优先判断
            if u.strip().lower() == "#devmode":
                self.dev_mode = not self.dev_mode  # 切换模式
                status = "进入" if self.dev_mode else "退出"
                yield (AI_NAME, f"已{status}开发者模式")
                return

            # 只在语音输入时显示处理提示
            if is_voice_input:
                print(f"开始处理用户输入：{now()}")  # 语音转文本结束，开始处理
            
            # 异步启动意图分析（使用Agent Server）
            intent_analysis_task = None
            if not self.dev_mode and self.agent_server_client:  # 开发者模式跳过意图分析
                try:
                    # 构建分析用的消息格式
                    analysis_messages = []
                    for msg in self.messages[-5:]:  # 只分析最近5条消息
                        analysis_messages.append({
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", "")
                        })
                    # 添加当前用户消息
                    analysis_messages.append({
                        "role": "user", 
                        "content": u
                    })
                    
                    # 异步启动意图分析（通过Agent Server）
                    intent_analysis_task = asyncio.create_task(
                        self._call_agent_server_analyze(analysis_messages, "main_session")
                    )
                    print(f"🧠 启动意图分析：{now()}")
                except Exception as e:
                    logger.debug(f"意图分析启动失败: {e}")
                    intent_analysis_task = None
                     
            # 获取过滤后的服务列表
            available_services = self.mcp.get_available_services_filtered()
            
            # 检查意图分析是否完成
            intent_analysis = None
            if intent_analysis_task and intent_analysis_task.done():
                try:
                    intent_analysis = intent_analysis_task.result()
                    print(f"🧠 意图分析完成：{now()}")
                    if intent_analysis.get("has_tasks", False):
                        tasks = intent_analysis.get("tasks", [])
                        print(f"   发现 {len(tasks)} 个潜在任务")
                except Exception as e:
                    logger.debug(f"获取意图分析结果失败: {e}")
            
            services_text = self._format_services_for_prompt(available_services, intent_analysis)
            
            # 添加handoff提示词 - 先获取服务信息再格式化
            system_prompt = get_prompt("naga_system_prompt", ai_name=AI_NAME, **services_text)
            
            # 使用消息管理器统一的消息拼接逻辑（UI界面使用）
            from apiserver.message_manager import message_manager
            msgs = message_manager.build_conversation_messages_from_memory(
                memory_messages=self.messages,
                system_prompt=system_prompt,
                current_message=u,
                max_history_rounds=config.api.max_history_rounds
            )

            print(f"GTP请求发送：{now()}")  # AI请求前
            
            # 禁用非线性思考判断
            # thinking_task = None
            # if hasattr(self, 'tree_thinking') and self.tree_thinking and getattr(self.tree_thinking, 'is_enabled', False):
            #     # 启动异步思考判断任务
            #     import asyncio
            #     thinking_task = asyncio.create_task(self._async_thinking_judgment(u))
            
            # 流式处理：实时检测工具调用，使用统一的工具调用循环
            try:
                # 导入流式工具调用提取器
                from apiserver.streaming_tool_extractor import StreamingToolCallExtractor
                import queue
                
                # 创建工具调用队列
                tool_calls_queue = queue.Queue()
                tool_extractor = StreamingToolCallExtractor(self.mcp)
                
                # 用于累积前端显示的纯文本（不包含工具调用）
                display_text = ""
                
                # 设置回调函数
                def on_text_chunk(text: str, chunk_type: str):
                    """处理文本块 - 发送到前端显示"""
                    if chunk_type == "chunk":
                        nonlocal display_text
                        display_text += text
                        return (AI_NAME, text)
                    return None
                
                def on_sentence(sentence: str, sentence_type: str):
                    """处理完整句子"""
                    if sentence_type == "sentence":
                        print(f"完成句子: {sentence}")
                    return None
                
                def on_tool_result(result: str, result_type: str):
                    """处理工具结果 - 不发送到前端"""
                    if result_type == "tool_result":
                        print(f"✅ 工具执行完成: {result[:100]}...")
                    elif result_type == "tool_error":
                        print(f"❌ 工具执行错误: {result}")
                    return None
                
                # 设置回调
                tool_extractor.set_callbacks(
                    on_text_chunk=on_text_chunk,
                    on_sentence=on_sentence,
                    on_tool_result=on_tool_result,
                    tool_calls_queue=tool_calls_queue
                )
                
                # 调用LLM API - 流式模式
                resp = await self.async_client.chat.completions.create(
                    model=config.api.model,
                    messages=msgs,
                    temperature=config.api.temperature,
                    max_tokens=config.api.max_tokens,
                    stream=True
                )
                
                # 处理流式响应
                async for chunk in resp:
                    # 原始增量日志（AI 原始输出）
                    try:
                        delta = getattr(chunk.choices[0], 'delta', None) if chunk.choices else None
                        if delta is not None:
                            logger.info("openai.delta: %r", getattr(delta, 'content', None))
                    except Exception:
                        pass

                    # 安全检查：确保chunk.choices不为空且有内容
                    if (chunk.choices and 
                        len(chunk.choices) > 0 and 
                        hasattr(chunk.choices[0], 'delta') and 
                        chunk.choices[0].delta.content):
                        content = chunk.choices[0].delta.content
                        # 使用流式工具调用提取器处理内容
                        results = await tool_extractor.process_text_chunk(content)
                        if results:
                            for result in results:
                                if isinstance(result, tuple) and len(result) == 2:
                                    yield result
                                elif isinstance(result, str):
                                    yield (AI_NAME, result)
                
                # 完成处理
                final_results = await tool_extractor.finish_processing()
                if final_results:
                    for result in final_results:
                        if isinstance(result, tuple) and len(result) == 2:
                            yield result
                        elif isinstance(result, str):
                            yield (AI_NAME, result)
                
                # 检查是否有工具调用需要处理
                if not tool_calls_queue.empty():
                    # 使用统一的工具调用循环处理
                    async def llm_caller(messages, use_stream=False):
                        """LLM调用函数，用于工具调用循环"""
                        # 这里不需要实际调用LLM，因为工具调用已经提取完成
                        return {'content': '', 'status': 'success'}
                    
                    # 使用工具调用循环处理工具调用
                    result = await tool_call_loop(msgs, self.mcp, llm_caller, is_streaming=True, tool_calls_queue=tool_calls_queue)
                    
                    if result.get('has_tool_results'):
                        # 有工具执行结果，让LLM继续处理
                        tool_results = result['content']
                        
                        # 构建包含工具结果的消息（使用统一的消息拼接逻辑）
                        tool_messages = message_manager.build_conversation_messages_from_memory(
                            memory_messages=self.messages,
                            system_prompt=system_prompt,
                            current_message=f"工具执行结果：{tool_results}",
                            max_history_rounds=config.api.max_history_rounds
                        )
                        
                        # 调用LLM继续处理工具结果
                        try:
                            resp2 = await self.async_client.chat.completions.create(
                                model=config.api.model,
                                messages=tool_messages,
                                temperature=config.api.temperature,
                                max_tokens=config.api.max_tokens,
                                stream=True
                            )
                            
                            # 处理LLM的继续响应 - 也需要通过流式工具调用提取器处理
                            async for chunk in resp2:
                                # 安全检查：确保chunk.choices不为空且有内容
                                if (chunk.choices and 
                                    len(chunk.choices) > 0 and 
                                    hasattr(chunk.choices[0], 'delta') and 
                                    chunk.choices[0].delta.content):
                                    content = chunk.choices[0].delta.content
                                    # 使用流式工具调用提取器处理内容
                                    results = await tool_extractor.process_text_chunk(content)
                                    if results:
                                        for result in results:
                                            if isinstance(result, tuple) and len(result) == 2:
                                                yield result
                                            elif isinstance(result, str):
                                                yield (AI_NAME, result)
                                    
                                    # 注意：文本内容通过 on_text_chunk 回调函数已经累积到 display_text 中
                        except Exception as e:
                            print(f"LLM继续处理工具结果失败: {e}")
                
                # 完成所有处理，获取最终的纯文本内容
                final_results = await tool_extractor.finish_processing()
                if final_results:
                    for result in final_results:
                        if isinstance(result, tuple) and len(result) == 2:
                            yield result
                        elif isinstance(result, str):
                            yield (AI_NAME, result)
                
                # 等待意图分析完成（最多等待2秒）
                if intent_analysis_task and not intent_analysis_task.done():
                    try:
                        await asyncio.wait_for(intent_analysis_task, timeout=2.0)
                        final_intent_analysis = intent_analysis_task.result()
                        if final_intent_analysis.get("has_tasks", False):
                            tasks = final_intent_analysis.get("tasks", [])
                            print(f"🧠 意图分析最终结果：发现 {len(tasks)} 个潜在任务")
                    except asyncio.TimeoutError:
                        print(f"🧠 意图分析超时，继续处理")
                    except Exception as e:
                        logger.debug(f"等待意图分析完成失败: {e}")
                
                # 保存对话历史（使用前端显示的纯文本）
                print(f"[DEBUG] 最终display_text长度: {len(display_text)}")
                print(f"[DEBUG] 最终display_text内容: {display_text[:200]}...")
                self.messages += [{"role": "user", "content": u}, {"role": "assistant", "content": display_text}]
                self.save_log(u, display_text)
                
                # GRAG记忆存储（开发者模式不写入）- 使用前端显示的纯文本
                if self.memory_manager and not self.dev_mode:
                    try:
                        # 使用前端显示的纯文本进行五元组提取
                        await self.memory_manager.add_conversation_memory(u, display_text)
                    except Exception as e:
                        logger.error(f"GRAG记忆存储失败: {e}")
                
                # 禁用异步思考判断结果检查
                # if thinking_task and not thinking_task.done():
                #     # 等待思考判断完成（最多等待3秒）
                #     try:
                #         await asyncio.wait_for(thinking_task, timeout=3.0)
                #         if thinking_task.result():
                #             yield ("娜迦", "\n💡 这个问题较为复杂，下面我会更详细地解释这个流程...")
                #             # 启动深度思考
                #             try:
                #                 thinking_result = await self.tree_thinking.think_deeply(u)
                #                 if thinking_result and "answer" in thinking_result:
                #                     # 直接使用thinking系统的结果，避免重复处理
                #                     yield ("娜迦", f"\n{thinking_result['answer']}")
                #                     
                #                     # 更新对话历史
                #                     final_thinking_answer = thinking_result['answer']
                #                     self.messages[-1] = {"role": "assistant", "content": final_content + "\n\n" + final_thinking_answer}
                #                     self.save_log(u, final_content + "\n\n" + final_thinking_answer)
                #                     
                #                     # GRAG记忆存储（开发者模式不写入）
                #                     if self.memory_manager and not self.dev_mode:
                #                         try:
                #                             await self.memory_manager.add_conversation_memory(u, final_content + "\n\n" + final_thinking_answer)
                #                         except Exception as e:
                #                             logger.error(f"GRAG记忆存储失败: {e}")
                #             except Exception as e:
                #                 logger.error(f"深度思考处理失败: {e}")
                #                 yield ("娜迦", f"🌳 深度思考系统出错: {str(e)}")
                #     except asyncio.TimeoutError:
                #         # 超时取消任务
                #         thinking_task.cancel()
                #     except Exception as e:
                #         logger.debug(f"思考判断任务异常: {e}")
                
            except Exception as e:
                print(f"工具调用循环失败: {e}")
                # 区分API错误和MCP错误
                if "API" in str(e) or "api" in str(e) or "HTTP" in str(e) or "连接" in str(e):
                    yield (AI_NAME, f"[API调用异常]: {e}")
                else:
                    yield (AI_NAME, f"[MCP服务异常]: {e}")
                return

            return
        except Exception as e:
            import sys
            import traceback
            traceback.print_exc(file=sys.stderr)
            # 区分API错误和MCP错误
            if "API" in str(e) or "api" in str(e) or "HTTP" in str(e) or "连接" in str(e):
                yield (AI_NAME, f"[API调用异常]: {e}")
            else:
                yield (AI_NAME, f"[MCP服务异常]: {e}")
            return

    async def get_response(self, prompt: str, temperature: float = 0.7) -> str:
        """为树状思考系统等提供API调用接口""" # 统一接口
        try:
            response = await self.async_client.chat.completions.create(
                model=config.api.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=config.api.max_tokens
            )
            return response.choices[0].message.content
        except RuntimeError as e:
            if "handler is closed" in str(e):
                logger.debug(f"忽略连接关闭异常，重新创建客户端: {e}")
                # 重新创建客户端并重试
                self.async_client = AsyncOpenAI(api_key=config.api.api_key, base_url=config.api.base_url.rstrip('/') + '/')
                response = await self.async_client.chat.completions.create(
                    model=config.api.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=config.api.max_tokens
                )
                return response.choices[0].message.content
            else:
                logger.error(f"API调用失败: {e}")
                return f"API调用出错: {str(e)}"
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return f"API调用出错: {str(e)}"

    # async def _async_thinking_judgment(self, question: str) -> bool:
    #     """异步判断问题是否需要深度思考
        
    #     Args:
    #         question: 用户问题
            
    #     Returns:
    #         bool: 是否需要深度思考
    #     """
    #     try:
    #         if not self.tree_thinking:
    #             return False
            
    #         # 使用thinking文件夹中现成的难度判断器
    #         difficulty_assessment = await self.tree_thinking.difficulty_judge.assess_difficulty(question)
    #         difficulty = difficulty_assessment.get("difficulty", 3)
            
    #         # 根据难度判断是否需要深度思考
    #         # 难度4-5（复杂/极难）建议深度思考
    #         should_think_deeply = difficulty >= 4
            
    #         logger.info(f"难度判断：{difficulty}/5，建议深度思考：{should_think_deeply}")
    #         return should_think_deeply
                   
    #     except Exception as e:
    #         logger.debug(f"异步思考判断失败: {e}")
    #         return False

async def process_user_message(s,msg):
    if config.system.voice_enabled and not msg: #无文本输入时启动语音识别
        async for text in s.voice.stt_stream():
            if text:
                msg=text
                break
        return await s.process(msg, is_voice_input=True)  # 语音输入
    return await s.process(msg, is_voice_input=False)  # 文字输入
