# Naga多智能体系统升级方案

基于博弈论项目的优秀设计，为Naga项目实现了智能的多智能体协作系统。

## 架构设计

### 核心组件

1. **任务规划器 (TaskPlanner)**
   - 智能分析任务类型
   - 制定执行计划
   - 任务优先级管理

2. **任务执行器 (TaskExecutor)**
   - 统一的任务执行调度
   - 多进程并行处理
   - 执行状态跟踪

3. **多智能体协调器 (MultiAgentCoordinator)**
   - 智能体注册管理
   - 多种协调策略
   - 协作任务管理

4. **增强的AgentManager**
   - 集成任务规划能力
   - 智能任务路由
   - 状态管理

## 主要特性

### 1. 智能任务分析
- 自动识别任务类型（Agent对话、MCP工具、电脑控制）
- 智能选择最佳执行方式
- 任务分解和步骤规划

### 2. 多智能体协作
- **顺序协调**: 智能体依次执行
- **并行协调**: 智能体同时执行
- **层次协调**: 主智能体协调其他智能体
- **共识协调**: 多智能体达成共识

### 3. 任务管理
- 完整的任务生命周期管理
- 任务状态跟踪
- 执行统计和性能监控
- 任务取消和清理

### 4. 智能体注册
- 动态智能体注册
- 能力描述和优先级
- 可用性管理

## 使用方法

### 基本使用

```python
from agentserver.core.agent_manager import process_intelligent_task

# 智能任务处理
result = await process_intelligent_task("帮我分析一下市场趋势")
print(result)
```

### 多智能体协调

```python
from agentserver.core.multi_agent_coordinator import coordinate_task

# 使用不同协调策略
result = await coordinate_task(
    query="请帮我写一份技术报告",
    strategy="hierarchical"  # sequential, parallel, hierarchical, consensus
)
```

### 任务管理

```python
from agentserver.core.agent_manager import get_task_list, get_task_status

# 获取任务列表
tasks = await get_task_list(status_filter="running")

# 获取任务状态
status = await get_task_status(task_id)
```

### 智能体注册

```python
from mcpserver.multi_agent_coordinator import register_agent, AgentCapability

# 注册新智能体
new_agent = AgentCapability(
    agent_id="data_analyst",
    name="数据分析师",
    description="专门进行数据分析",
    capabilities=["数据分析", "可视化", "报告生成"],
    priority=4
)
register_agent(new_agent)
```

## 协调策略详解

### 1. Sequential (顺序协调)
- 智能体按顺序依次执行
- 适合需要前一步结果的场景
- 执行时间较长但结果更准确

### 2. Parallel (并行协调)
- 所有智能体同时执行
- 适合独立任务
- 执行时间短但可能产生冲突

### 3. Hierarchical (层次协调)
- 主智能体协调其他智能体
- 适合复杂任务分解
- 平衡了效率和准确性

### 4. Consensus (共识协调)
- 多个智能体达成共识
- 适合需要多方验证的场景
- 结果最可靠但执行时间最长

## 配置说明

### 任务规划器配置
```python
# 在task_planner.py中配置
MAX_CONCURRENT_TASKS = 5  # 最大并发任务数
TASK_TIMEOUT = 300  # 任务超时时间（秒）
PRIORITY_LEVELS = 5  # 优先级级别数
```

### 执行器配置
```python
# 在task_executor.py中配置
MAX_WORKERS = 3  # 最大工作进程数
RESULT_QUEUE_SIZE = 100  # 结果队列大小
CLEANUP_INTERVAL = 3600  # 清理间隔（秒）
```

## 性能优化

### 1. 任务调度优化
- 基于优先级的任务调度
- 智能负载均衡
- 资源使用监控

### 2. 内存管理
- 定期清理已完成任务
- 智能体会话管理
- 结果缓存机制

### 3. 并发控制
- 最大并发任务限制
- 智能体可用性检查
- 任务超时处理

## 扩展开发

### 添加新的协调策略
```python
async def custom_coordination(self, task, agents, query, context):
    # 实现自定义协调逻辑
    pass

# 注册新策略
coordinator.coordination_strategies["custom"] = custom_coordination
```

### 添加新的智能体类型
```python
class CustomAgent:
    async def process(self, query, context):
        # 实现自定义智能体逻辑
        pass

# 注册到协调器
coordinator.register_agent(CustomAgent())
```

## 监控和调试

### 执行统计
```python
from agentserver.core.agent_manager import get_execution_stats

stats = await get_execution_stats()
print(f"成功率: {stats['success_rate']:.2%}")
print(f"平均执行时间: {stats['avg_execution_time']:.2f}秒")
```

### 任务状态监控
```python
# 获取运行中的任务
running_tasks = coordinator.task_executor.get_running_tasks()
for task in running_tasks:
    print(f"任务 {task['task_id']} 正在运行")
```

## 故障排除

### 常见问题

1. **任务执行失败**
   - 检查智能体可用性
   - 查看错误日志
   - 验证任务参数

2. **内存使用过高**
   - 启用定期清理
   - 调整任务队列大小
   - 监控智能体会话

3. **协调策略不生效**
   - 检查智能体注册
   - 验证策略实现
   - 查看协调日志

## 升级说明

### 从旧版本升级
1. 备份现有配置
2. 安装新依赖
3. 运行迁移脚本
4. 测试新功能

### 兼容性
- 完全向后兼容
- 渐进式升级
- 降级支持

## 贡献指南

### 开发环境设置
```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试
python -m pytest tests/

# 运行演示
python mcpserver/multi_agent_demo.py
```

### 代码规范
- 遵循PEP 8
- 添加类型注解
- 编写文档字符串
- 单元测试覆盖

## 许可证

本项目采用MIT许可证，详见LICENSE文件。
