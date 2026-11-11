import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from config import Config, ModelConfig
from core.client.recognition.engine_host import EngineHost
from core.engine.engines.base import EngineCapabilities, RecognitionResult
from core.engine.engines.qwen_common.schema import ForcedAlignItem, ForcedAlignResult
from core.engine.schema import Result, Task
from core.engine.state import WorkerState
from core.engine.worker.pipeline import TaskPipeline


def make_task(*, index=0, final=False, save_srt=True):
    samples = np.zeros(16000, dtype=np.float32)
    return Task(
        type="file",
        data=samples.tobytes(),
        offset=float(index * 60),
        overlap=4.0,
        task_id="file-task",
        is_final=final,
        time_start=1.0,
        time_submit=2.0,
        save_srt=save_srt,
    )


class FakeStream:
    def __init__(self):
        self.result = RecognitionResult()

    def accept_waveform(self, sample_rate, audio):
        self.audio = audio


class FakeRecognizer:
    capabilities = [EngineCapabilities.ASR]

    def __init__(self):
        self.encode_calls = 0
        self.decode_encoded_calls = 0

    def encode_audio(self, samples):
        self.encode_calls += 1
        return "asr-embedding", {"total_time": 0.1}

    def create_stream(self):
        return FakeStream()

    def decode_encoded(self, stream, audio_embd, encoder_perf, **kwargs):
        self.decode_encoded_calls += 1
        self.last_embedding = audio_embd
        stream.result.text = "hello"

    def decode_stream(self, *args, **kwargs):
        raise AssertionError("已有预编码结果时不应重新执行同步编码")


class FakeAligner:
    def __init__(self):
        self.encode_calls = 0
        self.align_encoded_calls = 0

    def encode_audio(self, samples):
        self.encode_calls += 1
        return "aligner-embedding", {"total_time": 0.2}

    def align_encoded(self, audio_embd, encoder_perf, text, **kwargs):
        self.align_encoded_calls += 1
        self.last_embedding = audio_embd
        return ForcedAlignResult(
            items=[ForcedAlignItem(text="hello", start_time=0.0, end_time=1.0)]
        )

    def align(self, *args, **kwargs):
        raise AssertionError("已有预编码结果时不应重新执行同步编码")


class TaskPipelinePrefetchTests(unittest.TestCase):
    def test_srt_prepare_encodes_asr_and_aligner_then_reuses_both(self):
        recognizer = FakeRecognizer()
        aligner = FakeAligner()
        pipeline = TaskPipeline(recognizer, aligner=aligner)
        task = make_task(save_srt=True)

        prepared = pipeline.prepare(task)
        result = pipeline.process(task, prepared=prepared)

        self.assertEqual(recognizer.encode_calls, 1)
        self.assertEqual(recognizer.decode_encoded_calls, 1)
        self.assertEqual(recognizer.last_embedding, "asr-embedding")
        self.assertEqual(aligner.encode_calls, 1)
        self.assertEqual(aligner.align_encoded_calls, 1)
        self.assertEqual(aligner.last_embedding, "aligner-embedding")
        self.assertEqual(result.text, "hello")
        self.assertEqual(result.tokens, ["hello"])

    def test_txt_prepare_skips_forced_aligner(self):
        recognizer = FakeRecognizer()
        aligner = FakeAligner()
        pipeline = TaskPipeline(recognizer, aligner=aligner)
        task = make_task(save_srt=False)

        prepared = pipeline.prepare(task)
        pipeline.process(task, prepared=prepared)

        self.assertEqual(recognizer.encode_calls, 1)
        self.assertEqual(recognizer.decode_encoded_calls, 1)
        self.assertEqual(aligner.encode_calls, 0)
        self.assertEqual(aligner.align_encoded_calls, 0)

    def test_production_config_only_pins_aligner_threads(self):
        self.assertEqual(ModelConfig.asr["onnx_intra_threads"], 0)
        self.assertEqual(ModelConfig.aligner["onnx_intra_threads"], 10)


class ImmediateLoop:
    def call_soon_threadsafe(self, callback, message):
        callback(message)


class SchedulingPipeline:
    def __init__(self):
        self.second_prepared = threading.Event()
        self.prepare_calls = []
        self.process_calls = []
        self.overlap_observed = False

    def prepare(self, task):
        self.prepare_calls.append(task.offset)
        if task.offset == 60.0:
            self.second_prepared.set()
        return SimpleNamespace(samples="prepared", offset=task.offset)

    def process(self, task, prepared=None):
        if task.offset == 0.0:
            self.overlap_observed = self.second_prepared.wait(timeout=1.0)
        self.process_calls.append((task.offset, prepared.offset))
        return Result(
            task_id=task.task_id,
            type=task.type,
            duration=task.offset + 60.0,
            is_final=task.is_final,
        )


class EngineHostPrefetchSchedulingTests(unittest.TestCase):
    def test_next_file_segment_is_prepared_while_current_is_processed(self):
        host = EngineHost.__new__(EngineHost)
        host._task_queue = queue.Queue()
        host._pipeline = SchedulingPipeline()
        host._worker_state = WorkerState()
        host._aligner = object()
        host.app = SimpleNamespace(loop=ImmediateLoop())
        messages = []
        host._dispatch_result = messages.append
        host._ensure_aligner = lambda: None

        host._task_queue.put(make_task(index=0, final=False))
        host._task_queue.put(make_task(index=1, final=True))
        host._task_queue.put(None)

        with mock.patch.object(Config, "file_pipeline_prefetch", True):
            host._inference_loop()

        self.assertTrue(host._pipeline.overlap_observed)
        self.assertEqual(host._pipeline.prepare_calls, [0.0, 60.0])
        self.assertEqual(host._pipeline.process_calls, [(0.0, 0.0), (60.0, 60.0)])
        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[-1].is_final)


if __name__ == "__main__":
    unittest.main()
