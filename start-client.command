#!/bin/bash
# =============================================================================
# CapsWriter-Offline 双模式启动器：
#   直接双击：麦克风语音输入
#   将音视频文件拖到本文件上：生成 TXT 和 SRT
# 首次使用需在「系统设置 → 隐私与安全性」中给「终端」授权：
#   麦克风 / 输入监控 / 辅助功能
# =============================================================================
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "未找到虚拟环境 .venv，请先执行一次性准备： / Virtual environment .venv missing. Run the setup commands below."
    echo "    uv venv --python 3.13 .venv"
    echo "    uv pip install -r requirements-macos.txt --python .venv/bin/python"
    echo ""
    read -r -p "按回车键关闭窗口... / Press Return to close..."
    exit 1
fi

if [ "$#" -gt 0 ]; then
    echo "正在启动音视频文件转录... / Starting media transcription..."
    echo "待处理文件数量 / Files queued: $#"
    echo "完成后将在原文件旁生成 TXT 和 SRT。 / TXT and SRT will be saved alongside the source files."
    set -- --output both "$@"
else
    echo "正在启动麦克风语音输入... / Starting microphone dictation..."
    echo "按住右 Command 说话，松开即上屏；说话中按右 Option 强制润色。 / Hold Right Command to speak and release to insert text. Press Right Option while recording to request polishing."
    echo "按 Control+C 或菜单栏图标中的「退出」停止。 / Press Control+C or select Quit in the menu bar to stop."
fi
echo "首次启动会加载语音识别模型，请稍候。 / Loading the speech recognition model. Please wait."
echo "-----------------------------------------------------------------"
exec .venv/bin/python start.py "$@"
