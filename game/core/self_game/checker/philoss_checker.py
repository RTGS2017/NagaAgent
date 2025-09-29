"""
PhilossChecker - 创新性评估组件

基于Qwen2.5-VL 7B模型实现的创新性评估器,通过植入MLP层预测模型隐藏状态,
根据预测误差大小判断文本的创新性和新颖度.

核心原理:
1. 冻结Qwen2.5-VL其他参数,植入MLP层
2. 将大模型输出按100token切分为文本块
3. 基于State x预测State x+1的隐藏层状态
4. 计算预测误差,误差大=创新度高,误差小=内容常规
"""

import asyncio
import logging
import time
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from ...models.data_models import HiddenState, TextBlock, NoveltyScore
from ...models.config import GameConfig
from ..actor import ActorOutput
from ..criticizer import CriticOutput

logger = logging.getLogger(__name__)


@dataclass
class PhilossOutput:
    """Philoss评估输出结果"""
    target_content_id: str  # 目标内容ID
    novelty_score: float  # 创新性评分 (Novel score)
    text_blocks: List[TextBlock]  # 文本块列表
    hidden_states: List[HiddenState]  # 隐藏状态序列
    prediction_errors: List[float]  # 预测误差列表
    analysis_time: float  # 分析耗时
    metadata: Dict[str, Any]  # 额外元数据
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'target_content_id': self.target_content_id,
            'novelty_score': self.novelty_score,
            'text_blocks': [block.to_dict() for block in self.text_blocks],
            'hidden_states': [state.to_dict() for state in self.hidden_states],
            'prediction_errors': self.prediction_errors,
            'analysis_time': self.analysis_time,
            'metadata': self.metadata
        }


class PhilossChecker:
    """Philoss创新性评估器 - 基于Qwen2.5-VL的创新度检测"""
    
    def __init__(self, config: GameConfig):
        """
        初始化PhilossChecker
        
        Args:
            config: 游戏配置,包含Philoss模块配置
        """
        self.config = config
        self.model = None
        self.tokenizer = None
        self.mlp_layer = None
        self.device = config.philoss.device
        self.token_block_size = config.philoss.token_block_size
        self.prediction_threshold = config.philoss.prediction_threshold
        self.novelty_threshold = config.philoss.novelty_threshold
        self.evaluation_history: List[PhilossOutput] = []
        
        # 初始化模型
        self._initialize_model()
    
    def _initialize_model(self):
        """初始化Qwen2.5-VL模型和MLP层"""
        try:
            logger.info("开始初始化Qwen2.5-VL模型...")
            
            # 检查是否有可用的模型环境
            try:
                import torch
                import transformers
                from transformers import AutoTokenizer, AutoModel
                
                # 自动设备检测：CUDA不可用则使用CPU
                if not getattr(torch, 'cuda', None) or not torch.cuda.is_available():
                    self.device = 'cpu'
                dtype = torch.float16 if self.device == 'cuda' else torch.float32

                # 仅允许加载指定的 qwen2.5-vl 1B 或 7B
                requested = (self.config.philoss.model_name or "").strip()
                allowed = {
                    "Qwen/Qwen2.5-VL-1B-Instruct",
                    "Qwen/Qwen2.5-VL-7B-Instruct",
                }
                if requested and requested not in allowed:
                    logger.warning(f"指定模型 {requested} 不在允许列表，改用最近似允许项。")
                    # 简单映射：包含"1b"则用1B；否则用7B
                    requested = "Qwen/Qwen2.5-VL-1B-Instruct" if ("1b" in self.config.philoss.model_name.lower()) else "Qwen/Qwen2.5-VL-7B-Instruct"
                elif not requested:
                    requested = "Qwen/Qwen2.5-VL-1B-Instruct"

                logger.info(f"加载模型: {requested}")
                pretrained_source = self.config.philoss.model_path if self.config.philoss.model_path else requested
                auth_token = (self.config.philoss.hf_token or None)
                local_only = bool(self.config.philoss.local_files_only)

                self.tokenizer = AutoTokenizer.from_pretrained(
                    pretrained_source,
                    trust_remote_code=True,
                    cache_dir=self.config.philoss.cache_dir,
                    local_files_only=local_only,
                    use_auth_token=auth_token,
                )
                self.model = AutoModel.from_pretrained(
                    pretrained_source,
                    dtype=dtype,
                    trust_remote_code=True,
                    cache_dir=self.config.philoss.cache_dir,
                    local_files_only=local_only,
                    use_auth_token=auth_token,
                )
                # 放到目标设备并 eval()
                try:
                    self.model.to(self.device)
                except Exception as move_err:
                    logger.warning(f"模型移动到{self.device}失败，回退到CPU: {move_err}")
                    self.model.to('cpu')
                    self.device = 'cpu'
                self.model.eval()
                logger.info(f"模型加载成功: {requested}")
                 
                # 冻结主要参数
                if self.model is not None:
                    for param in self.model.parameters():
                        param.requires_grad = False
                
                # 创建MLP层用于隐藏状态预测
                self._create_mlp_layer()
                
                if self.model is not None:
                    logger.info("Philoss文本模型初始化成功")
                else:
                    logger.info("Philoss进入模拟模式")
                 
            except ImportError as e:
                logger.warning(f"深度学习库未安装,使用模拟模式:{e}")
                self.model = None
                self.tokenizer = None
            
        except Exception as e:
            logger.error(f"模型初始化失败:{e}")
            self.model = None
            self.tokenizer = None
    
    def _create_mlp_layer(self):
        """创建用于隐藏状态预测的MLP层"""
        try:
            import torch
            import torch.nn as nn
            
            hidden_size = self.config.philoss.hidden_size
            mlp_hidden_size = self.config.philoss.mlp_hidden_size
            
            # 创建简单的MLP预测器
            self.mlp_layer = nn.Sequential(
                nn.Linear(hidden_size, mlp_hidden_size),
                nn.ReLU(),
                nn.Linear(mlp_hidden_size, hidden_size),
                nn.Tanh()
            )
            try:
                self.mlp_layer.to(self.device)
            except Exception as move_err:
                logger.warning(f"MLP移动到{self.device}失败，回退到CPU: {move_err}")
                self.mlp_layer.to('cpu')
                self.device = 'cpu'
            
            # MLP层参数需要梯度更新
            for param in self.mlp_layer.parameters():
                param.requires_grad = True
            
            logger.info(f"MLP预测层创建成功:{hidden_size} -> {mlp_hidden_size} -> {hidden_size}")
            
        except Exception as e:
            logger.error(f"MLP层创建失败:{e}")
            self.mlp_layer = None
    
    async def evaluate_novelty(self, 
                               content: str, 
                               content_id: str,
                               context: Optional[str] = None) -> PhilossOutput:
        """
        评估内容的创新性
        
        Args:
            content: 待评估的文本内容
            content_id: 内容标识符
            context: 额外上下文信息
            
        Returns:
            Philoss评估结果
        """
        start_time = time.time()
        
        try:
            logger.info(f"开始Philoss创新性评估:{content_id}")
            
            # 步骤1:文本预处理和分块
            text_blocks = self._split_into_blocks(content)
            
            # 步骤2:提取隐藏状态序列
            hidden_states = await self._extract_hidden_states(text_blocks, context)
            
            # 步骤3:计算预测误差
            prediction_errors = self._calculate_prediction_errors(hidden_states)
            
            # 步骤4:计算创新性评分
            novelty_score = self._calculate_novelty_score(prediction_errors)
            
            # 创建输出结果
            philoss_output = PhilossOutput(
                target_content_id=content_id,
                novelty_score=novelty_score,
                text_blocks=text_blocks,
                hidden_states=hidden_states,
                prediction_errors=prediction_errors,
                analysis_time=time.time() - start_time,
                metadata={
                    'content_length': len(content),
                    'block_count': len(text_blocks),
                    'has_context': context is not None,
                    'model_available': self.model is not None,
                    'average_error': np.mean(prediction_errors) if prediction_errors else 0,
                    'max_error': max(prediction_errors) if prediction_errors else 0
                }
            )
            
            # 记录到历史
            self.evaluation_history.append(philoss_output)
            
            logger.info(f"Philoss评估完成,创新性评分:{novelty_score:.3f}")
            return philoss_output
            
        except Exception as e:
            logger.error(f"Philoss评估失败:{e}")
            # 返回默认评估结果
            return self._get_default_evaluation(content_id, content, start_time)
    
    def _split_into_blocks(self, content: str) -> List[TextBlock]:
        """将文本按100token切分为块"""
        try:
            if self.tokenizer is None:
                # 模拟模式:按字符数近似切分
                return self._split_by_chars(content)
            
            # 实际模式:使用tokenizer精确切分
            tokens = self.tokenizer.encode(content)
            blocks = []
            
            for i in range(0, len(tokens), self.token_block_size):
                block_tokens = tokens[i:i + self.token_block_size]
                block_text = self.tokenizer.decode(block_tokens)
                
                text_block = TextBlock(
                    block_id=f"block_{i // self.token_block_size}",
                    content=block_text,
                    token_count=len(block_tokens),
                    start_position=i,
                    end_position=min(i + self.token_block_size, len(tokens))
                )
                blocks.append(text_block)
            
            logger.debug(f"文本切分完成:{len(blocks)}个块,总token数:{len(tokens)}")
            return blocks
            
        except Exception as e:
            logger.error(f"文本切分失败:{e}")
            return self._split_by_chars(content)
    
    def _split_by_chars(self, content: str) -> List[TextBlock]:
        """按字符数模拟切分（用于无tokenizer环境）"""
        # 假设平均1个token = 4个字符（中文）,100token ≈ 400字符
        char_block_size = self.token_block_size * 4
        blocks = []
        
        for i in range(0, len(content), char_block_size):
            block_text = content[i:i + char_block_size]
            
            text_block = TextBlock(
                block_id=f"char_block_{i // char_block_size}",
                content=block_text,
                token_count=len(block_text) // 4,  # 近似token数
                start_position=i,
                end_position=min(i + char_block_size, len(content))
            )
            blocks.append(text_block)
        
        return blocks
    
    async def _extract_hidden_states(self, 
                                   text_blocks: List[TextBlock], 
                                   context: Optional[str] = None) -> List[HiddenState]:
        """提取每个文本块的隐藏状态"""
        if self.model is None:
            # 模拟模式:生成随机隐藏状态
            return self._generate_mock_hidden_states(text_blocks)
        
        try:
            import torch
            
            hidden_states = []
            
            for block in text_blocks:
                # 构建输入文本
                input_text = block.content
                if context:
                    input_text = f"{context}\n{input_text}"
                
                # 编码输入
                inputs = self.tokenizer(
                    input_text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512
                )
                # 将inputs移动到目标设备
                for k, v in inputs.items():
                    if hasattr(v, 'to'):
                        inputs[k] = v.to(self.device)
                
                # 前向传播获取隐藏状态
                with torch.no_grad():
                    try:
                        outputs = self.model(**inputs, output_hidden_states=True)
                        last_hidden = getattr(outputs, 'hidden_states', None)
                        if last_hidden is not None:
                            last_hidden_state = last_hidden[-1]
                        else:
                            # 退化到 last_hidden_state/第一输出
                            if hasattr(outputs, 'last_hidden_state'):
                                last_hidden_state = outputs.last_hidden_state
                            else:
                                # 一些自定义模型可能返回 tuple
                                last_hidden_state = outputs[0]
                    except TypeError:
                        # 不支持 output_hidden_states 参数时，退化处理
                        outputs = self.model(**inputs)
                        if hasattr(outputs, 'last_hidden_state'):
                            last_hidden_state = outputs.last_hidden_state
                        else:
                            last_hidden_state = outputs[0]
                    
                    # 获取最后一层隐藏状态的平均值
                    pooled_state = torch.mean(last_hidden_state, dim=1).squeeze()
                
                # 创建隐藏状态对象
                hidden_state = HiddenState(
                    state_id=f"state_{block.block_id}",
                    vector=pooled_state.cpu().numpy().tolist(),
                    block_id=block.block_id,
                    timestamp=time.time()
                )
                hidden_states.append(hidden_state)
            
            logger.debug(f"隐藏状态提取完成:{len(hidden_states)}个状态")
            return hidden_states
            
        except Exception as e:
            logger.error(f"隐藏状态提取失败:{e}")
            return self._generate_mock_hidden_states(text_blocks)
    
    def _generate_mock_hidden_states(self, text_blocks: List[TextBlock]) -> List[HiddenState]:
        """生成模拟隐藏状态（用于测试）"""
        hidden_states = []
        hidden_size = self.config.philoss.hidden_size
        
        for block in text_blocks:
            # 生成基于内容的伪随机向量
            np.random.seed(hash(block.content) % 2**32)
            vector = np.random.normal(0, 1, hidden_size).tolist()
            
            hidden_state = HiddenState(
                state_id=f"mock_state_{block.block_id}",
                vector=vector,
                block_id=block.block_id,
                timestamp=time.time()
            )
            hidden_states.append(hidden_state)
        
        return hidden_states
    
    def _calculate_prediction_errors(self, hidden_states: List[HiddenState]) -> List[float]:
        """计算隐藏状态预测误差"""
        if len(hidden_states) < 2:
            return [0.0]  # 至少需要两个状态才能计算预测误差
        
        try:
            if self.model is None or self.mlp_layer is None:
                # 模拟模式:基于状态向量相似度计算伪误差
                return self._calculate_mock_prediction_errors(hidden_states)
            
            import torch
            
            prediction_errors = []
            
            for i in range(len(hidden_states) - 1):
                current_state = torch.tensor(hidden_states[i].vector).to(self.device)
                next_state = torch.tensor(hidden_states[i + 1].vector).to(self.device)
                
                # 使用MLP预测下一个状态
                with torch.no_grad():
                    predicted_state = self.mlp_layer(current_state)
                
                # 计算预测误差（MSE）
                error = torch.mean((predicted_state - next_state) ** 2).item()
                prediction_errors.append(error)
            
            logger.debug(f"预测误差计算完成:{len(prediction_errors)}个误差值")
            return prediction_errors
            
        except Exception as e:
            logger.error(f"预测误差计算失败:{e}")
            return self._calculate_mock_prediction_errors(hidden_states)
    
    def _calculate_mock_prediction_errors(self, hidden_states: List[HiddenState]) -> List[float]:
        """计算模拟预测误差"""
        prediction_errors = []
        
        for i in range(len(hidden_states) - 1):
            current_vector = np.array(hidden_states[i].vector)
            next_vector = np.array(hidden_states[i + 1].vector)
            
            # 计算余弦相似度,转换为"预测误差"
            similarity = np.dot(current_vector, next_vector) / (
                np.linalg.norm(current_vector) * np.linalg.norm(next_vector)
            )
            
            # 相似度越低,"预测误差"越大
            error = 1.0 - abs(similarity)
            prediction_errors.append(error)
        
        return prediction_errors
    
    def _calculate_novelty_score(self, prediction_errors: List[float]) -> float:
        """基于预测误差计算创新性评分"""
        if not prediction_errors:
            return 5.0  # 默认中等评分
        
        try:
            # 计算误差统计量
            mean_error = np.mean(prediction_errors)
            max_error = max(prediction_errors)
            std_error = np.std(prediction_errors) if len(prediction_errors) > 1 else 0
            
            # 综合评分公式:结合平均误差、最大误差和误差方差
            # 误差越大,创新性越高
            novelty_score = (
                mean_error * 0.5 +      # 平均创新度权重50%
                max_error * 0.3 +       # 峰值创新度权重30%
                std_error * 0.2         # 创新度变化权重20%
            ) * 10  # 缩放到0-10分
            
            # 限制在合理范围内
            novelty_score = max(0.0, min(10.0, novelty_score))
            
            # 应用阈值调整
            if mean_error > self.prediction_threshold:
                novelty_score *= 1.2  # 高误差时提升评分
            else:
                novelty_score *= 0.8  # 低误差时降低评分
            
            return min(10.0, novelty_score)
            
        except Exception as e:
            logger.error(f"创新性评分计算失败:{e}")
            return 5.0
    
    def _get_default_evaluation(self, 
                                content_id: str, 
                                content: str, 
                                start_time: float) -> PhilossOutput:
        """获取默认评估结果（当评估失败时使用）"""
        # 创建基本的文本块
        text_blocks = [TextBlock(
            block_id="default_block",
            content=content[:400] + "..." if len(content) > 400 else content,
            token_count=len(content) // 4,
            start_position=0,
            end_position=len(content)
        )]
        
        # 创建默认隐藏状态
        hidden_states = [HiddenState(
            state_id="default_state",
            vector=[0.0] * self.config.philoss.hidden_size,
            block_id="default_block",
            timestamp=time.time()
        )]
        
        return PhilossOutput(
            target_content_id=content_id,
            novelty_score=5.0,  # 默认中等创新性
            text_blocks=text_blocks,
            hidden_states=hidden_states,
            prediction_errors=[0.5],  # 默认预测误差
            analysis_time=time.time() - start_time,
            metadata={
                'error': True,
                'message': '使用默认评估结果',
                'model_available': False
            }
        )
    
    async def batch_evaluate(self, 
                              contents: List[Tuple[str, str]], 
                              context: Optional[str] = None) -> List[PhilossOutput]:
        """批量评估多个内容的创新性"""
        logger.info(f"开始批量Philoss评估,内容数量:{len(contents)}")
        
        # 并发评估所有内容
        async def evaluate_single(content_data: Tuple[str, str]) -> PhilossOutput:
            content, content_id = content_data
            return await self.evaluate_novelty(content, content_id, context)
        
        tasks = [evaluate_single(content_data) for content_data in contents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"内容{contents[i][1]}评估失败:{result}")
                # 创建错误结果
                error_result = self._get_default_evaluation(
                    contents[i][1], contents[i][0], time.time()
                )
                valid_results.append(error_result)
            else:
                valid_results.append(result)
        
        logger.info(f"批量评估完成,成功:{len([r for r in valid_results if not r.metadata.get('error')])}/{len(contents)}")
        return valid_results
    
    def get_evaluation_statistics(self) -> Dict[str, Any]:
        """获取评估统计信息"""
        if not self.evaluation_history:
            return {
                'total_evaluations': 0,
                'average_novelty_score': 0,
                'model_available': self.model is not None,
                'mlp_available': self.mlp_layer is not None
            }
        
        successful_evaluations = [e for e in self.evaluation_history if not e.metadata.get('error', False)]
        total_novelty = sum(e.novelty_score for e in self.evaluation_history)
        
        return {
            'total_evaluations': len(self.evaluation_history),
            'successful_evaluations': len(successful_evaluations),
            'failed_evaluations': len(self.evaluation_history) - len(successful_evaluations),
            'average_novelty_score': total_novelty / len(self.evaluation_history),
            'average_analysis_time': sum(e.analysis_time for e in self.evaluation_history) / len(self.evaluation_history),
            'model_available': self.model is not None,
            'mlp_available': self.mlp_layer is not None,
            'device': self.device,
            'token_block_size': self.token_block_size
        }
    
    def get_latest_evaluation(self) -> Optional[PhilossOutput]:
        """获取最新的评估结果"""
        return self.evaluation_history[-1] if self.evaluation_history else None
    
    def clear_history(self):
        """清空评估历史"""
        self.evaluation_history.clear()
        logger.info("PhilossChecker评估历史已清空")
    
    def is_model_ready(self) -> bool:
        """检查模型是否就绪"""
        return self.model is not None and self.mlp_layer is not None 
 