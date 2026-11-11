"""CapsWriter macOS 单机版统一配置。"""

from pathlib import Path

__version__ = '2.6'
BASE_DIR = Path(__file__).resolve().parent


class Config:
    """日常使用设置。"""

    # 输入快捷键：按住右 Command 录音；录音中按右 Option 强制润色。
    shortcut_key = 'cmd_r'
    recording_mode = 'hold'  # hold：按住说话；toggle：按一下开始，再按一下结束
    threshold = 0.3
    force_llm_key = 'alt_r'

    # 识别与纠错
    language = 'auto'
    hot = True  # 热词总开关，同时控制实时识别和音视频文件转录
    hot_rule = True
    hot_thresh = 0.85
    hot_similar = 0.6
    format_num = True
    format_spell = True
    traditional_convert = False
    traditional_locale = 'zh-hant'

    # 文本输出与润色
    trash_punc = '。'
    trash_punc_thresh = 8
    llm_enabled = True

    # 麦克风与录音
    # None 表示跟随 macOS 系统默认输入设备；从菜单栏选择后会自动保存设备名。
    mic_device = None
    mic_only_on_press = False
    mic_close_delay = 600.0
    mic_seg_duration = 60
    mic_seg_overlap = 4
    # 音视频文件转录
    file_seg_duration = 60
    file_seg_overlap = 4
    file_save_json = False
    file_save_merge = False
    # 文件模式下，用一个后台 CPU 线程预编码下一片段；Metal 解码仍保持单路。
    # 麦克风实时识别不使用该优化。
    file_pipeline_prefetch = True

    log_level = 'DEBUG'


class ModelConfig:
    """本地模型路径与推理参数，通常无需修改。"""

    model_dir = Path('models')
    asr_dir = model_dir / 'Qwen3-ASR' / 'Qwen3-ASR-1.7B'
    aligner_dir = model_dir / 'Qwen3-ForcedAligner' / 'Qwen3-ForcedAligner-0.6B'

    asr = {
        'model_dir': asr_dir.as_posix(),
        'encoder_frontend_fn': 'qwen3_asr_encoder_frontend.onnx',
        'encoder_backend_fn': 'qwen3_asr_encoder_backend.onnx',
        'llm_fn': 'qwen3_asr_llm.q5_k.gguf',
        'onnx_provider': 'CPU',
        'llm_use_gpu': True,
        'n_ctx': 2048,
        'chunk_size': 80.0,
        'memory_num': 1,
        'dml_pad_to': 0,
        'verbose': False,
        # ASR 固定线程收益很小，保持 ORT 自动线程以降低长视频热负担。
        'onnx_intra_threads': 0,
    }
    aligner = {
        'model_dir': aligner_dir.as_posix(),
        'encoder_frontend_fn': 'qwen3_aligner_encoder_frontend.int4.onnx',
        'encoder_backend_fn': 'qwen3_aligner_encoder_backend.int4.onnx',
        'llm_fn': 'qwen3_aligner_llm.q5_k.gguf',
        'onnx_provider': 'CPU',
        'llm_use_gpu': True,
        'n_ctx': 3072,
        'dml_pad_to': 0,
        # 5 分钟样本实测：对齐器固定 10 线程比 ORT 自动线程快约 27%，
        # 且识别文本与强制对齐输出逐片一致。
        'onnx_intra_threads': 10,
    }
