#!/usr/bin/env python3
"""
简化的HTTP客户端 - 只负责与apiserver通信
UI层不应该处理复杂的业务逻辑，只负责显示结果
"""

from nagaagent_core.vendors.PyQt5.QtCore import QThread, pyqtSignal
import requests
import base64
import json
from system.config import config, logger


class SimpleHttpClient(QThread):
    """简化的HTTP客户端 - 只负责与apiserver通信"""
    
    # 信号定义
    chunk_received = pyqtSignal(str)  # 接收到文本块
    response_complete = pyqtSignal(str)  # 响应完成
    error_occurred = pyqtSignal(str)  # 发生错误
    status_changed = pyqtSignal(str)  # 状态变化
    
    def __init__(self, url, payload, parent=None):
        super().__init__(parent)
        self.url = url
        self.payload = payload
        self._cancelled = False
        self.last_session_id = None  # 保存从服务器返回的会话ID
        
    def cancel(self):
        """取消请求"""
        self._cancelled = True
        
    def run(self):
        """执行HTTP请求"""
        try:
            self.status_changed.emit("连接到服务器...")
            
            # 配置请求
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'text/event-stream',
                'Connection': 'keep-alive'
            }
            
            # 发送请求
            response = requests.post(
                self.url,
                json=self.payload,
                headers=headers,
                stream=True,
                timeout=(30, 120)
            )
            
            if response.status_code != 200:
                self.error_occurred.emit(f"请求失败: HTTP {response.status_code}")
                return
                
            self.status_changed.emit("正在接收响应...")
            
            # 处理流式响应
            complete_text = ""
            for line in response.iter_lines(decode_unicode=False):
                if self._cancelled:
                    break
                    
                if line:
                    try:
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str == '[DONE]':
                                break
                            elif data_str.startswith('session_id: '):
                                # 保存会话ID
                                self.last_session_id = data_str[len('session_id: '):].strip()
                                continue
                            elif data_str.startswith('audio_url: '):
                                continue  # 忽略音频URL，由apiserver处理
                            else:
                                # 解码base64内容
                                try:
                                    decoded = base64.b64decode(data_str).decode('utf-8')
                                    complete_text += decoded
                                    self.chunk_received.emit(decoded)
                                except:
                                    # 如果不是base64，直接使用原始内容
                                    complete_text += data_str
                                    self.chunk_received.emit(data_str)
                    except Exception as e:
                        logger.warning(f"处理响应行时出错: {e}")
                        continue
                        
            if not self._cancelled:
                self.response_complete.emit(complete_text)
                
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"网络错误: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"未知错误: {str(e)}")
            logger.exception("HTTP客户端错误")


class SimpleBatchClient(QThread):
    """简化的批量HTTP客户端"""
    
    # 信号定义
    response_received = pyqtSignal(str)  # 接收到完整响应
    error_occurred = pyqtSignal(str)  # 发生错误
    status_changed = pyqtSignal(str)  # 状态变化
    
    def __init__(self, url, payload, parent=None):
        super().__init__(parent)
        self.url = url
        self.payload = payload
        self._cancelled = False
        self.last_session_id = None  # 保存从服务器返回的会话ID
        
    def cancel(self):
        """取消请求"""
        self._cancelled = True
        
    def run(self):
        """执行HTTP请求"""
        try:
            self.status_changed.emit("正在处理...")
            
            # 发送请求
            response = requests.post(
                self.url,
                json=self.payload,
                timeout=120
            )
            
            if response.status_code != 200:
                self.error_occurred.emit(f"请求失败: HTTP {response.status_code}")
                return
                
            # 解析响应
            try:
                result = response.json()
                response_text = result.get("response", "")
                # 保存会话ID
                self.last_session_id = result.get("session_id")
            except:
                response_text = response.text
                
            if not self._cancelled:
                self.response_received.emit(response_text)
                
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"网络错误: {str(e)}")
        except Exception as e:
            self.error_occurred.emit(f"未知错误: {str(e)}")
            logger.exception("批量HTTP客户端错误")
