#!/usr/bin/env bash
# =============================================================================
# 为 macOS 准备 Qwen3-ASR / Fun-ASR-Nano 所需的 llama.cpp 原生库
#
# 重要：llama.cpp 版本必须是 b7798，以匹配当前 Python ctypes 接口。
#       llama.py 的 ctypes 结构体 ABI 是固定的，装错版本（如最新的 b10369）
#       会导致结构体字段错位、加载崩溃。
#
# 脚本会自动：
#   1. 安装 Python 依赖 gguf
#   2. 通过 GitHub API 自动定位 b7798 的 macOS arm64 发布包（兼容 .zip/.tar）
#   3. 下载、解压
#   4. 去除隔离属性 + ad-hoc 签名（否则 macOS 拒绝加载未签名 dylib）
#   5. 复制 .dylib 到 core/engine/engines/llama/bin/ 并做 ABI 自检
#
# 用法：
#   ./setup_macos_llama.sh            # 默认 b7798
#   ./setup_macos_llama.sh b7798      # 指定版本
# =============================================================================
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$BASE_DIR/core/engine/engines/llama/bin"
PYTHON="${PYTHON:-$BASE_DIR/.venv/bin/python}"
VERSION="${1:-b7798}"

echo "==> [1/5] 安装 Python 依赖 gguf"
uv pip install gguf --python "$PYTHON"

# 2. 定位发布包
echo "==> [2/5] 定位 llama.cpp $VERSION 的 macOS arm64 发布包"
URL=""
if command -v python3 >/dev/null; then
  URL="$(curl -s "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/$VERSION" \
    | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    for a in data.get("assets", []):
        n = a["name"]
        if "macos" in n and ("arm64" in n or "aarch64" in n):
            print(a["browser_download_url"]); break
except Exception:
    pass
')"
fi
if [ -z "$URL" ]; then
  echo "    GitHub API 未找到资产，尝试常见文件名..."
  for ext in zip tar tar.gz tgz; do
    cand="https://github.com/ggml-org/llama.cpp/releases/download/$VERSION/llama-${VERSION}-bin-macos-arm64.$ext"
    echo "    尝试: $cand"
    if curl -sfL -o /dev/null "$cand"; then
      URL="$cand"
      break
    fi
  done
fi
if [ -z "$URL" ]; then
  echo "错误：无法自动定位 $VERSION 的 macOS arm64 发布包。"
  echo "请手动打开下面的发布页，下载 macOS (Apple Silicon) 资产，解压后把其中所有"
  echo "  .dylib 复制到 $BIN_DIR 再运行本脚本做签名/自检："
  echo "    https://github.com/ggml-org/llama.cpp/releases/tag/$VERSION"
  exit 1
fi
echo "    下载地址: $URL"

# 3. 下载并解压
echo "==> [3/5] 下载并解压发布包"
TMPBIN="/tmp/llama-${VERSION}-macos-arm64.bin"
curl -L -o "$TMPBIN" "$URL"
EXTRACT_DIR="$(mktemp -d)"
case "$URL" in
  *.zip) unzip -q -o "$TMPBIN" -d "$EXTRACT_DIR" ;;
  *)     tar -xf "$TMPBIN" -C "$EXTRACT_DIR" ;;
esac

# 4. 去隔离 + 签名
echo "==> [4/5] 去除隔离属性并 ad-hoc 签名 dylib"
find "$EXTRACT_DIR" -name "*.dylib" -exec xattr -dr com.apple.quarantine {} \; 2>/dev/null || true
find "$EXTRACT_DIR" -name "*.dylib" -exec codesign --force --sign - {} \; 2>/dev/null || true

# 5. 复制 + ABI 自检
echo "==> [5/5] 复制 .dylib 到 $BIN_DIR"
mkdir -p "$BIN_DIR"
COUNT=0
while IFS= read -r -d '' f; do
  cp -f "$f" "$BIN_DIR/"
  COUNT=$((COUNT + 1))
done < <(find "$EXTRACT_DIR" -name "*.dylib" -print0)
rm -rf "$EXTRACT_DIR" "$TMPBIN"
if [ "$COUNT" -eq 0 ]; then
  echo "警告：发布包中未找到 .dylib"
  exit 1
fi
echo "    已复制 $COUNT 个 .dylib"

# ABI 自检
echo "==> ABI 自检"
if "$PYTHON" -c "
import ctypes, os
lib_dir = r'$BIN_DIR'
class llama_model_params(ctypes.Structure):
    _fields_ = [
        ('devices', ctypes.POINTER(ctypes.c_void_p)),
        ('tensor_buft_overrides', ctypes.POINTER(ctypes.c_void_p)),
        ('n_gpu_layers', ctypes.c_int32),
        ('split_mode', ctypes.c_int32),
        ('main_gpu', ctypes.c_int32),
        ('tensor_split', ctypes.POINTER(ctypes.c_float)),
        ('progress_callback', ctypes.c_void_p),
        ('progress_callback_user_data', ctypes.c_void_p),
        ('kv_overrides', ctypes.POINTER(ctypes.c_void_p)),
        ('vocab_only', ctypes.c_bool),
        ('use_mmap', ctypes.c_bool),
        ('use_direct_io', ctypes.c_bool),
        ('use_mlock', ctypes.c_bool),
        ('check_tensors', ctypes.c_bool),
        ('use_extra_bufts', ctypes.c_bool),
        ('no_host', ctypes.c_bool),
        ('no_alloc', ctypes.c_bool),
    ]
libllama = ctypes.CDLL(os.path.join(lib_dir, 'libllama.dylib'))
libllama.llama_model_default_params.restype = llama_model_params
mp = libllama.llama_model_default_params()
assert mp.use_mmap is True, 'ABI 不匹配: use_mmap=%r' % mp.use_mmap
print('ABI 自检通过 (use_mmap=True)，库版本与 llama.py 兼容')
" 2>/dev/null; then
  echo ""
  echo "完成！本地 Qwen3-ASR 运行库已准备好。"
  echo "    双击 启动客户端.command 即可启动。"
else
  echo ""
  echo "⚠️  ABI 自检未通过：下载的库版本与 llama.py 不兼容（可能仍是最新版而非 $VERSION）。"
  echo "    请确认从 b7798 发布页下载的是 macOS Apple Silicon 资产。"
  exit 1
fi
