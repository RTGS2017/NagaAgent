import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
import traceback
import os
import sys

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
try:
    from system.config import config
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("无法导入 config 模块，使用默认设置")

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    future: Optional[asyncio.Future] = None


class QuintupleTaskManager:
    """五元组提取任务管理器 - 重构版"""

    def __init__(self, max_workers: int = 3, max_queue_size: int = 100):
        # 从配置文件读取设置或使用默认值
        try:
            self.max_workers = max_workers or config.grag.max_workers
            self.max_queue_size = max_queue_size or config.grag.max_queue_size
            self.task_timeout = config.grag.task_timeout
            self.auto_cleanup_hours = config.grag.auto_cleanup_hours
            self.enabled = True
        except Exception:
            self.max_workers = max_workers or 3
            self.max_queue_size = max_queue_size or 100
            self.task_timeout = 30
            self.auto_cleanup_hours = 24
            self.enabled = True

        # 任务存储
        self.tasks: Dict[str, ExtractionTask] = {}
        self.task_queue = asyncio.Queue(maxsize=self.max_queue_size)

        # 工作协程管理
        self.worker_tasks: List[asyncio.Task] = []
        self.is_running = False
        self.lock = asyncio.Lock()

        # 统计信息
        self.completed_tasks = 0
        self.failed_tasks = 0

        # 回调函数
        self.on_task_completed: Optional[Callable] = None
        self.on_task_failed: Optional[Callable] = None

        # 自动清理任务
        self.cleanup_task: Optional[asyncio.Task] = None

        logger.info(f"任务管理器初始化完成: workers={self.max_workers}, queue_size={self.max_queue_size}")

    async def start(self):
        if self.is_running:
            logger.info("任务管理器已在运行")
            return

        logger.info("正在启动任务管理器...")
        self.is_running = True

        try:
            # 确保在事件循环中运行
            loop = asyncio.get_running_loop()

            # 创建工作协程
            for i in range(self.max_workers):
                worker_task = loop.create_task(  # 使用当前循环创建任务
                    self._worker_loop(f"worker-{i + 1}"),
                    name=f"task_worker_{i}"
                )
                self.worker_tasks.append(worker_task)

            # 添加工作协程状态检查
            await asyncio.sleep(0.5)  # 短暂等待协程启动
            active_workers = sum(1 for t in self.worker_tasks if not t.done())
            logger.info(f"活跃工作协程: {active_workers}/{self.max_workers}")

            # 启动自动清理任务 - 添加异常处理
            try:
                self.cleanup_task = asyncio.create_task(self._auto_cleanup_loop())
                logger.info("自动清理任务已启动")
            except Exception as e:
                logger.error(f"启动自动清理任务失败: {e}, 但任务管理器将继续运行")
                # 即使自动清理失败，也不关闭任务管理器
                self.cleanup_task = None

            logger.info(f"任务管理器已启动，工作线程数: {self.max_workers}")
        except Exception as e:
            logger.error(f"启动任务管理器失败: {e}")
            self.is_running = False
            raise

    async def shutdown(self):
        """停止任务管理器"""
        if not self.is_running:
            return

        self.is_running = False

        # 取消所有工作协程
        for task in self.worker_tasks:
            task.cancel()

        # 等待工作协程完成
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)

        # 取消清理任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.warning("任务管理器正在关闭...")
        logger.warning(f"调用栈: {''.join(traceback.format_stack())}")

        logger.info("任务管理器已停止")

    def _generate_task_id(self, text: str) -> str:
        """生成唯一的任务ID"""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        timestamp = int(time.time() * 1000)
        return f"extract_{text_hash[:8]}_{timestamp}"

    def _generate_text_hash(self, text: str) -> str:
        """生成文本哈希值"""
        return hashlib.sha256(text.encode()).hexdigest()

    def is_active(self) -> bool:
        """检查任务管理器是否活跃运行"""
        return self.is_running and any(not t.done() for t in self.worker_tasks)

    async def add_task(self, text: str) -> str:
        logger.info("add_task被调用")  # 改为INFO级别确保输出
        """添加新的提取任务"""
        if not self.enabled:
            raise RuntimeError("任务管理器已禁用")

        if not text or not text.strip():
            raise ValueError("文本不能为空")

        text_hash = self._generate_text_hash(text)

        # === 关键修复1: 添加状态检查 ===
        if not self.is_running:
            logger.warning("任务管理器未运行，尝试启动...")
            await self.start()  # 确保任务管理器已启动

        # 检查重复任务
        async with self.lock:
            for task in self.tasks.values():
                if task.text_hash == text_hash and task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                    logger.info(f"发现重复任务: {task.task_id}")
                    return task.task_id

        # 创建新任务
        task_id = self._generate_task_id(text)
        task = ExtractionTask(
            task_id=task_id,
            text=text,
            text_hash=text_hash,
            status=TaskStatus.PENDING,
            created_at=time.time(),
            future=asyncio.Future()
        )

        # 添加到任务字典
        async with self.lock:
            self.tasks[task_id] = task

        logger.info(f"添加新任务: {task_id} (长度={len(text)})")

        # 将任务放入队列
        try:
            if self.task_queue.full():
                logger.warning(f"任务队列已满 ({self.task_queue.qsize()}/{self.max_queue_size})")

            await self.task_queue.put(task)
            logger.info(f"任务已加入队列: {task_id}")
            return task_id
        except Exception as e:
            logger.error(f"加入队列失败: {task_id}, 错误: {e}")
            async with self.lock:
                del self.tasks[task_id]
            raise RuntimeError("加入队列失败")

    async def get_task_result(self, task_id: str, timeout: float = None) -> Tuple[List, str]:
        """获取任务结果，支持超时等待"""
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                raise ValueError(f"任务不存在: {task_id}")

            if task.status == TaskStatus.COMPLETED:
                return task.result, None
            elif task.status in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
                return None, task.error or "任务失败或被取消"

        # 等待任务完成
        try:
            await asyncio.wait_for(task.future, timeout=timeout)
            if task.status == TaskStatus.COMPLETED:
                return task.result, None
            else:
                return None, task.error or "任务失败"
        except asyncio.TimeoutError:
            return None, "任务超时"
        except asyncio.CancelledError:
            return None, "任务被取消"

    async def _worker_loop(self, worker_id: str):
        """工作协程主循环"""
        logger.info(f"工作协程启动: {worker_id}")

        # === 添加启动确认日志 ===
        logger.info(f"✅ {worker_id} 已进入工作循环，状态: running={self.is_running}")

        while self.is_running:
            try:
                # === 添加队列状态日志 ===
                logger.debug(f"{worker_id} 正在等待新任务 (队列大小: {self.task_queue.qsize()})")

                # 使用带超时的get，避免永久阻塞
                try:
                    task = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # 超时但继续循环检查
                    continue

                logger.info(f"{worker_id} 获取到任务: {task.task_id}")

                if task.status != TaskStatus.PENDING:
                    logger.warning(f"任务状态异常: {task.task_id} ({task.status.value})")
                    self.task_queue.task_done()
                    continue

                # 更新任务状态
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()
                logger.info(f"{worker_id} 开始处理任务: {task.task_id}")

                # 执行任务
                result = None
                error = None
                try:
                    # 导入提取函数（避免循环导入）
                    from .quintuple_extractor import extract_quintuples_async
                    logger.info(f"{worker_id} 调用五元组提取API: {task.task_id}")

                    # 使用超时控制执行任务
                    result = await asyncio.wait_for(
                        extract_quintuples_async(task.text),
                        timeout=self.task_timeout
                    )
                    logger.info(f"{worker_id} 提取到 {len(result)} 个五元组: {task.text}")

                    # 更新任务状态
                    async with self.lock:
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                        task.completed_at = time.time()
                        self.completed_tasks += 1

                except asyncio.TimeoutError:
                    error = "任务执行超时"
                    logger.warning(f"{worker_id} 任务超时: {task.task_id}")
                    async with self.lock:
                        task.status = TaskStatus.FAILED
                        task.error = error
                        task.completed_at = time.time()
                        self.failed_tasks += 1

                except Exception as e:
                    error = str(e)
                    logger.error(f"{worker_id} 任务失败: {task.task_id}, 错误: {error}")
                    traceback.print_exc()
                    async with self.lock:
                        task.status = TaskStatus.FAILED
                        task.error = error
                        task.completed_at = time.time()
                        self.failed_tasks += 1

                # 设置future结果
                if not task.future.done():
                    if task.status == TaskStatus.COMPLETED:
                        task.future.set_result(result)
                    else:
                        task.future.set_exception(Exception(error or "任务失败"))

                # 触发回调
                try:
                    if task.status == TaskStatus.COMPLETED and self.on_task_completed:
                        self.on_task_completed(task.task_id, result)
                    elif task.status == TaskStatus.FAILED and self.on_task_failed:
                        self.on_task_failed(task.task_id, error)
                except Exception as e:
                    logger.error(f"任务回调失败: {task.task_id}, 错误: {str(e)}")

                # 标记任务完成
                self.task_queue.task_done()
                logger.info(f"{worker_id} 任务处理完成: {task.task_id}")


            except asyncio.CancelledError:
                logger.info(f"{worker_id} 工作协程被取消")
                break

            except Exception as e:
                logger.error(f"{worker_id} 工作协程异常: {str(e)}")
                logger.error(traceback.format_exc())
                # 防止异常导致循环崩溃
                await asyncio.sleep(1)


    async def clear_completed_tasks(self, max_age_hours: int = None):
        """清理已完成的任务"""
        if max_age_hours is None:
            max_age_hours = self.auto_cleanup_hours

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        removed_count = 0

        async with self.lock:
            tasks_to_remove = []
            for task_id, task in self.tasks.items():
                if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    if task.completed_at and (current_time - task.completed_at) > max_age_seconds:
                        tasks_to_remove.append(task_id)

            for task_id in tasks_to_remove:
                del self.tasks[task_id]
                removed_count += 1

        if removed_count > 0:
            logger.info(f"清理了 {removed_count} 个过期任务")

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
        return [self.get_task_status(task_id) for task_id in self.tasks.keys()]

    def get_running_tasks(self) -> List[str]:
        """获取正在运行的任务ID列表"""
        return [
            task_id for task_id, task in self.tasks.items()
            if task.status == TaskStatus.RUNNING
        ]

    def get_pending_tasks(self) -> List[str]:
        """获取等待中的任务ID列表"""
        return [
            task_id for task_id, task in self.tasks.items()
            if task.status == TaskStatus.PENDING
        ]

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
                task.status = TaskStatus.CANCELLED
                task.completed_at = time.time()

                # 设置future异常
                if task.future and not task.future.done():
                    task.future.set_exception(asyncio.CancelledError("任务被取消"))

                logger.info(f"任务已取消: {task_id}")
                return True

            return False

    async def _auto_cleanup_loop(self):
        """自动清理任务循环"""
        logger.info("自动清理任务已启动")

        while self.is_running:
            try:
                # 每小时清理一次
                await asyncio.sleep(3600)
                await self.clear_completed_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动清理失败: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟

    def get_stats(self) -> Dict:
        """获取任务管理器统计信息"""
        total_tasks = len(self.tasks)
        pending_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.PENDING)
        running_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.RUNNING)
        completed_tasks = self.completed_tasks
        failed_tasks = self.failed_tasks
        cancelled_tasks = sum(1 for task in self.tasks.values() if task.status == TaskStatus.CANCELLED)

        return {
            "enabled": self.enabled,
            "total_tasks": total_tasks,
            "pending_tasks": pending_tasks,
            "running_tasks": running_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "cancelled_tasks": cancelled_tasks,
            "max_workers": self.max_workers,
            "max_queue_size": self.max_queue_size,
            "queue_size": self.task_queue.qsize(),
            "queue_usage": f"{self.task_queue.qsize()}/{self.max_queue_size}",
            "task_timeout": self.task_timeout
        }


# 全局任务管理器实例
task_manager = QuintupleTaskManager()

async def auto_cleanup_tasks():
    """自动清理已完成的任务"""
    while True:
        try:
            await asyncio.sleep(3600)  # 每小时执行一次
            await task_manager.clear_completed_tasks()
        except Exception as e:
            logger.error(f"自动清理任务失败: {e}")

def start_auto_cleanup():
    """启动自动清理任务"""
    try:
        # 确保在正确的事件循环中运行
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环已在运行，直接创建任务
            loop.create_task(auto_cleanup_tasks())
        else:
            # 如果事件循环未运行，启动它
            def run_cleanup():
                asyncio.run(auto_cleanup_tasks())

            thread = threading.Thread(target=run_cleanup, daemon=True)
            thread.start()
    except RuntimeError as e:
        if "no current event loop" in str(e):
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.create_task(auto_cleanup_tasks())
            # 在新线程中运行事件循环
            thread = threading.Thread(target=loop.run_forever, daemon=True)
            thread.start()
        else:
            logger.error(f"启动自动清理任务失败: {e}")
    except Exception as e:
        logger.error(f"启动自动清理任务异常: {e}")

# 添加全局标志
_task_manager_running = False

async def start_task_manager():
    global _task_manager_running
    if not _task_manager_running:
        logger.info("启动任务管理器...")
        await task_manager.start()
        _task_manager_running = True
        logger.info("任务管理器已成功启动")
    else:
        logger.info("任务管理器已在运行中")

async def stop_task_manager():
    global _task_manager_running
    if _task_manager_running:
        logger.info("停止任务管理器...")
        await task_manager.shutdown()
        _task_manager_running = False
        logger.info("任务管理器已停止")
