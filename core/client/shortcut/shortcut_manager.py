# coding: utf-8
"""macOS 单快捷键录音管理器。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

from pynput import keyboard

from . import logger
from .shortcut_config import Shortcut
from .task import ShortcutTask

if TYPE_CHECKING:
    from core.client.app import CapsWriterClient
    from core.client.state import ClientState


class ShortcutManager:
    """监听一个普通键盘键：支持按住说话和按一下说话。"""

    def __init__(self, app: CapsWriterClient, shortcut_key: str):
        self.app = app
        self.shortcut = Shortcut(key=shortcut_key)
        self.keyboard_listener: Optional[keyboard.Listener] = None
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._shortcut_pressed = False
        self._force_llm_pressed = False
        self._force_llm_key_name = self._resolve_force_llm_key_name()

        self.task = ShortcutTask(self.app, self.shortcut)
        self.task.pool = self._pool
        from config import Config
        self.recording_mode = getattr(Config, 'recording_mode', 'hold')
        self.task.threshold = self.shortcut.get_threshold(Config.threshold)

    @property
    def state(self) -> ClientState:
        return self.app.state

    @staticmethod
    def _resolve_force_llm_key_name() -> str:
        from config import Config
        return (Config.force_llm_key or '').strip()

    @staticmethod
    def _matches_force_llm_key(key_name: str, configured: str) -> bool:
        if configured == 'alt':
            return key_name in ('alt', 'alt_l', 'alt_r', 'alt_gr')
        return bool(configured) and key_name == configured

    @staticmethod
    def _native_key_name(key) -> Optional[str]:
        try:
            if isinstance(key, keyboard.Key):
                return key.name
            if isinstance(key, keyboard.KeyCode):
                if key.char:
                    return key.char.lower()
                if key.vk is not None:
                    return f'vk_{key.vk}'
        except Exception:
            pass
        return None

    def _on_press(self, key) -> None:
        key_name = self._native_key_name(key)
        if key_name is None:
            return
        if (self.task.is_recording
                and self._matches_force_llm_key(key_name, self._force_llm_key_name)):
            self._force_llm_pressed = True
        if key_name != self.shortcut.key or self._shortcut_pressed:
            return
        self._shortcut_pressed = True
        if self.task.is_recording:
            if self.recording_mode == 'toggle':
                self.task.finish(force_llm=self._force_llm_pressed)
            return
        self._force_llm_pressed = False
        self.task.launch()

    def _on_release(self, key) -> None:
        key_name = self._native_key_name(key)
        if key_name != self.shortcut.key:
            return
        self._shortcut_pressed = False
        if self.recording_mode == 'toggle' or not self.task.is_recording:
            return
        duration = time.time() - self.task.recording_start_time
        if duration < self.task.threshold:
            self.task.cancel()
        else:
            self.task.finish(force_llm=self._force_llm_pressed)

    def start(self) -> None:
        if self.keyboard_listener and self.keyboard_listener.is_alive():
            return
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.keyboard_listener.start()
        mode = '按一下开始，再按一下结束' if self.recording_mode == 'toggle' else '按住说话，松开结束'
        logger.info(f"macOS 键盘监听器已启动: {self.shortcut.key}（{mode}）")

    def stop(self) -> None:
        if self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
            except Exception:
                pass
            self.keyboard_listener = None
        if self.task.is_recording:
            self.task.cancel()
        self.task.cleanup()
        self._pool.shutdown(wait=False)
