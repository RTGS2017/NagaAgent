import sys, os; sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
from .styles.button_factory import ButtonFactory
from PyQt5.QtWidgets import QApplication, QWidget, QTextEdit, QSizePolicy, QHBoxLayout, QLabel, QVBoxLayout, QStackedLayout, QPushButton, QStackedWidget, QDesktopWidget, QScrollArea, QSplitter, QFileDialog, QMessageBox, QFrame
from PyQt5.QtCore import Qt, QRect, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QFont, QPen
from system.conversation_core import NagaConversation
import os
from system.config import config, AI_NAME, Live2DConfig # 导入统一配置
from ui.response_utils import extract_message  # 新增：引入消息提取工具
from ui.styles.progress_widget import EnhancedProgressWidget  # 导入进度组件
from ui.enhanced_worker import StreamingWorker, BatchWorker  # 导入增强Worker
from ui.elegant_settings_widget import ElegantSettingsWidget
from ui.message_renderer import MessageRenderer  # 导入消息渲染器
from ui.live2d_side_widget import Live2DSideWidget  # 导入Live2D侧栏组件
import json
import requests
from pathlib import Path
import time

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

# 初始化全局变量
ui_config = get_ui_config()
BG_ALPHA = ui_config['BG_ALPHA']
WINDOW_BG_ALPHA = ui_config['WINDOW_BG_ALPHA']
USER_NAME = ui_config['USER_NAME']
MAC_BTN_SIZE = ui_config['MAC_BTN_SIZE']
MAC_BTN_MARGIN = ui_config['MAC_BTN_MARGIN']
MAC_BTN_GAP = ui_config['MAC_BTN_GAP']
ANIMATION_DURATION = ui_config['ANIMATION_DURATION']



class TitleBar(QWidget):
    def __init__(s, text, parent=None):
        super().__init__(parent)
        s.text = text
        s.setFixedHeight(100)
        s.setAttribute(Qt.WA_TranslucentBackground)
        s._offset = None
        # mac风格按钮
        for i,(txt,color,hover,cb) in enumerate([
            ('-','#FFBD2E','#ffe084',lambda:s.parent().showMinimized()),
            ('×','#FF5F57','#ff8783',lambda:s.parent().close())]):
            btn=QPushButton(txt,s)
            btn.setGeometry(s.width()-MAC_BTN_MARGIN-MAC_BTN_SIZE*(2-i)-MAC_BTN_GAP*(1-i),36,MAC_BTN_SIZE,MAC_BTN_SIZE)
            btn.setStyleSheet(f"QPushButton{{background:{color};border:none;border-radius:{MAC_BTN_SIZE//2}px;color:#fff;font:18pt;}}QPushButton:hover{{background:{hover};}}")
            btn.clicked.connect(cb)
            setattr(s,f'btn_{"min close".split()[i]}',btn)
    def mousePressEvent(s, e):
        if e.button()==Qt.LeftButton: s._offset = e.globalPos()-s.parent().frameGeometry().topLeft()
    def mouseMoveEvent(s, e):
        if s._offset and e.buttons()&Qt.LeftButton:
            s.parent().move(e.globalPos()-s._offset)
    def mouseReleaseEvent(s,e):s._offset=None
    def paintEvent(s, e):
        qp = QPainter(s)
        qp.setRenderHint(QPainter.Antialiasing)
        w, h = s.width(), s.height()
        qp.setPen(QColor(255,255,255,180))
        qp.drawLine(0, 2, w, 2)
        qp.drawLine(0, h-3, w, h-3)
        font = QFont("Consolas", max(10, (h-40)//2), QFont.Bold)
        qp.setFont(font)
        rect = QRect(0, 20, w, h-40)
        for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            qp.setPen(QColor(0,0,0))
            qp.drawText(rect.translated(dx,dy), Qt.AlignCenter, s.text)
        qp.setPen(QColor(255,255,255))
        qp.drawText(rect, Qt.AlignCenter, s.text)
    def resizeEvent(s,e):
        x=s.width()-MAC_BTN_MARGIN
        for i,btn in enumerate([s.btn_min,s.btn_close]):btn.move(x-MAC_BTN_SIZE*(2-i)-MAC_BTN_GAP*(1-i),36)


class ChatWindow(QWidget):
    def __init__(s):
        super().__init__()
        
        # 获取屏幕大小并自适应
        desktop = QDesktopWidget()
        screen_rect = desktop.screenGeometry()
        # 设置为屏幕大小的80%
        window_width = int(screen_rect.width() * 0.8)
        window_height = int(screen_rect.height() * 0.8)
        s.resize(window_width, window_height)
        
        # 窗口居中显示
        x = (screen_rect.width() - window_width) // 2
        y = (screen_rect.height() - window_height) // 2
        s.move(x, y)
        
        # 移除置顶标志，保留无边框
        s.setWindowFlags(Qt.FramelessWindowHint)
        s.setAttribute(Qt.WA_TranslucentBackground)
        
        # 添加窗口背景和拖动支持
        s._offset = None
        s.setStyleSheet(f"""
            ChatWindow {{
                background: rgba(25, 25, 25, {WINDOW_BG_ALPHA});
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
        """)
        
        fontfam,fontsize='Lucida Console',16
        
        # 创建主分割器，替换原来的HBoxLayout
        s.main_splitter = QSplitter(Qt.Horizontal, s)
        s.main_splitter.setStyleSheet("""
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
        
        # 聊天区域容器
        chat_area=QWidget()
        chat_area.setMinimumWidth(400)  # 设置最小宽度
        vlay=QVBoxLayout(chat_area);vlay.setContentsMargins(0,0,0,0);vlay.setSpacing(10)
        
        # 用QStackedWidget管理聊天区和设置页
        s.chat_stack = QStackedWidget(chat_area)
        s.chat_stack.setStyleSheet("""
            QStackedWidget {
                background: transparent;
                border: none;
            }
        """) # 保证背景穿透
        
        # 创建聊天页面容器
        s.chat_page = QWidget()
        s.chat_page.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        
        # 创建滚动区域来容纳消息对话框
        s.chat_scroll_area = QScrollArea(s.chat_page)
        s.chat_scroll_area.setWidgetResizable(True)
        s.chat_scroll_area.setStyleSheet("""
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
        s.chat_content = QWidget()
        s.chat_content.setStyleSheet("""
            QWidget {
                background: transparent;
                border: none;
            }
        """)
        
        # 创建垂直布局来排列消息对话框
        s.chat_layout = QVBoxLayout(s.chat_content)
        s.chat_layout.setContentsMargins(10, 10, 10, 10)
        s.chat_layout.setSpacing(10)
        s.chat_layout.addStretch()  # 添加弹性空间，让消息从顶部开始
        
        s.chat_scroll_area.setWidget(s.chat_content)
        
        # 创建聊天页面布局
        chat_page_layout = QVBoxLayout(s.chat_page)
        chat_page_layout.setContentsMargins(0, 0, 0, 0)
        chat_page_layout.addWidget(s.chat_scroll_area)
        
        s.chat_stack.addWidget(s.chat_page) # index 0 聊天页
        s.settings_page = s.create_settings_page() # index 1 设置页
        s.chat_stack.addWidget(s.settings_page)
        vlay.addWidget(s.chat_stack, 1)
        
        # 添加进度显示组件
        s.progress_widget = EnhancedProgressWidget(chat_area)
        vlay.addWidget(s.progress_widget)
        
        s.input_wrap=QWidget(chat_area)
        s.input_wrap.setFixedHeight(60)  # 增加输入框包装器的高度，与字体大小匹配
        hlay=QHBoxLayout(s.input_wrap);hlay.setContentsMargins(0,0,0,0);hlay.setSpacing(8)
        s.prompt=QLabel('>',s.input_wrap)
        s.prompt.setStyleSheet(f"color:#fff;font:{fontsize}pt '{fontfam}';background:transparent;")
        hlay.addWidget(s.prompt)
        s.input = QTextEdit(s.input_wrap)
        s.input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(17,17,17,{int(BG_ALPHA*255)});
                color: #fff;
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 50);
                font: {fontsize}pt '{fontfam}';
                padding: 8px;
            }}
        """)
        s.input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        s.input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        hlay.addWidget(s.input)
        
        # 添加文档上传按钮
        s.upload_btn = ButtonFactory.create_action_button("upload", s.input_wrap)
        hlay.addWidget(s.upload_btn)
        
        # 添加心智云图按钮
        s.mind_map_btn = ButtonFactory.create_action_button("mind_map", s.input_wrap)
        hlay.addWidget(s.mind_map_btn)
        
        vlay.addWidget(s.input_wrap,0)
        
        # 将聊天区域添加到分割器
        s.main_splitter.addWidget(chat_area)
        
        # 侧栏（Live2D/图片显示区域）- 使用Live2D侧栏Widget
        s.side = Live2DSideWidget()
        s.collapsed_width = 400  # 收缩状态宽度
        s.expanded_width = 800  # 展开状态宽度
        s.side.setMinimumWidth(s.collapsed_width)  # 设置最小宽度为收缩状态
        s.side.setMaximumWidth(s.collapsed_width)  # 初始状态为收缩
        
        # 优化侧栏的悬停效果，使用QPainter绘制
        def setup_side_hover_effects():
            def original_enter(e):
                s.side.set_background_alpha(int(BG_ALPHA * 0.5 * 255))
                s.side.set_border_alpha(80)
            def original_leave(e):
                s.side.set_background_alpha(int(BG_ALPHA * 255))
                s.side.set_border_alpha(50)
            return original_enter, original_leave
        
        s.side_hover_enter, s.side_hover_leave = setup_side_hover_effects()
        s.side.enterEvent = s.side_hover_enter
        s.side.leaveEvent = s.side_hover_leave
        
        # 设置鼠标指针，提示可点击
        s.side.setCursor(Qt.PointingHandCursor)
        
        # 设置默认图片
        default_image = os.path.join(os.path.dirname(__file__), 'standby.png')
        if os.path.exists(default_image):
            s.side.set_fallback_image(default_image)
        
        # 连接Live2D侧栏的信号
        s.side.model_loaded.connect(s.on_live2d_model_loaded)
        s.side.error_occurred.connect(s.on_live2d_error)
        
        # 创建昵称标签（保持原有功能）
        nick=QLabel(f"● {AI_NAME}{config.system.version}",s.side)
        nick.setStyleSheet("""
            QLabel {
                color: #fff;
                font: 18pt 'Consolas';
                background: rgba(0,0,0,100);
                padding: 12px 0 12px 0;
                border-radius: 10px;
                border: none;
            }
        """)
        nick.setAlignment(Qt.AlignHCenter|Qt.AlignTop)
        nick.setAttribute(Qt.WA_TransparentForMouseEvents)
        nick.hide()  # 隐藏昵称
        
        # 将侧栏添加到分割器
        s.main_splitter.addWidget(s.side)
        
        # 设置分割器的初始比例 - 侧栏收缩状态
        s.main_splitter.setSizes([window_width - s.collapsed_width - 20, s.collapsed_width])  # 大部分给聊天区域
        
        # 创建包含分割器的主布局
        main=QVBoxLayout(s)
        main.setContentsMargins(10,110,10,10)
        main.addWidget(s.main_splitter)
        
        s.nick=nick
        s.naga=NagaConversation()  # 第三次初始化：ChatWindow构造函数中创建
        s.worker=None
        s.full_img=0 # 立绘展开标志，0=收缩状态，1=展开状态
        s.streaming_mode = config.system.stream_mode  # 根据配置决定是否使用流式模式
        s.current_response = ""  # 当前响应缓冲
        s.animating = False  # 动画标志位，动画期间为True
        s._img_inited = False  # 标志变量，图片自适应只在初始化时触发一次
        
        # Live2D相关配置
        s.live2d_enabled = config.live2d.enabled  # 是否启用Live2D
        s.live2d_model_path = config.live2d.model_path  # Live2D模型路径
        
        # 初始化消息存储
        s._messages = {}
        s._message_counter = 0
        
        # 加载持久化历史对话到前端
        s._load_persistent_context_to_ui()
        
        # 连接进度组件信号
        s.progress_widget.cancel_requested.connect(s.cancel_current_task)
        
        s.input.textChanged.connect(s.adjust_input_height)
        s.input.installEventFilter(s)
        
        # 连接文档上传按钮
        s.upload_btn.clicked.connect(s.upload_document)
        
        # 连接心智云图按钮
        s.mind_map_btn.clicked.connect(s.open_mind_map)
        
        s.setLayout(main)
        s.titlebar = TitleBar('NAGA AGENT', s)
        s.titlebar.setGeometry(0,0,s.width(),100)
        s.side.mousePressEvent=s.toggle_full_img # 侧栏点击切换聊天/设置
        s.resizeEvent(None)  # 强制自适应一次，修复图片初始尺寸
        
        # 初始化Live2D（如果启用）
        s.initialize_live2d()

    def create_settings_page(s):
        page = QWidget()
        page.setObjectName("SettingsPage")
        page.setStyleSheet("""
            #SettingsPage {
                background: transparent;
                border-radius: 24px;
                padding: 12px;
            }
        """)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 20);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 60);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 80);
            }
        """)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 滚动内容
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(20)
        # 只保留系统设置界面
        s.settings_widget = ElegantSettingsWidget(scroll_content)
        s.settings_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        s.settings_widget.settings_changed.connect(s.on_settings_changed)
        scroll_layout.addWidget(s.settings_widget, 1)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)
        return page

    def resizeEvent(s, e):
        if getattr(s, '_animating', False):  # 动画期间跳过所有重绘操作，避免卡顿
            return
        # 图片调整现在由Live2DSideWidget内部处理
        super().resizeEvent(e)
            

    def adjust_input_height(s):
        doc = s.input.document()
        h = int(doc.size().height())+10
        s.input.setFixedHeight(min(max(60, h), 150))  # 增加最小高度，与字体大小匹配
        s.input_wrap.setFixedHeight(s.input.height())
        
    def eventFilter(s, obj, event):
        if obj is s.input and event.type()==6:
            if event.key()==Qt.Key_Return and not (event.modifiers()&Qt.ShiftModifier):
                s.on_send();return True
        return False
    def add_user_message(s, name, content):
        """添加用户消息"""
        from ui.response_utils import extract_message
        msg = extract_message(content)
        content_html = str(msg).replace('\\n', '\n').replace('\n', '<br>')
        
        # 生成消息ID
        if not hasattr(s, '_message_counter'):
            s._message_counter = 0
        s._message_counter += 1
        message_id = f"msg_{s._message_counter}"
        
        # 初始化消息存储
        if not hasattr(s, '_messages'):
            s._messages = {}
        
        # 存储消息信息
        s._messages[message_id] = {
            'name': name,
            'content': content_html,
            'full_content': content,
            'dialog_widget': None
        }
        
        # 使用消息渲染器创建对话框
        if name == "系统":
            message_dialog = MessageRenderer.create_system_message(name, content_html, s.chat_content)
        else:
            message_dialog = MessageRenderer.create_user_message(name, content_html, s.chat_content)
        
        # 存储对话框引用
        s._messages[message_id]['dialog_widget'] = message_dialog
        
        # 在弹性空间之前插入新的消息对话框
        stretch_index = s.chat_layout.count() - 1
        s.chat_layout.insertWidget(stretch_index, message_dialog)
        
        # 滚动到底部
        s.scroll_to_bottom()
        
        return message_id
    
    def update_last_message(s, name, content):
        """更新最后一条消息的内容"""
        from ui.response_utils import extract_message
        msg = extract_message(content)
        content_html = str(msg).replace('\\n', '\n').replace('\n', '<br>')
        
        # 检查是否有当前消息ID
        if hasattr(s, '_current_message_id') and s._current_message_id:
            # 更新存储的消息信息
            if hasattr(s, '_messages') and s._current_message_id in s._messages:
                s._messages[s._current_message_id]['content'] = content_html
                s._messages[s._current_message_id]['full_content'] = content
                
                # 使用消息渲染器更新对话框内容
                dialog_widget = s._messages[s._current_message_id]['dialog_widget']
                if dialog_widget:
                    MessageRenderer.update_message_content(dialog_widget, content_html)
        else:
            # 如果没有当前消息ID，直接添加新消息
            s.add_user_message(name, content)
    
    def scroll_to_bottom(s):
        """滚动到聊天区域底部"""
        # 使用QTimer延迟滚动，确保布局完成
        QTimer.singleShot(10, lambda: s.chat_scroll_area.verticalScrollBar().setValue(
            s.chat_scroll_area.verticalScrollBar().maximum()
        ))
        
    def _load_persistent_context_to_ui(s):
        """从持久化上下文加载历史对话到前端UI"""
        try:
            # 检查是否启用持久化上下文
            if not config.api.persistent_context:
                print("📝 持久化上下文功能已禁用，跳过历史记录加载")
                return
                
            # 导入日志解析器
            from logs.log_context_parser import get_log_parser
            parser = get_log_parser()
            
            # 使用新的方法加载历史对话到UI
            ui_messages = parser.load_persistent_context_to_ui(
                parent_widget=s.chat_content,
                max_messages=config.api.max_history_rounds * 2
            )
            
            if ui_messages:
                # 将历史消息添加到UI布局中
                for message_id, message_info, dialog in ui_messages:
                    # 在弹性空间之前插入历史消息对话框
                    stretch_index = s.chat_layout.count() - 1
                    s.chat_layout.insertWidget(stretch_index, dialog)
                    
                    # 存储到消息管理器中
                    s._messages[message_id] = message_info
                
                # 更新消息计数器
                s._message_counter = len(ui_messages)
                
                # 滚动到底部显示最新消息
                s.scroll_to_bottom()
                
                print(f"✅ 前端UI已加载 {len(ui_messages)} 条历史对话")
            else:
                print("📝 前端UI未找到历史对话记录")
                
        except ImportError as e:
            print(f"⚠️ 日志解析器模块未找到，跳过前端历史记录加载: {e}")
        except Exception as e:
            print(f"❌ 前端加载持久化上下文失败: {e}")
            # 失败时不影响正常使用，继续使用空上下文
            print("💡 将继续使用空上下文，不影响正常对话功能")
    
    def clear_chat_history(s):
        """清除聊天历史记录"""
        # 清除所有消息对话框
        if hasattr(s, '_messages'):
            for message_id, message_info in s._messages.items():
                dialog_widget = message_info.get('dialog_widget')
                if dialog_widget:
                    dialog_widget.deleteLater()
            s._messages.clear()
        
        # 清除布局中的所有widget（除了弹性空间）
        while s.chat_layout.count() > 1:  # 保留最后的弹性空间
            item = s.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    def on_send(s):
        u = s.input.toPlainText().strip()
        if u:
            s.add_user_message(USER_NAME, u)
            s.input.clear()
            
            # 如果已有任务在运行，先取消
            if s.worker and s.worker.isRunning():
                s.cancel_current_task()
                return
            
            # 清空当前响应缓冲
            s.current_response = ""
            
            # 确保worker被清理
            if s.worker:
                s.worker.deleteLater()
                s.worker = None
            
            # 根据模式选择Worker类型，创建全新实例
            if s.streaming_mode:
                s.worker = StreamingWorker(s.naga, u)
                s.setup_streaming_worker()
            else:
                s.worker = BatchWorker(s.naga, u)
                s.setup_batch_worker()
            
            # 启动进度显示 - 恢复原来的调用方式
            s.progress_widget.set_thinking_mode()
            
            # 启动Worker
            s.worker.start()
    
    def setup_streaming_worker(s):
        """配置流式Worker的信号连接"""
        s.worker.progress_updated.connect(s.progress_widget.update_progress)
        s.worker.status_changed.connect(lambda status: s.progress_widget.status_label.setText(status))
        s.worker.error_occurred.connect(s.handle_error)
        
        # 流式专用信号
        s.worker.stream_chunk.connect(s.append_response_chunk)
        s.worker.stream_complete.connect(s.finalize_streaming_response)
        s.worker.finished.connect(s.on_response_finished)
        
        # 工具调用相关信号
        s.worker.tool_call_detected.connect(s.handle_tool_call)
        s.worker.tool_result_received.connect(s.handle_tool_result)
    
    def setup_batch_worker(s):
        """配置批量Worker的信号连接"""
        s.worker.progress_updated.connect(s.progress_widget.update_progress)
        s.worker.status_changed.connect(lambda status: s.progress_widget.status_label.setText(status))
        s.worker.error_occurred.connect(s.handle_error)
        s.worker.finished.connect(s.on_batch_response_finished)
    
    def append_response_chunk(s, chunk):
        """追加响应片段（流式模式）- 实时显示"""
        # 实时更新显示 - 立即显示到UI
        if not hasattr(s, '_current_message_id'):
            # 第一次收到chunk时，创建新消息
            s._current_message_id = s.add_user_message(AI_NAME, chunk)
            s.current_response = chunk
        else:
            # 后续chunk，追加到当前消息
            s.current_response += chunk
            s.update_last_message(AI_NAME, s.current_response)
            
        # 强制UI更新
        s.chat_scroll_area.viewport().update()
    
    def finalize_streaming_response(s):
        """完成流式响应 - 立即处理"""
        if s.current_response:
            # 对累积的完整响应进行消息提取（多步自动\n分隔）
            from ui.response_utils import extract_message
            final_message = extract_message(s.current_response)
            
            # 更新最终消息
            if hasattr(s, '_current_message_id'):
                s.update_last_message(AI_NAME, final_message)
                delattr(s, '_current_message_id')
            else:
                s.add_user_message(AI_NAME, final_message)
        
        # 立即停止加载状态
        s.progress_widget.stop_loading()
    
    def on_response_finished(s, response):
        """处理完成的响应（流式模式后备）"""
        # 检查是否是取消操作的响应
        if response == "操作已取消":
            return  # 不显示，因为已经在cancel_current_task中显示了
        if not s.current_response:  # 如果流式没有收到数据，使用最终结果
            from ui.response_utils import extract_message
            final_message = extract_message(response)
            s.add_user_message(AI_NAME, final_message)
        s.progress_widget.stop_loading()
    
    def on_batch_response_finished(s, response):
        """处理完成的响应（批量模式）"""
        # 检查是否是取消操作的响应
        if response == "操作已取消":
            return  # 不显示，因为已经在cancel_current_task中显示了
        from ui.response_utils import extract_message
        final_message = extract_message(response)
        s.add_user_message(AI_NAME, final_message)
        s.progress_widget.stop_loading()
    
    def handle_error(s, error_msg):
        """处理错误"""
        s.add_user_message("系统", f"❌ {error_msg}")
        s.progress_widget.stop_loading()
    
    def handle_tool_call(s, notification):
        """处理工具调用通知"""
        # 创建专门的工具调用内容对话框（没有用户名）
        tool_call_dialog = MessageRenderer.create_tool_call_content_message(notification, s.chat_content)
        
        # 设置嵌套对话框内容
        nested_title = "工具调用详情"
        nested_content = f"""
工具名称: {notification}
状态: 正在执行...
时间: {time.strftime('%H:%M:%S')}
        """.strip()
        tool_call_dialog.set_nested_content(nested_title, nested_content)
        
        # 生成消息ID
        if not hasattr(s, '_message_counter'):
            s._message_counter = 0
        s._message_counter += 1
        message_id = f"tool_call_{s._message_counter}"
        
        # 初始化消息存储
        if not hasattr(s, '_messages'):
            s._messages = {}
        
        # 存储工具调用消息信息
        s._messages[message_id] = {
            'name': '工具调用',
            'content': notification,
            'full_content': notification,
            'dialog_widget': tool_call_dialog
        }
        
        # 在弹性空间之前插入工具调用对话框
        stretch_index = s.chat_layout.count() - 1
        s.chat_layout.insertWidget(stretch_index, tool_call_dialog)
        
        # 滚动到底部
        s.scroll_to_bottom()
        
        # 在状态栏也显示工具调用状态
        s.progress_widget.status_label.setText(f"🔧 {notification}")
        print(f"工具调用: {notification}")
    
    def handle_tool_result(s, result):
        """处理工具执行结果"""
        # 查找最近的工具调用对话框并更新
        if hasattr(s, '_messages'):
            for message_id, message_info in reversed(list(s._messages.items())):
                if message_id.startswith('tool_call_'):
                    dialog_widget = message_info.get('dialog_widget')
                    if dialog_widget:
                        # 更新工具调用对话框显示结果
                        MessageRenderer.update_message_content(dialog_widget, f"✅ {result}")
                        
                        # 更新嵌套对话框内容
                        if hasattr(dialog_widget, 'set_nested_content'):
                            nested_title = "工具调用结果"
                            nested_content = f"""
工具名称: {message_info.get('content', '未知工具')}
状态: 执行完成 ✅
时间: {time.strftime('%H:%M:%S')}
结果: {result[:200]}{'...' if len(result) > 200 else ''}
                            """.strip()
                            dialog_widget.set_nested_content(nested_title, nested_content)
                        break
        
        # 在状态栏也显示工具执行结果
        s.progress_widget.status_label.setText(f"✅ {result[:50]}...")
        print(f"工具结果: {result}")
    
    def cancel_current_task(s):
        """取消当前任务 - 优化版本，减少卡顿"""
        if s.worker and s.worker.isRunning():
            # 立即设置取消标志
            s.worker.cancel()
            
            # 非阻塞方式处理线程清理
            s.progress_widget.stop_loading()
            s.add_user_message("系统", "🚫 操作已取消")
            
            # 清空当前响应缓冲，避免部分响应显示
            s.current_response = ""
            
            # 使用QTimer延迟处理线程清理，避免UI卡顿
            def cleanup_worker():
                if s.worker:
                    s.worker.quit()
                    if not s.worker.wait(500):  # 只等待500ms
                        s.worker.terminate()
                        s.worker.wait(200)  # 再等待200ms
                    s.worker.deleteLater()
                    s.worker = None
            
            # 50ms后异步清理，避免阻塞UI
            QTimer.singleShot(50, cleanup_worker)
        else:
            s.progress_widget.stop_loading()

    def toggle_full_img(s,e):
        if getattr(s, '_animating', False):  # 动画期间禁止重复点击
            return
        s._animating = True  # 设置动画标志位
        s.full_img^=1  # 立绘展开标志切换
        target_width = s.expanded_width if s.full_img else s.collapsed_width  # 目标宽度：展开或收缩
        
        # --- 立即切换界面状态 ---
        if s.full_img:  # 展开状态 - 进入设置页面
            s.input_wrap.hide()  # 隐藏输入框
            s.chat_stack.setCurrentIndex(1)  # 切换到设置页
            s.side.setCursor(Qt.PointingHandCursor)  # 保持点击指针，可点击收缩
            s.titlebar.text = "SETTING PAGE"
            s.titlebar.update()
            s.side.setStyleSheet(f"""
                QWidget {{
                    background: rgba(17,17,17,{int(BG_ALPHA*255*0.9)});
                    border-radius: 15px;
                    border: 1px solid rgba(255, 255, 255, 80);
                }}
            """)
        else:  # 收缩状态 - 主界面聊天模式
            s.input_wrap.show()  # 显示输入框
            s.chat_stack.setCurrentIndex(0)  # 切换到聊天页
            s.input.setFocus()  # 恢复输入焦点
            s.side.setCursor(Qt.PointingHandCursor)  # 保持点击指针
            s.titlebar.text = "NAGA AGENT"
            s.titlebar.update()
            s.side.setStyleSheet(f"""
                QWidget {{
                    background: rgba(17,17,17,{int(BG_ALPHA*255*0.7)});
                    border-radius: 15px;
                    border: 1px solid rgba(255, 255, 255, 40);
                }}
            """)
        # --- 立即切换界面状态 END ---
        
        # 创建优化后的动画组
        group = QParallelAnimationGroup(s)
        
        # 侧栏宽度动画 - 合并为单个动画
        side_anim = QPropertyAnimation(s.side, b"minimumWidth", s)
        side_anim.setDuration(ANIMATION_DURATION)
        side_anim.setStartValue(s.side.width())
        side_anim.setEndValue(target_width)
        side_anim.setEasingCurve(QEasingCurve.OutCubic)  # 使用更流畅的缓动
        group.addAnimation(side_anim)
        
        side_anim2 = QPropertyAnimation(s.side, b"maximumWidth", s)
        side_anim2.setDuration(ANIMATION_DURATION)
        side_anim2.setStartValue(s.side.width())
        side_anim2.setEndValue(target_width)
        side_anim2.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(side_anim2)
        
        # 输入框动画 - 进入设置时隐藏，退出时显示
        if s.full_img:
            input_hide_anim = QPropertyAnimation(s.input_wrap, b"maximumHeight", s)
            input_hide_anim.setDuration(ANIMATION_DURATION // 2)
            input_hide_anim.setStartValue(s.input_wrap.height())
            input_hide_anim.setEndValue(0)
            input_hide_anim.setEasingCurve(QEasingCurve.OutQuad)
            group.addAnimation(input_hide_anim)
        else:
            input_show_anim = QPropertyAnimation(s.input_wrap, b"maximumHeight", s)
            input_show_anim.setDuration(ANIMATION_DURATION // 2)
            input_show_anim.setStartValue(0)
            input_show_anim.setEndValue(60)
            input_show_anim.setEasingCurve(QEasingCurve.OutQuad)
            group.addAnimation(input_show_anim)
        
        def on_side_width_changed():
            """侧栏宽度变化时实时更新"""
            # Live2D侧栏会自动处理大小调整
            pass
        
        def on_animation_finished():
            s._animating = False  # 动画结束标志
            # Live2D侧栏会自动处理最终调整
            pass
        
        # 连接信号
        side_anim.valueChanged.connect(on_side_width_changed)
        group.finished.connect(on_animation_finished)
        group.start()
        

    # 添加整个窗口的拖动支持
    def mousePressEvent(s, event):
        if event.button() == Qt.LeftButton:
            s._offset = event.globalPos() - s.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(s, event):
        if s._offset and event.buttons() & Qt.LeftButton:
            s.move(event.globalPos() - s._offset)
            event.accept()

    def mouseReleaseEvent(s, event):
        s._offset = None
        event.accept()

    def paintEvent(s, event):
        """绘制窗口背景"""
        painter = QPainter(s)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制主窗口背景 - 使用可调节的透明度
        painter.setBrush(QBrush(QColor(25, 25, 25, WINDOW_BG_ALPHA)))
        painter.setPen(QColor(255, 255, 255, 30))
        painter.drawRoundedRect(s.rect(), 20, 20)

    def on_settings_changed(s, setting_key, value):
        """处理设置变化"""
        print(f"设置变化: {setting_key} = {value}")
        
        # 透明度设置将在保存时统一应用，避免动画卡顿
        if setting_key in ("all", "ui.bg_alpha", "ui.window_bg_alpha"):  # UI透明度变化 #
            # 保存时应用透明度设置
            s.apply_opacity_from_config()
            return
        if setting_key in ("system.stream_mode", "STREAM_MODE"):
            s.streaming_mode = value if setting_key == "system.stream_mode" else value  # 兼容新旧键名 #
            s.add_user_message("系统", f"● 流式模式已{'启用' if s.streaming_mode else '禁用'}")
        elif setting_key in ("system.voice_enabled", "VOICE_ENABLED"):
            s.add_user_message("系统", f"● 语音功能已{'启用' if value else '禁用'}")
        elif setting_key in ("system.debug", "DEBUG"):
            s.add_user_message("系统", f"● 调试模式已{'启用' if value else '禁用'}")
        
        # 发送设置变化信号给其他组件
        # 这里可以根据需要添加更多处理逻辑

    def set_window_background_alpha(s, alpha):
        """设置整个窗口的背景透明度
        Args:
            alpha: 透明度值，可以是:
                   - 0-255的整数 (PyQt原生格式)
                   - 0.0-1.0的浮点数 (百分比格式)
        """
        global WINDOW_BG_ALPHA
        
        # 处理不同格式的输入
        if isinstance(alpha, float) and 0.0 <= alpha <= 1.0:
            # 浮点数格式：0.0-1.0 转换为 0-255
            WINDOW_BG_ALPHA = int(alpha * 255)
        elif isinstance(alpha, int) and 0 <= alpha <= 255:
            # 整数格式：0-255
            WINDOW_BG_ALPHA = alpha
        else:
            print(f"警告：无效的透明度值 {alpha}，应为0-255的整数或0.0-1.0的浮点数")
            return
        
        # 更新CSS样式表
        s.setStyleSheet(f"""
            ChatWindow {{
                background: rgba(25, 25, 25, {WINDOW_BG_ALPHA});
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
        """)
    
        # 触发重绘
        s.update()
        
        print(f"✅ 窗口背景透明度已设置为: {WINDOW_BG_ALPHA}/255 ({WINDOW_BG_ALPHA/255*100:.1f}%不透明度)")

    def apply_opacity_from_config(s):
        """从配置中应用UI透明度(聊天区/输入框/侧栏/窗口)"""
        # 更新全局变量，保持其它逻辑一致 #
        global BG_ALPHA, WINDOW_BG_ALPHA
        # 直接读取配置值，避免函数调用开销
        BG_ALPHA = config.ui.bg_alpha
        WINDOW_BG_ALPHA = config.ui.window_bg_alpha

        # 计算alpha #
        alpha_px = int(BG_ALPHA * 255)

        # 更新聊天区域背景 - 现在使用透明背景，对话框有自己的背景
        s.chat_content.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border: none;
            }}
        """)

        # 更新输入框背景 #
        fontfam, fontsize = 'Lucida Console', 16
        s.input.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(17,17,17,{alpha_px});
                color: #fff;
                border-radius: 15px;
                border: 1px solid rgba(255, 255, 255, 50);
                font: {fontsize}pt '{fontfam}';
                padding: 8px;
            }}
        """)

        # 更新侧栏背景 #
        if hasattr(s, 'side') and isinstance(s.side, QWidget):
            try:
                s.side.set_background_alpha(alpha_px)
            except Exception:
                pass

        # 更新主窗口背景 #
        s.set_window_background_alpha(WINDOW_BG_ALPHA)
    

    def showEvent(s, event):
        """窗口显示事件"""
        super().showEvent(event)
        
        # 其他初始化代码...
        s.setFocus()
        s.input.setFocus()
        # 图片初始化现在由Live2DSideWidget处理
        s._img_inited = True

    def upload_document(s):
        """上传文档功能"""
        try:
            # 打开文件选择对话框
            file_path, _ = QFileDialog.getOpenFileName(
                s,
                "选择要上传的文档",
                "",
                "支持的文档格式 (*.docx *.txt *.md);;Word文档 (*.docx);;文本文件 (*.txt);;Markdown文件 (*.md);;所有文件 (*)"
            )
            
            if not file_path:
                return  # 用户取消选择
            
            # 检查文件格式
            file_ext = Path(file_path).suffix.lower()
            supported_formats = ['.docx', '.txt', '.md']
            
            if file_ext not in supported_formats:
                QMessageBox.warning(s, "格式不支持", 
                                   f"不支持的文件格式: {file_ext}\n\n支持的格式: {', '.join(supported_formats)}")
                return
            
            # 检查文件大小 (限制为10MB)
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10MB
                QMessageBox.warning(s, "文件过大", "文件大小不能超过10MB")
                return
            
            # 上传文件到API服务器
            s.upload_file_to_server(file_path)
            
        except Exception as e:
            QMessageBox.critical(s, "上传错误", f"文档上传失败:\n{str(e)}")
    
    def upload_file_to_server(s, file_path):
        """将文件上传到API服务器"""
        try:
            # 显示上传进度
            s.add_user_message("系统", f"📤 正在上传文档: {Path(file_path).name}")
            s.progress_widget.set_thinking_mode()
            s.progress_widget.status_label.setText("上传文档中...")
            
            # 准备上传数据
            api_url = "http://localhost:8000/upload/document"
            
            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f, 'application/octet-stream')}
                data = {'description': f'通过NAGA聊天界面上传的文档'}
                
                # 发送上传请求
                response = requests.post(api_url, files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                s.progress_widget.stop_loading()
                s.add_user_message("系统", f"✅ 文档上传成功: {result['filename']}")
                
                # 询问用户想要进行什么操作
                s.show_document_options(result['file_path'], result['filename'])
            else:
                s.progress_widget.stop_loading()
                s.add_user_message("系统", f"❌ 上传失败: {response.text}")
                
        except requests.exceptions.ConnectionError:
            s.progress_widget.stop_loading()
            s.add_user_message("系统", "❌ 无法连接到API服务器，请确保服务器正在运行")
        except Exception as e:
            s.progress_widget.stop_loading()
            s.add_user_message("系统", f"❌ 上传失败: {str(e)}")
    
    def show_document_options(s, file_path, filename):
        """显示文档处理选项"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame, QPushButton
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont
        
        dialog = QDialog(s)
        dialog.setWindowTitle("文档处理选项")
        dialog.setFixedSize(650, 480)
        # 隐藏标题栏的图标按钮
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(20)
        
        # 标题
        title_label = QLabel("文档上传成功")
        title_font = QFont("Microsoft YaHei", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 25px; padding: 15px; min-height: 40px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 文件信息
        info_label = QLabel(f"文件名: {filename}")
        info_label.setStyleSheet("color: #34495e; font-size: 14px; padding: 10px;")
        layout.addWidget(info_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(line)
        
        # 操作按钮
        actions = [
            ("📖 读取内容", "read", "读取文档的完整内容"),
            ("🔍 分析文档", "analyze", "分析文档结构和内容"),
            ("📝 生成摘要", "summarize", "生成文档的简洁摘要")
        ]
        
        for btn_text, action, description in actions:
            btn = ButtonFactory.create_document_action_button(btn_text)
            
            # 添加描述标签
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-bottom: 10px;")
            layout.addWidget(desc_label)
            layout.addWidget(btn)
            
            # 连接按钮事件
            btn.clicked.connect(lambda checked, f=file_path, a=action, d=dialog: s.process_document(f, a, d))
        
        # 取消按钮
        cancel_btn = ButtonFactory.create_cancel_button()
        cancel_btn.clicked.connect(dialog.close)
        layout.addWidget(cancel_btn)
        
        dialog.exec_()
    
    def process_document(s, file_path, action, dialog=None):
        """处理文档"""
        if dialog:
            dialog.close()
        
        try:
            s.add_user_message("系统", f"🔄 正在处理文档: {Path(file_path).name}")
            s.progress_widget.set_thinking_mode()
            s.progress_widget.status_label.setText("处理文档中...")
            
            # 调用API处理文档
            api_url = "http://localhost:8000/document/process"
            data = {
                "file_path": file_path,
                "action": action
            }
            
            response = requests.post(api_url, json=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                s.progress_widget.stop_loading()
                
                if action == "read":
                    s.add_user_message(AI_NAME, f"📖 文档内容:\n\n{result['content']}")
                elif action == "analyze":
                    s.add_user_message(AI_NAME, f"🔍 文档分析:\n\n{result['analysis']}")
                elif action == "summarize":
                    s.add_user_message(AI_NAME, f"📝 文档摘要:\n\n{result['summary']}")
            else:
                s.progress_widget.stop_loading()
                s.add_user_message("系统", f"❌ 文档处理失败: {response.text}")
                
        except requests.exceptions.ConnectionError:
            s.progress_widget.stop_loading()
            s.add_user_message("系统", "❌ 无法连接到API服务器，请确保服务器正在运行")
        except Exception as e:
            s.progress_widget.stop_loading()
            s.add_user_message("系统", f"❌ 文档处理失败: {str(e)}")
    
    def open_mind_map(s):
        """打开心智云图"""
        try:
            # 检查是否存在知识图谱文件
            graph_file = "logs/knowledge_graph/graph.html"
            quintuples_file = "logs/knowledge_graph/quintuples.json"
            
            # 如果quintuples.json存在，删除现有的graph.html并重新生成
            if os.path.exists(quintuples_file):
                # 如果graph.html存在，先删除它
                if os.path.exists(graph_file):
                    try:
                        os.remove(graph_file)
                        print(f"已删除旧的graph.html文件")
                    except Exception as e:
                        print(f"删除graph.html文件失败: {e}")
                
                # 生成新的HTML
                s.add_user_message("系统", "🔄 正在生成心智云图...")
                try:
                    from summer_memory.quintuple_visualize_v2 import visualize_quintuples
                    visualize_quintuples()
                    if os.path.exists(graph_file):
                        import webbrowser
                        # 获取正确的绝对路径
                        if os.path.isabs(graph_file):
                            abs_graph_path = graph_file
                        else:
                            # 如果是相对路径，基于项目根目录构建绝对路径
                            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                            abs_graph_path = os.path.join(current_dir, graph_file)
                        
                        webbrowser.open("file:///" + abs_graph_path)
                        s.add_user_message("系统", "🧠 心智云图已生成并打开")
                    else:
                        s.add_user_message("系统", "❌ 心智云图生成失败")
                except Exception as e:
                    s.add_user_message("系统", f"❌ 生成心智云图失败: {str(e)}")
            else:
                # 没有五元组数据，提示用户
                s.add_user_message("系统", "❌ 未找到五元组数据，请先进行对话以生成知识图谱")
        except Exception as e:
            s.add_user_message("系统", f"❌ 打开心智云图失败: {str(e)}")
    
    def initialize_live2d(s):
        """初始化Live2D"""
        if s.live2d_enabled and s.live2d_model_path:
            if os.path.exists(s.live2d_model_path):
                s.side.set_live2d_model(s.live2d_model_path) # 调用已有输出逻辑
            else:
                print(f"⚠️ Live2D模型文件不存在: {s.live2d_model_path}")
        else:
            print("📝 Live2D功能未启用或未配置模型路径")
    
    def on_live2d_model_loaded(s, success):
        """Live2D模型加载状态回调"""
        if success:
            print("✅ Live2D模型已成功加载")
        else:
            print("🔄 已回退到图片模式")
    
    def on_live2d_error(s, error_msg):
        """Live2D错误回调"""
        s.add_user_message("系统", f"❌ Live2D错误: {error_msg}")
    
    def set_live2d_model(s, model_path):
        """设置Live2D模型"""
        if not os.path.exists(model_path):
            s.add_user_message("系统", f"❌ Live2D模型文件不存在: {model_path}")
            return False
        
        s.live2d_model_path = model_path
        s.live2d_enabled = True
        
        s.add_user_message("系统", "🔄 正在切换Live2D模型...")
        success = s.side.set_live2d_model(model_path)
        
        if success:
            s.add_user_message("系统", "✅ Live2D模型切换成功")
        else:
            s.add_user_message("系统", "⚠️ Live2D模型切换失败，已回退到图片模式")
        
        return success
    
    def set_fallback_image(s, image_path):
        """设置回退图片"""
        if not os.path.exists(image_path):
            s.add_user_message("系统", f"❌ 图片文件不存在: {image_path}")
            return False
        
        s.side.set_fallback_image(image_path)
        s.add_user_message("系统", f"✅ 回退图片已设置: {os.path.basename(image_path)}")
        return True
    
    def get_display_mode(s):
        """获取当前显示模式"""
        return s.side.get_display_mode()
    
    def is_live2d_available(s):
        """检查Live2D是否可用"""
        return s.side.is_live2d_available()

if __name__=="__main__":
    app = QApplication(sys.argv)
    win = ChatWindow()
    win.show()
    sys.exit(app.exec_())
