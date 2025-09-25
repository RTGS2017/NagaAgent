"""
GameCriticizer - 批判优化组件

负责对Actor输出的初始成果进行多维度批判,精准识别逻辑漏洞、创新性不足、
细节缺失等问题,并针对性地提出优化建议,同时为成果表现和建议满意度进行打分.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from ..models.data_models import Agent, Task
from ..models.config import GameConfig
from .actor import ActorOutput

logger = logging.getLogger(__name__)


@dataclass
class CriticOutput:
    """Criticizer组件的输出结果（简化为无维度枚举,仅保留必要字段）"""
    target_output_id: str
    critic_agent_id: str
    overall_score: float  # 批判分(0.0~1.0)
    satisfaction_score: float  # 响应分(0.0~1.0, 若无则与overall相同)
    dimension_scores: List[Dict[str, Any]]  # 兼容旧字段,但不做枚举
    summary_critique: str
    improvement_suggestions: List[str]
    critique_time: float
    iteration: int
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'target_output_id': self.target_output_id,
            'critic_agent_id': self.critic_agent_id,
            'overall_score': self.overall_score,
            'satisfaction_score': self.satisfaction_score,
            'dimension_scores': self.dimension_scores,
            'summary_critique': self.summary_critique,
            'improvement_suggestions': self.improvement_suggestions,
            'critique_time': self.critique_time,
            'iteration': self.iteration,
            'metadata': self.metadata,
        }


class GameCriticizer:
    """游戏Criticizer组件 - 批判优化器（无枚举与模拟模板）"""

    def __init__(self, config: GameConfig, naga_conversation=None):
        self.config = config
        self.naga_conversation = naga_conversation
        self.critique_history: List[CriticOutput] = []
        self.current_iteration = 0
        self._init_naga_api()

    def _init_naga_api(self):
        if self.naga_conversation is None:
            try:
                from system.conversation_core import NagaConversation
                self.naga_conversation = NagaConversation()
                logger.info("GameCriticizer成功初始化NagaAgent API连接")
            except ImportError as e:
                logger.error(f"GameCriticizer无法导入NagaAgent API: {e}")

    async def critique_output(
        self,
        actor_output: ActorOutput,
        critic_agent: Agent,
        task: Task,
        previous_critiques: Optional[List[CriticOutput]] = None,
    ) -> CriticOutput:
        start_time = time.time()
        self.current_iteration += 1

        try:
            logger.info(f"Criticizer开始批判:{critic_agent.name} 批判 {actor_output.agent_id}")

            prompt = self._build_critique_prompt(
                actor_output, critic_agent, task, previous_critiques
            )

            llm_text = await self._call_llm_for_critique(prompt)
            overall, response_score, summary, suggestions, dim_scores = self._parse_llm_json(
                llm_text, has_previous=self.current_iteration >= 2
            )

            critique = CriticOutput(
                target_output_id=actor_output.target_output_id,
                critic_agent_id=critic_agent.agent_id,
                overall_score=overall,
                satisfaction_score=response_score,
                dimension_scores=dim_scores,
                summary_critique=summary,
                improvement_suggestions=suggestions,
                critique_time=time.time() - start_time,
                iteration=self.current_iteration,
                metadata={
                    'target_agent_name': actor_output.metadata.get('agent_name', 'unknown'),
                    'critic_agent_name': critic_agent.name,
                    'task_domain': task.domain,
                    'content_length': len(actor_output.content),
                },
            )

            self.critique_history.append(critique)
            logger.info(
                f"Criticizer完成批判, 批判分{overall:.3f}, 响应分{response_score:.3f}"
            )
            return critique

        except Exception as e:
            logger.error(f"Criticizer批判失败:{e}")
            # 将错误上抛，让引擎感知失败
            raise

    def _build_critique_prompt(
        self,
        actor_output: ActorOutput,
        critic_agent: Agent,
        task: Task,
        previous_critiques: Optional[List[CriticOutput]] = None,
    ) -> str:
        prompt = (
            "你是一个批判者，负责对执行者的输出进行批判，但是若是没有大问题不强行批判。"
            "除了你以外还有若干个同类批判者，执行者会对批判者的回复都作出回应，但是你只能看见你自己的上下文。\n"
            f"以下是被你批判的模型的提示词内容: {actor_output.metadata.get('actor_system_prompt','')}\n"
            "以下是执行者除了最新输出外响应的上下文\n"
            f"{actor_output.metadata.get('previous_context','')}\n"
            "以下是你此前进行的批判\n"
        )

        if previous_critiques:
            last = previous_critiques[-1]
            prompt += f"上一轮你的批判摘要: {last.summary_critique}\n"
        else:
            prompt += "（无历史批判）\n"

        prompt += (
            "以下是执行者最新输出\n"
            f"{actor_output.content}\n"
        )

        rules = (
            "你最后的输出打分是json化的最新实现满意度得分，称为批判分，越高越好。范围从0.0到1.0。"
        )

        if self.current_iteration >= 2:
            rules += (
                " 此外，若是当前批判者是自博弈的第二或者更后面轮次，"
                "你在json中还需要输出对模型对你的批判回应的满意度，称为响应分。"
            )

        prompt += (
            "请仅输出一个严格JSON对象，不要包含任何注释或额外文字。字段包括："
            "{\"critique_score\": number, \"response_score\": number (可选), \"summary\": string, \"suggestions\": string[]}"
        )

        return prompt

    async def _call_llm_for_critique(self, prompt: str) -> str:
        if self.naga_conversation is None:
            raise RuntimeError("LLM不可用，无法执行批判")
        return await self.naga_conversation.get_response(prompt, temperature=0.4)

    def _parse_llm_json(self, text: str, has_previous: bool) -> tuple:
        import json, re
        s = text.strip()
        m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", s)
        if m:
            s = m.group(1)

        data = json.loads(s)
        critique_score = float(max(0.0, min(1.0, data.get('critique_score', 0.5))))
        response_score = float(max(0.0, min(1.0, data.get('response_score', critique_score)))) if has_previous else critique_score
        summary = str(data.get('summary', ''))
        suggestions = list(data.get('suggestions', []))

        return critique_score, response_score, summary, suggestions, []

    async def batch_critique(
        self,
        actor_outputs: List[ActorOutput],
        critic_agents: List[Agent],
        task: Task,
    ) -> List[CriticOutput]:
        logger.info(
            f"开始批量批判,输出数量:{len(actor_outputs)},批判者数量:{len(critic_agents)}"
        )
        critique_tasks = []
        for actor_output in actor_outputs:
            for critic_agent in critic_agents:
                if actor_output.agent_id != critic_agent.agent_id:
                    critique_tasks.append(
                        self.critique_output(actor_output, critic_agent, task)
                    )

        results = await asyncio.gather(*critique_tasks, return_exceptions=True)
        valid: List[CriticOutput] = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"批判任务失败:{r}")
            else:
                valid.append(r)
        logger.info(f"批量批判完成,成功:{len(valid)}/{len(critique_tasks)}")
        return valid

    def get_critique_statistics(self) -> Dict[str, Any]:
        if not self.critique_history:
            return {
                'total_critiques': 0,
                'average_overall_score': 0.0,
                'average_satisfaction_score': 0.0,
                'current_iteration': self.current_iteration,
                'api_available': self.naga_conversation is not None,
            }
        total_overall = sum(c.overall_score for c in self.critique_history)
        total_satisfaction = sum(c.satisfaction_score for c in self.critique_history)
        return {
            'total_critiques': len(self.critique_history),
            'average_overall_score': total_overall / len(self.critique_history),
            'average_satisfaction_score': total_satisfaction / len(self.critique_history),
            'current_iteration': self.current_iteration,
            'api_available': self.naga_conversation is not None,
        }

    def get_latest_critique(self) -> Optional[CriticOutput]:
        return self.critique_history[-1] if self.critique_history else None

    def clear_history(self):
        self.critique_history.clear()
        self.current_iteration = 0
        logger.info("Criticizer批判历史已清空") 
 