import asyncio
import logging
import time
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from NagaAgent.summer_memory.quintuple_extractor import extract_quintuples_async

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待中
    RUNNING = "running"      # 运行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消

@dataclass
class ExtractionTask:
    """五元组提取任务"""
    task_id: str
    text: str
    text_hash: str
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[List] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

class QuintupleTaskManager:
    """五元组提取任务管理器"""
    
    def __init__(self, max_workers: int = None, max_queue_size: int = None):
        # 从配置文件读取设置
        try:
            from config import config
            self.enabled = config.grag.task_manager_enabled
            self.max_workers = max_workers or config.grag.max_workers
            self.max_queue_size = max_queue_size or config.grag.max_queue_size
            self.task_timeout = config.grag.task_timeout
            self.auto_cleanup_hours = config.grag.auto_cleanup_hours
        except Exception as e:
            logger.warning(f"无法读取配置文件，使用默认设置: {e}")
            self.enabled = True
            self.max_workers = max_workers or 3
            self.max_queue_size = max_queue_size or 100
            self.task_timeout = 30
            self.auto_cleanup_hours = 24
        
        self.tasks: Dict[str, ExtractionTask] = {}
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.lock = threading.Lock()
        self.running_tasks = 0
        self.completed_tasks = 0
        self.failed_tasks = 0
        
        # 回调函数
        self.on_task_completed: Optional[Callable] = None
        self.on_task_failed: Optional[Callable] = None
        
        logger.info(f"五元组任务管理器初始化完成，最大并发数: {self.max_workers}, 队列大小: {self.max_queue_size}")
    
    def _generate_task_id(self, text: str) -> str:
        """生成任务ID"""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        timestamp = int(time.time() * 1000)
        return f"extract_{text_hash[:8]}_{timestamp}"
    
    def _generate_text_hash(self, text: str) -> str:
        """生成文本哈希"""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def add_task(self, text: str) -> str:
        """添加提取任务"""
        if not self.enabled:
            raise RuntimeError("任务管理器已禁用")
            
        if not text or not text.strip():
            raise ValueError("文本不能为空")
        
        text_hash = self._generate_text_hash(text)
        
        # 检查是否已有相同文本的任务
        with self.lock:
            for task in self.tasks.values():
                if task.text_hash == text_hash and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    logger.info(f"发现重复任务，返回现有任务ID: {task.task_id}")
                    return task.task_id
        
        # 检查队列大小
        pending_count = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
        if pending_count >= self.max_queue_size:
            raise RuntimeError(f"任务队列已满，最大容量: {self.max_queue_size}")
        
        task_id = self._generate_task_id(text)
        task = ExtractionTask(
            task_id=task_id,
            text=text,
            text_hash=text_hash,
            status=TaskStatus.PENDING,
            created_at=time.time()
        )
        
        with self.lock:
            self.tasks[task_id] = task
        
        logger.info(f"添加提取任务: {task_id}, 文本长度: {len(text)}")
        
        # 异步启动任务
        asyncio.create_task(self._process_task(task_id))
        
        return task_id

    async def _process_task(self, task_id: str, text: str):
        """处理单个任务"""
        try:
            quintuples = await extract_quintuples_async(text)

            # 修复：确保在主线程触发回调
            if self.on_task_completed:
                # 使用线程安全的方式调度回调
                asyncio.run_coroutine_threadsafe(
                    self.on_task_completed(task_id, quintuples),
                    loop=asyncio.get_event_loop()
                )

            return quintuples
        except Exception as e:
            logger.error(f"任务处理失败: {task_id}, 错误: {e}")
            if self.on_task_failed:
                asyncio.run_coroutine_threadsafe(
                    self.on_task_failed(task_id, str(e)),
                    loop=asyncio.get_event_loop()
                )
            return []
    
    def _extract_quintuples_sync(self, text: str) -> List:
        """同步执行五元组提取（在线程池中运行）"""
        try:
            from .quintuple_extractor import extract_quintuples
            return extract_quintuples(text)
        except Exception as e:
            logger.error(f"五元组提取失败: {e}")
            raise
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        if not task:
            return None
        
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "result_count": len(task.result) if task.result else 0,
            "error": task.error,
            "retry_count": task.retry_count
        }
    
    def get_all_tasks(self) -> List[Dict]:
        """获取所有任务状态"""
        with self.lock:
            return [self.get_task_status(task_id) for task_id in self.tasks.keys()]
    
    def get_running_tasks(self) -> List[str]:
        """获取正在运行的任务ID列表"""
        with self.lock:
            return [
                task_id for task_id, task in self.tasks.items() 
                if task.status == TaskStatus.RUNNING
            ]
    
    def get_pending_tasks(self) -> List[str]:
        """获取等待中的任务ID列表"""
        with self.lock:
            return [
                task_id for task_id, task in self.tasks.items() 
                if task.status == TaskStatus.PENDING
            ]
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            with self.lock:
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()
                if task.status == TaskStatus.RUNNING:
                    self.running_tasks -= 1
            
            logger.info(f"任务已取消: {task_id}")
            return True
        
        return False
    
    def get_stats(self) -> Dict:
        """获取任务管理器统计信息"""
        with self.lock:
            total_tasks = len(self.tasks)
            pending_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
            completed_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.COMPLETED)
            failed_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.FAILED)
            cancelled_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.CANCELLED)
            
            return {
                "enabled": self.enabled,
                "total_tasks": total_tasks,
                "pending_tasks": pending_tasks,
                "running_tasks": self.running_tasks,
                "completed_tasks": completed_tasks,
                "failed_tasks": failed_tasks,
                "cancelled_tasks": cancelled_tasks,
                "max_workers": self.max_workers,
                "max_queue_size": self.max_queue_size,
                "queue_usage": f"{pending_tasks}/{self.max_queue_size}",
                "task_timeout": self.task_timeout
            }
    
    def clear_completed_tasks(self, max_age_hours: int = None):
        """清理已完成的任务"""
        if max_age_hours is None:
            max_age_hours = self.auto_cleanup_hours
            
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        with self.lock:
            tasks_to_remove = []
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if task.completed_at and (current_time - task.completed_at) > max_age_seconds:
                        tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
            
            if tasks_to_remove:
                logger.info(f"清理了 {len(tasks_to_remove)} 个过期任务")
    
    def shutdown(self):
        """关闭任务管理器"""
        logger.info("正在关闭任务管理器...")
        
        # 取消所有等待中的任务
        with self.lock:
            for task_id, task in self.tasks.items():
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
        
        # 关闭线程池
        self.executor.shutdown(wait=True)
        logger.info("任务管理器已关闭")

# 全局任务管理器实例
task_manager = QuintupleTaskManager()

# 自动清理任务（每小时清理一次）
async def auto_cleanup_tasks():
    """自动清理已完成的任务"""
    while True:
        try:
            await asyncio.sleep(3600)  # 每小时执行一次
            task_manager.clear_completed_tasks()
        except Exception as e:
            logger.error(f"自动清理任务失败: {e}")

# 启动自动清理
def start_auto_cleanup():
    """启动自动清理任务"""
    try:
        # 检查是否在异步上下文中
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(auto_cleanup_tasks())
        else:
            # 如果不在异步上下文中，使用线程来启动
            import threading
            def run_cleanup():
                try:
                    asyncio.run(auto_cleanup_tasks())
                except RuntimeError:
                    # 如果已经有事件循环在运行，使用create_task
                    loop = asyncio.get_event_loop()
                    asyncio.create_task(auto_cleanup_tasks())
            
            thread = threading.Thread(target=run_cleanup, daemon=True)
            thread.start()
    except Exception as e:
        logger.warning(f"启动自动清理任务失败: {e}") 
