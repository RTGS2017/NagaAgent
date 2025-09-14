#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理器 - 统一管理配置热更新和模块重新加载
参考的配置热更新机制
"""

import os
import sys
import json
import threading
import time
from typing import Dict, Any, List, Callable, Optional
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from .config import config, hot_reload_config, add_config_listener, remove_config_listener

class ConfigManager:
    """配置管理器 - 统一管理配置热更新
    
    功能特性:
    - 配置热更新：无需重启应用即可使配置变更生效
    - 模块重新加载：配置变更后自动重新加载相关模块
    - 配置监视器：自动监视配置文件变化
    - 配置快照：支持配置的保存和恢复
    - 错误处理：完善的错误处理和日志记录
    """
    
    def __init__(self):
        # 模块管理
        self._modules_to_reload: List[str] = []
        self._reload_callbacks: List[Callable] = []
        
        # 配置监视器
        self._config_watcher_thread: Optional[threading.Thread] = None
        self._stop_watching = False
        
        # 注册配置变更监听器
        add_config_listener(self._on_config_changed)
        print("✅ 配置管理器初始化完成")
        
    def register_module_reload(self, module_name: str):
        """注册需要重新加载的模块"""
        if module_name not in self._modules_to_reload:
            self._modules_to_reload.append(module_name)
            print(f"注册模块重新加载: {module_name}")
    
    def register_reload_callback(self, callback: Callable):
        """注册重新加载回调函数"""
        self._reload_callbacks.append(callback)
        print(f"注册重新加载回调: {callback.__name__ if hasattr(callback, '__name__') else 'anonymous'}")
    
    def _on_config_changed(self):
        """配置变更时的处理"""
        print("🔄 配置已变更，开始重新加载相关模块...")
        
        # 执行所有重新加载回调
        self._execute_reload_callbacks()
        
        # 重新加载注册的模块
        self._reload_registered_modules()
        
        print("✅ 配置变更处理完成")
    
    def _execute_reload_callbacks(self):
        """执行所有重新加载回调"""
        if not self._reload_callbacks:
            print("ℹ️ 没有注册的重新加载回调")
            return
        
        print(f"🔄 执行 {len(self._reload_callbacks)} 个重新加载回调...")
        
        for i, callback in enumerate(self._reload_callbacks, 1):
            try:
                callback()
                callback_name = callback.__name__ if hasattr(callback, '__name__') else f'callback_{i}'
                print(f"✅ 回调执行成功: {callback_name}")
            except Exception as e:
                callback_name = callback.__name__ if hasattr(callback, '__name__') else f'callback_{i}'
                print(f"❌ 回调执行失败: {callback_name} - {e}")
    
    def _reload_registered_modules(self):
        """重新加载注册的模块"""
        if not self._modules_to_reload:
            print("ℹ️ 没有注册的模块需要重新加载")
            return
        
        print(f"🔄 重新加载 {len(self._modules_to_reload)} 个模块...")
        
        for module_name in self._modules_to_reload:
            self._reload_single_module(module_name)
    
    def _reload_single_module(self, module_name: str):
        """重新加载单个模块"""
        try:
            if module_name not in sys.modules:
                print(f"⚠️ 模块 {module_name} 未加载，跳过重新加载")
                return
            
            module = sys.modules[module_name]
            if not hasattr(module, 'reload_config'):
                print(f"⚠️ 模块 {module_name} 没有 reload_config 方法，跳过重新加载")
                return
            
            module.reload_config()
            print(f"✅ 模块重新加载成功: {module_name}")
            
        except Exception as e:
            print(f"❌ 模块重新加载失败: {module_name} - {e}")
    
    def start_config_watcher(self, config_file: str = None):
        """启动配置文件监视器"""
        if self._config_watcher_thread and self._config_watcher_thread.is_alive():
            return
        
        if config_file is None:
            config_file = str(Path(__file__).parent.parent / "config.json")
        
        self._stop_watching = False
        self._config_watcher_thread = threading.Thread(
            target=self._watch_config_file,
            args=(config_file,),
            daemon=True
        )
        self._config_watcher_thread.start()
        print(f"🔍 配置文件监视器已启动: {config_file}")
    
    def stop_config_watcher(self):
        """停止配置文件监视器"""
        self._stop_watching = True
        if self._config_watcher_thread:
            self._config_watcher_thread.join(timeout=1)
        print("🔍 配置文件监视器已停止")
    
    def _watch_config_file(self, config_file: str):
        """监视配置文件变化"""
        last_modified = 0
        
        while not self._stop_watching:
            try:
                if os.path.exists(config_file):
                    current_modified = os.path.getmtime(config_file)
                    if current_modified > last_modified:
                        last_modified = current_modified
                        print(f"📝 检测到配置文件变更: {config_file}")
                        
                        # 等待文件写入完成
                        time.sleep(0.1)
                        
                        # 重新加载配置
                        hot_reload_config()
                
                time.sleep(1)  # 每秒检查一次
            except Exception as e:
                print(f"配置文件监视器错误: {e}")
                time.sleep(5)  # 出错时等待更长时间
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """更新配置并触发热更新
        
        Args:
            updates: 要更新的配置字典，支持嵌套结构
            
        Returns:
            bool: 更新是否成功
        """
        try:
            print(f"🔄 开始更新配置，共 {len(updates)} 项...")
            
            # 验证配置文件存在性
            config_path = str(Path(__file__).parent.parent / "config.json")
            if not os.path.exists(config_path):
                print(f"❌ 配置文件不存在: {config_path}")
                print(f"❌ 当前工作目录: {os.getcwd()}")
                print(f"❌ 配置文件父目录: {Path(__file__).parent.parent}")
                return False
            
            # 加载当前配置
            config_data = self._load_config_file(config_path)
            if config_data is None:
                return False
            
            # 递归更新配置
            self._recursive_update(config_data, updates)
            
            # 保存配置
            if not self._save_config_file(config_path, config_data):
                return False
            
            # 触发热更新
            hot_reload_config()
            
            # 等待配置重新加载完成
            time.sleep(0.1)
            
            print(f"✅ 配置更新成功: {len(updates)} 项")
            return True
            
        except Exception as e:
            print(f"❌ 配置更新失败: {e}")
            return False
    
    def _load_config_file(self, config_path: str) -> Optional[Dict[str, Any]]:
        """加载配置文件"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            return None
    
    def _save_config_file(self, config_path: str, config_data: Dict[str, Any]) -> bool:
        """保存配置文件"""
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ 保存配置文件失败: {e}")
            return False
    
    def _recursive_update(self, target: Dict[str, Any], updates: Dict[str, Any]):
        """递归更新配置字典"""
        for key, value in updates.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # 递归更新嵌套字典
                self._recursive_update(target[key], value)
            else:
                # 直接更新值
                target[key] = value
    
    def get_config_snapshot(self) -> Dict[str, Any]:
        """获取配置快照"""
        # 直接读取config.json文件，避免序列化问题
        try:
            config_path = str(Path(__file__).parent.parent / "config.json")
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 获取配置快照失败: {e}")
            # 如果读取失败，返回一个基本的配置结构
            return {
                "system": {"version": "3.0"},
                "api": {"api_key": ""},
                "api_server": {"enabled": True},
                "grag": {"enabled": False},
                "handoff": {"max_loop_stream": 5},
                "browser": {"playwright_headless": False},
                "tts": {"port": 5048},
                "weather": {"api_key": ""},
                "mqtt": {"enabled": False},
                "ui": {"user_name": "用户"},
                "naga_portal": {"portal_url": "https://naga.furina.chat/"},
                "online_search": {"Bocha_API_KEY": "-"}
            }
    
    def restore_config_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        """恢复配置快照"""
        try:
            config_path = str(Path(__file__).parent.parent / "config.json")
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            
            hot_reload_config()
            print("✅ 配置快照恢复成功")
            return True
        except Exception as e:
            print(f"❌ 配置快照恢复失败: {e}")
            return False

# 全局配置管理器实例
config_manager = ConfigManager()

# ============================================================================
# 便捷函数 - 提供简化的API接口
# ============================================================================

def register_module_reload(module_name: str):
    """注册模块重新加载
    
    Args:
        module_name: 模块名称，如 "voice.voice_integration"
        
    Example:
        >>> register_module_reload("voice.voice_integration")
        >>> register_module_reload("apiserver.api_server")
    """
    config_manager.register_module_reload(module_name)

def register_reload_callback(callback: Callable):
    """注册重新加载回调
    
    Args:
        callback: 配置变更时要执行的回调函数
        
    Example:
        >>> def my_callback():
        ...     print("配置已变更")
        >>> register_reload_callback(my_callback)
    """
    config_manager.register_reload_callback(callback)

def update_config(updates: Dict[str, Any]) -> bool:
    """更新配置并触发热更新
    
    Args:
        updates: 要更新的配置字典，支持嵌套结构
        
    Returns:
        bool: 更新是否成功
        
    Example:
        >>> success = update_config({
        ...     "system": {"debug": True},
        ...     "api": {"temperature": 0.8}
        ... })
    """
    return config_manager.update_config(updates)

def start_config_watcher(config_file: str = None):
    """启动配置监视器
    
    Args:
        config_file: 要监视的配置文件路径
        
    Example:
        >>> start_config_watcher("config.json")
    """
    config_manager.start_config_watcher(config_file)

def stop_config_watcher():
    """停止配置监视器
    
    Example:
        >>> stop_config_watcher()
    """
    config_manager.stop_config_watcher()

def get_config_snapshot() -> Dict[str, Any]:
    """获取当前配置快照
    
    Returns:
        Dict[str, Any]: 当前配置的完整快照
        
    Example:
        >>> snapshot = get_config_snapshot()
        >>> print(f"配置包含 {len(snapshot)} 个顶级配置项")
    """
    return config_manager.get_config_snapshot()

def restore_config_snapshot(snapshot: Dict[str, Any]) -> bool:
    """恢复配置快照
    
    Args:
        snapshot: 要恢复的配置快照
        
    Returns:
        bool: 恢复是否成功
        
    Example:
        >>> snapshot = get_config_snapshot()
        >>> # 修改配置...
        >>> success = restore_config_snapshot(snapshot)
    """
    return config_manager.restore_config_snapshot(snapshot)

if __name__ == "__main__":
    # 测试配置管理器
    print("🧪 测试配置管理器...")
    
    # 注册一些测试回调
    def test_callback1():
        print("测试回调1执行")
    
    def test_callback2():
        print("测试回调2执行")
    
    register_reload_callback(test_callback1)
    register_reload_callback(test_callback2)
    
    # 测试配置更新
    test_updates = {
        "system": {
            "debug": True
        }
    }
    
    success = update_config(test_updates)
    print(f"配置更新测试: {'成功' if success else '失败'}")
    
    # 启动配置监视器
    start_config_watcher()
    
    print("配置管理器测试完成")
