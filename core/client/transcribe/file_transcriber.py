# coding: utf-8
"""
文件转录模块

提供 FileTranscriber 类用于将音视频文件转录为字幕。
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from config import Config
from core.client.state import console
from core.protocol import AudioMessage, RecognitionMessage
from .media_tool import MediaTool
from .result_handler import ResultHandler
from . import logger
from core.tools.token_sync import sync_tokens_from_text

if TYPE_CHECKING:
    from core.client.state import ClientState
    from core.client.app import CapsWriterClient


class FileTranscriber:
    """
    文件转录器
    
    协调转录流程：
    1. 检查环境与文件
    2. 调用 MediaTool 提取音频
    3. 将音频分段提交给本地识别引擎
    4. 调用 ResultHandler 处理结果
    """
    
    def __init__(
        self,
        app: CapsWriterClient,
        file: Path,
        *,
        save_txt: bool,
        save_srt: bool,
    ):
        """
        初始化文件转录器
        
        Args:
            app: 客户端 App 实例
            file: 要转录的文件路径
        """
        self.app = app
        self.file = file
        self.task_id: Optional[str] = None
        self._audio_duration: float = 0.0
        self._time_start: float = 0.0
        self.save_txt = save_txt
        self.save_srt = save_srt
        if not self.save_txt and not self.save_srt:
            raise ValueError("请至少选择一种输出格式 / Select TXT, SRT, or both")

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    @property
    def _ws_manager(self):
        """快捷访问内嵌 ASR 引擎宿主"""
        return self.app.engine
    
    async def check(self) -> bool:
        """检查转录条件"""
        # 检查文件是否存在
        if not self.file.exists():
            logger.error(f"文件不存在 / File not found: {self.file}")
            return False

        # 检查媒体工具环境 (FFmpeg)
        if not MediaTool.check_environment():
            return False

        # 等待本地识别引擎准备完成
        if not await self._ws_manager.connect():
            logger.error("本地识别引擎不可用 / Local speech recognition engine unavailable")
            return False
        
        
        return True
    
    async def send(self) -> None:
        """将音频数据提交给本地引擎（异步分段处理）。"""
        
        self.task_id = str(uuid.uuid1())
        await self._ws_manager.register_result_queue(self.task_id)
        console.print(f'\n任务标识 / Task ID: {self.task_id}')
        console.print(f'    处理文件 / File: {self.file}')
        output_names = []
        if self.save_txt:
            output_names.append('TXT')
        if self.save_srt:
            output_names.append('SRT')
        console.print(f'    输出格式 / Output format: {" + ".join(output_names)}')
        
        # 1. 预先获取时长
        self._audio_duration = await MediaTool.get_audio_duration(self.file)
        if self._audio_duration > 0:
            console.print(f'    音频长度 / Audio duration: {self._audio_duration:.2f}s')
        
        logger.info(f"开始转录文件: {self.file}, 任务ID: {self.task_id}")
        
        # 2. 启动 FFmpeg 进程
        ffmpeg_cmd = MediaTool.build_ffmpeg_cmd(self.file)
        # 整个文件任务共用同一个起始时间。旧实现每个分片调用 time.time()，
        # 最终显示的“处理耗时”只覆盖最后一小段，明显低估长文件耗时。
        self._time_start = time.time()
        
        try:
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # 分块大小：1分钟音频 (16000 * 4 * 60 bytes)
            chunk_size = 16000 * 4 * 60
            bytes_sent = 0
            
            while True:
                data = await process.stdout.read(chunk_size)
                if not data:
                    break
                
                bytes_sent += len(data)
                progress = bytes_sent / 4 / 16000
                if self._audio_duration > 0:
                    prog_str = f'    发送进度：{progress:.2f}s / {self._audio_duration:.2f}s'
                else:
                    prog_str = f'    发送进度：{progress:.2f}s'
                console.print(prog_str, end='\r')

                message = AudioMessage(
                    task_id=self.task_id,
                    source='file',
                    data=base64.b64encode(data).decode('utf-8'),
                    is_final=False,
                    time_start=self._time_start,
                    seg_duration=Config.file_seg_duration,
                    seg_overlap=Config.file_seg_overlap,
                    context='',
                    language=Config.language,
                    save_srt=self.save_srt,
                )
                if not await self._ws_manager.send(message):
                    raise ConnectionError("消息发送失败，连接可能已断开 / Could not send the message. The connection may have closed.")

            # 发送结束标志
            final_message = AudioMessage(
                task_id=self.task_id,
                source='file',
                data='',
                is_final=True,
                time_start=self._time_start,
                seg_duration=Config.file_seg_duration,
                seg_overlap=Config.file_seg_overlap,
                context='',
                language=Config.language,
                save_srt=self.save_srt,
            )
            if not await self._ws_manager.send(final_message):
                raise ConnectionError("结束标志发送失败 / Could not send the end-of-stream marker")
            await process.wait()
            
            if self._audio_duration == 0:
                self._audio_duration = progress 
                console.print(f'    音频长度 / Audio duration: {self._audio_duration:.2f}s')

            logger.debug("音频数据发送完成")
            
        except ConnectionError as e:
            logger.error(f"发送数据失败 / Could not send audio data: {e}, 文件 / file: {self.file}")
            if 'process' in locals() and process.returncode is None:
                process.terminate()
            return
        except Exception as e:
            logger.error(f"转录发送异常 / Transcription submission failed: {e}", exc_info=True)
            if 'process' in locals() and process.returncode is None:
                process.terminate()
            return
    
    async def receive(self) -> None:
        """接收转录结果"""
        
        try:
            while True:
                msg = await self._ws_manager.receive(self.task_id)
                if not msg:
                    break
                
                console.print(f'    转录进度 / Transcription progress: {msg.duration:.2f}s', end='\r')
                if msg.is_final:
                    message = msg # 保持变量名兼容后续调用
                    break
        except ConnectionError as e:
            logger.error(f"{e}, 文件 / file: {self.file}")
            return
        except Exception as e:
            logger.error(f"接收消息错误 / Could not receive a transcription message: {e}")
            return

        # 应用热词并同步 tokens
        self._apply_hotwords(message)

        # 调用结果处理器进行保存和格式化
        text_display = ResultHandler.save_results(
            self.file,
            message,
            save_txt=self.save_txt,
            save_srt=self.save_srt,
        )
        
        process_duration = message.time_complete - message.time_start
        console.print(f'\033[K    处理耗时 / Processing time: {process_duration:.2f}s')
        console.print(f'    识别结果 / Transcript:\n[green]{text_display}')
        
        logger.info(
            f"转录完成: {self.file}, 处理耗时: {process_duration:.2f}s, "
            f"文本长度: {len(text_display)}"
        )

    def _apply_hotwords(self, message: RecognitionMessage) -> None:
        """对识别结果应用热词替换并同步 tokens"""
        if not Config.hot:
            logger.debug("热词功能已关闭，跳过文件转录热词修正")
            return

        text_accu = message.text_accu or message.text
        corrected = text_accu

        # 1. 音素热词替换
        correction = self.app.hotword.get_phoneme_corrector().correct(text_accu, k=10)
        corrected = correction.text
        # 记录热词匹配日志
        for origin, hw, score in correction.matchs:
            logger.info(f"热词匹配 / Hotword match: 「{origin}」→「{hw}」(分数 / score={score:.2f})")
            console.print(f'    [cyan]热词匹配 / Hotword match:[/] 「{origin}」→「[green]{hw}[/]」(分数 / score={score:.2f})')
        for origin, hw, score in correction.similars:
            logger.debug(f"热词参考: 「{origin}」≈「{hw}」(分数 / score={score:.2f})")

        # 2. 规则替换
        if Config.hot_rule:
            corrected = self.app.hotword.get_rule_corrector().substitute(corrected)

        # 3. 有变化则同步到 tokens 并更新 message
        if corrected != text_accu and message.tokens:
            new_tokens, new_timestamps = sync_tokens_from_text(
                message.tokens, message.timestamps, corrected
            )
            message.text_accu = corrected
            message.text = corrected
            message.tokens = new_tokens
            message.timestamps = new_timestamps
            logger.debug(f"热词修正: {text_accu[:60]} → {corrected[:60]}")

    async def close(self) -> None:
        """释放本次文件转录资源。"""
        if self.task_id:
            self._ws_manager.unregister_result_queue(self.task_id)
        await self._ws_manager.close()
