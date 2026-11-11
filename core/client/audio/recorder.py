# coding: utf-8
"""
音频录制模块

提供 AudioRecorder 类用于管理录音会话，包括开始录音、
提交音频给本地识别引擎并管理录音结束。
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from typing import TYPE_CHECKING, Optional

import numpy as np

from config import Config
from core.client.state import console
from core.protocol import AudioMessage
from . import logger

if TYPE_CHECKING:
    from core.client.state import ClientState
    from core.client.app import CapsWriterClient

# 日志记录器


class AudioRecorder:
    """
    音频录制器
    
    管理一次完整的录音会话，包括：
    - 从音频流接收数据
    - 将音频数据提交给本地识别引擎
    """
    
    def __init__(self, app: CapsWriterClient):
        """
        初始化录制器
        
        Args:
            app: 客户端 App 实例
        """
        self.app = app
        self.task_id: Optional[str] = None
        self._start_time: float = 0.0
        self._duration: float = 0.0
        self._cache: list = []

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    @property
    def _ws_manager(self):
        """快捷访问内嵌 ASR 引擎宿主"""
        return self.app.engine

    async def _send_message(self, message: AudioMessage) -> None:
        """发送消息到识别引擎（内部会等待模型就绪，不丢音频）"""
        success = await self._ws_manager.send(message)
        if not success and message.is_final:
            console.print('    语音识别模型不可用，无法发送\n')
            logger.warning("语音识别模型不可用，无法发送音频数据")
    
    async def record_and_send(self) -> None:
        """
        录音并发送数据
        
        从队列中读取音频数据并提交给本地引擎识别。
        """
        try:
            # 生成唯一任务 ID
            self.task_id = str(uuid.uuid1())
            logger.debug(f"创建录音任务，任务ID: {self.task_id}")
            
            self._start_time = 0.0
            self._duration = 0.0
            self._cache = []
            
            # 从队列读取数据
            while task := await self.state.queue_in.get():
                self.state.queue_in.task_done()
                
                if task['type'] == 'begin':
                    self._start_time = task['time']
                    logger.debug(f"录音开始，时间戳: {self._start_time}")
                    
                elif task['type'] == 'data':
                    # 在阈值之前积攒音频数据
                    if task['time'] - self._start_time < Config.threshold:
                        self._cache.append(task['data'])
                        continue
                    
                    # 获取音频数据
                    if self._cache:
                        data = np.concatenate(self._cache)
                        self._cache.clear()
                    else:
                        data = task['data']
                    
                    self._duration += len(data) / 48000
                    
                    # 发送音频数据用于识别
                    message = AudioMessage(
                        task_id=self.task_id,
                        source='mic',
                        data=base64.b64encode(
                            np.mean(data[::3], axis=1).tobytes()
                        ).decode('utf-8'),
                        is_final=False,
                        time_start=self._start_time,
                        seg_duration=Config.mic_seg_duration,
                        seg_overlap=Config.mic_seg_overlap,
                        context='',
                        language=Config.language,
                    )
                    asyncio.create_task(self._send_message(message))
                    
                elif task['type'] == 'finish':
                    # 如果有缓存的数据未发送，先发送缓存
                    if self._cache:
                        data = np.concatenate(self._cache)
                        self._cache.clear()
                        
                        self._duration += len(data) / 48000
                        message = AudioMessage(
                            task_id=self.task_id,
                            source='mic',
                            data=base64.b64encode(
                                np.mean(data[::3], axis=1).tobytes()
                            ).decode('utf-8'),
                            is_final=False,
                            time_start=self._start_time,
                            seg_duration=Config.mic_seg_duration,
                            seg_overlap=Config.mic_seg_overlap,
                            context='',
                            language=Config.language,
                        )
                        asyncio.create_task(self._send_message(message))

                    console.print(f'任务标识：{self.task_id}')
                    console.print(f'    录音时长：{self._duration:.2f}s')
                    logger.info(f"录音任务完成，任务ID: {self.task_id}, 时长: {self._duration:.2f}s")
                    
                    # 告诉本地引擎音频片段结束了
                    message = AudioMessage(
                        task_id=self.task_id,
                        source='mic',
                        data='',
                        is_final=True,
                        time_start=self._start_time,
                        seg_duration=Config.mic_seg_duration,
                        seg_overlap=Config.mic_seg_overlap,
                        context='',
                        language=Config.language,
                    )
                    asyncio.create_task(self._send_message(message))
                    break
                    
        except Exception as e:
            logger.error(f"录音任务错误: {e}", exc_info=True)
    
