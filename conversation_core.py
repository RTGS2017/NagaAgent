import asyncio
import logging
import os
# import asyncio # 日志与系统
from datetime import datetime # 时间
from mcpserver.mcp_manager import get_mcp_manager # 多功能管理
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX # handoff提示词
# from mcpserver.agent_playwright_master import ControllerAgent, BrowserAgent, ContentAgent # 导入浏览器相关类
from openai import OpenAI,AsyncOpenAI # LLM
# import difflib # 模糊匹配
import sys
import json
import traceback
import time # 时间戳打印
import re # 添加re模块导入
from typing import List, Dict # 修复List未导入
# 恢复树状思考系统导入
from thinking import TreeThinkingEngine # 树状思考引擎
from thinking.config import COMPLEX_KEYWORDS # 复杂关键词
from config import config
# 导入独立的工具调用模块
from apiserver.tool_call_utils import parse_tool_calls, execute_tool_calls, tool_call_loop

# GRAG记忆系统导入
if config.grag.enabled:
    try:
        from summer_memory.memory_manager import memory_manager
        print("[GRAG] ✅ 夏园记忆系统初始化成功")
    except Exception as e:
        logger = logging.getLogger("NagaConversation")
        logger.error(f"夏园记忆系统加载失败: {e}")
        memory_manager = None
else:
    memory_manager = None

def now():
    return time.strftime('%H:%M:%S:')+str(int(time.time()*1000)%10000) # 当前时间
_builtin_print=print
def print(*a, **k):
    return sys.stderr.write('[print] '+(' '.join(map(str,a)))+'\n')

# 配置日志 - 使用统一配置系统的日志级别
log_level = getattr(logging, config.system.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

# 特别设置httpcore和openai的日志级别，减少连接异常噪音
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)  # 屏蔽HTTP请求DEBUG
logging.getLogger("httpx").setLevel(logging.WARNING)  # 屏蔽httpx DEBUG
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
# 隐藏asyncio的DEBUG日志
logging.getLogger("asyncio").setLevel(logging.WARNING)
logger = logging.getLogger("NagaConversation")

# _MCP_HANDOFF_REGISTERED=False  # 已移除，不再需要
_TREE_THINKING_SUBSYSTEMS_INITIALIZED=False
_MCP_SERVICES_INITIALIZED=False

_VOICE_ENABLED_LOGGED=False

class NagaConversation: # 对话主类
    def __init__(self):
        self.mcp = get_mcp_manager()
        self.messages = []
        self.dev_mode = False
        self.client = OpenAI(api_key=config.api.api_key, base_url=config.api.base_url.rstrip('/') + '/')
        self.async_client = AsyncOpenAI(api_key=config.api.api_key, base_url=config.api.base_url.rstrip('/') + '/')
        
        # 初始化MCP服务系统
        self._init_mcp_services()
        
        # 初始化GRAG记忆系统（只在首次初始化时显示日志）
        self.memory_manager = memory_manager
        if self.memory_manager and not hasattr(self.__class__, '_memory_initialized'):
            logger.info("夏园记忆系统已初始化")
            self.__class__._memory_initialized = True
        
        # 初始化语音处理系统
        self.voice = None
        if config.system.voice_enabled:
            try:
                # 语音功能已迁移到voice_integration.py，由ui/enhanced_worker.py调用
                # 不再需要在这里初始化VoiceHandler
                # 使用全局变量避免重复输出日志
                global _VOICE_ENABLED_LOGGED
                if not _VOICE_ENABLED_LOGGED:
                    logger.info("语音功能已启用，由UI层管理")
                    _VOICE_ENABLED_LOGGED = True
            except Exception as e:
                logger.warning(f"语音系统初始化失败: {e}")
                self.voice = None
        
        # 恢复树状思考系统
        self.tree_thinking = None
        # 集成树状思考系统（参考handoff的全局变量保护机制）
        global _TREE_THINKING_SUBSYSTEMS_INITIALIZED
        if not _TREE_THINKING_SUBSYSTEMS_INITIALIZED:
            try:
                self.tree_thinking = TreeThinkingEngine(api_client=self, memory_manager=self.memory_manager)
                print("[TreeThinkingEngine] ✅ 树状外置思考系统初始化成功")
                _TREE_THINKING_SUBSYSTEMS_INITIALIZED = True
            except Exception as e:
                logger.warning(f"树状思考系统初始化失败: {e}")
                self.tree_thinking = None
        else:
            # 如果子系统已经初始化过，创建新实例但不重新初始化子系统（静默处理）
            try:
                self.tree_thinking = TreeThinkingEngine(api_client=self, memory_manager=self.memory_manager)
            except Exception as e:
                logger.warning(f"树状思考系统实例创建失败: {e}")
                self.tree_thinking = None

        self.loop = asyncio.get_event_loop()


    def _init_mcp_services(self):
        """初始化MCP服务系统（只在首次初始化时输出日志，后续静默）"""
        global _MCP_SERVICES_INITIALIZED
        if _MCP_SERVICES_INITIALIZED:
            # 静默跳过，不输出任何日志
            return
        try:
            # 自动注册所有MCP服务和handoff
            self.mcp.auto_register_services()
            logger.info("MCP服务系统初始化完成")
            _MCP_SERVICES_INITIALIZED = True
        except Exception as e:
            logger.error(f"MCP服务系统初始化失败: {e}")

    def save_log(self, u, a):  # 保存对话日志
        if self.dev_mode:
            return  # 开发者模式不写日志
        d = datetime.now().strftime('%Y-%m-%d')
        t = datetime.now().strftime('%H:%M:%S')
        
        # 确保日志目录存在
        log_dir = config.system.log_dir
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            logger.info(f"已创建日志目录: {log_dir}")
        
        # 保存对话日志
        log_file = os.path.join(log_dir, f"{d}.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{t}] 用户: {u}\n")
                f.write(f"[{t}] 娜迦: {a}\n")
                f.write("-" * 50 + "\n")
        except Exception as e:
            logger.error(f"保存日志失败: {e}")
    
    def add_message(self, role: str, content: str):
        """添加消息到对话历史"""
        self.messages.append({"role": role, "content": content})
        
        # 限制历史消息数量，避免内存泄漏
        max_messages = 20
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    async def _call_llm(self, messages: List[Dict]) -> Dict:
        """调用LLM API"""
        try:
            resp = await self.async_client.chat.completions.create(
                model=config.api.model, 
                messages=messages, 
                temperature=config.api.temperature, 
                max_tokens=config.api.max_tokens, 
                stream=False  # 工具调用循环中不使用流式
            )
            return {
                'content': resp.choices[0].message.content,
                'status': 'success'
            }
        except RuntimeError as e:
            if "handler is closed" in str(e):
                logger.debug(f"忽略连接关闭异常: {e}")
                # 重新创建客户端并重试
                self.async_client = AsyncOpenAI(api_key=config.api.api_key, base_url=config.api.base_url.rstrip('/') + '/')
                resp = await self.async_client.chat.completions.create(
                    model=config.api.model, 
                    messages=messages, 
                    temperature=config.api.temperature, 
                    max_tokens=config.api.max_tokens, 
                    stream=False
                )
                return {
                    'content': resp.choices[0].message.content,
                    'status': 'success'
                }
            else:
                raise
        except Exception as e:
            logger.error(f"LLM API调用失败: {e}")
            return {
                'content': f"API调用失败: {str(e)}",
                'status': 'error'
            }

    # 工具调用循环相关方法
    def handle_llm_response(self, a, mcp):
        # 只保留普通文本流式输出逻辑 #
        async def text_stream():
            for line in a.splitlines():
                yield ("娜迦", line)
        return text_stream()

    def _format_services_for_prompt(self, available_services: dict) -> str:
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
                                    # 特殊处理city参数，注入本地城市信息
                                    if key == 'city' and name == 'WeatherTimeAgent':
                                        params.append(f"{key}: {local_city}")
                                    else:
                                        params.append(f"{key}: {value}")
                            
                            # 构建调用格式
                            format_str = f"  {tool_name}: ｛\n"
                            format_str += f"    \"agentType\": \"mcp\",\n"
                            format_str += f"    \"service_name\": \"{name}\",\n"
                            format_str += f"    \"tool_name\": \"{tool_name}\",\n"
                            for param in params:
                                # 将中文参数名转换为英文
                                param_key, param_value = param.split(': ', 1)
                                if param_key == 'city' and name == 'WeatherTimeAgent':
                                    format_str += f"    \"{param_key}\": \"{local_city}\",\n"
                                else:
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
            from mcpserver.agent_manager import get_agent_manager
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
        
        # 返回格式化的服务列表
        result = {
            "available_mcp_services": "\n".join(mcp_list) + local_info if mcp_list else "无" + local_info,
            "available_agent_services": "\n".join(agent_list) if agent_list else "无"
        }
        
        return result

    async def process(self, u, is_voice_input=False):  # 添加is_voice_input参数
        try:
            # 开发者模式优先判断
            if u.strip().lower() == "#devmode":
                self.dev_mode = not self.dev_mode  # 切换模式
                status = "进入" if self.dev_mode else "退出"
                yield ("娜迦", f"已{status}开发者模式")
                return

            # 只在语音输入时显示处理提示
            if is_voice_input:
                print(f"开始处理用户输入：{now()}")  # 语音转文本结束，开始处理
            
            # 完全禁用GRAG记忆查询
            # GRAG记忆查询
            # memory_context = ""
            # if self.memory_manager:
            #     try:
            #         memory_result = await self.memory_manager.query_memory(u)
            #         if memory_result:
            #             # memory_context = f"\n[记忆检索结果]: {memory_result}\n"
            #             logger.info("从GRAG记忆中检索到相关信息")
            #     except Exception as e:
            #         logger.error(f"GRAG记忆查询失败: {e}")
            
            # 添加handoff提示词
            system_prompt = f"{RECOMMENDED_PROMPT_PREFIX}\n{config.prompts.naga_system_prompt}"
            
            # 获取过滤后的服务列表
            available_services = self.mcp.get_available_services_filtered()
            services_text = self._format_services_for_prompt(available_services)
            
            # 简化的消息拼接逻辑（UI界面使用）
            sysmsg = {"role": "system", "content": system_prompt.format(**services_text)}
            msgs = [sysmsg] if sysmsg else []
            msgs += self.messages[-20:] + [{"role": "user", "content": u}]

            print(f"GTP请求发送：{now()}")  # AI请求前
            
            # 非线性思考判断：启动后台异步判断任务
            thinking_task = None
            if hasattr(self, 'tree_thinking') and self.tree_thinking and getattr(self.tree_thinking, 'is_enabled', False):
                # 启动异步思考判断任务
                import asyncio
                thinking_task = asyncio.create_task(self._async_thinking_judgment(u))
            
            # 普通模式：走工具调用循环（根据配置决定是否流式）
            try:
                # 根据配置决定是否使用流式处理
                is_streaming = config.system.stream_mode
                result = await tool_call_loop(msgs, self.mcp, self._call_llm, is_streaming=is_streaming)
                final_content = result['content']
                recursion_depth = result['recursion_depth']
                
                if recursion_depth > 0:
                    print(f"工具调用循环完成，共执行 {recursion_depth} 轮")
                
                # 根据配置决定输出方式
                if is_streaming:
                    # 流式输出最终结果
                    for line in final_content.splitlines():
                        yield ("娜迦", line)
                else:
                    # 非流式输出完整结果
                    yield ("娜迦", final_content)
                
                # 保存对话历史
                self.messages += [{"role": "user", "content": u}, {"role": "assistant", "content": final_content}]
                self.save_log(u, final_content)
                
                # GRAG记忆存储（开发者模式不写入）
                if self.memory_manager and not self.dev_mode:
                    try:
                        await self.memory_manager.add_conversation_memory(u, final_content)
                    except Exception as e:
                        logger.error(f"GRAG记忆存储失败: {e}")
                
                # 检查异步思考判断结果，如果建议深度思考则提示用户
                if thinking_task and not thinking_task.done():
                    # 等待思考判断完成（最多等待3秒）
                    try:
                        await asyncio.wait_for(thinking_task, timeout=3.0)
                        if thinking_task.result():
                            yield ("娜迦", "\n💡 这个问题较为复杂，下面我会更详细地解释这个流程...")
                            # 启动深度思考
                            try:
                                thinking_result = await self.tree_thinking.think_deeply(u)
                                if thinking_result and "answer" in thinking_result:
                                    # 直接使用thinking系统的结果，避免重复处理
                                    yield ("娜迦", f"\n{thinking_result['answer']}")
                                    
                                    # 更新对话历史
                                    final_thinking_answer = thinking_result['answer']
                                    self.messages[-1] = {"role": "assistant", "content": final_content + "\n\n" + final_thinking_answer}
                                    self.save_log(u, final_content + "\n\n" + final_thinking_answer)
                                    
                                    # GRAG记忆存储（开发者模式不写入）
                                    if self.memory_manager and not self.dev_mode:
                                        try:
                                            await self.memory_manager.add_conversation_memory(u, final_content + "\n\n" + final_thinking_answer)
                                        except Exception as e:
                                            logger.error(f"GRAG记忆存储失败: {e}")
                            except Exception as e:
                                logger.error(f"深度思考处理失败: {e}")
                                yield ("娜迦", f"🌳 深度思考系统出错: {str(e)}")
                    except asyncio.TimeoutError:
                        # 超时取消任务
                        thinking_task.cancel()
                    except Exception as e:
                        logger.debug(f"思考判断任务异常: {e}")
                
            except Exception as e:
                print(f"工具调用循环失败: {e}")
                yield ("娜迦", f"[MCP异常]: {e}")
                return

            return
        except Exception as e:
            import sys
            import traceback
            traceback.print_exc(file=sys.stderr)
            yield ("娜迦", f"[MCP异常]: {e}")
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

    async def _async_thinking_judgment(self, question: str) -> bool:
        """异步判断问题是否需要深度思考
        
        Args:
            question: 用户问题
            
        Returns:
            bool: 是否需要深度思考
        """
        try:
            if not self.tree_thinking:
                return False
            
            # 使用thinking文件夹中现成的难度判断器
            difficulty_assessment = await self.tree_thinking.difficulty_judge.assess_difficulty(question)
            difficulty = difficulty_assessment.get("difficulty", 3)
            
            # 根据难度判断是否需要深度思考
            # 难度4-5（复杂/极难）建议深度思考
            should_think_deeply = difficulty >= 4
            
            logger.info(f"难度判断：{difficulty}/5，建议深度思考：{should_think_deeply}")
            return should_think_deeply
                   
        except Exception as e:
            logger.debug(f"异步思考判断失败: {e}")
            return False

async def process_user_message(s,msg):
    if config.system.voice_enabled and not msg: #无文本输入时启动语音识别
        async for text in s.voice.stt_stream():
            if text:
                msg=text
                break
        return await s.process(msg, is_voice_input=True)  # 语音输入
    return await s.process(msg, is_voice_input=False)  # 文字输入
