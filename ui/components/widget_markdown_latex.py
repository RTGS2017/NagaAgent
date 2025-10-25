
# markdown_latex_widget.py
import re
import os
import tempfile
from pathlib import Path
from nagaagent_core.vendors.PyQt5.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QApplication, QLabel, QSizePolicy
from nagaagent_core.vendors.PyQt5.QtWebEngineWidgets import QWebEngineView
from nagaagent_core.vendors.PyQt5.QtCore import Qt, QUrl
from markdown import markdown


# ---------- 与 demo 相同的模板 ----------
TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>PyQt5 Markdown+Latex+HTML Demo</title>
<script>
window.MathJax = {{
  tex: {{
    inlineMath: [ ['$','$'], ['\\(','\\)'] ],   // 启用 $…$
    displayMath: [ ['$$','$$'], ['\\[','\\]'] ]
  }}
}};
</script>
<script src="https://polyfill.alicdn.com/v3/polyfill.min.js?features=es6 "></script>
<script id="MathJax-script" async
        src="https://jsd.onmicrosoft.cn/npm/mathjax@3/es5/tex-mml-chtml.js "></script>
<style>
body{{font-family:"Segoe UI",Arial,sans-serif;margin:20px;color:#ffffff;background:transparent;}}
code{{background:#f4f4f4;padding:2px 4px;border-radius:3px;}}
pre{{background:#f6f8fa;padding:10px;border-radius:5px;overflow:auto;}}
table{{border-collapse:collapse;}}
th,td{{border:1px solid #ddd;padding:6px 10px;}}
th{{background:#f2f2f2;}}
</style>
</head>
<body>
{content}
</body>
</html>"""


def md_tex_to_html(raw: str) -> str:
    """与 demo 完全一致"""
    block_cache = {}
    def block_save(m):
        key = f"___BLOCK_MATH_{len(block_cache)}___"
        block_cache[key] = m.group(0)
        return key
    text = re.sub(r'\$\$(.*?)\$\$', block_save, raw, flags=re.S)

    inline_cache = {}
    def inline_save(m):
        key = f"___INLINE_MATH_{len(inline_cache)}___"
        inline_cache[key] = m.group(0)
        return key
    text = re.sub(r'(?<!\$)\$(?!\$)(.+?)\$(?!\$)', inline_save, text)

    for k, v in block_cache.items():
        text = text.replace(k, v)
    for k, v in inline_cache.items():
        text = text.replace(k, v)

    html = markdown(text, extensions=['extra', 'codehilite'])
    return TEMPLATE.format(content=html)


# ---------- 可复用 Widget ----------
class MarkdownLatexWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._temp_files = []          # 用于清理
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 顶部工具栏（可选：隐藏即可）
        toolbar = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新", self)
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        # 浏览器核心
        self.browser = QWebEngineView(self)
        layout.addWidget(self.browser)

        self.browser.page().setBackgroundColor(Qt.transparent)  # Qt 5.12+
        # 老版本 Qt 用 self.browser.page().mainFrame().setScrollBarPolicy(...)
        # 若仍无效，再补一行：
        self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
        pol = self.browser.sizePolicy()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # 同时把内部的 QWebEngineView 也改成同样策略
        self.browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.browser.setSizePolicy(pol)
        self.setMinimumHeight(20)

    # 对外唯一接口
    def set_text(self, markdown_text: str):
        html = md_tex_to_html(markdown_text)
        temp = tempfile.NamedTemporaryFile(mode='w', suffix='.html',
                                           delete=False, encoding='utf-8')
        temp.write(html)
        temp.close()
        self.browser.load(QUrl.fromLocalFile(temp.name))
        self._temp_files.append(temp.name)

    # 重新加载当前文本（如果内部有编辑器可调用）
    def refresh(self):
        # 如果以后加编辑器，这里重新抓取文本即可
        pass

    # 清理临时文件
    def closeEvent(self, event):
        for f in self._temp_files:
            try:
                os.unlink(f)
            except Exception:
                pass
        event.accept()
# 在你的主窗口代码里
from nagaagent_core.vendors.PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("主窗口")
        self.resize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 1. 直接创建组件
        self.md_widget = MarkdownLatexWidget(self)
        layout.addWidget(self.md_widget)

        # 2. 灌入任意文本
        self.md_widget.set_text(r"""
# 测试文档

行内公式 $E=mc^2$，块级公式：
$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

| 语言   | 年份 |
|--------|------|
| Python | 1991 |

```python
print("hello")
```

<p style="color:red;">原生 HTML 不会被破坏</p>
        """)


if __name__ == '__main__':
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec_()