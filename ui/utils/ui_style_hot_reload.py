"""UI 风格配置热更新辅助模块"""

from typing import List
from weakref import WeakSet

from system.config import add_config_listener
from nagaagent_core.vendors.PyQt5.QtCore import QTimer


_windows: "WeakSet[object]" = WeakSet()
_registered = False


def _schedule_apply(window):
    try:
        if hasattr(window, "apply_ui_style"):
            QTimer.singleShot(0, window.apply_ui_style)
    except RuntimeError:
        # 窗口可能已经销毁，忽略
        pass


def _on_config_changed():
    for window in list(_windows):
        _schedule_apply(window)


def register_window(window):
    """注册需要响应 UI 风格热更新的窗口"""
    global _registered
    _windows.add(window)
    _schedule_apply(window)
    if not _registered:
        add_config_listener(_on_config_changed)
        _registered = True
