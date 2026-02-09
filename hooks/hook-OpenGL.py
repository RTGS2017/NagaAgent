"""
PyInstaller hook for OpenGL
确保OpenGL相关模块和平台文件被正确打包
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import os
import sys

# 收集OpenGL的所有子模块
hiddenimports = collect_submodules('OpenGL')

# 确保包含OpenGL平台相关模块
hiddenimports.extend([
    'OpenGL.platform',
    'OpenGL.platform.egl',
    'OpenGL.platform.glx',
    'OpenGL.platform.win32',
    'OpenGL.platform.darwin',
    'OpenGL.platform.base_platform',
    'OpenGL_accelerate',
])

# 收集OpenGL数据文件
datas = []
binaries = []
try:
    import OpenGL
    opengl_path = os.path.dirname(OpenGL.__file__)
    
    # 收集平台文件
    platform_path = os.path.join(opengl_path, 'platform')
    if os.path.exists(platform_path):
        platform_files = collect_data_files('OpenGL.platform')
        datas.extend(platform_files)
    
    # 收集其他重要数据文件
    opengl_files = collect_data_files('OpenGL')
    datas.extend(opengl_files)
    
except ImportError:
    pass

# 对于Linux系统，确保包含EGL相关文件
if sys.platform.startswith('linux'):
    hiddenimports.extend([
        'OpenGL.EGL',
        'OpenGL.raw.EGL',
    ])
    
    # 尝试收集系统EGL库（如果存在）
    egl_paths = [
        '/usr/lib/x86_64-linux-gnu/libEGL.so',
        '/usr/lib/libEGL.so',
        '/usr/local/lib/libEGL.so',
    ]
    
    for egl_path in egl_paths:
        if os.path.exists(egl_path):
            binaries.append((egl_path, '.'))