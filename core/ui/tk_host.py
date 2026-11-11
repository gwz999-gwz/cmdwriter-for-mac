# coding: utf-8
"""
Tk 主线程托管模块（macOS 专用修复）

背景
----
macOS 的 AppKit 强制要求所有 GUI 操作在主线程执行。CapsWriter 原本把
Tkinter 主循环放到独立子线程里（toast / 对话框管理器），在 macOS 26 + Tk 9.0
下创建任意 Tk 窗口即崩溃：

    *** Terminating app due to uncaught exception 'NSInvalidArgumentException',
        reason: '-[NSApplication macOSVersion]: unrecognized selector sent to instance'

本模块在主线程持有一个隐藏的 Tk 根窗口，并提供线程安全的 run_on_tk() 调度：
任意线程发起的 Tk 操作被排队，由主线程的事件循环执行
（toast/对话框的 root.after 轮询，以及 app.py 主线程驱动的 root.update()）。

用法
----
- 主线程启动时调用一次 start() 创建根窗口并启动队列轮询。
- 任意线程调用 run_on_tk(fn, *args) 把 Tk 操作调度到主线程。
"""

import logging
import threading
import tkinter as tk

_logger = logging.getLogger(__name__)

_root: tk.Tk | None = None
_tasks: list = []                     # [(fn, args, kwargs), ...]
_tasks_lock = threading.Lock()
_active = False
_QUEUE_POLL_MS = 50


def is_main_thread() -> bool:
    """当前是否处于主线程。"""
    return threading.current_thread() is threading.main_thread()


def is_active() -> bool:
    """是否已启用主线程托管（macOS 模式）。"""
    return _active


def get_root() -> tk.Tk | None:
    """返回隐藏的 Tk 根窗口（未创建时为 None）。"""
    return _root


def ensure_root() -> tk.Tk:
    """创建隐藏的 Tk 根窗口（必须从主线程调用）。幂等。"""
    global _root
    if _root is None:
        _root = tk.Tk()
        _root.withdraw()
    return _root


def start() -> None:
    """在主线程创建隐藏 Tk 根窗口并启动队列轮询。幂等。"""
    global _active
    if not is_main_thread():
        raise RuntimeError("tk_host.start() 必须在主线程调用")
    root = ensure_root()
    if not _active:
        _active = True
        root.after(_QUEUE_POLL_MS, _pump)


def run_on_tk(fn, *args, **kwargs) -> None:
    """线程安全：把 fn(*args, **kwargs) 调度到主线程执行。

    调用方若已处于主线程则立即执行，否则排队等待主线程轮询拾取。
    """
    if is_main_thread():
        _invoke(fn, args, kwargs)
        return
    with _tasks_lock:
        _tasks.append((fn, args, kwargs))


def _pump() -> None:
    """主线程轮询：执行排队的 Tk 任务，并继续调度下一次轮询。"""
    global _tasks
    with _tasks_lock:
        batch = _tasks
        _tasks = []
    for fn, args, kwargs in batch:
        _invoke(fn, args, kwargs)
    if _active and _root is not None:
        try:
            _root.after(_QUEUE_POLL_MS, _pump)
        except tk.TclError:
            pass


def _invoke(fn, args, kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:
        _logger.exception("Tk 主线程任务执行失败: %r", fn)
