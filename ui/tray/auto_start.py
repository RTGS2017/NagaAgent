"""
自启动管理模块
提供系统自启动功能的完整实现
"""
import os
import sys
import platform
import subprocess
from pathlib import Path

# 平台特定导入
if platform.system() == 'Windows':
    import winreg
else:
    # 在非Windows平台上，winreg模块不可用
    winreg = None


class AutoStartManager:
    """自启动管理器"""
    
    def __init__(self, app_name="NagaAgent4.0"):
        self.app_name = app_name
        self.registry_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    def is_enabled(self):
        """检查是否已启用自启动"""
        if platform.system() != 'Windows' or winreg is None:
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_key,
                0, winreg.KEY_READ
            )
            winreg.QueryValueEx(key, self.app_name)
            winreg.CloseKey(key)
            return True
        except:
            return False
    
    def enable(self):
        """启用自启动"""
        if platform.system() != 'Windows' or winreg is None:
            print("自启动功能仅在Windows平台上可用")
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_key,
                0, winreg.KEY_SET_VALUE
            )

            # 获取启动命令
            command = self._get_startup_command()

            winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, command)
            winreg.CloseKey(key)
            return True

        except Exception as e:
            print(f"启用自启动失败: {e}")
            return False
    
    def disable(self):
        """禁用自启动"""
        if platform.system() != 'Windows' or winreg is None:
            print("自启动功能仅在Windows平台上可用")
            return False

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.registry_key,
                0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, self.app_name)
            winreg.CloseKey(key)
            return True

        except Exception as e:
            print(f"禁用自启动失败: {e}")
            return False
    
    def _get_startup_command(self):
        """获取启动命令"""
        # 获取当前脚本路径
        script_path = os.path.abspath(sys.argv[0])
        
        if script_path.endswith('.py'):
            # Python脚本，使用pythonw启动（无控制台窗口）
            pythonw_path = os.path.join(sys.exec_prefix, 'pythonw.exe')
            command = f'"{pythonw_path}" "{script_path}"'
        else:
            # 可执行文件
            command = f'"{script_path}"'
        
        return command
    
    def toggle(self):
        """切换自启动状态"""
        if self.is_enabled():
            return self.disable()
        else:
            return self.enable()
    
    def get_status(self):
        """获取自启动状态信息"""
        enabled = self.is_enabled()
        command = self._get_startup_command() if enabled else ""
        
        return {
            "enabled": enabled,
            "command": command,
            "app_name": self.app_name
        }


class TaskSchedulerManager:
    """任务计划程序管理器"""
    
    def __init__(self, task_name="NagaAgent4.0"):
        self.task_name = task_name
    
    def create_task(self, script_path):
        """创建开机启动任务"""
        try:
            # 构建schtasks命令
            command = [
                "schtasks", "/create", "/tn", self.task_name,
                "/tr", f'"{script_path}"',
                "/sc", "onlogon",
                "/ru", "SYSTEM",
                "/f"
            ]
            
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            print(f"创建任务失败: {e}")
            return False
    
    def delete_task(self):
        """删除开机启动任务"""
        try:
            command = ["schtasks", "/delete", "/tn", self.task_name, "/f"]
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            print(f"删除任务失败: {e}")
            return False
    
    def task_exists(self):
        """检查任务是否存在"""
        try:
            command = ["schtasks", "/query", "/tn", self.task_name]
            result = subprocess.run(command, capture_output=True, text=True)
            return result.returncode == 0
            
        except Exception as e:
            return False


class StartupFolderManager:
    """启动文件夹管理器"""
    
    def __init__(self, app_name="NagaAgent4.0"):
        self.app_name = app_name
        self.startup_folder = self._get_startup_folder()
        self.shortcut_path = os.path.join(self.startup_folder, f"{app_name}.lnk")
    
    def _get_startup_folder(self):
        """获取启动文件夹路径"""
        if platform.system() == 'Windows' and winreg is not None:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
                )
                startup_folder = winreg.QueryValueEx(key, "Startup")[0]
                winreg.CloseKey(key)
                return startup_folder
            except:
                pass

        # 默认启动文件夹（Windows）
        if platform.system() == 'Windows':
            return os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        elif platform.system() == 'Darwin':
            # macOS启动文件夹
            return os.path.expanduser("~/Library/LaunchAgents")
        else:
            # Linux启动文件夹
            return os.path.expanduser("~/.config/autostart")
    
    def create_shortcut(self, target_path):
        """创建快捷方式"""
        if platform.system() != 'Windows':
            print(f"快捷方式创建功能仅在Windows平台上可用，在 {platform.system()} 上跳过")
            return False

        try:
            import winshell
            from win32com.client import Dispatch

            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(self.shortcut_path)
            shortcut.Targetpath = target_path
            shortcut.WorkingDirectory = os.path.dirname(target_path)
            shortcut.save()
            return True

        except Exception as e:
            print(f"创建快捷方式失败: {e}")
            return False
    
    def remove_shortcut(self):
        """删除快捷方式"""
        try:
            if os.path.exists(self.shortcut_path):
                os.remove(self.shortcut_path)
                return True
            return False
            
        except Exception as e:
            print(f"删除快捷方式失败: {e}")
            return False
    
    def shortcut_exists(self):
        """检查快捷方式是否存在"""
        return os.path.exists(self.shortcut_path)
    
    def enable(self, target_path):
        """启用自启动（通过启动文件夹）"""
        return self.create_shortcut(target_path)
    
    def disable(self):
        """禁用自启动（通过启动文件夹）"""
        return self.remove_shortcut()
    
    def is_enabled(self):
        """检查是否已启用"""
        return self.shortcut_exists()


def get_auto_start_manager(method="registry"):
    """获取自启动管理器实例"""
    if method == "registry":
        return AutoStartManager()
    elif method == "task_scheduler":
        return TaskSchedulerManager()
    elif method == "startup_folder":
        return StartupFolderManager()
    else:
        return AutoStartManager()  # 默认使用注册表方式
