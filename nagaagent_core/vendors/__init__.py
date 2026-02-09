"""第三方库代理模块集合：统一从 nagaagent_core.vendors.* 导入"""  #

__all__ = [
    # 数值/科学计算 #
    "numpy",
    # GUI/多媒体/浏览器 #
    "playwright", "html2text", "pil",
    # 常用第三方统一入口 #
    "cv2", "pyautogui", "pytesseract", "paho_mqtt",
    # 系统控制 #
    "screen_brightness_control", "pycaw", "comtypes",
    # 新增依赖 #
    "charset_normalizer", "json5", "markdown", "pyneo",
]

