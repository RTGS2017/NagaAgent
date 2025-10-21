#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live2D Widget（精简版）
基于QOpenGLWidget的Live2D显示组件
"""

import logging
from typing import Optional, Callable
from nagaagent_core.vendors.PyQt5.QtWidgets import QOpenGLWidget
from nagaagent_core.vendors.PyQt5.QtCore import Qt, QTimer, pyqtSignal
from nagaagent_core.vendors.PyQt5.QtGui import QMouseEvent

from .renderer import Live2DRenderer, RendererState
from .animator import Live2DAnimator
from .config_manager import get_config

logger = logging.getLogger("live2d.widget")


class Live2DWidget(QOpenGLWidget):
    """Live2D显示Widget（精简版）"""

    # 信号定义
    model_loaded = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)
    gl_initialized = pyqtSignal(bool)

    def __init__(self, parent=None, target_fps: int = 60, scale_factor: float = 1.0):
        """
        初始化Live2D Widget

        参数:
            parent: 父Widget
            target_fps: 目标帧率
            scale_factor: 模型缩放因子
        """
        super().__init__(parent)

        # 基本设置
        self.scale_factor = scale_factor
        self.target_fps = max(30, min(120, target_fps))

        # 渲染器和动画器
        self.renderer = Live2DRenderer(scale_factor=scale_factor)
        self.animator: Optional[Live2DAnimator] = None

        # 定时器
        self.render_timer: Optional[QTimer] = None

        # 延迟加载标志
        self._pending_load_model: Optional[str] = None
        self._pending_load_callback: Optional[Callable[[float], None]] = None

        # 错误处理相关
        self._error_count = 0
        self._max_errors = 5
        self._consecutive_frame_errors = 0
        self._max_consecutive_errors = 10
        self._fallback_mode = False
        self._last_error_time = 0

        # Widget属性
        self.setMinimumSize(100, 150)
        self.setStyleSheet('background: transparent; border: none;')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        logger.debug(f"Live2D Widget创建，FPS: {self.target_fps}")

    def initializeGL(self):
        """初始化OpenGL上下文"""
        try:
            if self.renderer.initialize():
                # 创建动画器
                self.animator = Live2DAnimator(self.renderer)
                logger.debug("OpenGL初始化成功")
                self.gl_initialized.emit(True)

                # 检查是否有待加载的模型
                if self._pending_load_model:
                    logger.debug(f"发现待加载模型: {self._pending_load_model}")
                    QTimer.singleShot(100, self.update)
            else:
                self._handle_init_error("初始化失败")

        except Exception as e:
            self._handle_init_error(str(e))

    def _handle_init_error(self, error_msg: str):
        """处理初始化错误"""
        logger.error(f"OpenGL初始化失败: {error_msg}")
        self.error_occurred.emit(error_msg)
        self.gl_initialized.emit(False)

    def load_model(self, model_path: str, progress_callback: Optional[Callable[[float], None]] = None) -> bool:
        """加载Live2D模型"""
        # 如果渲染器还未初始化，保存请求等待初始化完成
        if self.renderer.state == RendererState.UNINITIALIZED:
            logger.debug("渲染器未初始化，保存模型加载请求")
            self._pending_load_model = model_path
            self._pending_load_callback = progress_callback
            # 如果Widget已经显示，触发更新以初始化OpenGL
            if self.isVisible():
                self.update()
            return True

        # 检查渲染器是否可用
        if not self.renderer.is_available():
            error_msg = self.renderer.get_error_reason() if hasattr(self.renderer, 'get_error_reason') else "渲染器不可用"
            logger.error(f"渲染器不可用: {error_msg}")
            self.error_occurred.emit(error_msg)
            self.model_loaded.emit(False)
            return False

        # 保存加载请求，在paintGL中执行
        self._pending_load_model = model_path
        self._pending_load_callback = progress_callback
        self.update()
        return True

    def paintGL(self):
        """绘制Live2D模型"""
        # 检查待加载的模型
        if self._pending_load_model:
            model_path = self._pending_load_model
            callback = self._pending_load_callback

            # 清除加载请求
            self._pending_load_model = None
            self._pending_load_callback = None

            # 加载模型
            success = self.renderer.load_model(model_path, callback)

            if success:
                self._start_render_timer()
                self.model_loaded.emit(True)
                logger.debug(f"模型加载成功: {model_path}")
            else:
                self.model_loaded.emit(False)
                self.error_occurred.emit(f"模型加载失败: {model_path}")
                logger.error(f"模型加载失败: {model_path}")
                return

        # 正常渲染
        if self.renderer and self.renderer.has_model():
            try:
                self.renderer.update()
                self.renderer.draw()
            except Exception as e:
                logger.error(f"绘制失败: {e}")

    def resizeGL(self, width: int, height: int):
        """调整OpenGL视口大小"""
        if self.renderer:
            try:
                self.renderer.resize(width, height)
            except Exception as e:
                logger.error(f"视口调整失败: {e}")

    def _start_render_timer(self):
        """启动渲染定时器"""
        if not self.render_timer:
            self.render_timer = QTimer(self)
            self.render_timer.timeout.connect(self._update_frame)

        interval = int(1000 / self.target_fps)
        self.render_timer.start(interval)

    def _update_frame(self):
        """更新帧 - 带错误恢复机制"""
        if not self.renderer.has_model() or self._fallback_mode:
            return

        try:
            if self.animator:
                self.animator.update()
            self.update()

            # 成功更新，重置连续错误计数
            if self._consecutive_frame_errors > 0:
                self._consecutive_frame_errors = 0
                logger.debug("Live2D恢复正常渲染")

        except Exception as e:
            self._consecutive_frame_errors += 1
            self._error_count += 1

            # 记录错误但不频繁输出
            import time
            current_time = time.time()
            if current_time - self._last_error_time > 5:  # 5秒内只记录一次
                logger.error(f"帧更新失败 (连续错误: {self._consecutive_frame_errors}): {e}")
                self._last_error_time = current_time

            # 检查是否需要进入降级模式
            if self._consecutive_frame_errors >= self._max_consecutive_errors:
                self._enter_fallback_mode()

    def _enter_fallback_mode(self):
        """进入降级模式"""
        self._fallback_mode = True
        logger.warning("Live2D进入降级模式，停止动画渲染")

        # 停止渲染定时器
        if self.render_timer:
            self.render_timer.stop()

        # 发送错误信号
        self.error_occurred.emit("Live2D渲染出现持续错误，已进入降级模式")

        # 尝试在5秒后恢复
        QTimer.singleShot(5000, self._try_recover)

    def _try_recover(self):
        """尝试从降级模式恢复"""
        if not self._fallback_mode:
            return

        logger.debug("尝试从降级模式恢复...")
        self._fallback_mode = False
        self._consecutive_frame_errors = 0

        # 重置动画器缓存
        if self.animator and hasattr(self.animator, 'reset_cache'):
            self.animator.reset_cache()

        # 重启渲染定时器
        if self.render_timer and self.renderer.has_model():
            self._start_render_timer()
            logger.debug("Live2D已从降级模式恢复")

    def set_emotion(self, emotion: str, intensity: float = 1.0):
        """设置情绪"""
        if self.animator:
            self.animator.set_emotion(emotion, intensity)

    def set_eye_target(self, x: float, y: float):
        """设置眼球跟踪目标"""
        if self.animator:
            self.animator.set_eye_target(x, y)

    def trigger_motion(self, group: str, index: int = 0, priority: int = 3):
        """触发动作"""
        if self.renderer:
            self.renderer.trigger_motion(group, index, priority)

    def trigger_expression(self, expression_id: str):
        """触发表情"""
        if self.renderer:
            self.renderer.trigger_expression(expression_id)

    def set_scale_factor(self, scale_factor: float):
        """设置模型缩放因子"""
        self.scale_factor = max(0.5, min(3.0, scale_factor))
        if self.renderer:
            self.renderer.set_scale_factor(self.scale_factor)
            self.update()

    def is_model_loaded(self) -> bool:
        """检查是否已加载模型"""
        return self.renderer and self.renderer.has_model()

    def cleanup(self):
        """清理资源"""
        try:
            if self.render_timer:
                self.render_timer.stop()
                self.render_timer = None

            if self.animator:
                self.animator.cleanup()
                self.animator = None

            if self.renderer:
                self.renderer.cleanup()

            logger.debug("Live2D Widget资源已清理")
        except Exception as e:
            logger.error(f"资源清理失败: {e}")

    # 鼠标事件处理
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton and self.is_model_loaded():
            # 触发简单动作
            import random
            actions = ["tap_body", "tap_head"]
            self.trigger_motion(random.choice(actions), 0)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """鼠标释放事件"""
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动事件（眼球跟踪）"""
        if self.is_model_loaded():
            # 转换坐标
            x = (event.x() / self.width()) * 2.0 - 1.0
            y = -((event.y() / self.height()) * 2.0 - 1.0)
            self.set_eye_target(x, y)

        super().mouseMoveEvent(event)


def create_widget_from_config(parent=None, config=None):
    """从配置创建Widget"""
    if config is None:
        config = get_config()

    # 基本配置
    target_fps = 60
    scale_factor = 1.0

    if config and config.performance:
        target_fps = getattr(config.performance, 'target_fps', 60)

    if config and config.model:
        scale_factor = getattr(config.model, 'scale_factor', 1.0)

    widget = Live2DWidget(
        parent=parent,
        target_fps=target_fps,
        scale_factor=scale_factor
    )

    logger.debug(f"从配置创建Widget，FPS: {target_fps}, 缩放: {scale_factor}")
    return widget