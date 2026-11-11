"""
LLM 处理器 - 协调器

功能：
1. 加载唯一的润色配置并构建单句消息
2. 提供统一的处理接口
3. 流式输出
"""

from dataclasses import dataclass
from typing import Tuple

from .llm_config_schema import LLMConfig
from .llm_client_pool import ClientPool
from .llm_message_builder import MessageBuilder
from .llm_processor import LLMProcessor
from . import logger


@dataclass
class LLMResult:
    """LLM 处理结果"""
    result: str                    # 润色后的文本
    processed: bool                # 是否经过处理
    token_count: int               # token数
    polish_time: float             # 总耗时（秒）
    input_text: str                # 本次识别文本
    generation_time: float = 0.0   # 生成时间（秒，从第一个 token 开始）


# ======================================================================
# --- LLM 处理器（协调器）---

class LLMHandler:
    """LLM 润色处理器（协调器）"""

    def __init__(self, app):
        logger.info("初始化 LLM 处理器")
        self.app = app

        # 获取热词管理器
        self.hotword_manager = app.hotword

        self.config = self._load_config()
        if self.config is not None:
            logger.info(f"已加载唯一 LLM 润色配置: {self.config.model}")

        # 客户端池
        self.client_pool = ClientPool()

        # 消息构建器
        self.message_builder = MessageBuilder(app)

        # LLM 处理引擎
        self.processor = LLMProcessor(self.client_pool)

    def start(self):
        """LLM 无需额外常驻监控。"""

    def stop(self):
        """释放 LLM 客户端缓存。"""
        self.client_pool.clear()

    @staticmethod
    def _load_config() -> LLMConfig | None:
        """从根目录 llm_config.py 加载唯一的润色配置。"""
        from dataclasses import fields
        import importlib
        try:
            import llm_config
        except ModuleNotFoundError as exc:
            if exc.name != 'llm_config':
                raise
            return None

        # 设置窗口会在运行期间改写该文件，显式 reload 以绕过模块缓存。
        llm_config = importlib.reload(llm_config)

        values = {
            field.name: getattr(llm_config, field.name)
            for field in fields(LLMConfig)
            if hasattr(llm_config, field.name)
        }
        required = ('api_url', 'api_key', 'model', 'system_prompt')
        if any(not values.get(name) for name in required):
            return None
        return LLMConfig(**values)

    def process(self, role_config: LLMConfig, content: str, matched_hotwords=None) -> Tuple[str, int, float]:
        """执行实际的 LLM 模型调用（内部方法）

        Args:
            role_config: 唯一润色配置
            content: 当前一句识别内容
            matched_hotwords: [(hotword, score), ...] 来自 hot_phoneme 的检索结果

        Returns:
            (处理后的文本, 输出token数, 生成时间秒)
        """
        logger.debug(f"开始单句润色 [内容长度: {len(content)}]")

        # 构建消息
        messages = self.message_builder.build_messages(
            role_config, content,
            hotwords=matched_hotwords,
        )
        
        # 使用 LLM 处理引擎执行请求
        result_text, token_count, gen_time = self.processor.process(
            role_config=role_config,
            messages=messages,
        )

        return result_text, token_count, gen_time

    async def process_and_output(self, text: str, matched_hotwords=None) -> LLMResult:
        """
        统一入口：润色并直接输入到当前光标位置。
        
        Args:
            text: 待润色的完整原始文本（含可能的前缀）
            matched_hotwords: 潜在热词列表
        """
        import time
        from .llm_output_typing import handle_typing_mode

        start_time = time.time()
        # 所有结果只通过键盘输入到当前光标位置。
        result, token_count, gen_time, processed = await handle_typing_mode(
            self, text, matched_hotwords, self.config
        )

        # 5. 后置处理
        # 更新全局状态（即便是中断了，也记录已经输出的部分）
        if result:
            self.app.state.set_output_text(result)

        return LLMResult(
            result=result,
            processed=processed,
            token_count=token_count,
            polish_time=time.time() - start_time,
            input_text=text,
            generation_time=gen_time
        )



