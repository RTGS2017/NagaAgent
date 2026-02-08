"""
优雅的设置界面组件
统一风格的设置界面，包含API配置、系统配置等多个选项
"""

import sys
import os
import json

# 添加项目根目录到path，以便导入配置
project_root = os.path.abspath(os.path.dirname(__file__) + "/..")
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 添加nagaagent-core目录到path，以便导入PyQt5
nagaagent_core_dir = os.path.join(project_root, "nagaagent-core")
if nagaagent_core_dir not in sys.path:
    sys.path.insert(0, nagaagent_core_dir)

from nagaagent_core.vendors.PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QFrame,
    QScrollArea,
    QSlider,
    QTextEdit,
    QGroupBox,
    QGridLayout,
    QFileDialog,
)  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, QEasingCurve  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtGui import QFont, QPainter, QColor  # 统一入口 #

from system.config import config, AI_NAME, UIConfig, Live2DConfig
from ui.styles.settings_styles import (
    SYSTEM_PROMPT_CARD_STYLE,
    SYSTEM_PROMPT_EDITOR_STYLE,
    SYSTEM_PROMPT_TITLE_STYLE,
    SYSTEM_PROMPT_DESC_STYLE,
    SETTING_CARD_BASE_STYLE,
    SETTING_CARD_TITLE_STYLE,
    SETTING_CARD_DESC_STYLE,
    SETTING_GROUP_HEADER_CONTAINER_STYLE,
    SETTING_GROUP_HEADER_BUTTON_STYLE,
    SETTING_GROUP_RIGHT_LABEL_STYLE,
    SCROLL_AREA_STYLE,
    SCROLL_CONTENT_STYLE,
    STATUS_LABEL_STYLE,
    SAVE_BUTTON_STYLE,
    RESET_BUTTON_STYLE,
    NAGA_PORTAL_BUTTON_STYLE,
    VOICE_MODE_DISABLED_STYLE,
    TEST_WINDOW_STYLE,
    INPUT_STYLE,
    COMBO_STYLE,
    CHECKBOX_STYLE,
    SLIDER_STYLE,
    SPIN_STYLE,
    LABEL_STYLE,
    OPENCLAW_STATUS_INSTALLED_STYLE,
    OPENCLAW_STATUS_NOT_INSTALLED_STYLE,
    OPENCLAW_CONNECTED_STYLE,
    OPENCLAW_DISCONNECTED_STYLE,
    OPENCLAW_REFRESH_BUTTON_STYLE,
    OPENCLAW_DOCS_BUTTON_STYLE,
    OPENCLAW_TERMINAL_ACTIVE_STYLE,
    OPENCLAW_TERMINAL_IDLE_STYLE,
    OPENCLAW_TERMINAL_ERROR_STYLE,
    OPENCLAW_TERMINAL_DETAILS_STYLE,
    OPENCLAW_MONITOR_TEXT_STYLE,
)


class SettingCard(QWidget):
    """单个设置卡片"""

    value_changed = pyqtSignal(str, object)  # 设置名, 新值

    def __init__(self, title, description, control_widget, setting_key=None, parent=None):
        super().__init__(parent)
        self.setting_key = setting_key
        self.control_widget = control_widget
        self.setup_ui(title, description)

    def setup_ui(self, title, description):
        """初始化卡片UI"""
        self.setFixedHeight(80)
        self.setStyleSheet(SETTING_CARD_BASE_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 左侧文本区域
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet(SETTING_CARD_TITLE_STYLE)
        text_layout.addWidget(title_label)

        # 描述
        desc_label = QLabel(description)
        desc_label.setStyleSheet(SETTING_CARD_DESC_STYLE)
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout, 1)

        # 右侧控件区域
        control_container = QWidget()
        control_container.setFixedWidth(400)  # 增加到两倍宽度
        control_layout = QHBoxLayout(control_container)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.addWidget(self.control_widget)

        layout.addWidget(control_container)

        # 连接控件信号
        self.connect_signals()

    def connect_signals(self):
        """连接控件信号"""
        if isinstance(self.control_widget, QLineEdit):
            self.control_widget.textChanged.connect(self.on_value_changed)
        elif isinstance(self.control_widget, QCheckBox):
            self.control_widget.toggled.connect(self.on_value_changed)
        elif isinstance(self.control_widget, (QSpinBox, QDoubleSpinBox)):
            self.control_widget.valueChanged.connect(self.on_value_changed)
        elif isinstance(self.control_widget, QComboBox):
            self.control_widget.currentTextChanged.connect(self.on_value_changed)
        elif isinstance(self.control_widget, QSlider):
            self.control_widget.valueChanged.connect(self.on_value_changed)

    def on_value_changed(self, value):
        """处理值变化"""
        if self.setting_key:
            self.value_changed.emit(self.setting_key, value)


class SettingGroup(QWidget):
    """设置组(支持展开/收起)"""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.cards = []  # 卡片列表 #
        self._title = title  # 标题文本 #
        self._expanded = False  # 默认收起 #
        self.setup_ui(title)  # 初始化UI #
        self.set_collapsed(True, animate=False)  # 初始直接收起(无动画) #

    def setup_ui(self, title):
        """初始化组UI(带可点击头部)"""
        layout = QVBoxLayout(self)  # 主布局 #
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 头部容器(按钮+右侧文本) #
        self.header_container = QWidget()  # 容器 #
        self.header_container.setStyleSheet(SETTING_GROUP_HEADER_CONTAINER_STYLE)
        self.header_layout = QHBoxLayout(self.header_container)  # 水平布局 #
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(8)

        self.header_button = QPushButton(f"▶ {title}")  # 默认收起显示右箭头 #
        self.header_button.setCheckable(True)  # 可切换 #
        self.header_button.setChecked(False)  # 默认未选中为收起 #
        self.header_button.setCursor(Qt.PointingHandCursor)  # 指针手型 #
        self.header_button.setStyleSheet(SETTING_GROUP_HEADER_BUTTON_STYLE)
        self.header_button.clicked.connect(self.on_header_clicked)  # 绑定点击事件 #
        self.header_layout.addWidget(self.header_button, 0, Qt.AlignLeft)

        self.header_layout.addStretch(1)  # 中间拉伸 #

        self.header_right_label = QLabel("")  # 右侧文本(如版本) #
        self.header_right_label.setStyleSheet(SETTING_GROUP_RIGHT_LABEL_STYLE)
        self.header_right_label.setVisible(False)  # 默认不显示 #
        self.header_layout.addWidget(self.header_right_label, 0, Qt.AlignRight)

        layout.addWidget(self.header_container)

        # 卡片容器 #
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(4)
        self.cards_container.setVisible(False)  # 初始隐藏 #
        self.cards_container.setMaximumHeight(0)  # 初始高度为0用于动画 #

        # 动画：最大高度属性动画 #
        self.animation = QPropertyAnimation(self.cards_container, b"maximumHeight", self)  # 动画对象 #
        self.animation.setDuration(220)  # 时长 #
        self.animation.setEasingCurve(QEasingCurve.OutCubic)  # 缓动曲线 #
        self.animation.finished.connect(self._on_animation_finished)  # 动画结束处理 #
        layout.addWidget(self.cards_container)

    def on_header_clicked(self, checked):
        """头部点击切换展开/收起"""
        self.set_collapsed(not checked)  # 与按钮选中状态相反为收起 #

    def set_collapsed(self, collapsed, animate=True):
        """设置收起/展开状态"""
        self._expanded = not collapsed  # 同步内部状态 #
        arrow = "▼" if not collapsed else "▶"  # 箭头符号 #
        self.header_button.setChecked(not collapsed)  # 同步按钮 #
        self.header_button.setText(f"{arrow} {self._title}")  # 更新标题 #

        if not animate:  # 立即切换 #
            self.cards_container.setVisible(not collapsed)  # 直接显隐 #
            if collapsed:
                self.cards_container.setMaximumHeight(0)  # 收起高度0 #
            else:
                self.cards_container.setMaximumHeight(16777215)  # 展开恢复最大 #
            self.updateGeometry()  # 刷新布局 #
            return

        # 动画切换 #
        self.animation.stop()  # 停止旧动画 #
        if collapsed:
            # 从当前高度收起到0 #
            self.cards_container.setVisible(True)  # 动画期间保持可见 #
            start_h = self.cards_container.maximumHeight()  # 当前最大高度 #
            if start_h == 16777215:
                start_h = self.cards_container.sizeHint().height()  # 若为无穷大则取内容高度 #
            self.animation.setStartValue(max(0, start_h))  # 起始值 #
            self.animation.setEndValue(0)  # 结束值 #
        else:
            # 从0展开到内容高度 #
            self.cards_container.setVisible(True)  # 先显示 #
            self.cards_container.setMaximumHeight(0)  # 起始0 #
            end_h = self.cards_container.sizeHint().height()  # 内容高度 #
            self.animation.setStartValue(0)  # 起始值 #
            self.animation.setEndValue(max(0, end_h))  # 结束值 #
        self.animation.start()  # 开始动画 #

    def add_card(self, card):
        """添加设置卡片或普通控件"""
        if hasattr(card, "value_changed"):  # 是SettingCard #
            self.cards.append(card)  # 保存引用 #
        self.cards_layout.addWidget(card)  # 加入布局 #
        # 若在展开状态下新增卡片，更新容器高度以避免裁剪 #
        if self._expanded and self.cards_container.isVisible():  # 展开中 #
            # 动态调整到新的内容高度 #
            self.cards_container.setMaximumHeight(self.cards_container.sizeHint().height())  # 更新高度 #
            self.updateGeometry()  # 刷新布局 #

    def _on_animation_finished(self):
        """动画结束时收尾"""
        if self._expanded:
            self.cards_container.setMaximumHeight(16777215)  # 展开后取消高度限制 #
        else:
            self.cards_container.setVisible(False)  # 收起后隐藏 #
        self.updateGeometry()  # 刷新布局 #

    def set_right_text(self, text):
        """设置标题栏右侧文本(空则隐藏)"""
        has_text = bool(text)
        self.header_right_label.setVisible(has_text)
        self.header_right_label.setText(str(text) if has_text else "")

    def set_right_widget(self, widget):
        """在标题栏右侧放置一个自定义控件(如按钮)"""
        # 先隐藏右侧文本 #
        self.header_right_label.setVisible(False)
        # 移除已存在的右侧控件 #
        if hasattr(self, "header_right_widget") and self.header_right_widget is not None:
            self.header_layout.removeWidget(self.header_right_widget)
            self.header_right_widget.setParent(None)
        self.header_right_widget = widget  # 保存引用 #
        if widget is not None:
            self.header_layout.addWidget(widget, 0, Qt.AlignRight)  # 添加到右侧 #


class ElegantSettingsWidget(QWidget):
    """优雅的设置界面"""

    settings_changed = pyqtSignal(str, object)  # 设置名, 新值

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status_label = None
        self.pending_changes = {}  # 待保存的更改
        self.setup_ui()
        self.load_current_settings()

        # 添加配置变更监听器，实现实时更新
        try:
            from system.config import add_config_listener

            add_config_listener(self.on_config_reloaded)
        except ImportError as e:
            # 如果导入失败，尝试重新设置路径
            import sys
            import os

            project_root = os.path.abspath(os.path.dirname(__file__) + "/..")
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
            from system.config import add_config_listener

            add_config_listener(self.on_config_reloaded)

    def on_config_reloaded(self):
        """配置重新加载后的处理"""
        # 重新加载当前设置到界面
        self.load_current_settings()
        # 清空待保存的更改
        self.pending_changes.clear()
        # 更新状态标签
        self.update_status_label("✓ 配置已重新加载，界面已更新")

    def setup_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        # 滚动内容
        scroll_content = QWidget()
        scroll_content.setStyleSheet(SCROLL_CONTENT_STYLE)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(20)

        # 创建设置组
        self.create_system_group(scroll_layout)
        self.create_ui_style_group(scroll_layout)
        self.create_naga_portal_group(scroll_layout)
        self.create_api_group(scroll_layout)
        self.create_xiayuan_group(scroll_layout)
        self.create_voice_input_group(scroll_layout)  # 语音输入设置（ASR）
        self.create_voice_output_group(scroll_layout)  # 语音输出设置（TTS）
        self.create_mqtt_group(scroll_layout)
        self.create_openclaw_group(scroll_layout)  # OpenClaw 集成设置
        self.create_save_section(scroll_layout)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

    def create_api_group(self, parent_layout):
        group = SettingGroup("API 配置")
        # API Key
        if hasattr(config.api, "api_key"):
            api_key_input = QLineEdit()
            api_key_input.setText(config.api.api_key)
            api_key_input.setStyleSheet(INPUT_STYLE)
            api_key_card = SettingCard("API Key", "用于连接API的密钥", api_key_input, "api.api_key")
            api_key_card.value_changed.connect(self.on_setting_changed)
            group.add_card(api_key_card)
            self.api_key_input = api_key_input
        # Base URL
        if hasattr(config.api, "base_url"):
            base_url_input = QLineEdit()
            base_url_input.setText(config.api.base_url)
            base_url_input.setStyleSheet(INPUT_STYLE)
            base_url_card = SettingCard("API Base URL", "API基础URL", base_url_input, "api.base_url")
            base_url_card.value_changed.connect(self.on_setting_changed)
            group.add_card(base_url_card)
            self.base_url_input = base_url_input
        # Model
        if hasattr(config.api, "model"):
            model_combo = QLineEdit()
            model_combo.setText(config.api.model)
            model_combo.setStyleSheet(INPUT_STYLE)
            model_card = SettingCard("AI模型", "选择用于对话的AI模型", model_combo, "api.model")
            model_card.value_changed.connect(self.on_setting_changed)
            group.add_card(model_card)
            self.model_combo = model_combo

        # 电脑控制配置
        if hasattr(config, "computer_control"):
            # 电脑控制模型
            computer_control_model_input = QLineEdit()
            computer_control_model_input.setText(config.computer_control.model)
            computer_control_model_input.setStyleSheet(INPUT_STYLE)
            computer_control_model_card = SettingCard(
                "电脑控制模型", "用于电脑控制任务的主要模型", computer_control_model_input, "computer_control.model"
            )
            computer_control_model_card.value_changed.connect(self.on_setting_changed)
            group.add_card(computer_control_model_card)
            self.computer_control_model_input = computer_control_model_input

            # 电脑控制API地址
            computer_control_url_input = QLineEdit()
            computer_control_url_input.setText(config.computer_control.model_url)
            computer_control_url_input.setStyleSheet(INPUT_STYLE)
            computer_control_url_card = SettingCard(
                "电脑控制API地址", "电脑控制模型的API地址", computer_control_url_input, "computer_control.model_url"
            )
            computer_control_url_card.value_changed.connect(self.on_setting_changed)
            group.add_card(computer_control_url_card)
            self.computer_control_url_input = computer_control_url_input

            # 电脑控制API密钥
            computer_control_api_key_input = QLineEdit()
            computer_control_api_key_input.setText(config.computer_control.api_key)
            computer_control_api_key_input.setEchoMode(QLineEdit.Password)
            computer_control_api_key_input.setStyleSheet(INPUT_STYLE)
            computer_control_api_key_card = SettingCard(
                "电脑控制API密钥", "电脑控制模型的API密钥", computer_control_api_key_input, "computer_control.api_key"
            )
            computer_control_api_key_card.value_changed.connect(self.on_setting_changed)
            group.add_card(computer_control_api_key_card)
            self.computer_control_api_key_input = computer_control_api_key_input

            # 定位模型
            grounding_model_input = QLineEdit()
            grounding_model_input.setText(config.computer_control.grounding_model)
            grounding_model_input.setStyleSheet(INPUT_STYLE)
            grounding_model_card = SettingCard(
                "定位模型", "用于元素定位和坐标识别的模型", grounding_model_input, "computer_control.grounding_model"
            )
            grounding_model_card.value_changed.connect(self.on_setting_changed)
            group.add_card(grounding_model_card)
            self.grounding_model_input = grounding_model_input

            # 定位模型API地址
            grounding_url_input = QLineEdit()
            grounding_url_input.setText(config.computer_control.grounding_url)
            grounding_url_input.setStyleSheet(INPUT_STYLE)
            grounding_url_card = SettingCard(
                "定位模型API地址", "定位模型的API地址", grounding_url_input, "computer_control.grounding_url"
            )
            grounding_url_card.value_changed.connect(self.on_setting_changed)
            group.add_card(grounding_url_card)
            self.grounding_url_input = grounding_url_input

            # 定位模型API密钥
            grounding_api_key_input = QLineEdit()
            grounding_api_key_input.setText(config.computer_control.grounding_api_key)
            grounding_api_key_input.setEchoMode(QLineEdit.Password)
            grounding_api_key_input.setStyleSheet(INPUT_STYLE)
            grounding_api_key_card = SettingCard(
                "定位模型API密钥", "定位模型的API密钥", grounding_api_key_input, "computer_control.grounding_api_key"
            )
            grounding_api_key_card.value_changed.connect(self.on_setting_changed)
            group.add_card(grounding_api_key_card)
            self.grounding_api_key_input = grounding_api_key_input

        parent_layout.addWidget(group)

    def create_system_group(self, parent_layout):
        group = SettingGroup("系统配置")
        # 在标题栏最右侧显示版本号(若有) #
        if hasattr(config.system, "version"):
            group.set_right_text(f"v{config.system.version}")

        # AI 名称输入框（写入 config.system.ai_name） #
        ai_name_input = QLineEdit()
        ai_name_input.setText(getattr(config.system, "ai_name", ""))
        ai_name_input.setStyleSheet(INPUT_STYLE)
        ai_name_card = SettingCard(
            "AI 名称", "修改后将写入config.json的system.ai_name", ai_name_input, "system.ai_name"
        )
        ai_name_card.value_changed.connect(self.on_setting_changed)
        group.add_card(ai_name_card)
        self.ai_name_input = ai_name_input  # 保存引用 #

        # 最大Token数（从API配置移过来）
        if hasattr(config.api, "max_tokens"):
            max_tokens_spin = QSpinBox()
            max_tokens_spin.setRange(100, 32768)
            max_tokens_spin.setValue(config.api.max_tokens)
            max_tokens_spin.setStyleSheet(SPIN_STYLE)
            max_tokens_card = SettingCard("最大Token数", "单次对话的最大长度限制", max_tokens_spin, "api.max_tokens")
            max_tokens_card.value_changed.connect(self.on_setting_changed)
            group.add_card(max_tokens_card)
            self.max_tokens_spin = max_tokens_spin

        # 历史轮数（从API配置移过来）
        if hasattr(config.api, "max_history_rounds"):
            history_spin = QSpinBox()
            history_spin.setRange(1, 200)
            history_spin.setValue(config.api.max_history_rounds)
            history_spin.setStyleSheet(SPIN_STYLE)
            history_card = SettingCard(
                "历史轮数",
                "上下文对话轮数（系统会保留最近多少轮对话内容作为上下文）",
                history_spin,
                "api.max_history_rounds",
            )
            history_card.value_changed.connect(self.on_setting_changed)
            group.add_card(history_card)
            self.history_spin = history_spin

        # 加载天数设置（从API配置移过来）
        if hasattr(config.api, "context_load_days"):
            context_days_spin = QSpinBox()
            context_days_spin.setRange(1, 30)
            context_days_spin.setValue(config.api.context_load_days)
            context_days_spin.setStyleSheet(SPIN_STYLE)
            context_days_card = SettingCard(
                "加载天数", "从最近几天的日志文件中加载历史对话", context_days_spin, "api.context_load_days"
            )
            context_days_card.value_changed.connect(self.on_setting_changed)
            group.add_card(context_days_card)
            self.context_days_spin = context_days_spin

        # 系统提示词编辑（对接 system/prompts/naga_system_prompt.txt） #
        prompt_editor = QTextEdit()
        prompt_editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用垂直滚动条 #
        prompt_editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用水平滚动条 #
        prompt_editor.setStyleSheet(SYSTEM_PROMPT_EDITOR_STYLE)

        try:
            from system.config import get_prompt  # 懒加载 #

            # 直接读取对话风格提示词文件 #
            preview_text = get_prompt("conversation_style_prompt")
        except Exception:
            preview_text = ""
        prompt_editor.setPlainText(preview_text)

        # 自动调整高度 #
        def adjust_height():
            try:
                doc = prompt_editor.document()
                doc.setTextWidth(prompt_editor.viewport().width())
                # 计算文本高度，增加更多边距 #
                text_height = int(doc.size().height())
                padding = 40  # 增加内边距 #
                new_height = min(max(text_height + padding, 80), 200)  # 最小80px，最大200px #
                if prompt_editor.height() != new_height:  # 避免重复设置相同高度 #
                    prompt_editor.setFixedHeight(new_height)
            except Exception as e:
                print(f"调整高度失败: {e}")  # 调试信息 #

        # 为系统提示词创建特殊的全宽卡片 #
        prompt_card = QWidget()
        # 不设置固定高度，让内容决定高度 #
        prompt_card.setStyleSheet(SYSTEM_PROMPT_CARD_STYLE)

        prompt_layout = QVBoxLayout(prompt_card)
        prompt_layout.setContentsMargins(16, 12, 16, 12)
        prompt_layout.setSpacing(8)

        # 标题和描述 #
        title_label = QLabel("系统提示词")
        title_label.setStyleSheet(SYSTEM_PROMPT_TITLE_STYLE)
        prompt_layout.addWidget(title_label)

        desc_label = QLabel("编辑对话风格提示词，影响AI的回复风格和语言特点")
        desc_label.setStyleSheet(SYSTEM_PROMPT_DESC_STYLE)
        desc_label.setWordWrap(True)
        prompt_layout.addWidget(desc_label)

        # 提示词编辑器占满剩余空间 #
        prompt_layout.addWidget(prompt_editor)

        group.add_card(prompt_card)
        self.system_prompt_editor = prompt_editor  # 保存引用 #

        # 统一的文本变化处理函数 #
        def _on_text_changed():
            try:
                # 调整高度 #
                adjust_height()
                # 记录提示词更改 #
                preview_text = self.system_prompt_editor.toPlainText()
                # 保存到对话风格提示词文件 #
                if not hasattr(self, "pending_prompts"):
                    self.pending_prompts = {}
                self.pending_prompts["conversation_style_prompt"] = preview_text
                self.update_status_label("● 系统提示词 已修改")
            except Exception as e:
                print(f"文本变化处理失败: {e}")

        # 连接文本变化信号 #
        prompt_editor.textChanged.connect(_on_text_changed)

        # 保存原始的resizeEvent方法 #
        original_resize_event = prompt_editor.resizeEvent

        def custom_resize_event(event):
            try:
                original_resize_event(event)  # 调用原始方法 #
                adjust_height()  # 调整高度 #
            except Exception as e:
                print(f"resize事件处理失败: {e}")

        prompt_editor.resizeEvent = custom_resize_event

        # 初始调整 #
        adjust_height()

        group.set_collapsed(True)  # 默认收起系统配置 #
        parent_layout.addWidget(group)

    def create_ui_style_group(self, parent_layout):
        group = SettingGroup("UI 风格配置")

        reset_btn = QPushButton("重置为默认值")
        reset_btn.setFixedSize(120, 36)
        reset_btn.setStyleSheet(RESET_BUTTON_STYLE)
        reset_btn.clicked.connect(self.reset_ui_style_defaults)
        group.set_right_widget(reset_btn)

        user_name_input = QLineEdit()
        user_name_input.setText(config.ui.user_name)
        user_name_input.setStyleSheet(INPUT_STYLE)
        user_name_card = SettingCard("用户昵称", "聊天窗口显示的用户昵称", user_name_input, "ui.user_name")
        user_name_card.value_changed.connect(self.on_setting_changed)
        group.add_card(user_name_card)
        self.ui_user_name_input = user_name_input

        bg_alpha_spin = QDoubleSpinBox()
        bg_alpha_spin.setRange(0.0, 1.0)
        bg_alpha_spin.setDecimals(2)
        bg_alpha_spin.setSingleStep(0.05)
        bg_alpha_spin.setValue(config.ui.bg_alpha)
        bg_alpha_spin.setStyleSheet(SPIN_STYLE)  # 使用统一的样式
        bg_alpha_card = SettingCard(
            "聊天背景透明度", "影响聊天区域卡片背景的透明度（0=完全透明）", bg_alpha_spin, "ui.bg_alpha"
        )
        bg_alpha_card.value_changed.connect(self.on_setting_changed)
        group.add_card(bg_alpha_card)
        self.ui_bg_alpha_spin = bg_alpha_spin

        window_alpha_spin = QSpinBox()
        window_alpha_spin.setRange(0, 255)
        window_alpha_spin.setValue(config.ui.window_bg_alpha)
        window_alpha_spin.setStyleSheet(SPIN_STYLE)
        window_alpha_card = SettingCard(
            "窗口背景透明度", "控制主窗口背景的不透明度", window_alpha_spin, "ui.window_bg_alpha"
        )
        window_alpha_card.value_changed.connect(self.on_setting_changed)
        group.add_card(window_alpha_card)
        self.ui_window_alpha_spin = window_alpha_spin

        mac_btn_size_spin = QSpinBox()
        mac_btn_size_spin.setRange(10, 100)
        mac_btn_size_spin.setValue(config.ui.mac_btn_size)
        mac_btn_size_spin.setStyleSheet(SPIN_STYLE)
        mac_btn_size_card = SettingCard(
            "标题栏按钮尺寸", "调整标题栏圆形按钮的大小", mac_btn_size_spin, "ui.mac_btn_size"
        )
        mac_btn_size_card.value_changed.connect(self.on_setting_changed)
        group.add_card(mac_btn_size_card)
        self.ui_mac_btn_size_spin = mac_btn_size_spin

        mac_btn_margin_spin = QSpinBox()
        mac_btn_margin_spin.setRange(0, 50)
        mac_btn_margin_spin.setValue(config.ui.mac_btn_margin)
        mac_btn_margin_spin.setStyleSheet(SPIN_STYLE)
        mac_btn_margin_card = SettingCard(
            "标题栏按钮边距", "调整按钮距离窗口右侧的边距", mac_btn_margin_spin, "ui.mac_btn_margin"
        )
        mac_btn_margin_card.value_changed.connect(self.on_setting_changed)
        group.add_card(mac_btn_margin_card)
        self.ui_mac_btn_margin_spin = mac_btn_margin_spin

        mac_btn_gap_spin = QSpinBox()
        mac_btn_gap_spin.setRange(0, 30)
        mac_btn_gap_spin.setValue(config.ui.mac_btn_gap)
        mac_btn_gap_spin.setStyleSheet(SPIN_STYLE)
        mac_btn_gap_card = SettingCard("标题栏按钮间距", "调整两个按钮之间的距离", mac_btn_gap_spin, "ui.mac_btn_gap")
        mac_btn_gap_card.value_changed.connect(self.on_setting_changed)
        group.add_card(mac_btn_gap_card)
        self.ui_mac_btn_gap_spin = mac_btn_gap_spin

        animation_duration_spin = QSpinBox()
        animation_duration_spin.setRange(100, 2000)
        animation_duration_spin.setSingleStep(50)
        animation_duration_spin.setValue(config.ui.animation_duration)
        animation_duration_spin.setStyleSheet(SPIN_STYLE)
        animation_duration_card = SettingCard(
            "界面动画时长", "控制侧边栏等动画的持续时间（毫秒）", animation_duration_spin, "ui.animation_duration"
        )
        animation_duration_card.value_changed.connect(self.on_setting_changed)
        group.add_card(animation_duration_card)
        self.ui_animation_duration_spin = animation_duration_spin

        live2d_enabled_checkbox = QCheckBox()
        live2d_enabled_checkbox.setChecked(config.live2d.enabled)
        live2d_enabled_card = SettingCard(
            "启用Live2D", "控制是否启用Live2D功能（需要重启或切换模式生效）", live2d_enabled_checkbox, "live2d.enabled"
        )
        live2d_enabled_card.value_changed.connect(self.on_setting_changed)
        group.add_card(live2d_enabled_card)
        self.live2d_enabled_checkbox = live2d_enabled_checkbox

        group.set_collapsed(True)
        parent_layout.addWidget(group)

    def reset_ui_style_defaults(self):
        """重置 UI 风格相关设置为默认值"""
        defaults = UIConfig()
        live2d_defaults = Live2DConfig()
        updates = {
            "ui.user_name": defaults.user_name,
            "ui.bg_alpha": defaults.bg_alpha,
            "ui.window_bg_alpha": defaults.window_bg_alpha,
            "ui.mac_btn_size": defaults.mac_btn_size,
            "ui.mac_btn_margin": defaults.mac_btn_margin,
            "ui.mac_btn_gap": defaults.mac_btn_gap,
            "ui.animation_duration": defaults.animation_duration,
            "live2d.enabled": live2d_defaults.enabled,
        }

        widget_mapping = {
            "ui_user_name_input": ("setText", updates["ui.user_name"]),
            "ui_bg_alpha_spin": ("setValue", updates["ui.bg_alpha"]),
            "ui_window_alpha_spin": ("setValue", updates["ui.window_bg_alpha"]),
            "ui_mac_btn_size_spin": ("setValue", updates["ui.mac_btn_size"]),
            "ui_mac_btn_margin_spin": ("setValue", updates["ui.mac_btn_margin"]),
            "ui_mac_btn_gap_spin": ("setValue", updates["ui.mac_btn_gap"]),
            "ui_animation_duration_spin": ("setValue", updates["ui.animation_duration"]),
            "live2d_enabled_checkbox": ("setChecked", updates["live2d.enabled"]),
        }

        for attr_name, (setter_name, value) in widget_mapping.items():
            widget = getattr(self, attr_name, None)
            if widget is None:
                continue
            try:
                widget.blockSignals(True)
            except AttributeError:
                pass
            setter = getattr(widget, setter_name, None)
            if callable(setter):
                setter(value)
            try:
                widget.blockSignals(False)
            except AttributeError:
                pass

        self.pending_changes.update(updates)
        self.update_status_label("UI 风格已恢复默认值，记得保存生效")

    def create_naga_portal_group(self, parent_layout):
        group = SettingGroup("娜迦官网API申请")  # 折叠组 #

        # 标题栏右侧跳转按钮 #
        portal_btn = QPushButton("访问官网")
        portal_btn.setStyleSheet(NAGA_PORTAL_BUTTON_STYLE)
        portal_btn.clicked.connect(self.open_naga_api)  # 复用原跳转 #
        group.set_right_widget(portal_btn)  # 放置在右侧 #

        # 用户名 #
        naga_user_input = QLineEdit()
        naga_user_input.setText(getattr(config.naga_portal, "username", ""))
        naga_user_input.setStyleSheet(INPUT_STYLE)
        naga_user_card = SettingCard("用户名", "娜迦官网登录用户名", naga_user_input, "naga_portal.username")
        naga_user_card.value_changed.connect(self.on_setting_changed)
        group.add_card(naga_user_card)

        # 密码 #
        naga_pwd_input = QLineEdit()
        naga_pwd_input.setText(getattr(config.naga_portal, "password", ""))
        naga_pwd_input.setEchoMode(QLineEdit.Password)
        naga_pwd_input.setStyleSheet(INPUT_STYLE)
        naga_pwd_card = SettingCard("密码", "娜迦官网登录密码", naga_pwd_input, "naga_portal.password")
        naga_pwd_card.value_changed.connect(self.on_setting_changed)
        group.add_card(naga_pwd_card)

        group.set_collapsed(True)  # 默认收起 #
        parent_layout.addWidget(group)

    def create_xiayuan_group(self, parent_layout):
        group = SettingGroup("夏园记忆系统")
        # grag部分
        if hasattr(config.grag, "neo4j_uri"):
            neo4j_uri_input = QLineEdit()
            neo4j_uri_input.setText(config.grag.neo4j_uri)
            neo4j_uri_input.setStyleSheet(INPUT_STYLE)
            neo4j_uri_card = SettingCard("Neo4j URI", "知识图谱数据库地址", neo4j_uri_input, "grag.neo4j_uri")
            neo4j_uri_card.value_changed.connect(self.on_setting_changed)
            group.add_card(neo4j_uri_card)
        if hasattr(config.grag, "neo4j_user"):
            neo4j_user_input = QLineEdit()
            neo4j_user_input.setText(config.grag.neo4j_user)
            neo4j_user_input.setStyleSheet(INPUT_STYLE)
            neo4j_user_card = SettingCard("Neo4j 用户名", "知识图谱数据库用户名", neo4j_user_input, "grag.neo4j_user")
            neo4j_user_card.value_changed.connect(self.on_setting_changed)
            group.add_card(neo4j_user_card)
        if hasattr(config.grag, "neo4j_password"):
            neo4j_pwd_input = QLineEdit()
            neo4j_pwd_input.setText(config.grag.neo4j_password)
            neo4j_pwd_input.setEchoMode(QLineEdit.Password)
            neo4j_pwd_input.setStyleSheet(INPUT_STYLE)
            neo4j_pwd_card = SettingCard("Neo4j 密码", "知识图谱数据库密码", neo4j_pwd_input, "grag.neo4j_password")
            neo4j_pwd_card.value_changed.connect(self.on_setting_changed)
            group.add_card(neo4j_pwd_card)

        # Similarity Threshold
        if hasattr(config.grag, "similarity_threshold"):
            sim_slider = QSlider(Qt.Horizontal)
            sim_slider.setRange(0, 100)
            sim_slider.setValue(int(config.grag.similarity_threshold * 100))
            sim_slider.setStyleSheet(SLIDER_STYLE)
            sim_card = SettingCard("相似度阈值", "知识图谱检索的相似度阈值", sim_slider, "grag.similarity_threshold")
            sim_card.value_changed.connect(self.on_setting_changed)
            group.add_card(sim_card)
            self.sim_slider = sim_slider

        parent_layout.addWidget(group)

    def create_voice_input_group(self, parent_layout):
        """创建语音输入设置组（ASR）"""
        group = SettingGroup("语音输入设置")

        # 如果配置存在，显示语音输入设置
        if hasattr(config, "voice_realtime"):
            # === 基础设置 ===
            # 启用语音输入
            voice_input_enabled_checkbox = QCheckBox()
            voice_input_enabled_checkbox.setChecked(config.voice_realtime.enabled)
            voice_input_enabled_checkbox.setStyleSheet(CHECKBOX_STYLE)
            voice_input_enabled_card = SettingCard(
                "启用语音输入",
                "启用语音识别（ASR）功能，支持实时语音转文本",
                voice_input_enabled_checkbox,
                "voice_realtime.enabled",
            )
            voice_input_enabled_card.value_changed.connect(self.on_setting_changed)
            group.add_card(voice_input_enabled_card)

            # 语音模式选择
            mode_combo = QComboBox()
            mode_combo.addItems(["auto", "local", "end2end", "hybrid"])
            current_mode = getattr(config.voice_realtime, "voice_mode", "auto")
            mode_combo.setCurrentText(current_mode)
            mode_combo.setStyleSheet(COMBO_STYLE)
            mode_card = SettingCard(
                "语音模式",
                "auto:自动选择 | local:本地离线 | end2end:端到端 | hybrid:混合模式",
                mode_combo,
                "voice_realtime.voice_mode",
            )
            mode_card.value_changed.connect(self.on_setting_changed)
            mode_card.value_changed.connect(self.on_voice_mode_changed)  # 监听模式变化
            group.add_card(mode_card)
            self.voice_mode_combo = mode_combo  # 保存引用

            # 服务提供商
            provider_combo = QComboBox()
            provider_combo.addItems(["local", "qwen", "openai"])
            provider_combo.setCurrentText(config.voice_realtime.provider)
            provider_combo.setStyleSheet(COMBO_STYLE)
            self.provider_card = SettingCard(
                "ASR服务提供商",
                "local:本地FunASR | qwen:通义千问 | openai:OpenAI",
                provider_combo,
                "voice_realtime.provider",
            )
            self.provider_card.value_changed.connect(self.on_setting_changed)
            self.provider_card.value_changed.connect(self.on_voice_provider_changed)  # 监听提供商变化
            group.add_card(self.provider_card)
            self.voice_provider_combo = provider_combo  # 保存引用

            # === 本地模式专用设置 ===
            # ASR服务地址（本地模式）
            asr_host_input = QLineEdit()
            asr_host_input.setText(getattr(config.voice_realtime, "asr_host", "localhost"))
            asr_host_input.setStyleSheet(INPUT_STYLE)
            self.asr_host_card = SettingCard(
                "ASR服务地址", "本地FunASR服务地址（仅本地模式）", asr_host_input, "voice_realtime.asr_host"
            )
            self.asr_host_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.asr_host_card)

            # ASR服务端口（本地模式）
            asr_port_spin = QSpinBox()
            asr_port_spin.setRange(1, 65535)
            asr_port_spin.setValue(getattr(config.voice_realtime, "asr_port", 5000))
            asr_port_spin.setStyleSheet(SPIN_STYLE)
            self.asr_port_card = SettingCard(
                "ASR服务端口", "本地FunASR服务端口（仅本地模式）", asr_port_spin, "voice_realtime.asr_port"
            )
            self.asr_port_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.asr_port_card)

            # 录音时长（本地模式）
            record_duration_spin = QSpinBox()
            record_duration_spin.setRange(5, 60)
            record_duration_spin.setValue(getattr(config.voice_realtime, "record_duration", 10))
            record_duration_spin.setStyleSheet(SPIN_STYLE)
            self.record_duration_card = SettingCard(
                "最大录音时长", "本地模式最大录音时长（秒）", record_duration_spin, "voice_realtime.record_duration"
            )
            self.record_duration_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.record_duration_card)

            # === 云端模式设置 ===
            # API密钥（云端模式）
            api_key_input = QLineEdit()
            api_key_input.setText(config.voice_realtime.api_key)
            api_key_input.setEchoMode(QLineEdit.Password)
            api_key_input.setStyleSheet(INPUT_STYLE)
            self.api_key_card = SettingCard(
                "API密钥", "语音服务API密钥（云端模式）", api_key_input, "voice_realtime.api_key"
            )
            self.api_key_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.api_key_card)

            # 模型选择（云端模式）
            model_input = QLineEdit()
            model_input.setText(config.voice_realtime.model)
            model_input.setStyleSheet(INPUT_STYLE)
            self.model_card = SettingCard(
                "ASR模型名称", "语音识别模型名称（云端模式）", model_input, "voice_realtime.model"
            )
            self.model_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.model_card)

            # VAD阈值（云端模式）
            vad_slider = QSlider(Qt.Horizontal)
            vad_slider.setRange(0, 100)
            vad_slider.setValue(int(config.voice_realtime.vad_threshold * 100))
            vad_slider.setStyleSheet(SLIDER_STYLE)
            vad_label = QLabel(f"{config.voice_realtime.vad_threshold:.2f}")
            vad_label.setStyleSheet(LABEL_STYLE)
            vad_slider.valueChanged.connect(lambda v: vad_label.setText(f"{v / 100:.2f}"))
            vad_container = QWidget()
            vad_layout = QHBoxLayout(vad_container)
            vad_layout.setContentsMargins(0, 0, 0, 0)
            vad_layout.addWidget(vad_slider)
            vad_layout.addWidget(vad_label)
            self.vad_card = SettingCard(
                "静音检测阈值", "VAD静音检测灵敏度（云端模式）", vad_container, "voice_realtime.vad_threshold"
            )
            self.vad_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.vad_card)

            # 初始化显示状态
            self.update_voice_cards_visibility()

            # 初始化时检查模式，如果是local模式则禁用provider选择
            if hasattr(self, "voice_mode_combo") and hasattr(self, "voice_provider_combo"):
                if self.voice_mode_combo.currentText() == "local":
                    self.voice_provider_combo.setCurrentText("local")
                    self.voice_provider_combo.setEnabled(False)
                    # 应用禁用样式
                    self.voice_provider_combo.setStyleSheet(COMBO_STYLE + VOICE_MODE_DISABLED_STYLE)

        parent_layout.addWidget(group)

    def create_voice_output_group(self, parent_layout):
        """创建语音输出设置组（TTS）"""
        group = SettingGroup("语音输出设置")

        # 如果配置存在，显示语音输出设置
        if hasattr(config, "voice_realtime"):
            # === TTS基础设置 ===
            # TTS语音选择
            tts_voice_combo = QComboBox()
            tts_voices = [
                "zh-CN-XiaoyiNeural",  # 中文女声
                "zh-CN-YunxiNeural",  # 中文男声
                "zh-CN-XiaoxiaoNeural",  # 中文女童
                "en-US-JennyNeural",  # 英文女声
                "en-US-GuyNeural",  # 英文男声
            ]
            tts_voice_combo.addItems(tts_voices)
            current_tts_voice = getattr(config.voice_realtime, "tts_voice", "zh-CN-XiaoyiNeural")
            tts_voice_combo.setCurrentText(current_tts_voice)
            tts_voice_combo.setStyleSheet(COMBO_STYLE)
            self.tts_voice_card = SettingCard(
                "TTS语音", "文本转语音的声音选择", tts_voice_combo, "voice_realtime.tts_voice"
            )
            self.tts_voice_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.tts_voice_card)

            # === TTS服务设置 ===
            # TTS服务地址
            tts_host_input = QLineEdit()
            tts_host_input.setText(getattr(config.voice_realtime, "tts_host", "localhost"))
            tts_host_input.setStyleSheet(INPUT_STYLE)
            self.tts_host_card = SettingCard(
                "TTS服务地址", "本地TTS服务地址", tts_host_input, "voice_realtime.tts_host"
            )
            self.tts_host_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.tts_host_card)

            # TTS服务端口
            tts_port_spin = QSpinBox()
            tts_port_spin.setRange(1, 65535)
            tts_port_spin.setValue(getattr(config.voice_realtime, "tts_port", 5061))
            tts_port_spin.setStyleSheet(SPIN_STYLE)
            self.tts_port_card = SettingCard("TTS服务端口", "本地TTS服务端口", tts_port_spin, "voice_realtime.tts_port")
            self.tts_port_card.value_changed.connect(self.on_setting_changed)
            group.add_card(self.tts_port_card)

            # === 高级设置 ===
            # 自动播放
            auto_play_checkbox = QCheckBox()
            auto_play_checkbox.setChecked(getattr(config.voice_realtime, "auto_play", True))
            auto_play_checkbox.setStyleSheet(CHECKBOX_STYLE)
            auto_play_card = SettingCard(
                "自动播放", "AI回复后自动播放语音", auto_play_checkbox, "voice_realtime.auto_play"
            )
            auto_play_card.value_changed.connect(self.on_setting_changed)
            group.add_card(auto_play_card)

            # 打断播放
            interrupt_playback_checkbox = QCheckBox()
            interrupt_playback_checkbox.setChecked(getattr(config.voice_realtime, "interrupt_playback", True))
            interrupt_playback_checkbox.setStyleSheet(CHECKBOX_STYLE)
            interrupt_playback_card = SettingCard(
                "允许打断",
                "用户说话时自动打断AI语音播放",
                interrupt_playback_checkbox,
                "voice_realtime.interrupt_playback",
            )
            interrupt_playback_card.value_changed.connect(self.on_setting_changed)
            group.add_card(interrupt_playback_card)

        parent_layout.addWidget(group)

    def create_mqtt_group(self, parent_layout):
        group = SettingGroup("MQTT 配置")
        if hasattr(config.mqtt, "broker"):
            mqtt_broker_input = QLineEdit()
            mqtt_broker_input.setText(config.mqtt.broker)
            mqtt_broker_input.setStyleSheet(INPUT_STYLE)
            mqtt_broker_card = SettingCard("MQTT Broker", "MQTT服务器地址", mqtt_broker_input, "mqtt.broker")
            mqtt_broker_card.value_changed.connect(self.on_setting_changed)
            group.add_card(mqtt_broker_card)
        if hasattr(config.mqtt, "port"):
            mqtt_port_spin = QSpinBox()
            mqtt_port_spin.setRange(1, 65535)
            mqtt_port_spin.setValue(config.mqtt.port)
            mqtt_port_spin.setStyleSheet(SPIN_STYLE)
            mqtt_port_card = SettingCard("MQTT端口", "MQTT服务器端口", mqtt_port_spin, "mqtt.port")
            mqtt_port_card.value_changed.connect(self.on_setting_changed)
            group.add_card(mqtt_port_card)
        if hasattr(config.mqtt, "username"):
            mqtt_user_input = QLineEdit()
            mqtt_user_input.setText(config.mqtt.username)
            mqtt_user_input.setStyleSheet(INPUT_STYLE)
            mqtt_user_card = SettingCard("MQTT用户名", "MQTT服务器用户名", mqtt_user_input, "mqtt.username")
            mqtt_user_card.value_changed.connect(self.on_setting_changed)
            group.add_card(mqtt_user_card)
        if hasattr(config.mqtt, "password"):
            mqtt_pwd_input = QLineEdit()
            mqtt_pwd_input.setText(config.mqtt.password)
            mqtt_pwd_input.setEchoMode(QLineEdit.Password)
            mqtt_pwd_input.setStyleSheet(INPUT_STYLE)
            mqtt_pwd_card = SettingCard("MQTT密码", "MQTT服务器密码", mqtt_pwd_input, "mqtt.password")
            mqtt_pwd_card.value_changed.connect(self.on_setting_changed)
            group.add_card(mqtt_pwd_card)
        parent_layout.addWidget(group)

    def create_openclaw_group(self, parent_layout):
        """创建 OpenClaw 集成设置组"""
        group = SettingGroup("OpenClaw 集成")

        # 右侧文档按钮
        docs_btn = QPushButton("官方文档")
        docs_btn.setStyleSheet(OPENCLAW_DOCS_BUTTON_STYLE)
        docs_btn.clicked.connect(self.open_openclaw_docs)
        group.set_right_widget(docs_btn)

        # 检测 OpenClaw 安装状态
        self.openclaw_status = None
        self.detect_openclaw_status()

        # 安装状态显示卡片
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(12)

        # 状态标签
        self.openclaw_status_label = QLabel("检测中...")
        self.openclaw_status_label.setStyleSheet(LABEL_STYLE)
        status_layout.addWidget(self.openclaw_status_label)

        status_layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton("刷新状态")
        refresh_btn.setStyleSheet(OPENCLAW_REFRESH_BUTTON_STYLE)
        refresh_btn.clicked.connect(self.refresh_openclaw_status)
        status_layout.addWidget(refresh_btn)

        status_card = SettingCard("安装状态", "检测本机 OpenClaw 安装情况 (~/.openclaw)", status_widget)
        group.add_card(status_card)

        # Gateway URL
        self.openclaw_gateway_input = QLineEdit()
        self.openclaw_gateway_input.setStyleSheet(INPUT_STYLE)
        self.openclaw_gateway_input.setPlaceholderText("http://localhost:18789")
        gateway_card = SettingCard(
            "Gateway 地址",
            "OpenClaw Gateway 服务地址（默认端口 18789）",
            self.openclaw_gateway_input,
            "openclaw.gateway_url",
        )
        gateway_card.value_changed.connect(self.on_setting_changed)
        group.add_card(gateway_card)

        # Token
        self.openclaw_token_input = QLineEdit()
        self.openclaw_token_input.setStyleSheet(INPUT_STYLE)
        self.openclaw_token_input.setEchoMode(QLineEdit.Password)
        self.openclaw_token_input.setPlaceholderText("自动从 ~/.openclaw/openclaw.json 读取")
        token_card = SettingCard(
            "认证 Token", "Gateway 认证令牌（对应 gateway.auth.token）", self.openclaw_token_input, "openclaw.token"
        )
        token_card.value_changed.connect(self.on_setting_changed)
        group.add_card(token_card)

        # 连接状态
        connection_widget = QWidget()
        connection_layout = QHBoxLayout(connection_widget)
        connection_layout.setContentsMargins(0, 0, 0, 0)
        connection_layout.setSpacing(12)

        self.openclaw_connection_label = QLabel("未检测")
        self.openclaw_connection_label.setStyleSheet(LABEL_STYLE)
        connection_layout.addWidget(self.openclaw_connection_label)

        connection_layout.addStretch()

        # 测试连接按钮
        test_btn = QPushButton("测试连接")
        test_btn.setStyleSheet(OPENCLAW_REFRESH_BUTTON_STYLE)
        test_btn.clicked.connect(self.test_openclaw_connection)
        connection_layout.addWidget(test_btn)

        connection_card = SettingCard("连接状态", "测试与 OpenClaw Gateway 的连接", connection_widget)
        group.add_card(connection_card)

        # 启用开关
        self.openclaw_enabled_checkbox = QCheckBox()
        self.openclaw_enabled_checkbox.setStyleSheet(CHECKBOX_STYLE)
        enabled_card = SettingCard(
            "启用 OpenClaw",
            "启用后 Naga 可以调度 OpenClaw 执行任务",
            self.openclaw_enabled_checkbox,
            "openclaw.enabled",
        )
        enabled_card.value_changed.connect(self.on_setting_changed)
        group.add_card(enabled_card)

        # ========== OpenClaw 状态监控卡片（使用全宽卡片而非 SettingCard）==========
        monitor_card = QWidget()
        monitor_card.setStyleSheet(SYSTEM_PROMPT_CARD_STYLE)  # 复用系统提示词卡片样式

        monitor_layout = QVBoxLayout(monitor_card)
        monitor_layout.setContentsMargins(16, 16, 16, 16)
        monitor_layout.setSpacing(12)

        # 标题行（标题 + 刷新按钮）
        monitor_header = QHBoxLayout()
        monitor_header.setSpacing(12)

        monitor_title = QLabel("状态监控")
        monitor_title.setStyleSheet(SYSTEM_PROMPT_TITLE_STYLE)
        monitor_header.addWidget(monitor_title)

        self.openclaw_monitor_status_label = QLabel("请和 OpenClaw 交互以显示状态")
        self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_IDLE_STYLE)
        monitor_header.addWidget(self.openclaw_monitor_status_label)

        monitor_header.addStretch()

        # 刷新按钮
        refresh_monitor_btn = QPushButton("刷新")
        refresh_monitor_btn.setFixedSize(60, 28)
        refresh_monitor_btn.setStyleSheet(OPENCLAW_REFRESH_BUTTON_STYLE)
        refresh_monitor_btn.clicked.connect(self.refresh_openclaw_monitor)
        monitor_header.addWidget(refresh_monitor_btn)

        monitor_layout.addLayout(monitor_header)

        # 描述
        monitor_desc = QLabel("显示 OpenClaw 实时状态和 Naga 调度的交互记录")
        monitor_desc.setStyleSheet(SYSTEM_PROMPT_DESC_STYLE)
        monitor_layout.addWidget(monitor_desc)

        # OpenClaw 状态详情（显示 session_status 返回的信息）
        status_label = QLabel("OpenClaw 状态:")
        status_label.setStyleSheet(LABEL_STYLE)
        monitor_layout.addWidget(status_label)

        self.openclaw_status_text = QTextEdit()
        self.openclaw_status_text.setReadOnly(True)
        self.openclaw_status_text.setStyleSheet(OPENCLAW_MONITOR_TEXT_STYLE)
        self.openclaw_status_text.setMinimumHeight(100)
        self.openclaw_status_text.setMaximumHeight(150)
        self.openclaw_status_text.setPlaceholderText("OpenClaw 状态信息将在此显示...")
        self.openclaw_status_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        monitor_layout.addWidget(self.openclaw_status_text)

        # API 交互历史（显示最近的消息）
        self.openclaw_history_label = QLabel("最近交互:")
        self.openclaw_history_label.setStyleSheet(LABEL_STYLE)
        monitor_layout.addWidget(self.openclaw_history_label)

        self.openclaw_history_text = QTextEdit()
        self.openclaw_history_text.setReadOnly(True)
        self.openclaw_history_text.setStyleSheet(OPENCLAW_MONITOR_TEXT_STYLE)
        self.openclaw_history_text.setMinimumHeight(80)
        self.openclaw_history_text.setMaximumHeight(120)
        self.openclaw_history_text.setPlaceholderText("对话历史将在此显示...")
        self.openclaw_history_text.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        monitor_layout.addWidget(self.openclaw_history_text)

        group.add_card(monitor_card)

        # 设置定时刷新（每 2 秒，更实时）
        self.openclaw_monitor_timer = QTimer()
        self.openclaw_monitor_timer.timeout.connect(self.refresh_openclaw_monitor)
        self.openclaw_monitor_timer.start(2000)

        # 初始化
        QTimer.singleShot(500, self.refresh_openclaw_monitor)

        # 更新UI显示
        self.update_openclaw_ui()

        parent_layout.addWidget(group)

    def detect_openclaw_status(self):
        """检测 OpenClaw 安装状态"""
        try:
            from agentserver.openclaw import detect_openclaw

            self.openclaw_status = detect_openclaw(check_connection=False)
        except Exception as e:
            print(f"检测 OpenClaw 状态失败: {e}")
            self.openclaw_status = None

    def update_openclaw_ui(self):
        """更新 OpenClaw UI 显示"""
        if self.openclaw_status is None:
            self.openclaw_status_label.setText("检测失败")
            self.openclaw_status_label.setStyleSheet(OPENCLAW_STATUS_NOT_INSTALLED_STYLE)
            return

        if self.openclaw_status.installed:
            version_text = f"v{self.openclaw_status.version}" if self.openclaw_status.version else ""
            self.openclaw_status_label.setText(f"已安装 {version_text}")
            self.openclaw_status_label.setStyleSheet(OPENCLAW_STATUS_INSTALLED_STYLE)

            # 自动填充检测到的配置
            if self.openclaw_status.gateway_url:
                self.openclaw_gateway_input.setText(self.openclaw_status.gateway_url)

            if self.openclaw_status.gateway_token:
                self.openclaw_token_input.setText(self.openclaw_status.gateway_token)

            # 设置启用状态
            self.openclaw_enabled_checkbox.setChecked(self.openclaw_status.gateway_enabled)
        else:
            self.openclaw_status_label.setText("未安装")
            self.openclaw_status_label.setStyleSheet(OPENCLAW_STATUS_NOT_INSTALLED_STYLE)
            # 使用默认值
            self.openclaw_gateway_input.setText("http://localhost:18789")
            self.openclaw_enabled_checkbox.setChecked(False)

    def refresh_openclaw_status(self):
        """刷新 OpenClaw 状态"""
        self.openclaw_status_label.setText("检测中...")
        self.openclaw_status_label.setStyleSheet(LABEL_STYLE)

        # 使用 QTimer 延迟执行，避免界面卡顿
        QTimer.singleShot(100, self._do_refresh_openclaw)

    def _do_refresh_openclaw(self):
        """实际执行 OpenClaw 状态刷新"""
        self.detect_openclaw_status()
        self.update_openclaw_ui()
        self.update_status_label("OpenClaw 状态已刷新")

    def test_openclaw_connection(self):
        """测试 OpenClaw 连接"""
        self.openclaw_connection_label.setText("测试中...")
        self.openclaw_connection_label.setStyleSheet(LABEL_STYLE)

        # 使用 QTimer 延迟执行
        QTimer.singleShot(100, self._do_test_openclaw_connection)

    def _do_test_openclaw_connection(self):
        """实际执行 OpenClaw 连接测试"""
        try:
            from agentserver.openclaw import OpenClawDetector

            detector = OpenClawDetector()
            gateway_url = self.openclaw_gateway_input.text() or "http://localhost:18789"

            # 同步检查连接
            reachable = detector._check_gateway_connection(gateway_url)

            if reachable:
                self.openclaw_connection_label.setText("已连接")
                self.openclaw_connection_label.setStyleSheet(OPENCLAW_CONNECTED_STYLE)
                self.update_status_label("OpenClaw Gateway 连接成功")
            else:
                self.openclaw_connection_label.setText("无法连接")
                self.openclaw_connection_label.setStyleSheet(OPENCLAW_DISCONNECTED_STYLE)
                self.update_status_label("OpenClaw Gateway 连接失败")
        except Exception as e:
            self.openclaw_connection_label.setText(f"错误: {str(e)[:20]}")
            self.openclaw_connection_label.setStyleSheet(OPENCLAW_DISCONNECTED_STYLE)
            self.update_status_label(f"连接测试失败: {e}")

    def open_openclaw_docs(self):
        """打开 OpenClaw 官方文档"""
        import webbrowser

        try:
            webbrowser.open("https://docs.openclaw.ai/")
        except Exception as e:
            print(f"打开 OpenClaw 文档失败: {e}")

    def refresh_openclaw_monitor(self):
        """刷新 OpenClaw 状态监控 - 显示真实的对话内容"""
        try:
            import httpx
            from system.config import get_server_port

            agent_server_port = get_server_port("agent_server")

            with httpx.Client(timeout=8.0) as client:
                # 1. 获取 Naga 的会话信息
                session_key = None
                try:
                    session_resp = client.get(f"http://127.0.0.1:{agent_server_port}/openclaw/session")
                    if session_resp.status_code == 200:
                        session_data = session_resp.json()
                        if session_data.get("has_session"):
                            session = session_data.get("session", {})
                            session_key = session.get("session_key")
                            self.openclaw_monitor_status_label.setText(
                                f"会话: {session_key or 'N/A'} · 消息: {session.get('message_count', 0)}"
                            )
                            self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_ACTIVE_STYLE)
                        else:
                            self.openclaw_monitor_status_label.setText("请和 OpenClaw 交互以显示对话")
                            self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_IDLE_STYLE)
                            self.openclaw_status_text.setPlaceholderText("等待与 OpenClaw 交互...")
                            self.openclaw_history_text.setPlaceholderText("对话历史将在此显示...")
                            return
                    elif session_resp.status_code == 503:
                        self.openclaw_monitor_status_label.setText("OpenClaw 客户端未就绪")
                        self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_ERROR_STYLE)
                        return
                except Exception as e:
                    self.openclaw_monitor_status_label.setText(f"连接失败: {str(e)[:30]}")
                    self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_ERROR_STYLE)
                    return

                # 2. 获取 OpenClaw 当前状态
                try:
                    status_resp = client.get(f"http://127.0.0.1:{agent_server_port}/openclaw/status")
                    if status_resp.status_code == 200:
                        status_data = status_resp.json()
                        if status_data.get("success"):
                            status_text = status_data.get("status_text", "")
                            if status_text:
                                self.openclaw_status_text.setText(status_text)
                            else:
                                self.openclaw_status_text.setText("OpenClaw 空闲中...")
                        else:
                            self.openclaw_status_text.setText(f"状态获取失败: {status_data.get('error', 'unknown')}")
                    else:
                        self.openclaw_status_text.setText(f"HTTP {status_resp.status_code}")
                except Exception as e:
                    self.openclaw_status_text.setText(f"状态查询失败: {str(e)[:50]}")

                # 3. 获取真实的会话历史消息
                try:
                    history_resp = client.get(
                        f"http://127.0.0.1:{agent_server_port}/openclaw/history", params={"limit": 10}
                    )
                    if history_resp.status_code == 200:
                        history_data = history_resp.json()
                        if history_data.get("success"):
                            messages = history_data.get("messages", [])
                            if messages:
                                # 格式化对话历史
                                history_lines = []
                                for msg in messages:
                                    role = msg.get("role", "unknown")
                                    content = msg.get("content", "")[:80]
                                    if role == "user":
                                        history_lines.append(f"[User] {content}")
                                    elif role == "assistant":
                                        history_lines.append(f"[Agent] {content}")
                                    else:
                                        # 处理 raw 类型
                                        if content:
                                            history_lines.append(content[:100])

                                if history_lines:
                                    self.openclaw_history_text.setText("\n".join(history_lines))
                                else:
                                    # 回退到本地任务记录
                                    self._show_local_tasks(client, agent_server_port)
                            else:
                                # 没有远程消息，显示本地任务记录
                                self._show_local_tasks(client, agent_server_port)
                        else:
                            error = history_data.get("error", "unknown")
                            if error == "no_session":
                                self.openclaw_history_text.setText("尚未建立会话，请先发送消息")
                            else:
                                self.openclaw_history_text.setText(f"获取历史失败: {error}")
                    else:
                        self.openclaw_history_text.setText(f"HTTP {history_resp.status_code}")
                except Exception as e:
                    self.openclaw_history_text.setText(f"历史查询失败: {str(e)[:50]}")

                # 滚动到底部显示最新内容
                self.openclaw_status_text.verticalScrollBar().setValue(
                    self.openclaw_status_text.verticalScrollBar().maximum()
                )
                self.openclaw_history_text.verticalScrollBar().setValue(
                    self.openclaw_history_text.verticalScrollBar().maximum()
                )

        except Exception as e:
            self.openclaw_monitor_status_label.setText("Agent 服务器未运行")
            self.openclaw_monitor_status_label.setStyleSheet(OPENCLAW_TERMINAL_IDLE_STYLE)
            self.openclaw_status_text.setText(f"错误: {str(e)[:100]}")

    def _show_local_tasks(self, client, agent_server_port):
        """显示本地发送的任务记录作为历史"""
        try:
            tasks_resp = client.get(f"http://127.0.0.1:{agent_server_port}/openclaw/tasks")
            if tasks_resp.status_code == 200:
                tasks_data = tasks_resp.json()
                tasks = tasks_data.get("tasks", [])
                if tasks:
                    # 显示最近的任务
                    history_lines = []
                    for task in tasks[-8:]:  # 最近8条
                        msg = task.get("message", "")[:60]
                        status = task.get("status", "unknown")
                        status_icon = "✓" if status == "completed" else ("⏳" if status == "running" else "✗")
                        history_lines.append(f"{status_icon} [Naga→OC] {msg}")
                    self.openclaw_history_text.setText("\n".join(history_lines))
                else:
                    self.openclaw_history_text.setText("暂无发送记录\n请通过 Naga 向 OpenClaw 发送消息")
            else:
                self.openclaw_history_text.setText("暂无交互记录")
        except Exception:
            self.openclaw_history_text.setText("暂无交互记录")

    def create_save_section(self, parent_layout):
        """创建保存区域"""
        save_container = QWidget()
        save_container.setFixedHeight(60)
        save_layout = QHBoxLayout(save_container)
        save_layout.setContentsMargins(0, 10, 0, 10)

        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(STATUS_LABEL_STYLE)
        save_layout.addWidget(self.status_label)

        save_layout.addStretch()

        # 重置按钮
        reset_btn = QPushButton("重置")
        reset_btn.setFixedSize(80, 36)
        reset_btn.setStyleSheet(RESET_BUTTON_STYLE)
        reset_btn.clicked.connect(self.reset_settings)
        save_layout.addWidget(reset_btn)

        # 保存按钮
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setFixedSize(100, 36)
        self.save_btn.setStyleSheet(SAVE_BUTTON_STYLE)
        self.save_btn.clicked.connect(self.save_settings)
        save_layout.addWidget(self.save_btn)

        parent_layout.addWidget(save_container)

    def on_setting_changed(self, setting_key, value):
        """处理设置变化"""
        # 统一转换为新式键名，兼容旧逻辑 #
        key_map = {
            "STREAM_MODE": "system.stream_mode",
            "DEBUG": "system.debug",
        }
        normalized_key = key_map.get(setting_key, setting_key)
        self.pending_changes[normalized_key] = value
        self.update_status_label(f"● {normalized_key} 已修改")

        # 移除实时透明度预览，避免动画卡顿
        # 透明度设置将在保存时统一应用

    def on_voice_mode_changed(self, setting_key, value):
        """处理语音模式变化，动态显示/隐藏相关设置"""
        # 先调用通用处理
        self.on_setting_changed(setting_key, value)

        # 处理不同模式的逻辑
        if value == "local" and hasattr(self, "voice_provider_combo"):
            # local模式：强制设置provider为local并禁用
            self.voice_provider_combo.setCurrentText("local")
            self.voice_provider_combo.setEnabled(False)
            # 更新样式显示禁用状态
            self.voice_provider_combo.setStyleSheet(COMBO_STYLE + VOICE_MODE_DISABLED_STYLE)
            # 同时更新配置
            self.on_setting_changed("voice_realtime.provider", "local")

        elif value == "auto" and hasattr(self, "voice_provider_combo"):
            # auto模式：允许选择provider，根据provider自动决定实际模式
            self.voice_provider_combo.setEnabled(True)
            self.voice_provider_combo.setStyleSheet(COMBO_STYLE)
            # auto模式不改变当前provider选择

        elif value in ["end2end", "hybrid"] and hasattr(self, "voice_provider_combo"):
            # end2end和hybrid模式：需要云端provider
            self.voice_provider_combo.setEnabled(True)
            self.voice_provider_combo.setStyleSheet(COMBO_STYLE)
            # 如果当前是local，切换到qwen
            if self.voice_provider_combo.currentText() == "local":
                self.voice_provider_combo.setCurrentText("qwen")
                self.on_setting_changed("voice_realtime.provider", "qwen")

        # 更新卡片显示状态
        self.update_voice_cards_visibility()

    def on_voice_provider_changed(self, setting_key, value):
        """处理语音提供商变化，动态显示/隐藏相关设置"""
        # 先调用通用处理
        self.on_setting_changed(setting_key, value)

        # 如果在auto模式下选择了local provider，可以提示用户考虑切换到local模式
        if hasattr(self, "voice_mode_combo"):
            current_mode = self.voice_mode_combo.currentText()
            if current_mode == "auto" and value == "local":
                # 可选：自动切换到local模式
                # self.voice_mode_combo.setCurrentText('local')
                # self.on_voice_mode_changed('voice_realtime.voice_mode', 'local')
                pass  # 保持auto模式，让系统自动选择

        # 更新卡片显示状态
        self.update_voice_cards_visibility()

    def update_voice_cards_visibility(self):
        """根据当前语音模式和提供商动态显示/隐藏设置卡片"""
        if not hasattr(self, "voice_mode_combo"):
            return

        # 获取当前模式和提供商
        mode = self.voice_mode_combo.currentText() if hasattr(self, "voice_mode_combo") else "auto"
        provider = self.voice_provider_combo.currentText() if hasattr(self, "voice_provider_combo") else "qwen"

        # 如果是auto模式，根据provider推断实际模式
        if mode == "auto":
            if provider == "local":
                actual_mode = "local"
            elif hasattr(self, "pending_changes") and self.pending_changes.get("voice_realtime.use_api_server"):
                actual_mode = "hybrid"
            else:
                actual_mode = "end2end"
        else:
            actual_mode = mode

        # 本地模式专用设置
        local_cards = [
            getattr(self, "asr_host_card", None),
            getattr(self, "asr_port_card", None),
            getattr(self, "record_duration_card", None),
        ]

        # 云端模式专用设置
        cloud_cards = [
            getattr(self, "api_key_card", None),
            getattr(self, "model_card", None),
            getattr(self, "voice_role_card", None),
            getattr(self, "vad_card", None),
        ]

        # TTS设置（本地和混合模式）
        tts_cards = [
            getattr(self, "tts_voice_card", None),
        ]

        # 根据模式显示/隐藏卡片
        if actual_mode == "local":
            # 本地模式：显示本地设置和TTS，隐藏云端设置
            for card in local_cards:
                if card:
                    card.setVisible(True)
            for card in cloud_cards:
                if card:
                    card.setVisible(False)
            for card in tts_cards:
                if card:
                    card.setVisible(True)
        elif actual_mode == "end2end":
            # 端到端模式：显示云端设置，隐藏本地和TTS设置
            for card in local_cards:
                if card:
                    card.setVisible(False)
            for card in cloud_cards:
                if card:
                    card.setVisible(True)
            for card in tts_cards:
                if card:
                    card.setVisible(False)
        elif actual_mode == "hybrid":
            # 混合模式：显示云端设置和TTS，隐藏本地设置
            for card in local_cards:
                if card:
                    card.setVisible(False)
            for card in cloud_cards:
                if card:
                    card.setVisible(True)
            for card in tts_cards:
                if card:
                    card.setVisible(True)

    def update_status_label(self, text):
        """更新状态标签"""
        if not hasattr(self, "status_label") or self.status_label is None:
            return
        self.status_label.setText(text)
        # 3秒后清空状态
        QTimer.singleShot(3000, lambda: self.status_label.setText(""))

    def load_current_settings(self):
        """加载当前设置"""
        try:
            # API设置 - 优先从.env文件读取API密钥
            if hasattr(self, "api_key_input"):
                env_api_key = self.read_api_key_from_env()
                if env_api_key:
                    self.api_key_input.setText(env_api_key)
                else:
                    self.api_key_input.setText(
                        config.api.api_key if config.api.api_key != "sk-placeholder-key-not-set" else ""
                    )

            if hasattr(self, "base_url_input"):
                self.base_url_input.setText(config.api.base_url)

            # if hasattr(self, 'model_combo'):
            #     index = self.model_combo.findText(config.api.model)
            #     if index >= 0:
            #         self.model_combo.setCurrentIndex(index)

            # 系统设置
            if hasattr(self, "max_tokens_spin"):
                self.max_tokens_spin.setValue(config.api.max_tokens)
            if hasattr(self, "history_spin"):
                self.history_spin.setValue(config.api.max_history_rounds)
            if hasattr(self, "context_days_spin"):
                self.context_days_spin.setValue(config.api.context_load_days)
            if hasattr(self, "ui_user_name_input"):
                self.ui_user_name_input.setText(config.ui.user_name)
            if hasattr(self, "ui_bg_alpha_spin"):
                self.ui_bg_alpha_spin.setValue(config.ui.bg_alpha)
            if hasattr(self, "ui_window_alpha_spin"):
                self.ui_window_alpha_spin.setValue(config.ui.window_bg_alpha)
            if hasattr(self, "ui_mac_btn_size_spin"):
                self.ui_mac_btn_size_spin.setValue(config.ui.mac_btn_size)
            if hasattr(self, "ui_mac_btn_margin_spin"):
                self.ui_mac_btn_margin_spin.setValue(config.ui.mac_btn_margin)
            if hasattr(self, "ui_mac_btn_gap_spin"):
                self.ui_mac_btn_gap_spin.setValue(config.ui.mac_btn_gap)
            if hasattr(self, "ui_animation_duration_spin"):
                self.ui_animation_duration_spin.setValue(config.ui.animation_duration)

            # 电脑控制设置
            if hasattr(self, "computer_control_model_input"):
                self.computer_control_model_input.setText(config.computer_control.model)
            if hasattr(self, "computer_control_url_input"):
                self.computer_control_url_input.setText(config.computer_control.model_url)
            if hasattr(self, "computer_control_api_key_input"):
                self.computer_control_api_key_input.setText(config.computer_control.api_key)
            if hasattr(self, "grounding_model_input"):
                self.grounding_model_input.setText(config.computer_control.grounding_model)
            if hasattr(self, "grounding_url_input"):
                self.grounding_url_input.setText(config.computer_control.grounding_url)
            if hasattr(self, "grounding_api_key_input"):
                self.grounding_api_key_input.setText(config.computer_control.grounding_api_key)

            # 界面设置
            if hasattr(self, "voice_checkbox"):
                self.voice_checkbox.setChecked(config.system.voice_enabled)
            if hasattr(self, "debug_checkbox"):
                self.debug_checkbox.setChecked(config.system.debug)
            if hasattr(self, "log_combo"):
                index = self.log_combo.findText(config.system.log_level)
                if index >= 0:
                    self.log_combo.setCurrentIndex(index)

            # 高级设置
            if hasattr(self, "sim_slider"):
                self.sim_slider.setValue(int(config.grag.similarity_threshold * 100))

            # 系统提示词与AI名称回填 #
            if hasattr(self, "ai_name_input"):
                self.ai_name_input.setText(getattr(config.system, "ai_name", ""))
            if hasattr(self, "system_prompt_editor"):
                try:
                    from system.config import get_prompt  # 延迟导入 #

                    # 直接读取对话风格提示词文件 #
                    content = get_prompt("conversation_style_prompt")
                except Exception:
                    content = ""
                # 避免触发textChanged循环 #
                self.system_prompt_editor.blockSignals(True)
                self.system_prompt_editor.setPlainText(content)
                self.system_prompt_editor.blockSignals(False)

            # OpenClaw 设置 - 优先从检测器获取，其次从 config
            if hasattr(self, "openclaw_gateway_input") and hasattr(self, "openclaw_token_input"):
                # 先检测 OpenClaw 状态并更新 UI
                self.detect_openclaw_status()
                self.update_openclaw_ui()

                # 如果检测未获取到配置，使用 config 中的值
                if hasattr(config, "openclaw"):
                    if not self.openclaw_gateway_input.text():
                        self.openclaw_gateway_input.setText(config.openclaw.gateway_url)
                    if not self.openclaw_token_input.text() and config.openclaw.token:
                        self.openclaw_token_input.setText(config.openclaw.token)
                    if hasattr(self, "openclaw_enabled_checkbox"):
                        # 使用检测到的 enabled 状态或 config 中的值
                        if self.openclaw_status and self.openclaw_status.installed:
                            self.openclaw_enabled_checkbox.setChecked(self.openclaw_status.gateway_enabled)
                        else:
                            self.openclaw_enabled_checkbox.setChecked(config.openclaw.enabled)

        except Exception as e:
            print(f"加载设置失败: {e}")

    def read_api_key_from_env(self):
        """从.env文件读取API密钥"""
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("API_KEY"):
                        return line.strip().split("=", 1)[-1].strip()
        return ""

    def write_api_key_to_env(self, new_key):
        """将API密钥写入.env文件"""
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env_lines = []
        found = False

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
            for i, line in enumerate(env_lines):
                if line.strip().startswith("API_KEY"):
                    env_lines[i] = f"API_KEY={new_key}\n"
                    found = True
                    break
        if not found:
            env_lines.append(f"API_KEY={new_key}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(env_lines)

    def save_settings(self):
        """保存所有设置到config.json"""
        try:
            changes_count = len(self.pending_changes)
            prompt_changes_count = len(getattr(self, "pending_prompts", {}))

            if changes_count == 0:
                # 没有config更改，若有提示词更改也继续保存 #
                if prompt_changes_count == 0:
                    self.update_status_label("● 没有需要保存的更改")
                    return

            # 使用配置管理器进行统一的配置更新
            try:
                from system.config_manager import update_config
            except ImportError as e:
                # 如果导入失败，尝试重新设置路径
                import sys
                import os

                project_root = os.path.abspath(os.path.dirname(__file__) + "/..")
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)
                from system.config_manager import update_config
            # 将扁平化的配置键值对转换为嵌套字典格式
            nested_updates = self._convert_to_nested_updates(self.pending_changes)

            ui_updates = nested_updates.get("ui", {}) if nested_updates else {}

            # 特殊处理API密钥 - 先写入.env文件
            if "api.api_key" in self.pending_changes:
                self.write_api_key_to_env(self.pending_changes["api.api_key"])

            # 通过配置管理器更新配置（会自动写入config.json并触发热更新）
            success = True
            if changes_count > 0:
                success = update_config(nested_updates)
                if not success:
                    self.update_status_label("✗ 配置更新失败")
                    return

            # 保存系统提示词到文件 #
            if success and ui_updates:
                for attr, value in ui_updates.items():
                    try:
                        setattr(config.ui, attr, value)
                    except Exception:
                        pass
            if success and hasattr(config, "window") and getattr(config, "window", None):
                try:
                    config.window.apply_ui_style()
                except Exception:
                    pass

            if prompt_changes_count > 0:
                try:
                    from system.config import save_prompt  # 延迟导入 #

                    for name, content in self.pending_prompts.items():
                        save_prompt(name, content)
                except Exception as e:
                    self.update_status_label(f"✗ 提示词保存失败: {e}")
                    return

            self.update_status_label(f"✓ 已保存 配置{changes_count}项/提示词{prompt_changes_count}项")
            self.pending_changes.clear()
            if hasattr(self, "pending_prompts"):
                self.pending_prompts.clear()

            # 等待配置重新加载完成
            import time

            time.sleep(0.2)

            # 重新加载设置到界面，确保显示最新值
            self.load_current_settings()

            # 发送设置变化信号
            self.settings_changed.emit("all", None)

        except Exception as e:
            error_msg = str(e)
            print(f"设置保存失败: {error_msg}")  # 打印详细错误信息到控制台
            self.update_status_label(f"✗ 保存失败: {error_msg}")

    def open_naga_api(self):
        """打开娜迦API网站"""
        import webbrowser

        try:
            webbrowser.open("https://naga.furina.chat/")
        except Exception as e:
            print(f"打开娜迦API网站失败: {e}")

    def _convert_to_nested_updates(self, flat_updates: dict) -> dict:
        """将扁平化的配置键值对转换为嵌套字典格式"""
        nested_updates = {}

        for setting_key, value in flat_updates.items():
            # 解析嵌套的配置键 (例如 "api.api_key")
            keys = setting_key.split(".")
            current = nested_updates

            # 导航到父级
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            # 设置值，处理特殊转换
            final_key = keys[-1]
            if setting_key in ["api.temperature", "grag.similarity_threshold"]:
                # 温度、相似度值从0-100转换为0.0-1.0
                current[final_key] = value / 100.0
            else:
                current[final_key] = value

        return nested_updates

    def reset_settings(self):
        """重置所有设置"""
        self.pending_changes.clear()
        self.load_current_settings()
        self.update_status_label("● 设置已重置")


from nagaagent_core.vendors.PyQt5.QtCore import Qt
from nagaagent_core.vendors.PyQt5.QtWidgets import (
    QWidget,
    QTextEdit,
    QSizePolicy,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QStackedWidget,
    QScrollArea,
    QSplitter,
)
from ui.controller import setting


class SettingWidget(QWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.setStyleSheet("""
                    #SettingsPage {
                        background: transparent;
                        border-radius: 24px;
                        padding: 12px;
                    }
                """)
        layout = QVBoxLayout(self)
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
        self.settings_widget = ElegantSettingsWidget(scroll_content)
        self.settings_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.settings_widget.settings_changed.connect(setting.on_settings_changed)
        scroll_layout.addWidget(self.settings_widget, 1)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)


if __name__ == "__main__":
    from nagaagent_core.vendors.PyQt5.QtWidgets import QApplication  # 统一入口 # type: ignore

    app = QApplication([])

    # 创建测试窗口
    test_window = QWidget()
    test_window.setStyleSheet(TEST_WINDOW_STYLE)
    test_window.resize(800, 600)

    layout = QVBoxLayout(test_window)

    # 添加设置界面
    settings = ElegantSettingsWidget()
    settings.settings_changed.connect(lambda key, value: print(f"设置变化: {key} = {value}"))

    layout.addWidget(settings)

    test_window.show()
    app.exec_()
