#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
语音客户端工厂
统一管理所有语音服务提供商的客户端创建
"""

from dataclasses import dataclass
from importlib import import_module
from typing import Dict, Type, Optional, Union
import logging

from .base_client import BaseVoiceClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _LazyProvider:
    """延迟加载语音适配器，避免可选依赖阻塞普通导入。"""

    module_path: str
    class_name: str


ProviderEntry = Union[Type[BaseVoiceClient], _LazyProvider]


class VoiceClientFactory:
    """
    语音客户端工厂类
    支持通过配置动态创建不同提供商的客户端
    """

    # 注册的客户端类型
    _registry: Dict[str, ProviderEntry] = {}

    @classmethod
    def register(cls, provider_name: str, client_class: Type[BaseVoiceClient]):
        """
        注册新的客户端类型

        参数:
            provider_name: 提供商名称（如 'qwen', 'openai', 'azure'）
            client_class: 客户端类（必须继承自 BaseVoiceClient）

        示例:
            VoiceClientFactory.register('qwen', QwenVoiceClientAdapter)
            VoiceClientFactory.register('openai', OpenAIVoiceClientAdapter)
        """
        if not issubclass(client_class, BaseVoiceClient):
            raise TypeError(f"{client_class} must inherit from BaseVoiceClient")

        cls._registry[provider_name.lower()] = client_class
        logger.info(f"Registered voice client provider: {provider_name}")

    @classmethod
    def register_lazy(cls, provider_name: str, module_path: str, class_name: str) -> None:
        """
        注册延迟加载的客户端类型。

        参数:
            provider_name: 提供商名称
            module_path: 适配器模块路径
            class_name: 模块中的客户端类名
        """
        cls._registry[provider_name.lower()] = _LazyProvider(module_path=module_path, class_name=class_name)
        logger.info(f"Registered lazy voice client provider: {provider_name}")

    @classmethod
    def _resolve_client_class(cls, provider_key: str) -> Type[BaseVoiceClient]:
        entry = cls._registry[provider_key]
        if isinstance(entry, type):
            return entry

        try:
            module = import_module(entry.module_path)
            client_class = getattr(module, entry.class_name)
        except ImportError as exc:
            raise ImportError(
                f"语音提供商 '{provider_key}' 的可选依赖未安装或不可用: {exc}"
            ) from exc

        if not isinstance(client_class, type) or not issubclass(client_class, BaseVoiceClient):
            raise TypeError(f"{entry.module_path}.{entry.class_name} must inherit from BaseVoiceClient")

        cls._registry[provider_key] = client_class
        return client_class

    @classmethod
    def create(
        cls,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        debug: bool = False,
        **kwargs
    ) -> BaseVoiceClient:
        """
        创建客户端实例

        参数:
            provider: 提供商名称（如 'qwen', 'openai', 'azure'）
            api_key: API密钥
            model: 模型名称（可选，使用提供商默认值）
            voice: 语音角色（可选，使用提供商默认值）
            debug: 是否启用调试模式
            **kwargs: 其他提供商特定参数

        返回:
            BaseVoiceClient: 客户端实例

        抛出:
            ValueError: 如果提供商未注册

        示例:
            client = VoiceClientFactory.create(
                provider='qwen',
                api_key='sk-xxx',
                model='qwen3-omni-flash-realtime',
                voice='Cherry'
            )
        """
        provider_key = provider.lower()

        if provider_key not in cls._registry:
            available = ', '.join(cls._registry.keys())
            raise ValueError(
                f"Unknown voice provider: {provider}. "
                f"Available providers: {available}"
            )

        client_class = cls._resolve_client_class(provider_key)
        logger.info(f"Creating {provider} voice client")

        # 准备参数
        init_kwargs = {
            'api_key': api_key,
            'debug': debug,
            **kwargs
        }

        # 添加可选参数
        if model:
            init_kwargs['model'] = model
        if voice:
            init_kwargs['voice'] = voice

        # 创建实例
        try:
            client = client_class(**init_kwargs)
            logger.info(f"{provider} voice client created successfully")
            return client
        except Exception as e:
            logger.error(f"Failed to create {provider} client: {e}")
            raise

    @classmethod
    def get_available_providers(cls) -> list:
        """
        获取所有已注册的提供商列表

        返回:
            list: 提供商名称列表
        """
        return list(cls._registry.keys())

    @classmethod
    def is_provider_available(cls, provider: str) -> bool:
        """
        检查提供商是否已注册

        参数:
            provider: 提供商名称

        返回:
            bool: 是否可用
        """
        return provider.lower() in cls._registry

    @classmethod
    def unregister(cls, provider_name: str) -> bool:
        """
        注销客户端类型

        参数:
            provider_name: 提供商名称

        返回:
            bool: 是否成功注销
        """
        provider_key = provider_name.lower()
        if provider_key in cls._registry:
            del cls._registry[provider_key]
            logger.info(f"Unregistered voice client provider: {provider_name}")
            return True
        return False


# 全局单例管理
_global_clients: Dict[str, BaseVoiceClient] = {}


def get_voice_client(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    debug: bool = False,
    use_singleton: bool = True,
    **kwargs
) -> BaseVoiceClient:
    """
    获取语音客户端实例（支持单例模式）

    参数:
        provider: 提供商名称
        api_key: API密钥
        model: 模型名称（可选）
        voice: 语音角色（可选）
        debug: 是否启用调试模式
        use_singleton: 是否使用单例模式（默认True）
        **kwargs: 其他参数

    返回:
        BaseVoiceClient: 客户端实例

    示例:
        # 获取通义千问客户端（单例）
        client = get_voice_client('qwen', api_key='sk-xxx', model='qwen3-omni-flash-realtime')

        # 创建新的OpenAI客户端实例
        client = get_voice_client('openai', api_key='sk-xxx', model='gpt-4o-realtime', use_singleton=False)
    """
    if use_singleton:
        key = f"{provider}:{model or 'default'}"
        if key not in _global_clients:
            _global_clients[key] = VoiceClientFactory.create(
                provider=provider,
                api_key=api_key,
                model=model,
                voice=voice,
                debug=debug,
                **kwargs
            )
        return _global_clients[key]
    else:
        return VoiceClientFactory.create(
            provider=provider,
            api_key=api_key,
            model=model,
            voice=voice,
            debug=debug,
            **kwargs
        )


def reset_global_clients():
    """重置所有全局客户端实例"""
    global _global_clients
    for client in _global_clients.values():
        try:
            if client.is_active():
                client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")
    _global_clients.clear()
    logger.info("All global voice clients have been reset")
