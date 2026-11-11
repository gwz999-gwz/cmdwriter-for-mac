# coding: utf-8
import os
import re
import subprocess
import sys
import threading

from . import logger
from config import Config


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app):
        self.app = app

    @property
    def state(self):
        return self.app.state

    def _build_menu_options(self):
        """构建 more_options 列表（设备信息 + 功能菜单项）"""
        device_info = self.app.stream.device_info if hasattr(self.app, 'stream') and self.app.stream else '🎤 未知设备'
        return [
            (device_info, None),  # callback=None 表示禁用项，纯展示
            ('🎤 选择麦克风', self._build_microphone_options()),
            ('📋 复制结果', self._copy_last_result),
            ('✨ 添加热词…', self._add_hotword),
            ('🔥 启用热词', self._toggle_hotwords, bool(Config.hot)),
            ('🤖 修改 AI 润色设置', self._edit_llm_config),
            ('🗣️ 说话方式', self._build_recording_mode_options()),
            ('🎙️ 仅按下时启用麦克风', self._toggle_mic_only_on_press, bool(Config.mic_only_on_press)),
            ('♻️ 重开音频', self._restart_audio),
        ]

    def _build_recording_mode_options(self):
        mode = getattr(Config, 'recording_mode', 'hold')
        return [
            ('按住说话（按住 Command，松开结束）',
             lambda icon=None, item=None: self._set_recording_mode('hold'),
             mode == 'hold', True),
            ('按一下说话（按 Command 开始，再按一下结束）',
             lambda icon=None, item=None: self._set_recording_mode('toggle'),
             mode == 'toggle', True),
        ]

    def _set_recording_mode(self, mode):
        if mode not in ('hold', 'toggle') or mode == getattr(Config, 'recording_mode', 'hold'):
            return
        try:
            self._update_config_attr('recording_mode', mode)
        except Exception as exc:
            logger.error(f"切换说话方式失败: {exc}")
            return
        self._restart_app()

    def _build_microphone_options(self):
        """构建麦克风单选子菜单。"""
        stream = getattr(self.app, 'stream', None)
        if stream is None:
            return [('未检测到麦克风', None)]

        options = [(
            '跟随系统默认',
            self._device_callback(None, None),
            lambda _, stream=stream: stream.follows_system_default,
            True,
        )]
        devices = stream.get_input_devices()
        name_counts = {}
        for device in devices:
            name_counts[device['name']] = name_counts.get(device['name'], 0) + 1
        for device in devices:
            label = device['name']
            if name_counts[label] > 1 and device.get('hostapi'):
                label = f"{label} ({device['hostapi']})"
            options.append((
                label,
                self._device_callback(device['id'], device['name']),
                lambda _, device_id=device['id'], stream=stream: (
                    not stream.follows_system_default
                    and stream.selected_device_id == device_id
                ),
                True,
            ))
        options.append(('刷新设备列表', self._refresh_audio_devices))
        return options

    def _device_callback(self, device_id, device_name):
        def callback(icon=None, item=None):
            threading.Thread(
                target=self._select_microphone,
                args=(device_id, device_name),
                name='select-microphone',
                daemon=True,
            ).start()
        return callback

    def _select_microphone(self, device_id, device_name):
        stream = getattr(self.app, 'stream', None)
        if stream is None or not stream.select_input_device(device_id, device_name):
            return
        try:
            self._update_config_attr('mic_device', device_name)
            Config.mic_device = device_name
        except Exception as exc:
            logger.warning(f"保存麦克风选择失败（本次切换仍然有效）: {exc}")
        self._refresh_audio_devices()

    def _refresh_audio_devices(self, icon=None, item=None):
        try:
            from ..ui import update_tray_options
            update_tray_options(self._build_menu_options())
        except Exception as exc:
            logger.warning(f"刷新麦克风菜单失败: {exc}")

    def _on_device_changed(self, device_info: str) -> None:
        """音频设备变更时更新托盘菜单中的设备信息"""
        try:
            from ..ui import update_tray_info
            update_tray_info(device_info)
        except Exception:
            pass

    def start(self):
        """初始化系统托盘图标"""
        try:
            from ..ui import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')

        # 启用托盘
        enable_min_to_tray(
            'CapsWriter Client',
            icon_path,
            exit_callback=self.app.stop,
            more_options=self._build_menu_options(),
        )
        logger.info("托盘图标已启用")

        # 注册设备变更回调：设备切换时自动更新托盘菜单
        if hasattr(self.app, 'stream') and self.app.stream:
            self.app.stream.on_device_changed(self._on_device_changed)

    def stop(self):
        """停止托盘图标"""
        try:
            from ..ui import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")

    def set_recording_state(self, recording: bool):
        """录音开始/结束时切换托盘图标状态（反色提示，替代原 toast 弹窗）。"""
        try:
            from ..ui import set_tray_recording_state
            set_tray_recording_state(recording)
            logger.debug(f"托盘图标状态: {'录音中' if recording else '空闲'}")
        except Exception as e:
            logger.debug(f"更新录音状态图标失败: {e}")

    def _restart_audio(self):
        """重启音频流回调"""
        if hasattr(self.app, 'stream') and self.app.stream:
            self.app.stream.reopen()
            logger.info("用户请求重启音频")

    def _toggle_mic_only_on_press(self, icon=None, item=None):
        """切换配置并重启客户端。"""
        new_value = not bool(Config.mic_only_on_press)
        try:
            self._update_config_attr('mic_only_on_press', new_value)
        except Exception as e:
            logger.error(f"切换 mic_only_on_press 失败: {e}")
            return
        # 启动新进程并退出当前进程
        self._restart_app()

    def _toggle_hotwords(self, icon=None, item=None):
        """切换热词总开关并重启客户端，使所有识别模式使用同一设置。"""
        new_value = not bool(Config.hot)
        try:
            self._update_config_attr('hot', new_value)
        except Exception as e:
            logger.error(f"切换热词功能失败: {e}")
            return
        self._restart_app()

    def _update_config_attr(self, attr_name: str, new_value) -> None:
        """用正则替换 config.py 中 `attr = <值>` 那一行。
        注意：保留原缩进和行尾注释。"""
        config_path = os.path.abspath(os.path.join(self.app.base_dir, 'config.py'))
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if isinstance(new_value, bool):
            value_literal = 'True' if new_value else 'False'
        elif isinstance(new_value, (int, float)):
            value_literal = repr(new_value)
        elif isinstance(new_value, str):
            escaped = new_value.replace('\\', '\\\\').replace("'", "\\'")
            value_literal = f"'{escaped}'"
        else:
            value_literal = repr(new_value)
        pattern = re.compile(
            rf'^(\s*)({re.escape(attr_name)}\s*=\s*)(.+?)([\s]*\#.*)?$',
            re.MULTILINE,
        )
        new_content, count = pattern.subn(
            lambda m: f"{m.group(1)}{m.group(2)}{value_literal}{m.group(4) or ''}",
            content,
        )
        if count == 0:
            raise RuntimeError(f"未在 config.py 中找到属性 {attr_name}")
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        logger.info(f"已改写 config.py: {attr_name} = {value_literal}")

    def _restart_app(self):
        """启动脱离当前 GUI/终端会话的新实例，再退出当前实例。"""
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, *sys.argv[1:]]
        else:
            cmd = [sys.executable, os.path.join(self.app.base_dir, 'start.py'), *sys.argv[1:]]
        subprocess.Popen(
            cmd,
            cwd=self.app.base_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        logger.info(f"已启动新客户端进程: {cmd[0]}")
        self.app.stop()

    def _add_hotword(self, icon=None, item=None):
        """打开热词输入窗口，写入项目根目录的 hot.txt。"""
        from core.ui.hotword_menu_handler import on_add_hotword
        on_add_hotword(self.app.base_dir)

    def _edit_llm_config(self, icon=None, item=None):
        """在独立 GUI 进程中修改 AI 润色设置，避免阻塞菜单栏。"""
        threading.Thread(
            target=self._run_llm_config_dialog,
            name='llm-config-dialog',
            daemon=True,
        ).start()

    def _run_llm_config_dialog(self):
        target = os.path.join(self.app.base_dir, 'llm_config.py')
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'core.ui.llm_config_dialog', target],
                cwd=self.app.base_dir,
                timeout=None,
                check=False,
            )
            if result.returncode != 0:
                logger.error('AI 润色设置窗口异常退出，返回码: %s', result.returncode)
                return

            # 窗口可能是“取消”关闭；重新读取没有副作用，也能确保后续请求使用最新配置。
            self.app.llm.config = self.app.llm._load_config()
            self.app.llm.client_pool.clear()
            if self.app.llm.config is not None:
                logger.info('AI 润色设置已重新加载: %s', self.app.llm.config.model)
        except Exception as exc:
            logger.error('打开或重新加载 AI 润色设置失败: %s', exc, exc_info=True)

    def _copy_last_result(self):
        """复制最后一次识别结果到剪贴板回调"""
        text = self.state.last_output_text
        if text:
            from ..clipboard import copy_to_clipboard
            copy_to_clipboard(text)

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()
