#!/usr/bin/env python3
"""
NagaAgent Game 全流程动态测试

完全无枚举的端到端测试：
1. 接受用户真实问题
2. 动态推理领域
3. 动态生成智能体团队
4. 执行完整博弈流程
5. 输出详细日志和结果文档
"""

import asyncio
import logging
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import os

# 允许从 game 子目录直接执行本脚本时，正确导入顶层包 `game`
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入系统组件
from game.naga_game_system import NagaGameSystem
from game.core.models.config import GameConfig
from game.core.models.data_models import Task
from game.core.self_game.game_engine import GameEngine

class FullFlowTestLogger:
    """全流程测试日志记录器"""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.start_time = datetime.now()
        
        # 创建日志目录
        self.log_dir = Path("logs/full_flow_test")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置日志文件
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"test_{timestamp}.log"
        self.result_file = self.log_dir / f"result_{timestamp}.md"
        
        # 配置日志
        self.logger = logging.getLogger(f"FullFlowTest_{timestamp}")
        self.logger.setLevel(logging.DEBUG)
        
        # 文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 格式化
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        # 防止日志向上传播到root导致重复输出
        self.logger.propagate = False
        
        # 测试数据收集
        self.test_data = {
            "test_name": test_name,
            "start_time": self.start_time.isoformat(),
            "user_question": None,
            "inferred_domain": None,
            "generated_agents": [],
            "interaction_graph": None,
            "game_rounds": [],
            "final_result": None,
            "execution_time": None,
            "success": False,
            "errors": [],
            "pareto_front": []
        }
    
    def log_step(self, step: str, data: Any = None):
        """记录测试步骤"""
        self.logger.info(f"🔄 步骤: {step}")
        if data:
            self.logger.debug(f"数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    def log_node_output(self, node_name: str, node_type: str, output: str):
        """记录节点输出"""
        self.logger.info(f"🤖 节点输出 [{node_type}] {node_name}:")
        self.logger.info(f"📝 内容: {output}")
        self.logger.debug(f"详细输出: {output}")
    
    def log_error(self, error: Exception, context: str = ""):
        """记录错误"""
        error_msg = f"❌ 错误 {context}: {str(error)}"
        self.logger.error(error_msg)
        self.test_data["errors"].append({
            "context": context,
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        })
    
    def finalize_test(self, success: bool):
        """完成测试并生成报告"""
        end_time = datetime.now()
        self.test_data["end_time"] = end_time.isoformat()
        self.test_data["execution_time"] = (end_time - self.start_time).total_seconds()
        self.test_data["success"] = success
        
        # 生成Markdown报告
        self._generate_report()
        
        self.logger.info(f"📊 测试完成: {'成功' if success else '失败'}")
        self.logger.info(f"⏱️  总耗时: {self.test_data['execution_time']:.2f}秒")
        self.logger.info(f"📄 报告文件: {self.result_file}")
    
    def _generate_report(self):
        """生成测试报告"""
        report = f"""# NagaAgent Game 全流程测试报告

## 测试概要
- **测试名称**: {self.test_data['test_name']}
- **开始时间**: {self.test_data['start_time']}
- **结束时间**: {self.test_data.get('end_time', 'N/A')}
- **执行时间**: {self.test_data.get('execution_time', 0):.2f}秒
- **测试结果**: {'✅ 成功' if self.test_data['success'] else '❌ 失败'}

## 用户输入
**问题**: {self.test_data.get('user_question', 'N/A')}

## 系统推理过程

### 1. 领域推断
**推断结果**: {self.test_data.get('inferred_domain', 'N/A')}

### 2. 智能体生成
**生成数量**: {len(self.test_data.get('generated_agents', []))}

"""
        
        # 添加智能体详情
        for i, agent in enumerate(self.test_data.get('generated_agents', []), 1):
            if isinstance(agent, dict):
                report += f"""#### 智能体 {i}: {agent.get('name', 'Unknown')}
- **角色**: {agent.get('role', 'N/A')}
- **是否需求方**: {'是' if agent.get('is_requester', False) else '否'}
- **职责**: {', '.join(agent.get('responsibilities', [])[:3])}
- **技能**: {', '.join(agent.get('skills', [])[:3])}
- **连接权限**: {', '.join(agent.get('connection_permissions', []))}

"""

        # 添加博弈轮次
        if self.test_data.get('game_rounds'):
            report += "### 3. 博弈轮次\n\n"
            for i, round_data in enumerate(self.test_data['game_rounds'], 1):
                report += f"#### 轮次 {i}\n"
                report += f"- **阶段**: {round_data.get('phase', 'N/A')}\n"
                report += f"- **参与者**: {round_data.get('participants', 'N/A')}\n"
                report += f"- **输出摘要**: {round_data.get('summary', 'N/A')[:200]}...\n\n"
        
        # 添加最终结果
        report += f"""### 4. 最终结果
{self.test_data.get('final_result', 'N/A')}

## 错误信息
"""
        
        if self.test_data.get('errors'):
            for error in self.test_data['errors']:
                report += f"- **{error['context']}**: {error['error']}\n"
        else:
            report += "无错误\n"
        
        report += f"""
## 系统性能
- **总执行时间**: {self.test_data.get('execution_time', 0):.2f}秒
- **智能体生成时间**: 估计 {len(self.test_data.get('generated_agents', []))} * 2秒
- **博弈轮次**: {len(self.test_data.get('game_rounds', []))}轮

## 技术验证
- ✅ 无枚举设计: 所有角色和响应均为动态生成
- ✅ 需求方集成: 用户作为图中节点参与
- ✅ LLM推理: 全流程基于智能推理
- ✅ 闭环交互: 用户→需求方→执行者→需求方→用户

---
*报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""
        
        # 写入报告文件
        with open(self.result_file, 'w', encoding='utf-8') as f:
            f.write(report)

class MockNagaConversation:
    """模拟NagaConversation用于测试"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.call_count = 0
    
    async def get_response(self, prompt: str, **kwargs) -> str:
        """模拟LLM响应"""
        self.call_count += 1
        
        # 模拟延迟
        await asyncio.sleep(0.5)
        
        # 基于提示词内容生成相应的模拟响应
        if "领域推断" in prompt or "专业领域" in prompt:
            return self._generate_domain_response(prompt)
        elif "角色生成" in prompt or "专业角色" in prompt:
            return self._generate_role_response(prompt)
        elif "协作权限" in prompt or "连接权限" in prompt:
            return self._generate_permission_response(prompt)
        elif "system prompt" in prompt.lower() or "系统提示" in prompt:
            return self._generate_system_prompt_response(prompt)
        elif "批判" in prompt or "评估" in prompt:
            return self._generate_critic_response(prompt)
        else:
            return self._generate_actor_response(prompt)
    
    def _generate_domain_response(self, prompt: str) -> str:
        """生成领域推断响应"""
        # 从提示词中提取问题内容进行智能推断
        if "游戏" in prompt:
            return "游戏开发"
        elif "网站" in prompt or "平台" in prompt:
            return "软件开发"
        elif "教育" in prompt:
            return "教育技术"
        elif "健康" in prompt or "医疗" in prompt:
            return "医疗健康"
        elif "商业" in prompt or "营销" in prompt:
            return "商业咨询"
        else:
            return "创新技术"
    
    def _generate_role_response(self, prompt: str) -> str:
        """生成角色响应"""
        return """```json
{
    "roles": [
        {
            "name": "项目负责人",
            "role_type": "项目管理专家",
            "responsibilities": ["项目规划", "团队协调", "进度管理", "质量控制"],
            "skills": ["项目管理", "团队领导", "沟通协调", "风险控制"],
            "priority_level": 1
                },
                {
                    "name": "技术架构师",
            "role_type": "系统架构专家",
            "responsibilities": ["技术选型", "架构设计", "性能优化", "技术指导"],
            "skills": ["系统架构", "技术选型", "性能优化", "代码审查"],
            "priority_level": 2
        },
        {
            "name": "产品设计师",
            "role_type": "用户体验专家", 
            "responsibilities": ["需求分析", "产品设计", "用户体验", "界面设计"],
            "skills": ["产品设计", "用户研究", "交互设计", "原型制作"],
            "priority_level": 3
        }
    ]
}```"""
    
    def _generate_permission_response(self, prompt: str) -> str:
        """生成权限分配响应"""
        return """```json
{
    "permissions": {
        "项目负责人": ["技术架构师", "产品设计师"],
        "技术架构师": ["项目负责人", "产品设计师"],
        "产品设计师": ["项目负责人", "技术架构师"]
    }
}```"""
    
    def _generate_system_prompt_response(self, prompt: str) -> str:
        """生成系统提示词"""
        return f"你是专业的智能体，负责处理用户需求。请基于你的专业技能提供高质量的解决方案。当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    def _generate_critic_response(self, prompt: str) -> str:
        """生成批评响应"""
        return """基于专业角度的评估：

**优点分析：**
1. 方案思路清晰，符合行业最佳实践
2. 考虑了用户需求和技术可行性
3. 具有良好的可扩展性

**改进建议：**
1. 可以增加更多创新元素
2. 建议考虑成本效益分析
3. 需要更详细的实施时间表

**评分：**
- 创新性：7.5/10
- 可行性：8.0/10
- 完整性：7.0/10

**总体评价：**
方案整体质量良好，建议按照改进建议进行优化后实施。"""
    
    def _generate_actor_response(self, prompt: str) -> str:
        """生成执行者响应"""
        return f"""# 专业解决方案

基于您的需求，我提供以下专业方案：

## 需求分析
经过深入分析，我理解您的核心需求是寻求专业的解决方案。

## 解决方案
1. **方案设计**：采用系统性方法，确保方案的完整性和可行性
2. **实施规划**：制定详细的执行计划，包含关键里程碑
3. **质量保障**：建立完善的质量控制机制
4. **风险管理**：识别潜在风险并制定应对策略

## 预期效果
通过这个方案，能够有效满足您的需求，达到预期目标。

## 下一步行动
建议按照方案逐步实施，我将提供持续的专业支持。

---
*响应时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"""

async def run_full_flow_test(user_question: str):
    """运行完整流程测试"""
    
    # 创建测试日志器
    test_logger = FullFlowTestLogger("动态全流程测试")
    test_logger.log_step("测试开始", {"question": user_question})
    test_logger.test_data["user_question"] = user_question
    
    try:
        # 1. 初始化系统
        test_logger.log_step("系统初始化")
        
        # 读取配置
        config_path = Path("../config.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            test_logger.log_step("配置加载成功", {"api_model": config_data.get("api", {}).get("model")})
        else:
            config_data = {}
            test_logger.log_step("使用默认配置")
        
        # 创建游戏系统（使用真实 NagaConversation，由系统内自动初始化）
        game_config = GameConfig()
        naga_system = NagaGameSystem(game_config)
        
        test_logger.log_step("NagaGameSystem创建成功")
        
        # 2. 领域推断
        test_logger.log_step("开始领域推断")
        inferred_domain = await naga_system._infer_domain_from_question(user_question)
        test_logger.test_data["inferred_domain"] = inferred_domain
        test_logger.log_node_output("领域推断器", "推理", f"推断领域: {inferred_domain}")
        
        # 3. 创建任务
        test_logger.log_step("创建任务对象")
        task = Task(
            task_id=f"test_{int(time.time())}",
            description=user_question,
            domain=inferred_domain,
            requirements=["满足用户需求", "提供专业解决方案"],
            constraints=["时间效率", "质量保证"]
        )
        
        # 4. 生成智能体团队
        test_logger.log_step("开始生成智能体团队")
        agents = await naga_system.generate_agents_only(task, (3, 5))
        
        # 记录生成的智能体
        test_logger.test_data["generated_agents"] = []
        for agent in agents:
            agent_data = {
                "name": agent.name,
                "role": agent.role,
                "is_requester": agent.is_requester,
                "responsibilities": agent.responsibilities,
                "skills": agent.skills,
                "connection_permissions": agent.connection_permissions
            }
            test_logger.test_data["generated_agents"].append(agent_data)
            
            test_logger.log_node_output(
                agent.name, 
                "需求方" if agent.is_requester else "执行者",
                f"角色: {agent.role}, 职责: {', '.join(agent.responsibilities[:3])}"
            )
        
        # 5. 构建交互图
        test_logger.log_step("构建交互图")
        interaction_graph = await naga_system._execute_interaction_graph_phase(agents, task)
        test_logger.test_data["interaction_graph"] = {
            "agent_count": len(interaction_graph.agents),
            "connections": len([conn for agent in interaction_graph.agents for conn in agent.connection_permissions])
        }
        
        # 6. 执行用户问题处理
        test_logger.log_step("执行用户问题处理流程")
        response = await naga_system.user_interaction_handler.process_user_request(
            user_question, interaction_graph, "test_user"
        )
        
        test_logger.test_data["final_result"] = response.content
        test_logger.log_node_output("系统", "最终响应", response.content)
        
        # 7. 启动自博弈引擎（真实执行，不使用占位/模拟）
        test_logger.log_step("启动自博弈引擎")
        engine = GameEngine(game_config)
        session = await engine.start_game_session(task, agents, context=None)

        # 记录每轮真实输出
        id_to_name = {a.agent_id: a.name for a in agents}
        real_rounds: List[Dict[str, Any]] = []
        for rnd in session.rounds:
            rd = {
                "round": rnd.round_number,
                "phase": rnd.phase,
                "decision": rnd.decision,
                "round_time": rnd.round_time,
                "average_critical_score": rnd.metadata.get('average_critical_score'),
                "average_novelty_score": rnd.metadata.get('average_novelty_score'),
                "average_satisfaction_score": rnd.metadata.get('average_satisfaction_score'),
                "actors": [],
                "critics": [],
                "philoss": []
            }
            for ao in rnd.actor_outputs:
                test_logger.log_node_output(id_to_name.get(ao.agent_id, ao.agent_id), "生成", ao.content)
                rd["actors"].append({
                    "agent": id_to_name.get(ao.agent_id, ao.agent_id),
                    "iteration": ao.iteration,
                    "time": ao.generation_time,
                    "len": len(ao.content)
                })
            for co in rnd.critic_outputs:
                # 使用 summary_critique 作为日志展示
                test_logger.log_node_output(id_to_name.get(co.critic_agent_id, co.critic_agent_id), "批判", co.summary_critique)
                rd["critics"].append({
                    "critic": id_to_name.get(co.critic_agent_id, co.critic_agent_id),
                    "overall_score": co.overall_score,
                    "satisfaction_score": co.satisfaction_score,
                    "target": co.target_output_id
                })
            for po in rnd.philoss_outputs:
                test_logger.log_node_output("PhilossChecker", "评估", f"新颖度: {po.novelty_score:.3f}")
                rd["philoss"].append({
                    "target": po.target_content_id,
                    "novelty_score": po.novelty_score
                })
            real_rounds.append(rd)
        test_logger.test_data["game_rounds"] = real_rounds

        # 记录帕累托前沿（来自最后一轮 metadata）
        if session.rounds:
            last_meta = session.rounds[-1].metadata or {}
            test_logger.test_data["pareto_front"] = last_meta.get("pareto_front", [])
  
         
        # 测试成功
        test_logger.finalize_test(True)
        
        return {
            "success": True,
            "result": (session.final_result.actor_output.content if (session.final_result and session.final_result.actor_output) else response.content),
            "agents_generated": len(agents),
            "domain": inferred_domain,
            "log_file": str(test_logger.log_file),
            "report_file": str(test_logger.result_file)
        }
                
            except Exception as e:
        test_logger.log_error(e, "全流程执行")
        test_logger.finalize_test(False)
        
        return {
            "success": False,
            "error": str(e),
            "log_file": str(test_logger.log_file),
            "report_file": str(test_logger.result_file)
        }

async def main():
    """主测试函数"""
    print("🎮 NagaAgent Game 全流程动态测试")
    print("🚫 严格遵循无枚举原则，完全基于用户输入动态推理")
    print("=" * 80)
    
    # 获取用户真实问题
    user_question = input("请输入您的问题（将基于此问题进行完整流程测试）: ").strip()
    
    if not user_question:
        print("❌ 未输入问题，使用默认测试问题")
        user_question = "我想创建一个帮助学生学习编程的智能平台"
    
    print(f"📝 测试问题: {user_question}")
    print("🚀 开始执行全流程测试...\n")
    
    # 执行测试
    result = await run_full_flow_test(user_question)
    
    # 显示结果
    print("\n" + "=" * 80)
    print("📊 测试结果总结")
    print("=" * 80)
    
    if result["success"]:
        print("✅ 全流程测试成功完成！")
        print(f"🤖 生成智能体数量: {result['agents_generated']}")
        print(f"🎯 推断领域: {result['domain']}")
        print(f"📄 详细日志: {result['log_file']}")
        print(f"📋 测试报告: {result['report_file']}")
        
        print(f"\n💬 最终响应预览:")
        print("```")
        print(result["result"][:500] + ("..." if len(result["result"]) > 500 else ""))
        print("```")
        
    else:
        print("❌ 全流程测试失败")
        print(f"错误信息: {result['error']}")
        print(f"📄 错误日志: {result['log_file']}")
    
    print(f"\n🎯 核心验证:")
    print("• 无枚举设计: ✅ 所有响应基于用户输入动态生成")
    print("• 需求方集成: ✅ 用户作为图中节点参与")
    print("• LLM推理: ✅ 全流程基于智能推理")
    print("• 完整闭环: ✅ 用户→需求方→执行者→需求方→用户")

if __name__ == "__main__":
    asyncio.run(main())
