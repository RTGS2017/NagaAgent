#!/usr/bin/env python3
"""
LLM服务模块
提供统一的LLM调用接口，替代conversation_core.py中的get_response方法
使用 LiteLLM 统一处理多模型的 COT/reasoning_content
"""

import logging
import sys
import os
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import litellm
from litellm import acompletion
from fastapi import FastAPI, HTTPException
from system.config_value_utils import is_placeholder_api_key
from system.config import get_config
from . import naga_auth

# 配置日志
logger = logging.getLogger("LLMService")


@dataclass
class LLMResponse:
    """LLM响应结构，包含内容和推理过程"""

    content: str
    reasoning_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"content": self.content}
        if self.reasoning_content:
            result["reasoning_content"] = self.reasoning_content
        return result


class LLMService:
    """LLM服务类 - 使用 LiteLLM 提供统一的LLM调用接口，支持 COT/reasoning_content"""

    def __init__(self):
        self._initialized = False
        self._initialize_client()

    def _initialize_client(self):
        """初始化 LiteLLM 配置"""
        try:
            cfg = get_config()
            litellm.api_key = cfg.api.api_key
            # Anthropic 格式下不设置全局 api_base，由每次调用的参数传递
            # 避免全局 base 污染导致请求被路由到错误的端点
            if cfg.api.api_format != "anthropic":
                if cfg.api.base_url and "openai.com" not in cfg.api.base_url:
                    litellm.api_base = cfg.api.base_url.rstrip("/") + "/"
            self._initialized = True
            logger.info("LLM服务 (LiteLLM) 初始化成功")
        except Exception as e:
            logger.error(f"LLM服务初始化失败: {e}")
            self._initialized = False

    def _get_model_name(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """获取 LiteLLM 格式的模型名称

        Args:
            model: 模型名称，默认使用 config.api.model
            base_url: API地址，默认使用 config.api.base_url
        """
        cfg = get_config()
        model = model or cfg.api.model
        base_url = (base_url or cfg.api.base_url or "").lower()
        api_format = cfg.api.api_format
        provider_name = (provider or cfg.api.provider or "auto").lower()

        # NagaModel 网关：使用用户选择的模型名，由服务端路由
        # 需要 openai/ 前缀让 LiteLLM 识别为 OpenAI 兼容提供商
        if naga_auth.should_use_model_gateway():
            return f"openai/{model or 'default'}"

        # Anthropic 格式：使用 anthropic/ 前缀让 LiteLLM 走 Anthropic Messages API
        if api_format == "anthropic" or provider_name == "anthropic":
            if not model.startswith("anthropic/"):
                return f"anthropic/{model}"
            return model

        if provider_name == "gemini":
            if not model.startswith("gemini/"):
                return f"gemini/{model}"
            return model

        if provider_name == "openrouter":
            if not model.startswith("openrouter/"):
                return f"openrouter/{model}"
            return model

        if provider_name == "deepseek":
            if not model.startswith("deepseek/"):
                return f"deepseek/{model}"
            return model

        if provider_name == "openai":
            return model

        # OpenAI 格式：根据 base_url 判断提供商，添加正确的前缀
        if "deepseek" in base_url:
            if not model.startswith("deepseek/"):
                return f"deepseek/{model}"
        elif "openrouter" in base_url:
            if not model.startswith("openrouter/"):
                return f"openrouter/{model}"
        elif "openai.com" in base_url:
            return model
        else:
            if not model.startswith("openai/"):
                return f"openai/{model}"
        return model

    def _get_llm_params(self) -> Dict[str, Any]:
        """获取 LLM 调用参数，NagaModel 登录态时自动切换网关"""
        if naga_auth.should_use_model_gateway():
            token = naga_auth.get_access_token()
            return {
                "api_key": token,
                "api_base": naga_auth.NAGA_MODEL_URL + "/",
                "extra_body": {"user_token": token},
            }
        cfg = get_config()
        if cfg.api.api_format == "anthropic":
            params: Dict[str, Any] = {"api_key": cfg.api.api_key}
            if cfg.api.base_url and "anthropic.com" not in cfg.api.base_url:
                # LiteLLM 会自动追加 /v1/messages，不要加尾部 /
                params["api_base"] = cfg.api.base_url.rstrip("/")
            return params
        return {
            "api_key": cfg.api.api_key,
            "api_base": cfg.api.base_url.rstrip("/") + "/" if cfg.api.base_url else None,
        }

    def _get_overridden_llm_params(
        self, api_key: Optional[str] = None, api_base: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取 LLM 调用参数，支持覆写。NagaModel 登录态优先，否则使用覆写值"""
        if naga_auth.should_use_model_gateway():
            token = naga_auth.get_access_token()
            return {
                "api_key": token,
                "api_base": naga_auth.NAGA_MODEL_URL + "/",
                "extra_body": {"user_token": token},
            }
        cfg = get_config()
        effective_key = api_key or cfg.api.api_key
        effective_base = api_base or cfg.api.base_url
        if cfg.api.api_format == "anthropic" and not api_base:
            params: Dict[str, Any] = {"api_key": effective_key}
            if effective_base and "anthropic.com" not in effective_base:
                params["api_base"] = effective_base.rstrip("/")
            return params
        return {
            "api_key": effective_key,
            "api_base": (effective_base.rstrip("/") + "/" if effective_base else None),
        }

    def _local_api_config_error(self, llm_params: Dict[str, Any]) -> Optional[str]:
        """Return a user-facing configuration error for invalid local model settings."""
        if naga_auth.should_use_model_gateway():
            return None
        if is_placeholder_api_key(llm_params.get("api_key")):
            return "未配置本地模型 API 密钥：请填写真实 API Key，或登录后启用 NagaModel 网关。"
        return None

    def _supports_reasoning_replay(
        self,
        model_name: str,
        api_base: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bool:
        """DeepSeek Thinking Mode tool-call turns require replaying assistant reasoning_content."""
        combined = " ".join(
            str(part or "").lower()
            for part in (model_name, api_base, provider)
        )
        if "deepseek-reasoner" in combined:
            return False
        return "deepseek" in combined

    def _prepare_messages_for_model(
        self,
        messages: List[Dict[str, Any]],
        model_name: str,
        api_base: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Strip or retain reasoning_content according to the target model contract."""
        allow_reasoning_replay = self._supports_reasoning_replay(model_name, api_base, provider)
        prepared: List[Dict[str, Any]] = []
        for message in messages:
            item = dict(message)
            if "reasoning_content" in item:
                can_replay = (
                    allow_reasoning_replay
                    and item.get("role") == "assistant"
                    and bool(item.get("tool_calls"))
                )
                if not can_replay:
                    item.pop("reasoning_content", None)
            prepared.append(item)
        return prepared

    # 不支持自定义 temperature 的模型约束表: {前缀: 强制值}
    _TEMPERATURE_CONSTRAINTS: Dict[str, float] = {
        "gpt-5": 1,
    }

    def _normalize_temperature(self, model_name: str, temperature: Optional[float]) -> Optional[float]:
        """兼容不支持自定义 temperature 的模型参数约束。"""
        if temperature is None:
            return None

        normalized_model = (model_name or "").lower()
        for prefix, forced_value in self._TEMPERATURE_CONSTRAINTS.items():
            if normalized_model.startswith(prefix) and temperature != forced_value:
                logger.info(f"[LLM] 模型 {model_name} 仅支持 temperature={forced_value}，自动调整当前值 {temperature}")
                return forced_value

        return temperature

    async def get_response(self, prompt: str, temperature: float = 0.7) -> str:
        """为其他模块提供API调用接口（保持向后兼容，只返回 content）"""
        response = await self.get_response_with_reasoning(prompt, temperature)
        return response.content

    async def get_response_with_reasoning(self, prompt: str, temperature: float = 0.7) -> LLMResponse:
        """为其他模块提供API调用接口，返回包含 reasoning_content 的完整响应"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        try:
            model_name = self._get_model_name()
            llm_params = self._get_llm_params()
            config_error = self._local_api_config_error(llm_params)
            if config_error:
                return LLMResponse(content=config_error)
            response = await acompletion(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._normalize_temperature(model_name, temperature),
                max_tokens=get_config().api.max_tokens,
                **llm_params
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "", reasoning_content=getattr(message, "reasoning_content", None)
            )
        except Exception as e:
            logger.error(f"API调用失败: {e}")
            return LLMResponse(content=f"API调用出错: {str(e)}")

    def is_available(self) -> bool:
        """检查LLM服务是否可用"""
        return self._initialized

    async def chat_with_context(self, messages: List[Dict], temperature: float = 0.7) -> str:
        """带上下文的聊天调用（保持向后兼容，只返回 content）"""
        response = await self.chat_with_context_and_reasoning(messages, temperature)
        return response.content

    async def chat_with_context_and_reasoning_with_overrides(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        model_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        api_base_override: Optional[str] = None,
        provider_hint: Optional[str] = None,
    ) -> LLMResponse:
        """带上下文聊天（支持模型/网关覆写）"""
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                return LLMResponse(content="LLM服务不可用: 客户端初始化失败")

        final_model = model_override or get_config().api.model
        final_base = api_base_override or get_config().api.base_url
        final_api_key = api_key_override or get_config().api.api_key

        try:
            model_name = final_model
            if provider_hint and provider_hint != "openai":
                # gemini 等非 openai provider，加 LiteLLM 前缀
                if not model_name.startswith(f"{provider_hint}/"):
                    model_name = f"{provider_hint}/{model_name}"
            else:
                # openai 或未指定: 走原有 base_url 推断逻辑
                model_name = self._get_model_name(model_name, final_base, provider_hint)

            llm_params = self._get_overridden_llm_params(final_api_key, final_base)
            config_error = self._local_api_config_error(llm_params)
            if config_error:
                return LLMResponse(content=config_error)
            prepared_messages = self._prepare_messages_for_model(
                messages,
                model_name,
                final_base,
                provider_hint,
            )
            response = await acompletion(
                model=model_name,
                messages=prepared_messages,
                temperature=self._normalize_temperature(model_name, temperature),
                max_tokens=get_config().api.max_tokens if hasattr(get_config().api, 'max_tokens') else None,
                **llm_params
            )
            message = response.choices[0].message
            return LLMResponse(
                content=message.content or "", reasoning_content=getattr(message, "reasoning_content", None)
            )
        except Exception as e:
            logger.error(f"上下文聊天调用失败: {e}")
            return LLMResponse(content=f"聊天调用出错: {str(e)}")

    async def chat_with_context_and_reasoning(self, messages: List[Dict], temperature: float = 0.7) -> LLMResponse:
        """带上下文的聊天调用，返回包含 reasoning_content 的完整响应"""
        return await self.chat_with_context_and_reasoning_with_overrides(
            messages=messages,
            temperature=temperature,
            model_override=None,
            api_key_override=None,
            api_base_override=None,
        )

    async def stream_chat_with_context(self, messages: List[Dict], temperature: float = 0.7,
                                       model_override: Optional[Dict[str, str]] = None,
                                       tools: Optional[List[Dict]] = None):
        """带上下文的流式聊天调用，支持 reasoning_content 交织输出 + 原生 function calling

        Args:
            messages: 对话消息列表
            temperature: 生成温度
            model_override: 临时模型覆盖参数，用于切换到视觉模型等场景
                格式: {"model": "glm-4.5v", "api_base": "https://...", "api_key": "..."}
            tools: OpenAI function calling schemas（可选）

        Yields:
            格式为 "data: <json>\n\n" 的 SSE 事件
            JSON 结构: {"type": "content"|"reasoning"|"tool_calls_native", "text": "..."}
        """
        if not self._initialized:
            self._initialize_client()
            if not self._initialized:
                yield self._format_sse_chunk("content", "LLM服务不可用: 客户端初始化失败")
                return

        # 重试策略：最多 3 次
        #   - 401 AuthenticationError → 刷新 token 后重试（最多 1 次）
        #   - 连接错误 / 流中断  → 直接重试（最多 2 次）
        max_attempts = 3
        auth_retried = False

        for attempt in range(max_attempts):
            try:
                # 如果提供了 model_override，使用覆盖参数替代默认配置
                if model_override:
                    # NagaModel 登录态：只取 model 名，api_base/api_key 走网关
                    if naga_auth.should_use_model_gateway():
                        token = naga_auth.get_access_token()
                        model_name = self._get_model_name(
                            model=model_override.get("model"),
                            base_url=naga_auth.NAGA_MODEL_URL,
                        )
                        llm_params = {
                            "api_key": token,
                            "api_base": naga_auth.NAGA_MODEL_URL + "/",
                            "extra_body": {"user_token": token},
                        }
                    else:
                        override_base = model_override.get("api_base", "")
                        override_key = model_override.get("api_key", "")
                        model_name = self._get_model_name(
                            model=model_override.get("model"),
                            base_url=override_base,
                            provider=model_override.get("provider"),
                        )
                        llm_params = {
                            "api_key": override_key,
                            "api_base": override_base.rstrip("/") + "/" if override_base else None,
                        }
                    logger.info(f"使用覆盖模型: {model_name}, api_base: {llm_params.get('api_base')}")
                else:
                    llm_params = self._get_llm_params()
                    model_name = self._get_model_name()

                # 诊断日志：打印认证状态和 token 前缀
                _tk = naga_auth.get_access_token()
                logger.debug(f"[LLM] attempt={attempt} is_auth={naga_auth.is_authenticated()} "
                             f"token_prefix={_tk[:20] + '...' if _tk else 'None'} "
                             f"api_key_prefix={str(llm_params.get('api_key', ''))[:20]}... "
                             f"api_base={llm_params.get('api_base')}")

                config_error = self._local_api_config_error(llm_params)
                if config_error:
                    yield self._format_sse_chunk("content", config_error)
                    return

                prepared_messages = self._prepare_messages_for_model(
                    messages,
                    model_name,
                    str(llm_params.get("api_base") or ""),
                    model_override.get("provider") if model_override else get_config().api.provider,
                )
                call_params = {
                    "model": model_name,
                    "messages": prepared_messages,
                    "temperature": self._normalize_temperature(model_name, temperature),
                    "max_tokens": get_config().api.max_tokens if hasattr(get_config().api, "max_tokens") else None,
                    "stream": True,
                    "timeout": 120,
                    "stream_timeout": 120,
                    "num_retries": 0,
                    **llm_params
                }
                if tools:
                    call_params["tools"] = tools
                    if get_config().api.api_format != "anthropic":
                        call_params["parallel_tool_calls"] = True

                response = await acompletion(**call_params)

                # 累积器：tool_calls 增量拼接
                pending_tool_calls: Dict[int, Dict[str, str]] = {}  # {index: {id, name, arguments}}
                saw_content = False
                saw_reasoning = False
                final_finish_reason: Optional[str] = None

                async for chunk in response:
                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    final_finish_reason = getattr(choice, "finish_reason", None) or final_finish_reason
                    delta = choice.delta

                    # 处理 reasoning_content（思考过程）
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        saw_reasoning = True
                        yield self._format_sse_chunk("reasoning", reasoning)

                    # 处理 content（正式回答）
                    content = getattr(delta, "content", None)
                    if content:
                        saw_content = True
                        yield self._format_sse_chunk("content", content)

                    # 处理 tool_calls delta（原生 function calling）
                    tc_deltas = getattr(delta, "tool_calls", None)
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = tc.index
                            if idx not in pending_tool_calls:
                                pending_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                            if tc.id:
                                pending_tool_calls[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    pending_tool_calls[idx]["name"] = tc.function.name
                                if tc.function.arguments:
                                    pending_tool_calls[idx]["arguments"] += tc.function.arguments

                # 流结束后，如果有 tool_calls，yield 一个完整事件
                if pending_tool_calls:
                    import json
                    calls = [pending_tool_calls[i] for i in sorted(pending_tool_calls)]
                    yield self._format_sse_chunk("tool_calls_native", json.dumps(calls, ensure_ascii=False))

                if not saw_content and not saw_reasoning and not pending_tool_calls:
                    logger.warning(
                        "[LLM] 流式调用返回空响应: model=%s attempt=%s/%s finish_reason=%s",
                        model_name,
                        attempt + 1,
                        max_attempts,
                        final_finish_reason,
                    )
                    if attempt < max_attempts - 1:
                        continue
                    yield self._format_sse_chunk(
                        "content",
                        "模型服务返回空响应（无正文、无思考、无工具调用）。请稍后重试，或检查当前模型、API Key 与网关状态。",
                    )

                # 流式响应正常完成，跳出重试循环
                return

            except litellm.AuthenticationError as e:
                _tk = naga_auth.get_access_token()
                logger.error(f"LLM 401 诊断: attempt={attempt} is_auth={naga_auth.is_authenticated()} "
                             f"token={'set(' + _tk[:20] + '...)' if _tk else 'None'} "
                             f"has_refresh={naga_auth.has_refresh_token()}")
                if not auth_retried and naga_auth.is_authenticated():
                    auth_retried = True
                    logger.warning(f"LLM 调用 401，尝试刷新 token 后重试: {e}")
                    try:
                        result = await naga_auth.refresh()
                        new_token = result.get("access_token")
                        # 通过 SSE 推送新 token 给前端，避免前端旧 token 轮询覆盖后端新 token
                        if new_token:
                            yield self._format_sse_chunk("token_refreshed", new_token)
                        logger.info("Token 刷新成功，重试 LLM 调用")
                        continue  # 重试
                    except Exception as refresh_err:
                        logger.error(f"Token 刷新失败: {refresh_err}")
                # 刷新失败或已刷新过 → 通知前端触发重新登录
                logger.error(f"流式聊天认证失败: {e}")
                yield self._format_sse_chunk("auth_expired", "登录已过期，请重新登录")
                return

            except (litellm.APIConnectionError, litellm.ServiceUnavailableError, litellm.Timeout) as e:
                # 连接错误 / 流中断 / 超时 → 重试
                if attempt < max_attempts - 1:
                    logger.warning(f"[LLM] 流式调用连接异常 (attempt {attempt + 1}/{max_attempts})，重试中: {e}")
                    import asyncio
                    await asyncio.sleep(1)  # 短暂等待后重试
                    continue
                logger.error(f"[LLM] 流式调用连接异常，已耗尽重试次数: {e}")
                yield self._format_sse_chunk("content", f"流式调用出错（连接异常，已重试 {max_attempts} 次）: {str(e)}")
                return

            except Exception as e:
                logger.error(f"流式聊天调用失败: {e}")
                yield self._format_sse_chunk("content", f"流式调用出错: {str(e)}")
                return

    def _format_sse_chunk(self, chunk_type: str, text: str) -> str:
        """格式化 SSE 数据块

        Args:
            chunk_type: "content" 或 "reasoning"
            text: 文本内容

        Returns:
            SSE 格式的数据块
        """
        import json

        data = {"type": chunk_type, "text": text}
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# 全局LLM服务实例
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """获取全局LLM服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


# 创建独立的LLM服务API
llm_app = FastAPI(title="LLM Service API", description="LLM服务API", version="1.0.0")


@llm_app.post("/llm/chat")
async def llm_chat(request: Dict[str, Any]):
    """LLM聊天接口 - 为其他模块提供LLM调用服务"""
    try:
        prompt = request.get("prompt", "")
        temperature = request.get("temperature", 0.7)

        if not prompt:
            raise HTTPException(status_code=400, detail="prompt参数不能为空")

        llm_service = get_llm_service()
        response = await llm_service.get_response(prompt, temperature)

        return {"status": "success", "response": response, "temperature": temperature}

    except Exception as e:
        logger.error(f"LLM聊天接口异常: {e}")
        raise HTTPException(status_code=500, detail=f"LLM服务异常: {str(e)}")
