import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config import Config
from core.client.audio.stream import AudioStreamManager
from core.client.manager.tray_manager import TrayManager
from core.ui import tk_host, tray


class MicrophoneMenuTests(unittest.TestCase):
    def test_menu_lists_default_and_available_microphones_as_radio_items(self):
        stream = SimpleNamespace(
            device_info="🎤 MacBook 麦克风，声道数：1",
            follows_system_default=False,
            selected_device_id=4,
            get_input_devices=Mock(return_value=[
                {'id': 2, 'name': 'MacBook 麦克风', 'channels': 1, 'hostapi': 'Core Audio'},
                {'id': 4, 'name': '蓝牙耳机', 'channels': 1, 'hostapi': 'Core Audio'},
            ]),
        )
        manager = TrayManager(SimpleNamespace(state=SimpleNamespace(), stream=stream))

        microphone_menu = next(
            option[1] for option in manager._build_menu_options()
            if option[0] == "🎤 选择麦克风"
        )

        self.assertEqual([item[0] for item in microphone_menu[:3]], [
            '跟随系统默认', 'MacBook 麦克风', '蓝牙耳机',
        ])
        self.assertFalse(microphone_menu[0][2](None))
        self.assertFalse(microphone_menu[1][2](None))
        self.assertTrue(microphone_menu[2][2](None))
        self.assertTrue(all(item[3] for item in microphone_menu[:3]))

    def test_successful_selection_is_persisted(self):
        stream = SimpleNamespace(select_input_device=Mock(return_value=True))
        app = SimpleNamespace(state=SimpleNamespace(), stream=stream, base_dir=Path('.'))
        manager = TrayManager(app)
        manager._update_config_attr = Mock()
        manager._refresh_audio_devices = Mock()

        with patch.object(Config, 'mic_device', None):
            manager._select_microphone(4, '蓝牙耳机')
            self.assertEqual(Config.mic_device, '蓝牙耳机')

        stream.select_input_device.assert_called_once_with(4, '蓝牙耳机')
        manager._update_config_attr.assert_called_once_with('mic_device', '蓝牙耳机')
        manager._refresh_audio_devices.assert_called_once_with()


class AudioStreamDeviceTests(unittest.TestCase):
    def test_switch_from_unavailable_input_starts_new_stream_and_queues_tray_updates(self):
        app = SimpleNamespace(state=SimpleNamespace(stream=None, recording=False))
        devices = [{'id': 1, 'name': 'FIIO BTR11', 'channels': 1, 'hostapi': 'Core Audio'}]
        device_info = {'name': 'FIIO BTR11', 'max_input_channels': 1}
        new_stream = Mock()
        menu = Mock()

        with (
            patch.object(Config, 'mic_device', 'MacBook Air麦克风'),
            patch.object(Config, 'mic_only_on_press', False),
            patch.object(tray, '_tray_instance', menu),
            patch.object(tk_host, '_tasks', []),
            patch.object(AudioStreamManager, 'get_input_devices', return_value=devices),
            patch('core.client.audio.stream.sd.query_devices', return_value=device_info),
            patch('core.client.audio.stream.sd.InputStream', return_value=new_stream),
        ):
            app.stream = AudioStreamManager(app)
            manager = TrayManager(app)
            manager._update_config_attr = Mock()
            app.stream.on_device_changed(manager._on_device_changed)

            with ThreadPoolExecutor(max_workers=1) as worker:
                worker.submit(manager._select_microphone, 1, 'FIIO BTR11').result()

            self.assertEqual(menu.mock_calls, [])
            self.assertIs(app.state.stream, new_stream)
            new_stream.start.assert_called_once_with()
            manager._update_config_attr.assert_called_once_with('mic_device', 'FIIO BTR11')
            self.assertEqual(Config.mic_device, 'FIIO BTR11')

            tk_host._pump()
            menu.update_info_text.assert_called_once_with('🎤 FIIO BTR11，声道数：1')
            menu.update_options.assert_called_once()
            mic_options = menu.update_options.call_args.args[0][1][1]
            self.assertTrue(mic_options[1][2](None))

    def test_prepare_opens_saved_microphone_by_device_id(self):
        state = SimpleNamespace(stream=None, recording=False)
        app = SimpleNamespace(state=state, loop=None)
        fake_stream = Mock()
        devices = [
            {'name': 'MacBook 麦克风', 'max_input_channels': 1, 'hostapi': 0},
            {'name': '蓝牙耳机', 'max_input_channels': 1, 'hostapi': 0},
        ]

        def query_devices(device=None, kind=None):
            if device is None and kind is None:
                return devices
            if device == 1:
                return devices[1]
            raise AssertionError((device, kind))

        with (
            patch.object(Config, 'mic_device', '蓝牙耳机'),
            patch('core.client.audio.stream.sd.query_devices', side_effect=query_devices),
            patch('core.client.audio.stream.sd.query_hostapis', return_value=[{'name': 'Core Audio'}]),
            patch('core.client.audio.stream.sd.InputStream', return_value=fake_stream) as input_stream,
        ):
            manager = AudioStreamManager(app)
            result = manager.prepare()

        self.assertIs(result, fake_stream)
        self.assertEqual(manager.selected_device_id, 1)
        self.assertEqual(manager.device_info, '🎤 蓝牙耳机，声道数：1')
        self.assertEqual(input_stream.call_args.kwargs['device'], 1)


if __name__ == '__main__':
    unittest.main()
