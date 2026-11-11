# coding: utf-8
"""
shortcut 子模块

包含 macOS 单键长按录音所需的快捷键功能。
"""

from .. import logger
from core.client.shortcut.shortcut_config import Shortcut
from core.client.shortcut.shortcut_manager import ShortcutManager

__all__ = [
    'logger',
    'Shortcut',
    'ShortcutManager',
]
