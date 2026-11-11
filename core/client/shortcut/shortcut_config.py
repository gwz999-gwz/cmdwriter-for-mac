# coding: utf-8
"""
快捷键配置数据类

定义 Shortcut 数据结构，用于配置快捷键行为。
避免循环导入：此模块不依赖 config.py。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Shortcut:
    """
    快捷键配置类

    Attributes:
        key: pynput 键盘按键名称，例如 cmd_r、f12 或 a
        threshold: 按下快捷键后触发语音识别的时间阈值（秒），用于防止误触。None 表示使用 Config.threshold
        enabled: 是否启用此快捷键

    注意：
        - 非阻塞模式下，对于可恢复的切换键（CapsLock/NumLock/ScrollLock），会自动补发以恢复状态
        - 在阻塞模式下，短按松开会自动补发按键，不影响单击功能
    """
    key: str
    threshold: Optional[float] = None  # None 表示使用 Config.threshold

    def __post_init__(self):
        """初始化后验证配置"""
        # 规范化键名
        self.key = self._normalize_key(self.key)

    def get_threshold(self, default_threshold: float = 0.3) -> float:
        """
        获取快捷键的阈值

        Args:
            default_threshold: 默认阈值

        Returns:
            float: 阈值（秒）
        """
        return self.threshold if self.threshold is not None else default_threshold

    @staticmethod
    def _normalize_key(key: str) -> str:
        """
        规范化键名

        Args:
            key: 原始键名

        Returns:
            str: 规范化后的键名（pynput 格式）
        """
        # 转小写
        key = key.lower().strip()

        # 替换常见别名
        aliases = {' ': 'space', 'control': 'ctrl'}

        for old, new in aliases.items():
            key = key.replace(old, new)

        # 移除左右修饰符标记（pynput 会自动处理）
        # 保留 'left ctrl' 这样的形式

        return key
