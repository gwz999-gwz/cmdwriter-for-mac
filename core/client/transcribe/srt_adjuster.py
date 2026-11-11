# coding: utf-8
"""
SRT 调整模块

提供 SrtAdjuster 类用于调整 SRT 字幕时间轴。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from core.client.state import console
from core.tools import srt_from_txt
from . import logger



class SrtAdjuster:
    """
    SRT 字幕调整器
    
    根据文本文件重新生成 SRT 字幕时间轴。
    """
    
    def adjust(self, file: Path) -> None:
        """
        调整 SRT 字幕时间轴
        
        Args:
            file: 文本文件路径
        """
        task_id = str(uuid.uuid1())
        console.print(f'\n任务标识 / Task ID: {task_id}')
        console.print(f'    处理文件 / File: {file}')
        
        logger.info(f"开始调整 SRT: {file}")
        
        try:
            srt_from_txt.one_task(file)
            console.print('    [green]SRT 调整完成 / SRT adjustment complete')
            logger.info(f"SRT 调整完成: {file}")
        except Exception as e:
            console.print(f'    [red]SRT 调整失败 / SRT adjustment failed: {e}')
            logger.error(f"SRT 调整失败 / SRT adjustment failed: {e}", exc_info=True)
