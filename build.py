from requests import get as iget
from zipfile import ZipFile
from os import remove, name, system, chdir as cd
from shutil import rmtree as rm
from zipfile import ZIP_DEFLATED
import os
IS_WINDOWS = True if name == 'nt' else False

print("开始下载运行时文件...")
url = 'https://www.pylindex.top/naga/files/build_files/py3119.zip'
response = iget(url)
with open("py3119.zip", "wb") as code:
    code.write(response.content)

f = ZipFile("py3119.zip", 'r')
for file in f.namelist():
    f.extract(file, ".")
f.close()

remove("py3119.zip")
rm(".venv")

print("运行时文件下载完成，开始安装依赖...")
if IS_WINDOWS:
    system(".\\py3119\\python.exe -m pip install --upgrade pip --no-warn-script-location. -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
    system(".\\py3119\\python.exe -m pip install --upgrade setuptools wheel -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
    system(".\\py3119\\python.exe -m pip install -r requirements.txt --no-warn-script-location -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
else:
    system("wine ./py3119/python.exe -m pip install --upgrade pip setuptools wheel --no-warn-script-location. -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")
    system("wine ./py3119/python.exe -m pip install -r requirements.txt --no-warn-script-location -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple")

print("依赖安装完成，开始打包...")
with open("使用必看说明.txt", "w", encoding="utf-8") as f:
    f.write("""双击 启动.cmd 即可运行
有问题请反馈至QQ：1708213363
config.json配置可参考README.md相关部分
使用需在config.json内填入api_key，可前往Deepseek申请一个（无账号请注册，并充值几元钱）：https://platform.deepseek.com
""")

with open("启动.cmd", "w", encoding="utf-8") as f:
    f.write("""@echo off
chcp 65001
set PATH=""
.\\py3119\\python.exe main.py
""")
    
with open(".is_package", "w", encoding="utf-8") as f:
    f.write("""更新占位文件""")
    
cd("..")

archive_name = 'NagaAgent_Win64.zip'
root_dir = './NagaAgent'

with ZipFile(archive_name, 'w', compression=ZIP_DEFLATED) as zf:
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # don't descend into any .git directories
        dirnames[:] = [d for d in dirnames if d != '.git']
        for fname in filenames:
            file_path = os.path.join(dirpath, fname)
            arcname = os.path.relpath(file_path, root_dir)
            print(f'Adding {arcname}')
            zf.write(file_path, arcname)

print("打包完成")
