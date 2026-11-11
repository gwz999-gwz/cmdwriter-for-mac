"""
LLM 客户端池

功能：
1. 缓存 OpenAI 客户端实例
2. 为唯一的 OpenAI 兼容 API 创建客户端
"""
from openai import OpenAI
from typing import Dict, Any


class ClientPool:
    """OpenAI 客户端池"""

    def __init__(self):
        self._clients: Dict[str, Any] = {}

    def get_client(self, api_url: str, api_key: str) -> Any:
        """获取 LLM 客户端（带缓存）

        Args:
            api_url: OpenAI 兼容 API 地址
            api_key: API Key

        Returns:
            OpenAI 客户端实例
        """
        cache_key = api_url

        if cache_key not in self._clients:
            self._clients[cache_key] = OpenAI(
                base_url=api_url,
                api_key=api_key,
                timeout=10.0,
            )

        return self._clients[cache_key]

    def clear(self):
        """清空客户端缓存"""
        self._clients.clear()
