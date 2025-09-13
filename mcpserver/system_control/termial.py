import subprocess


def run_command(command: str, cwd: str):
    """执行系统命令并返回输出和状态码"""
    try:
        # 执行命令
        result = subprocess.run(
            command,
            shell=True,  # 如果使用字符串命令而不是列表，需要shell=True
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30  # 设置超时时间
        )

        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'stdout': '',
            'stderr': '命令执行超时',
            'returncode': -1
        }
    except Exception as e:
        return {
            'success': False,
            'stdout': '',
            'stderr': str(e),
            'returncode': -1
        }
