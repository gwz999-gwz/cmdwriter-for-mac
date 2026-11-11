# CmdWriter for Mac

macOS 语音输入与音视频转文字工具。语音识别、热词纠错和字幕对齐在 Mac 上本地运行。可选的 AI 润色使用你自行配置的 API。

## 安装

安装脚本使用适用于 Apple 芯片（M 系列）的 llama.cpp 运行库。先在终端安装依赖，再进入项目根目录（含 `start.py` 的目录）执行：

```bash
brew install uv ffmpeg portaudio
uv venv --python 3.13 .venv
uv pip install -r requirements-macos.txt --python .venv/bin/python
bash setup_macos_llama.sh
```

`ffmpeg` 用于音视频文件转录。若菜单设置窗口打不开，可用 `.venv/bin/python -m tkinter` 检查当前 Python 是否支持 Tk。

## 下载和放置模型

在[上游 Models 发布页](https://github.com/HaujetZhao/CapsWriter-Offline/releases/tag/models)的 Assets 中下载并解压：

- `Qwen3-ASR-1.7B-q5_k.zip` 用于麦克风听写和文件转录。
- `Qwen3-ForcedAligner-0.6B.zip` 用于生成 SRT 字幕的时间轴。只使用听写或 TXT 转录时，可跳过这个模型。

在 `start.py` 旁创建 `models` 目录。将解压出的文件按下列结构放置，保留文件名和大小写。若解压后多出一层压缩包同名目录，请把里面的文件移到下图对应目录。

```text
cmdwriter-for-mac/
├── start.py
└── models/
    ├── Qwen3-ASR/
    │   └── Qwen3-ASR-1.7B/
    │       ├── qwen3_asr_encoder_frontend.onnx
    │       ├── qwen3_asr_encoder_backend.onnx
    │       └── qwen3_asr_llm.q5_k.gguf
    └── Qwen3-ForcedAligner/
        └── Qwen3-ForcedAligner-0.6B/
            ├── qwen3_aligner_encoder_frontend.int4.onnx
            ├── qwen3_aligner_encoder_backend.int4.onnx
            └── qwen3_aligner_llm.q5_k.gguf
```

## 使用

1. 直接双击 `启动客户端.command`，进入麦克风语音输入模式。
2. 默认按住右 Command 说话，松开后识别结果输入当前光标位置。菜单栏“说话方式”可切换为“按一下说话”：按一下右 Command 开始录音，说完后再按一下结束。切换会保存设置并自动重启客户端。
3. 配置 AI 润色后，录音过程中按一下右 Option 可润色本句。
4. 双击 `拖放音视频转字幕.command`，再将一个或多个音频、视频文件拖进打开的终端窗口，按回车后为本次任务选择 TXT、SRT 或两者。TXT 模式跳过强制对齐、速度更快；SRT 模式生成精确字幕时间轴。

如果 `启动客户端.command` 已经在运行且模型加载完成，转字幕窗口会自动把文件交给该客户端，复用内存中的模型；客户端未运行时，转字幕窗口才会自行加载模型。文件转录和麦克风识别可以同时提交，内部会按任务隔离并依次使用推理引擎。

首次运行需要在“系统设置 → 隐私与安全性”中，为终端开启麦克风、辅助功能和输入监控权限。授权后需要完全退出并重新打开终端。

## 菜单栏图标

启动成功后，macOS 菜单栏会显示 CapsWriter 图标。点击图标后，在“选择麦克风”子菜单中可以切换 Mac 自带麦克风、蓝牙耳机等输入设备，也可以选择“跟随系统默认”；选择会保存并在下次启动时继续使用。设备刚连接却未显示时，点击子菜单底部的“刷新设备列表”。菜单还可用于复制结果、直接添加热词、启用或关闭热词、修改 AI 润色设置、切换麦克风模式、重开音频、重启或退出。关闭“启用热词”后，麦克风识别和音视频转字幕都不会加载或应用 `hot.txt`、`hot-rule.txt`，该设置会保存并自动重启客户端生效。录音时图标会反色提示，识别和润色结果始终直接输入当前光标位置。

单击 macOS 菜单栏图标即可显示功能菜单。

## 识别增强

- `hot.txt`：音素模糊热词纠错。
- `hot-rule.txt`：正则强制替换。
- `language`：指定识别语言，默认自动判断。
- Qwen Forced Aligner：为文件转录生成精确字幕时间戳。
- LLM 润色：录音时按右 Option 触发。

## 配置

程序设置位于 `config.py`；AI 润色的 API 地址、API Key、模型和提示词可从菜单栏的“修改 AI 润色设置”对话框编辑，首次保存会在根目录创建个人配置 `llm_config.py`。仓库中的 `llm_config_example.py` 留空了 API 地址和密钥，可直接使用离线识别。

## 上游项目

CmdWriter for Mac 的 macOS 实现参考并改编自 Haujet Zhao 的 [CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)。原项目版本及模型资源见 [CapsWriter-Offline Releases](https://github.com/HaujetZhao/CapsWriter-Offline/releases)。上游 MIT 许可证及版权声明见 [LICENSE](LICENSE)。
