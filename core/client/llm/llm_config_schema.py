"""
LLM 单一润色配置

使用 Dataclass 替代字典，提供类型安全和更好的 IDE 支持
"""
from dataclasses import dataclass


@dataclass
class LLMConfig:
    """唯一的单句润色配置。"""

    # API 配置
    api_url: str = ''                             # API 地址
    api_key: str = ''                             # API Key
    model: str = 'qwen3.7-flash'                  # 模型名称

    # System Prompt
    system_prompt: str = ''                       # 系统提示词

