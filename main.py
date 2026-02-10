# pyinstaller适配
import os
import sys
import subprocess
# Windows 控制台 UTF-8，避免打印 emoji/中文 时 UnicodeEncodeError
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        else:
            import io
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
if os.path.exists("_internal"):
    os.chdir("_internal")

# 打包库识别适配

# 检测是否在打包环境中
# PyInstaller打包后的程序会设置sys.frozen属性
IS_PACKAGED = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

# 标准库导入
import asyncio
import logging
import socket
import threading
import time
import warnings
import requests

# 过滤弃用警告，提升启动体验
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*websockets.legacy.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*WebSocketServerProtocol.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*websockets.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*uvicorn.*")

# 修复Windows socket兼容性问题
if not hasattr(socket, 'EAI_ADDRFAMILY'):
    # Windows系统缺少这些错误码，添加兼容性常量
    socket.EAI_ADDRFAMILY = -9
    socket.EAI_AGAIN = -3
    socket.EAI_BADFLAGS = -1
    socket.EAI_FAIL = -4
    socket.EAI_MEMORY = -10
    socket.EAI_NODATA = -5
    socket.EAI_NONAME = -2
    socket.EAI_OVERFLOW = -12
    socket.EAI_SERVICE = -8
    socket.EAI_SOCKTYPE = -7
    socket.EAI_SYSTEM = -11

# 本地模块导入
from system.system_checker import run_system_check, run_quick_check
from system.config import config, AI_NAME

# V14版本已移除早期拦截器，采用运行时猴子补丁

# conversation_core已删除，相关功能已迁移到apiserver
from summer_memory.memory_manager import memory_manager
from summer_memory.task_manager import task_manager

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("summer_memory")
logger.setLevel(logging.INFO)

# 过滤HTTP相关日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# 优化Live2D相关日志输出，减少启动时的信息噪音
logging.getLogger("live2d").setLevel(logging.WARNING)  # Live2D库日志
logging.getLogger("live2d.renderer").setLevel(logging.WARNING)  # 渲染器日志
logging.getLogger("live2d.animator").setLevel(logging.WARNING)  # 动画器日志
logging.getLogger("live2d.widget").setLevel(logging.WARNING)  # 组件日志
logging.getLogger("live2d.config").setLevel(logging.WARNING)  # 配置日志
logging.getLogger("live2d.config_dialog").setLevel(logging.WARNING)  # 配置对话框日志
logging.getLogger("OpenGL").setLevel(logging.WARNING)  # OpenGL日志
logging.getLogger("OpenGL.acceleratesupport").setLevel(logging.WARNING)  # OpenGL加速日志

# 服务管理器类
class ServiceManager:
    """服务管理器 - 统一管理所有后台服务"""
    
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.bg_thread = None
        self.api_thread = None
        self.agent_thread = None
        self.tts_thread = None
        self._services_ready = False  # 服务就绪状态
    
    def start_background_services(self):
        """启动后台服务 - 异步非阻塞"""
        # 启动后台任务管理器
        self.bg_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.bg_thread.start()
        logger.info(f"后台服务线程已启动: {self.bg_thread.name}")
        
        # 移除阻塞等待，改为异步检查
        # time.sleep(1)  # 删除阻塞等待
    
    def _run_event_loop(self):
        """运行事件循环"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._init_background_services())
        logger.info("后台服务事件循环已启动")
    
    async def _init_background_services(self):
        """初始化后台服务 - 优化启动流程"""
        logger.info("正在启动后台服务...")
        try:
            # 任务管理器由memory_manager自动启动，无需手动启动
            # await start_task_manager()
            
            # 标记服务就绪
            self._services_ready = True
            logger.info(f"任务管理器状态: running={task_manager.is_running}")
            
            # 保持事件循环活跃
            while True:
                await asyncio.sleep(3600)  # 每小时检查一次
        except Exception as e:
            logger.error(f"后台服务异常: {e}")
    
    def check_port_available(self, host, port):
        """检查端口是否可用"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((host, port))
                return True
        except OSError:
            return False
    
    def start_all_servers(self):
        """并行启动所有服务：API(可选)、Agent、TTS（MCP/MQTT 已从启动流程中排除）"""
        print("🚀 正在并行启动所有服务...")
        print("=" * 50)
        threads = []
        service_status = {}  # 服务状态跟踪
        
        try:
            self._init_proxy_settings()
            # 预检查所有端口，减少重复检查（不含 MCP）
            from system.config import get_server_port
            port_checks = {
                'api': config.api_server.enabled and config.api_server.auto_start and 
                      self.check_port_available(config.api_server.host, config.api_server.port),
                # 'mcp': 已禁用，不再在 main 启动流程中启动 MCP
                'agent': self.check_port_available("0.0.0.0", get_server_port("agent_server")),
                'tts': self.check_port_available("0.0.0.0", config.tts.port)
            }
            
            # API服务器（可选）
            if port_checks['api']:
                api_thread = threading.Thread(target=self._start_api_server, daemon=True)
                threads.append(("API", api_thread))
                service_status['API'] = "准备启动"
            elif config.api_server.enabled and config.api_server.auto_start:
                print(f"⚠️  API服务器: 端口 {config.api_server.port} 已被占用，跳过启动")
                service_status['API'] = "端口占用"

            # MCP服务器（已禁用：不再在 main 启动流程中启动）
            # if port_checks['mcp']:
            #     mcp_thread = threading.Thread(target=self._start_mcp_server, daemon=True)
            #     threads.append(("MCP", mcp_thread))
            #     service_status['MCP'] = "准备启动"
            # else:
            #     print(f"⚠️  MCP服务器: 端口 {get_server_port('mcp_server')} 已被占用，跳过启动")
            #     service_status['MCP'] = "端口占用"

            # Agent服务器
            if port_checks['agent']:
                agent_thread = threading.Thread(target=self._start_agent_server, daemon=True)
                threads.append(("Agent", agent_thread))
                service_status['Agent'] = "准备启动"
            else:
                print(f"⚠️  Agent服务器: 端口 {get_server_port('agent_server')} 已被占用，跳过启动")
                service_status['Agent'] = "端口占用"

            # TTS服务器
            if port_checks['tts']:
                tts_thread = threading.Thread(target=self._start_tts_server, daemon=True)
                threads.append(("TTS", tts_thread))
                service_status['TTS'] = "准备启动"
            else:
                print(f"⚠️  TTS服务器: 端口 {config.tts.port} 已被占用，跳过启动")
                service_status['TTS'] = "端口占用"
            
            # 显示服务启动计划
            print("\n📋 服务启动计划:")
            for service, status in service_status.items():
                if status == "准备启动":
                    print(f"   🔄 {service}服务器: 正在启动...")
                else:
                    print(f"   ⚠️  {service}服务器: {status}")
            
            print("\n🚀 开始启动服务...")
            print("-" * 30)

            # 批量启动所有线程
            for name, thread in threads:
                thread.start()
                print(f"✅ {name}服务器: 启动线程已创建")

            # 等待所有服务启动（给服务器启动时间）
            print("⏳ 等待服务初始化...")
            time.sleep(2)

            print("-" * 30)
            print(f"🎉 服务启动完成: {len(threads)} 个服务正在运行")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ 并行启动服务异常: {e}")

    def _init_proxy_settings(self):
        """初始化代理设置：若不启用代理，则清空系统代理环境变量"""
        # 检测 applied_proxy 状态
        if not config.api.applied_proxy:  # 当 applied_proxy 为 False 时
            print("检测到不启用代理，正在清空系统代理环境变量...")

            # 清空 HTTP/HTTPS 代理环境变量（跨平台兼容）
            proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
            for var in proxy_vars:
                if var in os.environ:
                    del os.environ[var]  # 删除环境变量
                    print(f"已清除代理环境变量: {var}")

            # 额外：确保 requests Session 没有全局代理配置
            global_session = requests.Session()
            if global_session.proxies:
                global_session.proxies.clear()
                print("已清空 requests Session 全局代理配置")
    def _start_api_server(self):
        """内部API服务器启动方法"""
        try:
            import asyncio
            import uvicorn
            from apiserver.api_server import app

            print(f"   🚀 API服务器: 正在启动 on {config.api_server.host}:{config.api_server.port}...")

            uvicorn.run(
                app,
                host=config.api_server.host,
                port=config.api_server.port,
                log_level="info",
                access_log=False,
                reload=False,
                ws_ping_interval=None,
                ws_ping_timeout=None
            )
        except ImportError as e:
            print(f"   ❌ API服务器依赖缺失: {e}", flush=True)
        except Exception as e:
            print(f"   ❌ API服务器启动失败: {e}", flush=True)
    
    # MCP 已从启动流程中排除，不再在 main 中启动
    # def _start_mcp_server(self):
    #     """内部MCP服务器启动方法"""
    #     try:
    #         import uvicorn
    #         from mcpserver.mcp_server import app
    #         from system.config import get_server_port
    #         uvicorn.run(
    #             app,
    #             host="0.0.0.0",
    #             port=get_server_port("mcp_server"),
    #             log_level="error",
    #             access_log=False,
    #             reload=False,
    #             ws_ping_interval=None,
    #             ws_ping_timeout=None
    #         )
    #     except Exception as e:
    #         print(f"   ❌ MCP服务器启动失败: {e}")
    
    def _start_agent_server(self):
        """内部Agent服务器启动方法"""
        try:
            import uvicorn
            from agentserver.agent_server import app
            from system.config import get_server_port

            uvicorn.run(
                app,
                host="0.0.0.0",
                port=get_server_port("agent_server"),
                log_level="error",
                access_log=False,
                reload=False,
                ws_ping_interval=None,  # 禁用WebSocket ping
                ws_ping_timeout=None    # 禁用WebSocket ping超时
            )
        except Exception as e:
            import traceback
            print(f"   ❌ Agent服务器启动失败: {e}", flush=True)
            traceback.print_exc()
    
    def _start_tts_server(self):
        """内部TTS服务器启动方法"""
        try:
            from voice.output.start_voice_service import start_http_server
            start_http_server()
        except Exception as e:
            import traceback
            print(f"   ❌ TTS服务器启动失败: {e}", flush=True)
            traceback.print_exc()

    
    def _init_voice_system(self):
        """初始化语音处理系统"""
        try:
            if config.system.voice_enabled:
                logger.info("语音功能已启用（语音输入+输出），由UI层管理")
            else:
                logger.info("语音功能已禁用")
        except Exception as e:
            logger.warning(f"语音系统初始化失败: {e}")
    
    def _init_memory_system(self):
        """初始化记忆系统"""
        try:
            if memory_manager and memory_manager.enabled:
                logger.info("夏园记忆系统已初始化")
            else:
                logger.info("夏园记忆系统已禁用")
        except Exception as e:
            logger.warning(f"记忆系统初始化失败: {e}")
    
    def _init_mcp_services(self):
        """初始化MCP服务系统"""
        try:
            # MCP服务现在由mcpserver独立管理，这里只需要记录日志
            logger.info("MCP服务系统由mcpserver独立管理")
        except Exception as e:
            logger.error(f"MCP服务系统初始化失败: {e}")

# 工具函数
def show_help():
    print('系统命令: 清屏, 查看索引, 帮助, 退出')

def show_index():
    print('主题分片索引已集成，无需单独索引查看')

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def check_and_update_if_needed() -> bool:
    """检查上次系统检测时间，如果检测通过且超过5天则执行更新"""
    from datetime import datetime
    from charset_normalizer import from_path
    import json5

    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    if not os.path.exists(config_file):
        return False

    try:
        # 使用Charset Normalizer自动检测编码
        charset_results = from_path(config_file)
        if charset_results:
            best_match = charset_results.best()
            if best_match:
                detected_encoding = best_match.encoding
                with open(config_file, 'r', encoding=detected_encoding) as f:
                    config_data = json5.load(f)
            else:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json5.load(f)
        else:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json5.load(f)

        system_check = config_data.get('system_check', {})
        timestamp_str = system_check.get('timestamp')
        passed = system_check.get('passed', False)

        if not timestamp_str:
            return False

        # 只在检测通过的情况下才检查时间
        if not passed:
            return False

        # 解析时间戳
        last_check_time = datetime.fromisoformat(timestamp_str)
        now = datetime.now()
        days_since_last_check = (now - last_check_time).days

        # 如果超过5天
        if days_since_last_check >= 5:
            print(f"⚠️ 上次系统检测已超过 {days_since_last_check} 天，开始执行更新...")
            print("=" * 50)

            # 执行 update.py
            update_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "update.py")
            if os.path.exists(update_script):
                result = subprocess.run([sys.executable, update_script], cwd=os.path.dirname(os.path.abspath(__file__)))
                if result.returncode == 0:
                    print("✅ 更新成功")
                else:
                    print(f"⚠️ 更新失败，返回码: {result.returncode}")
            else:
                print("⚠️ update.py 不存在，跳过更新")

            # 重置检测状态为 false
            config_data['system_check']['passed'] = False
            # 保存配置
            detected_encoding = 'utf-8'
            if charset_results:
                best_match = charset_results.best()
                if best_match:
                    detected_encoding = best_match.encoding
            with open(config_file, 'w', encoding=detected_encoding) as f:
                import json
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            print("✅ 检测状态已重置为 false")
            print("=" * 50)
            print("🔄 正在重启程序...")
            # 重启程序
            os.execv(sys.executable, [sys.executable] + sys.argv)

        return False

    except Exception as e:
        print(f"⚠️ 检查上次检测时间失败: {e}")
        return False

# 延迟初始化 - 避免启动时阻塞
def _lazy_init_services():
    """延迟初始化服务 - 在需要时才初始化"""
    global service_manager, n
    if not hasattr(_lazy_init_services, '_initialized'):
        # 初始化服务管理器
        service_manager = ServiceManager()
        service_manager.start_background_services()
        
        # conversation_core已删除，相关功能已迁移到apiserver
        n = None
        
        # 初始化各个系统（MCP 已从启动流程中排除，不再初始化）
        # service_manager._init_mcp_services()
        service_manager._init_voice_system()
        service_manager._init_memory_system()
        
        # 显示系统状态
        print("=" * 30)
        print(f"GRAG状态: {'启用' if memory_manager.enabled else '禁用'}")
        if memory_manager.enabled:
            stats = memory_manager.get_memory_stats()
            from summer_memory.quintuple_graph import get_graph, GRAG_ENABLED
            graph = get_graph()
            print(f"Neo4j连接: {'成功' if graph and GRAG_ENABLED else '失败'}")
        print("=" * 30)
        print(f'{AI_NAME}系统已启动')
        print("=" * 30)
        
        # 启动服务（并行异步）
        service_manager.start_all_servers()
        
        show_help()
        
        _lazy_init_services._initialized = True

# NagaAgent适配器 - 优化重复初始化
class NagaAgentAdapter:
    def __init__(s):
        # 使用全局实例，避免重复初始化
        _lazy_init_services()  # 确保服务已初始化
        s.naga = n  # 使用全局实例
    
    async def respond_stream(s, txt):
        async for resp in s.naga.process(txt):
            yield AI_NAME, resp, None, True, False

# 主程序入口
if __name__ == "__main__":
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="NagaAgent - 智能对话助手")
    parser.add_argument("--check-env", action="store_true", help="运行系统环境检测")
    parser.add_argument("--quick-check", action="store_true", help="运行快速环境检测")
    parser.add_argument("--force-check", action="store_true", help="强制运行环境检测（忽略缓存）")

    args = parser.parse_args()

    # 处理检测命令
    if args.check_env or args.quick_check:
        if args.quick_check:
            success = run_quick_check()
        else:
            success = run_system_check(force_check=args.force_check)
        sys.exit(0 if success else 1)

    # 检查上次系统检测时间，如果超过7天则执行更新
    check_and_update_if_needed()

    # 系统环境检测
    print("🚀 正在启动NagaAgent...")
    print("=" * 50)

    # 如果是打包环境，跳过所有环境检测
    if IS_PACKAGED:
        print("📦 检测到打包环境，跳过系统环境检测...")
    else:
        # 执行系统检测（只在第一次启动时检测）
        if not run_system_check():
            print("\n❌ 系统环境检测失败，程序无法启动")
            print("请根据上述建议修复问题后重新启动")
            i=input("是否无视检测结果继续启动？是则按y，否则按其他任意键退出...")
            if i != "y" and i != "Y":
                sys.exit(1)
            else:
                # 用户选择强制启动，将检测状态设置为通过
                from charset_normalizer import from_path
                import json5
                from datetime import datetime
                
                config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
                if os.path.exists(config_file):
                    try:
                        charset_results = from_path(config_file)
                        if charset_results:
                            best_match = charset_results.best()
                            detected_encoding = best_match.encoding if best_match else 'utf-8'
                        else:
                            detected_encoding = 'utf-8'
                        
                        with open(config_file, 'r', encoding=detected_encoding) as f:
                            config_data = json5.load(f)
                        
                        if 'system_check' not in config_data:
                            config_data['system_check'] = {}
                        
                        config_data['system_check']['passed'] = True
                        config_data['system_check']['timestamp'] = datetime.now().isoformat()
                        
                        with open(config_file, 'w', encoding=detected_encoding) as f:
                            import json
                            json.dump(config_data, f, ensure_ascii=False, indent=2)
                        
                        print("✅ 已将检测状态设置为通过")
                    except Exception as e:
                        print(f"⚠️ 保存检测状态失败: {e}")

    print("\n🎉 系统环境检测通过，正在启动应用...")
    print("=" * 50)

    if not asyncio.get_event_loop().is_running():
        asyncio.set_event_loop(asyncio.new_event_loop())

    # 启动后端服务
    _lazy_init_services()
    print("\n✅ 所有后端服务已启动，等待前端连接...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 正在关闭后端服务...")
        sys.exit(0)
