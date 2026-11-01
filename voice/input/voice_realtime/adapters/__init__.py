#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
适配器模块
包含各种语音服务提供商的适配器
"""

from importlib import import_module
from typing import Any

__all__ = [
    'QwenVoiceClientAdapter',
    'OpenAIVoiceClientAdapter',
    'LocalVoiceClientAdapter',
]

_ADAPTERS = {
    'QwenVoiceClientAdapter': '.qwen_adapter',
    'OpenAIVoiceClientAdapter': '.openai_adapter',
    'LocalVoiceClientAdapter': '.local',
}


def __getattr__(name: str) -> Any:
    if name not in _ADAPTERS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_ADAPTERS[name], __name__)
    return getattr(module, name)
