# coding: utf-8
from __future__ import annotations
from pathlib import Path
from config import Config
from . import logger


class FileRunner:
    """
    文件模式运行器：负责文件转录模式下的逻辑，包括音视频文件的 ASR 转录和字幕文件的时间轴调整。
    """
    def __init__(self, app, files: list[Path], output_mode: str):
        if output_mode not in {"txt", "srt", "both"}:
            raise ValueError("文件转录须指定 txt、srt 或 both / File transcription requires txt, srt, or both")
        self.app = app
        self.files = files
        self.output_mode = output_mode
        self.save_txt = output_mode in {"txt", "both"}
        self.save_srt = output_mode in {"srt", "both"}

    @property
    def state(self):
        return self.app.state

    @property
    def ws_manager(self):
        return self.app.engine

    async def run(self):
        """文件转录模式主循环 (Coroutine)"""
        from ..transcribe import FileTranscriber, SrtAdjuster
        from ..ui import TipsDisplay
        
        TipsDisplay.show_file_tips()
        
        logger.info(f"待处理文件 / Files queued: {[str(f) for f in self.files]}")
        
        
        # 热词总开关也适用于音视频文件转录。
        if Config.hot:
            self.app.hotword.start()
        else:
            logger.info("文件转录热词已关闭 / Hotwords disabled for file transcription")

        try:
            for file in self.files:

                logger.info(f"正在处理文件 / Processing file: {file}")
                
                # 情况 1：文本类文件，执行 SRT 时间轴调整
                if file.suffix.lower() in ['.txt', '.json', '.srt', '.vtt']:
                    srt_adjuster = SrtAdjuster()
                    srt_adjuster.adjust(file)
                    
                # 情况 2：媒体文件，执行 ASR 识别转录
                else:
                    transcriber = FileTranscriber(
                        self.app,
                        file,
                        save_txt=self.save_txt,
                        save_srt=self.save_srt,
                    )
                    if await transcriber.check():
                        await transcriber.send()
                        await transcriber.receive()
                        await transcriber.close()
                
                logger.info(f"文件处理完成 / File processed: {file}")
            
            logger.info("所有文件已处理完成 / All files processed")

            try:
                input('\n按回车退出 / Press Return to exit\n')
            except EOFError:
                pass  # 非交互环境（如脚本调用）直接退出

        except Exception as e:
            logger.error(f"文件转录异常 / File transcription failed: {e}", exc_info=True)
            raise
        finally:
            self.app.hotword.stop()
