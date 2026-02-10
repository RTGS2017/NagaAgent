# -*- mode: python ; coding: utf-8 -*-
"""
NagaAgent Headless Backend - PyInstaller Spec
编译后端为独立二进制，供 Electron 前端打包使用。
排除 PyQt5 及 UI 相关模块。
"""

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(SPECPATH))

# 需要打包的数据文件（mcpserver / mqtt_tool 已禁用，不再打包）
datas = [
    ('system/prompts', 'system/prompts'),
    ('config.json', '.'),
    # ('mcpserver', 'mcpserver'),  # 已禁用
    ('agentserver', 'agentserver'),
    ('apiserver', 'apiserver'),
    ('system', 'system'),
    ('summer_memory', 'summer_memory'),
    ('voice', 'voice'),
    # ('mqtt_tool', 'mqtt_tool'),  # 已禁用
    ('skills', 'skills'),
    ('nagaagent_core', 'nagaagent_core'),
]

# 第三方包的数据文件
datas += collect_data_files('tiktoken')
datas += collect_data_files('tiktoken_ext')
datas += collect_data_files('litellm')

# 动态导入的模块（PyInstaller 静态分析可能遗漏）
hiddenimports = [
    # Web 框架
    'uvicorn',
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'starlette',
    # HTTP 客户端
    'httpx',
    'httpcore',
    # LLM
    'langchain_openai',
    'litellm',
    'openai',
    # 数据处理
    'pydantic',
    'json5',
    'charset_normalizer',
    # 异步
    'asyncio',
    'anyio',
    # 其他（MCP/redis 已禁用）
    # 'key_value',
    # 'key_value.aio',
    # 'redis',
    'requests',
    # tiktoken 编码
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
]

# 排除不需要的大型库（环境有 910 个包，只需约 27 个核心包）
excludes = [
    # PyQt / Qt / UI
    'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PyQt5.QtCore', 'PyQt5.QtOpenGL',
    'PyQt6', 'PyQt6.QtWidgets', 'PyQt6.QtGui', 'PyQt6.QtCore',
    'ui', 'tkinter',
    # 深度学习框架（后端调 API，不跑本地模型）
    'torch', 'torchaudio', 'torchvision', 'torchgen', 'torchdata',
    'paddle', 'paddlenlp', 'paddleocr',
    'tensorflow', 'keras',
    'onnxruntime', 'onnx',
    'transformers', 'accelerate', 'diffusers', 'safetensors',
    'modelscope',
    # 科学计算
    'scipy', 'sympy', 'numba', 'llvmlite',
    'statsmodels', 'patsy',
    # 数据处理 / 分析
    'pandas', 'polars', '_polars_runtime_32', 'pyarrow', 'dask',
    'geopandas', 'folium', 'branca', 'xyzservices', 'fiona', 'shapely', 'pyproj', 'pyogrio',
    'h5py', 'tables',
    # 可视化
    'matplotlib', 'bokeh', 'plotly', 'seaborn', 'panel', 'holoviews', 'datashader',
    # 图像 / CV（MCP可选，不打包）
    'cv2', 'opencv', 'skimage', 'sklearn',
    # NLP 本地库
    'nltk', 'spacy', 'gensim',
    # 分布式 / 大数据
    'pyspark', 'ray', 'distributed',
    # Google / Cloud（不需要）
    'googleapiclient', 'google.cloud', 'google.auth', 'google_auth_httplib2',
    # 音视频处理（MCP可选）
    'av', 'librosa', 'soundfile', 'pyaudio',
    # Web 工具（不需要）
    'gradio', 'streamlit', 'dash',
    # Jupyter / 开发工具
    'IPython', 'jupyter', 'notebook', 'nbconvert', 'nbformat', 'nbclassic',
    'sphinx', 'docutils',
    'pytest', 'unittest',
    'spyder', 'pylint', 'autopep8', 'flake8', 'mypy',
    # 浏览器自动化（MCP可选）
    'playwright', 'patchright', 'selenium',
    # 数据库 ORM
    'sqlalchemy', 'alembic',
    # 国际化
    'babel',
    # 漫画（MCP可选）
    'jmcomic',
    # 其他大型库
    'lxml', 'wandb', 'mlflow',
    'faiss', 'milvus_lite',
    'pymupdf', 'fitz',
    'astropy',
    # GUI 自动化（MCP可选）
    'pyautogui', 'pytesseract', 'pycaw', 'screen_brightness_control',
    # 图数据库（连接失败也不影响）
    'neo4j', 'py2neo', 'pyneo', 'pyvis',
    # 游戏 / 音频播放
    'pygame',
    # 爬虫（MCP可选）
    'crawl4ai',
    # 压缩（MCP可选）
    'py7zr', 'pyzipper',
    # 其他可选
    'gevent', 'flask', 'docx2pdf', 'img2pdf', 'msoffcrypto', 'pikepdf',
    'dashscope', 'Crypto', 'pycryptodome',
    'agents',
    'jieba',
]

a = Analysis(
    ['main.py'],
    pathex=[PROJECT_ROOT, os.path.join(PROJECT_ROOT, 'nagaagent-core')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='naga-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # headless 模式需要控制台输出
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='naga-backend',
)
