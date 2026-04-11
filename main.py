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

# ── 热补丁加载 ──
# 打包环境下，优先从补丁目录加载 .pyc/.py 模块，实现不重装的代码热更新
# 补丁目录由 Electron 通过环境变量 NAGA_PATCH_DIR 传入
_patch_dir = os.environ.get("NAGA_PATCH_DIR", "")
if _patch_dir and os.path.isdir(_patch_dir):
    sys.path.insert(0, _patch_dir)
    print(f"[HotPatch] 补丁目录已加载: {_patch_dir}", flush=True)
elif IS_PACKAGED:
    # 打包环境下的默认补丁路径（与 Electron userData 对齐）
    # Electron productName 是 "Naga Agent"，userData 目录名因平台而异
    _candidate_dirs = []
    if sys.platform == "win32":
        _appdata = os.environ.get("APPDATA", "")
        _candidate_dirs = [
            os.path.join(_appdata, "Naga Agent", "patches", "backend"),
            os.path.join(_appdata, "naga-agent", "patches", "backend"),
        ]
    elif sys.platform == "darwin":
        _candidate_dirs = [
            os.path.expanduser("~/Library/Application Support/Naga Agent/patches/backend"),
            os.path.expanduser("~/Library/Application Support/naga-agent/patches/backend"),
        ]
    else:
        _candidate_dirs = [
            os.path.expanduser("~/.config/Naga Agent/patches/backend"),
            os.path.expanduser("~/.config/naga-agent/patches/backend"),
        ]
    for _default_patch in _candidate_dirs:
        if os.path.isdir(_default_patch):
            sys.path.insert(0, _default_patch)
            print(f"[HotPatch] 补丁目录已加载: {_default_patch}", flush=True)
            break

# 标准库导入
import asyncio
import json as _json
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

# 统一日志系统初始化
from system.logging_setup import setup_logging
setup_logging()

logger = logging.getLogger("summer_memory")
logger.setLevel(logging.INFO)

# 优化Live2D相关日志输出，减少启动时的信息噪音
logging.getLogger("live2d").setLevel(logging.WARNING)
logging.getLogger("live2d.renderer").setLevel(logging.WARNING)
logging.getLogger("live2d.animator").setLevel(logging.WARNING)
logging.getLogger("live2d.widget").setLevel(logging.WARNING)
logging.getLogger("live2d.config").setLevel(logging.WARNING)
logging.getLogger("live2d.config_dialog").setLevel(logging.WARNING)
logging.getLogger("OpenGL").setLevel(logging.WARNING)
logging.getLogger("OpenGL.acceleratesupport").setLevel(logging.WARNING)


def _emit_progress(percent: int, phase: str):
    """向 stdout 发送结构化进度信号，供 Electron 主进程解析"""
    print(f"##PROGRESS##{_json.dumps({'percent': percent, 'phase': phase})}", flush=True)


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
        """并行启动所有服务：API(可选)、MCP、Agent、TTS"""
        print("🚀 正在并行启动所有服务...")
        print("=" * 50)
        threads = []
        service_status = {}  # 服务状态跟踪

        try:
            self._init_proxy_settings()
            # 预检查所有端口（端口已在启动前由 kill_port_occupiers 清理）
            from system.config import get_server_port
            port_checks = {
                # API 不做“启动前 bind 预检查”，避免在 Windows/虚拟机环境误判为占用导致根本不启动。
                # 实际绑定冲突交给 uvicorn 抛错并记录详细日志。
                'api': config.api_server.enabled and config.api_server.auto_start,
                'mcp': self.check_port_available("0.0.0.0", get_server_port("mcp_server")),
                'agent': self.check_port_available("0.0.0.0", get_server_port("agent_server")),
                'tts': self.check_port_available("0.0.0.0", config.tts.port)
            }

            # API服务器（可选）
            if port_checks['api']:
                self.api_thread = threading.Thread(target=self._start_api_server, daemon=True)
                threads.append(("API", self.api_thread))
                service_status['API'] = "准备启动"
            else:
                service_status['API'] = (
                    "自动启动关闭" if config.api_server.enabled else "已禁用"
                )

            # MCP服务器（提供外部统一HTTP API）
            if port_checks['mcp']:
                mcp_thread = threading.Thread(target=self._start_mcp_server, daemon=True)
                threads.append(("MCP", mcp_thread))
                service_status['MCP'] = "准备启动"
            else:
                print(f"⚠️  MCP服务器: 端口 {get_server_port('mcp_server')} 已被占用，跳过启动")
                service_status['MCP'] = "端口占用"

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

            # 等待服务启动：轮询端口可连接性，最长等 3s
            print("⏳ 等待服务初始化...")
            expected_ports = []
            if port_checks.get('api'):
                expected_ports.append(config.api_server.port)
            if port_checks.get('mcp'):
                expected_ports.append(get_server_port("mcp_server"))
            if port_checks.get('agent'):
                expected_ports.append(get_server_port("agent_server"))
            if port_checks.get('tts'):
                expected_ports.append(config.tts.port)

            if expected_ports:
                for _ in range(15):  # 最多 15 × 0.2s = 3s
                    all_ready = True
                    for p in expected_ports:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.1)
                        if s.connect_ex(('127.0.0.1', p)) != 0:
                            all_ready = False
                        s.close()
                        if not all_ready:
                            break
                    if all_ready:
                        break
                    time.sleep(0.2)

            # API 端口额外诊断日志，方便定位虚拟机内的“无监听/SYN_SENT”问题
            if port_checks.get('api'):
                api_port = config.api_server.port
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.2)
                api_ready = (s.connect_ex(('127.0.0.1', api_port)) == 0)
                s.close()
                if not api_ready:
                    print(
                        f"⚠️  API服务器端口 {api_port} 当前不可连接（可能启动失败、仍在启动或本机环回被拦截）"
                    )
                if self.api_thread is not None and not self.api_thread.is_alive():
                    print("❌ API服务器线程已退出，启动可能失败（请查看上方异常日志）")
                    logger.error("API服务器线程已退出，启动可能失败")

            _emit_progress(45, "等待服务就绪...")

            print("-" * 30)
            print(f"🎉 服务启动完成: {len(threads)} 个服务正在运行")
            print("=" * 50)
            
        except Exception as e:
            print(f"❌ 并行启动服务异常: {e}")

    def _init_proxy_settings(self):
        """初始化代理设置：若不启用代理，则清空系统代理环境变量；始终为内部通信设置 NO_PROXY"""
        # 始终确保本地服务通信不走代理
        no_proxy_hosts = "localhost,127.0.0.1,0.0.0.0"
        existing = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
        if existing:
            no_proxy_hosts = f"{existing},{no_proxy_hosts}"
        os.environ["NO_PROXY"] = no_proxy_hosts
        os.environ["no_proxy"] = no_proxy_hosts
        print(f"已设置 NO_PROXY={no_proxy_hosts}")

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
        import traceback
        host = str(config.api_server.host).strip() or "127.0.0.1"
        port = config.api_server.port
        hosts = [host]
        if host != "0.0.0.0":
            hosts.append("0.0.0.0")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            for bind_host in hosts:
                try:
                    import uvicorn
                    from apiserver.api_server import app

                    print(
                        f"   🚀 API服务器: 正在启动 on {bind_host}:{port} (attempt {attempt}/{max_attempts})...",
                        flush=True,
                    )
                    logger.info(
                        f"API服务器启动: host={bind_host} port={port} attempt={attempt}/{max_attempts}"
                    )

                    uvicorn.run(
                        app,
                        host=bind_host,
                        port=port,
                        log_level="info",
                        access_log=False,
                        reload=False,
                        ws_ping_interval=None,
                        ws_ping_timeout=None,
                    )
                    logger.warning(
                        f"API服务器已退出: host={bind_host} port={port} attempt={attempt}/{max_attempts}"
                    )
                    print("   ⚠️ API服务器进程已退出，准备重试...", flush=True)
                except ImportError as e:
                    print(f"   ❌ API服务器依赖缺失: {e}", flush=True)
                    logger.exception(f"API服务器依赖缺失: {e}")
                    traceback.print_exc()
                    return
                except Exception as e:
                    print(f"   ❌ API服务器启动失败: {e}", flush=True)
                    logger.exception(f"API服务器启动失败: {e}")
                    traceback.print_exc()

            if attempt < max_attempts:
                print("   🔁 API服务器启动重试中...", flush=True)
                time.sleep(1.5)

        print("   ❌ API服务器连续重试失败，已放弃自动启动", flush=True)
        logger.error(f"API服务器连续重试失败: host={host} port={port}")
    
    def _start_mcp_server(self):
        """内部MCP服务器启动方法"""
        try:
            import uvicorn
            from mcpserver.mcp_server import app
            from system.config import get_server_port

            uvicorn.run(
                app,
                host="0.0.0.0",
                port=get_server_port("mcp_server"),
                log_level="error",
                access_log=False,
                reload=False,
                ws_ping_interval=None,
                ws_ping_timeout=None
            )
        except Exception as e:
            import traceback
            print(f"   ❌ MCP服务器启动失败: {e}", flush=True)
            traceback.print_exc()

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
            # 启动时确保有有效 access_token（Windows 端 refresh_token 恢复后需主动刷新）
            try:
                from apiserver.naga_auth import ensure_access_token
                import asyncio as _asyncio
                try:
                    loop = _asyncio.get_running_loop()
                    # 已在事件循环中，创建 task（不阻塞当前线程）
                    loop.create_task(ensure_access_token())
                except RuntimeError:
                    # 没有运行中的事件循环，同步执行
                    _asyncio.run(ensure_access_token())
            except Exception as e:
                logger.warning(f"启动时刷新 token 失败: {e}")

            # 优先检查远程 NagaMemory 服务
            from summer_memory.memory_client import get_remote_memory_client
            remote = get_remote_memory_client()
            if remote is not None:
                logger.info("记忆系统使用远程 NagaMemory 服务")
                return

            # 回退到本地 summer_memory
            if memory_manager and memory_manager.enabled:
                logger.info("夏园记忆系统已初始化")
            else:
                logger.info("夏园记忆系统已禁用")
        except Exception as e:
            logger.warning(f"记忆系统初始化失败: {e}")
    
    def _init_mcp_services(self):
        """初始化MCP服务系统 - in-process 注册 agent"""
        try:
            from mcpserver.mcp_registry import auto_register_mcp
            registered = auto_register_mcp()
            logger.info(f"MCP服务已注册（in-process），共 {len(registered)} 个: {registered}")
        except Exception as e:
            logger.error(f"MCP服务系统初始化失败: {e}")

def _kill_port_pids(port: int, my_pid: int) -> bool:
    """杀掉占用指定端口的所有进程及其子进程树，返回是否杀掉了任何进程"""
    killed = False
    if sys.platform == "win32":
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    if pid != my_pid and pid > 0:
                        # /T 连同子进程一起杀
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
                        print(f"   已终止占用端口 {port} 的进程树 (PID {pid})")
                        killed = True
        except Exception as e:
            print(f"   ⚠️ 清理端口 {port} 时出错: {e}")
    else:
        pids_to_kill = set()
        # 方法1: lsof -nP (跳过 DNS/端口名解析，macOS 上必须加)
        try:
            result = subprocess.run(
                ["lsof", "-nP", "-t", "-i", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            for pid_str in result.stdout.strip().split("\n"):
                pid_str = pid_str.strip()
                if pid_str:
                    try:
                        pids_to_kill.add(int(pid_str))
                    except ValueError:
                        pass
        except Exception:
            pass

        # 方法2: 如果 lsof 没找到，用 shell 管道兜底
        if not pids_to_kill:
            try:
                result = subprocess.run(
                    f"lsof -nP -i :{port} 2>/dev/null | grep LISTEN | awk '{{print $2}}'",
                    shell=True, capture_output=True, text=True, timeout=5,
                )
                for pid_str in result.stdout.strip().split("\n"):
                    pid_str = pid_str.strip()
                    if pid_str:
                        try:
                            pids_to_kill.add(int(pid_str))
                        except ValueError:
                            pass
            except Exception:
                pass

        # 杀掉找到的进程及其整个进程组
        for pid in pids_to_kill:
            if pid == my_pid or pid <= 0:
                continue
            try:
                # 先尝试杀整个进程组（杀掉 uvicorn workers 等子进程）
                pgid = os.getpgid(pid)
                if pgid != my_pid and pgid > 0:
                    try:
                        os.killpg(pgid, 9)
                        print(f"   已终止占用端口 {port} 的进程组 (PGID {pgid})")
                        killed = True
                        continue
                    except ProcessLookupError:
                        pass
            except (ProcessLookupError, PermissionError):
                pass
            # 回退：单独杀进程
            try:
                os.kill(pid, 9)
                print(f"   已终止占用端口 {port} 的进程 (PID {pid})")
                killed = True
            except ProcessLookupError:
                pass
    return killed


def _is_port_free(port: int) -> bool:
    """检查端口是否已释放"""
    import socket as _sock
    try:
        with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def kill_port_occupiers():
    """启动前杀掉占用后端端口的进程，循环重试直到所有端口释放（最多 30 轮 × 2s = 60 秒）"""
    from system.config import get_all_server_ports
    all_ports = get_all_server_ports()
    ports = [
        all_ports["api_server"],
        all_ports["agent_server"],
        all_ports["mcp_server"],
        all_ports["tts_server"],
    ]
    my_pid = os.getpid()
    max_attempts = 30

    for attempt in range(1, max_attempts + 1):
        # 找出仍被占用的端口
        busy = [p for p in ports if not _is_port_free(p)]
        if not busy:
            if attempt > 1:
                print("   ✅ 所有端口已释放")
            return

        print(f"   第 {attempt}/{max_attempts} 轮清理: 端口 {', '.join(map(str, busy))} 被占用")
        for port in busy:
            _kill_port_pids(port, my_pid)

        # 等待端口释放
        wait = 2 if attempt < max_attempts else 0
        if wait:
            time.sleep(wait)

    # 最终检查
    still_busy = [p for p in ports if not _is_port_free(p)]
    if still_busy:
        print(f"   ⚠️ 端口 {', '.join(map(str, still_busy))} 仍被占用，将跳过对应服务")


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
    import json5

    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

    if not os.path.exists(config_file):
        return False

    try:
        # 直接用 UTF-8 读取（本项目 config.json 始终为 UTF-8 编码）
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
            import json
            with open(config_file, 'w', encoding='utf-8') as f:
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
        _emit_progress(15, "初始化服务...")

        # conversation_core已删除，相关功能已迁移到apiserver
        n = None

        # 初始化各个系统
        service_manager._init_mcp_services()
        _emit_progress(20, "注册MCP服务...")
        service_manager._init_voice_system()
        service_manager._init_memory_system()
        _emit_progress(25, "初始化子系统...")
        
        # 显示系统状态
        print("=" * 30)
        # 检查远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client
        remote_memory = get_remote_memory_client()
        if remote_memory is not None:
            print(f"记忆系统: 远程 NagaMemory ({config.memory_server.url})")
            try:
                # 启动时用同步 httpx 做健康检查，避免 event loop 问题
                import httpx as _httpx
                resp = _httpx.get(f"{config.memory_server.url}/health", timeout=5.0)
                ok = resp.status_code == 200
                print(f"NagaMemory连接: {'成功' if ok else '失败'}")
            except Exception as e:
                print(f"NagaMemory连接: 失败 ({e})")
        else:
            print(f"GRAG状态: {'启用' if memory_manager.enabled else '禁用'}")
            if memory_manager.enabled:
                stats = memory_manager.get_memory_stats()
                from summer_memory import quintuple_graph as _qg
                graph = _qg.get_graph()
                print(f"Neo4j连接: {'成功' if graph and _qg.GRAG_ENABLED else '失败'}")
        print("=" * 30)
        print(f'{AI_NAME}系统已启动')
        print("=" * 30)
        
        # 启动服务（并行异步）
        _emit_progress(30, "启动服务器...")
        service_manager.start_all_servers()
        _emit_progress(50, "后端就绪")
        
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
    parser.add_argument("--headless", action="store_true", help="无头模式（Electron/Web，跳过交互提示）")

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

    # 启动前清理占用端口的进程
    print("🔍 检查端口占用...")
    kill_port_occupiers()

    # 系统环境检测
    print("🚀 正在启动NagaAgent...")
    print("=" * 50)

    headless = args.headless or not sys.stdin.isatty()

    # 如果是打包环境，跳过所有环境检测
    if IS_PACKAGED:
        print("📦 检测到打包环境，跳过系统环境检测...")
    else:
        # 执行系统检测（只在第一次启动时检测）
        if not run_system_check():
            print("\n❌ 系统环境检测失败，程序无法启动")
            print("请根据上述建议修复问题后重新启动")
            if headless:
                print("⚠️ 无头模式：自动继续启动...")
            else:
                i=input("是否无视检测结果继续启动？是则按y，否则按其他任意键退出...")
                if i != "y" and i != "Y":
                    sys.exit(1)

    print("\n🎉 系统环境检测通过，正在启动应用...")
    print("=" * 50)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # 启动后端服务
    _lazy_init_services()
    print("\n✅ 所有后端服务已启动，等待前端连接...")

    import signal

    def _shutdown(signum=None, frame=None):
        print("\n👋 正在关闭后端服务...")
        os._exit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()
