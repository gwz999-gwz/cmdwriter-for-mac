import base64
import queue
import unittest

from core.client.recognition.engine_host import AudioCache, EngineHost
from core.constants import AudioFormat
from core.protocol import AudioMessage


class EngineHostAudioSegmentationTests(unittest.TestCase):
    def setUp(self):
        # _handle_audio_message 只依赖缓存与任务队列；绕过模型加载，令测试
        # 保持快速、确定，并专门覆盖文件分段逻辑。
        self.host = EngineHost.__new__(EngineHost)
        self.host._caches = {}
        self.host._task_queue = queue.Queue()

    @staticmethod
    def _message(data: bytes, *, final: bool = False) -> AudioMessage:
        return AudioMessage(
            task_id="file-task",
            source="file",
            data=base64.b64encode(data).decode("ascii"),
            is_final=final,
            time_start=1.0,
            seg_duration=60,
            seg_overlap=4,
        )

    def test_threshold_submits_one_segment_and_keeps_overlap(self):
        # 复现故障现场：发送进度首次略过 68 秒时，旧实现会无限提交空任务。
        data = bytes(AudioFormat.seconds_to_bytes(68.06))

        self.host._handle_audio_message(self._message(data))

        self.assertEqual(self.host._task_queue.qsize(), 1)
        task = self.host._task_queue.get_nowait()
        self.assertEqual(len(task.data), AudioFormat.seconds_to_bytes(64))
        self.assertEqual(task.offset, 0)
        self.assertFalse(task.is_final)

        cache = self.host._caches["file-task"]
        self.assertAlmostEqual(cache.duration, 8.06, places=2)
        self.assertAlmostEqual(cache.total_duration, 68.06, places=2)

    def test_multiple_segments_advance_by_stride_then_flush_tail(self):
        first = bytes(AudioFormat.seconds_to_bytes(68))
        second = bytes(AudioFormat.seconds_to_bytes(60))

        self.host._handle_audio_message(self._message(first))
        self.host._handle_audio_message(self._message(second))
        self.host._handle_audio_message(self._message(b"", final=True))

        tasks = [self.host._task_queue.get_nowait() for _ in range(3)]
        self.assertEqual([task.offset for task in tasks], [0, 60, 120])
        self.assertEqual(
            [len(task.data) for task in tasks],
            [
                AudioFormat.seconds_to_bytes(64),
                AudioFormat.seconds_to_bytes(64),
                AudioFormat.seconds_to_bytes(8),
            ],
        )
        self.assertEqual([task.is_final for task in tasks], [False, False, True])
        self.assertNotIn("file-task", self.host._caches)


class AudioCacheTests(unittest.TestCase):
    def test_buffered_and_total_durations_are_distinct(self):
        cache = AudioCache()
        cache.chunks = bytes(AudioFormat.seconds_to_bytes(8))
        cache.byte_count = AudioFormat.seconds_to_bytes(68)

        self.assertEqual(cache.duration, 8)
        self.assertEqual(cache.total_duration, 68)


if __name__ == "__main__":
    unittest.main()
