# coding: utf-8
"""
剪贴板子模块

提供统一的剪贴板操作接口，包括：
1. 安全读取剪贴板（支持多种编码）
2. 安全写入剪贴板
3. 通过 Command+V 粘贴并恢复原剪贴板
"""

from .. import logger
from core.client.clipboard.clipboard import (
    safe_paste,
    safe_copy,
    copy_to_clipboard,
    paste_text,
    CLIPBOARD_ENCODINGS,
)

__all__ = [
    'logger',
    'safe_paste',
    'safe_copy',
    'copy_to_clipboard',
    'paste_text',
    'CLIPBOARD_ENCODINGS',
]
