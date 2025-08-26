import logging
import asyncio
import traceback
import weakref
from typing import List, Dict, Optional, Tuple
from .quintuple_extractor import extract_quintuples
from .quintuple_graph import store_quintuples, query_graph_by_keywords, get_all_quintuples
from .quintuple_rag_query import query_knowledge, set_context
from .memory_decision import memory_decision_maker
from .task_manager import task_manager, start_auto_cleanup, start_task_manager
from system.config import config, AI_NAME

logger = logging.getLogger(__name__)

class GRAGMemoryManager:
    """GRAG知识图谱记忆管理器"""
    
    def __init__(self):
        self.enabled = config.grag.enabled
        self.auto_extract = config.grag.auto_extract
        self.context_length = config.grag.context_length
        self.similarity_threshold = config.grag.similarity_threshold
        self.recent_context = [] # 最近对话上下文
        self.extraction_cache = set() # 避免重复提取
        self.active_tasks = set() # 当前活跃的任务ID

        if not self.enabled:
            logger.info("GRAG记忆系统已禁用")
            return

        try:
            # 初始化Neo4j连接
            from .quintuple_graph import graph
            logger.info("GRAG记忆系统初始化成功")

            # 启动自动清理任务
            start_auto_cleanup()

            # 设置任务完成回调
            self._weak_ref = weakref.ref(self)
            task_manager.on_task_completed = self._on_task_completed_wrapper

        except Exception as e:
            logger.error(f"GRAG记忆系统初始化失败: {e}")
            self.enabled = False

    async def add_conversation_memory(self, user_input: str, ai_response: str) -> bool:
        """添加对话记忆到知识图谱（使用任务管理器并发处理）"""
        if not self.enabled:
            return False
        try:
            # 拼接本轮内容
            conversation_text = f"用户: {user_input}\n{AI_NAME}: {ai_response}"
            logger.info(f"添加对话记忆: {conversation_text[:50]}...")

            # 更新recent_context（限制长度）
            self.recent_context.append(conversation_text)
            if len(self.recent_context) > self.context_length:
                self.recent_context = self.recent_context[-self.context_length:]

            # 使用任务管理器异步提取五元组
            if self.auto_extract:
                try:
                    if not task_manager.is_running:
                        logger.warning("任务管理器未运行，正在启动...")
                        from .task_manager import start_task_manager
                        await start_task_manager()
                        await asyncio.sleep(1)  # 等待启动完成

                    logger.info(f"任务管理器状态: running={task_manager.is_running}, workers={len(task_manager.worker_tasks)}")

                    task_id = await task_manager.add_task(conversation_text)
                    self.active_tasks.add(task_id)
                    logger.info(f"已提交五元组提取任务: {task_id}")
                    return True
                except Exception as e:
                    logger.error(f"提交提取任务失败: {e}")
                    # 如果任务管理器失败，回退到同步提取
                    await self._extract_and_store_quintuples_fallback(conversation_text)

            return True
        except Exception as e:
            logger.error(f"添加对话记忆失败: {e}")
            return False


    def _on_task_completed_wrapper(self, task_id: str, quintuples: List):
        """包装回调方法，处理实例可能被销毁的情况"""
        instance = self._weak_ref()
        if instance:
            asyncio.run_coroutine_threadsafe(
                instance._on_task_completed(task_id, quintuples),
                loop=asyncio.get_event_loop()
            )

    async def _on_task_completed(self, task_id: str, quintuples: List) -> None:
        try:
            self.active_tasks.discard(task_id)
            logger.info(f"任务完成回调: {task_id}, 提取到 {len(quintuples)} 个五元组")

            # 确保在事件循环线程中执行
            if not quintuples:
                logger.warning(f"任务 {task_id} 未提取到五元组")
                return

            logger.debug(f"准备存储五元组: {quintuples[:2]}...")

            # 直接调用同步存储函数（避免线程切换）
            store_success = store_quintuples(quintuples)

            if store_success:
                logger.info(f"任务 {task_id} 的五元组存储成功")
            else:
                logger.error(f"任务 {task_id} 的五元组存储失败")

        except Exception as e:
            logger.error(f"任务完成回调处理失败: {e}")

    async def _on_task_failed(self, task_id: str, error: str) -> None:
        """任务失败回调"""
        try:
            self.active_tasks.discard(task_id)
            logger.error(f"任务失败回调: {task_id}, 错误: {error}")
        except Exception as e:
            logger.error(f"任务失败回调处理失败: {e}")

    async def _extract_and_store_quintuples_fallback(self, text: str) -> bool:
        """回退到同步提取方法"""
        try:
            import hashlib
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            if text_hash in self.extraction_cache:
                logger.debug(f"跳过已处理的文本: {text[:50]}...")
                return True

            logger.info(f"使用回退方法提取五元组: {text[:100]}...")
            
            # 添加超时保护，避免长时间阻塞
            try:
                quintuples = await asyncio.wait_for(
                    asyncio.to_thread(extract_quintuples, text), 
                    timeout=30.0  # 30秒超时
                )
            except asyncio.TimeoutError:
                logger.warning("五元组提取超时，跳过本次提取")
                return False

            if not quintuples:
                logger.warning("未提取到五元组")
                return False

            logger.info(f"提取到 {len(quintuples)} 个五元组，准备存储")

            # 存储到Neo4j - 也添加超时保护
            try:
                store_success = await asyncio.wait_for(
                    asyncio.to_thread(store_quintuples, quintuples),
                    timeout=15.0  # 15秒超时
                )
            except asyncio.TimeoutError:
                logger.warning("五元组存储超时，跳过本次存储")
                return False

            if store_success:
                self.extraction_cache.add(text_hash)
                logger.info("五元组存储成功")
                return True
            else:
                logger.error("五元组存储失败")
                return False

        except Exception as e:
            logger.error(f"提取和存储五元组失败: {str(e)}")
            logger.error(traceback.format_exc())
            return False
    
    async def query_memory(self, question: str) -> Optional[str]:
        """查询记忆"""
        if not self.enabled:
            return None
            
        try:
            # 设置查询上下文
            set_context(self.recent_context)
            
            # 异步查询
            result = await asyncio.to_thread(query_knowledge, question)
            
            if result and "未在知识图谱中找到相关信息" not in result:
                logger.info("从记忆中找到相关信息")
                return result
            return None
        except Exception as e:
            logger.error(f"查询记忆失败: {e}")
            return None
    
    async def get_relevant_memories(self, query: str, limit: int = 3) -> List[Tuple[str, str, str, str, str]]:
        """获取相关记忆（五元组格式）"""
        if not self.enabled:
            return []
            
        try:
            # 从Neo4j查询相关五元组
            quintuples = await asyncio.to_thread(query_graph_by_keywords, [query])
            
            # 限制返回数量
            return quintuples[:limit]
        except Exception as e:
            logger.error(f"获取相关记忆失败: {e}")
            return []
    
    def get_memory_stats(self) -> Dict:
        """获取记忆统计信息"""
        if not self.enabled:
            return {"enabled": False}
            
        try:
            all_quintuples = get_all_quintuples()
            task_stats = task_manager.get_stats()
            
            return {
                "enabled": True,
                "total_quintuples": len(all_quintuples),
                "context_length": len(self.recent_context),
                "cache_size": len(self.extraction_cache),
                "active_tasks": len(self.active_tasks),
                "task_manager": task_stats
            }
        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}")
            return {"enabled": False, "error": str(e)}
    
    def get_task_status(self, task_id: str) -> Optional[Dict]:
        """获取任务状态"""
        return task_manager.get_task_status(task_id)
    
    def get_all_task_status(self) -> List[Dict]:
        """获取所有任务状态"""
        return task_manager.get_all_tasks()
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        if task_id in self.active_tasks:
            self.active_tasks.discard(task_id)
        return task_manager.cancel_task(task_id)
    
    async def clear_memory(self) -> bool:
        """清空记忆"""
        if not self.enabled:
            return False
            
        try:
            self.recent_context.clear()
            self.extraction_cache.clear()
            
            # 取消所有活跃任务
            for task_id in list(self.active_tasks):
                task_manager.cancel_task(task_id)
            self.active_tasks.clear()
            
            logger.info("记忆已清空")
            return True
        except Exception as e:
            logger.error(f"清空记忆失败: {e}")
            return False
    
    async def query_memory_intelligent(self, user_question: str) -> Optional[str]:
        """智能记忆查询：基于决策结果进行查询"""
        if not self.enabled:
            return None
            
        try:
            # 1. 记忆查询决策
            query_decision = await memory_decision_maker.decide_memory_query(user_question)
            
            if not query_decision.should_query:
                logger.info("记忆查询决策：无需查询记忆")
                return None
            
            logger.info(f"记忆查询决策：需要查询，关键词={query_decision.query_keywords}，类型={query_decision.memory_types}")
            
            # 2. 执行查询
            return await self._query_memory_by_decision(query_decision, user_question)
            
        except Exception as e:
            logger.error(f"智能记忆查询失败: {e}")
            return None
    
    async def _query_memory_by_decision(self, query_decision, user_question: str) -> Optional[str]:
        """根据决策结果执行记忆查询"""
        try:
            # 设置查询上下文
            set_context(self.recent_context)
            
            # 使用决策结果中的关键词进行查询
            keywords = query_decision.query_keywords
            if not keywords:
                # 如果没有关键词，使用用户问题
                keywords = [user_question]
            
            # 执行查询
            result = await asyncio.to_thread(query_knowledge, user_question)
            
            if result and "未在知识图谱中找到相关信息" not in result:
                logger.info(f"智能记忆查询成功，找到相关信息")
                return result
            else:
                logger.info("智能记忆查询：未找到相关信息")
                return None
                
        except Exception as e:
            logger.error(f"根据决策结果查询记忆失败: {e}")
            return None
    
    async def store_memory_intelligent(self, user_question: str, ai_response: str) -> bool:
        """智能记忆存储：基于决策结果进行存储"""
        if not self.enabled:
            return False
            
        try:
            # 1. 记忆生成决策
            generation_decision = await memory_decision_maker.decide_memory_generation(user_question, ai_response)
            
            if not generation_decision.should_store:
                logger.info("记忆生成决策：无需存储记忆")
                return False
            
            logger.info(f"记忆生成决策：需要存储，类型={generation_decision.memory_type}，重要性={generation_decision.importance_score}")
            
            # 2. 执行存储
            return await self._store_memory_by_decision(generation_decision, user_question, ai_response)
            
        except Exception as e:
            logger.error(f"智能记忆存储失败: {e}")
            return False
    
    async def _store_memory_by_decision(self, generation_decision, user_question: str, ai_response: str) -> bool:
        """根据决策结果执行记忆存储"""
        try:
            # 拼接对话内容
            conversation_text = f"用户: {user_question}\n娜迦: {ai_response}"
            
            # 更新recent_context
            self.recent_context.append(conversation_text)
            if len(self.recent_context) > self.context_length:
                self.recent_context = self.recent_context[-self.context_length:]
            
            # 使用任务管理器异步提取五元组
            if self.auto_extract:
                try:
                    if not task_manager.is_running:
                        logger.warning("任务管理器未运行，正在启动...")
                        from .task_manager import start_task_manager
                        await start_task_manager()
                        await asyncio.sleep(1)
                    
                    task_id = await task_manager.add_task(conversation_text)
                    self.active_tasks.add(task_id)
                    logger.info(f"已提交智能记忆存储任务: {task_id}")
                    return True
                except Exception as e:
                    logger.error(f"提交智能记忆存储任务失败: {e}")
                    # 回退到同步提取
                    return await self._extract_and_store_quintuples_fallback(conversation_text)
            
            return True
            
        except Exception as e:
            logger.error(f"根据决策结果存储记忆失败: {e}")
            return False

# 全局记忆管理器实例
memory_manager = GRAGMemoryManager() 
