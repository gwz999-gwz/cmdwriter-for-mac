# coding: utf-8
"""
文本输出模块

提供 TextOutput 类用于将识别结果输出到当前窗口。
"""

from __future__ import annotations

import re

from config import Config
from core.client.clipboard import paste_text
from . import logger


# 语义字符计数模式：匹配中文字、英文单词、数字
# 中文字（含日韩等）各算 1 个语义单元，英文连续字母算 1 个，连续数字算 1 个
_SEMANTIC_UNIT_RE = re.compile(
    r'[一-鿿㐀-䶿豈-﫿]'
    r'|[a-zA-Z]+'
    r'|\d+'
)


def count_semantic_units(text: str) -> int:
    """计算语义字符数：中文字=1，英文单词=1，数字=1"""
    return len(_SEMANTIC_UNIT_RE.findall(text))



class TextOutput:
    """
    文本输出器
    
    在 macOS 上通过剪贴板粘贴，并恢复用户原剪贴板文本。
    """
    
    @staticmethod
    def strip_punc(text: str) -> str:
        """
        消除末尾最后一个标点

        语义字符数不超过 trash_punc_thresh 时去除末尾标点，
        超过时保留标点（长句正常说话场景）。
        Args:
            text: 原始文本

        Returns:
            处理后的文本
        """
        if not text or not Config.trash_punc:
            return text

        # 检查是否在强制去标点的应用中
        force_strip = False
        if not force_strip and Config.trash_punc_thresh > 0 and count_semantic_units(text) > Config.trash_punc_thresh:
            return text

        clean_text = re.sub(f"(?<=.)[{Config.trash_punc}]$", "", text)
        return clean_text
    
    async def output(self, text: str) -> None:
        """将文本粘贴到当前光标位置并恢复剪贴板。"""
        if not text:
            return
        logger.debug(f"使用粘贴方式输出文本，长度: {len(text)}")
        await paste_text(text)
