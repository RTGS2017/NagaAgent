import os
import json
from nagaagent_core.vendors.PyQt5.QtWidgets import (
    QWidget, QStackedLayout, QLabel, QSizePolicy, QPushButton,
    QVBoxLayout, QScrollArea, QHBoxLayout
)  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QRect  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QPen  # 统一入口 #

from system.config import config, logger
# 导入独立的Live2D模块
try:
    from ..live2d import Live2DWidget
    from ..live2d.config_dialog import Live2DConfigDialog
    LIVE2D_AVAILABLE = True
except ImportError as e:
    LIVE2D_AVAILABLE = False
    print(f"Live2D模块未找到，将使用图片模式: {e}")


class Live2DSideWidget(QWidget):
    """支持Live2D和图片的侧栏Widget"""
    
    # 信号定义
    model_loaded = pyqtSignal(bool)  # 模型加载状态信号
    error_occurred = pyqtSignal(str)  # 错误信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # 从配置中读取透明度设置，避免硬编码
        try:
            import sys, os
            sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
            from system.config import config
            # 使用配置中的透明度，转换为0-255范围
            self.bg_alpha = int(config.ui.bg_alpha * 255)  # 背景透明度
            self.border_alpha = 50  # 边框透明度（保持固定值）
        except Exception:
            # 如果配置加载失败，使用默认值
            self.bg_alpha = 200  # 背景透明度
            self.border_alpha = 50  # 边框透明度
        self.glow_intensity = 0  # 发光强度
        self.is_glowing = False
        
        # 显示模式：'live2d' 或 'image'
        self.display_mode = 'image'
        self.live2d_model_path = None
        self.fallback_image_path = None
        self._original_pixmap = None  # 原图缓存，防止重复缩放导致画质下降 #
        
        # 创建堆叠布局
        self.stack_layout = QStackedLayout(self)
        self.stack_layout.setContentsMargins(5, 5, 5, 5)
        
        # 创建Live2D Widget
        if LIVE2D_AVAILABLE:
            self.live2d_widget = Live2DWidget(self)
            self.live2d_widget.setStyleSheet('background: transparent; border: none;')
        else:
            self.live2d_widget = None
        
        # 创建图片显示Widget
        self.image_widget = QLabel(self)
        self.image_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_widget.setAlignment(Qt.AlignCenter)
        self.image_widget.setMinimumSize(1, 1)
        self.image_widget.setMaximumSize(16777215, 16777215)
        self.image_widget.setStyleSheet('background: transparent; border: none;')
        
        # 添加到堆叠布局
        self.stack_layout.addWidget(self.image_widget)  # index 0: 图片模式
        if self.live2d_widget:
            self.stack_layout.addWidget(self.live2d_widget)  # index 1: Live2D模式

        # Live2D相关配置
        self.live2d_enabled = config.live2d.enabled  # 是否启用Live2D
        self.live2d_model_path = config.live2d.model_path  # Live2D模型路径
        # 默认显示图片模式
        self.stack_layout.setCurrentIndex(0)
        
        # 设置鼠标指针
        self.setCursor(Qt.PointingHandCursor)

        # 创建Live2D/图片模式切换按钮（放在右上角）
        self.toggle_button = QPushButton("🎭", self)
        self.toggle_button.setFixedSize(45, 30)  # 设置固定大小
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 100, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: rgba(150, 150, 150, 200);
                border: 2px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(200, 200, 200, 220);
            }
        """)
        self.toggle_button.setToolTip("切换 Live2D/图片 模式")
        self.toggle_button.clicked.connect(self.toggle_display_mode)
        # 初始设置按钮位置（会在resizeEvent和showEvent中更新）
        self.toggle_button.move(10, 10)  # 先放在左上角，后续会调整
        # 确保按钮显示并在最上层
        self.toggle_button.show()
        self.toggle_button.raise_()

        # 创建配置按钮（在切换按钮下面）
        self.config_button = QPushButton("⚙️", self)
        self.config_button.setFixedSize(45, 30)
        self.config_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 100, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: rgba(150, 150, 150, 200);
                border: 2px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(200, 200, 200, 220);
            }
        """)
        self.config_button.setToolTip("配置Live2D动作")
        self.config_button.clicked.connect(self.open_config_dialog)
        self.config_button.hide()  # 默认隐藏，Live2D模式时显示

        # 创建展开按钮（在配置按钮下面）
        self.expand_button = QPushButton("▼", self)
        self.expand_button.setFixedSize(45, 30)
        self.expand_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 100, 180);
                color: white;
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: rgba(150, 150, 150, 200);
                border: 2px solid rgba(255, 255, 255, 150);
            }
            QPushButton:pressed {
                background-color: rgba(200, 200, 200, 220);
            }
        """)
        self.expand_button.setToolTip("展开/收起动作列表")

        # 使用lambda确保正确连接
        self.expand_button.clicked.connect(lambda: self.on_expand_clicked())
        # 添加pressed信号测试
        self.expand_button.pressed.connect(lambda: logger.info("展开按钮 pressed 信号"))
        # 添加released信号测试
        self.expand_button.released.connect(lambda: logger.info("展开按钮 released 信号"))
        logger.info("展开按钮已创建并连接信号")
        self.expand_button.hide()  # 默认隐藏，Live2D模式时显示

        # 创建动作列表面板
        self.actions_panel = QWidget(self)
        self.actions_panel.setStyleSheet("""
            QWidget {
                background-color: rgba(50, 50, 50, 200);
                border: 1px solid rgba(255, 255, 255, 100);
                border-radius: 5px;
            }
        """)
        self.actions_panel.hide()  # 默认隐藏

        # 动作列表布局
        self.actions_layout = QVBoxLayout(self.actions_panel)
        self.actions_layout.setContentsMargins(5, 5, 5, 5)
        self.actions_layout.setSpacing(2)

        # 动作列表展开状态
        self.actions_expanded = False

        # 保存的动作配置
        self.saved_actions = []
        self.load_action_config()

    def initialize_live2d(self):
        """初始化Live2D - 优化版"""
        import os
        import glob

        logger.info("开始初始化Live2D...")

        if not self.live2d_enabled:
            logger.info("Live2D功能未启用")
            return

        if not self.live2d_model_path:
            logger.warning("Live2D模型路径未配置")
            return

        model_path = self.live2d_model_path

        # 转换为绝对路径（兼容非 ASCII 目录）
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.isabs(model_path):
            model_path = os.path.normpath(os.path.join(base_dir, model_path))
        else:
            model_path = os.path.normpath(model_path)

        # 检查文件是否存在
        if os.path.exists(model_path):
            logger.info(f"准备加载Live2D模型: {model_path}")
            success = self.set_live2d_model(model_path)
            if not success:
                logger.warning("Live2D模型加载失败，回退到图片模式")
                self.fallback_to_image_mode()
        else:
            logger.warning(f"Live2D模型文件不存在: {model_path}")
            # 尝试查找其他可用的模型
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_dirs = glob.glob(os.path.join(base_dir, 'ui/live2d/live2d_models/*/'))
            for model_dir in model_dirs:
                model_files = glob.glob(os.path.join(model_dir, '*.model3.json'))
                if model_files:
                    logger.info(f"找到备选模型: {model_files[0]}")
                    success = self.set_live2d_model(model_files[0])
                    if success:
                        return
            # 没有找到任何模型，回退到图片模式
            self.fallback_to_image_mode()

    def toggle_display_mode(self):
        """切换Live2D和图片显示模式"""
        if not LIVE2D_AVAILABLE:
            print("Live2D功能不可用")
            return

        if self.display_mode == 'image':
            # 尝试切换到Live2D模式
            if self.live2d_model_path and os.path.exists(self.live2d_model_path):
                success = self.set_live2d_model(self.live2d_model_path)
                if success:
                    print("已切换到Live2D模式")
                    self.toggle_button.setText("📷")  # 显示相机图标
                else:
                    print("切换到Live2D模式失败")
            else:
                # 如果没有配置模型路径，尝试使用默认模型
                self.initialize_live2d()
                if self.display_mode == 'live2d':
                    self.toggle_button.setText("📷")
        else:
            # 切换到图片模式
            self.fallback_to_image_mode()
            print("已切换到图片模式")
            self.toggle_button.setText("🎭")  # 显示面具图标

        # 最后再确保按钮在最上层并可见
        self.toggle_button.raise_()
        self.toggle_button.setVisible(True)

    def set_background_alpha(self, alpha):
        """设置背景透明度"""
        self.bg_alpha = alpha
        self.update()
    
    def set_border_alpha(self, alpha):
        """设置边框透明度"""
        self.border_alpha = alpha
        self.update()
    
    def set_glow_intensity(self, intensity):
        """设置发光强度 0-20"""
        self.glow_intensity = max(0, min(20, intensity))
        self.update()
    
    def start_glow_animation(self):
        """开始发光动画"""
        self.is_glowing = True
        self.update()
    
    def stop_glow_animation(self):
        """停止发光动画"""
        self.is_glowing = False
        self.glow_intensity = 0
        self.update()
    
    def set_live2d_model(self, model_path):
        """设置Live2D模型路径"""
        self.live2d_model_path = model_path

        # 检查文件是否存在
        if not os.path.exists(model_path):
            self.error_occurred.emit(f"Live2D模型文件不存在: {model_path}")
            return False

        # 尝试加载Live2D模型
        if LIVE2D_AVAILABLE and self.live2d_widget:
            success = self.live2d_widget.load_model(model_path)
            if success:
                self.display_mode = 'live2d'
                self.stack_layout.setCurrentIndex(1)  # 切换到Live2D模式
                # 更新按钮文字为相机图标
                self.toggle_button.setText("📷")
                # 确保按钮在最上层
                self.toggle_button.raise_()
                self.toggle_button.setVisible(True)
                # 显示Live2D控制按钮
                self.config_button.setVisible(True)
                self.config_button.raise_()
                self.expand_button.setVisible(True)
                self.expand_button.raise_()

                # 使用定时器确保按钮显示
                def ensure_buttons_visible():
                    self.config_button.setVisible(True)
                    self.config_button.raise_()
                    self.expand_button.setVisible(True)
                    self.expand_button.raise_()
                    # 确保按钮可以接收鼠标事件
                    self.expand_button.setEnabled(True)
                    self.expand_button.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                    logger.info(f"Live2D控制按钮状态检查 - config: {self.config_button.isVisible()}, expand: {self.expand_button.isVisible()}, expand_enabled: {self.expand_button.isEnabled()}")

                from nagaagent_core.vendors.PyQt5.QtCore import QTimer as QT
                QT.singleShot(100, ensure_buttons_visible)

                # 确保按钮位置正确
                if self.width() > 0:
                    button_x = self.width() - self.toggle_button.width() - 10
                    button_y = self.toggle_button.y() + self.toggle_button.height() + 5
                    self.config_button.move(button_x, button_y)
                    button_y += self.config_button.height() + 5
                    self.expand_button.move(button_x, button_y)
                    logger.info(f"按钮位置已更新 - config: ({button_x}, {button_y-35}), expand: ({button_x}, {button_y})")
                self.model_loaded.emit(True)
                print(f"切换到Live2D模式: {model_path}")
                return True
            else:
                self.error_occurred.emit(f"Live2D模型加载失败: {model_path}")
        else:
            self.error_occurred.emit("Live2D功能不可用")

        # Live2D加载失败，回退到图片模式
        self.fallback_to_image_mode()
        return False
    
    def set_fallback_image(self, image_path):
        """设置回退图片路径"""
        self.fallback_image_path = image_path
        self.load_image(image_path)
    
    def fallback_to_image_mode(self):
        """回退到图片模式"""
        self.display_mode = 'image'
        self.stack_layout.setCurrentIndex(0)  # 切换到图片模式

        # 更新按钮文字为面具图标
        self.toggle_button.setText("🎭")
        # 确保按钮在最上层
        self.toggle_button.raise_()
        self.toggle_button.setVisible(True)
        # 隐藏Live2D控制按钮
        self.config_button.hide()
        self.expand_button.hide()
        self.actions_panel.hide()
        self.actions_expanded = False

        # 如果有回退图片，加载它
        if self.fallback_image_path and os.path.exists(self.fallback_image_path):
            self.load_image(self.fallback_image_path)
        else:
            # 使用默认图片
            default_image = os.path.join(os.path.dirname(__file__), 'img/standby.png')
            if os.path.exists(default_image):
                self.load_image(default_image)

        self.model_loaded.emit(False)
        print("已回退到图片模式")
    
    def load_image(self, image_path):
        """加载图片"""
        if not os.path.exists(image_path):
            print(f"图片文件不存在: {image_path}")
            return False
        
        try:
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                print(f"无法加载图片: {image_path}")
                return False
            
            # 缓存原图并自适应缩放
            self._original_pixmap = pixmap  # 缓存原图 #
            self.resize_image(self._original_pixmap)
            return True
            
        except Exception as e:
            print(f"图片加载失败: {e}")
            return False
    
    def resize_image(self, pixmap=None):
        """调整图片大小"""
        if pixmap is None:
            pixmap = self._original_pixmap  # 始终从原图缩放 #
        if pixmap is None:
            return
        
        if pixmap.isNull():
            return
        
        # 获取可用空间（减去边距）
        available_width = self.width() - 10
        available_height = self.height() - 10
        
        if available_width > 50 and available_height > 50:
            # 缩放图片以填满空间
            scaled_pixmap = pixmap.scaled(
                available_width, available_height,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            self.image_widget.setPixmap(scaled_pixmap)
            self.image_widget.resize(available_width, available_height)
    
    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)

        # 更新所有按钮位置，保持在右上角竖向排列
        if hasattr(self, 'toggle_button') and self.width() > 0:
            button_x = self.width() - self.toggle_button.width() - 10

            # 切换按钮
            button_y = 10
            self.toggle_button.move(button_x, button_y)
            self.toggle_button.setVisible(True)
            self.toggle_button.raise_()

            # 配置按钮（在切换按钮下面）
            if hasattr(self, 'config_button'):
                button_y += self.toggle_button.height() + 5
                self.config_button.move(button_x, button_y)
                if self.display_mode == 'live2d':
                    self.config_button.setVisible(True)
                    self.config_button.raise_()

            # 展开按钮（在配置按钮下面）
            if hasattr(self, 'expand_button'):
                button_y += self.config_button.height() + 5
                self.expand_button.move(button_x, button_y)
                if self.display_mode == 'live2d':
                    self.expand_button.setVisible(True)
                    self.expand_button.raise_()

            # 动作面板（在展开按钮下面）
            if hasattr(self, 'actions_panel'):
                self.actions_panel.setFixedWidth(150)
                panel_x = self.width() - self.actions_panel.width() - 10
                panel_y = self.expand_button.y() + self.expand_button.height() + 5
                self.actions_panel.move(panel_x, panel_y)

        # 延迟调整图片大小，避免频繁重绘
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._delayed_resize)

        self._resize_timer.start(50)  # 50ms后执行调整

    def showEvent(self, event):
        """显示事件 - 用于首次显示时设置按钮位置"""
        super().showEvent(event)

        # 首次显示时设置按钮位置
        if hasattr(self, 'toggle_button') and self.width() > 0:
            button_x = self.width() - self.toggle_button.width() - 10
            button_y = 10
            self.toggle_button.move(button_x, button_y)
            self.toggle_button.setVisible(True)
            self.toggle_button.raise_()

            # 配置按钮（在切换按钮下面）
            if hasattr(self, 'config_button') and self.display_mode == 'live2d':
                button_y += self.toggle_button.height() + 5
                self.config_button.move(button_x, button_y)
                self.config_button.raise_()

            # 展开按钮（在配置按钮下面）
            if hasattr(self, 'expand_button') and self.display_mode == 'live2d':
                button_y += self.config_button.height() + 5 if hasattr(self, 'config_button') else self.toggle_button.height() + 5
                self.expand_button.move(button_x, button_y)
                self.expand_button.raise_()

        # 首次显示时尝试初始化Live2D - 已删除重复初始化
        # if not hasattr(self, '_initialized'):
        #     self._initialized = True
        #     if self.live2d_enabled and LIVE2D_AVAILABLE:
        #         # 延迟初始化Live2D，确保窗口完全显示
        #         from nagaagent_core.vendors.PyQt5.QtCore import QTimer as QT
        #         QT.singleShot(500, self.initialize_live2d)
    
    def _delayed_resize(self):
        """延迟执行的大小调整"""
        if self.display_mode == 'image':
            self.resize_image()
        elif self.display_mode == 'live2d' and self.live2d_widget and self.live2d_widget.is_model_loaded():
            # Live2D Widget会自动处理大小调整
            pass
    
    def paintEvent(self, event):
        """自定义绘制方法"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        rect = self.rect()
        
        # 绘制发光效果（如果有）
        if self.glow_intensity > 0:
            glow_rect = rect.adjusted(-2, -2, 2, 2)
            glow_color = QColor(100, 200, 255, self.glow_intensity)
            painter.setPen(QPen(glow_color, 2))
            painter.setBrush(QBrush(Qt.NoBrush))
            painter.drawRoundedRect(glow_rect, 17, 17)
        
        # 绘制主要背景
        bg_color = QColor(17, 17, 17, self.bg_alpha)
        painter.setBrush(QBrush(bg_color))
        
        # 绘制边框
        border_color = QColor(255, 255, 255, self.border_alpha)
        painter.setPen(QPen(border_color, 1))
        
        # 绘制圆角矩形
        painter.drawRoundedRect(rect, 15, 15)
        
        super().paintEvent(event)
    
    def get_display_mode(self):
        """获取当前显示模式"""
        return self.display_mode
    
    def is_live2d_available(self):
        """检查Live2D是否可用"""
        return LIVE2D_AVAILABLE
    
    def cleanup(self):
        """清理资源"""
        if self.live2d_widget:
            self.live2d_widget.cleanup()
    
    def mousePressEvent(self, event):
        """鼠标点击事件 - 传递给适当的组件处理"""
        # 如果是Live2D模式，传递事件给Live2D Widget
        if self.display_mode == 'live2d' and self.live2d_widget and self.live2d_widget.is_model_loaded():
            # 将坐标映射到Live2D Widget
            mapped_pos = self.live2d_widget.mapFromParent(event.pos())
            # 创建新的事件传递给Live2D Widget
            from nagaagent_core.vendors.PyQt5.QtGui import QMouseEvent
            new_event = QMouseEvent(
                event.type(),
                mapped_pos,
                event.globalPos(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            self.live2d_widget.mousePressEvent(new_event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件 - 传递给适当的组件处理"""
        # 如果是Live2D模式，传递事件给Live2D Widget
        if self.display_mode == 'live2d' and self.live2d_widget and self.live2d_widget.is_model_loaded():
            # 将坐标映射到Live2D Widget
            mapped_pos = self.live2d_widget.mapFromParent(event.pos())
            # 创建新的事件传递给Live2D Widget
            from nagaagent_core.vendors.PyQt5.QtGui import QMouseEvent
            new_event = QMouseEvent(
                event.type(),
                mapped_pos,
                event.globalPos(),
                event.button(),
                event.buttons(),
                event.modifiers()
            )
            self.live2d_widget.mouseReleaseEvent(new_event)
        else:
            super().mouseReleaseEvent(event)

    def load_action_config(self):
        """加载动作配置"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), '..', 'live2d', 'action_config.json')
            logger.info(f"正在加载动作配置文件: {config_file}")
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.saved_actions = data.get('selected_actions', [])
                    logger.info(f"成功加载 {len(self.saved_actions)} 个动作配置")
            else:
                logger.warning(f"动作配置文件不存在: {config_file}")
                self.saved_actions = []
        except Exception as e:
            logger.error(f"加载动作配置失败: {e}")
            self.saved_actions = []

    def save_action_config(self):
        """保存动作配置"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), '..', 'live2d', 'action_config.json')
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump({'selected_actions': self.saved_actions}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存动作配置失败: {e}")

    def open_config_dialog(self):
        """打开配置对话框"""
        if not LIVE2D_AVAILABLE or not self.live2d_widget or not self.live2d_widget.is_model_loaded():
            return

        # 获取当前模型支持的动作
        available_actions = self.live2d_widget.renderer.detect_model_actions()

        # 创建配置对话框
        dialog = Live2DConfigDialog(available_actions, self.saved_actions, self)
        dialog.config_updated.connect(self.on_config_updated)
        dialog.exec_()

    def on_config_updated(self, config):
        """配置更新回调"""
        self.saved_actions = config.get('selected_actions', [])
        self.save_action_config()
        self.update_actions_panel()

    def on_expand_clicked(self):
        """展开按钮点击事件处理"""
        logger.info("展开按钮被点击了！")
        self.toggle_actions_panel()

    def toggle_actions_panel(self):
        """切换动作面板展开/收起"""
        logger.info(f"切换动作面板，当前状态: expanded={self.actions_expanded}")
        if self.actions_expanded:
            # 收起
            self.actions_panel.hide()
            self.expand_button.setText("▼")
            self.actions_expanded = False
            logger.info("动作面板已收起")
        else:
            # 展开
            self.update_actions_panel()
            self.actions_panel.show()
            self.actions_panel.raise_()  # 确保面板在最上层
            self.expand_button.setText("▲")
            self.actions_expanded = True
            logger.info(f"动作面板已展开 - 可见: {self.actions_panel.isVisible()}, 位置: ({self.actions_panel.x()}, {self.actions_panel.y()}), 大小: {self.actions_panel.size()}")

    def update_actions_panel(self):
        """更新动作面板"""
        logger.info(f"更新动作面板，已保存的动作数量: {len(self.saved_actions)}")

        # 清空现有按钮
        while self.actions_layout.count():
            child = self.actions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 添加动作按钮
        for i, action in enumerate(self.saved_actions):
            btn_text = f"{action.get('icon', '')} {action.get('display', action.get('name'))}"
            logger.info(f"创建按钮 {i+1}: {btn_text}")
            btn = QPushButton(btn_text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(80, 80, 80, 180);
                    color: white;
                    border: 1px solid rgba(255, 255, 255, 80);
                    border-radius: 3px;
                    padding: 5px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: rgba(120, 120, 120, 200);
                }
                QPushButton:pressed {
                    background-color: rgba(150, 150, 150, 220);
                }
            """)

            # 绑定动作触发
            action_name = action.get('name')
            action_type = action.get('type', 'motion')
            btn.clicked.connect(lambda checked, n=action_name, t=action_type: self.trigger_action(n, t))
            self.actions_layout.addWidget(btn)

        # 更新面板大小
        button_height = 35
        panel_height = len(self.saved_actions) * button_height + 10
        self.actions_panel.setFixedHeight(panel_height)
        logger.info(f"动作面板高度设置为: {panel_height}px")

        # 更新面板位置
        if hasattr(self, 'expand_button'):
            panel_x = self.width() - self.actions_panel.width() - 10
            panel_y = self.expand_button.y() + self.expand_button.height() + 5
            self.actions_panel.move(panel_x, panel_y)
            self.actions_panel.raise_()  # 确保面板在最上层
            logger.info(f"动作面板位置更新: ({panel_x}, {panel_y})")

    def trigger_action(self, action_name, action_type):
        """触发动作或表情"""
        logger.info(f"准备触发{action_type}: '{action_name}'")

        if not self.live2d_widget or not self.live2d_widget.is_model_loaded():
            logger.warning(f"无法触发{action_type}: Live2D未加载")
            return

        if action_type == 'expression':
            logger.info(f"触发表情: '{action_name}'")
            self.live2d_widget.trigger_expression(action_name)
        else:
            logger.info(f"触发动作: '{action_name}'")
            self.live2d_widget.trigger_motion(action_name, 0)
