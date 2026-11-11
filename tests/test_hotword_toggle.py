import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from config import Config
from core.client.manager.tray_manager import TrayManager
from core.client.output.result_processor import ResultProcessor
from core.client.transcribe.file_transcriber import FileTranscriber
from core.protocol import RecognitionMessage


def recognition_message(text="原始识别。"):
    return RecognitionMessage(
        task_id="hotword-toggle-test",
        is_final=True,
        duration=1.0,
        time_start=1.0,
        time_submit=1.0,
        time_complete=2.0,
        text=text,
        text_accu=text,
        tokens=list(text),
        timestamps=[float(index) for index in range(len(text))],
    )


class TrayHotwordToggleTests(unittest.TestCase):
    def test_menu_contains_checked_hotword_toggle(self):
        app = SimpleNamespace(state=SimpleNamespace(), stream=None)
        manager = TrayManager(app)

        option = next(
            option for option in manager._build_menu_options()
            if option[0] == "🔥 启用热词"
        )

        self.assertIs(option[1].__self__, manager)
        self.assertEqual(option[2], bool(Config.hot))

    def test_toggle_persists_inverse_value_and_restarts(self):
        app = SimpleNamespace(state=SimpleNamespace(), stream=None)
        manager = TrayManager(app)
        manager._update_config_attr = Mock()
        manager._restart_app = Mock()

        with patch.object(Config, "hot", True):
            manager._toggle_hotwords()

        manager._update_config_attr.assert_called_once_with("hot", False)
        manager._restart_app.assert_called_once_with()


class FileTranscriberHotwordToggleTests(unittest.TestCase):
    def test_disabled_hotwords_leave_file_transcript_unchanged(self):
        hotword = SimpleNamespace(
            get_phoneme_corrector=Mock(),
            get_rule_corrector=Mock(),
        )
        transcriber = FileTranscriber.__new__(FileTranscriber)
        transcriber.app = SimpleNamespace(hotword=hotword)
        message = recognition_message()

        with patch.object(Config, "hot", False):
            transcriber._apply_hotwords(message)

        hotword.get_phoneme_corrector.assert_not_called()
        hotword.get_rule_corrector.assert_not_called()
        self.assertEqual(message.text, "原始识别。")
        self.assertEqual(message.text_accu, "原始识别。")


class RealtimeHotwordToggleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_hotwords_skip_all_realtime_hotword_processing(self):
        state = SimpleNamespace(
            last_recognition_text="",
            force_llm=False,
            set_output_text=Mock(),
        )
        hotword = SimpleNamespace(
            get_phoneme_corrector=Mock(),
            get_rule_corrector=Mock(),
        )
        output = SimpleNamespace(output=AsyncMock())
        app = SimpleNamespace(
            state=state,
            hotword=hotword,
            output=output,
            engine=SimpleNamespace(),
            llm=SimpleNamespace(process_and_output=AsyncMock()),
        )
        processor = ResultProcessor(app)

        with (
            patch.object(Config, "hot", False),
            patch.object(Config, "llm_enabled", False),
            patch.object(Config, "traditional_convert", False),
        ):
            await processor._handle_message(recognition_message())

        hotword.get_phoneme_corrector.assert_not_called()
        hotword.get_rule_corrector.assert_not_called()
        output.output.assert_awaited_once_with("原始识别")


if __name__ == "__main__":
    unittest.main()
