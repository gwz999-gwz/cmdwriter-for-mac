import unittest

from benchmark_transcription import estimate_speedups, split_audio, thermal_drift


class BenchmarkMathTest(unittest.TestCase):
    def test_split_audio_matches_file_segmentation(self):
        import numpy as np

        audio = np.zeros(300 * 16_000, dtype=np.float32)
        segments = split_audio(audio, segment_duration=60, overlap=4)
        self.assertEqual([len(x[1]) / 16_000 for x in segments], [64, 64, 64, 64, 60])
        self.assertEqual([x[0] for x in segments], [0, 60, 120, 180, 240])

    def test_amdahl_estimate(self):
        stages = {
            "asr_onnx_backend": 20.0,
            "asr_llama_generate": 30.0,
            "aligner_llama_decode": 20.0,
            "aligner_other": 10.0,
        }
        results = estimate_speedups(stages, processing_time=100.0)
        no_alignment = results[0]
        self.assertAlmostEqual(no_alignment["time_saved_percent"], 30.0)
        self.assertAlmostEqual(no_alignment["speedup"], 100.0 / 70.0)

    def test_thermal_drift_uses_normalized_encoder_time(self):
        segments = []
        for encoder_time in (1.0, 1.0, 1.2, 1.2):
            segments.append(
                {
                    "audio_duration": 10.0,
                    "asr": {"encoder": {"backend_time": encoder_time, "total_time": encoder_time}},
                    "aligner": None,
                }
            )
        result = thermal_drift(segments)
        self.assertAlmostEqual(result["metrics"]["asr_encoder"]["drift_percent"], 20.0)
        self.assertEqual(result["status"], "检测到明显后段变慢")


if __name__ == "__main__":
    unittest.main()
