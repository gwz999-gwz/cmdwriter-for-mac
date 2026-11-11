# coding: utf-8
"""
提示信息显示模块

提供 TipsDisplay 类用于显示启动提示信息。
"""

from __future__ import annotations

import os

from rich.markdown import Markdown

from core.client.state import console
from config import Config, __version__
from . import logger



def _format_shortcut_name(key: str) -> str:
    """
    格式化快捷键名称用于显示

    Args:
        key: 快捷键名称（如 'caps_lock', 'f12'）

    Returns:
        str: 格式化后的名称（如 'CapsLock', 'F12'）
    """
    mac_names = {
        'cmd_r': '右 Command',
        'cmd': '左 Command',
        'alt_r': '右 Option',
        'alt_l': '左 Option',
        'caps_lock': 'Caps Lock',
    }
    return mac_names.get(key, key.replace('_', ' ').title())


def _get_shortcuts_display() -> str:
    """获取录音快捷键的显示字符串。"""
    return _format_shortcut_name(Config.shortcut_key)


class TipsDisplay:
    """
    提示信息显示器
    
    显示客户端启动时的提示信息。
    """
    
    @staticmethod
    def show_mic_tips() -> None:
        """显示麦克风模式的启动提示"""
        shortcuts_display = _get_shortcuts_display()
        recording_instruction = (
            f'按一下快捷键（`{shortcuts_display}`）开始说话，说完后再按一下结束'
            if getattr(Config, 'recording_mode', 'hold') == 'toggle'
            else f'按住快捷键（`{shortcuts_display}`）说话，松开结束'
        )

        console.rule('[bold #d55252]CapsWriter Offline（单端）[/]')
        console.print(f'\n版本：[bold green]{__version__}[/]')

        markdown = f'''

项目地址：https://github.com/HaujetZhao/CapsWriter-Offline

**CapsWriter-Offline** 是一个**完全离线**、单进程运行的 macOS 语音输入工具。

使用步骤：

1. 启动本程序，自动加载语音识别模型（Qwen3-ASR）。
2. {recording_instruction}；录音时菜单栏图标会反色提示。
3. 说话过程中按 `alt_r`（Mac 右 Option，可在 `config.py` 修改）可强制启用 AI 润色。
4. 双击“拖放音视频转字幕.command”，把文件拖进终端后按回车，就可以转录音视频。


特性：

1. **快、准、稳**：完全离线运行，响应极快，支持自动标点、数字 ITN 和中英间距调整。
2. **热词系统**：支持 `hot.txt` 音素级模糊匹配，准确替换专业术语，支持中英。
3. **正则替换**：支持 `hot-rule.txt` 强制替换规则。
4. **LLM 润色**：录音过程中按强制键，只润色当前这一句话；普通语音不会自动触发。
5. **菜单栏管理**：点击菜单栏图标可修改配置、添加热词、复制结果或退出程序。


注意事项：

1. 当前快捷键：`{shortcuts_display}`，可在 `config.py` 中修改。
2. 识别结果默认去除末尾逗句号。
        '''

        console.print(Markdown(markdown), highlight=True)
        console.rule()
        console.print(f'\n当前基文件夹：[cyan underline]{os.getcwd()}[/]')
        console.print(f'\n识别引擎：[cyan underline]本地 Qwen3-ASR[/]')
        console.print(f'\n当前所用快捷键：[green4]{shortcuts_display}[/]')
        if Config.mic_only_on_press:
            console.print(
                '\n麦克风模式：[bold cyan]仅按下录音快捷键时启用[/]'
                '\n（节省蓝牙麦克风电量，可在菜单栏切换）'
            )
        else:
            console.print(
                '\n麦克风模式：[bold cyan]持续启用[/]'
                '\n（可在菜单栏切换为「仅按下时启用」以节省蓝牙麦克风电量）'
            )
        console.line()

        logger.debug("已显示麦克风模式启动提示")
    
    @staticmethod
    def show_file_tips() -> None:
        """显示文件转录模式的启动提示"""
        console.print(f'\n版本：[bold green]{__version__}[/]')

        markdown = '\n项目地址：https://github.com/HaujetZhao/CapsWriter-Offline'
        console.print(Markdown(markdown), highlight=True)
        console.print(f'当前基文件夹：[cyan underline]{os.getcwd()}[/]')
        console.print(f'识别引擎：[cyan underline]本地 Qwen3-ASR[/]')

        logger.debug("已显示文件转录模式启动提示")
