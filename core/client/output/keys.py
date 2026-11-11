# coding: utf-8
"""
macOS 按键模拟模块

基于 pynput 提供按键操作。

功能：
1. press_and_release  —— 模拟按下并松开某个按键
2. press_enter()      —— 发送回车
3. get_pressed_keys() —— 返回当前按住的键（调试用）
"""

from typing import List

from core import get_logger

logger = get_logger('client')


# 延迟导入 pynput（无 GUI 环境 / 无辅助功能权限时避免导入失败）
def _get_controller():
    from pynput import keyboard
    return keyboard, keyboard.Controller()


def _resolve_key(key_name: str):
    """将按键名称解析为 pynput 按键对象"""
    from pynput import keyboard

    # 特殊键（Key 枚举成员，如 'enter'、'caps_lock'、'ctrl_l'）
    key_obj = getattr(keyboard.Key, key_name, None)
    if key_obj is not None:
        return key_obj

    # 单个字符键（字母、数字、符号）
    if len(key_name) == 1:
        return keyboard.KeyCode.from_char(key_name)

    return None


def press_and_release(key_name: str) -> None:
    """
    模拟按下并松开一个按键。

    Args:
        key_name: 按键名称（如 'enter'、'caps_lock'、'a'）
    """
    try:
        keyboard, controller = _get_controller()  # noqa: F841
        key = _resolve_key(key_name)
        if key is None:
            logger.warning(f"[{key_name}] 跳过未知按键 / Skipping an unrecognized key")
            return
        controller.press(key)
        controller.release(key)
    except Exception as e:
        logger.warning(f"模拟按键失败 / Could not send key {key_name}: {e}")


def press_enter() -> None:
    """发送回车键"""
    press_and_release('enter')


def get_pressed_keys() -> List[str]:
    """
    返回当前按住的键（仅用于调试日志）。

    原实现读取 boppreh keyboard 库的私有属性 _pressed_events，
    macOS 没有便捷的 pynput 接口读取所有当前按键，
    不影响任何功能。
    """
    return []
