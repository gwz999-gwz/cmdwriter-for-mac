# coding=utf-8
import os
import time
import numpy as np
from typing import Optional, List
from .inference.asr import QwenASREngine as QwenInternalEngine
from ..qwen_common.schema import ASREngineConfig, MsgType, StreamingMessage
from ..base import BaseASREngine, RecognitionStream, EngineCapabilities, RecognitionResult
from ..language import get_language, ENGINE_QWEN_ASR


class QwenASRStream(RecognitionStream):
    """Qwen-ASR 识别流结构"""
    def __init__(self, sample_rate=16000):
        super().__init__(sample_rate)
        self.audio_data = None

    def accept_waveform(self, sample_rate, audio):
        self.sample_rate = sample_rate
        self.audio_data = audio.astype(np.float32)


class QwenASREngine(BaseASREngine):
    """Qwen-ASR 推理引擎适配器，实现与 FunASREngine 类似的接口"""

    def __init__(self, config: ASREngineConfig):
        super().__init__(config)
        self.engine = QwenInternalEngine(config)

    @property
    def capabilities(self) -> List[EngineCapabilities]:
        """声明具备的能力"""
        return [
            EngineCapabilities.ASR, 
            EngineCapabilities.PUNC
        ]

    def create_stream(self, hotwords: Optional[str] = None) -> QwenASRStream:
        """创建识别流"""
        return QwenASRStream()

    def decode_stream(
        self, 
        stream: QwenASRStream, 
        context: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.4,
        **kwargs
    ):
        """
        解码识别流
        """
        if stream.audio_data is None:
            return

        audio_embd, encoder_perf = self.encode_audio(stream.audio_data)
        self.decode_encoded(
            stream,
            audio_embd,
            encoder_perf,
            context=context,
            language=language,
            temperature=temperature,
        )

    def encode_audio(self, audio_data: np.ndarray):
        """只执行 CPU/ONNX 音频编码，供跨片段预取使用。"""
        sr = 16000
        max_samples = int(self.config.chunk_size * sr)
        if len(audio_data) > max_samples:
            audio_data = audio_data[:max_samples]
        audio_embd, enc_time = self.engine.encoder.encode(audio_data)
        encoder_perf = dict(getattr(self.engine.encoder, "last_performance", {}))
        return audio_embd, encoder_perf or {"total_time": enc_time}

    def decode_encoded(
        self,
        stream: QwenASRStream,
        audio_embd: np.ndarray,
        encoder_perf: dict,
        context: Optional[str] = None,
        language: Optional[str] = None,
        temperature: float = 0.4,
    ):
        """使用已编码 embedding 执行 Prompt 构造和 Metal LLM 解码。"""
        t_decode_start = time.perf_counter()
        t_prompt_start = time.perf_counter()
        mapped_lang = get_language(ENGINE_QWEN_ASR, language) if language else None
        full_embd = self.engine._build_prompt_embd(
            audio_embd=audio_embd,
            prefix_text="", # 这里的 prefix_text 是 Assistant 已说的内容，流式分段时通常为空或使用 context
            context=context,
            language=mapped_lang
        )
        prompt_time = time.perf_counter() - t_prompt_start

        # 4. 执行解码
        res = self.engine._safe_decode(
            full_embd, 
            prefix_text="", 
            rollback_num=5, 
            is_last_chunk=True, 
            temperature=temperature, 
            streaming=False, 
        )

        # 5. 更新结果
        stream.result.text = res.text
        stream.result.performance = {
            "encoder": encoder_perf,
            "prompt_build_time": prompt_time,
            "llama_prefill_time": res.t_prefill,
            "llama_generate_time": res.t_generate,
            "prefill_tokens": res.n_prefill,
            "generate_tokens": res.n_generate,
            "total_time": encoder_perf.get("total_time", 0.0) + time.perf_counter() - t_decode_start,
        }
        # Qwen 纯 ASR 模式下暂不支持 token 级时间戳，由本地流水线补齐。

    def update_hotwords(self, hotwords: List[str]):
        """Qwen 暂不支持热词动态更新"""
        pass

    def cleanup(self):
        """释放资源"""
        self.engine.shutdown()
