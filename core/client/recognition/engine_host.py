# coding: utf-8
"""
单进程内嵌 ASR 引擎宿主

在当前进程中运行完整推理管线：
- 后台线程加载 Qwen3-ASR；文件生成 SRT 时再延迟加载时间戳对齐器
- 后台推理线程消费 Task，同步调用 pipeline.process()，产出 RecognitionMessage
- 对录音和文件转录提供异步收发接口

这样客户端（录音、热键、热词、LLM 润色、输出）与文件转录逻辑完全复用，
不启动网络服务或额外进程。
"""

from __future__ import annotations

import asyncio
import base64
import os
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

from core.constants import AudioFormat
from core.protocol import AudioMessage, RecognitionMessage
from core.engine.schema import Task
from core.engine.state import WorkerState
from core.engine.worker.pipeline import TaskPipeline
from core.engine.engines.qwen_asr_gguf.asr_engine import QwenASREngine
from core.engine.engines.qwen_common.schema import ASREngineConfig
from config import Config, ModelConfig

from .. import logger

if TYPE_CHECKING:
    from ..app import CapsWriterClient

class AudioCache:
    """本地音频分段缓冲区。

    缓存接收到的音频数据，直到达到分段阈值后提交处理。
    """

    def __init__(self):
        self.chunks: bytes = b''
        self.offset: float = 0.0
        self.byte_count: int = 0

    @property
    def duration(self) -> float:
        """缓冲区音频时长（秒）"""
        return AudioFormat.bytes_to_seconds(len(self.chunks))

    @property
    def total_duration(self) -> float:
        """累计接收的音频总时长（秒，仅用于统计）"""
        return AudioFormat.bytes_to_seconds(self.byte_count)

    def reset(self) -> None:
        self.chunks = b''
        self.offset = 0.0
        self.byte_count = 0


class EngineHost:
    """
    内嵌 ASR 引擎宿主

    引擎加载一次后常驻，直到 cleanup() 才释放（多文件转录期间不可关闭）。
    """

    def __init__(self, app: "CapsWriterClient"):
        self.app = app
        self._engine = None
        self._aligner = None
        self._pipeline = None
        self._worker_state = None
        self._ready = threading.Event()
        self._failed = False
        self._load_error: Optional[Exception] = None

        self._task_queue: queue.Queue = queue.Queue()        # 推理线程消费
        self._result_queue: Optional[asyncio.Queue] = None   # 未订阅任务（麦克风）的结果队列
        self._task_result_queues: dict[str, asyncio.Queue] = {}
        self._infer_thread: Optional[threading.Thread] = None
        self._caches: dict[str, AudioCache] = {}

    # ------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        """模型是否加载完成。"""
        return self._ready.is_set()

    @property
    def is_failed(self) -> bool:
        """模型加载是否失败。"""
        return self._failed

    @property
    def load_error(self) -> Optional[Exception]:
        """模型加载失败原因。"""
        return self._load_error

    @property
    def is_connected(self) -> bool:
        """模型是否已经可用。"""
        return self.is_ready

    def start(self) -> None:
        """启动模型加载（后台线程）。可安全重复调用。"""
        if self._infer_thread is not None or self._ready.is_set():
            return
        threading.Thread(
            target=self._load_models,
            daemon=True,
            name="EngineLoadThread",
        ).start()

    # ------------------------------------------------------------
    # 模型加载与推理循环
    # ------------------------------------------------------------

    def _load_models(self) -> None:
        try:
            logger.info("正在加载语音识别模型（Qwen3-ASR），请稍候…")
            self._engine = QwenASREngine(ASREngineConfig(**dict(ModelConfig.asr)))

            # 引擎依赖的 llama.py 可能在导入时改变工作目录，恢复之
            os.chdir(self.app.base_dir)

            self._worker_state = WorkerState()
            self._pipeline = TaskPipeline(
                self._engine,
                punc_model=None,
                aligner=None,
                state=self._worker_state,
            )

            self._infer_thread = threading.Thread(
                target=self._inference_loop,
                daemon=True,
                name="EngineInferThread",
            )
            self._infer_thread.start()
            self._ready.set()
            logger.info("语音识别模型加载完成")
        except Exception as e:
            self._failed = True
            self._load_error = e
            logger.error(f"语音识别模型加载失败: {e}", exc_info=True)

    def _inference_loop(self) -> None:
        """后台推理线程。

        文件任务使用一个 CPU 预取线程编码下一片段，同时当前片段只在本线程
        执行 Metal 解码。这样不会并发访问两个 llama/Metal context，也不会影响
        麦克风任务的低延迟同步路径。
        """
        pending_task = None
        pending_prepared: Optional[Future] = None

        with ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="FileEncoderPrefetch",
        ) as encoder_pool:
            while True:
                task = pending_task if pending_task is not None else self._task_queue.get()
                pending_task = None
                if task is None:
                    break

                stop_after_current = False
                try:
                    if task.type == 'file' and task.save_srt:
                        self._ensure_aligner()

                    use_prefetch = (
                        task.type == 'file'
                        and Config.file_pipeline_prefetch
                        and hasattr(self._pipeline, 'prepare')
                    )
                    if pending_prepared is not None:
                        prepared = pending_prepared.result()
                        pending_prepared = None
                    elif use_prefetch:
                        # 首片段没有可复用的 Future，只付一次同步预编码成本。
                        prepared = self._pipeline.prepare(task)
                    else:
                        prepared = None

                    # 文件发送端会快速排入后续片段；取出一个同任务片段，让其
                    # CPU/ONNX 编码与当前片段的 Metal 解码并行。
                    if use_prefetch and not task.is_final:
                        try:
                            candidate = self._task_queue.get_nowait()
                        except queue.Empty:
                            candidate = None
                        else:
                            if candidate is None:
                                stop_after_current = True
                            else:
                                pending_task = candidate
                                if (
                                    candidate.type == 'file'
                                    and candidate.task_id == task.task_id
                                ):
                                    pending_prepared = encoder_pool.submit(
                                        self._pipeline.prepare,
                                        candidate,
                                    )

                    result = self._pipeline.process(task, prepared=prepared)
                    msg = RecognitionMessage(
                        task_id=result.task_id,
                        is_final=result.is_final,
                        duration=result.duration,
                        time_start=result.time_start,
                        time_submit=result.time_submit,
                        time_complete=result.time_complete,
                        text=result.text,
                        text_accu=result.text_accu,
                        tokens=result.tokens,
                        timestamps=result.timestamps,
                    )
                    if result.is_final:
                        self._worker_state.sessions.pop(task.task_id, None)
                    self.app.loop.call_soon_threadsafe(self._dispatch_result, msg)
                except Exception as e:
                    logger.error(
                        f"推理任务失败，task_id={task.task_id[:8]}: {e}",
                        exc_info=True,
                    )

                if stop_after_current:
                    break

    def _ensure_aligner(self) -> None:
        """首次处理 SRT 文件任务时才加载强制对齐模型。"""
        if self._aligner is not None:
            return
        try:
            from core.engine.engines.force_aligner_gguf.align_engine import QwenForceAligner
            from core.engine.engines.qwen_common.schema import AlignerConfig

            logger.info("文件任务需要精确字幕，正在加载对齐模型…")
            self._aligner = QwenForceAligner(
                AlignerConfig(**dict(ModelConfig.aligner))
            )
            self._pipeline.aligner = self._aligner
            logger.info("对齐模型加载完成")
        except Exception as e:
            # False 表示已经尝试但失败，避免后续每个文件分片重复加载。
            self._aligner = False
            self._pipeline.aligner = None
            logger.warning(f"对齐模型加载失败，将不生成精确时间戳: {e}")

    # ------------------------------------------------------------
    # 本地异步接口
    # ------------------------------------------------------------

    async def wait_ready(self) -> bool:
        """等待模型加载完成；失败时抛出异常。"""
        while not self._ready.is_set() and not self._failed:
            await asyncio.sleep(0.1)
        if self._failed:
            raise RuntimeError(f"语音识别模型加载失败: {self._load_error}")
        if self._result_queue is None:
            self._result_queue = asyncio.Queue()
        return True

    async def connect(self) -> bool:
        """兼容旧接口：等待模型就绪，返回是否可用。"""
        try:
            await self.wait_ready()
            return True
        except RuntimeError:
            return False

    async def register_result_queue(self, task_id: str) -> None:
        """为文件等独立任务注册专用结果队列，避免被麦克风处理器取走。"""
        await self.wait_ready()
        self._task_result_queues[task_id] = asyncio.Queue()

    def unregister_result_queue(self, task_id: str) -> None:
        self._task_result_queues.pop(task_id, None)

    def _dispatch_result(self, message: RecognitionMessage) -> None:
        queue_for_task = self._task_result_queues.get(message.task_id)
        if queue_for_task is None:
            queue_for_task = self._result_queue
        if queue_for_task is not None:
            queue_for_task.put_nowait(message)

    async def send(self, message: AudioMessage) -> bool:
        """接收客户端音频消息，分段后交给推理线程。"""
        try:
            await self.wait_ready()
        except RuntimeError:
            return False
        try:
            self._handle_audio_message(message)
            return True
        except Exception as e:
            logger.error(
                f"处理音频消息失败，task_id={message.task_id[:8]}: {e}", exc_info=True
            )
            return False

    def _handle_audio_message(self, msg: AudioMessage) -> None:
        """复制原 ws_recv.message_handler 的分段逻辑：AudioMessage → Task 队列。"""
        seg_threshold = msg.seg_duration + msg.seg_overlap * 2

        cache = self._caches.setdefault(msg.task_id, AudioCache())

        data = base64.b64decode(msg.data)
        cache.chunks += data
        cache.byte_count += len(data)

        if not msg.is_final:
            segment_bytes = AudioFormat.seconds_to_bytes(
                msg.seg_duration + msg.seg_overlap
            )
            stride_bytes = AudioFormat.seconds_to_bytes(msg.seg_duration)

            # 分段条件必须基于当前仍在缓存中的音频，而不是任务自开始以来
            # 累计收到的音频。累计时长只增不减；若用它判断，第一次达到
            # 阈值后循环将永远成立，并持续提交空分片，最终淹没推理队列。
            while cache.duration >= seg_threshold:
                segment_data = cache.chunks[:segment_bytes]
                cache.chunks = cache.chunks[stride_bytes:]

                task = Task(
                    type=msg.source,
                    data=segment_data,
                    offset=cache.offset,
                    task_id=msg.task_id,
                    overlap=msg.seg_overlap,
                    is_final=False,
                    time_start=msg.time_start,
                    time_submit=time.time(),
                    context=msg.context,
                    language=msg.language,
                    save_srt=msg.save_srt,
                )
                cache.offset += msg.seg_duration
                self._task_queue.put(task)
        else:
            task = Task(
                type=msg.source,
                data=cache.chunks,
                offset=cache.offset,
                task_id=msg.task_id,
                overlap=msg.seg_overlap,
                is_final=True,
                time_start=msg.time_start,
                time_submit=time.time(),
                context=msg.context,
                language=msg.language,
                save_srt=msg.save_srt,
            )
            self._task_queue.put(task)
            self._caches.pop(msg.task_id, None)

    async def receive(self, task_id: Optional[str] = None) -> Optional[RecognitionMessage]:
        """从结果队列取一条识别结果。"""
        await self.wait_ready()
        if task_id is None:
            return await self._result_queue.get()
        queue_for_task = self._task_result_queues.get(task_id)
        if queue_for_task is None:
            raise RuntimeError(f"任务结果队列未注册: {task_id}")
        return await queue_for_task.get()

    async def close(self) -> None:
        """多文件转录期间保持引擎常驻。"""
        pass

    def close_sync(self) -> None:
        """同步清理入口。"""
        self.cleanup()

    def cleanup(self) -> None:
        """停止推理线程并释放模型资源（应用退出时调用）。"""
        try:
            self._task_queue.put(None)
        except Exception:
            pass
        if self._infer_thread is not None:
            try:
                self._infer_thread.join(timeout=2)
            except Exception:
                pass
            self._infer_thread = None
        for engine in (self._aligner, self._engine):
            if engine:
                try:
                    engine.cleanup()
                except Exception as e:
                    logger.warning(f"引擎清理失败: {e}")
        self._engine = None
        self._aligner = None
        self._pipeline = None
        self._worker_state = None
        self._caches.clear()
        self._task_result_queues.clear()
        self._ready.clear()
