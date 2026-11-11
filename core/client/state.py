# coding: utf-8
"""
客户端状态管理模块

提供 ClientState 类用于管理客户端的全局状态。
使用 dataclass 提供类型安全和清晰的状态定义。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import sounddevice as sd
    from .app import CapsWriterClient

from rich.console import Console
from rich.theme import Theme

from . import logger


# 配置 Rich console
_theme = Theme({
    'markdown.code': 'cyan',
    'markdown.item.number': 'yellow'
})
console = Console(highlight=False, soft_wrap=True, theme=_theme)


@dataclass
class ClientState:
    """
    客户端运行状态

    管理音频流、录音状态和本地任务队列。

    Attributes:
        loop: asyncio 事件循环
        queue_in: 音频数据输入队列
        stream: 音频输入流
        recording: 是否正在录音
        recording_start_time: 录音开始时间戳
        last_recognition_text: 最近一次识别的最终文本（热词替换后），供"添加纠错记录"使用
    """

    queue_in: asyncio.Queue = field(default_factory=asyncio.Queue)
    stream: Optional[sd.InputStream] = None
    app: Optional[CapsWriterClient] = None

    recording: bool = False
    recording_start_time: float = 0.0
    # 最近一次识别结果（用于手动添加纠错记录）
    last_recognition_text: Optional[str] = None

    # 最近一次输出内容（如果是 LLM 润色，则是润色结果；否则是原始识别结果）
    last_output_text: Optional[str] = None

    # 强制 LLM 润色标志（录音期间按过触发键则置为 True，识别结果处理后立即重置）
    force_llm: bool = False
    

    
    def reset(self) -> None:
        """
        重置状态

        清理所有状态，关闭连接和流。用于重新初始化或退出时清理。
        """
        logger.debug("正在重置客户端状态...")

        # 关闭音频流
        if self.stream is not None:
            try:
                self.stream.close()
                logger.debug("音频流已关闭")
            except Exception:
                pass
            self.stream = None


        # 重置其他状态
        self.recording = False
        self.recording_start_time = 0.0

        logger.debug("客户端状态重置完成")
    
    def start_recording(self, start_time: float) -> None:
        """
        开始录音
        
        Args:
            start_time: 录音开始的时间戳
        """
        self.recording = True
        self.recording_start_time = start_time
        logger.debug(f"录音状态已更新: recording=True, start_time={start_time:.2f}")
    
    def stop_recording(self) -> float:
        """
        停止录音
        
        Returns:
            录音持续时间（秒）
        """
        duration = 0.0
        if self.recording_start_time > 0:
            duration = time.time() - self.recording_start_time
        
        self.recording = False
        self.recording_start_time = 0.0
        logger.debug(f"录音状态已更新: recording=False, duration={duration:.2f}s")
        return duration
    
    def set_output_text(self, text: str) -> None:
        """
        设置最近一次输出文本
        
        Args:
            text: 输出文本内容
        """
        self.last_output_text = text
