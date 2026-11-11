import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import Config
from core.client.shortcut.shortcut_manager import ShortcutManager
from core.client.manager.tray_manager import TrayManager


class RecordingModeTests(unittest.TestCase):
    def manager(self, mode):
        with patch.object(Config, 'recording_mode', mode):
            manager = ShortcutManager(SimpleNamespace(), 'cmd_r')
        self.addCleanup(manager._pool.shutdown, wait=False)
        manager._native_key_name = lambda key: key
        task = SimpleNamespace(is_recording=False, recording_start_time=0, threshold=0.3)
        def launch():
            task.is_recording = True
            task.recording_start_time = time.time()
        def stop(**kwargs):
            task.is_recording = False
        task.launch = Mock(side_effect=launch)
        task.finish = Mock(side_effect=stop)
        task.cancel = Mock(side_effect=stop)
        manager.task = task
        return manager

    def test_toggle_release_does_not_stop_and_repeat_does_not_toggle(self):
        manager = self.manager('toggle')
        manager._on_press('cmd_r')
        manager._on_press('cmd_r')
        manager.task.finish.assert_not_called()
        manager._on_release('cmd_r')
        self.assertTrue(manager.task.is_recording)
        manager._on_press('alt_r')
        manager._on_release('alt_r')
        manager._on_press('cmd_r')
        manager.task.finish.assert_called_once_with(force_llm=True)
        manager._on_press('cmd_r')
        manager._on_release('cmd_r')
        manager._on_press('cmd_r')
        self.assertEqual(manager.task.launch.call_count, 2)
        manager._on_release('cmd_r')
        manager._on_press('cmd_r')
        self.assertEqual(manager.task.finish.call_args.kwargs, {'force_llm': False})

    def test_hold_threshold_and_force_polish(self):
        manager = self.manager('hold')
        manager._on_press('cmd_r')
        manager._on_release('cmd_r')
        manager.task.cancel.assert_called_once()
        manager._on_press('cmd_r')
        manager.task.recording_start_time -= 1
        manager._on_press('alt_r')
        manager._on_release('alt_r')
        manager._on_release('cmd_r')
        manager.task.finish.assert_called_once_with(force_llm=True)

    def test_menu_selection_persists_and_restarts(self):
        tray = TrayManager(SimpleNamespace())
        tray._update_config_attr = Mock()
        tray._restart_app = Mock()
        with patch.object(Config, 'recording_mode', 'hold'):
            options = tray._build_recording_mode_options()
            self.assertTrue(options[0][2])
            self.assertFalse(options[1][2])
            options[0][1]()
            tray._restart_app.assert_not_called()
            options[1][1]()
        tray._update_config_attr.assert_called_once_with('recording_mode', 'toggle')
        tray._restart_app.assert_called_once()

    def test_failed_save_does_not_restart(self):
        tray = TrayManager(SimpleNamespace())
        tray._update_config_attr = Mock(side_effect=OSError('test'))
        tray._restart_app = Mock()
        with patch.object(Config, 'recording_mode', 'hold'):
            tray._set_recording_mode('toggle')
        tray._restart_app.assert_not_called()


if __name__ == '__main__':
    unittest.main()
