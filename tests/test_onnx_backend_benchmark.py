import unittest

from benchmark_onnx_backend import make_options, model_spec


class OnnxBackendBenchmarkTest(unittest.TestCase):
    def test_models_use_expected_input_precision(self):
        import numpy as np

        self.assertEqual(model_spec("asr", 832)[1], np.float16)
        self.assertEqual(model_spec("aligner", 832)[1], np.float32)

    def test_thread_variant_is_accepted(self):
        options = make_options("threads4", 832)
        self.assertEqual(options.intra_op_num_threads, 4)
        self.assertEqual(options.inter_op_num_threads, 1)


if __name__ == "__main__":
    unittest.main()
