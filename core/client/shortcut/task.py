# coding: utf-8
"""
快捷键任务模块

管理单个快捷键的录音任务状态
"""

from __future__ import annotations
import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

from . import logger
from core.tools.my_status import Status

if TYPE_CHECKING:
    from core.client.shortcut.shortcut_config import Shortcut
    from core.client.state import ClientState
    from core.client.audio.recorder import AudioRecorder
    from core.client.app import CapsWriterClient



class ShortcutTask:
    """
    单个快捷键的录音任务

    跟踪每个快捷键独立的录音状态，防止互相干扰。
    """

    def __init__(self, app: CapsWriterClient, shortcut: Shortcut, recorder_class=None):
        """
        初始化快捷键任务

        Args:
            app: 客户端 App 实例
            shortcut: 快捷键配置
            recorder_class: AudioRecorder 类（可选，用于延迟导入）
        """
        self.app = app
        self.shortcut = shortcut
        self._recorder_class = recorder_class

        # 任务状态
        self.task: Optional[asyncio.Future] = None
        self.recording_start_time: float = 0.0
        self.is_recording: bool = False

        # 线程池（由快捷键管理器持有）
        self.pool = None

        # mic_only_on_press 模式：延迟关闭音频流的 Timer 与互斥锁
        self._close_timer: Optional[threading.Timer] = None
        self._close_timer_lock = threading.Lock()

        # mic_only_on_press 模式：异步执行音频操作的独立线程池
        self._mic_pool: Optional[ThreadPoolExecutor] = None

        # 录音状态动画
        self._status = Status('开始录音', spinner='point')

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    def _get_recorder(self) -> AudioRecorder:
        """获取 AudioRecorder 实例"""
        if self._recorder_class is None:
            from core.client.audio.recorder import AudioRecorder
            self._recorder_class = AudioRecorder
        return self._recorder_class(self.app)

    def launch(self) -> None:
        """启动录音任务"""
        logger.info(f"[{self.shortcut.key}] 触发：开始录音")

        from config import Config
        if Config.mic_only_on_press:
            # 取消上次录音完成的延迟关闭定时器，避免连续输入时麦克风反复重连
            self._cancel_pending_close()

        # 记录开始时间
        self.recording_start_time = time.time()
        self.is_recording = True

        # 将开始标志放入队列
        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({'type': 'begin', 'time': self.recording_start_time, 'data': None}),
            self.app.loop
        )

        # 更新录音状态
        self.state.start_recording(self.recording_start_time)

        # 托盘图标反色提示录音中（方案 C，替代 toast 弹窗）
        try:
            self.app.tray.set_recording_state(True)
        except Exception:
            pass

        # 标记"录音提示待显示"：真正的 toast 等音频流首帧到达后再弹出，
        # 避免 mic_only_on_press 模式蓝牙重连延迟期间误导用户。

        # 打印动画：正在录音
        self._status.start()

        # 启动识别任务
        recorder = self._get_recorder()
        self.task = asyncio.run_coroutine_threadsafe(
            recorder.record_and_send(),
            self.app.loop,
        )

        if Config.mic_only_on_press:
            # 异步提交音频流操作，避免阻塞键盘监听回调
            # 只有当流没在传输时才需要 reopen_and_start 重建（蓝牙麦克风需重新协商设备参数,会丢前几个 block）。
            # 若流仍在传输（mic_close_delay 间隔内的连续录音），
            # 直接 start_streaming() 即可（内部判断 _streaming=True 后是 no-op），
            # 流对象保留、回调立刻可用，前几个字不丢。
            if not self.app.stream._streaming:
                self._submit_mic_task(self.app.stream.reopen_and_start)
            else:
                self._submit_mic_task(self.app.stream.start_streaming)

    def cancel(self) -> None:
        """取消录音任务（时间过短）"""
        logger.debug(f"[{self.shortcut.key}] 取消录音任务（时间过短）")

        self.is_recording = False
        self.state.stop_recording()
        # 恢复托盘图标（方案 C）
        try:
            self.app.tray.set_recording_state(False)
        except Exception:
            pass
        self._status.stop()

        self.task.cancel()
        self.task = None

        from config import Config
        if Config.mic_only_on_press:
            # 录音完成，延迟关闭音频流
            self._schedule_close_stream(Config.mic_close_delay)

    def finish(self, force_llm=False) -> None:
        """完成录音任务"""
        logger.info(f"[{self.shortcut.key}] 释放：完成录音")

        self.is_recording = False
        self.state.stop_recording()
        # 恢复托盘图标（方案 C）
        try:
            self.app.tray.set_recording_state(False)
        except Exception:
            pass
        self._status.stop()

        # 设置强制 LLM 润色标志
        if force_llm:
            self.state.force_llm = True
            from config import Config
            logger.info(f"[{self.shortcut.key}] 录音期间检测到 {Config.force_llm_key} 按下，强制启用 LLM 润色")

        asyncio.run_coroutine_threadsafe(
            self.state.queue_in.put({
                'type': 'finish',
                'time': time.time(),
                'data': None
            }),
            self.app.loop
        )

        from config import Config
        if Config.mic_only_on_press:
            # 录音完成，延迟关闭音频流
            self._schedule_close_stream(Config.mic_close_delay)

    def _submit_mic_task(self, fn) -> None:
        """把音频流操作提交到独立线程池异步执行，
        避免阻塞 pynput 键盘事件循环。"""
        if not hasattr(self, '_mic_pool') or self._mic_pool is None:
            self._mic_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f'mic-{self.shortcut.key}'
            )
        self._mic_pool.submit(fn)

    def _schedule_close_stream(self, delay: float) -> None:
        """延迟 N 秒后关闭音频流。
        用于 mic_only_on_press 模式：录音完成不要立刻 stop_streaming，
        而是等一段时间（mic_close_delay 秒），期间若用户又按下快捷键，
        会被 launch() 中的 _cancel_pending_close() 取消，
        避免连续输入时蓝牙麦克风反复重连造成的延迟。"""
        self._cancel_pending_close()
        if delay <= 0:
            return
        timer = threading.Timer(delay, self._do_delayed_close)
        timer.daemon = True
        with self._close_timer_lock:
            self._close_timer = timer
        timer.start()

    def _cancel_pending_close(self) -> None:
        """取消已调度的延迟关闭任务。launch 时调用，避免误关。"""
        with self._close_timer_lock:
            timer = self._close_timer
            self._close_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    def _do_delayed_close(self) -> None:
        """延迟关闭定时器触发时的实际回调。"""
        with self._close_timer_lock:
            self._close_timer = None
        if not hasattr(self.app, 'stream'):
            return
        self._submit_mic_task(self.app.stream.stop_streaming)

    def cleanup(self) -> None:
        """客户端退出时清理本任务持有的资源（主要是取消延迟关闭定时器）。"""
        self._cancel_pending_close()
