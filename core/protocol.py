# coding: utf-8
"""
本地音频与识别结果消息。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal


@dataclass
class AudioMessage:
    """
    录音器提交给本地识别引擎的音频消息
    
    Attributes:
        task_id: 任务唯一标识
        source: 音频来源 ('mic' 麦克风 或 'file' 文件)
        data: Base64 编码的音频数据 (float32, 16kHz, mono)
        is_final: 是否为当前任务的最后一个数据包
        time_start: 录音/音频开始时间戳
        seg_duration: 分段时长（秒）
        seg_overlap: 重叠时长（秒）
    """
    task_id: str
    source: Literal['mic', 'file']
    data: str                    # base64 编码的音频
    is_final: bool
    time_start: float
    seg_duration: float = 15.0
    seg_overlap: float = 2.0
    context: str = ''
    language: str = 'auto'
    save_srt: bool = False


@dataclass
class RecognitionMessage:
    """
    本地识别引擎产生的结果消息
    
    Attributes:
        task_id: 任务唯一标识
        is_final: 是否为最终结果（所有片段识别完成）
        duration: 已处理的音频总时长（秒）
        time_start: 录音/音频开始时间戳
        time_submit: 最后一个片段的提交时间戳
        time_complete: 识别完成时间戳
        
        text: 主要输出 - 简单文本拼接结果（不依赖时间戳）
        text_accu: 精确输出 - 基于时间戳去重的拼接结果（用于字幕生成）
        tokens: 字级 token 列表（与 timestamps 对应）
        timestamps: 字级时间戳列表（秒）
    """
    task_id: str
    is_final: bool
    duration: float
    time_start: float
    time_submit: float
    time_complete: float
    
    # 主要输出（简单文本拼接）
    text: str
    
    # 精确输出（时间戳拼接）
    text_accu: str = ''
    tokens: List[str] = field(default_factory=list)
    timestamps: List[float] = field(default_factory=list)
    
