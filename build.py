import os
import shutil
import subprocess
import sys
import platform
import glob

def user_confirmation():
    """提示清空配置，让用户确认是否继续"""
    print("=========================================")
    print("  提示：此操作将清空并重建配置（删除 config.json）。")
    print("=========================================")
    response = input("请确认是否继续 (输入 'Y' 继续，或按 Enter/n 取消): ").strip().lower()
    
    if response != 'y' and response != '':
        print("\n操作已取消。")
        sys.exit(0)

def check_uv():
    """检查 uv 是否存在，不存在就提示安装，然后退出"""
    print("\n[1/8] 检查 uv 是否已安装...")
    try:
        # 运行 uv --version 来检查是否存在
        # capture_output=True 和 check=True 确保在失败时能捕获输出或抛出异常
        subprocess.run(['uv', '--version'], 
                       capture_output=True, 
                       text=True, 
                       check=True) 
        print("    -> uv 检查通过。")
    except FileNotFoundError:
        print("\n[错误] 找不到 'uv' 命令。")
        print("请先安装 uv (推荐使用 pipx install uv) 或确保它在系统 PATH 中。")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n[错误] 执行 'uv --version' 失败，返回非零状态码: {e.returncode}")
        print("请检查 uv 安装是否正确。")
        sys.exit(1)

def manage_config_files():
    """删除 config.json 并复制 config.json.example"""
    config_file = "config.json"
    example_file = "config.json.example"

    print(f"\n[2/8] 删除 {config_file}...")
    try:
        os.remove(config_file)
        print(f"    -> {config_file} 已删除。")
    except FileNotFoundError:
        print(f"    -> {config_file} 不存在，跳过删除。")
    except Exception as e:
        print(f"[错误] 删除 {config_file} 失败: {e}")
        sys.exit(1)

    print(f"\n[3/8] 复制 {example_file} 到 {config_file}...")
    try:
        shutil.copy2(example_file, config_file)
        print("    -> 配置已重置。")
    except FileNotFoundError:
        print(f"[错误] 找不到 {example_file}，请确保文件存在。")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 复制文件失败: {e}")
        sys.exit(1)

def run_build_commands():
    """执行 uv sync 和 pyinstaller 命令"""
    
    print("\n[4/8] 安装所需依赖...")
    try:
        subprocess.run(['uv', 'sync', '--group', 'build'], check=True)
        print("    -> uv sync 完成。")
    except subprocess.CalledProcessError:
        print("[错误] 'uv sync' 失败。请检查 'pyproject.toml' 和网络连接。")
        sys.exit(1)
    if platform.system() != "Windows":
        print("\n[5/8] 授予执行权限...")
        try:
            # 使用 glob 递归查找 .venv 下的 .so* 文件，并为每个文件添加可执行权限
            so_files = glob.glob('.venv/**/*.so*', recursive=True)
            if not so_files:
                print("    -> 未发现 .so* 文件，跳过授予执行权限。")
            else:
                for f in so_files:
                    try:
                        st = os.stat(f).st_mode
                        os.chmod(f, st | 0o111)
                    except Exception as e:
                        print(f"    -> 无法修改权限 {f}: {e}")
                print("    -> 执行权限授予完成。")
        except Exception:
            print("[错误] 执行权限授予失败。")
            sys.exit(1)
    else:
        print("\n[5/8] Windows无需授予执行权限，已跳过...")
        print("\n[5/8] Windows无需授予执行权限，已跳过...")

    print("\n[6/8] 运行构建命令")
    try:
        # pyinstaller 命令
        subprocess.run(['uv', 'run', 'pyinstaller', 'main.spec', '--clean', '--noconfirm'], check=True)
        print("    -> PyInstaller 构建完成。")
    except subprocess.CalledProcessError:
        print("[错误] 'pyinstaller' 构建失败。请检查 PyInstaller 配置。")
        sys.exit(1)

def create_instructions_and_venv_placeholder():
    """创建说明文件和 .venv 占位符"""
    
    # 路径定义
    dist_main_dir = os.path.join('dist', 'main')
    instructions_path = os.path.join(dist_main_dir, '使用说明.txt')
    venv_path = os.path.join(dist_main_dir, '.venv')
    placeholder_path = os.path.join(venv_path, '说明.txt')

    # 使用说明内容
    instructions_content = """\
config.json（配置文件）位置：_internal/config.json，也可以使用GUI进行配置填写
错误请群里反应或前往https://github.com/69gg/NagaAgent/issues，不要前往官方仓库
双击运行可执行文件即可启动程序
"""
    # .venv/说明.txt 内容
    placeholder_content = "占位"

    print(f"\n[7/8] 创建 {instructions_path} 和 {venv_path} 占位文件...")
    
    # 确保目标目录存在
    os.makedirs(dist_main_dir, exist_ok=True)
    os.makedirs(venv_path, exist_ok=True)

    # 写入使用说明
    try:
        with open(instructions_path, 'w', encoding='utf-8') as f:
            f.write(instructions_content)
        print(f"    -> {os.path.basename(instructions_path)} 写入完成。")
    except Exception as e:
        print(f"[警告] 写入使用说明失败: {e}")

    # 写入 .venv 占位文件
    try:
        with open(placeholder_path, 'w', encoding='utf-8') as f:
            f.write(placeholder_content)
        print("    -> .venv/说明.txt 写入完成。")
    except Exception as e:
        print(f"[警告] 写入 .venv 占位文件失败: {e}")

def rename_and_zip_output():
    """重命名 dist/main 目录并压缩"""
    
    # 确定系统名称
    sys_map = {
        'Windows': 'Windows',
        'Linux': 'Linux',
        'Darwin': 'Darwin'
    }
    current_system = sys_map.get(platform.system(), 'Unknown')
    
    source_dir = os.path.join('dist', 'main')
    target_base_name = f'NagaAgent_{current_system}'
    target_dir_path = os.path.join('dist', target_base_name)
    
    if not os.path.isdir(source_dir):
        print(f"\n[错误] 找不到构建目录 {source_dir}。请检查 PyInstaller 是否成功运行。")
        sys.exit(1)

    print(f"\n[8/8] 打包为压缩包...")
    try:
        # 如果目标目录已存在，先删除，确保重命名成功
        if os.path.exists(target_dir_path):
            shutil.rmtree(target_dir_path)
            print(f"    -> 已删除旧目录 {target_dir_path}。")
        
        print(f"\n重命名 {source_dir} 为 {target_dir_path}...")
        os.rename(source_dir, target_dir_path)
        print("    -> 重命名完成。")
    except Exception as e:
        print(f"[错误] 重命名失败: {e}")
        sys.exit(1)

    print(f"\n    -> 压缩 {target_dir_path} 为 {target_base_name}.zip...")
    try:
        # 使用 shutil.make_archive 进行压缩
        # base_name: 压缩文件的目标路径和名称（不含扩展名）
        # format: 压缩格式 ('zip')
        # root_dir: 开始归档的根目录（这里是 'dist'）
        # base_dir: 实际要归档的目录（在 root_dir 之下）
        output_filename = shutil.make_archive(
            base_name=target_dir_path,
            format='zip',
            root_dir='dist',
            base_dir=target_base_name
        )
        print(f"    -> 压缩完成。文件位置: {output_filename}")
    except Exception as e:
        print(f"[错误] 压缩失败: {e}")
        sys.exit(1)

def main():
    user_confirmation()
    check_uv()
    manage_config_files()
    run_build_commands()
    create_instructions_and_venv_placeholder()
    rename_and_zip_output()
    
    print("\n=========================================")
    print("      构建和打包流程已全部完成！")
    print("=========================================")

if __name__ == "__main__":
    main()
