# coding: utf-8
"""
CapsWriter-Offline macOS 单机启动脚本

单端架构：录音、内嵌 ASR 识别（Qwen3-ASR）、LLM 润色、文本输出都在同一进程内完成，
不监听网络端口。

用法：
    python start.py                # 麦克风实时语音输入
    python start.py 音频.wav        # 文件转录（可拖拽多个文件）
"""
import argparse
import os
import sys
from pathlib import Path

# 确保项目根目录加入 sys.path，并将工作目录切换到根目录
# （打包环境：exe 位于项目根目录，config_*.py / models / LLM 等均为外部文件）
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
    # 打包环境：core 等已内置于程序包，BASE_DIR 只能放到 sys.path 末尾，
    # 否则外部的 core 源码会遮蔽内置模块
    if str(BASE_DIR) not in sys.path:
        sys.path.append(str(BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)

from core.client.app import CapsWriterClient


def parse_start_args(argv: list[str]) -> tuple[list[str], str | None]:
    """解析启动参数；文件模式必须显式指定本次输出格式。"""
    parser = argparse.ArgumentParser(
        description="CapsWriter Offline 本地语音输入与文件转录"
    )
    parser.add_argument(
        "--output",
        choices=("txt", "srt", "both"),
        help="文件转录输出格式；拖放脚本会在每次任务中询问",
    )
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    if args.files and args.output is None:
        parser.error("文件转录必须用 --output txt、srt 或 both 指定本次输出格式")
    return args.files, args.output


def main():
    files, output_mode = parse_start_args(sys.argv[1:])
    sys.argv = [sys.argv[0], *files]
    CapsWriterClient().start(file_output_mode=output_mode)


if __name__ == '__main__':
    main()
