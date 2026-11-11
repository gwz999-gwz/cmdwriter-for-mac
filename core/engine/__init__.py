# coding: utf-8
"""
本地语音识别引擎模块。
"""

from core.engine.state import console
from core.logger import get_logger, setup_logger
from config import Config, __version__

setup_logger('engine', level=Config.log_level)
logger = get_logger('engine')

from core.engine.schema import Task, Result

__all__ = [
    'console',
    'logger',
    'Task',
    'Result',
]
