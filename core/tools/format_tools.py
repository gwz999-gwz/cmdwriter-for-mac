# coding: utf-8
"""
文本格式化工具

提供中英文混排文本的空格调整功能。
主要用于调整识别结果中中英文之间的空格。
"""

from __future__ import annotations
import re
from typing import Match

# 匹配中文字符包围的英文/数字/符号序列
_EN_IN_ZH_PATTERN = re.compile(r"""(?ix)
    ([\u4e00-\u9fa5])?                  # 左侧：中文
    (                                   # 中间：英文数字及常用技术符号序列
        [a-z0-9+#]                      # 起头：字母、数字、+、#
        [a-z0-9\s'.,!+#/_:@%&?-]*       # 中间：允许空格和更多符号 (将 - 移至末尾)
        [a-z0-9+#%]                     # 结尾：字母、数字、+、#、%
        |
        [a-z0-9]                        # 或者：单个字母或数字
    )
    ([\u4e00-\u9fa5])?                  # 右侧：中文
""")


def _merge_parts(words: list[str]) -> str:
    """合并 ASR 输出的碎片化字母/数字序列

    处理两种典型碎片：
    - 全是单字符/数字 → 拼接："C O M F Y" → "COMFY"
    - 单字母 + 字母开头的词 → 融合："F P16" → "FP16"
    """
    if len(words) <= 1:
        return words[0] if words else ''
    if all(len(w) == 1 or w.isdigit() for w in words):
        return ''.join(words)
    if len(words) == 2 and len(words[0]) == 1 and words[0].isalpha() and words[1][0].isalpha():
        return words[0] + words[1]
    return ' '.join(words)


def _replacer(match: Match) -> str:
    left, raw, right = (match.group(i) or '' for i in (1, 2, 3))
    center = _merge_parts(raw.strip().split())
    has_alpha = bool(re.search(r'[a-zA-Z]', center))

    if left and has_alpha:
        left += ' '
    if right and has_alpha:
        right = ' ' + right

    return f'{left}{center}{right}'



def adjust_space(text: str) -> str:
    """
    调整中英文/数字之间的空格

    1. 在中文和英文、数字之间插入空格。
    2. 将连续的单个英文字母（如 "A B C"）合并为 "ABC"。
    3. 支持常用技术符号如 C++, TCP/IP, 100%。

    因为正则匹配不重叠，同一中文字符只能当一个边界。
    迭代替换可解决相邻中英文边界连续出现的场景。

    Args:
        text: 输入文本

    Returns:
        优化后的文本
    """
    for _ in range(3):
        new_text = _EN_IN_ZH_PATTERN.sub(_replacer, text)
        if new_text == text:
            break
        text = new_text
    return text

