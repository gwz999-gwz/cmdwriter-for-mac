# coding: utf-8
"""
识别工作包（单端架构）

保留供单进程内嵌复用的组件：
- pipeline: 推理管线（文本拼接 / 去重 / 格式化）
- audio: 音频片段处理

原多进程 Worker / TaskHandler / 模型加载等，已由
core.client.recognition.engine_host 内嵌到客户端进程取代。
"""

from .. import logger
