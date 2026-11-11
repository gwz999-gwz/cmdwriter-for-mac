# coding: utf-8
"""
音频流管理模块

提供 AudioStreamManager 类用于管理音频输入流，包括流的创建、
启动、停止和设备检测。
"""

from __future__ import annotations

import time
import threading
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import sounddevice as sd

from config import Config
from core.client.state import console
from . import logger

if TYPE_CHECKING:
    from core.client.state import ClientState
    from ..app import CapsWriterClient



class AudioStreamManager:
    """
    音频流管理器

    负责管理音频输入流的生命周期，包括：
    - 检测和选择音频设备
    - 创建和启动音频流
    - 处理音频数据回调
    - 流的重启和关闭

    Attributes:
        state: 客户端状态实例
        sample_rate: 采样率（默认 48000Hz）
        block_duration: 每个数据块的时长（秒，默认 0.05s）
    """

    SAMPLE_RATE = 48000
    BLOCK_DURATION = 0.05  # 50ms

    def __init__(self, app: CapsWriterClient):
        """
        初始化音频流管理器

        Args:
            app: 客户端 App 实例
        """
        self.app = app
        self._channels = 1
        self._device_name = '未知设备'
        self._device_id: Optional[int] = None
        self._preferred_device_name: Optional[str] = getattr(Config, 'mic_device', None)
        self._running = False        # 流对象是否已创建
        self._streaming = False      # 流是否在传输
        self._device_change_callbacks = []  # 设备变更回调列表
        self._stream_ready = threading.Event()
        self._stream_ready.set()    # 初始为"就绪"状态
        self._stream_lock = threading.RLock()

    @property
    def device_info(self) -> str:
        """返回当前音频设备信息（设备名 + 声道数）"""
        return f"🎤 {self._device_name}，声道数：{self._channels}"

    @property
    def selected_device_id(self) -> Optional[int]:
        """当前实际使用的 PortAudio 输入设备编号。None 表示尚未建立音频流。"""
        return self._device_id

    @property
    def follows_system_default(self) -> bool:
        """是否配置为跟随系统默认输入设备。"""
        return self._preferred_device_name is None

    def get_input_devices(self) -> list[dict[str, Any]]:
        """返回当前可用的输入设备，供菜单栏构建麦克风子菜单。"""
        try:
            devices = sd.query_devices()
            host_apis = sd.query_hostapis()
        except Exception as exc:
            logger.warning(f"枚举麦克风失败: {exc}")
            return []

        result = []
        for index, device in enumerate(devices):
            channels = int(device.get('max_input_channels', 0))
            if channels <= 0:
                continue
            hostapi_index = int(device.get('hostapi', -1))
            hostapi_name = ''
            if 0 <= hostapi_index < len(host_apis):
                hostapi_name = host_apis[hostapi_index].get('name', '')
            result.append({
                'id': index,
                'name': device.get('name', f'输入设备 {index}'),
                'channels': channels,
                'hostapi': hostapi_name,
            })
        return result

    def _resolve_device(self) -> tuple[Optional[int], Any]:
        """把保存的设备名解析为本次 PortAudio 设备编号和设备信息。"""
        if self._preferred_device_name:
            for candidate in self.get_input_devices():
                if candidate['name'] == self._preferred_device_name:
                    return candidate['id'], sd.query_devices(candidate['id'], kind='input')
            logger.warning(
                f"已选择的麦克风“{self._preferred_device_name}”当前不可用，临时使用系统默认麦克风"
            )

        device = sd.query_devices(kind='input')
        default_device = sd.default.device
        try:
            device_id = int(default_device[0])
        except (TypeError, ValueError, IndexError):
            device_id = None
        if device_id is not None and device_id < 0:
            device_id = None
        return device_id, device

    def on_device_changed(self, callback) -> None:
        """注册设备变更回调。callback 接收 device_info 字符串参数。"""
        self._device_change_callbacks.append(callback)

    def _notify_device_changed(self) -> None:
        """通知所有注册的回调"""
        info = self.device_info
        for cb in self._device_change_callbacks:
            try:
                cb(info)
            except Exception:
                pass

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags
    ) -> None:
        """
        音频数据回调函数

        当音频流接收到新数据时调用，将数据放入异步队列中。
        录音状态由菜单栏图标反色提示。
        """
        # 只在录音状态时处理数据
        if not self.state.recording:
            return

        import asyncio

        # 将数据放入队列
        if self.app.loop and self.state.queue_in:
            asyncio.run_coroutine_threadsafe(
                self.state.queue_in.put({
                    'type': 'data',
                    'time': time.time(),
                    'data': indata.copy(),
                }),
                self.app.loop
            )

    def _on_stream_finished(self) -> None:
        """音频流结束回调

        注意：sounddevice 的 InputStream.close() 每次都会触发 finished_callback
        （PortAudio 线程），这是 sounddevice 的预期行为，不是异常。
        流生命周期由调用方（mic 池线程）完全管理；此处不应再调 reopen_and_start，
        否则会与 mic 池 reopen_and_start 并发，导致多流并存 bug。
        """
        logger.debug("音频流 finished_callback 触发（sounddevice close 预期行为，无操作）")

    def prepare(self) -> Optional[sd.InputStream]:
        """仅创建音频流对象（不调用 stream.start）。用于 mic_only_on_press
        场景下提前查询设备、保留流对象，等待 start_streaming() 触发。"""
        with self._stream_lock:
            return self._prepare_locked()

    def _prepare_locked(self) -> Optional[sd.InputStream]:
        """prepare 的锁内实现。"""
        if self._running:
            logger.debug("音频流对象已存在，跳过 prepare")
            return self.state.stream

        self._stream_ready.clear()

        # 检测音频设备
        try:
            device_id, device = self._resolve_device()
            self._device_id = device_id
            self._channels = min(2, device['max_input_channels'])
            self._device_name = device.get('name', '未知设备')
            console.print(
                f'使用音频设备：[italic]{self._device_name}，声道数：{self._channels}',
                end='\n\n'
            )
            logger.info(f"找到音频设备: {self._device_name}, 声道数: {self._channels}")
            self._notify_device_changed()
        except UnicodeDecodeError:
            logger.warning("无法获取音频设备名称（编码问题）")
        except sd.PortAudioError:
            logger.error("未找到麦克风设备")
            self._stream_ready.set()
            return None

        # 创建音频流（不启动）
        try:
            stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                blocksize=int(self.BLOCK_DURATION * self.SAMPLE_RATE),
                device=self._device_id,
                dtype="float32",
                channels=self._channels,
                callback=self._audio_callback,
                finished_callback=self._on_stream_finished,
            )

            self.state.stream = stream
            self._running = True
            self._streaming = False
            self._stream_ready.set()
            logger.debug(
                f"音频流对象已创建（未启动）: 采样率={self.SAMPLE_RATE}, "
                f"块大小={int(self.BLOCK_DURATION * self.SAMPLE_RATE)}"
            )
            return stream

        except Exception as e:
            logger.error(f"创建音频流对象失败: {e}", exc_info=True)
            self._stream_ready.set()
            return None

    def start_streaming(self) -> bool:
        """对已存在但未启动的流对象执行 stream.start()。"""
        with self._stream_lock:
            return self._start_streaming_locked()

    def _start_streaming_locked(self) -> bool:
        if not self._running:
            logger.warning("音频流对象未创建，无法启动传输")
            return False
        if self._streaming:
            logger.debug("音频流已在传输中，跳过 start_streaming")
            return True
        stream = self.state.stream
        if stream is None:
            logger.warning("state.stream 为空，无法启动传输")
            return False
        try:
            stream.start()
            self._streaming = True
            logger.debug("音频流传输已启动")
            return True
        except Exception as e:
            logger.error(f"启动音频流传输失败: {e}", exc_info=True)
            return False

    def stop_streaming(self) -> None:
        """对已启动的流执行 stream.stop()（不关闭流对象）。
        等待后台 reopen_and_start 完成后再 stop（最多 2s）。"""
        # 等待后台 reopen_and_start 完成（如果正在进行）
        self._stream_ready.wait(timeout=2.0)
        with self._stream_lock:
            self._stop_streaming_locked()

    def _stop_streaming_locked(self) -> None:

        if not self._running or not self._streaming:
            return

        stream = self.state.stream
        if stream is None:
            self._streaming = False
            return

        self._streaming = False
        try:
            stream.stop()
            logger.debug("音频流传输已停止（流对象保留）")
        except Exception as e:
            logger.warning(f"停止音频流传输时发生错误: {e}")

    def reopen_and_start(self) -> Optional[sd.InputStream]:
        """关闭旧流 + 创建新流 + 启动传输。
        必须在后台线程调用，避免阻塞键盘监听回调。
        注意：不要在这里 sleep，不要重载 PortAudio。"""
        with self._stream_lock:
            return self._reopen_locked(start_after=True)

    def _reopen_locked(self, start_after: bool) -> Optional[sd.InputStream]:
        logger.info("正在重启音频流...")

        # 必须先于 close() 把标志清掉，否则 close 触发的 finished_callback
        # 看到 _streaming=True 会调 reopen_and_start，导致多流并存。
        self._stream_ready.clear()
        self._running = False
        self._streaming = False  # ← 必须先于 close

        # 停止旧流
        if self.state.stream is not None:
            try:
                self.state.stream.close()
                logger.debug("旧音频流已关闭")
            except Exception as e:
                logger.warning(f"关闭旧音频流时发生错误: {e}")
            finally:
                self.state.stream = None

        # 创建并启动新流
        new_stream = self._prepare_locked()
        if new_stream is not None and start_after:
            self._start_streaming_locked()
        else:
            self._stream_ready.set()
        return new_stream

    def select_input_device(self, device_id: Optional[int], device_name: Optional[str]) -> bool:
        """切换输入设备并按录音模式重建音频流。

        device_name 为 None 时恢复“跟随系统默认”。录音过程中不允许切换，
        避免正在识别的一段音频被从中截断。
        """
        with self._stream_lock:
            if self.state.recording:
                logger.warning("录音过程中不能切换麦克风，请结束本次录音后重试")
                return False

            if device_name is not None:
                current = next(
                    (item for item in self.get_input_devices()
                     if item['id'] == device_id and item['name'] == device_name),
                    None,
                )
                if current is None:
                    logger.warning(f"所选麦克风“{device_name}”已不可用，请刷新设备列表")
                    return False

            old_preference = self._preferred_device_name
            start_after = self._streaming or not Config.mic_only_on_press
            self._preferred_device_name = device_name
            new_stream = self._reopen_locked(start_after=start_after)
            if new_stream is not None and (not start_after or self._streaming):
                logger.info(
                    f"麦克风已切换为: {self._device_name}"
                    if device_name is not None else
                    f"麦克风已改为跟随系统默认: {self._device_name}"
                )
                return True

            logger.error("切换麦克风失败，正在恢复之前的设备")
            self._preferred_device_name = old_preference
            self._reopen_locked(start_after=start_after)
            return False

    def start(self) -> Optional[sd.InputStream]:
        """启动音频流（兼容两种调用场景）

        - `_running=False` → 调 `prepare()` + `start_streaming()`（首次启动）
        - `_running=True, _streaming=False` → 直接 `start_streaming()`（托盘"重开音频"可能遇到）

        Returns:
            创建的音频输入流，如果失败返回 None
        """
        if not self._running:
            stream = self.prepare()
            if stream is None:
                return None
            self.start_streaming()
            return stream

        if not self._streaming:
            self.start_streaming()
        return self.state.stream

    def stop(self) -> None:
        """停止音频流"""
        with self._stream_lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if not self._running:
            return

        self._running = False
        self._streaming = False
        if self.state.stream is not None:
            try:
                self.state.stream.close()
                logger.debug("音频流已停止")
            except Exception as e:
                logger.warning(f"停止音频流时发生错误: {e}")
            finally:
                self.state.stream = None
        self._stream_ready.set()

    def reopen(self) -> Optional[sd.InputStream]:
        """
        重新启动音频流

        Returns:
            新创建的音频输入流
        """
        return self.reopen_and_start()
