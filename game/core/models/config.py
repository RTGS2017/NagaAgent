"""
NagaAgent Game 配置管理
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any
import os
from pathlib import Path


@dataclass
class PhilossConfig:
    """Philoss配置"""
    model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct"  # 模型名称
    model_path: str = ""  # 模型本地路径
    device: str = "cuda"  # 设备类型
    max_memory: str = "8GB"  # 最大内存使用
    token_block_size: int = 100  # 文本块大小（token数）
    hidden_size: int = 768  # 隐藏层大小
    mlp_hidden_size: int = 256  # MLP隐藏层大小
    prediction_threshold: float = 0.6  # 预测阈值
    novelty_threshold: float = 0.6  # 创新性阈值
    cache_dir: str = "models"  # 模型缓存目录（仅忽略仓库根目录 /models）
    local_files_only: bool = False  # 仅使用本地权重（不联网下载）
    exclusive_model_loading: bool = True  # 禁止回退到其他模型
    hf_token: str = ""  # HuggingFace token（可选，用于需要鉴权的模型）
    
    def __post_init__(self):
        # 如果没有指定本地路径,使用默认路径
        if not self.model_path:
            self.model_path = os.path.expanduser(f"~/.cache/huggingface/transformers/{self.model_name}")
        # 确保缓存目录存在
        try:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


@dataclass  
class SelfGameConfig:
    """自博弈配置"""
    max_iterations: int = 10  # 最大迭代次数
    max_critics: int = 3  # 最大批判者数量
    timeout_seconds: int = 300  # 超时时间
    convergence_threshold: float = 0.8  # 收敛阈值
    quality_threshold: float = 0.7  # 质量阈值
    enable_thinking_vector: bool = True  # 是否启用思维向量
    thinking_vector_max_depth: int = 5  # 思维向量最大深度
    max_self_route_iterations: int = 10  # 单节点自指最大迭代轮次
    branches_per_agent: int = 1  # 每个角色并行的自博弈分支数（默认1，避免重复执行五次）


@dataclass
class InteractionGraphConfig:
    """交互图配置"""
    max_agents: int = 10  # 最大智能体数量
    min_agents: int = 2  # 最小智能体数量
    role_templates_path: str = "templates/roles"  # 角色模板路径
    collaboration_rules_path: str = "templates/collaboration"  # 协作规则路径
    enable_dynamic_routing: bool = True  # 是否启用动态路由
    max_routing_hops: int = 3  # 最大路由跳数


@dataclass
class SystemConfig:
    """系统配置"""
    log_level: str = "INFO"  # 日志级别
    save_intermediate_results: bool = True  # 是否保存中间结果
    results_dir: str = "results"  # 结果保存目录
    enable_async: bool = True  # 是否启用异步处理
    max_concurrent_tasks: int = 5  # 最大并发任务数
    checkpoint_interval: int = 10  # 检查点间隔（秒）
    max_concurrent_api: int = 10  # API限流-最大并发
    min_api_interval_seconds: float = 0.0  # API限流-最小调用间隔


@dataclass  
class GameConfig:
    """博弈系统总配置"""
    philoss: PhilossConfig = field(default_factory=PhilossConfig)
    self_game: SelfGameConfig = field(default_factory=SelfGameConfig) 
    interaction_graph: InteractionGraphConfig = field(default_factory=InteractionGraphConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    
    def __post_init__(self):
        # 确保结果目录存在
        Path(self.system.results_dir).mkdir(parents=True, exist_ok=True)
        
        # 确保角色模板目录存在
        Path(self.interaction_graph.role_templates_path).mkdir(parents=True, exist_ok=True)
        Path(self.interaction_graph.collaboration_rules_path).mkdir(parents=True, exist_ok=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'philoss': self.philoss.__dict__,
            'self_game': self.self_game.__dict__,
            'interaction_graph': self.interaction_graph.__dict__,
            'system': self.system.__dict__
        }
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'GameConfig':
        """从字典创建配置"""
        config = cls()
        
        if 'philoss' in config_dict:
            config.philoss = PhilossConfig(**config_dict['philoss'])
        if 'self_game' in config_dict:
            config.self_game = SelfGameConfig(**config_dict['self_game'])
        if 'interaction_graph' in config_dict:
            config.interaction_graph = InteractionGraphConfig(**config_dict['interaction_graph'])
        if 'system' in config_dict:
            config.system = SystemConfig(**config_dict['system'])
            
        return config
    
    def save_to_file(self, file_path: str):
        """保存配置到文件"""
        import json
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> 'GameConfig':
        """从文件加载配置"""
        import json
        with open(file_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
        return cls.from_dict(config_dict)


# 默认配置实例
DEFAULT_CONFIG = GameConfig()


def get_domain_config(domain: str) -> GameConfig:
    """基于域字符串的动态配置（无固定领域枚举）。
    算法性启发：
    - 以域字符串的长度与散列生成稳定但无模板依赖的参数
    - 保持参数在合理范围内
    """
    import hashlib
    base = GameConfig()
    name = (domain or "").strip()

    # 生成稳定哈希
    seed_int = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) if name else 0

    # 交互图智能体数量范围：min_agents ∈ [2,6]，max_agents ∈ [min+1, min+4] 且不超过10
    min_agents = 2 + (seed_int % 5)  # 2..6
    extra = 1 + ((seed_int >> 3) % 4)  # 1..4
    max_agents = min(10, min_agents + extra)
    base.interaction_graph.min_agents = min_agents
    base.interaction_graph.max_agents = max_agents

    # 自博弈迭代上限：依据字符串长度与哈希，范围 [8, 20]
    length_factor = max(0, min(len(name), 24))  # 限制影响范围
    iter_base = 8 + (length_factor // 4)  # 8..14
    iter_jitter = (seed_int >> 7) % 7  # 0..6
    base.self_game.max_iterations = min(20, iter_base + iter_jitter)

    # 阈值动态微调（±0.1 内抖动）
    base.self_game.convergence_threshold = max(0.6, min(0.95, base.self_game.convergence_threshold + (((seed_int >> 11) % 21 - 10) / 100)))
    base.self_game.quality_threshold = max(0.5, min(0.9, base.self_game.quality_threshold + (((seed_int >> 13) % 21 - 10) / 100)))

    return base 
 
 