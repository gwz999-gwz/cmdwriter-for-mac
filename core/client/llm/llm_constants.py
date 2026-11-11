"""
LLM 常量配置

集中管理所有魔法数字、默认值和配置常量
"""

class TokenConstants:
    """单次请求的 token 估算常量。"""
    # Token 估算常量
    CHARS_PER_TOKEN_CN = 1.5      # 中文字符：约 1.5 字符 = 1 token
    CHARS_PER_TOKEN_EN = 4.0      # 英文字符：约 4 字符 = 1 token

    # Unicode 中文字符范围
    CN_CHAR_START = '\u4e00'
    CN_CHAR_END = '\u9fff'


# ==================== Token 估算工具 ====================
def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量

    Args:
        text: 待估算的文本

    Returns:
        估算的 token 数量
    """
    if not text:
        return 0

    # 统计中文字符数量
    chinese_chars = sum(
        1 for c in text
        if TokenConstants.CN_CHAR_START <= c <= TokenConstants.CN_CHAR_END
    )

    # 统计非中文字符数量
    other_chars = len(text) - chinese_chars

    # 中文字符：约 1.5 字符 = 1 token
    # 英文和其他字符：约 4 字符 = 1 token
    tokens = int(
        chinese_chars / TokenConstants.CHARS_PER_TOKEN_CN +
        other_chars / TokenConstants.CHARS_PER_TOKEN_EN
    )

    return max(tokens, 1)  # 至少 1 个 token
