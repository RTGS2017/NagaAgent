import sys
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout,
                             QPushButton, QLabel, QSizePolicy, QGraphicsOpacityEffect)
from PyQt5.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QCoreApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor

bg_alpha = 0.8  # 背景透明度
animation_duration = 300  # 动画持续时间
sidebar_width = 80  # 侧边栏宽度
border_radius = 15  # 边框圆角
border_alpha = 50  # 边框透明度

def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容PyInstaller打包环境"""
    try:
        # PyInstaller创建临时文件夹，将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    # 尝试在多个可能的路径中查找文件
    possible_paths = [
        os.path.join(base_path, relative_path),
        os.path.join(base_path, "_internal", relative_path),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", relative_path),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path),
        relative_path
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    # 如果都找不到，返回原始路径（让错误抛出）
    return relative_path

class SidebarItem(QWidget):
    """侧边栏项目组件，包含图标和文字"""

    def __init__(self, icon_path, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.icon_path = icon_path

        # 设置布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        # 创建图标按钮
        self.icon_btn = QPushButton()
        white_pixmap = self.convert_to_white_icon(icon_path)
        self.icon_btn.setIcon(QIcon(white_pixmap))
        self.icon_btn.setIconSize(QSize(40, 40))
        self.icon_btn.setFixedSize(50, 50)
        self.icon_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 50);
            }
        """)

        # 创建文本标签（初始隐藏）
        self.text_label = QLabel(text)
        self.text_label.setStyleSheet("""
            QLabel {
                color: #fff;
                font-size: 12px;
                font-family: 'Arial', sans-serif;
                background: transparent;
            }
        """)
        self.text_label.setAlignment(Qt.AlignCenter)

        # 添加透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self.text_label)
        self.opacity_effect.setOpacity(0.0)  # 初始透明
        self.text_label.setGraphicsEffect(self.opacity_effect)

        # 添加到布局
        self.layout.addWidget(self.icon_btn, alignment=Qt.AlignCenter)
        self.layout.addWidget(self.text_label, alignment=Qt.AlignCenter)

        # 设置大小策略
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # 创建透明度动画
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(animation_duration)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

    def convert_to_white_icon(self, icon_path, size=40):
        """将图标转换为白色版本"""
        # 加载原始图像
        # 获取正确的资源路径
        resolved_path = get_resource_path(icon_path)
        pixmap = QPixmap(resolved_path)

        if pixmap.isNull():
            raise FileNotFoundError(f"无法加载图标文件: {icon_path}({resolved_path})。请检查文件路径是否正确。")
        scaled = pixmap.scaled(
            size, size,
            Qt.KeepAspectRatio,  # 保持宽高比
            Qt.SmoothTransformation  # 平滑缩放
        )
        # 创建白色版本的图标
        white_icon = QPixmap(scaled.size())
        white_icon.fill(Qt.transparent)  # 透明背景
        painter = QPainter(white_icon)

        # 先绘制原始图标作为掩码
        painter.drawPixmap(0, 0, scaled)

        # 切换合成模式：只在已有像素上绘制
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(white_icon.rect(), Qt.white)
        painter.end()

        return white_icon

    def enterEvent(self, event):
        """鼠标进入时显示文本（带动画）"""
        self.animation.stop()
        self.animation.setStartValue(self.opacity_effect.opacity())
        self.animation.setEndValue(1.0)
        self.animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开时隐藏文本（带动画）"""
        self.animation.stop()
        self.animation.setStartValue(self.opacity_effect.opacity())
        self.animation.setEndValue(0.0)
        self.animation.start()
        super().leaveEvent(event)


class SidebarWidget(QWidget):
    """侧边栏Widget，包含四个功能项目"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """设置UI布局"""
        _bg_alpha = int(bg_alpha * 255)

        # 设置侧边栏样式
        self.setStyleSheet(f"""
            QWidget {{
                background: rgba(17, 17, 17, {_bg_alpha});
                border-radius: {border_radius}px;
                border: 1px solid rgba(255, 255, 255, {border_alpha});
            }}
        """)

        # 创建垂直布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 20, 10, 20)
        self.layout.setSpacing(30)

        # 项目配置
        self.items_config = [
            ("ui/img/icons/naga_chat.png", "对话"),
            ("ui/img/icons/mind_map.png", "心智云图"),
            ("ui/img/icons/personality_game.png", "博弈图"),
            ("ui/img/icons/love_adventure.png", "游戏拓展")
        ]

        #self._prepare_icons()

        # 创建并添加项目
        self.items = []
        for icon_path, text in self.items_config:
            item = SidebarItem(icon_path, text)
            self.items.append(item)
            self.layout.addWidget(item, alignment=Qt.AlignCenter)

        # 添加伸缩项
        self.layout.addStretch()

        # 设置固定宽度
        self.setFixedWidth(sidebar_width)

    def _prepare_icons(self):
        """准备图标文件"""
        if not os.path.exists("ui/img/icons"):
            os.makedirs("ui/img/icons")

        for icon_path, text in self.items_config:
            if not os.path.exists(icon_path):
                pixmap = QPixmap(40, 40)
                pixmap.fill(QColor(50, 150, 255, 100))
                painter = QPainter(pixmap)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(pixmap.rect(), Qt.AlignCenter, text[0])
                painter.end()
                pixmap.save(icon_path)

    def set_item_click_handler(self, index, handler):
        """为指定索引的项目设置点击事件处理器"""
        if 0 <= index < len(self.items):
            # 先断开已有的连接
            try:
                self.items[index].icon_btn.clicked.disconnect()
            except:
                pass
            # 绑定新的处理器
            self.items[index].icon_btn.clicked.connect(handler)

    # 支持通过索引访问和设置项目
    def __getitem__(self, index):
        if 0 <= index < len(self.items):
            return self.items[index]
        raise IndexError("侧边栏项目索引超出范围")

    def __setitem__(self, index, handler):
        if callable(handler):
            self.set_item_click_handler(index, handler)
        else:
            raise ValueError("设置的值必须是可调用的函数或方法")


def main():
    """主函数：测试侧边栏功能"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # 创建主窗口
    main_window = QWidget()
    main_window.setWindowTitle("侧边栏演示")
    main_window.setStyleSheet("background-color: #1a1a1a;")
    main_window.resize(800, 600)

    # 创建主布局
    layout = QHBoxLayout(main_window)
    layout.setContentsMargins(50, 50, 50, 50)

    # 添加侧边栏
    sidebar = SidebarWidget()
    layout.addWidget(sidebar)

    # 创建内容显示区域
    content_label = QLabel("当前界面：默认")
    content_label.setStyleSheet("""
        QLabel {
            color: #fff;
            font-size: 24px;
            font-family: 'Arial', sans-serif;
            background: transparent;
        }
    """)
    content_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(content_label, 1)  # 添加伸缩比例，让内容区域占大部分空间

    # 定义更新文本的函数（确保正确更新UI）
    def update_content(text):
        content_label.setText(text)
        # 强制UI更新
        content_label.update()
        QCoreApplication.processEvents()

    # 为每个按钮设置点击事件（使用更可靠的绑定方式）
    sidebar[0] = lambda: update_content("当前界面：娜迦对话")
    sidebar[1] = lambda: update_content("当前界面：心智云图")
    sidebar[2] = lambda: update_content("当前界面：性格博弈")
    sidebar[3] = lambda: update_content("当前界面：恋爱冒险")

    main_window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
