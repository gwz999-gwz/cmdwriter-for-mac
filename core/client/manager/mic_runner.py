# coding: utf-8
import asyncio
from . import logger
from ..ui import TipsDisplay
from config import Config, __version__


def _check_macos_accessibility() -> None:
    """macOS：检测辅助功能(Accessibility)权限，缺失时给出明确提示。

    缺少该权限会导致全局按键监听不可用。
    """
    try:
        from HIServices import AXIsProcessTrusted
        if AXIsProcessTrusted():
            return
    except Exception:
        return  # 无法检测时静默跳过，不打扰

    from core.client.state import console
    console.print(
        '[bold yellow]⚠️ 未获得 macOS「辅助功能」权限[/bold yellow]\n'
        '    全局按键监听不可用，录音与强制润色快捷键将无法使用。\n'
        '    请在 [bold]系统设置 → 隐私与安全性 → 辅助功能[/bold] 中勾选本程序'
        '（源码运行勾选「终端」，编译后勾选对应 App），然后重启本程序。\n'
    )


class MicRunner:
    """
    麦克风模式运行器：负责麦克风模式下的资源初始化、识别处理器循环及生命周期监控。
    """
    def __init__(self, app):
        self.app = app
        self.processor = None

    @property
    def state(self):
        return self.app.state

    @property
    def ws_manager(self):
        return self.app.engine

    @property
    def tray_manager(self):
        return self.app.tray

    def start_resources(self):
        """初始化麦克风模式特有资源 (音频硬件、快捷键、UI 托盘)"""
        # 0. 辅助功能权限提示（macOS 热键监听需要）
        _check_macos_accessibility()

        # 1. 音频流（需在托盘之前启动，托盘菜单要显示设备信息）
        if Config.mic_only_on_press:
            logger.info("已启用「仅按下录音快捷键时启用麦克风」，启动时不打开音频流")
            self.app.stream.prepare()       # 只建流不启动，让托盘能看到设备名
        else:
            self.app.stream.start()

        # 2. 托盘
        self.tray_manager.start()

        # 3. UI 提示
        TipsDisplay.show_mic_tips()

        # 4. 开启快捷键监听
        self.app.shortcut.start()
        
        # 5. 开启后台功能 (热词、LLM)
        if Config.hot:
            self.app.hotword.start()
        else:
            logger.info("热词功能已关闭，跳过热词资源加载")
        self.app.llm.start()

    async def run(self):
        """麦克风模式主入口"""
        
        logger.info("=" * 50)
        logger.info(f"CapsWriter Offline Client {__version__} (麦克风模式)")
        logger.info(f"日志级别: {Config.log_level}")
        
        # 1. 资源启动
        await self.app.file_server.start()
        self.start_resources()
        
        # 2. 启动核心处理器 (内部处理连接与循环)
        
        from ..output import ResultProcessor
        self.processor = ResultProcessor(self.app)
        await self.processor.start()
            
