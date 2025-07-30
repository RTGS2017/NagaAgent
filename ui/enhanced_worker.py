"""
增强版Worker类
支持进度更新、状态回调、错误处理和取消操作
现在支持通过API或直接调用NagaAgent
"""

import asyncio
import time
import json
import aiohttp
from PyQt5.QtCore import QThread, pyqtSignal
from ui.response_utils import extract_message
from config import config

class EnhancedWorker(QThread):
    """增强版工作线程"""
    
    # 信号定义
    finished = pyqtSignal(str)  # 完成信号，返回最终结果
    progress_updated = pyqtSignal(int, str)  # 进度更新信号 (value, status)
    status_changed = pyqtSignal(str)  # 状态变化信号
    error_occurred = pyqtSignal(str)  # 错误发生信号
    partial_result = pyqtSignal(str)  # 部分结果信号（流式输出）
    
    def __init__(self, naga, user_input, parent=None, use_api=False):
        super().__init__(parent)
        self.naga = naga
        self.user_input = user_input
        self.is_cancelled = False
        self.result_buffer = []
        self.use_api = use_api  # 是否使用API模式
        
        # 初始化语音集成模块
        try:
            from voice.voice_integration import get_voice_integration
            self.voice_integration = get_voice_integration()
        except Exception as e:
            print(f"语音集成初始化失败: {e}")
            self.voice_integration = None
        
    def cancel(self):
        """取消当前操作"""
        self.is_cancelled = True
        self.status_changed.emit("正在取消...")
        # 立即发出完成信号，避免UI等待
        self.finished.emit("操作已取消")
        
    def run(self):
        """主执行函数"""
        try:
            # 重置取消状态（确保新任务开始时状态正确）
            self.is_cancelled = False
            
            # 检查是否在开始前就被取消
            if self.is_cancelled:
                return
            
            self.status_changed.emit("正在初始化...")
            self.progress_updated.emit(10, "准备处理请求")
            
            if self.is_cancelled:
                return
                
            # 设置事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 执行异步处理
                if self.use_api:
                    result = loop.run_until_complete(self.process_with_api())
                else:
                    result = loop.run_until_complete(self.process_with_progress())
                
                if not self.is_cancelled and result:
                    # 提取最终消息
                    final_message = extract_message(result)
                    self.finished.emit(final_message)
                    
            finally:
                loop.close()
                
        except Exception as e:
            if not self.is_cancelled:  # 只有在未取消时才报告错误
                error_msg = f"处理失败: {str(e)}"
                self.error_occurred.emit(error_msg)
                self.finished.emit(f"抱歉，处理您的请求时遇到了问题：{error_msg}")
            
    async def process_with_progress(self):
        """带进度的异步处理（直接调用NagaAgent）"""
        start_time = time.time()
        
        try:
            self.status_changed.emit("正在思考...")
            self.progress_updated.emit(20, "分析您的问题")
            
            if self.is_cancelled:
                return ""
                
            # 开始处理
            result_chunks = []
            chunk_count = 0
            
            self.status_changed.emit("正在生成回复...")
            self.progress_updated.emit(40, "AI正在思考")
            
            async for chunk in self.naga.process(self.user_input):
                if self.is_cancelled:
                    break
                    
                chunk_count += 1
                
                # 处理chunk格式 - 不进行extract_message处理，直接累积原始内容
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    speaker, content = chunk
                    if speaker == "娜迦":
                        content_str = str(content)
                        result_chunks.append(content_str)
                        # 发送部分结果用于实时显示
                        self.partial_result.emit(content_str)
                else:
                    content_str = str(chunk)
                    result_chunks.append(content_str)
                    self.partial_result.emit(content_str)
                
                # 更新进度
                progress = min(90, 40 + chunk_count * 2)
                self.progress_updated.emit(progress, f"正在生成回复... ({chunk_count})")
                
                # 短暂休眠，让UI有时间更新
                await asyncio.sleep(0.01)
            
            if not self.is_cancelled:
                self.progress_updated.emit(95, "完成生成")
                full_result = ''.join(result_chunks)
                
                # 处理完成
                elapsed = time.time() - start_time
                self.status_changed.emit(f"完成 (用时 {elapsed:.1f}s)")
                self.progress_updated.emit(100, "处理完成")
                
                return full_result
            else:
                return ""
                
        except Exception as e:
            self.error_occurred.emit(f"异步处理错误: {str(e)}")
            raise
            
    async def process_with_api(self):
        """通过API处理请求"""
        start_time = time.time()
        
        try:
            self.status_changed.emit("连接到API...")
            self.progress_updated.emit(15, "建立API连接")
            
            if self.is_cancelled:
                return ""
            
            # 构造OpenAI兼容的请求
            api_url = f"http://{config.api_server.host}:{config.api_server.port}/v1/chat/completions"
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": config.api.model,
                "messages": [{"role": "user", "content": self.user_input}],
                "temperature": config.api.temperature,
                "max_tokens": config.api.max_tokens,
                "stream": True
            }
            
            self.status_changed.emit("正在生成回复...")
            self.progress_updated.emit(30, "API处理中")
            
            result_chunks = []
            word_count = 0
            
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        raise Exception(f"API请求失败: {resp.status}")
                    
                    # 流式处理响应
                    async for line in resp.content:
                        if self.is_cancelled:
                            break
                            
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]  # Remove "data: " prefix
                            if data_str.strip() == "[DONE]":
                                break
                                
                            try:
                                data = json.loads(data_str)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        result_chunks.append(content)
                                        self.partial_result.emit(content)
                                        word_count += len(content)
                                        
                                        # 更新进度
                                        if word_count < 50:
                                            status = "开始回复..."
                                            progress = 35
                                        elif word_count < 200:
                                            status = "正在详细解答..."
                                            progress = 50
                                        elif word_count < 500:
                                            status = "完善回答内容..."
                                            progress = 70
                                        else:
                                            status = "整理最终回复..."
                                            progress = 85
                                            
                                        self.progress_updated.emit(progress, f"{status} ({word_count}字)")
                            except json.JSONDecodeError:
                                continue
            
            if not self.is_cancelled:
                elapsed = time.time() - start_time
                self.status_changed.emit(f"回复完成 (用时 {elapsed:.1f}s，{word_count}字)")
                self.progress_updated.emit(100, "完成")
                
                return ''.join(result_chunks)
            else:
                return ""
                
        except Exception as e:
            self.error_occurred.emit(f"API处理错误: {str(e)}")
            raise


class StreamingWorker(EnhancedWorker):
    """流式处理Worker，专门优化流式对话体验"""
    
    # 额外信号
    stream_chunk = pyqtSignal(str)  # 流式数据块
    stream_complete = pyqtSignal()  # 流式完成
    
    def __init__(self, naga, user_input, parent=None):
        super().__init__(naga, user_input, parent)
        self.streaming_buffer = ""
        
    async def process_with_progress(self):
        """流式处理优化版本"""
        start_time = time.time()
        
        try:
            self.status_changed.emit("连接到AI...")
            self.progress_updated.emit(15, "建立连接")
            
            if self.is_cancelled:
                return ""
            
            self.status_changed.emit("正在思考...")
            self.progress_updated.emit(30, "[夏园系统]:正在使用CPU推理")
            
            # 开始流式处理
            result_chunks = []
            word_count = 0
            
            async for chunk in self.naga.process(self.user_input):
                if self.is_cancelled:
                    break
                
                # 处理chunk - 不进行extract_message处理，直接累积原始内容
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    speaker, content = chunk
                    if speaker == "娜迦":
                        content_str = str(content)
                        result_chunks.append(content_str)
                        
                        # 发送流式数据到前端
                        self.stream_chunk.emit(content_str)
                        
                        # 发送文本到语音集成模块
                        if self.voice_integration:
                            try:
                                self.voice_integration.receive_text_chunk(content_str)
                            except Exception as e:
                                print(f"语音集成错误: {e}")
                        
                        # 更新缓冲区用于实时显示
                        self.streaming_buffer += content_str
                        word_count += len(content_str)
                else:
                    content_str = str(chunk)
                    result_chunks.append(content_str)
                    self.stream_chunk.emit(content_str)
                    
                    # 发送文本到语音集成模块
                    if self.voice_integration:
                        try:
                            self.voice_integration.receive_text_chunk(content_str)
                        except Exception as e:
                            print(f"语音集成错误: {e}")
                    
                    self.streaming_buffer += content_str
                    word_count += len(content_str)
                
                # 动态更新状态
                if word_count < 50:
                    status = "开始回复..."
                    progress = 35
                elif word_count < 200:
                    status = "正在详细解答..."
                    progress = 50
                elif word_count < 500:
                    status = "完善回答内容..."
                    progress = 70
                else:
                    status = "整理最终回复..."
                    progress = 85
                    
                self.progress_updated.emit(progress, f"{status} ({word_count}字)")
                
                # 短暂休眠让UI更新
                await asyncio.sleep(0.005)
            
            if not self.is_cancelled:
                # 发送最终完整文本到语音集成模块
                if self.voice_integration:
                    try:
                        final_text = ''.join(result_chunks)
                        self.voice_integration.receive_final_text(final_text)
                    except Exception as e:
                        print(f"语音集成错误: {e}")
                
                # 流式完成
                self.stream_complete.emit()
                
                elapsed = time.time() - start_time
                self.status_changed.emit(f"回复完成 (用时 {elapsed:.1f}s，{word_count}字)")
                self.progress_updated.emit(100, "完成")
                
                return ''.join(result_chunks)
            else:
                return ""
                
        except Exception as e:
            self.error_occurred.emit(f"流式处理错误: {str(e)}")
            raise


class BatchWorker(EnhancedWorker):
    """批量处理Worker，适用于一次性获取完整结果"""
    
    def __init__(self, naga, user_input, parent=None):
        super().__init__(naga, user_input, parent)
        self.thinking_time = 0
        
    async def process_with_progress(self):
        """批量处理优化版本"""
        start_time = time.time()
        
        try:
            # 模拟思考阶段
            self.status_changed.emit("深度思考中...")
            
            for i in range(20, 60, 5):
                if self.is_cancelled:
                    return ""
                self.progress_updated.emit(i, f"思考中... ({i-15}%)")
                await asyncio.sleep(0.1)
            
            # 收集所有结果
            result_chunks = []
            self.status_changed.emit("生成完整回复...")
            
            async for chunk in self.naga.process(self.user_input):
                if self.is_cancelled:
                    break
                    
                # 不进行extract_message处理，直接累积原始内容
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    speaker, content = chunk
                    if speaker == "娜迦":
                        result_chunks.append(str(content))
                else:
                    result_chunks.append(str(chunk))
            
            if not self.is_cancelled:
                # 发送最终完整文本到语音集成模块
                if self.voice_integration:
                    try:
                        final_text = ''.join(result_chunks)
                        self.voice_integration.receive_final_text(final_text)
                    except Exception as e:
                        print(f"语音集成错误: {e}")
                
                self.progress_updated.emit(90, "整理回复内容")
                await asyncio.sleep(0.2)  # 短暂等待，让用户看到进度
                
                elapsed = time.time() - start_time
                self.status_changed.emit(f"思考完成 (用时 {elapsed:.1f}s)")
                self.progress_updated.emit(100, "准备显示")
                
                return ''.join(result_chunks)
            else:
                return ""
                
        except Exception as e:
            self.error_occurred.emit(f"批量处理错误: {str(e)}")
            raise 