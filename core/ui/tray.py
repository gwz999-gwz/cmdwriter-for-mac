"""macOS 菜单栏图标。"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Optional

from . import logger, tk_host

_exit_callback = None
_tray_instance: Optional['_MenuBarSystem'] = None
_lock = threading.Lock()


def _create_icon(icon_path: Optional[str] = None):
    from PIL import Image, ImageDraw

    if icon_path and os.path.exists(icon_path):
        try:
            return Image.open(icon_path).convert('RGBA').resize((64, 64), Image.Resampling.LANCZOS)
        except Exception as exc:
            logger.warning(f"菜单栏图标加载失败，将使用默认图标: {exc}")

    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=16, fill=(55, 118, 171))
    draw.ellipse((14, 14, 50, 50), fill=(255, 211, 67))
    draw.ellipse((23, 23, 41, 41), fill=(255, 255, 255))
    return image


class _MenuBarSystem:
    def __init__(self, name: str, icon_path: Optional[str], more_options: list):
        import pystray
        from pystray import MenuItem as item

        self.title = name
        self._more_options = more_options
        self._info_item = None
        self._info_text = ''
        self._base_icon = _create_icon(icon_path)
        self.icon = pystray.Icon(
            'capswriter', self._base_icon, title=name,
            menu=self._create_menu(more_options),
        )

    def _create_menu(self, more_options):
        import pystray
        from pystray import MenuItem as item

        items = [item(self.title, lambda: None, enabled=False)]
        for option in more_options or []:
            label, callback, *checked = option
            if isinstance(callback, (list, tuple)):
                menu_item = item(label, self._create_submenu(callback))
            elif callback is None:
                self._info_text = str(label)
                menu_item = item(lambda _: self._info_text, lambda: None, enabled=False)
                self._info_item = self._info_item or menu_item
            elif checked:
                value = checked[0]
                checked_fn = value if callable(value) else lambda _, value=value: value
                radio = bool(checked[1]) if len(checked) > 1 else False
                menu_item = item(label, callback, checked=checked_fn, radio=radio)
            else:
                menu_item = item(label, callback)
            items.append(menu_item)
        items.extend((item('🔄 重启', self._restart), item('❌ 退出', self._exit)))
        return pystray.Menu(*items)

    def _create_submenu(self, options):
        import pystray
        from pystray import MenuItem as item

        items = []
        for option in options:
            label, callback, *properties = option
            if callback is None:
                items.append(item(label, lambda: None, enabled=False))
                continue
            checked = properties[0] if properties else None
            checked_fn = checked if callable(checked) else (
                (lambda _, value=checked: value) if properties else None
            )
            radio = bool(properties[1]) if len(properties) > 1 else False
            items.append(item(label, callback, checked=checked_fn, radio=radio))
        return pystray.Menu(*items)

    def start(self) -> None:
        # AppKit 对象和可见状态都在主线程建立；Tk 的主线程循环负责处理事件。
        self.icon.run_detached(setup=lambda icon: None)
        self.icon.visible = True
        self.icon.update_menu()
        logger.info(f"macOS 菜单栏图标已显示: {self.icon.visible}")

    def update_info_text(self, text: str) -> None:
        if self._info_item:
            self._info_text = text
            self.icon.update_menu()

    def update_options(self, more_options: list) -> None:
        """重新构建菜单，用于刷新热插拔设备和单选状态。"""
        self._more_options = more_options
        self._info_item = None
        self.icon.menu = self._create_menu(more_options)
        self.icon.update_menu()

    def set_recording_state(self, recording: bool) -> None:
        from PIL import Image, ImageOps
        if not recording:
            self.icon.icon = self._base_icon
            return
        rgba = self._base_icon.convert('RGBA')
        red, green, blue, alpha = rgba.split()
        self.icon.icon = Image.merge('RGBA', (
            ImageOps.invert(red), ImageOps.invert(green), ImageOps.invert(blue), alpha
        ))

    def _restart(self, icon, item) -> None:
        try:
            subprocess.Popen([sys.executable, *sys.argv])
        except Exception as exc:
            logger.error(f"重启失败: {exc}")
            return
        self._exit(icon, item)

    def _exit(self, icon, item) -> None:
        if _exit_callback:
            _exit_callback()
        icon.stop()


def enable_min_to_tray(name=None, icon_path=None, exit_callback=None, more_options=None) -> None:
    """显示 macOS 菜单栏图标。保留旧函数名以避免无意义的跨文件改名。"""
    global _tray_instance, _exit_callback
    _exit_callback = exit_callback
    with _lock:
        if _tray_instance is not None:
            return
        try:
            _tray_instance = _MenuBarSystem(name or 'CapsWriter', icon_path, more_options or [])
            _tray_instance.start()
        except Exception as exc:
            _tray_instance = None
            logger.error(f"macOS 菜单栏图标启动失败: {exc}", exc_info=True)


def update_tray_info(text: str) -> None:
    tk_host.run_on_tk(_update_tray_info, text)


def _update_tray_info(text: str) -> None:
    if _tray_instance:
        _tray_instance.update_info_text(text)


def update_tray_options(more_options: list) -> None:
    tk_host.run_on_tk(_update_tray_options, more_options)


def _update_tray_options(more_options: list) -> None:
    if _tray_instance:
        _tray_instance.update_options(more_options)


def set_tray_recording_state(recording: bool) -> None:
    tk_host.run_on_tk(_set_tray_recording_state, recording)


def _set_tray_recording_state(recording: bool) -> None:
    if _tray_instance:
        _tray_instance.set_recording_state(recording)


def stop_tray() -> None:
    global _tray_instance
    if _tray_instance:
        try:
            _tray_instance.icon.stop()
        except Exception:
            pass
    _tray_instance = None
