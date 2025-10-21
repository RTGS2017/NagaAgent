import sys, os; sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
from .styles.button_factory import ButtonFactory
from nagaagent_core.vendors.PyQt5.QtWidgets import QWidget, QTextEdit, QSizePolicy, QHBoxLayout, QLabel, QVBoxLayout, QStackedWidget, QDesktopWidget, QScrollArea, QSplitter, QFrame
from nagaagent_core.vendors.PyQt5.QtCore import Qt, QEvent
from nagaagent_core.vendors.PyQt5.QtGui import QColor, QPainter, QBrush
import os
from system.config import config, logger
from ui.utils.ui_style_hot_reload import register_window as register_ui_style_window
from ui.components.title_bar import TitleBar
from .components.widget_progress import EnhancedProgressWidget
from .components.widget_live2d_side import Live2DSideWidget
from .components.widget_settings import SettingWidget
from .components.widget_sidebar import SidebarWidget
from .controller import *

# 使用统一配置系统
def get_ui_config():
    """获取UI配置，确保使用最新的配置值"""
    return {
        'BG_ALPHA': config.ui.bg_alpha,
        'WINDOW_BG_ALPHA': config.ui.window_bg_alpha,
        'USER_NAME': config.ui.user_name,
        'MAC_BTN_SIZE': config.ui.mac_btn_size,
        'MAC_BTN_MARGIN': config.ui.mac_btn_margin,
        'MAC_BTN_GAP': config.ui.mac_btn_gap,
        'ANIMATION_DURATION': config.ui.animation_duration
    }


def refresh_ui_constants():
    global BG_ALPHA, WINDOW_BG_ALPHA, USER_NAME, MAC_BTN_SIZE, MAC_BTN_MARGIN, MAC_BTN_GAP, ANIMATION_DURATION
    ui_config = get_ui_config()
    BG_ALPHA = ui_config['BG_ALPHA']
    WINDOW_BG_ALPHA = ui_config['WINDOW_BG_ALPHA']
    USER_NAME = ui_config['USER_NAME']
    MAC_BTN_SIZE = ui_config['MAC_BTN_SIZE']
    MAC_BTN_MARGIN = ui_config['MAC_BTN_MARGIN']
    MAC_BTN_GAP = ui_config['MAC_BTN_GAP']
    ANIMATION_DURATION = ui_config['ANIMATION_DURATION']


refresh_ui_constants()

class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        config.window=self
        self._init_windows()
        self._init_Layout()
        self._init_buttons()
        self._init_side()
        self._init_end()
        register_ui_style_window(self)
        
    def _init_windows(self):
        # 设置为屏幕大小的80%
        desktop = QDesktopWidget()
        self.screen_rect = desktop.screenGeometry()
        self.window_width = int(self.screen_rect.width() * 0.8)
        self.window_height = int(self.screen_rect.height() * 0.8)
        self._offset = None
        # 获取屏幕大小并自适应
        self.resize(self.window_width, self.window_height)
        
        # 窗口居中显示
        x = (self.screen_rect.width() - self.window_width) // 2
        y = (self.screen_rect.height() - self.window_height) // 2
        self.move(x, y)
        
        # 移除置顶标志，保留无边框
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 添加窗口背景和拖动支持
        self.setStyleSheet(f"""
            ChatWindow {{
                background: rgba(25, 25, 25, {WINDOW_BG_ALPHA});
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
        """)
        self.titlebar = TitleBar('NAGA AGENT', self)
        self.titlebar.setGeometry(0,0,self.width(),100)
    
      
    def _init_Layout(self):
        fontfam,fontsize='Lucida Console',16
        
        # 创建主分割器，替换原来的HBoxLayout
        self.main_splitter = QSplitter(Qt.Horizontal, config.window)
        self.main_splitter.setStyleSheet("""
            QSplitter {
                background: transparent;
            }
            QSplitter::handle {
                background: rgba(255, 255, 255, 30);
                width: 2px;
                border-radius: 1px;
            }
            QSplitter::handle:hover {
                background: rgba(255, 255, 255, 60);
                width: 3px;
            }
        """)

        # 左侧侧边栏容器
        self.sidebar = SidebarWidget()
        self.sidebar_width = 80
        self.sidebar.setMinimumWidth(self.sidebar_width)
        self.sidebar.setMaximumWidth(self.sidebar_width)  # 固定宽度
        self.main_splitter.addWidget(self.sidebar)

        # 聊天区域容器
        self.chat_area=QWidget()
        self.chat_area.setMinimumWidth(400)
        self.vlay=QVBoxLayout(self.chat_area)
        self.vlay.setContentsMargins(0,0,0,0)
        self.vlay.setSpacing(10)

        self.chat_stack = QStackedWidget(self.chat_area)
        self.chat_stack.setStyleSheet("""
            QStackedWidget {
                background: transparent;
                border: none;
            }
        """)
        self.chat_page = QWidget()
        self.chat_page.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        
        # 创建滚动区域来容纳消息对话框
        self.chat_scroll_area = QScrollArea(self.chat_page)
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
                outline: none;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 30);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 80);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 120);
            }
        """)
        
        # 创建滚动内容容器
        self.chat_content = QWidget()
        self.chat_content.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        
        # 创建垂直布局来排列消息对话框
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(10)
        self.chat_layout.addStretch()  # 添加弹性空间，让消息从顶部开始
        self.chat_scroll_area.setWidget(self.chat_content)
        
        # 创建聊天页面布局
        self.chat_page_layout = QVBoxLayout(self.chat_page)
        self.chat_page_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_page_layout.addWidget(self.chat_scroll_area)

        self.chat_stack.addWidget(self.chat_page) # index 0 聊天页
        self.settings_page = SettingWidget()
        self.chat_stack.addWidget(self.settings_page) # index 1 设置页
        self.game_page = QWidget()
        self.chat_stack.addWidget(self.game_page) # index 2 博弈页
        self.mindmap_page = QWidget()
        self.chat_stack.addWidget(self.mindmap_page) # index 3 心智云图页
        self.galgame_page = QWidget()
        self.chat_stack.addWidget(self.galgame_page) # index 4 恋爱冒险页
        self.vlay.addWidget(self.chat_stack, 1)

        self.sidebar[0] = lambda: self.chat_stack.setCurrentIndex(0)
        # 1: 心智云图 - 切换到心智云图组件
        self.sidebar[1] = lambda: self.chat_stack.setCurrentIndex(2)
        # 2: 性格博弈 - 切换到性格博弈组件
        self.sidebar[2] = lambda: self.chat_stack.setCurrentIndex(3)
        # 3: 恋爱冒险 - 切换到恋爱冒险组件
        self.sidebar[3] = lambda: self.chat_stack.setCurrentIndex(4)
        
        # 添加进度显示组件
        self.progress_widget = EnhancedProgressWidget(self.chat_area)
        self.vlay.addWidget(self.progress_widget)
        # 连接进度组件信号
        self.progress_widget.cancel_requested.connect(chat.cancel_current_task)
        
        self.input_wrap=QWidget(self.chat_area)
        self.input_wrap.setFixedHeight(60)  # 增加输入框包装器的高度，与字体大小匹配
        self.hlay=QHBoxLayout(self.input_wrap)
        self.hlay.setContentsMargins(0,0,0,0)
        self.hlay.setSpacing(8)
        self.prompt=QLabel('>',self.input_wrap)
        self.prompt.setStyleSheet(f"color:#fff;font:{fontsize}pt '{fontfam}';background:transparent;")
        self.hlay.addWidget(self.prompt)
        self.input = QTextEdit(self.input_wrap)
        self.input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(17,17,17,{int(config.ui.bg_alpha*255)});
                color: #fff;
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 50);
                font: {fontsize}pt '{fontfam}';
                padding: 8px;
            }}
        """)
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.hlay.addWidget(self.input)
        
    def _init_buttons(self):
        # 初始化消息存储
        self._messages = {}
        self._message_counter = 0

        self.input.textChanged.connect(chat.adjust_input_height)
        self.input.installEventFilter(self)
        
        # 添加文档上传按钮
        self.upload_btn = ButtonFactory.create_action_button("upload", self.input_wrap)
        self.hlay.addWidget(self.upload_btn)
        # 连接文档上传按钮
        self.upload_btn.clicked.connect(document.upload_document)
        
        # 添加心智云图按钮
        self.mind_map_btn = ButtonFactory.create_action_button("mind_map", self.input_wrap)
        self.hlay.addWidget(self.mind_map_btn)
        # 连接心智云图按钮
        self.mind_map_btn.clicked.connect(mindmap.open_mind_map)

        # 添加博弈论启动/关闭按钮
        self.self_game_btn = ButtonFactory.create_action_button("self_game", self.input_wrap)
        self.self_game_btn.setToolTip("启动/关闭博弈论流程")
        self.hlay.addWidget(self.self_game_btn)
        # 连接博弈论按钮
        self.self_game_btn.clicked.connect(game.toggle_self_game)

        # 添加实时语音按钮
        self.voice_realtime_btn = ButtonFactory.create_action_button("voice_realtime", self.input_wrap)
        self.voice_realtime_btn.setToolTip("启动/关闭实时语音对话")
        self.hlay.addWidget(self.voice_realtime_btn)
        # 连接实时语音按钮
        self.voice_realtime_btn.clicked.connect(voice.toggle_voice_realtime)

        
    def _init_side(self):
        self.vlay.addWidget(self.input_wrap,0)
        # 将聊天区域添加到分割器
        self.main_splitter.addWidget(self.chat_area)
        
        # 侧栏（Live2D/图片显示区域）- 使用Live2D侧栏Widget
        self.side = Live2DSideWidget()
        self.collapsed_width = 480  # 收缩状态宽度
        self.expanded_width = 800  # 展开状态宽度
        self.side.setMinimumWidth(self.collapsed_width)  # 设置最小宽度为收缩状态
        self.side.setMaximumWidth(self.collapsed_width)  # 初始状态为收缩
        
        def _enter(e):
            self.side.set_background_alpha(int(BG_ALPHA * 0.5 * 255))
            self.side.set_border_alpha(80)
        # 优化侧栏的悬停效果，使用QPainter绘制
        self.side.enterEvent = _enter
        
        def _leave(e):
            self.side.set_background_alpha(int(BG_ALPHA * 255))
            self.side.set_border_alpha(50)
        self.side.leaveEvent = _leave
        
        # 设置鼠标指针，提示可点击
        self.side.setCursor(Qt.PointingHandCursor)
        self.side.mousePressEvent = side.toggle_full_img # 侧栏点击切换聊天/设置
        
        # 设置默认图片
        default_image = os.path.join(os.path.dirname(__file__), 'img/standby.png')
        if os.path.exists(default_image):
            self.side.set_fallback_image(default_image)
        
        # 连接Live2D侧栏的信号
        self.side.model_loaded.connect(live2d.on_live2d_model_loaded)
        self.side.error_occurred.connect(live2d.on_live2d_error)
        
        # 将侧栏添加到分割器
        self.main_splitter.addWidget(self.side)
        
        # 设置分割器的初始比例 - 侧栏收缩状态
        self.main_splitter.setSizes([self.sidebar_width, self.window_width - self.sidebar_width - self.collapsed_width - 20, self.collapsed_width])  # 大部分给聊天区域
        
        # 创建包含分割器的主布局
        self.main=QVBoxLayout(self)
        self.main.setContentsMargins(10,110,10,10)
        self.main.addWidget(self.main_splitter)
        self.setLayout(self.main)

        # 初始化Live2D
        self.side.initialize_live2d()

    def _init_end(self):
        self.resizeEvent(None)  # 强制自适应一次，修复图片初始尺寸
        # 加载历史记录（替换原_self_load_persistent_context_to_ui）
        chat.load_persistent_history(
            max_messages=config.api.max_history_rounds * 2
        )

    def apply_ui_style(self):
        """根据最新配置刷新窗口外观"""
        refresh_ui_constants()
        self.setStyleSheet(f"""
            ChatWindow {{
                background: rgba(25, 25, 25, {WINDOW_BG_ALPHA});
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
        """)

        alpha_px = int(BG_ALPHA * 255)
        fontfam, fontsize = 'Lucida Console', 16
        self.input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(17,17,17,{alpha_px});
                color: #fff;
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 50);
                font: {fontsize}pt '{fontfam}';
                padding: 8px;
            }}
        """)

        if hasattr(self.side, 'set_background_alpha'):
            self.side.set_background_alpha(alpha_px)
        if hasattr(self.side, 'set_border_alpha'):
            self.side.set_border_alpha(50)

        try:
            from ui.utils import message_renderer as mr
            mr.refresh_style_constants()
        except Exception:
            pass

        frame_background_style = f"""
            QFrame {{
                background: rgba(17,17,17,{alpha_px});
                border-radius: 0px;
                border: 1px solid rgba(255, 255, 255, 50);
                padding: 10px;
                margin: 5px 0px;
            }}
        """

        for frame in self.chat_content.findChildren(QFrame):
            base_style = frame.property("_base_stylesheet")
            if base_style is None:
                base_style = frame.styleSheet() or ""
                frame.setProperty("_base_stylesheet", base_style)
            frame.setStyleSheet(f"{base_style}\n{frame_background_style}")

        if hasattr(self.titlebar, 'update_style'):
            self.titlebar.update_style()

        try:
            from ui.controller.tool_chat import apply_config as apply_chat_tool_config
            apply_chat_tool_config()
        except Exception:
            pass

        self.update()



#==========MouseEvents==========
    # 添加整个窗口的拖动支持
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._offset and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._offset = None
        event.accept()

    def paintEvent(self, event):
        """绘制窗口背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制主窗口背景 - 使用可调节的透明度
        painter.setBrush(QBrush(QColor(25, 25, 25, WINDOW_BG_ALPHA)))
        painter.setPen(QColor(255, 255, 255, 30))
        painter.drawRoundedRect(self.rect(), 20, 20)
        
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        
        # 其他初始化代码...
        self.setFocus()
        self.input.setFocus()
        # 图片初始化现在由Live2DSideWidget处理
        self._img_inited = True
        
    def resizeEvent(self, e):
        if getattr(self, '_animating', False):  # 动画期间跳过所有重绘操作，避免卡顿
            return
        # 图片调整现在由Live2DSideWidget内部处理
        super().resizeEvent(e)
    
    def eventFilter(self, obj, event):
        """事件过滤器：处理输入框的键盘事件，实现回车发送、Shift+回车换行"""
        # 仅处理输入框（self.input）的事件
        if obj != self.input:
            return super().eventFilter(obj, event)

        # 仅处理「键盘按下」事件
        if event.type() == QEvent.KeyPress:
            # 捕获两种回车按键：主键盘回车（Key_Return）、小键盘回车（Key_Enter）
            is_enter_key = event.key() in (Qt.Key_Return, Qt.Key_Enter)
            # 判断是否按住了Shift键
            is_shift_pressed = event.modifiers() & Qt.ShiftModifier

            if is_enter_key:
                if not is_shift_pressed:
                    # 纯回车：发送消息，阻止默认换行
                    chat.on_send()
                    return True  # 返回True表示事件已处理，不传递给输入框
                else:
                    # Shift+回车：放行事件，让输入框正常换行
                    return False  # 返回False表示事件继续传递

        # 其他事件（如普通输入）：正常放行
        return super().eventFilter(obj, event)
    
    
#====================
