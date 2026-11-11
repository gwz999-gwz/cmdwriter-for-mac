import tempfile
import unittest
from pathlib import Path

from core.client.manager.file_runner import FileRunner
from core.client.transcribe.result_handler import ResultHandler
from core.protocol import RecognitionMessage
from start import parse_start_args


def recognition_message():
    return RecognitionMessage(
        task_id="output-test",
        is_final=True,
        duration=2.0,
        time_start=1.0,
        time_submit=1.5,
        time_complete=2.0,
        text="Hello world.",
        text_accu="Hello world.",
        tokens=["Hello", "world", "."],
        timestamps=[0.0, 0.8, 1.6],
    )


class StartOutputArgumentTests(unittest.TestCase):
    def test_file_start_requires_explicit_output_mode(self):
        with self.assertRaises(SystemExit):
            parse_start_args(["movie.mkv"])

    def test_selected_mode_is_returned_without_mutating_config(self):
        files, output_mode = parse_start_args(
            ["--output", "srt", "movie.mkv"]
        )
        self.assertEqual(files, ["movie.mkv"])
        self.assertEqual(output_mode, "srt")

    def test_microphone_start_does_not_require_output_mode(self):
        self.assertEqual(parse_start_args([]), ([], None))


class FileRunnerOutputModeTests(unittest.TestCase):
    def test_mode_is_converted_to_per_task_flags(self):
        txt = FileRunner(object(), [Path("a.mkv")], output_mode="txt")
        srt = FileRunner(object(), [Path("a.mkv")], output_mode="srt")
        both = FileRunner(object(), [Path("a.mkv")], output_mode="both")

        self.assertEqual((txt.save_txt, txt.save_srt), (True, False))
        self.assertEqual((srt.save_txt, srt.save_srt), (False, True))
        self.assertEqual((both.save_txt, both.save_srt), (True, True))


class ResultHandlerOutputModeTests(unittest.TestCase):
    def test_txt_mode_only_writes_txt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "sample.mkv"
            ResultHandler.save_results(
                media,
                recognition_message(),
                save_txt=True,
                save_srt=False,
            )

            self.assertTrue(media.with_suffix(".txt").is_file())
            self.assertFalse(media.with_suffix(".srt").exists())

    def test_srt_mode_only_writes_srt_and_preserves_existing_txt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            media = Path(temp_dir) / "sample.mkv"
            txt = media.with_suffix(".txt")
            txt.write_text("existing user text", encoding="utf-8")

            ResultHandler.save_results(
                media,
                recognition_message(),
                save_txt=False,
                save_srt=True,
            )

            self.assertTrue(media.with_suffix(".srt").is_file())
            self.assertEqual(txt.read_text(encoding="utf-8"), "existing user text")


if __name__ == "__main__":
    unittest.main()
