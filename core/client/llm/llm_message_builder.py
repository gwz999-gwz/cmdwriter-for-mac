
# coding: utf-8
"""
LLM 消息构建模块

负责组装单句话的 LLM 请求，包括：
1. System Prompt（系统提示词）
2. 热词列表（用于本句话的专有词纠错）
3. 用户输入
"""

from __future__ import annotations

from typing import List, Dict, Optional, Tuple

from .llm_config_schema import LLMConfig
from . import logger


class MessageBuilder:
    """LLM 消息构建器"""

    def __init__(self, app):
        """
        初始化消息构建器
        """
        self.app = app

    def build_messages(
        self,
        role_config: LLMConfig,
        user_content: str,
        hotwords: Optional[List[Tuple[str, float]]] = None,
    ) -> List[Dict]:
        """
        构建 LLM 请求消息

        Args:
            role_config: 唯一润色配置
            user_content: 用户输入内容
            hotwords: 匹配的热词列表 [(热词, 分数), ...]

        Returns:
            完整的消息列表
        """
        messages = []

        # 1. System Prompt
        if role_config.system_prompt:
            messages.append({
                "role": "system",
                "content": role_config.system_prompt
            })

        # 2. 本句话的辅助信息
        prompt_parts = []

        # 3.1 热词列表
        if hotwords:
            try:
                # hotwords 结构为 [(source, match, score), ...]
                words = [item[1] for item in hotwords]
                        
                if words:
                    prompt_parts.append(f"热词列表：[{', '.join(words)}]")
                    logger.debug(f"[消息构建] 已添加热词列表")
            except Exception as e:
                logger.error(f"[ERROR] Failed to process hotwords: {e}")
                logger.error(f"[ERROR] hotwords details: {[(type(hw), hw) for hw in hotwords[:5]]}")
                raise

        # 3.4 最终组装
        prompt_str = "\n\n".join(prompt_parts)
        prompt_str = prompt_str + "\n\n" if prompt_str else ""

        user_content = f"{prompt_str}用户输入：{user_content}"

        # 构建最终用户消息
        final_user_msg = {"role": "user", "content": user_content}

        messages.append(final_user_msg)

        self._debug_print_messages(messages)

        return messages

    def _debug_print_messages(
        self,
        messages: List[Dict]
    ):
        """打印本次单句请求。"""
        try:
            last_msg = messages[-1]
            content = last_msg.get('content', '')
            info_msg = [
                f"\n{'='*70}",
                "[LLM 单句润色请求]",
                f"{content}",
                f"{'='*70}\n"
            ]
            logger.info("\n".join(info_msg))

        except Exception as e:
            logger.error(f"消息日志输出失败 / Could not log messages: {e}")
