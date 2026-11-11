# coding: utf-8
"""把文件转录任务提交给已经运行的麦克风客户端。

使用仅当前用户可访问的 Unix Domain Socket，不监听 TCP/UDP 网络端口。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import logger
from .state import console

if TYPE_CHECKING:
    from .app import CapsWriterClient


def socket_path(base_dir: Path | None = None) -> Path:
    base = (base_dir or Path(__file__).parents[2]).resolve()
    project_id = hashlib.sha256(str(base).encode("utf-8")).hexdigest()[:12]
    return Path("/tmp") / f"capswriter-{os.getuid()}-{project_id}.sock"


class FileTaskServer:
    """在已加载模型的客户端进程内接收并串行执行文件任务。"""

    def __init__(self, app: "CapsWriterClient"):
        self.app = app
        self.path = socket_path(app.base_dir)
        self._server: asyncio.AbstractServer | None = None
        self._file_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.path.exists():
            try:
                reader, writer = await asyncio.open_unix_connection(str(self.path))
                writer.close()
                await writer.wait_closed()
                raise RuntimeError("已有 CapsWriter 客户端正在提供文件转录服务")
            except (ConnectionRefusedError, FileNotFoundError, OSError):
                self.path.unlink(missing_ok=True)

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.path)
        )
        os.chmod(self.path, 0o600)
        logger.info("文件转录复用服务已启动: %s", self.path)

    def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None
            self.path.unlink(missing_ok=True)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=10)
            request = json.loads(raw.decode("utf-8"))
            requested = request.get("files", [])
            if not isinstance(requested, list):
                raise ValueError("files 必须是路径列表")
            output_mode = request.get("output")
            if output_mode not in {"txt", "srt", "both"}:
                raise ValueError("output 必须是 txt、srt 或 both")

            files = [Path(item).expanduser().resolve() for item in requested]
            async with self._file_lock:
                result = await self._process_files(files, output_mode)
        except Exception as exc:
            logger.error("接收文件转录任务失败: %s", exc, exc_info=True)
            result = {"ok": False, "message": str(exc), "files": []}

        writer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_files(self, files: list[Path], output_mode: str) -> dict:
        from .transcribe import FileTranscriber, SrtAdjuster

        valid_files = [path for path in files if path.is_file()]
        if not valid_files:
            return {"ok": False, "message": "没有可处理的文件", "files": []}

        console.print(
            f"\n[bold cyan]收到复用模型的文件转录任务：{len(valid_files)} 个文件，"
            f"输出 {output_mode.upper()}[/bold cyan]"
        )
        save_txt = output_mode in {"txt", "both"}
        save_srt = output_mode in {"srt", "both"}
        expected_suffixes = ([".txt"] if save_txt else []) + ([".srt"] if save_srt else [])
        completed: list[str] = []
        failed: list[str] = []

        for path in valid_files:
            started_ns = time.time_ns()
            try:
                if path.suffix.lower() in {".txt", ".json", ".srt", ".vtt"}:
                    SrtAdjuster().adjust(path)
                    completed.append(str(path))
                    continue

                transcriber = FileTranscriber(
                    self.app,
                    path,
                    save_txt=save_txt,
                    save_srt=save_srt,
                )
                try:
                    if not await transcriber.check():
                        failed.append(str(path))
                        continue
                    await transcriber.send()
                    await transcriber.receive()
                finally:
                    await transcriber.close()

                outputs = tuple(path.with_suffix(suffix) for suffix in expected_suffixes)
                if all(
                    output.is_file() and output.stat().st_mtime_ns >= started_ns
                    for output in outputs
                ):
                    completed.append(str(path))
                else:
                    failed.append(str(path))
            except Exception as exc:
                logger.error("复用模型转录失败: %s: %s", path, exc, exc_info=True)
                failed.append(str(path))

        ok = not failed
        message = "全部转录完成" if ok else f"完成 {len(completed)} 个，失败 {len(failed)} 个"
        return {
            "ok": ok,
            "message": message,
            "files": completed,
            "failed": failed,
            "output": output_mode,
        }


async def submit_files(files: list[str], output_mode: str) -> int:
    path = socket_path()
    try:
        reader, writer = await asyncio.open_unix_connection(str(path))
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        path.unlink(missing_ok=True)
        return 2  # 没有可复用的客户端，调用方应独立启动

    request = {
        "files": [str(Path(item).expanduser().resolve()) for item in files],
        "output": output_mode,
    }
    writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
    await writer.drain()
    response_raw = await reader.readline()
    writer.close()
    await writer.wait_closed()

    if not response_raw:
        print("已运行的 CapsWriter 客户端没有返回处理结果", file=sys.stderr)
        return 1

    response = json.loads(response_raw.decode("utf-8"))
    print(response.get("message", "文件任务已结束"))
    return 0 if response.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="向已运行的 CapsWriter 提交文件转录任务")
    parser.add_argument("command", choices=["submit"])
    parser.add_argument(
        "--output",
        choices=["txt", "srt", "both"],
        required=True,
    )
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    return asyncio.run(submit_files(args.files, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
