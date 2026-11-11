# coding: utf-8
"""
识别结果处理模块

处理本地引擎产生的识别结果。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Optional

from config import Config
from core.client.state import console
from core.protocol import RecognitionMessage

from core.client.output.text_output import TextOutput
from core.client.output.keys import press_enter
from . import logger

from core.tools.zhconv import convert as zhconv_convert

if TYPE_CHECKING:
    from core.client.state import ClientState
    from core.client.app import CapsWriterClient
    from core.client.hotword.manager import HotwordManager



def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


async def _auto_enter(delay: float) -> None:
    """延迟发送回车键"""
    await asyncio.sleep(delay)
    press_enter()
    logger.debug(f"自动回车已发送 (延迟 {delay}s)")


class ResultProcessor:
    """
    识别结果处理器
    
    负责处理本地识别结果：
    - 执行热词替换
    - 可选地调用 LLM 进行润色
    - 输出最终文本
    """
    
    def __init__(self, app: CapsWriterClient):
        """
        初始化结果处理器

        Args:
            app: 客户端 App 实例
        """
        self.app = app
        self._exit_event = asyncio.Event()
        self._loop = asyncio.get_running_loop()  # 保存事件循环引用

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    @property
    def engine(self) -> EngineHost:
        """快捷访问内嵌 ASR 引擎宿主"""
        return self.app.engine

    @property
    def hotword(self) -> HotwordManager:
        """快捷访问热词管理器"""
        return self.app.hotword

    @property
    def output(self) -> TextOutput:
        """快捷访问文本输出器"""
        return self.app.output

    def request_exit(self):
        """请求退出处理循环（线程安全）"""
        logger.info("收到退出请求，设置退出事件")

        # 线程安全地设置事件
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._exit_event.set)
            logger.debug("已通过 call_soon_threadsafe 设置退出事件")
        else:
            self._exit_event.set()
            logger.debug("已直接设置退出事件")
    
    def _format_llm_result(self, llm_result) -> str:
        """格式化 LLM 结果输出"""
        polished_text = llm_result.result
        processed = llm_result.processed
        token_count = llm_result.token_count
        generation_time = llm_result.generation_time  # 使用生成时间（从第一个 token 开始）

        polished_text = polished_text.replace('\n', ' ').replace('\r', ' ')
        max_display_length = 50
        if len(polished_text) > max_display_length:
            polished_text = polished_text[:max_display_length] + '...'

        result_text = f'[green]{polished_text}[/green]' if processed else polished_text

        if token_count == 0 and polished_text:
            token_count = _estimate_tokens(polished_text)

        # 使用生成时间计算速度（更准确）
        if processed and generation_time > 0:
            speed = token_count / generation_time if token_count > 0 else 0
            speed_label = f'    {speed:.1f} tokens/s' if speed > 0 else ''
        else:
            speed_label = ''

        return f'    润色结果：{result_text}{speed_label}'
    
    async def start(self) -> None:
        """开启工作循环：等待内嵌引擎就绪，然后处理识别结果。"""
        try:
            await self.engine.wait_ready()
        except RuntimeError as e:
            console.print(f'[bold red]{e}[/bold red]')
            console.print('[bold red]语音识别模型加载失败，程序即将退出。[/bold red]')
            self.request_exit()
            return

        console.print('[bold green]语音识别模型已就绪[/bold green]\n')

        while not self._exit_event.is_set():
            try:
                message = await self.engine.receive()
                if message is None:
                    break
                await self._handle_message(message)
            except Exception as e:
                logger.debug(f"识别结果接收异常: {e}")
                break
            

    async def _handle_message(self, message: Optional[RecognitionMessage]) -> None:
        """处理接收到的消息"""
        if message is None:
            return


        # 使用 text 字段（简单拼接结果，用于语音输入）
        text = message.text
        original_text = text  # 保存原始识别结果
        delay = message.time_complete - message.time_submit

        if message.is_final:
            logger.info(f"收到最终识别结果: {text}, 时延: {delay:.2f}s")
        else:
            logger.debug(
                f"接收到识别结果，文本: {text[:50]}{'...' if len(text) > 50 else ''}, "
                f"时延: {delay:.2f}s"
            )

        # 如果非最终结果，继续等待
        if not message.is_final:
            return

        # 繁体转换
        if Config.traditional_convert:
            try:
                text = zhconv_convert(text, Config.traditional_locale)
            except Exception as e:
                logger.warning(f"繁体转换失败: {e}")

        # 热词总开关关闭时，不检索、不做规则替换，也不向 LLM 传热词提示。
        matched_hotwords = []
        potential_hotwords = []
        hotword_elapsed = 0.0
        if Config.hot:
            hotword_start = time.monotonic()
            correction_result = self.hotword.get_phoneme_corrector().correct(text, k=10)
            text = correction_result.text
            matched_hotwords = correction_result.matchs
            potential_hotwords = correction_result.similars

        # 2. 去掉末尾符号
        text = TextOutput.strip_punc(text)

        # 3. 正则替换
        if Config.hot and Config.hot_rule:
            text = self.hotword.get_rule_corrector().substitute(text)
        if Config.hot:
            hotword_elapsed = time.monotonic() - hotword_start

        # 保存最近一次识别结果
        self.state.last_recognition_text = text

        # 控制台输出：时延 + 热词时延合并到一行
        hotword_label = f'  热词时延: {hotword_elapsed:.2f}s' if Config.hot else ''
        console.print(f'    转录时延：{delay:.2f}s{hotword_label}')

        # 先显示原始识别结果
        original_text_stripped = TextOutput.strip_punc(original_text)
        console.print(f'    识别结果：[green]{original_text_stripped}')

        # 如果发生了热词替换，显示替换后的结果
        if original_text_stripped != text:
            console.print(f'    热词替换：[cyan]{text}')
            logger.debug(f"热词替换后: {text[:50]}{'...' if len(text) > 50 else ''}")

        # 1. 显示完全匹配/已替换的热词
        if matched_hotwords and Config.hot:
            # 提取热词文本 (现为 (原词, 热词, 分数))
            replaced_info = [f"{origin}->[green4]{hw}[/]" for origin, hw, score in matched_hotwords]
            console.print(f'    完全匹配：{", ".join(replaced_info)}')

        # 2. 潜在热词记录到 log
        if potential_hotwords and Config.hot:
            replaced_set = {hw for origin, hw, score in matched_hotwords}
            potential_matches = [(origin, hw, score) for origin, hw, score in potential_hotwords if hw not in replaced_set]
            if potential_matches:
                log_str = "; ".join([f"{origin}->{hw}({score:.2f})" for origin, hw, score in potential_matches])
                logger.debug(f"潜在热词: {log_str}")

        # 只有本次录音明确按过强制键，才润色当前这一句话。
        llm_result = None
        force_llm = self.state.force_llm
        self.state.force_llm = False
        if force_llm:
            console.print(f'[bold yellow]🔔 录音期间检测到 {Config.force_llm_key} 按下[/bold yellow]')

        if Config.llm_enabled and force_llm:
            llm_result = await self.app.llm.process_and_output(
                text,
                matched_hotwords=potential_hotwords
            )
        else:
            await self.output.output(text)
            self.state.set_output_text(text)

        # LLM 结果显示
        if llm_result and llm_result.processed:
            console.print(self._format_llm_result(llm_result))

        console.line()
