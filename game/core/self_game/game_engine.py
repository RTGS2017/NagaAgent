"""
GameEngine - 自博弈引擎

整合Actor-Criticizer-Checker三组件,实现"生成-批判-评估"的完整闭环优化机制.
负责协调各组件间的交互,控制迭代流程,并基于评分决策是否进入下一轮优化.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..models.data_models import Agent, Task, GameResult
from ..models.config import GameConfig
from .actor import GameActor, ActorOutput
from .criticizer import GameCriticizer, CriticOutput
from .checker.philoss_checker import PhilossChecker, PhilossOutput

logger = logging.getLogger(__name__)


PHASE_INIT = "初始化"
PHASE_GENERATION = "生成阶段"
PHASE_CRITIQUE = "批判阶段"
PHASE_EVALUATION = "评估阶段"
PHASE_DECISION = "决策阶段"
PHASE_COMPLETED = "完成"
PHASE_FAILED = "失败"


@dataclass
class GameRound:
    """单轮博弈结果"""
    round_number: int
    actor_outputs: List[ActorOutput]
    critic_outputs: List[CriticOutput]
    philoss_outputs: List[PhilossOutput]
    phase: str
    round_time: float
    decision: str  # 继续/完成/失败
    metadata: Dict[str, Any]


@dataclass
class GameSession:
    """完整博弈会话"""
    session_id: str
    task: Task
    agents: List[Agent]
    rounds: List[GameRound]
    final_result: Optional[GameResult]
    total_time: float
    status: str
    metadata: Dict[str, Any]


class GameEngine:
    """自博弈引擎 - 协调Actor/Criticizer/Checker三组件"""
    
    def __init__(self, config: GameConfig, naga_conversation=None):
        """
        初始化GameEngine
        
        Args:
            config: 游戏配置
            naga_conversation: NagaAgent的会话实例
        """
        self.config = config
        self.actor = GameActor(config, naga_conversation)
        self.criticizer = GameCriticizer(config, naga_conversation)
        self.philoss_checker = PhilossChecker(config)
        
        self.sessions: List[GameSession] = []
        self.current_session: Optional[GameSession] = None
    
    async def start_game_session(self, 
                                task: Task, 
                                agents: List[Agent],
                                context: Optional[str] = None) -> GameSession:
        """
        启动完整的自博弈会话
        
        Args:
            task: 任务描述
            agents: 参与博弈的智能体列表
            context: 额外上下文信息
            
        Returns:
            完整的博弈会话结果
        """
        start_time = time.time()
        session_id = f"session_{int(time.time() * 1000)}"
        
        logger.info(f"启动自博弈会话:{session_id},智能体数量:{len(agents)}")
        
        # 创建会话对象
        session = GameSession(
            session_id=session_id,
            task=task,
            agents=agents,
            rounds=[],
            final_result=None,
            total_time=0,
            status=PHASE_INIT,
            metadata={
                'context_provided': context is not None,
                'max_iterations': self.config.self_game.max_iterations,
                'convergence_threshold': self.config.self_game.convergence_threshold,
                'quality_threshold': self.config.self_game.quality_threshold
            }
        )
        
        self.current_session = session
        
        try:
            # 执行多轮博弈
            for round_number in range(1, self.config.self_game.max_iterations + 1):
                logger.info(f"开始第{round_number}轮博弈")
                
                # 执行单轮博弈
                game_round = await self._execute_game_round(
                    round_number, agents, task, context, session.rounds
                )
                
                session.rounds.append(game_round)
                session.status = game_round.phase
                
                # 检查是否应该结束博弈
                should_continue, decision_reason = self._should_continue_game(
                    game_round, session.rounds, task
                )
                
                game_round.decision = decision_reason
                
                if not should_continue:
                    logger.info(f"博弈在第{round_number}轮结束:{decision_reason}")
                    break
                
                # 为下一轮准备上下文
                context = self._prepare_next_round_context(session.rounds)
            
            # 生成最终结果
            session.final_result = await self._generate_final_result(session)
            session.status = PHASE_COMPLETED
            session.total_time = time.time() - start_time
            
            # 记录会话
            self.sessions.append(session)
            
            logger.info(f"自博弈会话完成:{session_id},总轮数:{len(session.rounds)}")
            return session
            
        except Exception as e:
            logger.error(f"自博弈会话失败:{e}")
            session.status = PHASE_FAILED
            session.total_time = time.time() - start_time
            session.metadata['error'] = str(e)
            
            self.sessions.append(session)
            return session
    
    async def _execute_game_round(self, 
                                 round_number: int,
                                 agents: List[Agent],
                                 task: Task,
                                 context: Optional[str],
                                 previous_rounds: List[GameRound]) -> GameRound:
        """执行单轮博弈"""
        round_start_time = time.time()
        
        try:
            # 阶段1:生成阶段 (Actor)
            logger.debug(f"第{round_number}轮 - 生成阶段")
            actor_outputs = await self._generation_phase(agents, task, context, previous_rounds)
            
            # 阶段2:批判阶段 (Criticizer)
            logger.debug(f"第{round_number}轮 - 批判阶段")
            critic_outputs = await self._critique_phase(actor_outputs, agents, task, previous_rounds)
            
            # 阶段3:评估阶段 (PhilossChecker)
            logger.debug(f"第{round_number}轮 - 评估阶段")
            philoss_outputs = await self._evaluation_phase(actor_outputs, previous_rounds)
            
            # 严格校验：任一阶段无有效结果则本轮失败
            if not actor_outputs:
                raise RuntimeError("生成阶段无有效输出")
            if not critic_outputs:
                raise RuntimeError("批判阶段无有效输出")
            if not philoss_outputs:
                raise RuntimeError("评估阶段无有效输出")

            # 创建轮次结果
            game_round = GameRound(
                round_number=round_number,
                actor_outputs=actor_outputs,
                critic_outputs=critic_outputs,
                philoss_outputs=philoss_outputs,
                phase=PHASE_DECISION,
                round_time=time.time() - round_start_time,
                decision="待决策",
                metadata={
                    'generation_count': len(actor_outputs),
                    'critique_count': len(critic_outputs),
                    'evaluation_count': len(philoss_outputs),
                    'average_critical_score': self._calculate_average_critical_score(critic_outputs),
                    'average_novelty_score': self._calculate_average_novelty_score(philoss_outputs),
                    'average_satisfaction_score': (sum(c.satisfaction_score for c in critic_outputs)/len(critic_outputs)) if critic_outputs else 0.0,
                    'context_length': len(context) if context else 0
                }
            )
            
            return game_round
            
        except Exception as e:
            logger.error(f"第{round_number}轮博弈执行失败:{e}")
            # 返回错误轮次
            return GameRound(
                round_number=round_number,
                actor_outputs=[],
                critic_outputs=[],
                philoss_outputs=[],
                phase=PHASE_FAILED,
                round_time=time.time() - round_start_time,
                decision=f"执行失败:{str(e)}",
                metadata={'error': True, 'error_message': str(e)}
            )
    
    async def _generation_phase(self, 
                                agents: List[Agent],
                                task: Task,
                                context: Optional[str],
                                previous_rounds: List[GameRound]) -> List[ActorOutput]:
        """生成阶段 - Actor组件执行"""
        try:
            # 准备历史Actor输出摘要，供后续批判器使用
            previous_outputs: List[ActorOutput] = []
            if previous_rounds:
                previous_outputs = previous_rounds[-1].actor_outputs
 
            # 筛选出非需求方的智能体进行内容生成
            execution_agents = [a for a in agents if not a.is_requester]
            
            # 并发生成所有执行智能体的内容（每个角色并行多个分支）
            generation_tasks = []
            branches = max(1, int(self.config.self_game.branches_per_agent))
            for agent in execution_agents:
                # 单节点自指轮次控制: 超过最大自指迭代轮次则不再继续该agent生成
                if getattr(agent, "current_iteration", 0) >= self.config.self_game.max_self_route_iterations:
                    logger.info(f"智能体{agent.name}已达自指最大迭代轮次，停止其本轮生成并回传上游")
                    continue
                for branch_id in range(1, branches + 1):
                    task_coroutine = self.actor.generate_content(
                        agent, task, context, previous_outputs, branch_id=branch_id
                    )
                    generation_tasks.append(task_coroutine)
            
            # 分批执行以限制并发，降低API超时概率
            actor_outputs: List[Any] = []
            if generation_tasks:
                batch_size = max(1, int(getattr(self.config.system, 'max_concurrent_tasks', 5)))
                for i in range(0, len(generation_tasks), batch_size):
                    batch = generation_tasks[i:i+batch_size]
                    batch_results = await asyncio.gather(*batch, return_exceptions=True)
                    actor_outputs.extend(batch_results)
            
            # 处理结果
            valid_outputs = []
            # 拼接上一轮Actor摘要，存入metadata.previous_context
            prev_context_text = ""
            if previous_outputs:
                parts = []
                for prev in previous_outputs[-3:]:
                    parts.append(f"- {prev.metadata.get('agent_name','未知')} 第{prev.iteration}轮: {prev.content[:200]}...")
                prev_context_text = "\n".join(parts)
 
            for i, output in enumerate(actor_outputs):
                if isinstance(output, Exception):
                    logger.error(f"智能体生成失败:{output}")
                    continue
                try:
                    output.metadata["previous_context"] = prev_context_text
                except Exception:
                    pass
                valid_outputs.append(output)
             
            logger.debug(f"生成阶段完成:{len(valid_outputs)} 个执行输出(含分支)")
            return valid_outputs
            
        except Exception as e:
            logger.error(f"生成阶段失败:{e}")
            return []
    
    async def _critique_phase(self, 
                             actor_outputs: List[ActorOutput],
                             agents: List[Agent],
                             task: Task,
                             previous_rounds: List[GameRound]) -> List[CriticOutput]:
        """批判阶段 - Criticizer组件执行"""
        try:
            if not actor_outputs:
                logger.warning("没有Actor输出可供批判")
                return []
            
            # 准备历史批判作为参考
            previous_critiques = []
            if previous_rounds:
                for round_data in previous_rounds[-1:]:  # 最近1轮
                    previous_critiques.extend(round_data.critic_outputs)
            
            # 为每个Actor输出分配批判者（避免同一agent自评）
            critique_tasks = []
            for actor_output in actor_outputs:
                for critic_agent in agents:
                    if actor_output.agent_id != critic_agent.agent_id:
                        task_coroutine = self.criticizer.critique_output(
                            actor_output, critic_agent, task, previous_critiques
                        )
                        critique_tasks.append(task_coroutine)
                        break  # 每个输出只分配一个批判者
            
            critic_outputs = await asyncio.gather(*critique_tasks, return_exceptions=True)
            
            # 处理结果
            valid_critiques = []
            for output in critic_outputs:
                if isinstance(output, Exception):
                    logger.error(f"批判任务失败:{output}")
                    continue
                valid_critiques.append(output)
            
            logger.debug(f"批判阶段完成:{len(valid_critiques)}个批判结果")
            return valid_critiques
            
        except Exception as e:
            logger.error(f"批判阶段失败:{e}")
            return []
    
    async def _evaluation_phase(self, 
                               actor_outputs: List[ActorOutput],
                               previous_rounds: List[GameRound]) -> List[PhilossOutput]:
        """评估阶段 - PhilossChecker组件执行"""
        try:
            if not actor_outputs:
                logger.warning("没有Actor输出可供评估")
                return []
            
            # 准备评估内容(按 target_output_id 唯一标识包含分支)
            contents = []
            for output in actor_outputs:
                contents.append((output.content, output.target_output_id))
            
            # 批量评估创新性
            philoss_outputs = await self.philoss_checker.batch_evaluate(contents)
            
            logger.debug(f"评估阶段完成:{len(philoss_outputs)}个创新性评估")
            return philoss_outputs
            
        except Exception as e:
            logger.error(f"评估阶段失败:{e}")
            return []
    
    def _should_continue_game(self, 
                             current_round: GameRound,
                             all_rounds: List[GameRound],
                             task: Task) -> Tuple[bool, str]:
        """判断是否应该继续博弈"""
        try:
            # 检查是否达到最大轮数
            if current_round.round_number >= self.config.self_game.max_iterations:
                return False, f"达到最大迭代次数({self.config.self_game.max_iterations})"
            
            # 检查是否有有效输出
            if (not current_round.actor_outputs or 
                not current_round.critic_outputs or 
                not current_round.philoss_outputs):
                return False, "当前轮次缺少有效输出"
            
            # 检查质量阈值
            avg_critical_score = current_round.metadata.get('average_critical_score', 0)
            if avg_critical_score >= self.config.self_game.quality_threshold:
                return False, f"质量达标(Critical Score: {avg_critical_score:.2f} >= {self.config.self_game.quality_threshold})"
            
            # 检查收敛性
            if len(all_rounds) >= 2:
                convergence = self._check_convergence(all_rounds[-2:])
                if convergence >= self.config.self_game.convergence_threshold:
                    return False, f"结果收敛(收敛度: {convergence:.2f} >= {self.config.self_game.convergence_threshold})"
            
            # 检查创新性阈值
            avg_novelty_score = current_round.metadata.get('average_novelty_score', 0)
            if avg_novelty_score >= self.config.philoss.novelty_threshold:
                return False, f"创新性达标(Novelty Score: {avg_novelty_score:.2f} >= {self.config.philoss.novelty_threshold})"
            
            # 继续博弈
            return True, f"继续优化(Critical: {avg_critical_score:.2f}, Novelty: {avg_novelty_score:.2f})"
            
        except Exception as e:
            logger.error(f"博弈决策判断失败:{e}")
            return False, f"决策异常:{str(e)}"
    
    def _check_convergence(self, recent_rounds: List[GameRound]) -> float:
        """检查最近轮次的收敛性"""
        try:
            if len(recent_rounds) < 2:
                return 0.0
            
            # 比较最近两轮的Critical Score
            prev_scores = [c.overall_score for c in recent_rounds[-2].critic_outputs]
            curr_scores = [c.overall_score for c in recent_rounds[-1].critic_outputs]
            
            if not prev_scores or not curr_scores:
                return 0.0
            
            prev_avg = sum(prev_scores) / len(prev_scores)
            curr_avg = sum(curr_scores) / len(curr_scores)
            
            # 计算改进程度（越小说明越收敛）
            improvement = abs(curr_avg - prev_avg)
            convergence = max(0.0, 1.0 - improvement / 10.0)  # 归一化到0-1
            
            return convergence
            
        except Exception as e:
            logger.error(f"收敛性检查失败:{e}")
            return 0.0
    
    def _calculate_average_critical_score(self, critic_outputs: List[CriticOutput]) -> float:
        """计算平均批判评分"""
        if not critic_outputs:
            return 0.0
        return sum(c.overall_score for c in critic_outputs) / len(critic_outputs)
    
    def _calculate_average_novelty_score(self, philoss_outputs: List[PhilossOutput]) -> float:
        """计算平均创新性评分"""
        if not philoss_outputs:
            return 0.0
        return sum(p.novelty_score for p in philoss_outputs) / len(philoss_outputs)
    
    def _prepare_next_round_context(self, rounds: List[GameRound]) -> str:
        """为下一轮准备上下文信息"""
        if not rounds:
            return ""
        
        last_round = rounds[-1]
        context_parts = [
            f"## 第{last_round.round_number}轮总结",
            f"- 批判平均分:{last_round.metadata.get('average_critical_score', 0):.2f}/10",
            f"- 创新性平均分:{last_round.metadata.get('average_novelty_score', 0):.2f}/10",
        ]
        
        # 添加主要改进建议
        if last_round.critic_outputs:
            suggestions = []
            for critique in last_round.critic_outputs:
                suggestions.extend(critique.improvement_suggestions[:2])  # 取前2个建议
            
            if suggestions:
                context_parts.append("- 主要改进建议:")
                for i, suggestion in enumerate(suggestions[:3], 1):  # 最多3个建议
                    context_parts.append(f"  {i}. {suggestion}")
        
        context_parts.append("\n请在上述基础上继续优化改进.")
        return "\n".join(context_parts)
    
    async def _generate_final_result(self, session: GameSession) -> GameResult:
        """生成最终博弈结果"""
        try:
            if not session.rounds:
                raise RuntimeError("没有有效轮次")
            
            # 获取最后一轮的最佳输出
            last_round = session.rounds[-1]
            final_outputs = []
            
            # 选择质量最高的Actor输出
            if last_round.actor_outputs:
                # 以三种分数的均值作为当前选择策略
                scored_outputs = []
                # 构建映射: target_output_id -> (critical_overall, satisfaction, novelty)
                score_map: Dict[str, Tuple[float,float,float]] = {}
                for co in last_round.critic_outputs:
                    score_map.setdefault(co.target_output_id, [0.0, 0.0, 0.0])
                    score_map[co.target_output_id][0] = max(score_map[co.target_output_id][0], co.overall_score)
                    score_map[co.target_output_id][1] = max(score_map[co.target_output_id][1], co.satisfaction_score)
                for po in last_round.philoss_outputs:
                    score_map.setdefault(po.target_content_id, [0.0, 0.0, 0.0])
                    score_map[po.target_content_id][2] = max(score_map[po.target_content_id][2], po.novelty_score)

                for actor_output in last_round.actor_outputs:
                    triple = score_map.get(actor_output.target_output_id, [0.0,0.0,0.0])
                    avg_score = sum(triple) / 3.0
                    scored_outputs.append((actor_output, avg_score, tuple(triple)))

                # 记录帕累托前沿：三维(critical,satisfaction,novelty)的非支配解
                pareto = []
                triples = [(ao, triple) for ao, _, triple in scored_outputs]
                for i, (ao_i, t_i) in enumerate(triples):
                    dominated = False
                    for j, (ao_j, t_j) in enumerate(triples):
                        if i == j:
                            continue
                        if (t_j[0] >= t_i[0] and t_j[1] >= t_i[1] and t_j[2] >= t_i[2]) and (t_j != t_i):
                            dominated = True
                            break
                    if not dominated:
                        pareto.append({
                            'target_output_id': ao_i.target_output_id,
                            'scores': {'critical': t_i[0], 'satisfaction': t_i[1], 'novel': t_i[2]}
                        })

                # 按平均分排序，作为当前偏好策略
                scored_outputs.sort(key=lambda x: x[1], reverse=True)
                final_outputs = [output for output, _, _ in scored_outputs]
            
            # 计算质量指标
            quality_metrics = self._calculate_quality_metrics(session.rounds)
            
            # 判断是否成功
            success = (
                quality_metrics.get('final_critical_score', 0) >= self.config.self_game.quality_threshold or
                quality_metrics.get('final_novelty_score', 0) >= self.config.philoss.novelty_threshold
            )
            
            result = GameResult(
                actor_output=final_outputs[0] if final_outputs else None,
                critic_scores={},
                novel_score=None,
                iteration_count=len(session.rounds),
                final_consensus="基于三分均值与帕累托前沿选优",
                phase=PHASE_COMPLETED,
                success=success,
                error_message="" if success else "质量或新颖性不达标",
                execution_time=session.total_time,
            )
            # 将帕累托前沿写入 metadata
            if session.rounds:
                last_round.metadata['pareto_front'] = pareto if 'pareto' in locals() else []
            return result
         
        except Exception as e:
            logger.error(f"最终结果生成失败:{e}")
            return GameResult(
                actor_output=None,
                critic_scores={},
                novel_score=None,
                iteration_count=len(session.rounds) if session.rounds else 0,
                final_consensus="异常",
                phase=PHASE_FAILED,
                success=False,
                error_message=str(e),
                execution_time=0.0,
            )
    
    def _calculate_quality_metrics(self, rounds: List[GameRound]) -> Dict[str, Any]:
        """计算质量指标"""
        if not rounds:
            return {}
        
        try:
            # 收集所有轮次的评分
            critical_scores = []
            novelty_scores = []
            satisfaction_scores = []
            
            for round_data in rounds:
                critical_scores.extend([c.overall_score for c in round_data.critic_outputs])
                novelty_scores.extend([p.novelty_score for p in round_data.philoss_outputs])
                satisfaction_scores.extend([c.satisfaction_score for c in round_data.critic_outputs])
            
            metrics = {
                'total_rounds': len(rounds),
                'final_critical_score': critical_scores[-1] if critical_scores else 0,
                'final_novelty_score': novelty_scores[-1] if novelty_scores else 0,
                'average_critical_score': sum(critical_scores) / len(critical_scores) if critical_scores else 0,
                'average_novelty_score': sum(novelty_scores) / len(novelty_scores) if novelty_scores else 0,
                'average_satisfaction_score': sum(satisfaction_scores) / len(satisfaction_scores) if satisfaction_scores else 0,
                'max_critical_score': max(critical_scores) if critical_scores else 0,
                'max_novelty_score': max(novelty_scores) if novelty_scores else 0,
                'score_improvement': 0,
                'convergence_achieved': False
            }
            
            # 计算改进程度
            if len(critical_scores) >= 2:
                initial_score = critical_scores[0]
                final_score = critical_scores[-1]
                metrics['score_improvement'] = final_score - initial_score
            
            # 检查收敛
            if len(rounds) >= 2:
                convergence = self._check_convergence(rounds[-2:])
                metrics['convergence_achieved'] = convergence >= self.config.self_game.convergence_threshold
            
            return metrics
            
        except Exception as e:
            logger.error(f"质量指标计算失败:{e}")
            return {'error': str(e)}
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """获取会话统计信息"""
        if not self.sessions:
            return {
                'total_sessions': 0,
                'successful_sessions': 0,
                'average_rounds': 0,
                'average_session_time': 0
            }
        
        successful_sessions = [s for s in self.sessions if s.final_result and s.final_result.success]
        total_rounds = sum(len(s.rounds) for s in self.sessions)
        total_time = sum(s.total_time for s in self.sessions)
        
        return {
            'total_sessions': len(self.sessions),
            'successful_sessions': len(successful_sessions),
            'failed_sessions': len(self.sessions) - len(successful_sessions),
            'success_rate': len(successful_sessions) / len(self.sessions) * 100,
            'average_rounds': total_rounds / len(self.sessions),
            'average_session_time': total_time / len(self.sessions),
            'total_game_time': total_time,
            'philoss_model_ready': self.philoss_checker.is_model_ready()
        }
    
    def get_latest_session(self) -> Optional[GameSession]:
        """获取最新的博弈会话"""
        return self.sessions[-1] if self.sessions else None
    
    def clear_history(self):
        """清空所有历史数据"""
        self.sessions.clear()
        self.current_session = None
        self.actor.clear_history()
        self.criticizer.clear_history()
        self.philoss_checker.clear_history()
        logger.info("GameEngine历史数据已清空") 
 