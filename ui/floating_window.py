import sys
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit, QApplication
from PyQt5.QtCore import Qt, QPoint, QPropertyAnimation, QRect, pyqtSignal
from PyQt5.QtGui import QFont


class FloatingWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 200);
                border-radius: 10px;
            }
            QPushButton {
                background-color: rgba(60, 60, 60, 180);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: rgba(80, 80, 80, 200);
            }
            QTextEdit {
                background-color: rgba(50, 50, 50, 180);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 5px;
            }
            QLabel {
                color: white;
            }
        """)

        self.collapsed_width = 200
        self.collapsed_height = 60
        self.expanded_width = 400
        self.expanded_height = 300
        
        self.is_expanded = False
        self.dragging = False
        self.drag_position = QPoint()

        self.init_ui()
        self.setGeometry(100, 100, self.collapsed_width, self.collapsed_height)

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel("娜迦助手")
        self.title_label.setFont(QFont("Arial", 12, QFont.Bold))
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # Toggle button
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(30, 30)
        self.toggle_btn.clicked.connect(self.toggle_expand)
        header_layout.addWidget(self.toggle_btn)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.close_window)
        header_layout.addWidget(close_btn)

        main_layout.addLayout(header_layout)

        # Content area (only visible when expanded)
        self.content_area = QTextEdit()
        self.content_area.setPlainText("这里是娜迦助手的内容区域...")
        self.content_area.setVisible(False)
        main_layout.addWidget(self.content_area)

        self.setLayout(main_layout)

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        
        if self.is_expanded:
            self.toggle_btn.setText("▲")
            self.content_area.setVisible(True)
            target_size = QRect(self.x(), self.y(), self.expanded_width, self.expanded_height)
        else:
            self.toggle_btn.setText("▼")
            self.content_area.setVisible(False)
            target_size = QRect(self.x(), self.y(), self.collapsed_width, self.collapsed_height)

        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(200)
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(target_size)
        self.animation.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            new_pos = event.globalPos() - self.drag_position
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()

    def close_window(self):
        self.closed.emit()
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FloatingWindow()
    window.show()
    sys.exit(app.exec_())
