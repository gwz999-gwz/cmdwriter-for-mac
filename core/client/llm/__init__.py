"""
LLM 模块

提供唯一的单句润色配置、消息构建和输出功能。"""

from core import get_logger
logger = get_logger('client')

# 核心处理器
from .llm_handler import LLMHandler, LLMResult

from .llm_config_schema import LLMConfig

# 消息构建和客户端池
from .llm_message_builder import MessageBuilder
from .llm_client_pool import ClientPool

from .llm_output_typing import handle_typing_mode


__all__ = [
    # 核心
    'LLMHandler',

    'LLMConfig',

    # 组件
    'MessageBuilder',
    'ClientPool',

    # 输出
    'handle_typing_mode',

    # 主入口
    'LLMResult',
]
