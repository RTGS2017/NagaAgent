from nagaagent_core.vendors.PyQt5.QtWidgets import QLabel
from ..utils.response_util import extract_message
from ui.utils.message_renderer import MessageRenderer
from ui.utils.simple_http_client import SimpleHttpClient, SimpleBatchClient
from system.config import config, AI_NAME, logger
from nagaagent_core.vendors.PyQt5.QtCore import QThread, QCoreApplication, Qt, QTimer, QMetaObject
import time
from typing import Dict, Optional


class ChatTool():
    def __init__(self, window):
        self.window = window
        self.current_response = ""  # 当前响应缓冲
        self.scroll_timer = QTimer(window)
        # 外部依赖
        self.chat_layout = window.chat_layout
        self.chat_scroll_area = window.chat_scroll_area
        self.progress_widget = window.progress_widget
        self.user_name = config.ui.user_name
        self.ai_name = AI_NAME
        self.streaming_mode = config.system.stream_mode

        # 消息管理
        self._messages: Dict[str, Dict] = {}  # 消息存储：ID -> 消息信息
        self.message_counter = 0  # 消息ID计数器

        # 流式处理状态
        self.current_message_id: Optional[str] = None  # 当前处理的消息ID
        self.current_response = ""  # 当前响应内容
        self.last_update_time = 0  # 上次UI更新时间（用于节流）

        # 打字机效果相关
        self.stream_typewriter_buffer = ""
        self.stream_typewriter_index = 0
        self.stream_typewriter_timer: Optional[QTimer] = None
        self.non_stream_timer: Optional[QTimer] = None
        self.non_stream_text = ""
        self.non_stream_index = 0
        self.non_stream_message_id = None

        self.current_ai_voice_message_id = None
        # HTTP客户端管理
        self.http_client = None

        # 工具调用状态
        self.in_tool_call_mode = False

    def adjust_input_height(self):
        window = self.window
        doc = window.input.document()
        h = int(doc.size().height()) + 10
        window.input.setFixedHeight(min(max(60, h), 150))  # 增加最小高度，与字体大小匹配
        window.input_wrap.setFixedHeight(window.input.height())

    def add_user_message(self, name, content, is_streaming=False):
        window = self.window
        """添加用户消息"""
        msg = extract_message(content)
        content_html = str(msg).replace('\n', '\n\n')#.replace('\n', '<br>')

        # 生成消息ID
        if not self.message_counter:
            self.message_counter = 0
        self.message_counter += 1
        message_id = f"msg_{self.message_counter}"

        # 初始化消息存储
        if self._messages:
            self._messages = {}

        # 存储消息信息
        self._messages[message_id] = {
            'name': name,
            'content': content_html,
            'full_content': content,
            'dialog_widget': None
        }

        # 使用消息渲染器创建对话框
        if name == "系统":
            message_dialog = MessageRenderer.create_system_message(name, content_html, window.chat_content)
        else:
            message_dialog = MessageRenderer.create_user_message(name, content_html, window.chat_content)

        # 存储对话框引用
        self._messages[message_id]['dialog_widget'] = message_dialog

        # 先移除stretch
        stretch_found = False
        stretch_index = -1
        for i in reversed(range(window.chat_layout.count())):
            item = window.chat_layout.itemAt(i)
            if item and not item.widget():  # 找到stretch
                window.chat_layout.removeItem(item)
                stretch_found = True
                stretch_index = i
                break

        # 添加消息
        window.chat_layout.addWidget(message_dialog)

        # 重新添加stretch到最后
        window.chat_layout.addStretch()

        # 滚动到底部
        self.smart_scroll_to_bottom()

        return message_id

    def on_send(self):
        # 1. 获取并验证用户输入
        user_input = self.window.input.toPlainText().strip()
        if not user_input:
            return

        # 2. 清理所有历史状态（合并关联的清理逻辑）
        self._cleanup_all_states()

        # 3. 显示用户消息并清空输入框
        self.add_user_message(config.ui.user_name, user_input)
        self.window.input.clear()

        # 4. 根据模式分发请求（核心分支逻辑）
        from .tool_game import game
        if game.self_game_enabled:
            self._send_self_game_request(user_input)
        else:
            if self.streaming_mode:
                self._send_stream_request(user_input)
            else:
                self._send_non_stream_request(user_input)

    def _cleanup_all_states(self):
        """合并：清理打字机、消息ID、运行中任务等所有状态"""
        # 清理非流式打字机
        if self.non_stream_timer and self.non_stream_timer.isActive():
            self.non_stream_timer.stop()
            self.non_stream_timer.deleteLater()
            if self.non_stream_text and self.non_stream_message_id:
                self.update_last_message(self.non_stream_text)
        # 重置非流式状态变量
        self.non_stream_timer = self.non_stream_text = self.non_stream_index = self.non_stream_message_id = None

        # 清理流式打字机
        if self.stream_typewriter_timer and self.stream_typewriter_timer.isActive():
            self.stream_typewriter_timer.stop()
            self.stream_typewriter_timer.deleteLater()
        self.stream_typewriter_timer = None  # 重置流式状态

        # 清理消息ID和响应缓冲
        self.current_message_id = self.current_ai_voice_message_id = None
        self.current_response = ""

        # 终止运行中的HTTP客户端
        if self.http_client and self.http_client.isRunning():
            self.cancel_current_task()
            self.http_client.deleteLater()
            self.http_client = None

    def _send_self_game_request(self, user_input):
        """博弈论模式（非流式）请求"""
        api_url = f"http://{config.api_server.host}:{config.api_server.port}/chat"
        data = self._build_request_data(user_input, stream=False, use_self_game=True)

        self.http_client = SimpleBatchClient(api_url, data)
        self._bind_batch_client_signals(self.http_client, "博弈论")
        self.progress_widget.set_thinking_mode()
        self.http_client.start()

    def _send_stream_request(self, user_input):
        """普通流式请求"""
        api_url = f"http://{config.api_server.host}:{config.api_server.port}/chat/stream"
        data = self._build_request_data(user_input, stream=True, use_self_game=False)

        self.http_client = SimpleHttpClient(api_url, data)
        self._bind_stream_client_signals(self.http_client)
        self.progress_widget.set_thinking_mode()
        self.http_client.start()

    def _send_non_stream_request(self, user_input):
        """普通非流式请求"""
        api_url = f"http://{config.api_server.host}:{config.api_server.port}/chat"
        data = self._build_request_data(user_input, stream=False, use_self_game=False)

        self.http_client = SimpleBatchClient(api_url, data)
        self._bind_batch_client_signals(self.http_client, "非流式")
        self.progress_widget.set_thinking_mode()
        self.http_client.start()

    # 保留必要的工具方法（未过度拆分）
    def _build_request_data(self, user_input, stream, use_self_game):
        """构建请求数据（复用逻辑）"""
        data = {"message": user_input, "stream": stream, "use_self_game": use_self_game}
        from system.config import config as _cfg
        if _cfg.system.voice_enabled and _cfg.voice_realtime.voice_mode in ["hybrid", "end2end"]:
            data["return_audio"] = True
        return data

    def _bind_batch_client_signals(self, client, error_prefix):
        """绑定批量HTTP客户端的信号"""
        client.status_changed.connect(lambda st: self.progress_widget.status_label.setText(st))
        client.error_occurred.connect(lambda err: (
            self.progress_widget.stop_loading(),
            self.add_user_message("系统", f"❌ {error_prefix}调用错误: {err}")
        ))
        client.response_received.connect(lambda text: (
            self.progress_widget.stop_loading(),
            self.start_non_stream_typewriter(text)
        ))
        
    def _bind_stream_client_signals(self, client):
        """绑定流式HTTP客户端的信号"""
        client.status_changed.connect(lambda st: self.progress_widget.status_label.setText(st))
        client.error_occurred.connect(lambda err: (
            self.progress_widget.stop_loading(),
            self.add_user_message("系统", f"❌ 流式调用错误: {err}")
        ))
        client.chunk_received.connect(self._handle_stream_chunk)
        client.response_complete.connect(self.finalize_streaming_response)

    def _handle_stream_chunk(self, text):
        """处理流式响应片段（文本已经由HTTP客户端解码）"""
        if text.startswith(('session_id: ', 'audio_url: ')):
            return
        self.append_response_chunk(text)

    def add_system_message(self, content: str) -> str:
        """添加系统消息到聊天界面"""
        msg = extract_message(content)
        content_html = str(msg)  # .replace('\\n', '\n').replace('\n', '<br>')

        # 生成消息ID
        self.message_counter += 1
        message_id = f"msg_{self.message_counter}"

        # 创建系统消息对话框
        parent_widget = self.chat_layout.parentWidget()
        message_dialog = MessageRenderer.create_system_message(
            "系统", content_html, parent_widget
        )

        # 存储消息信息
        self._messages[message_id] = {
            'name': "系统",
            'content': content_html,
            'full_content': content,
            'dialog_widget': message_dialog,
            'is_ai': False,
            'is_system': True
        }

        # 添加到布局
        self._remove_layout_stretch()
        self.chat_layout.addWidget(message_dialog)
        self.chat_layout.addStretch()

        # 滚动到底部
        self.smart_scroll_to_bottom()
        return message_id

    def add_ai_message(self, content: str = "") -> str:
        """添加AI消息到聊天界面（流式处理时初始化为空消息）"""
        msg = extract_message(content)
        content_html = str(msg)  # .replace('\\n', '\n').replace('\n', '<br>')

        # 生成消息ID
        self.message_counter += 1
        message_id = f"msg_{self.message_counter}"

        # 创建AI消息对话框
        parent_widget = self.chat_layout.parentWidget()
        message_dialog = MessageRenderer.create_assistant_message(
            self.ai_name, content_html, parent_widget
        )

        # 存储消息信息
        self._messages[message_id] = {
            'name': self.ai_name,
            'content': content_html,
            'full_content': content,
            'dialog_widget': message_dialog,
            'is_ai': True
        }

        # 添加到布局
        self._remove_layout_stretch()
        self.chat_layout.addWidget(message_dialog)
        self.chat_layout.addStretch()

        return message_id

    def update_last_message(self, new_text):
        """更新最后一条消息的内容"""
        line=new_text.count('\n')
        # 处理消息格式化
        msg = extract_message(new_text)
        from markdown import markdown
        content_html = str(msg).replace('\n', '<br>')
        content_html = markdown(content_html, extensions=['extra', 'codehilite'])

        # 优先使用当前消息ID（流式更新时设置的）
        message_id = None
        message_source = ""
        if self.current_message_id and self.current_message_id:
            message_id = self.current_message_id
            message_source = "text"
        elif self.current_ai_voice_message_id and self.current_ai_voice_message_id:
            message_id = self.current_ai_voice_message_id
            message_source = "voice"
        elif self._messages:
            # 如果没有当前消息ID，查找最后一个消息
            message_id = max(self._messages.keys(), key=lambda x: int(x.split('_')[-1]) if '_' in x else 0)
            message_source = "last"

        # 更新消息内容
        if message_id and message_id in self._messages:
            message_info = self._messages[message_id]

            # 更新存储的消息信息
            message_info['content'] = content_html
            message_info['full_content'] = new_text

            # 尝试使用MessageRenderer更新（更可靠）
            if 'dialog_widget' in message_info and message_info['dialog_widget']:
                try:
                    from ui.utils.message_renderer import MessageRenderer
                    MessageRenderer.update_message_content(message_info['dialog_widget'], content_html)
                except Exception as e:
                    # 如果MessageRenderer失败，使用备用方法
                    content_label = message_info['dialog_widget'].findChild(QLabel)
                    if content_label:
                        content_label.setText(content_html)
                        content_label.setTextFormat(1)  # Qt.RichText
                        content_label.setWordWrap(True)
            # 或者直接更新widget
            elif 'widget' in message_info:
                content_label = message_info['widget'].findChild(QLabel)
                if content_label:
                    # 使用HTML格式化的内容
                    content_label.setText(content_html)
                    # 确保标签可以正确显示HTML
                    content_label.setTextFormat(1)  # Qt.RichText
                    content_label.setWordWrap(True)

        # 自动滚动到底部，确保最新消息可见（使用智能滚动，不打扰正在查看历史的用户）
        self.smart_scroll_to_bottom()

    def clear_chat_history(self):
        """清除所有聊天历史"""
        # 清除UI组件
        for msg_id, msg_info in self._messages.items():
            if msg_info['dialog_widget']:
                msg_info['dialog_widget'].deleteLater()

        # 清除布局
        while self.chat_layout.count() > 0:
            item = self.chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # 重置状态
        self._messages.clear()
        self.message_counter = 0
        self.current_message_id = None
        self.current_response = ""

        # 恢复stretch
        self.chat_layout.addStretch()

    def load_persistent_history(self, max_messages: int = 20):
        """从持久化存储加载历史对话"""
        try:
            # 调用MessageRenderer加载历史
            ui_messages = MessageRenderer.load_persistent_context_to_ui(
                parent_widget=self.chat_layout.parentWidget(),
                max_messages=max_messages
            )

            if not ui_messages:
                logger.info("未加载到历史对话")
                return

            # 清空现有布局
            self._remove_layout_stretch()
            while self.chat_layout.count() > 0:
                item = self.chat_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            # 加载历史消息到UI和存储
            for message_id, message_info, dialog in ui_messages:
                self.chat_layout.addWidget(dialog)
                self._messages[message_id] = message_info
                self.message_counter = max(self.message_counter, int(message_id.split('_')[-1]))

            # 恢复stretch并滚动到底部
            self.chat_layout.addStretch()
            self.smart_scroll_to_bottom()
            logger.info(f"加载完成 {len(ui_messages)} 条历史对话")

        except Exception as e:
            logger.error(f"加载历史对话失败: {str(e)}")
            self.add_system_message(f"❌ 加载历史对话失败: {str(e)}")

        # ------------------------------
        # 工具调用处理
        # ------------------------------

    def handle_tool_call(self, notification: str):
        """处理工具调用通知"""
        # 标记进入工具调用模式
        self.in_tool_call_mode = True

        # 创建专门的工具调用内容对话框
        parent_widget = self.chat_layout.parentWidget()
        tool_call_dialog = MessageRenderer.create_tool_call_content_message(notification, parent_widget)

        # 设置嵌套对话框内容
        nested_title = "工具调用详情"
        nested_content = f"""
工具名称: {notification}
状态: 正在执行...
时间: {time.strftime('%H:%M:%S')}
        """.strip()
        tool_call_dialog.set_nested_content(nested_title, nested_content)

        # 生成消息ID
        self.message_counter += 1
        message_id = f"tool_call_{self.message_counter}"

        # 存储工具调用消息信息
        self._messages[message_id] = {
            'name': '工具调用',
            'content': notification,
            'full_content': notification,
            'dialog_widget': tool_call_dialog,
            'is_tool_call': True
        }

        # 添加到布局
        self._remove_layout_stretch()
        self.chat_layout.addWidget(tool_call_dialog)
        self.chat_layout.addStretch()

        # 滚动到底部
        self.smart_scroll_to_bottom()

        # 在状态栏显示工具调用状态
        self.progress_widget.status_label.setText(f"🔧 {notification}")
        logger.debug(f"工具调用: {notification}")

    def handle_tool_result(self, result: str):
        """处理工具执行结果"""
        # 查找最近的工具调用对话框并更新
        if self._messages:
            for message_id, message_info in reversed(list(self._messages.items())):
                if message_id.startswith('tool_call_'):
                    dialog_widget = message_info.get('dialog_widget')
                    if dialog_widget:
                        # 更新工具调用对话框显示结果
                        MessageRenderer.update_message_content(dialog_widget, f"✅ {result}")

                        # 更新嵌套对话框内容
                        if dialog_widget.set_nested_content:
                            nested_title = "工具调用结果"
                            nested_content = f"""
工具名称: {message_info.get('content', '未知工具')}
状态: 执行完成 ✅
时间: {time.strftime('%H:%M:%S')}
结果: {result[:200]}{'...' if len(result) > 200 else ''}
                            """.strip()
                            dialog_widget.set_nested_content(nested_title, nested_content)
                    break

        # 工具调用完成，退出工具调用模式
        self.in_tool_call_mode = False

        # 在状态栏显示工具执行结果
        self.progress_widget.status_label.setText(f"✅ {result[:50]}...")
        logger.debug(f"工具结果: {result}")

# 工具执行结果已通过LLM总结并保存到对话历史中
# UI可以通过查询历史获取工具执行结果

    # ------------------------------
    # 滚动控制
    # ------------------------------

    def smart_scroll_to_bottom(self):
        """智能滚动到底部（如果用户正在查看历史消息，则不滚动）"""
        # 如果不在 Qt 主线程，重新投递
        if QThread.currentThread() != QCoreApplication.instance().thread():
            logger.debug(
                f"不在qt线程。当前线程：{QThread.currentThread()} QT线程：{QCoreApplication.instance().thread()} ")
            QMetaObject.invokeMethod(self, "smart_scroll_to_bottom", Qt.QueuedConnection)
            return

        scrollbar = self.chat_scroll_area.verticalScrollBar()
        is_at_bottom = (scrollbar.value() >= (scrollbar.maximum() - 500))  # 修改距离阈值从1000改为500
        logger.debug(f"移动到末尾的距离检测：{is_at_bottom} 数值：{scrollbar.maximum() - scrollbar.value()} ")
        if is_at_bottom:
            def to_bottom():
                scrollbar.setValue(scrollbar.maximum())

            self.scroll_timer.singleShot(10, to_bottom)

    def _remove_layout_stretch(self):
        """移除布局中最后一个stretch"""
        for i in reversed(range(self.chat_layout.count())):
            item = self.chat_layout.itemAt(i)
            if item and not item.widget():  # 识别stretch/spacer
                self.chat_layout.removeItem(item)
                break

    # ------------------------------
    # 流式响应处理
    # ------------------------------


    def append_response_chunk(self, chunk: str):
        """追加响应片段（流式模式）- 实时显示到消息框"""
        # 检查是否为工具调用相关标记
        if any(marker in chunk for marker in ["[TOOL_CALL]", "[TOOL_START]", "[TOOL_RESULT]", "[TOOL_ERROR]"]):
            return

        logger.debug(f"收到chunk：{chunk}")

        # 检查是否在工具调用过程中
        if self.in_tool_call_mode:
            # 工具调用模式结束，创建新的消息框
            self.in_tool_call_mode = False
            self.current_message_id = None

        # 实时更新显示
        if not self.current_message_id:
            # 第一次收到chunk时，创建新消息
            self.current_message_id = self.add_ai_message(chunk)
            self.current_response = chunk
        else:
            # 后续chunk，追加到当前消息
            self.current_response += chunk
            #
            # # 限制更新频率（节流）
            # current_time = time.time()
            # # 每50毫秒更新一次UI，减少闪动
            # if current_time - self.last_update_time >= 0.05:
            self.update_last_message(self.current_response)
            # self.last_update_time = current_time

    def finalize_streaming_response(self):
        """完成流式响应处理"""
        if self.current_response:
            # 对累积的完整响应进行消息提取
            final_message = extract_message(self.current_response)

            # 更新最终消息
            if self.current_message_id:
                self.update_last_message(final_message)

        # 重置状态
        self.current_response = None
        self.current_message_id = None
        self.last_update_time = 0

        # 停止加载状态
        self.progress_widget.stop_loading()

    # ------------------------------
    # 打字机效果
    # ------------------------------

    def _start_stream_typewriter(self):
        """启动流式聊天的打字机效果"""
        if self.stream_typewriter_timer and self.stream_typewriter_timer.isActive():
            return

        self.stream_typewriter_timer = QTimer()
        self.stream_typewriter_timer.timeout.connect(self._stream_typewriter_tick)
        self.stream_typewriter_timer.start(100)  # 100ms一个字符

    def _stream_typewriter_tick(self):
        """流式聊天的打字机效果tick"""
        if self.stream_typewriter_index >= len(self.stream_typewriter_buffer):
            self._stop_stream_typewriter()
            return

        # 每次显示1-3个字符
        next_char = self.stream_typewriter_buffer[self.stream_typewriter_index]
        chars_to_add = 1

        # 如果是英文字符或空格，可以一次显示多个
        if next_char and ord(next_char) < 128:  # ASCII字符
            chars_to_add = min(3, len(self.stream_typewriter_buffer) - self.stream_typewriter_index)

        self.stream_typewriter_index += chars_to_add
        displayed_text = self.stream_typewriter_buffer[:self.stream_typewriter_index]

        # 更新消息显示
        self.update_last_message(displayed_text)

    def _stop_stream_typewriter(self):
        """停止流式打字机效果"""
        if self.stream_typewriter_timer and self.stream_typewriter_timer.isActive():
            self.stream_typewriter_timer.stop()
            self.stream_typewriter_timer.deleteLater()
            self.stream_typewriter_timer = None

    def start_non_stream_typewriter(self, full_text: str):
        """为非流式响应启动打字机效果"""
        # 创建空消息
        message_id = self.add_ai_message("")
        self.non_stream_message_id = message_id
        self.current_message_id = message_id  # 让update_last_message能找到这个消息

        # 初始化打字机变量
        self.non_stream_text = full_text
        self.non_stream_index = 0

        if not self.non_stream_timer:
            self.non_stream_timer = QTimer()
            self.non_stream_timer.timeout.connect(self._non_stream_typewriter_tick)

        # 启动定时器
        self.non_stream_timer.start(100)  # 100ms一个字符

    def _non_stream_typewriter_tick(self):
        """非流式响应的打字机效果tick"""
        if self.non_stream_index >= len(self.non_stream_text):
            # 所有字符都显示完了，停止定时器并清理
            self.non_stream_timer.stop()
            self.non_stream_timer.deleteLater()
            self.non_stream_timer = None

            # 清理临时变量
            self.non_stream_text = None
            self.non_stream_index = None
            self.non_stream_message_id = None
            self.current_message_id = None
            return

        # 每次显示1-3个字符
        next_char = self.non_stream_text[self.non_stream_index]
        chars_to_add = 1

        # 如果是英文字符或空格，可以一次显示多个
        if next_char and ord(next_char) < 128:  # ASCII字符
            chars_to_add = min(3, len(self.non_stream_text) - self.non_stream_index)

        self.non_stream_index += chars_to_add
        displayed_text = self.non_stream_text[:self.non_stream_index]

        # 更新消息显示
        self.update_last_message(displayed_text)


    def cancel_current_task(self):
        """取消当前任务"""
        # 停止所有打字机效果
        self._stop_stream_typewriter()

        if self.non_stream_timer and self.non_stream_timer.isActive():
            self.non_stream_timer.stop()
            self.non_stream_timer.deleteLater()
            self.non_stream_timer = None

            # 清理非流式打字机变量
            self.non_stream_text = None
            self.non_stream_index = None
            self.non_stream_message_id = None

        # 处理HTTP客户端
        if self.http_client and self.http_client.isRunning():
            # 立即设置取消标志
            self.http_client.cancel()

            # 非阻塞方式处理线程清理
            self.progress_widget.stop_loading()
            self.add_system_message("🚫 操作已取消")

            # 清空当前响应缓冲
            self.current_response = ""
            self.current_message_id = None

            # 使用QTimer延迟处理线程清理，避免UI卡顿
            QTimer.singleShot(50, self._cleanup_http_client)
        else:
            self.progress_widget.stop_loading()

    def _cleanup_http_client(self):
        """清理HTTP客户端资源"""
        if self.http_client:
            self.http_client.quit()
            if not self.http_client.wait(500):  # 只等待500ms
                self.http_client.terminate()
                self.http_client.wait(200)  # 再等待200ms
            self.http_client.deleteLater()
            self.http_client = None

    # ------------------------------
    # 属性访问器
    # ------------------------------

    @property
    def messages(self) -> Dict[str, Dict]:
        """获取所有消息"""
        return self._messages.copy()  # 返回副本，防止外部修改


from ..utils.lazy import lazy


@lazy
def chat():
    return ChatTool(config.window)