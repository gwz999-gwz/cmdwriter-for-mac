# coding: utf-8
"""AI 润色设置窗口及 llm_config.py 的安全改写工具。"""

import argparse
import ast
import importlib.util
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk


CONFIG_NAMES = ("api_url", "api_key", "model", "system_prompt")


def config_source(config_path: Path) -> Path:
    if config_path.exists():
        return config_path
    return config_path.with_name("llm_config_example.py")


def load_config(config_path: Path) -> dict[str, str]:
    """从指定文件加载设置，不依赖模块缓存。"""
    spec = importlib.util.spec_from_file_location("capswriter_dialog_llm_config", config_source(config_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {config_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: str(getattr(module, name, "")) for name in CONFIG_NAMES}


def update_config(config_path: Path, values: dict[str, str]) -> None:
    """仅替换四个配置赋值，保留文件内的说明、注释和其他设置。"""
    source = config_source(config_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    source_bytes = source.encode("utf-8")
    lines = source_bytes.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    replacements = []
    found = set()
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        name = targets[0].id
        if name not in values:
            continue
        value_node = node.value
        start = offsets[value_node.lineno - 1] + value_node.col_offset
        end = offsets[value_node.end_lineno - 1] + value_node.end_col_offset
        replacements.append((start, end, repr(values[name]).encode("utf-8")))
        found.add(name)

    missing = set(CONFIG_NAMES) - found
    if missing:
        raise RuntimeError(f"配置文件缺少字段: {', '.join(sorted(missing))}")
    for start, end, replacement in sorted(replacements, reverse=True):
        source_bytes = source_bytes[:start] + replacement + source_bytes[end:]

    # 同目录原子替换，避免程序恰好读取到写了一半的配置文件。
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_path.parent,
                                     prefix=".llm_config_", delete=False) as stream:
        stream.write(source_bytes.decode("utf-8"))
        temporary = Path(stream.name)
    temporary.replace(config_path)


class LLMConfigDialog:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.values = load_config(config_path)
        self.root = tk.Tk()
        self.root.title("CapsWriter — AI 润色设置")
        self.root.geometry("720x650")
        self.root.minsize(620, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=18)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(4, weight=1)

        ttk.Label(frame, text="修改后点击保存，新的润色请求会立即使用这些设置。",
                  foreground="#666666").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self.entries = {}
        labels = (("api_url", "API 地址"), ("api_key", "API Key"), ("model", "模型名称"))
        for row, (name, label) in enumerate(labels, start=1):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            entry = ttk.Entry(frame, show="•" if name == "api_key" else "")
            entry.insert(0, self.values[name])
            entry.grid(row=row, column=1, sticky="ew", pady=5)
            self.entries[name] = entry

        ttk.Label(frame, text="系统提示词").grid(row=4, column=0, columnspan=2, sticky="nw", pady=(12, 5))
        prompt_frame = ttk.Frame(frame)
        prompt_frame.grid(row=5, column=0, columnspan=2, sticky="nsew")
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)
        self.prompt = tk.Text(prompt_frame, wrap="word", undo=True, padx=8, pady=8)
        scrollbar = ttk.Scrollbar(prompt_frame, orient="vertical", command=self.prompt.yview)
        self.prompt.configure(yscrollcommand=scrollbar.set)
        self.prompt.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.prompt.insert("1.0", self.values["system_prompt"])

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, pady=(15, 0))
        ttk.Button(buttons, text="取消", command=self.root.destroy).pack(side="left", padx=6)
        ttk.Button(buttons, text="保存设置", command=self._save).pack(side="left", padx=6)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.lift()

    def _save(self) -> None:
        values = {name: entry.get().strip() for name, entry in self.entries.items()}
        values["system_prompt"] = self.prompt.get("1.0", "end-1c").strip()
        empty = [name for name in CONFIG_NAMES if not values[name]]
        if empty:
            messagebox.showwarning("设置不完整", "API 地址、API Key、模型名称和系统提示词都不能为空。")
            return
        try:
            update_config(self.config_path, values)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_path", type=Path)
    args = parser.parse_args()
    LLMConfigDialog(args.config_path.resolve()).run()


if __name__ == "__main__":
    main()
