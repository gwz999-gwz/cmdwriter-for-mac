"""
LLM 单句粘贴输出。

等待模型返回完整结果后一次性粘贴，并恢复原剪贴板文本。
"""
from core.tools.asyncio_to_thread import to_thread
from core.client.output.text_output import TextOutput
from core.client.clipboard import paste_text


async def handle_typing_mode(handler, text: str, matched_hotwords=None, role_config=None) -> tuple:
    """获取完整润色结果后一次性粘贴。"""
    from .llm_error_handler import handle_llm_error
    if not role_config:
        result_text = TextOutput.strip_punc(text)
        await output_text(result_text)
        return (result_text, 0, 0.0, False)

    content = text

    try:
        polished_text, token_count, gen_time = await to_thread(
            handler.process, role_config, content, matched_hotwords
        )
        if not polished_text or not polished_text.strip():
            from .llm_exceptions import APIException
            raise APIException("LLM 返回空文本 / The model returned empty text", 'qwen')

        final_text = TextOutput.strip_punc(polished_text)
        if not final_text:
            from .llm_exceptions import APIException
            raise APIException("润色结果经处理后为空 / The polished result was empty after formatting", 'qwen')

        await paste_text(final_text)
        return (final_text, token_count, gen_time, True)

    except Exception as e:
        result_text, processed = handle_llm_error(e, content)
        result_text = TextOutput.strip_punc(result_text)
        await output_text(result_text)
        return (result_text, 0, 0.0, processed)

async def output_text(text: str):
    """粘贴文本并恢复剪贴板。"""
    if not text:
        return
    await paste_text(text)
