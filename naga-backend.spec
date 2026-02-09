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

# 需要打包的数据文件
datas = [
    ('system/prompts', 'system/prompts'),
    ('config.json', '.'),
    ('mcpserver', 'mcpserver'),
    ('agentserver', 'agentserver'),
    ('apiserver', 'apiserver'),
    ('system', 'system'),
    ('summer_memory', 'summer_memory'),
    ('voice', 'voice'),
    ('mqtt_tool', 'mqtt_tool'),
    ('skills', 'skills'),
    ('nagaagent_core', 'nagaagent_core'),
]

# 第三方包的数据文件（py2neo 需要 VERSION 文件等）
datas += collect_data_files('py2neo')

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
    # 其他
    'key_value',
    'key_value.aio',
    'redis',
    'requests',
]

# 排除 PyQt5、UI 及不需要的大型科学计算库
excludes = [
    # PyQt / UI
    'PyQt5', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PyQt5.QtCore', 'PyQt5.QtOpenGL',
    'ui', 'tkinter',
    # 图像 / 可视化
    'matplotlib', 'PIL', 'Pillow',
    # 科学计算（后端不需要）
    'torch', 'torchaudio', 'torchvision', 'torchgen', 'torchdata',
    'scipy', 'sympy',
    'vtk', 'vtkmodules',
    # 地理 / 数据分析
    'geopandas', 'folium', 'branca', 'xyzservices', 'fiona', 'shapely', 'pyproj',
    'pandas', 'dask',
    # NLP（后端直接调 API，不需要本地模型）
    'nltk', 'spacy', 'transformers',
    # Jupyter / 测试
    'IPython', 'jupyter', 'notebook', 'nbconvert', 'nbformat',
    'pytest', 'unittest',
    # 其他大型库
    'cv2', 'opencv', 'skimage', 'sklearn',
    'bokeh', 'plotly', 'seaborn',
    'sqlalchemy',
    'lxml',
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
