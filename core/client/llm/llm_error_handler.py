"""
LLM 错误处理和用户提示

统一处理 LLM 异常，提供用户友好的错误提示
"""
from typing import Optional, Tuple
from .llm_exceptions import (
    OpenAIErrorWrapper,
)
from . import logger


def get_user_friendly_message(error: Exception) -> str:
    """
    获取用户友好的错误消息

    Args:
        error: 异常对象

    Returns:
        用户友好的错误消息
    """
    # 已包装的 OpenAI 异常
    if isinstance(error, OpenAIErrorWrapper):
        return error.user_message

    # 其他异常
    return f"处理失败: {type(error).__name__}"


def should_fallback_to_original(error: Exception) -> bool:
    """
    判断是否应该降级到原文本

    任何 LLM 错误都不应导致语音识别结果丢失。

    Args:
        error: 异常对象

    Returns:
        始终返回 True，表示应该降级到原文本
    """
    return True


def show_error_notification(error: Exception):
    """
    在日志中记录错误提示。

    Args:
        error: 异常对象
    """
    user_msg = get_user_friendly_message(error)

    # 记录日志
    logger.warning(f"[LLM 润色] {user_msg} - {error}")
    logger.error(f"LLM 润色: {user_msg}")


def handle_llm_error(error: Exception, original_text: str,
                     fallback_text: Optional[str] = None) -> Tuple[str, bool]:
    """
    统一的 LLM 错误处理入口

    Args:
        error: 异常对象
        original_text: 原始输入文本
        fallback_text: 降级时使用的文本（None 则使用 original_text）

    Returns:
        (输出文本, 是否成功)
    """
    # 错误需要被记录，但无论错误类型如何都降级到识别文本。
    show_error_notification(error)
    result = fallback_text if fallback_text is not None else original_text
    logger.info(f"[LLM 润色] 处理失败，降级到原文本: {error}")
    return (result, False)
