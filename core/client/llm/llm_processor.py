"""
LLM 处理引擎

功能：
1. 执行 LLM API 调用
2. 处理流式输出
3. 统一的错误处理和包装
4. 精确的生成时间统计（从第一个 token 开始）
"""
import time
import traceback
from typing import Dict, Any, List, Tuple
from .llm_config_schema import LLMConfig
from .llm_client_pool import ClientPool
from .llm_constants import estimate_tokens
from .llm_exceptions import (
    APIException,
    wrap_openai_error, OpenAIErrorWrapper,
    TimeoutErrorWrapper
)
from . import logger


class LLMProcessor:
    """LLM 处理引擎 - 负责 API 调用和流式输出"""

    def __init__(self, client_pool: ClientPool):
        """
        Args:
            client_pool: 客户端池
        """
        self.client_pool = client_pool

    def process(
        self,
        role_config: LLMConfig,
        messages: List[Dict[str, str]],
    ) -> Tuple[str, int, float]:
        """
        执行 LLM 处理

        Args:
            role_config: 单一 LLM 配置
            messages: 消息列表

        Returns:
            (处理后的文本, 输出token数, 生成时间秒)
        """
        logger.info(f"开始 LLM 处理，模型: {role_config.model}")

        # 获取客户端
        logger.debug(f"获取 LLM 客户端，API: {role_config.api_url}")
        client = self.client_pool.get_client(
            api_url=role_config.api_url,
            api_key=role_config.api_key
        )

        try:
            return self._stream_request(
                client,
                role_config,
                messages
            )

        except OpenAIErrorWrapper:
            raise
        except Exception as e:
            if isinstance(e, APIException):
                raise

            # 捕获 OpenAI SDK 原生异常并包装
            import openai

            # 处理 httpx 超时异常（在流式读取时发生）
            if 'httpx' in str(type(e).__module__):
                error_type = type(e).__name__
                if 'Timeout' in error_type or 'timeout' in error_type:
                    # httpx.ReadTimeout 或 httpx.TimeoutException
                    wrapped_error = TimeoutErrorWrapper(e, 'qwen')
                    logger.error(f"LLM API 请求超时: {wrapped_error}")
                    raise wrapped_error from e

            if isinstance(e, (
                openai.AuthenticationError,
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.APIConnectionError,
                openai.APIError
            )):
                wrapped_error = wrap_openai_error(e, 'qwen')
                logger.error(f"LLM API 调用失败: {wrapped_error}")
                raise wrapped_error from e

            # 其他未预期的异常，包装为 APIException 并抛出
            error_msg = f"LLM 处理失败: {e}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            raise APIException(error_msg, 'qwen') from e

    def _build_request_params(
        self,
        role_config: LLMConfig,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """统一构建请求参数"""
        return {
            'model': role_config.model,
            'messages': messages,
            'temperature': 0.3,
            'top_p': 0.8,
            'max_tokens': 4096,
        }

    def _stream_request(
        self,
        client: Any,
        role_config: LLMConfig,
        messages: List[Dict[str, str]]
    ) -> Tuple[str, int, float]:
        """执行流式请求并协调不同处理引擎"""

        result = self._process_openai_stream(client, role_config, messages)

        full_response, total_tokens, generation_time = result

        # 流式接口未返回 usage 时估算 token 数。
        if total_tokens == 0 and full_response:
            total_tokens = estimate_tokens(full_response)
            result = (full_response, total_tokens, generation_time)

        return result

    def _process_openai_stream(
        self,
        client: Any,
        role_config: LLMConfig,
        messages: List[Dict[str, str]],
    ) -> Tuple[str, int, float]:
        """专门处理 OpenAI 兼容 API 流响应"""

        params = self._build_request_params(role_config, messages)
        params['stream'] = True

        params['extra_body'] = {"thinking": {"type": "disabled"}}

        stream = client.chat.completions.create(**params)

        full_response, total_tokens, generation_start_time = "", 0, None
        finish_reason = None

        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                if generation_start_time is None:
                    generation_start_time = time.time()

            if hasattr(chunk, 'usage') and chunk.usage:
                total_tokens = getattr(chunk.usage, 'completion_tokens', 0)

            if chunk.choices and chunk.choices[0].finish_reason:
                finish_reason = chunk.choices[0].finish_reason

        if finish_reason == 'length':
            raise APIException("LLM 输出达到 token 上限，润色结果可能被截断", 'qwen')

        generation_time = time.time() - generation_start_time if generation_start_time else 0.0
        return full_response.strip(), total_tokens, generation_time
