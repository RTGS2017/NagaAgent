"""
控制台托盘管理器
将终端窗口隐藏到系统托盘
"""
import os
import sys
import platform
import threading
import subprocess
import time
from nagaagent_core.vendors.PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtCore import QTimer, pyqtSignal, QObject  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtGui import QIcon  # 统一入口 #

# 平台特定导入
if platform.system() == 'Windows':
    import winreg
    import ctypes
    from ctypes import wintypes
else:
    # macOS/Linux 平台特定导入
    try:
        import plistlib
        import shutil
    except ImportError:
        plistlib = None
        shutil = None
    # 在非Windows平台上，winreg模块不可用
    winreg = None


class ConsoleTrayManager(QObject):
    """控制台托盘管理器"""
    
    # 信号定义
    show_console = pyqtSignal()  # 显示控制台信号
    hide_console = pyqtSignal()  # 隐藏控制台信号
    quit_application = pyqtSignal()  # 退出应用信号
    
    def __init__(self, console_hwnd=None, auto_hide=True):
        super().__init__()
        self.console_hwnd = console_hwnd
        self.tray_icon = None
        self.is_auto_start = self._check_auto_start()
        self.console_visible = True
        self.auto_hide = auto_hide  # 是否自动隐藏控制台
        self.original_style = None  # 保存原始窗口样式
        self._setup_tray()
        self._find_console_window()
        
        # 如果启用自动隐藏，延迟隐藏控制台
        if self.auto_hide:
            QTimer.singleShot(3000, self._auto_hide_console)  # 3秒后自动隐藏
    
    def _auto_hide_console(self):
        """自动隐藏控制台"""
        if self.console_hwnd and self.console_visible:
            print("自动隐藏控制台窗口...")
            self.hide_console_window()
            # 显示托盘消息提示
            self.show_message("NagaAgent 4.0", "系统已启动，控制台已隐藏到托盘")
    
    def _setup_tray(self):
        """设置系统托盘"""
        try:
            # 创建托盘图标
            icon_path = os.path.join(os.path.dirname(__file__), "..", "img/window_icon.png")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.path.dirname(__file__), "..", "img/standby.png")
            
            # 创建系统托盘图标
            self.tray_icon = QSystemTrayIcon()
            self.tray_icon.setIcon(QIcon(icon_path))
            self.tray_icon.setToolTip("NagaAgent 4.0 - 控制台")
            
            # 创建托盘菜单
            self._create_tray_menu()
            
            # 连接信号
            self.tray_icon.activated.connect(self._on_tray_activated)
            
            # 显示托盘图标
            self.tray_icon.show()
            
        except Exception as e:
            print(f"控制台托盘设置失败: {e}")
    
    def _create_tray_menu(self):
        """创建托盘菜单"""
        menu = QMenu()
        
        # 显示控制台
        show_action = QAction("显示控制台", self)
        show_action.triggered.connect(self.show_console.emit)
        menu.addAction(show_action)
        
        # 隐藏控制台
        hide_action = QAction("隐藏控制台", self)
        hide_action.triggered.connect(self.hide_console.emit)
        menu.addAction(hide_action)
        
        menu.addSeparator()
        
        # 自启动开关
        self.auto_start_action = QAction("开机自启动", self)
        self.auto_start_action.setCheckable(True)
        self.auto_start_action.setChecked(self.is_auto_start)
        self.auto_start_action.triggered.connect(self._toggle_auto_start)
        menu.addAction(self.auto_start_action)
        
        menu.addSeparator()
        
        # 退出应用
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application.emit)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
    
    def _on_tray_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_console.emit()
    
    def _find_console_window(self):
        """查找控制台窗口句柄"""
        if platform.system() == 'Windows':
            self._find_console_window_windows()
        else:
            self._find_console_window_unix()
    
    def _find_console_window_windows(self):
        """Windows平台查找控制台窗口句柄"""
        try:
            # 获取当前进程的控制台窗口
            kernel32 = ctypes.windll.kernel32
            self.console_hwnd = kernel32.GetConsoleWindow()
            
            if self.console_hwnd:
                print(f"找到控制台窗口: {self.console_hwnd}")
                # 保存原始窗口样式
                self.original_style = ctypes.windll.user32.GetWindowLongW(self.console_hwnd, -16)  # GWL_EXSTYLE
            else:
                print("未找到控制台窗口")
                
        except Exception as e:
            print(f"查找控制台窗口失败: {e}")
    
    def _find_console_window_unix(self):
        """Unix/macOS平台查找控制台窗口"""
        try:
            # 在Unix/macOS上，我们无法直接获取控制台窗口句柄
            # 使用其他方法来管理终端窗口
            self.console_hwnd = None
            print("Unix/macOS平台：控制台窗口管理使用终端命令")
        except Exception as e:
            print(f"查找控制台窗口失败: {e}")
    
    def _hide_from_taskbar(self):
        """从任务栏隐藏窗口"""
        if platform.system() == 'Windows' and self.console_hwnd:
            self._hide_from_taskbar_windows()
        else:
            self._hide_from_taskbar_unix()
    
    def _hide_from_taskbar_windows(self):
        """Windows平台从任务栏隐藏窗口"""
        try:
            user32 = ctypes.windll.user32
            # 设置窗口扩展样式，从任务栏隐藏
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            
            # 获取当前样式
            current_style = user32.GetWindowLongW(self.console_hwnd, -16)  # GWL_EXSTYLE
            # 移除WS_EX_APPWINDOW，添加WS_EX_TOOLWINDOW
            new_style = (current_style & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(self.console_hwnd, -16, new_style)
            
            print("控制台窗口已从任务栏隐藏")
        except Exception as e:
            print(f"从任务栏隐藏失败: {e}")
    
    def _hide_from_taskbar_unix(self):
        """Unix/macOS平台从任务栏隐藏窗口"""
        try:
            # 在Unix/macOS上，使用终端命令来隐藏窗口
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "h" using command down'])
            print("Unix/macOS平台：控制台窗口隐藏")
        except Exception as e:
            print(f"从任务栏隐藏失败: {e}")
    
    def _show_in_taskbar(self):
        """在任务栏显示窗口"""
        if platform.system() == 'Windows' and self.console_hwnd:
            self._show_in_taskbar_windows()
        else:
            self._show_in_taskbar_unix()
    
    def _show_in_taskbar_windows(self):
        """Windows平台在任务栏显示窗口"""
        if self.console_hwnd and self.original_style is not None:
            try:
                user32 = ctypes.windll.user32
                # 恢复原始窗口样式
                user32.SetWindowLongW(self.console_hwnd, -16, self.original_style)
                print("控制台窗口已在任务栏显示")
            except Exception as e:
                print(f"在任务栏显示失败: {e}")
    
    def _show_in_taskbar_unix(self):
        """Unix/macOS平台在任务栏显示窗口"""
        try:
            # 在Unix/macOS上，使用终端命令来显示窗口
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "m" using command down'])
            print("Unix/macOS平台：控制台窗口显示")
        except Exception as e:
            print(f"在任务栏显示失败: {e}")
    
    def show_console_window(self):
        """显示控制台窗口"""
        if platform.system() == 'Windows' and self.console_hwnd:
            self._show_console_window_windows()
        else:
            self._show_console_window_unix()
    
    def _show_console_window_windows(self):
        """Windows平台显示控制台窗口"""
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(self.console_hwnd, 1)  # SW_SHOWNORMAL
            user32.SetForegroundWindow(self.console_hwnd)
            self.console_visible = True
            
            # 恢复在任务栏显示
            self._show_in_taskbar()
            
            print("控制台窗口已显示")
        except Exception as e:
            print(f"显示控制台窗口失败: {e}")
    
    def _show_console_window_unix(self):
        """Unix/macOS平台显示控制台窗口"""
        try:
            self.console_visible = True
            # 在Unix/macOS上，使用终端命令来显示窗口
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 'tell application "Terminal" to activate'])
                subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "m" using command down'])
            elif platform.system() == 'Linux':
                # Linux平台尝试使用xdotool或其他工具
                try:
                    subprocess.run(['xdotool', 'windowactivate', str(os.getpid())])
                except FileNotFoundError:
                    print("Linux平台：需要安装xdotool来管理窗口")
            print("Unix/macOS平台：控制台窗口已显示")
        except Exception as e:
            print(f"显示控制台窗口失败: {e}")
    
    def hide_console_window(self):
        """隐藏控制台窗口"""
        if platform.system() == 'Windows' and self.console_hwnd:
            self._hide_console_window_windows()
        else:
            self._hide_console_window_unix()
    
    def _hide_console_window_windows(self):
        """Windows平台隐藏控制台窗口"""
        try:
            user32 = ctypes.windll.user32
            user32.ShowWindow(self.console_hwnd, 0)  # SW_HIDE
            self.console_visible = False
            
            # 从任务栏隐藏
            self._hide_from_taskbar()
            
            print("控制台窗口已隐藏")
        except Exception as e:
            print(f"隐藏控制台窗口失败: {e}")
    
    def _hide_console_window_unix(self):
        """Unix/macOS平台隐藏控制台窗口"""
        try:
            self.console_visible = False
            # 在Unix/macOS上，使用终端命令来隐藏窗口
            if platform.system() == 'Darwin':  # macOS
                subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "h" using command down'])
            elif platform.system() == 'Linux':
                # Linux平台尝试使用xdotool或其他工具
                try:
                    subprocess.run(['xdotool', 'windowminimize', str(os.getpid())])
                except FileNotFoundError:
                    print("Linux平台：需要安装xdotool来管理窗口")
            print("Unix/macOS平台：控制台窗口已隐藏")
        except Exception as e:
            print(f"隐藏控制台窗口失败: {e}")
    
    def _toggle_auto_start(self):
        """切换自启动状态"""
        if self.auto_start_action.isChecked():
            self._enable_auto_start()
        else:
            self._disable_auto_start()
    
    def _enable_auto_start(self):
        """启用自启动"""
        if platform.system() == 'Windows':
            self._enable_auto_start_windows()
        elif platform.system() == 'Darwin':
            self._enable_auto_start_macos()
        else:
            self._enable_auto_start_linux()
    
    def _enable_auto_start_windows(self):
        """Windows平台启用自启动"""
        if platform.system() != 'Windows' or winreg is None:
            print("Windows自启动功能仅在Windows平台上可用")
            self.auto_start_action.setChecked(False)
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )

            # 获取启动命令
            command = self._get_startup_command()

            winreg.SetValueEx(key, "NagaAgent4.0", 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            self.is_auto_start = True
            print("自启动已启用")

        except Exception as e:
            print(f"启用自启动失败: {e}")
            self.auto_start_action.setChecked(False)
    
    def _enable_auto_start_macos(self):
        """macOS平台启用自启动"""
        try:
            if not plistlib:
                print("macOS平台：plistlib模块不可用")
                self.auto_start_action.setChecked(False)
                return
            
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            os.makedirs(launch_agents_dir, exist_ok=True)
            
            plist_file = os.path.join(launch_agents_dir, "com.nagaagent.NagaAgent4.0.plist")
            
            # 获取启动命令
            command = self._get_startup_command()
            
            plist_data = {
                'Label': 'com.nagaagent.NagaAgent4.0',
                'ProgramArguments': [command],
                'RunAtLoad': True,
                'KeepAlive': False
            }
            
            with open(plist_file, 'wb') as f:
                plistlib.dump(plist_data, f)
            
            self.is_auto_start = True
            print("macOS自启动已启用")
            
        except Exception as e:
            print(f"macOS启用自启动失败: {e}")
            self.auto_start_action.setChecked(False)
    
    def _enable_auto_start_linux(self):
        """Linux平台启用自启动"""
        try:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            os.makedirs(autostart_dir, exist_ok=True)
            
            desktop_file = os.path.join(autostart_dir, "nagaagent4.0.desktop")
            
            # 获取启动命令
            command = self._get_startup_command()
            
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=NagaAgent 4.0
Exec={command}
Terminal=false
StartupNotify=false
"""
            
            with open(desktop_file, 'w') as f:
                f.write(desktop_content)
            
            self.is_auto_start = True
            print("Linux自启动已启用")
            
        except Exception as e:
            print(f"Linux启用自启动失败: {e}")
            self.auto_start_action.setChecked(False)
    
    def _disable_auto_start(self):
        """禁用自启动"""
        if platform.system() == 'Windows':
            self._disable_auto_start_windows()
        elif platform.system() == 'Darwin':
            self._disable_auto_start_macos()
        else:
            self._disable_auto_start_linux()
    
    def _disable_auto_start_windows(self):
        """Windows平台禁用自启动"""
        if platform.system() != 'Windows' or winreg is None:
            print("Windows自启动功能仅在Windows平台上可用")
            self.auto_start_action.setChecked(False)
            return

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, "NagaAgent4.0")
            winreg.CloseKey(key)
            self.is_auto_start = False
            print("自启动已禁用")

        except Exception as e:
            print(f"禁用自启动失败: {e}")
            self.auto_start_action.setChecked(True)
    
    def _disable_auto_start_macos(self):
        """macOS平台禁用自启动"""
        try:
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_file = os.path.join(launch_agents_dir, "com.nagaagent.NagaAgent4.0.plist")
            
            if os.path.exists(plist_file):
                os.remove(plist_file)
            
            self.is_auto_start = False
            print("macOS自启动已禁用")
            
        except Exception as e:
            print(f"macOS禁用自启动失败: {e}")
            self.auto_start_action.setChecked(True)
    
    def _disable_auto_start_linux(self):
        """Linux平台禁用自启动"""
        try:
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "nagaagent4.0.desktop")
            
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
            
            self.is_auto_start = False
            print("Linux自启动已禁用")
            
        except Exception as e:
            print(f"Linux禁用自启动失败: {e}")
            self.auto_start_action.setChecked(True)
    
    def _check_auto_start(self):
        """检查是否已启用自启动"""
        if platform.system() == 'Windows':
            return self._check_auto_start_windows()
        elif platform.system() == 'Darwin':
            return self._check_auto_start_macos()
        else:
            return self._check_auto_start_linux()
    
    def _check_auto_start_windows(self):
        """Windows平台检查自启动"""
        if platform.system() != 'Windows' or winreg is None:
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_READ
            )
            winreg.QueryValueEx(key, "NagaAgent4.0")
            winreg.CloseKey(key)
            return True
        except:
            return False
    
    def _check_auto_start_macos(self):
        """macOS平台检查自启动"""
        try:
            if not plistlib:
                return False
            
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_file = os.path.join(launch_agents_dir, "com.nagaagent.NagaAgent4.0.plist")
            
            if os.path.exists(plist_file):
                with open(plist_file, 'rb') as f:
                    plist_data = plistlib.load(f)
                return plist_data.get('RunAtLoad', False)
            return False
        except Exception as e:
            print(f"macOS自启动检查失败: {e}")
            return False
    
    def _check_auto_start_linux(self):
        """Linux平台检查自启动"""
        try:
            # 检查 ~/.config/autostart 目录
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, "nagaagent4.0.desktop")
            return os.path.exists(desktop_file)
        except Exception as e:
            print(f"Linux自启动检查失败: {e}")
            return False
    
    def _get_startup_command(self):
        """获取启动命令"""
        # 获取当前脚本路径
        script_path = os.path.abspath(sys.argv[0])
        
        if platform.system() == 'Windows':
            if script_path.endswith('.py'):
                # Python脚本，使用pythonw启动（无控制台窗口）
                pythonw_path = os.path.join(sys.exec_prefix, 'pythonw.exe')
                command = f'"{pythonw_path}" "{script_path}"'
            else:
                # 可执行文件
                command = f'"{script_path}"'
        elif platform.system() == 'Darwin':
            # macOS平台处理
            if script_path.endswith('.py'):
                python_path = sys.executable
                command = f'"{python_path}" "{script_path}"'
            else:
                command = f'"{script_path}"'
        else:
            # Linux平台处理
            if script_path.endswith('.py'):
                python_path = sys.executable
                command = f'"{python_path}" "{script_path}"'
            else:
                command = f'"{script_path}"'
        
        return command
    
    def show_message(self, title, message, icon=QSystemTrayIcon.Information, timeout=3000):
        """显示托盘消息"""
        if self.tray_icon:
            self.tray_icon.showMessage(title, message, icon, timeout)
    
    def hide(self):
        """隐藏托盘图标"""
        if self.tray_icon:
            self.tray_icon.hide()
    
    def show(self):
        """显示托盘图标"""
        if self.tray_icon:
            self.tray_icon.show()


def create_console_tray(auto_hide=True):
    """创建控制台托盘管理器"""
    return ConsoleTrayManager(auto_hide=auto_hide)


def integrate_console_tray(auto_hide=True):
    """集成控制台托盘功能"""
    tray_manager = create_console_tray(auto_hide=auto_hide)
    
    # 连接信号
    tray_manager.show_console.connect(tray_manager.show_console_window)
    tray_manager.hide_console.connect(tray_manager.hide_console_window)
    tray_manager.quit_application.connect(lambda: os._exit(0))
    
    return tray_manager
