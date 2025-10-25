# -*- mode: python ; coding: utf-8 -*-

# pyproject.toml requires python >=3.11,<3.12

# 收集所有需要的资源文件
# (source_path, destination_in_bundle)
datas = [
    ('config.json.example', '.'),
    ('config.json', '.'),
    ('LICENSE', '.'),
    ('pyproject.toml', '.'),
    ('README.md', '.'),
    ('requirements.txt', '.'),
]

# 收集需要包含的目录
# Tree 对象需要在 Analysis 中单独处理
trees = [
    Tree('agentserver', prefix='agentserver'),
    Tree('apiserver', prefix='apiserver'),
    Tree('game', prefix='game'),
    Tree('logs', prefix='logs'),
    Tree('mcpserver', prefix='mcpserver'),
    Tree('mqtt_tool', prefix='mqtt_tool'),
    Tree('summer_memory', prefix='summer_memory'),
    Tree('system', prefix='system'),
    Tree('ui', prefix='ui'),
    Tree('voice', prefix='voice'),
]

# 添加py2neo包的VERSION文件到数据文件
import py2neo
py2neo_path = py2neo.__file__
py2neo_dir = os.path.dirname(py2neo_path)
version_file = os.path.join(py2neo_dir, 'VERSION')
if os.path.exists(version_file):
    datas.append((version_file, 'py2neo'))

# 添加图标文件到数据文件
icon_files = [
    'ui/img/icons/naga_chat.png',
    'ui/img/icons/love_adventure.png',
    'ui/img/icons/personality_game.png',
    'ui/img/icons/mind_map.png'
]
for icon_file in icon_files:
    if os.path.exists(icon_file):
        datas.append((icon_file, 'ui/img/icons'))

# 添加样式文件到数据文件
datas.append(('ui/styles/progress.txt', 'ui/styles'))

# 收集所有 agent-manifest.json 文件
from pathlib import Path
for manifest_path in Path('mcpserver').rglob('agent-manifest.json'):
    datas.append((str(manifest_path), str(manifest_path.parent)))

a = Analysis(
    ['main.py'],
    pathex=['/data0/code/NagaAgent'],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# 添加 Tree 对象到分析结果
for tree in trees:
    a.datas += tree

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NagaAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False, # 不使用UPX，保证速度和兼容性
    console=True, # GUI应用，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None # 您可以指定一个图标路径, e.g., icon='ui/img/icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='main',
)
