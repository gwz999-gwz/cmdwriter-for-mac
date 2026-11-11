# coding: utf-8
"""
audio 子模块

包含音频录制和音频流管理功能。
"""

from .. import logger
from core.client.audio.recorder import AudioRecorder
from core.client.audio.stream import AudioStreamManager

__all__ = [
    'logger',
    'AudioRecorder',
    'AudioStreamManager',
]
