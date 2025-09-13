from http.client import responses

from agents import Agent

from mcpserver.system_control import termial
from mcpserver.system_control.termial import run_command
from system.config import config  # 统一变量管理 #
import asyncio
import json

try:
    import screen_brightness_control as sbc  # 屏幕亮度调节 #
except ImportError:
    sbc = None
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    import comtypes  # COM组件初始化 #
except ImportError:
    AudioUtilities = None


class SystemControlAgent(Agent):
    """系统控制Agent #"""
    name = "SystemControlAgent"  # Agent名称 #
    instructions = "系统控制：执行指令、亮度、音量调节"  # 角色描述 #

    def __init__(self):
        super().__init__(
            name=self.name,
            instructions=self.instructions,
            tools=[],
            model=config.api.model
        )
        self._shutdown_pending = False  # 关机待确认状态 #
        self._shutdown_time = 0  # 待确认的关机时间 #

        print('系统控制mcp已加载')

    async def handle_handoff(self, data: dict) -> str:
        # 使用tool_name参数，与LLM生成的工具调用格式匹配
        action = data.get("tool_name")
        if not action:
            return json.dumps({"status": "error", "message": "缺少tool_name参数", "data": {}}, ensure_ascii=False)

        if action == "command":
            cwd = data.get('cwd')
            command = data.get('command')

            if not cwd:
                return json.dumps({"status": "error", "message": "cwd参数未设置", "data": {}}, ensure_ascii=False)
            if not command:
                return json.dumps({"status": "error", "message": "command参数未设置", "data": {}}, ensure_ascii=False)

            response = termial.run_command(command, cwd)

            return json.dumps({"status": "success", "data": response}, ensure_ascii=False)

        elif action == 'read_file':
            file = data.get('file')
            lines = data.get('lines', 500)
            offset = data.get('offset', 0)
            encoding = data.get('encoding', 'UTF-8')

            try:
                if not file:
                    return json.dumps({"status": "error", "message": "file参数未设置", "data": {}}, ensure_ascii=False)

                num_lines = int(lines) if isinstance(lines, int) or (isinstance(lines, str) and lines.isdigit()) else 500
                start_offset = int(offset) if isinstance(offset, int) or (isinstance(offset, str) and str(offset).lstrip('-').isdigit()) else 0
                if start_offset < 0:
                    start_offset = 0
                if num_lines <= 0:
                    num_lines = 500

                with open(file, 'r', encoding=encoding) as f:
                    content = f.read()

                    # 分割并添加行号
                    raw = content.split('\n')
                    selected_lines = raw[start_offset:start_offset + num_lines]

                    return json.dumps({
                        "status": "success",
                        "message": f"文件读取成功: 总行数{len(raw)}",
                        "data": '\n'.join(f'{i + 1 + start_offset}>|{line}' for i, line in enumerate(selected_lines))
                    }, ensure_ascii=False)

            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "data": {}}, ensure_ascii=False)

        elif action == 'apply_diff':
            file = data.get('file')
            end = data.get('end')  # 结束行（1-based）
            start = data.get('start', 0)  # 要编辑的代码起始行（1-based）
            diff = data.get('diff')
            encoding = data.get('encoding', 'UTF-8')

            try:
                if not file:
                    return json.dumps({"status": "error", "message": "file参数未设置", "data": {}}, ensure_ascii=False)
                if diff is None:
                    return json.dumps({"status": "error", "message": "diff参数未设置", "data": {}}, ensure_ascii=False)
                if start is None or end is None:
                    return json.dumps({"status": "error", "message": "start/end参数未设置", "data": {}}, ensure_ascii=False)

                # 解析diff结构：上文5行 + DIFF-START + 替换内容 + DIFF-END + 下文5行
                before_ctx = diff.split('-----DIFF-START-----')[0].split('\n')
                middle_replacement = diff.split('-----DIFF-START-----')[1].split('-----DIFF-END-----')[0].split('\n')
                after_ctx = diff.split('-----DIFF-END-----')[1].split('\n')

                with open(file, 'r', encoding=encoding) as f:
                    content = f.read()

                raw = content.split('\n')

                # 将传入的1-based行号转换为0-based索引
                try:
                    start_idx = int(start) - 1
                    end_idx = int(end) - 1
                except Exception:
                    return json.dumps({"status": "error", "message": "start/end参数必须为整数", "data": {}}, ensure_ascii=False)

                if start_idx < 0:
                    start_idx = 0
                if end_idx < start_idx:
                    return json.dumps({"status": "error", "message": "end必须不小于start", "data": {}}, ensure_ascii=False)
                if end_idx >= len(raw):
                    end_idx = len(raw) - 1

                # 取文件上下文5行进行校验（边界不足则按实际长度比较）
                above_slice_start = max(0, start_idx - 5)
                above_slice_end = start_idx
                below_slice_start = end_idx + 1
                below_slice_end = min(len(raw), end_idx + 6)

                above_ctx = raw[above_slice_start:above_slice_end]
                below_ctx = raw[below_slice_start:below_slice_end]

                # 允许可变长度上下文匹配：上文比较尾部， 下文比较头部
                above_tail = above_ctx[-len(before_ctx):] if before_ctx else []
                below_head = below_ctx[:len(after_ctx)] if after_ctx else []

                if before_ctx == above_tail and after_ctx == below_head:
                    # 替换 [start_idx, end_idx] 区间为 middle_replacement
                    raw[start_idx:end_idx + 1] = middle_replacement

                    with open(file, 'w', encoding=encoding) as f:
                        f.write('\n'.join(raw))

                    return json.dumps({"status": "success", "message": "文件修改成功", "data": {}}, ensure_ascii=False)
                else:
                    return json.dumps({
                        "status": "error",
                        "message": "上下文不匹配，已拒绝修改（请检查start/end与diff上下文）",
                        "data": {
                            "expected_above": before_ctx,
                            "actual_above_tail": above_tail,
                            "expected_below": after_ctx,
                            "actual_below_head": below_head
                        }
                    }, ensure_ascii=False)

            except Exception as e:
                return json.dumps({"status": "error", "message": str(e), "data": {}}, ensure_ascii=False)

        elif action == "brightness":
            value = int(data.get("value", 50))
            if sbc:
                sbc.set_brightness(value)
                return json.dumps(
                    {"status": "success", "message": f"亮度已设置为{value}", "data": {"brightness": value}},
                    ensure_ascii=False)
            else:
                return json.dumps(
                    {"status": "error", "message": "未安装screen_brightness_control库，无法调节亮度", "data": {}},
                    ensure_ascii=False)

        elif action == "volume":
            value = int(data.get("value", 50))
            if AudioUtilities:
                try:
                    comtypes.CoInitialize()  # 初始化COM组件 #
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = cast(interface, POINTER(IAudioEndpointVolume))
                    volume.SetMasterVolumeLevelScalar(value / 100, None)
                    return json.dumps(
                        {"status": "success", "message": f"音量已设置为{value}", "data": {"volume": value}},
                        ensure_ascii=False)
                except Exception as e:
                    return json.dumps({"status": "error", "message": f"音量设置失败: {e}", "data": {}},
                                      ensure_ascii=False)
                finally:
                    comtypes.CoUninitialize()  # 清理COM组件 #
            else:
                return json.dumps({"status": "error", "message": "未安装pycaw库，无法调节音量", "data": {}},
                                  ensure_ascii=False)
        else:
            return json.dumps({"status": "error", "message": f"未知操作: {action}", "data": {}}, ensure_ascii=False)


# 工厂函数，用于动态注册系统创建实例
def create_system_control_agent():
    """创建SystemControlAgent实例的工厂函数"""
    return SystemControlAgent()
