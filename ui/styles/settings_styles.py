"""
设置界面样式配置文件
将设置界面的样式从主代码中解耦出来，统一管理
"""

# 系统提示词卡片样式
SYSTEM_PROMPT_CARD_STYLE = """
QWidget {
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 10px;
    margin: 2px;
}
QWidget:hover {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 40);
}
"""

# 系统提示词编辑器样式
SYSTEM_PROMPT_EDITOR_STYLE = """
QTextEdit {
    background: rgba(17,17,17,180);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 6px;
    padding: 8px 12px;
    font: 10pt 'Lucida Console';
    line-height: 1.4;
}
QTextEdit:focus {
    border: 1px solid rgba(100, 200, 255, 100);
}
"""

# 系统提示词标题样式
SYSTEM_PROMPT_TITLE_STYLE = """
QLabel {
    color: #fff;
    font: 12pt 'Lucida Console';
    font-weight: bold;
    background: transparent;
    border: none;
}
"""

# 系统提示词描述样式
SYSTEM_PROMPT_DESC_STYLE = """
QLabel {
    color: rgba(255, 255, 255, 120);
    font: 9pt 'Lucida Console';
    background: transparent;
    border: none;
}
"""

# 设置卡片样式
SETTING_CARD_STYLE = """
SettingCard {
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 10px;
    margin: 2px;
}
SettingCard:hover {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 40);
}
"""

# 输入框样式
INPUT_STYLE = """
QLineEdit {
    background: rgba(17,17,17,180);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 6px;
    padding: 6px 10px;
    font: 10pt 'Lucida Console';
}
QLineEdit:focus {
    border: 1px solid rgba(100, 200, 255, 100);
}
"""

# 下拉框样式
COMBO_STYLE = """
QComboBox {
    background: rgba(17,17,17,180);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 6px;
    padding: 6px 10px;
    font: 10pt 'Lucida Console';
}
QComboBox:hover {
    border: 1px solid rgba(255, 255, 255, 80);
}
QComboBox::drop-down {
    border: none;
}
QComboBox::down-arrow {
    image: none;
    border: none;
}
"""

# 复选框样式
CHECKBOX_STYLE = """
QCheckBox {
    color: #fff;
    font: 10pt 'Lucida Console';
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid rgba(255, 255, 255, 50);
    background: rgba(17,17,17,180);
}
QCheckBox::indicator:checked {
    background: rgba(100, 200, 255, 150);
    border: 1px solid rgba(100, 200, 255, 200);
}
"""

# 滑块样式
SLIDER_STYLE = """
QSlider::groove:horizontal {
    border: 1px solid rgba(255, 255, 255, 30);
    height: 6px;
    background: rgba(17,17,17,180);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: rgba(100, 200, 255, 150);
    border: 1px solid rgba(100, 200, 255, 200);
    width: 16px;
    border-radius: 8px;
    margin: -5px 0;
}
QSlider::handle:horizontal:hover {
    background: rgba(120, 220, 255, 180);
}
"""

# 数字输入框样式
SPIN_STYLE = """
QSpinBox, QDoubleSpinBox {
    background: rgba(17,17,17,180);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 6px;
    padding: 6px 10px;
    font: 10pt 'Lucida Console';
}
QSpinBox:focus {
    border: 1px solid rgba(100, 200, 255, 100);
}
"""

# 设置组头部样式
SETTING_GROUP_HEADER_STYLE = """
QWidget {
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 30);
    margin-bottom: 2px;
}
"""

# 设置组头部按钮样式
SETTING_GROUP_HEADER_BUTTON_STYLE = """
QPushButton {
    color: #fff;
    font: 16pt 'Lucida Console';
    font-weight: bold;
    background: transparent;
    border: none;
    padding: 10px 0;
    text-align: left;
}
QPushButton:hover {
    color: #e8f6ff;
}
"""

# 滚动区域样式
SCROLL_AREA_STYLE = """
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
"""

# 状态标签样式
STATUS_LABEL_STYLE = """
QLabel {
    color: rgba(255, 255, 255, 120);
    font: 10pt 'Lucida Console';
    background: transparent;
    border: none;
}
"""

# 保存按钮样式
SAVE_BUTTON_STYLE = """
QPushButton {
    background: rgba(100, 200, 100, 150);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 8px;
    padding: 6px 12px;
    font: 11pt 'Lucida Console';
    font-weight: bold;
}
QPushButton:hover {
    border: 1px solid rgba(255, 255, 255, 80);
    background: rgba(120, 220, 120, 180);
}
QPushButton:pressed {
    background: rgba(80, 180, 80, 200);
}
"""

# 重置按钮样式
RESET_BUTTON_STYLE = """
QPushButton {
    background: rgba(100, 100, 100, 150);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 8px;
    padding: 6px 12px;
    font: 11pt 'Lucida Console';
}
QPushButton:hover {
    border: 1px solid rgba(255, 255, 255, 80);
    background: rgba(120, 120, 120, 180);
}
QPushButton:pressed {
    background: rgba(80, 80, 80, 200);
}
"""

# 设置卡片样式
SETTING_CARD_BASE_STYLE = """
SettingCard {
    background: rgba(255, 255, 255, 8);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 10px;
    margin: 2px;
}
SettingCard:hover {
    background: rgba(255, 255, 255, 15);
    border: 1px solid rgba(255, 255, 255, 40);
}
"""

# 设置卡片标题样式
SETTING_CARD_TITLE_STYLE = """
QLabel {
    color: #fff;
    font: 12pt 'Lucida Console';
    font-weight: bold;
    background: transparent;
    border: none;
}
"""

# 设置卡片描述样式
SETTING_CARD_DESC_STYLE = """
QLabel {
    color: rgba(255, 255, 255, 120);
    font: 9pt 'Lucida Console';
    background: transparent;
    border: none;
}
"""

# 设置组头部容器样式
SETTING_GROUP_HEADER_CONTAINER_STYLE = """
QWidget {
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 30);
    margin-bottom: 2px;
}
"""

# 设置组头部按钮样式
SETTING_GROUP_HEADER_BUTTON_STYLE = """
QPushButton {
    color: #fff;
    font: 16pt 'Lucida Console';
    font-weight: bold;
    background: transparent;
    border: none;
    padding: 10px 0;
    text-align: left;
}
QPushButton:hover {
    color: #e8f6ff;
}
"""

# 设置组右侧标签样式
SETTING_GROUP_RIGHT_LABEL_STYLE = """
QLabel {
    color: rgba(255,255,255,180);
    font: 10pt 'Lucida Console';
    background: transparent;
}
"""

# 滚动内容样式
SCROLL_CONTENT_STYLE = """
QWidget {
    background: transparent;
}
"""

# 娜迦官网按钮样式
NAGA_PORTAL_BUTTON_STYLE = """
QPushButton {
    background: rgba(100, 200, 255, 150);
    color: #fff;
    border: 1px solid rgba(255, 255, 255, 50);
    border-radius: 6px;
    padding: 6px 12px;
    font: 10pt 'Lucida Console';
    font-weight: bold;
}
QPushButton:hover {
    border: 1px solid rgba(255, 255, 255, 80);
    background: rgba(120, 220, 255, 180);
}
QPushButton:pressed {
    background: rgba(80, 180, 255, 200);
}
"""

# 语音模式禁用状态样式
VOICE_MODE_DISABLED_STYLE = """
QComboBox:disabled {
    background: rgba(50, 50, 50, 150);
    color: rgba(255, 255, 255, 100);
}
"""

# 测试窗口样式
TEST_WINDOW_STYLE = """
QWidget {
    background: rgba(25, 25, 25, 220);
    color: white;
}
"""

# 标签样式
LABEL_STYLE = """
QLabel {
    color: #fff;
    font: 10pt 'Lucida Console';
}
"""

# 对话框标题样式
DIALOG_HEADER_TITLE_STYLE = """
QLabel {
    color: #fff;
    font: 14pt 'Lucida Console';
    font-weight: bold;
    background: transparent;
    border: none;
}
"""

# 对话框提示文本样式
DIALOG_HINT_LABEL_STYLE = """
QLabel {
    color: rgba(255, 255, 255, 160);
    font: 10pt 'Lucida Console';
    background: transparent;
    border: none;
}
"""

# 对话框 Tab 样式
DIALOG_TAB_BAR_STYLE = """
QTabWidget::pane {
    background: transparent;
    border: none;
}
QTabBar::tab {
    background: rgba(255, 255, 255, 8);
    color: rgba(255, 255, 255, 180);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 18px;
    padding: 8px 22px;
    font: 11pt 'Lucida Console';
    margin: 0px 6px;
}
QTabBar::tab:selected {
    background: rgba(100, 200, 255, 120);
    color: #fff;
    border: 1px solid rgba(120, 220, 255, 200);
}
QTabBar::tab:hover {
    background: rgba(255, 255, 255, 18);
    color: #fff;
}
"""

# 对话框搜索容器样式
DIALOG_SEARCH_CONTAINER_STYLE = """
QWidget#Live2DSearchContainer {
    background: rgba(255, 255, 255, 6);
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 24px;
    padding: 4px 12px;
}
"""

# 动作卡片样式
ACTION_CARD_WIDGET_STYLE = """
QWidget#Live2DActionCard {
    background: rgba(255, 255, 255, 10);
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 16px;
    padding: 10px;
}
QWidget#Live2DActionCard:hover {
    background: rgba(255, 255, 255, 18);
    border: 1px solid rgba(120, 220, 255, 160);
}
QWidget#Live2DActionCard[selected="true"] {
    background: rgba(120, 220, 255, 80);
    border: 1px solid rgba(120, 220, 255, 220);
}
QWidget#Live2DActionCard QLabel {
    color: #fff;
}
QLabel#Live2DActionIcon {
    font: 26pt 'Segoe UI Emoji';
}
QLabel#Live2DActionName {
    font: 10pt 'Lucida Console';
    font-weight: bold;
}
QLabel#Live2DActionType {
    color: rgba(200, 230, 255, 220);
    font: 9pt 'Lucida Console';
}
"""
