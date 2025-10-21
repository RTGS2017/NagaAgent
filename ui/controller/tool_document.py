from nagaagent_core.vendors.PyQt5.QtWidgets import QFileDialog, QMessageBox, QDialog, QVBoxLayout, QLabel, QFrame, QPushButton  # 统一入口 #
from nagaagent_core.vendors.PyQt5.QtCore import Qt
from nagaagent_core.vendors.PyQt5.QtGui import QFont
from ..styles.button_factory import ButtonFactory
from pathlib import Path
from system.config import config, AI_NAME, logger
import os
import requests
import time
import shutil
from . import chat


class DocumentTool():
    def __init__(self, window):
        self.window = window
        self.progress_widget = window.progress_widget
    def upload_document(self):
        """上传文档功能"""
        try:
            # 打开文件选择对话框
            file_path, _ = QFileDialog.getOpenFileName(
                self.window,
                "选择要上传的文档",
                "",
                "支持的文档格式 (*.docx *.txt *.md);;Word文档 (*.docx);;文本文件 (*.txt);;Markdown文件 (*.md);;所有文件 (*)"
            )
            
            if not file_path:
                return  # 用户取消选择
            
            # 检查文件格式
            file_ext = Path(file_path).suffix.lower()
            supported_formats = ['.docx', '.txt', '.md']
            
            if file_ext not in supported_formats:
                QMessageBox.warning(self.window, "格式不支持", 
                                   f"不支持的文件格式: {file_ext}\n\n支持的格式: {', '.join(supported_formats)}")
                return
            
            # 检查文件大小 (限制为10MB)
            file_size = os.path.getsize(file_path)
            if file_size > 10 * 1024 * 1024:  # 10MB
                QMessageBox.warning(self.window, "文件过大", "文件大小不能超过10MB")
                return
            
            # 上传文件到API服务器
            self.upload_file_to_server(file_path)
            
        except Exception as e:
            QMessageBox.critical(self.window, "上传错误", f"文档上传失败:\n{str(e)}")
    
    def upload_file_to_server(self, file_path):
        """将文件上传到API服务器"""
        try:
            # 显示上传进度
            chat.add_user_message("系统", f"📤 正在上传文档: {Path(file_path).name}")
            self.progress_widget.set_thinking_mode()
            self.progress_widget.status_label.setText("上传文档中...")
            
            # 准备上传数据
            # 使用配置中的API服务器地址和端口
            api_url = f"http://{config.api_server.host}:{config.api_server.port}/upload/document"
            
            with open(file_path, 'rb') as f:
                files = {'file': (Path(file_path).name, f, 'application/octet-stream')}
                data = {'description': f'通过NAGA聊天界面上传的文档'}
                
                # 发送上传请求
                response = requests.post(api_url, files=files, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                self.progress_widget.stop_loading()
                chat.add_user_message("系统", f"✅ 文档上传成功: {result['filename']}")
                
                # 询问用户想要进行什么操作
                self.show_document_options(result['file_path'], result['filename'])
            else:
                self.progress_widget.stop_loading()
                chat.add_user_message("系统", f"❌ 上传失败: {response.text}")
                
        except requests.exceptions.ConnectionError:
            self.progress_widget.stop_loading()
            chat.add_user_message("系统", "❌ 无法连接到API服务器，请确保服务器正在运行")
        except Exception as e:
            self.progress_widget.stop_loading()
            chat.add_user_message("系统", f"❌ 上传失败: {str(e)}")
    
    def show_document_options(self, file_path, filename):
        """显示文档处理选项"""
        dialog = QDialog(self.window)
        dialog.setWindowTitle("文档处理选项")
        dialog.setFixedSize(650, 480)
        # 隐藏标题栏的图标按钮
        dialog.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
                border: 2px solid #ddd;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(20)
        
        # 标题
        title_label = QLabel("文档上传成功")
        title_font = QFont("Microsoft YaHei", 16, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 25px; padding: 15px; min-height: 40px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 文件信息
        info_label = QLabel(f"文件名: {filename}")
        info_label.setStyleSheet("color: #34495e; font-size: 14px; padding: 10px;")
        layout.addWidget(info_label)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #bdc3c7;")
        layout.addWidget(line)
        
        # 操作按钮
        actions = [
            ("📖 读取内容", "read", "读取文档的完整内容"),
            ("🔍 分析文档", "analyze", "分析文档结构和内容"),
            ("📝 生成摘要", "summarize", "生成文档的简洁摘要")
        ]
        
        for btn_text, action, description in actions:
            btn = ButtonFactory.create_document_action_button(btn_text)
            
            # 添加描述标签
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-bottom: 10px;")
            layout.addWidget(desc_label)
            layout.addWidget(btn)
            
            # 连接按钮事件
            btn.clicked.connect(lambda checked, f=file_path, a=action, d=dialog: self.process_document(f, a, d))
        
        # 取消按钮
        cancel_btn = ButtonFactory.create_cancel_button()
        cancel_btn.clicked.connect(dialog.close)
        layout.addWidget(cancel_btn)
        
        dialog.exec_()
    
    def process_document(self, file_path, action, dialog=None):
        """处理文档 - 整合文档处理逻辑"""
        if dialog:
            dialog.close()
        
        try:
            chat.add_user_message("系统", f"🔄 正在处理文档: {Path(file_path).name}")
            self.progress_widget.set_thinking_mode()
            self.progress_widget.status_label.setText("处理文档中...")
            
            # 直接处理文档，不通过API
            result = self._process_document_locally(file_path, action)
            
            self.progress_widget.stop_loading()
            
            if action == "read":
                chat.add_user_message(AI_NAME, f"📖 文档内容:\n\n{result['content']}")
            elif action == "analyze":
                chat.add_user_message(AI_NAME, f"🔍 文档分析:\n\n{result['analysis']}")
            elif action == "summarize":
                chat.add_user_message(AI_NAME, f"📝 文档摘要:\n\n{result['summary']}")
                
        except Exception as e:
            self.progress_widget.stop_loading()
            chat.add_user_message("系统", f"❌ 文档处理失败: {str(e)}")
    
    def _process_document_locally(self, file_path, action):
        """本地处理文档 - 整合apiserver中的文档处理逻辑"""
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                raise Exception(f"文件不存在: {file_path}")
            
            # 根据文件类型和操作类型处理文档
            if file_path.suffix.lower() == ".docx":
                # 使用Word MCP服务处理
                result = self._process_word_document(file_path, action)
            else:
                # 处理其他文件类型
                result = self._process_text_document(file_path, action)
            
            return result
            
        except Exception as e:
            raise Exception(f"文档处理失败: {str(e)}")
    
    def _process_word_document(self, file_path, action):
        """处理Word文档"""
        try:
            # 调用MCP服务处理Word文档
            mcp_request = {
                "query": f"处理Word文档: {file_path.name}",
                "tool_calls": [{
                    "service_name": "office_word_mcp",
                    "tool_name": "get_document_text",
                    "params": {"filename": str(file_path)},
                    "agentType": "mcp"
                }],
                "session_id": "document_processing",
                "callback_url": None  # 同步处理
            }
            
            # 调用MCP服务
            import httpx
            with httpx.Client() as client:
                response = client.post(
                    "http://localhost:8003/schedule",
                    json=mcp_request,
                    timeout=30.0
                )
                mcp_result = response.json()
            
            content = mcp_result.get("result", {}).get("result", "无法读取文档内容")
            
            if action == "read":
                return {"content": content}
            elif action == "analyze":
                # 让NAGA分析文档内容
                analysis_result = self._analyze_content_with_llm(content)
                return {"analysis": analysis_result}
            elif action == "summarize":
                # 让NAGA总结文档内容
                summary_result = self._summarize_content_with_llm(content)
                return {"summary": summary_result}
                
        except Exception as e:
            raise Exception(f"Word文档处理失败: {str(e)}")
    
    def _process_text_document(self, file_path, action):
        """处理文本文档"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if action == "read":
                return {"content": content}
            elif action == "analyze":
                # 让NAGA分析文档内容
                analysis_result = self._analyze_content_with_llm(content)
                return {"analysis": analysis_result}
            elif action == "summarize":
                # 让NAGA总结文档内容
                summary_result = self._summarize_content_with_llm(content)
                return {"summary": summary_result}
                
        except Exception as e:
            raise Exception(f"文本文档处理失败: {str(e)}")
    
    def _analyze_content_with_llm(self, content):
        """使用LLM分析内容"""
        try:
            # 调用LLM服务分析内容
            api_url = f"http://{config.api_server.host}:{config.api_server.port}/llm/chat"
            data = {
                "prompt": f"请分析以下文档内容，提供结构化的分析报告：\n\n{content}",
                "temperature": 0.7
            }
            
            response = requests.post(api_url, json=data, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "分析失败")
            else:
                return "LLM分析服务不可用"
                
        except Exception as e:
            return f"分析失败: {str(e)}"
    
    def _summarize_content_with_llm(self, content):
        """使用LLM总结内容"""
        try:
            # 调用LLM服务总结内容
            api_url = f"http://{config.api_server.host}:{config.api_server.port}/llm/chat"
            data = {
                "prompt": f"请总结以下文档内容，提供简洁的摘要：\n\n{content}",
                "temperature": 0.7
            }
            
            response = requests.post(api_url, json=data, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "总结失败")
            else:
                return "LLM总结服务不可用"
                
        except Exception as e:
            return f"总结失败: {str(e)}"
    
    def list_uploaded_documents(self):
        """获取已上传的文档列表 - 整合apiserver中的文档列表功能"""
        try:
            upload_dir = Path("uploaded_documents")
            if not upload_dir.exists():
                return {
                    "status": "success",
                    "documents": [],
                    "total": 0
                }
            
            documents = []
            for file_path in upload_dir.iterdir():
                if file_path.is_file():
                    stat = file_path.stat()
                    documents.append({
                        "filename": file_path.name,
                        "file_path": str(file_path),
                        "file_size": stat.st_size,
                        "file_type": file_path.suffix.lower(),
                        "upload_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                    })
            
            # 按上传时间排序
            documents.sort(key=lambda x: x["upload_time"], reverse=True)
            
            return {
                "status": "success",
                "documents": documents,
                "total": len(documents)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"获取文档列表失败: {str(e)}"
            }
    
from ..utils.lazy import lazy
@lazy
def document():
    return DocumentTool(config.window)