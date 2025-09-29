#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多智能体系统演示 - 展示新的多智能体架构的使用方法
"""

import asyncio
import logging
from typing import Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MultiAgentDemo")

async def demo_basic_usage():
    """演示基本使用方法"""
    print("=== 多智能体系统基本使用演示 ===")
    
    try:
        # 导入新的模块
        from .agent_manager import process_intelligent_task, get_task_status, get_task_list
        from .multi_agent_coordinator import coordinate_task, get_registered_agents
        
        # 1. 智能任务处理
        print("\n1. 智能任务处理演示:")
        query = "帮我分析一下今天的天气情况，并制定一个出行计划"
        result = await process_intelligent_task(query)
        print(f"查询: {query}")
        print(f"结果: {result}")
        
        # 2. 多智能体协调
        print("\n2. 多智能体协调演示:")
        coordination_result = await coordinate_task(
            query="请帮我写一份项目报告，包括技术分析和实施计划",
            strategy="hierarchical"
        )
        print(f"协调结果: {coordination_result}")
        
        # 3. 获取任务状态
        print("\n3. 任务状态查询:")
        if result.get("task_id"):
            task_status = await get_task_status(result["task_id"])
            print(f"任务状态: {task_status}")
        
        # 4. 获取任务列表
        print("\n4. 任务列表:")
        task_list = await get_task_list()
        print(f"当前任务数量: {len(task_list)}")
        for task in task_list[:3]:  # 显示前3个任务
            print(f"  - {task['title']} ({task['status']})")
        
        # 5. 获取已注册的智能体
        print("\n5. 已注册的智能体:")
        agents = get_registered_agents()
        print(f"智能体数量: {len(agents)}")
        for agent in agents:
            print(f"  - {agent['name']}: {agent['description']}")
        
    except Exception as e:
        logger.error(f"演示过程中出现错误: {e}")
        print(f"错误: {e}")

async def demo_coordination_strategies():
    """演示不同的协调策略"""
    print("\n=== 协调策略演示 ===")
    
    try:
        from .multi_agent_coordinator import coordinate_task
        
        query = "分析用户需求并制定解决方案"
        
        strategies = ["sequential", "parallel", "hierarchical", "consensus"]
        
        for strategy in strategies:
            print(f"\n{strategy.upper()} 策略:")
            result = await coordinate_task(query, strategy=strategy)
            print(f"  结果: {result.get('success', False)}")
            print(f"  参与者: {result.get('participants', [])}")
            
    except Exception as e:
        logger.error(f"协调策略演示失败: {e}")

async def demo_task_management():
    """演示任务管理功能"""
    print("\n=== 任务管理演示 ===")
    
    try:
        from .agent_manager import process_intelligent_task, get_task_list, get_execution_stats
        
        # 创建多个任务
        tasks = [
            "帮我写一份技术文档",
            "分析市场趋势",
            "制定学习计划",
            "优化代码性能"
        ]
        
        task_ids = []
        for task in tasks:
            result = await process_intelligent_task(task)
            if result.get("task_id"):
                task_ids.append(result["task_id"])
        
        print(f"创建了 {len(task_ids)} 个任务")
        
        # 获取任务列表
        task_list = await get_task_list()
        print(f"当前任务总数: {len(task_list)}")
        
        # 按状态分组
        status_groups = {}
        for task in task_list:
            status = task.get("status", "unknown")
            status_groups[status] = status_groups.get(status, 0) + 1
        
        print("任务状态分布:")
        for status, count in status_groups.items():
            print(f"  {status}: {count}")
        
        # 获取执行统计
        stats = await get_execution_stats()
        print(f"\n执行统计:")
        print(f"  总任务数: {stats.get('total_tasks', 0)}")
        print(f"  成功任务数: {stats.get('successful_tasks', 0)}")
        print(f"  失败任务数: {stats.get('failed_tasks', 0)}")
        print(f"  成功率: {stats.get('success_rate', 0):.2%}")
        print(f"  平均执行时间: {stats.get('avg_execution_time', 0):.2f}秒")
        
    except Exception as e:
        logger.error(f"任务管理演示失败: {e}")

async def demo_agent_registration():
    """演示智能体注册功能"""
    print("\n=== 智能体注册演示 ===")
    
    try:
        from .multi_agent_coordinator import get_coordinator, AgentCapability
        
        coordinator = get_coordinator()
        
        # 注册新的智能体
        new_agent = AgentCapability(
            agent_id="specialist_analyst",
            name="专业分析师",
            description="专门进行深度分析和数据挖掘",
            capabilities=["数据分析", "趋势预测", "风险评估"],
            priority=5
        )
        
        coordinator.register_agent(new_agent)
        print(f"已注册新智能体: {new_agent.name}")
        
        # 获取所有智能体
        agents = coordinator.get_registered_agents()
        print(f"\n当前注册的智能体 ({len(agents)} 个):")
        for agent in agents:
            print(f"  - {agent['name']} ({agent['agent_id']})")
            print(f"    描述: {agent['description']}")
            print(f"    能力: {', '.join(agent['capabilities'])}")
            print(f"    优先级: {agent['priority']}")
            print(f"    可用性: {agent['is_available']}")
            print()
        
    except Exception as e:
        logger.error(f"智能体注册演示失败: {e}")

async def main():
    """主演示函数"""
    print("Naga多智能体系统演示")
    print("=" * 50)
    
    try:
        # 基本使用演示
        await demo_basic_usage()
        
        # 协调策略演示
        await demo_coordination_strategies()
        
        # 任务管理演示
        await demo_task_management()
        
        # 智能体注册演示
        await demo_agent_registration()
        
        print("\n演示完成！")
        
    except Exception as e:
        logger.error(f"演示过程中出现严重错误: {e}")
        print(f"严重错误: {e}")

if __name__ == "__main__":
    asyncio.run(main())
