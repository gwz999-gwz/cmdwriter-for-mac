import unittest
from unittest.mock import patch

from core.engine.engines.llama import llama


class OwnedTokenBatchTests(unittest.TestCase):
    def test_batch_keeps_native_token_storage_alive(self):
        native_batch = object()

        with patch.object(llama, "llama_batch_get_one", return_value=native_batch) as make_batch:
            batch = llama.get_one_batch(12345)

        self.assertIs(batch.struct, native_batch)
        self.assertEqual(batch._token_storage[0], 12345)
        make_batch.assert_called_once()
        token_pointer, count = make_batch.call_args.args
        self.assertIs(token_pointer, batch._token_storage)
        self.assertEqual(count, 1)

    def test_decode_token_rejects_out_of_vocab_id_before_native_call(self):
        context = llama.LlamaContext.__new__(llama.LlamaContext)
        context.model = type("Model", (), {"n_vocab": 10})()

        with patch.object(context, "decode") as decode:
            with self.assertRaisesRegex(ValueError, "Token ID 越界"):
                context.decode_token(10)

        decode.assert_not_called()


if __name__ == "__main__":
    unittest.main()
