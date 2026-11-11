# coding: utf-8
"""macOS 菜单栏“添加热词”处理。"""

from pathlib import Path
import subprocess
import threading
from typing import Optional

from core.client.state import console
from . import logger


def on_add_hotword(base_dir: Optional[str] = None) -> None:
    """打开原生 macOS 输入框；菜单回调立即返回，避免卡住菜单栏。"""
    threading.Thread(
        target=_show_native_dialog_and_save,
        args=(base_dir,),
        name="hotword-dialog",
        daemon=True,
    ).start()


def _show_native_dialog_and_save(base_dir: Optional[str]) -> None:
    script = r'''
tell application "System Events"
    activate
    set dialogResult to display dialog "输入一个热词（也可以粘贴多行）：" ¬
        default answer "" ¬
        buttons {"取消", "添加到热词"} ¬
        default button "添加到热词" ¬
        cancel button "取消" ¬
        with title "CapsWriter — 添加热词"
    return text returned of dialogResult
end tell
'''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        # 用户点击取消时 osascript 返回 1 和 -128，不属于程序错误。
        if result.returncode != 0:
            if "(-128)" not in result.stderr:
                logger.error("无法打开热词输入框: %s", result.stderr.strip())
                console.print(f'[red]无法打开热词输入框: {result.stderr.strip()}[/]')
            return

        hotword_text = result.stdout.rstrip("\n").strip()
        if not hotword_text:
            return

        added, skipped = _save_hotwords(hotword_text, base_dir)
        if added:
            console.print(f'[green]✓[/] 已添加热词: {"、".join(added)}')
        if skipped:
            console.print(f'[yellow]已存在，未重复添加: {"、".join(skipped)}[/]')
    except subprocess.TimeoutExpired:
        logger.warning("热词输入窗口等待超时，已取消")
    except Exception as exc:
        logger.error("处理“添加热词”时发生错误: %s", exc, exc_info=True)
        console.print(f'[red]添加热词失败: {exc}[/]')


def _save_hotwords(text: str, base_dir: Optional[str] = None) -> tuple[list[str], list[str]]:
    """将输入逐行追加到 hot.txt，并跳过已有词条。"""
    hot_file = Path(base_dir or Path.cwd()) / "hot.txt"
    hot_file.touch(exist_ok=True)

    content = hot_file.read_text(encoding="utf-8")
    existing = {
        item.strip()
        for raw_line in content.splitlines()
        if raw_line.strip() and not raw_line.lstrip().startswith("#")
        for item in raw_line.split("|")
        if item.strip()
    }
    requested = list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
    added = [word for word in requested if word not in existing]
    skipped = [word for word in requested if word in existing]

    with hot_file.open("a", encoding="utf-8") as stream:
        if content and not content.endswith("\n") and added:
            stream.write("\n")
        for word in added:
            stream.write(f"{word}\n")

    logger.info("已向 %s 添加 %d 个热词，跳过 %d 个重复词", hot_file, len(added), len(skipped))
    return added, skipped
