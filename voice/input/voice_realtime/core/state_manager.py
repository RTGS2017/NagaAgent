#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
状态管理器
管理语音对话的状态机
"""

import time
import threading
import logging
from enum import Enum
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """对话状态枚举"""
    IDLE = "idle"                  # 空闲状态
    LISTENING = "listening"        # 监听中
    USER_SPEAKING = "user_speaking"  # 用户说话中
    PROCESSING = "processing"      # 处理中
    AI_SPEAKING = "ai_speaking"    # AI说话中
    COOLDOWN = "cooldown"          # 冷却期
    ERROR = "error"               # 错误状态


class StateManager:
    """
    状态管理器
    管理对话的状态转换和时间控制
    """

    def __init__(
        self,
        min_user_interval: float = 2.0,
        cooldown_duration: float = 1.0,
        max_user_speech: float = 30.0,
        debug: bool = False
    ):
        """
        初始化状态管理器

        参数:
            min_user_interval: 用户输入最小间隔（秒）
            cooldown_duration: AI响应后冷却期（秒）
            max_user_speech: 用户最大说话时长（秒）
            debug: 是否启用调试模式
        """
        self.min_user_interval = min_user_interval
        self.cooldown_duration = cooldown_duration
        self.max_user_speech = max_user_speech
        self.debug = debug

        # 当前状态
        self.current_state = ConversationState.IDLE
        self.previous_state = ConversationState.IDLE

        # 时间戳记录
        self.timestamps = {
            'last_user_input': 0,
            'last_ai_output': 0,
            'user_speech_start': 0,
            'processing_start': 0,
            'state_change': 0
        }

        # 状态锁
        self.state_lock = threading.Lock()

        # 状态回调
        self.state_callbacks: Dict[ConversationState, list] = {
            state: [] for state in ConversationState
        }

        # 冷却期定时器
        self.cooldown_timer = None

        logger.info(f"StateManager initialized: min_interval={min_user_interval}s, "
                   f"cooldown={cooldown_duration}s, max_speech={max_user_speech}s")

    def transition_to(self, new_state: ConversationState) -> bool:
        """
        转换到新状态

        参数:
            new_state: 目标状态

        返回:
            bool: 转换是否成功
        """
        with self.state_lock:
            # 检查转换是否合法
            if not self._is_valid_transition(self.current_state, new_state):
                logger.warning(f"Invalid transition: {self.current_state} -> {new_state}")
                return False

            # 记录状态变化
            self.previous_state = self.current_state
            self.current_state = new_state
            self.timestamps['state_change'] = time.time()

            logger.info(f"State transition: {self.previous_state} -> {new_state}")

            # 触发状态回调
            self._trigger_state_callbacks(new_state)

            # 处理特殊状态
            if new_state == ConversationState.COOLDOWN:
                self._start_cooldown_timer()

            return True

    def _is_valid_transition(self, from_state: ConversationState, to_state: ConversationState) -> bool:
        """
        检查状态转换是否合法

        参数:
            from_state: 源状态
            to_state: 目标状态

        返回:
            bool: 是否合法
        """
        # 定义合法的状态转换
        valid_transitions = {
            ConversationState.IDLE: [
                ConversationState.LISTENING,
                ConversationState.ERROR
            ],
            ConversationState.LISTENING: [
                ConversationState.USER_SPEAKING,
                ConversationState.IDLE,
                ConversationState.ERROR
            ],
            ConversationState.USER_SPEAKING: [
                ConversationState.PROCESSING,
                ConversationState.LISTENING,
                ConversationState.ERROR
            ],
            ConversationState.PROCESSING: [
                ConversationState.AI_SPEAKING,
                ConversationState.LISTENING,
                ConversationState.ERROR
            ],
            ConversationState.AI_SPEAKING: [
                ConversationState.COOLDOWN,
                ConversationState.LISTENING,
                ConversationState.ERROR
            ],
            ConversationState.COOLDOWN: [
                ConversationState.LISTENING,
                ConversationState.IDLE,
                ConversationState.ERROR
            ],
            ConversationState.ERROR: [
                ConversationState.IDLE,
                ConversationState.LISTENING
            ]
        }

        # 允许转换到自身（刷新状态）
        if from_state == to_state:
            return True

        # 检查转换是否在允许列表中
        return to_state in valid_transitions.get(from_state, [])

    def _trigger_state_callbacks(self, state: ConversationState):
        """
        触发状态回调

        参数:
            state: 当前状态
        """
        callbacks = self.state_callbacks.get(state, [])
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in state callback for {state}: {e}")

    def _start_cooldown_timer(self):
        """启动冷却期定时器"""
        if self.cooldown_timer:
            self.cooldown_timer.cancel()

        def end_cooldown():
            if self.current_state == ConversationState.COOLDOWN:
                logger.info("Cooldown period ended")
                self.transition_to(ConversationState.LISTENING)

        self.cooldown_timer = threading.Timer(self.cooldown_duration, end_cooldown)
        self.cooldown_timer.daemon = True
        self.cooldown_timer.start()

        logger.info(f"Cooldown timer started: {self.cooldown_duration}s")

    def add_state_callback(self, state: ConversationState, callback: Callable[[], None]):
        """
        添加状态回调

        参数:
            state: 状态
            callback: 回调函数
        """
        if state in self.state_callbacks:
            self.state_callbacks[state].append(callback)
            logger.debug(f"Added callback for state {state}")

    def remove_state_callback(self, state: ConversationState, callback: Callable[[], None]):
        """
        移除状态回调

        参数:
            state: 状态
            callback: 回调函数
        """
        if state in self.state_callbacks and callback in self.state_callbacks[state]:
            self.state_callbacks[state].remove(callback)
            logger.debug(f"Removed callback for state {state}")

    def can_accept_user_input(self) -> bool:
        """
        检查是否可以接受用户输入

        返回:
            bool: 是否可以接受
        """
        # 只在监听状态接受输入
        if self.current_state != ConversationState.LISTENING:
            return False

        # 检查最小间隔
        time_since_last = time.time() - self.timestamps['last_user_input']
        if time_since_last < self.min_user_interval:
            return False

        return True

    def on_user_speech_detected(self) -> bool:
        """用户开始说话时调用"""
        if self.current_state == ConversationState.LISTENING:
            self.timestamps['user_speech_start'] = time.time()
            return self.transition_to(ConversationState.USER_SPEAKING)
        return False

    def on_user_speech_ended(self) -> bool:
        """用户停止说话时调用"""
        if self.current_state == ConversationState.USER_SPEAKING:
            self.timestamps['last_user_input'] = time.time()
            return self.transition_to(ConversationState.PROCESSING)
        return False

    def on_ai_response_started(self) -> bool:
        """AI开始响应时调用"""
        if self.current_state in [ConversationState.PROCESSING, ConversationState.LISTENING]:
            self.timestamps['processing_start'] = time.time()
            return self.transition_to(ConversationState.AI_SPEAKING)
        return False

    def on_ai_response_ended(self) -> bool:
        """AI响应结束时调用"""
        if self.current_state == ConversationState.AI_SPEAKING:
            self.timestamps['last_ai_output'] = time.time()
            return self.transition_to(ConversationState.COOLDOWN)
        return False

    def reset(self):
        """重置状态机"""
        with self.state_lock:
            if self.cooldown_timer:
                self.cooldown_timer.cancel()
                self.cooldown_timer = None

            self.current_state = ConversationState.IDLE
            self.previous_state = ConversationState.IDLE
            self.timestamps = {key: 0 for key in self.timestamps}

            logger.info("State machine reset")

    def get_status(self) -> Dict[str, Any]:
        """获取状态信息"""
        with self.state_lock:
            return {
                'current_state': self.current_state.value,
                'previous_state': self.previous_state.value,
                'timestamps': self.timestamps.copy(),
                'time_in_state': time.time() - self.timestamps['state_change']
            }

    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        for key, value in config.items():
            if hasattr(self, key):
                setattr(self, key, value)
                logger.debug(f"Updated config: {key}={value}")