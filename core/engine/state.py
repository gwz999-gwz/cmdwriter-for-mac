# coding: utf-8
"""
本地识别状态管理模块

保存单机识别任务的会话状态。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict
from rich.console import Console

from core.engine.schema import Result, RecognitionSession

# Rich console 用于显示模型输出
console = Console(highlight=False)


@dataclass
class WorkerState:
    """
    本地识别线程运行状态：
    - sessions: 活跃识别会话，以 task_id 为键
    """
    # 识别会话集
    sessions: Dict[str, RecognitionSession] = field(default_factory=dict)
    
    def get_session(self, task_id: str, source: str = '') -> RecognitionSession:
        """获取或创建识别会话"""
        if task_id not in self.sessions:
            result = Result(task_id=task_id, type=source)
            self.sessions[task_id] = RecognitionSession(task_id=task_id, result=result)
        return self.sessions[task_id]
    
