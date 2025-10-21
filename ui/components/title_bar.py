import sys, os; sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))
from nagaagent_core.vendors.PyQt5.QtWidgets import QWidget, QPushButton
from nagaagent_core.vendors.PyQt5.QtCore import Qt, QRect
from nagaagent_core.vendors.PyQt5.QtGui import QColor, QPainter, QFont
from system.config import config, logger


def get_ui_config():
    """获取UI配置，确保使用最新的配置"""
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


class TitleBar(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.setFixedHeight(100)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._offset = None

        self._button_specs = [
            ('-', '#FFBD2E', '#ffe084', lambda: self.parent().showMinimized()),
            ('×', '#FF5F57', '#ff8783', lambda: self.parent().close()),
        ]
        self._buttons = []
        for idx, (txt, color, hover, cb) in enumerate(self._button_specs):
            btn = QPushButton(txt, self)
            btn.clicked.connect(cb)
            self._buttons.append((btn, color, hover))
            if idx == 0:
                self.btn_min = btn
            else:
                self.btn_close = btn
        self.update_style()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._offset = e.globalPos() - self.parent().frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._offset and e.buttons() & Qt.LeftButton:
            self.parent().move(e.globalPos() - self._offset)

    def mouseReleaseEvent(self, e):
        self._offset = None

    def paintEvent(self, e):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        qp.setPen(QColor(255, 255, 255, 180))
        qp.drawLine(0, 2, w, 2)
        qp.drawLine(0, h - 3, w, h - 3)
        font = QFont("Consolas", max(10, (h - 40) // 2), QFont.Bold)
        qp.setFont(font)
        rect = QRect(0, 20, w, h - 40)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            qp.setPen(QColor(0, 0, 0))
            qp.drawText(rect.translated(dx, dy), Qt.AlignCenter, self.text)
        qp.setPen(QColor(255, 255, 255))
        qp.drawText(rect, Qt.AlignCenter, self.text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_buttons()

    def update_style(self):
        refresh_ui_constants()
        for btn, color, hover in self._buttons:
            btn.setFixedSize(MAC_BTN_SIZE, MAC_BTN_SIZE)
            btn.setStyleSheet(
                f"QPushButton{{background:{color};border:none;border-radius:{MAC_BTN_SIZE//2}px;color:#fff;font:18pt;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
        self._layout_buttons()
        self.update()

    def _layout_buttons(self):
        if not self._buttons:
            return
        x = self.width() - MAC_BTN_MARGIN
        for i, (btn, _, _) in enumerate(self._buttons):
            btn.move(x - MAC_BTN_SIZE * (2 - i) - MAC_BTN_GAP * (1 - i), 36)
