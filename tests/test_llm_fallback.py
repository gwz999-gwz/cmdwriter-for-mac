import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.client.llm.llm_exceptions import APIException, AuthenticationErrorWrapper
from core.client.llm.llm_output_typing import handle_typing_mode, output_text
from core.client.llm.llm_processor import LLMProcessor


class _Handler:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def process(self, role_config, content, matched_hotwords):
        if self.error:
            raise self.error
        return self.result


class LLMFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_authentication_error_falls_back_to_original_text(self):
        handler = _Handler(error=AuthenticationErrorWrapper(RuntimeError("bad key"), "qwen"))

        with patch(
            "core.client.llm.llm_output_typing.paste_text", new_callable=AsyncMock
        ) as paste:
            result = await handle_typing_mode(handler, "识别原文", role_config=object())

        self.assertEqual(result, ("识别原文", 0, 0.0, False))
        paste.assert_awaited_once_with("识别原文")

    async def test_empty_model_response_falls_back_and_is_not_processed(self):
        handler = _Handler(result=("", 0, 0.0))

        with patch(
            "core.client.llm.llm_output_typing.paste_text", new_callable=AsyncMock
        ) as paste:
            result = await handle_typing_mode(handler, "识别原文", role_config=object())

        self.assertEqual(result, ("识别原文", 0, 0.0, False))
        paste.assert_awaited_once_with("识别原文")

    async def test_successful_polish_is_marked_processed(self):
        handler = _Handler(result=("润色结果", 4, 0.5))

        with patch(
            "core.client.llm.llm_output_typing.paste_text", new_callable=AsyncMock
        ) as paste:
            result = await handle_typing_mode(handler, "识别原文", role_config=object())

        self.assertEqual(result, ("润色结果", 4, 0.5, True))
        paste.assert_awaited_once_with("润色结果")

    async def test_empty_text_is_never_pasted(self):
        with patch(
            "core.client.llm.llm_output_typing.paste_text", new_callable=AsyncMock
        ) as paste:
            await output_text("")

        paste.assert_not_awaited()


class LLMStreamTests(unittest.TestCase):
    def test_length_finish_reason_is_treated_as_failure(self):
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="未完整结果"),
                    finish_reason="length",
                )
            ],
            usage=None,
        )
        completions = SimpleNamespace(create=lambda **params: iter([chunk]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        config = SimpleNamespace(model="test-model")
        processor = LLMProcessor(client_pool=None)

        with self.assertRaises(APIException):
            processor._process_openai_stream(client, config, [])


if __name__ == "__main__":
    unittest.main()
