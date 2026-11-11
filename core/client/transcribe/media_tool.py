# coding: utf-8
import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from core.client.state import console
from . import logger

class MediaTool:
    """媒体工具类：负责 FFmpeg 相关操作"""

    @staticmethod
    def check_environment() -> bool:
        """检查 FFmpeg 和 ffprobe 环境"""
        ffmpeg_path = shutil.which('ffmpeg')
        ffprobe_path = shutil.which('ffprobe')
        
        if ffmpeg_path is None:
            console.print(
                '[bold red]未找到 FFmpeg / FFmpeg not found[/bold red]\n'
                '请安装 FFmpeg 并确认终端可以找到它。\n'
                'Install FFmpeg and make sure it is on your PATH.\n'
                '[cyan]brew install ffmpeg[/cyan]'
            )
            logger.error("无法转录文件，缺少 FFmpeg / File transcription requires FFmpeg")
            return False

        if ffprobe_path is None:
            console.print(
                '[bold yellow]未找到 ffprobe / ffprobe not found[/bold yellow]\n'
                '转录进度将只显示已处理时长。\n'
                'Progress will show the processed duration only.'
            )
            logger.warning("未找到 ffprobe / ffprobe not found")

        return True

    @staticmethod
    async def get_audio_duration(file: Path) -> float:
        """获取音视频文件时长"""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(file)
        ]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                return float(stdout.decode().strip())
        except Exception as e:
            logger.warning(f"无法通过 ffprobe 获取时长 / ffprobe could not determine the duration: {e}")
        return 0.0

    @staticmethod
    def build_ffmpeg_cmd(file: Path) -> List[str]:
        """构建提取音频的 FFmpeg 命令"""
        return [
            "ffmpeg", "-i", str(file),
            "-f", "f32le", "-ac", "1", "-ar", "16000", "-"
        ]
