"""Startup tips for dictation and file transcription."""

import os

from rich.markdown import Markdown

from config import Config, __version__
from core.client.state import console

from . import logger


def _format_shortcut_name(key: str) -> str:
    mac_names = {
        'cmd_r': '右 Command / Right Command',
        'cmd': '左 Command / Left Command',
        'alt_r': '右 Option / Right Option',
        'alt_l': '左 Option / Left Option',
        'caps_lock': 'Caps Lock',
    }
    return mac_names.get(key, key.replace('_', ' ').title())


class TipsDisplay:
    @staticmethod
    def _show_project_info() -> None:
        console.rule('[bold #d55252]CmdWriter for Mac[/]')
        console.print(f'版本 / Version: [bold green]{__version__}[/]')
        console.print(f'项目目录 / Project folder: [cyan underline]{os.getcwd()}[/]')
        console.print('识别引擎 / Speech recognition: [cyan underline]Qwen3-ASR[/]')
        console.print(Markdown(
            '[项目主页 / Project homepage](https://github.com/gwz999-gwz/cmdwriter-for-mac)'
        ))

    @staticmethod
    def show_mic_tips() -> None:
        TipsDisplay._show_project_info()
        shortcut = _format_shortcut_name(Config.shortcut_key)
        polish_key = _format_shortcut_name(Config.force_llm_key)
        console.print(f'录音快捷键 / Recording shortcut: [green4]{shortcut}[/]')
        if Config.recording_mode == 'toggle':
            console.print(
                '按一下开始录音，再按一下结束。\n'
                'Press once to start recording and again to stop.'
            )
        else:
            console.print(
                '按住快捷键说话，松开后将文字输入到光标处。\n'
                'Hold the shortcut while speaking, then release it to insert text at the cursor.'
            )
        console.print(
            f'配置 AI 润色后，录音中按 {polish_key} 润色本句。\n'
            f'After configuring AI polishing, press {polish_key} while recording to polish the current utterance.'
        )
        console.print(
            '双击 transcribe-media.command 转录音视频。\n'
            'Double-click transcribe-media.command to transcribe audio or video files.'
        )
        microphone_mode = (
            '仅按下时启用 / Active while recording' if Config.mic_only_on_press
            else '持续启用 / Always active'
        )
        console.print(f'麦克风模式 / Microphone mode: [bold cyan]{microphone_mode}[/]')
        console.line()
        logger.debug('已显示麦克风模式启动提示')

    @staticmethod
    def show_file_tips() -> None:
        TipsDisplay._show_project_info()
        logger.debug('已显示文件转录模式启动提示')
