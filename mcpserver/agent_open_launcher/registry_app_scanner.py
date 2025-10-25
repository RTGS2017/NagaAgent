# registry_app_scanner.py # Windows注册表应用扫描器
import platform  # 平台检测 #
import os  # 操作系统 #
from typing import List, Dict, Optional  # 类型 #
import json  # JSON #

# 平台特定导入
if platform.system() == 'Windows':
    import winreg  # Windows注册表 #
else:
    # 在非Windows平台上，winreg模块不可用
    winreg = None

class RegistryAppScanner:
    """Windows注册表应用扫描器 #"""
    
    def __init__(self):
        self.apps_cache = []  # 应用缓存 #
        self._scan_registry()  # 扫描注册表 #
    
    def _scan_registry(self):
        """扫描Windows注册表获取应用信息 #"""
        apps = []

        # 非Windows平台直接返回空列表
        if platform.system() != 'Windows' or winreg is None:
            print(f"注册表扫描功能仅在Windows平台上可用，当前平台: {platform.system()}")
            self.apps_cache = []
            return

        # 扫描HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        app_name = winreg.EnumKey(key, i)
                        if app_name.endswith('.exe'):
                            app_key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{app_name}"
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, app_key_path) as app_key:
                                try:
                                    # 获取默认值（通常是可执行文件路径）
                                    exe_path, _ = winreg.QueryValueEx(app_key, "")
                                    if exe_path and os.path.exists(exe_path):
                                        # 获取应用名称（去掉.exe后缀）
                                        display_name = app_name[:-4] if app_name.endswith('.exe') else app_name

                                        # 尝试从注册表获取更友好的显示名称
                                        try:
                                            friendly_name, _ = winreg.QueryValueEx(app_key, "FriendlyAppName")
                                            if friendly_name:
                                                display_name = friendly_name
                                        except:
                                            pass

                                        apps.append({
                                            "name": display_name,
                                            "path": exe_path,
                                            "type": "registry",
                                            "description": f"从注册表扫描到的应用: {display_name}"
                                        })
                                except:
                                    pass
                    except:
                        continue
        except Exception as e:
            print(f"扫描App Paths注册表失败: {e}")

        # 扫描HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{subkey_name}"
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path) as subkey:
                            try:
                                # 获取显示名称
                                display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                # 获取安装位置
                                install_location, _ = winreg.QueryValueEx(subkey, "InstallLocation")

                                if display_name and install_location:
                                    # 查找可执行文件
                                    exe_files = self._find_exe_files(install_location)
                                    for exe_path in exe_files:
                                        apps.append({
                                            "name": display_name,
                                            "path": exe_path,
                                            "type": "uninstall_registry",
                                            "description": f"从卸载注册表扫描到的应用: {display_name}"
                                        })
                            except:
                                pass
                    except:
                        continue
        except Exception as e:
            print(f"扫描Uninstall注册表失败: {e}")

        # 扫描HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall") as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{subkey_name}"
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey_path) as subkey:
                            try:
                                # 获取显示名称
                                display_name, _ = winreg.QueryValueEx(subkey, "DisplayName")
                                # 获取安装位置
                                install_location, _ = winreg.QueryValueEx(subkey, "InstallLocation")

                                if display_name and install_location:
                                    # 查找可执行文件
                                    exe_files = self._find_exe_files(install_location)
                                    for exe_path in exe_files:
                                        apps.append({
                                            "name": display_name,
                                            "path": exe_path,
                                            "type": "user_uninstall_registry",
                                            "description": f"从用户卸载注册表扫描到的应用: {display_name}"
                                        })
                            except:
                                pass
                    except:
                        continue
        except Exception as e:
            print(f"扫描用户Uninstall注册表失败: {e}")

        # 去重并排序
        unique_apps = {}
        for app in apps:
            name = app["name"]
            if name not in unique_apps or app["type"] == "registry":
                unique_apps[name] = app

        self.apps_cache = list(unique_apps.values())
        # 按名称排序
        self.apps_cache.sort(key=lambda x: x["name"].lower())

        print(f"✅ 从注册表扫描到 {len(self.apps_cache)} 个应用")
    
    def _find_exe_files(self, directory: str) -> List[str]:
        """在指定目录中查找可执行文件 #"""
        exe_files = []
        if not os.path.exists(directory):
            return exe_files
        
        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.exe'):
                        exe_path = os.path.join(root, file)
                        if os.path.exists(exe_path):
                            exe_files.append(exe_path)
        except:
            pass
        
        return exe_files
    
    def get_apps(self) -> List[Dict]:
        """获取扫描到的应用列表 #"""
        return self.apps_cache.copy()
    
    def find_app_by_name(self, name: str) -> Optional[Dict]:
        """根据名称查找应用 #"""
        name_lower = name.lower()
        for app in self.apps_cache:
            if app["name"].lower() == name_lower:
                return app
        return None
    
    def refresh_apps(self):
        """刷新应用列表 #"""
        self._scan_registry()
    
    def get_app_info_for_llm(self) -> Dict:
        """获取供LLM选择的应用信息格式 #"""
        apps = self.get_apps()
        app_list = []
        
        for app in apps:
            app_list.append({
                "name": app["name"],
                "description": app["description"],
                "type": app["type"]
            })
        
        return {
            "total_count": len(app_list),
            "apps": app_list,
            "usage_format": {
                "tool_name": "open",
                "app": "应用名称（从上述列表中选择）",
                "args": "启动参数（可选）"
            },
            "example": {
                "tool_name": "open",
                "app": "notepad",
                "args": ""
            }
        }

# 全局实例 #
_registry_scanner = None

def get_registry_scanner() -> RegistryAppScanner:
    """获取全局注册表扫描器实例 #"""
    global _registry_scanner
    if _registry_scanner is None:
        _registry_scanner = RegistryAppScanner()
    return _registry_scanner

def refresh_registry_apps():
    """刷新注册表应用列表 #"""
    scanner = get_registry_scanner()
    scanner.refresh_apps()
