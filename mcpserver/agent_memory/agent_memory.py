import json
from nagaagent_core.vendors.agents import Agent  # 统一代理 #

# 直接导入summer_memory的memory_manager
try:
    from summer_memory.memory_manager import memory_manager
except Exception:
    memory_manager = None

class MemoryAgent(Agent):
    name = "MemoryAgent"
    instructions = "知识图谱记忆MCP Agent，支持五元组回忆与查询"
    def __init__(self):
        super().__init__(
            name=self.name,
            instructions=self.instructions,
            tools=[],
            model="memory-mcp"
        )

    async def handle_handoff(self, data: dict) -> str:
        tool_name = data.get("tool_name")
        if tool_name != "回忆":
            return json.dumps({
                "status": "error",
                "message": f"未知操作: {tool_name}",
                "data": ""
            }, ensure_ascii=False)
        # 支持 query 和 param_name 两种参数名，保持向后兼容
        query = data.get("query", "").strip() or data.get("param_name", "").strip()
        if not query:
            return json.dumps({
                "status": "error",
                "message": "缺少query或param_name参数",
                "data": ""
            }, ensure_ascii=False)
        if not memory_manager or not getattr(memory_manager, "enabled", False):
            return json.dumps({
                "status": "error",
                "message": "用户未启动五元组知识图谱，无法查询相关记忆",
                "data": ""
            }, ensure_ascii=False)
        try:
            # 调用memory_manager的query_memory
            result = await memory_manager.query_memory(query)
            if result:
                return json.dumps({
                    "status": "ok",
                    "message": "查询成功",
                    "data": result
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "status": "ok",
                    "message": "未找到相关记忆",
                    "data": ""
                }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "status": "error",
                "message": f"查询失败: {str(e)}",
                "data": ""
            }, ensure_ascii=False)

def create_memory_agent():
    return MemoryAgent() 