# coding: utf-8
"""
CapsWriter Offline 客户端主程序门面类 (Facade)

采用外观模式统一管理音频流 (AudioStreamManager)、
识别结果处理 (ResultProcessor) 和快捷键管理 (ShortcutManager)。
"""

import os
import sys
import time
import asyncio
from pathlib import Path

from .state import ClientState
from . import logger
from config import Config, __version__
from core.tools.signal_handler import register_signal
from .state import console
from .recognition.engine_host import EngineHost
from typing import TYPE_CHECKING, Optional
from .manager import (
    TrayManager,
    MicRunner, FileRunner
)
from .audio.stream import AudioStreamManager
from .shortcut.shortcut_manager import ShortcutManager

from .hotword.manager import HotwordManager
from .llm.llm_handler import LLMHandler
from .output.text_output import TextOutput
from .file_ipc import FileTaskServer



class CapsWriterClient:
    """
    CapsWriter 客户端门面类
    
    管理的外部接口简洁：start()。
    """
    def __init__(self):
        # 确保正确的工作目录
        # 打包环境（PyInstaller）：exe 位于项目根目录（models/、config_*.py 同在）
        if getattr(sys, 'frozen', False):
            self.base_dir = Path(sys.executable).resolve().parent
        else:
            self.base_dir = Path(__file__).parents[2]
        os.chdir(self.base_dir)
            
        # 初始化事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
            
        # 初始化状态容器
        self.state = ClientState(app=self)

        # 初始化热词管理器
        self.hotword = HotwordManager(
            hotword_files=None,
            threshold=Config.hot_thresh,
            similar_threshold=Config.hot_similar
        )

        # 4. 初始化 LLM 润色系统
        self.llm = LLMHandler(app=self)
        
        self.output = TextOutput()
        # 初始化各管理器
        # 内嵌本地 ASR 引擎
        self.engine = EngineHost(self)
        self.tray = TrayManager(self)

        # 实例化硬件资源管理组件
        self.stream = AudioStreamManager(self)
        self.shortcut = ShortcutManager(self, Config.shortcut_key)
        self.file_server = FileTaskServer(self)

    def stop(self):
        """
        统一释放所有资源（硬件、菜单栏、本地引擎和状态）
        """
        logger.info("正在执行 CapsWriterClient 资源释放...")

        # 1. 停止核心运行组件
        self.shortcut.stop()
        self.stream.stop()

        # 2. 托盘资源
        self.tray.stop()

        # 3. 关闭监控
        self.hotword.stop()
        self.llm.stop()
        self.file_server.stop()

        # 4. 释放内嵌 ASR 引擎（停止推理线程 + 卸载模型）
        self.engine.cleanup()

        # 5. 重置 State
        try:
            self.state.reset()
        except Exception as e:
            logger.warning(f"重置状态失败 / Could not reset application state: {e}")

        # 6. 停止事件循环（最后一步，确保前面的异步操作已调度）
        self.loop.stop()

        logger.info("资源释放完成")
        console.print('[green4]再见！ / Goodbye!')


    def start(self, file_output_mode: Optional[str] = None):
        """
        启动客户端 (唯一入口)
        
        自动根据命令行参数识别模式。内部管理异步循环。
        """

        # 注册退出函数
        register_signal(self.stop)

        # 转成绝对路径，避免后续工作目录变化（如模型库导入时）导致相对路径失效
        files = [Path(f).resolve() for f in sys.argv[1:] if os.path.exists(f)]

        if files:
            # 文件转录模式
            runner = FileRunner(self, files, output_mode=file_output_mode)
        else:
            # 麦克风实时模式
            runner = MicRunner(self)

        # 后台线程加载内嵌 ASR 模型
        self.engine.start()
        # 等待模型加载完成，避免 llama.py 导入时切换全局工作目录造成的竞态
        # （否则 hot.txt / 输入文件等相对路径可能解析失败）
        if not self.engine.is_ready:
            console.print('[yellow]正在加载语音识别模型（Qwen3-ASR）… / Loading the Qwen3-ASR model…[/yellow]')
        while not self.engine.is_ready:
            if self.engine.is_failed:
                console.print(f'[bold red]语音识别模型加载失败 / Could not load speech recognition model: {self.engine.load_error}[/bold red]')
                console.print('[bold red]程序退出。 / Exiting.[/bold red]')
                return
            time.sleep(0.1)
        console.print('[green]语音识别模型加载完成 / Speech recognition model loaded[/green]\n')

        self._start_macos(runner)

    def _start_macos(self, runner) -> None:
        """macOS 专用启动：主线程托管 Tk，asyncio 通过周期性 root.update() 同步推进。

        Tk 根窗口由主线程创建（core.ui.tk_host），toast / 对话框的 after 回调
        依赖主线程周期性处理 Tk 事件，因此 asyncio 事件循环仍保留在主线程，
        由 _tk_driver 协程每 10ms 调用一次 root.update() 等效于 mainloop。
        """
        from core.ui import tk_host
        tk_host.start()

        async def _run_with_tk_driver():
            import tkinter as tk
            root = tk_host.get_root()

            async def _tk_driver():
                while True:
                    try:
                        root.update()
                    except tk.TclError:
                        break
                    await asyncio.sleep(0.01)

            driver = asyncio.create_task(_tk_driver())
            try:
                await runner.run()
            finally:
                driver.cancel()
                try:
                    await driver
                except (asyncio.CancelledError, Exception):
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass

        try:
            self.loop.run_until_complete(_run_with_tk_driver())
        except RuntimeError:
            ...
