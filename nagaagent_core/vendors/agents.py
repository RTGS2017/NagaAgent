"""Proxy for external 'agents' SDK with graceful fallback #"""
try:
    import agents as _agents  # 引入外部agents包 #
    from agents import *  # noqa #
    # 不再尝试导入 agents.mcp，避免在无该模块环境的多余错误 #
    __all__ = getattr(_agents, '__all__', [])  # 导出符号 #
except Exception:
    # 提供最小兼容实现，避免项目崩溃 #
    __all__ = ['Agent', 'AgentHooks', 'RunContextWrapper', 'ComputerTool']  # 兼容导出 #

    class AgentHooks:  # 空Hook类 #
        async def on_start(self, *args, **kwargs):
            return None  # 占位 #
        async def on_end(self, *args, **kwargs):
            return None  # 占位 #

    class RunContextWrapper:  # 最小上下文包装 #
        def __init__(self, **kwargs):
            self.data = kwargs  # 简单存储 #

    class ComputerTool:  # 工具包装器 #
        def __init__(self, tool):
            self.tool = tool  # 保存引用 #

    class Agent:  # 最小Agent基类 #
        name = ''  # 名称 #
        instructions = ''  # 描述 #
        def __init__(self, name: str = '', instructions: str = '', tools=None, model: str = ''):
            self.name = name  # 名称 #
            self.instructions = instructions  # 描述 #
            self.tools = tools or []  # 工具列表 #
            self.model = model  # 模型名 #
        async def handle_handoff(self, data: dict) -> str:
            raise NotImplementedError('handle_handoff 未实现')  # 必须由子类实现 #


