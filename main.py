# 标准库导入
import asyncio
import logging
import os
import socket
import sys
import threading
import time

# 第三方库导入
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

# 本地模块导入
from system.system_checker import run_system_check
from system.config import config, AI_NAME
from system.conversation_core import NagaConversation
from summer_memory.memory_manager import memory_manager
from summer_memory.task_manager import start_task_manager, task_manager
from ui.pyqt_chat_window import ChatWindow
from ui.tray.console_tray import integrate_console_tray

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("summer_memory")
logger.setLevel(logging.INFO)

# 过滤HTTP相关日志
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# 服务管理器类
class ServiceManager:
    """服务管理器 - 统一管理所有后台服务"""
    
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.bg_thread = None
        self.api_thread = None
        self.tts_thread = None
    
    def start_background_services(self):
        """启动后台服务"""
        logger.info("正在启动后台服务...")
        
        # 启动后台任务管理器
        self.bg_thread = threading.Thread(target=self._run_event_loop, daemon=True)
        self.bg_thread.start()
        logger.info(f"后台服务线程已启动: {self.bg_thread.name}")
        
        # 短暂等待服务初始化
        time.sleep(1)
    
    def _run_event_loop(self):
        """运行事件循环"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._init_background_services())
        logger.info("后台服务事件循环已启动")
    
    async def _init_background_services(self):
        """初始化后台服务"""
        logger.info("正在启动后台服务...")
        try:
            # 启动任务管理器
            await start_task_manager()
            
            # 添加状态检查
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
    
    def start_api_server(self):
        """启动API服务器"""
        try:
            if not self.check_port_available(config.api_server.host, config.api_server.port):
                print(f"⚠️ 端口 {config.api_server.port} 已被占用，跳过API服务器启动")
                return
            
            import uvicorn
            
            print("🚀 正在启动夏园API服务器...")
            print(f"📍 地址: http://{config.api_server.host}:{config.api_server.port}")
            print(f"📚 文档: http://{config.api_server.host}:{config.api_server.port}/docs")
            
            def run_server():
                try:
                    uvicorn.run(
                        "apiserver.api_server:app",
                        host=config.api_server.host,
                        port=config.api_server.port,
                        log_level="error",
                        access_log=False,
                        reload=False
                    )
                except Exception as e:
                    print(f"❌ API服务器启动失败: {e}")
            
            self.api_thread = threading.Thread(target=run_server, daemon=True)
            self.api_thread.start()
            print("✅ API服务器已在后台启动")
            time.sleep(1)
            
        except ImportError as e:
            print(f"⚠️ API服务器依赖缺失: {e}")
            print("   请运行: pip install fastapi uvicorn")
        except Exception as e:
            print(f"❌ API服务器启动异常: {e}")
    
    def start_tts_server(self):
        """启动语音输出服务（TTS）"""
        try:
            if not self.check_port_available("0.0.0.0", config.tts.port):
                print(f"⚠️ 端口 {config.tts.port} 已被占用，跳过语音输出服务启动")
                return
            
            print(f"📍 地址: http://127.0.0.1:{config.tts.port}")
            
            def run_tts():
                try:
                    from voice.output.start_voice_service import start_http_server
                    start_http_server()
                except Exception as e:
                    print(f"❌ 语音输出服务启动失败: {e}")
            
            self.tts_thread = threading.Thread(target=run_tts, daemon=True)
            self.tts_thread.start()
            print("✅ 语音输出服务已在后台启动")
            time.sleep(1)
        except Exception as e:
            print(f"❌ 语音输出服务启动异常: {e}")
    
    def show_naga_portal_status(self):
        """显示NagaPortal配置状态（手动调用）"""
        try:
            if config.naga_portal.username and config.naga_portal.password:
                print(f"🌐 NagaPortal: 已配置账户信息")
                print(f"   地址: {config.naga_portal.portal_url}")
                print(f"   用户: {config.naga_portal.username[:3]}***{config.naga_portal.username[-3:] if len(config.naga_portal.username) > 6 else '***'}")
                
                # 获取并显示Cookie信息
                try:
                    from mcpserver.agent_naga_portal.portal_login_manager import get_portal_login_manager
                    login_manager = get_portal_login_manager()
                    status = login_manager.get_status()
                    cookies = login_manager.get_cookies()
                    
                    if cookies:
                        print(f"🍪 Cookie信息 ({len(cookies)}个):")
                        for name, value in cookies.items():
                            # 显示完整的cookie名称和值
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
                    print(f"🍪 状态获取失败: {e}")
            else:
                print(f"🌐 NagaPortal: 未配置账户信息")
                print(f"   如需使用NagaPortal功能，请在config.json中配置naga_portal.username和password")
        except Exception as e:
            print(f"🌐 NagaPortal: 配置检查失败 - {e}")

# 工具函数
def show_help():
    print('系统命令: 清屏, 查看索引, 帮助, 退出')

def show_index():
    print('主题分片索引已集成，无需单独索引查看')

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

# 初始化服务管理器
service_manager = ServiceManager()
service_manager.start_background_services()

# 创建对话实例
n = NagaConversation()

# 初始化进度文件
with open('./ui/styles/progress.txt', 'w') as f:
    f.write('0')

# 显示系统状态
print("=" * 30)
print(f"GRAG状态: {'启用' if memory_manager.enabled else '禁用'}")
if memory_manager.enabled:
    stats = memory_manager.get_memory_stats()
    from summer_memory.quintuple_graph import graph, GRAG_ENABLED
    print(f"Neo4j连接: {'成功' if graph and GRAG_ENABLED else '失败'}")
print("=" * 30)
print(f'{AI_NAME}系统已启动')
print("=" * 30)

# 启动服务
if config.api_server.enabled and config.api_server.auto_start:
    service_manager.start_api_server()

service_manager.start_tts_server()

# 物联网通讯连接已在后台异步执行，连接完成后会自动显示状态
print("⏳ 物联网通讯正在后台初始化连接...")

# NagaPortal自动登录已在后台异步执行，登录完成后会自动显示状态
print("⏳ NagaPortal正在后台自动登录...")
show_help()

# NagaAgent适配器
class NagaAgentAdapter:
    def __init__(s):
        s.naga = NagaConversation()  # 第二次初始化：NagaAgentAdapter构造函数中创建
    
    async def respond_stream(s, txt):
        async for resp in s.naga.process(txt):
            yield AI_NAME, resp, None, True, False

# 主程序入口
if __name__ == "__main__":
    # 系统环境检测
    print("🚀 正在启动NagaAgent...")
    print("=" * 50)
    
    # 执行系统检测（只在第一次启动时检测）
    if not run_system_check():
        print("\n❌ 系统环境检测失败，程序无法启动")
        print("请根据上述建议修复问题后重新启动")
        input("按回车键退出...")
        sys.exit(1)
    
    print("\n🎉 系统环境检测通过，正在启动应用...")
    print("=" * 50)
    
    if not asyncio.get_event_loop().is_running():
        asyncio.set_event_loop(asyncio.new_event_loop())
    
    app = QApplication(sys.argv)
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "window_icon.png")
    app.setWindowIcon(QIcon(icon_path))
    
    # 集成控制台托盘功能
    console_tray = integrate_console_tray()
    
    win = ChatWindow()
    win.setWindowTitle("NagaAgent")
    win.show()
    
    sys.exit(app.exec_())
