#!/bin/bash
# 双击打开后，把一个或多个音频/视频文件拖进终端窗口并按回车。

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 从 Finder 启动时 PATH 往往不包含 Homebrew；FFmpeg 通常安装在以下位置。
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

pause_and_exit() {
    local exit_code="${1:-0}"
    echo ""
    read -r -p "按回车键关闭窗口..." _
    exit "$exit_code"
}

if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    echo "错误：缺少项目的 Python 虚拟环境：$SCRIPT_DIR/.venv"
    echo "请先完成项目依赖安装。"
    pause_and_exit 1
fi

if [ "$#" -eq 0 ]; then
    echo "CapsWriter 音视频转字幕"
    echo "-----------------------------------------------------------------"
    echo "请执行下面两步："
    echo "  1. 在 Finder 中选中一个或多个音频/视频文件。"
    echo "  2. 把它们拖进这个终端窗口，然后按回车。"
    echo ""
    read -e -r -p "请拖入文件：" dropped_line

    if [ -z "$dropped_line" ]; then
        echo "没有收到文件。"
        pause_and_exit 1
    fi

    # Terminal 会把带空格的路径写成 shell 转义形式；用 shlex 安全还原，避免 eval。
    parsed_files=()
    while IFS= read -r parsed_file; do
        parsed_files+=("$parsed_file")
    done < <("$SCRIPT_DIR/.venv/bin/python" -c \
        'import shlex, sys; [print(path) for path in shlex.split(sys.argv[1])]' \
        "$dropped_line")

    set -- "${parsed_files[@]}"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "错误：没有找到 FFmpeg，音视频文件无法读取。"
    echo "可使用 Homebrew 安装：brew install ffmpeg"
    pause_and_exit 1
fi

valid_files=()
for input_file in "$@"; do
    if [ -f "$input_file" ]; then
        valid_files+=("$input_file")
    else
        echo "跳过（不是文件或文件不存在）：$input_file"
    fi
done

if [ "${#valid_files[@]}" -eq 0 ]; then
    echo "错误：没有可处理的文件。"
    pause_and_exit 1
fi

echo "CapsWriter 音视频转字幕"
echo "待处理文件：${#valid_files[@]} 个"
printf '  %s\n' "${valid_files[@]}"
echo ""

echo "请选择本次输出格式："
echo "  1. TXT（最快，不生成精确字幕时间轴）"
echo "  2. SRT（生成精确字幕，不额外输出 TXT）"
echo "  3. TXT + SRT（速度与 SRT 相同）"
output_mode=""
while [ -z "$output_mode" ]; do
    output_choice=""
    if ! read -r -p "请输入 1、2 或 3：" output_choice; then
        echo "没有收到输出格式。"
        pause_and_exit 1
    fi
    case "$output_choice" in
        1) output_mode="txt" ;;
        2) output_mode="srt" ;;
        3) output_mode="both" ;;
        *) echo "输入无效，请输入 1、2 或 3。" ;;
    esac
done

case "$output_mode" in
    txt)
        output_label="TXT"
        expected_extensions=("txt")
        ;;
    srt)
        output_label="SRT"
        expected_extensions=("srt")
        ;;
    both)
        output_label="TXT 和 SRT"
        expected_extensions=("txt" "srt")
        ;;
esac

echo "本次输出：$output_label"
echo ""
echo "正在检查是否有已加载模型的 CapsWriter 客户端……"
"$SCRIPT_DIR/.venv/bin/python" -m core.client.file_ipc submit \
    --output "$output_mode" "${valid_files[@]}"
ipc_status=$?

if [ "$ipc_status" -eq 0 ]; then
    echo "已复用正在运行的 CapsWriter 模型，无需重复加载。"
    pause_and_exit 0
elif [ "$ipc_status" -ne 2 ]; then
    echo "已运行的 CapsWriter 未能完成转录，请查看其窗口或日志。"
    pause_and_exit 1
fi

echo "没有发现可复用的客户端，将在本窗口加载本地语音模型。"
echo "正在加载并转录，请耐心等待……"
echo "完成后将在每个原文件旁生成 $output_label。"
echo "-----------------------------------------------------------------"

run_marker="$(mktemp /tmp/capswriter-transcribe.XXXXXX)"
trap 'rm -f "$run_marker"' EXIT

"$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/start.py" \
    --output "$output_mode" "${valid_files[@]}"
status=$?

missing_outputs=0
for input_file in "${valid_files[@]}"; do
    base_path="${input_file%.*}"
    file_complete=1
    for extension in "${expected_extensions[@]}"; do
        output_file="${base_path}.${extension}"
        if [ ! -f "$output_file" ] || [ ! "$output_file" -nt "$run_marker" ]; then
            file_complete=0
        fi
    done
    if [ "$file_complete" -ne 1 ]; then
        echo "未生成本次转录结果：$input_file"
        missing_outputs=$((missing_outputs + 1))
    fi
done

if [ "$status" -eq 0 ] && [ "$missing_outputs" -eq 0 ]; then
    echo "-----------------------------------------------------------------"
    echo "转录完成。请到原音视频文件所在目录查看 $output_label。"
else
    status=1
    echo "-----------------------------------------------------------------"
    echo "转录未正常完成。请保留本窗口中的错误信息。"
fi

pause_and_exit "$status"
