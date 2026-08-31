#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MarkItDown 图形化转换工具

功能：
- 拖拽文件或点击「选择文件」添加要转换的文件
- 自动把文件转换为 Markdown
- 输出目录默认与源文件同目录，可自定义
- 不支持的格式 / 缺少依赖 / 转换失败会给出提示
"""

import base64
import mimetypes
import os
import queue
import re
import threading
from pathlib import Path
from urllib.parse import unquote_to_bytes

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD

from markitdown import (
    MarkItDown,
    UnsupportedFormatException,
    FileConversionException,
    MissingDependencyException,
    MarkItDownException,
)

OUTPUT_EXT = ".md"

# ---- 主题配色（现代浅色）----
BG = "#F3F4F8"
CARD = "#FFFFFF"
FG = "#1F2937"
MUTED = "#6B7280"
ACCENT = "#3B82F6"
ACCENT_DARK = "#2563EB"
ACCENT_LIGHT = "#DBEAFE"
BORDER = "#E5E7EB"

# 匹配 Markdown 中的 data URI 图片，如 ![alt](data:image/png;base64,...)
_IMG_MARKDOWN_RE = re.compile(r"!\[([^\]]*)\]\((data:[^)]+)\)")


def _data_uri_to_bytes(data_uri):
    """解析 data URI，返回 (mimetype, bytes)；解析失败返回 (None, None)。"""
    if not data_uri.startswith("data:"):
        return None, None
    try:
        header, _, payload = data_uri[5:].partition(",")
        mime = header.split(";")[0] or "text/plain"
        if ";base64" in header:
            data = base64.b64decode(payload)
        else:
            data = unquote_to_bytes(payload)
        return mime, data
    except Exception:
        return None, None


def _mime_to_ext(mime):
    """MIME 类型映射为文件扩展名。"""
    ext = mimetypes.guess_extension(mime)
    return ext if ext else ".bin"


def _extract_images(markdown, src, out_dir):
    """把 Markdown 中的 base64 图片提取为独立文件，引用改为相对路径。

    - 图片保存到 <out_dir>/<原文件名>_images/ 下，命名 image_<序号>.<扩展名>
    - Markdown 中的 ![](data:...) 替换为 ![](<原文件名>_images/<文件名>)
    - 没有图片、数据为空或提取失败时原样返回
    """
    if not _IMG_MARKDOWN_RE.search(markdown):
        return markdown
    folder = f"{src.stem}_images"
    for ch in '\\/:*?"<>|':  # 清理目录名中的非法字符
        folder = folder.replace(ch, "_")
    images_dir = out_dir / folder
    images_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    def _repl(m):
        nonlocal count
        alt, uri = m.group(1), m.group(2)
        mime, data = _data_uri_to_bytes(uri)
        if mime is None or not mime.startswith("image/"):
            return m.group(0)  # 非图片，保持原样
        if not data:
            return m.group(0)  # 空数据（如被截断的 data URI），跳过
        count += 1
        fname = f"image_{count}{_mime_to_ext(mime)}"
        try:
            (images_dir / fname).write_bytes(data)
        except Exception:
            return m.group(0)
        return f"![{alt}]({folder}/{fname})"

    return _IMG_MARKDOWN_RE.sub(_repl, markdown)


_md_lock = threading.Lock()
_md_instance = None


def _get_markitdown():
    """惰性创建全局 MarkItDown 实例（magika 首次加载较慢，只加载一次）。"""
    global _md_instance
    with _md_lock:
        if _md_instance is None:
            _md_instance = MarkItDown()
        return _md_instance


def _convert_one(src, out_dir, out_name, seq, total):
    """在后台线程中转换单个文件。返回 (src, kind, detail)。

    kind: ok / unsupported / missing_dep / failed / write_error / error

    out_name 为用户自定义输出文件名（不含扩展名），多文件时自动追加序号。
    """
    src = Path(src)
    try:
        md = _get_markitdown()
        # keep_data_uris=True：保留完整 base64，供后续提取为独立图片文件
        result = md.convert(str(src), keep_data_uris=True)
    except UnsupportedFormatException:
        return (src, "unsupported", None)
    except MissingDependencyException as exc:
        return (src, "missing_dep", str(exc))
    except FileConversionException as exc:
        return (src, "failed", str(exc))
    except MarkItDownException as exc:
        return (src, "error", str(exc))
    except Exception as exc:  # 兜底，避免后台线程崩溃
        return (src, "error", f"{type(exc).__name__}: {exc}")

    # 确定输出路径：指定目录则输出到该目录，否则输出到源文件同目录
    target_dir = Path(out_dir) if out_dir else src.parent
    if out_name:
        # 用户自定义文件名；多文件时追加序号避免覆盖
        name = out_name if total <= 1 else f"{out_name}_{seq}"
        if not name.lower().endswith(OUTPUT_EXT):
            name += OUTPUT_EXT
        out_path = target_dir / name
    else:
        out_path = target_dir / (src.stem + OUTPUT_EXT)
        if out_path.resolve() == src.resolve():
            # 防止转换 Markdown 源文件时覆盖原文件
            out_path = target_dir / (src.stem + "_converted" + OUTPUT_EXT)
    try:
        # 把内嵌的 base64 图片提取为独立文件，引用改为相对路径
        markdown_text = _extract_images(result.markdown, src, target_dir)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(markdown_text)
        return (src, "ok", out_path)
    except Exception as exc:
        return (src, "write_error", f"{type(exc).__name__}: {exc}")


class MarkItDownApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MarkItDown 文件转 Markdown")
        self.root.geometry("760x600")
        self.root.minsize(600, 460)
        self.root.configure(bg=BG)

        self.file_paths = []
        self.result_queue = queue.Queue()
        self.busy = False
        self.total_count = 0
        self.ok_count = 0
        self.bad_count = 0
        self.last_md_path = None
        self.last_out_dir = None

        self._build_ui()
        self._poll_queue()

    # ---------- 界面 ----------
    def _apply_style(self):
        """应用现代浅色主题样式。"""
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Card.TLabel", background=CARD, foreground=FG)

        # 主按钮（蓝色填充）
        style.configure(
            "TButton",
            background=ACCENT,
            foreground="white",
            borderwidth=0,
            focusthickness=0,
            padding=(18, 9),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "TButton",
            background=[
                ("active", ACCENT_DARK),
                ("pressed", ACCENT_DARK),
                ("disabled", "#9CA3AF"),
            ],
            foreground=[("active", "white"), ("disabled", "white")],
        )

        # 次级按钮（白色描边）
        style.configure(
            "Secondary.TButton",
            background=CARD,
            foreground=FG,
            borderwidth=1,
            padding=(14, 7),
            font=("Segoe UI", 10),
        )
        style.map(
            "Secondary.TButton",
            background=[
                ("active", ACCENT_LIGHT),
                ("pressed", ACCENT_LIGHT),
                ("disabled", "#F3F4F6"),
            ],
            foreground=[("disabled", "#9CA3AF")],
        )

        # 输入框
        style.configure(
            "TEntry",
            fieldbackground=CARD,
            foreground=FG,
            bordercolor=BORDER,
            lightcolor=CARD,
            darkcolor=CARD,
            padding=6,
        )
        style.map("TEntry", bordercolor=[("focus", ACCENT)])

        # 进度条
        style.configure(
            "TProgressbar",
            background=ACCENT,
            troughcolor="#E5E7EB",
            borderwidth=0,
            thickness=10,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )

        # 滚动条
        style.configure(
            "Vertical.TScrollbar",
            background="#CBD5E1",
            troughcolor=BG,
            borderwidth=0,
            arrowsize=12,
        )
        style.map("Vertical.TScrollbar", background=[("active", "#94A3B8")])

    def _build_ui(self):
        self._apply_style()
        pad = {"padx": 16, "pady": 6}

        # ---- 顶部品牌横幅 ----
        header = tk.Frame(self.root, bg=ACCENT, height=62)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="MarkItDown", bg=ACCENT, fg="white",
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left", padx=(18, 0), pady=14)
        tk.Label(
            header, text="文件一键转 Markdown", bg=ACCENT, fg="#DBEAFE",
            font=("Segoe UI", 10),
        ).pack(side="left", padx=(10, 0), pady=14)
        self.status_label = tk.Label(
            header, text="就绪", bg=ACCENT, fg="#DBEAFE", font=("Segoe UI", 10)
        )
        self.status_label.pack(side="right", padx=18, pady=14)

        # ---- 提示条 ----
        ttk.Label(
            self.root,
            text="拖拽文件到下方列表，或点击「选择文件」添加。支持一次处理多个文件。",
            style="Muted.TLabel",
        ).pack(anchor="w", **pad)

        # ---- 文件列表卡片 ----
        card1 = tk.Frame(
            self.root, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card1.pack(fill="both", expand=True, **pad)

        list_header = tk.Frame(card1, bg=CARD)
        list_header.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(
            list_header, text="待转换文件", bg=CARD, fg=FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        self.file_count_label = tk.Label(
            list_header, text="共 0 个文件", bg=CARD, fg=MUTED, font=("Segoe UI", 9)
        )
        self.file_count_label.pack(side="right")

        self.file_list = tk.Listbox(
            card1, bg=CARD, fg=FG, selectbackground=ACCENT,
            selectforeground="white", borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), activestyle="none", selectmode="extended",
        )
        scroll = ttk.Scrollbar(card1, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.pack(
            side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12)
        )
        scroll.pack(side="right", fill="y", padx=(0, 12), pady=(0, 12))

        # 拖拽支持
        self.file_list.drop_target_register(DND_FILES)
        self.file_list.dnd_bind("<<Drop>>", self.on_drop)

        # 文件操作按钮
        btn_row = tk.Frame(self.root, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 2))
        ttk.Button(btn_row, text="选择文件", command=self.choose_files).pack(side="left")
        ttk.Button(
            btn_row, text="移除选中", style="Secondary.TButton",
            command=self.remove_selected,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            btn_row, text="清空列表", style="Secondary.TButton",
            command=self.clear_list,
        ).pack(side="left", padx=(10, 0))

        # ---- 输出设置卡片 ----
        card2 = tk.Frame(
            self.root, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card2.pack(fill="x", **pad)

        row_dir = tk.Frame(card2, bg=CARD)
        row_dir.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(row_dir, text="输出目录", bg=CARD, fg=FG).pack(side="left")
        self.out_dir_var = tk.StringVar()
        out_entry = ttk.Entry(row_dir, textvariable=self.out_dir_var)
        out_entry.pack(side="left", fill="x", expand=True, padx=(12, 8))
        ttk.Button(
            row_dir, text="浏览…", style="Secondary.TButton",
            command=self.choose_out_dir,
        ).pack(side="left")

        row_name = tk.Frame(card2, bg=CARD)
        row_name.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(row_name, text="输出文件名", bg=CARD, fg=FG).pack(side="left")
        self.out_name_var = tk.StringVar()
        name_entry = ttk.Entry(row_name, textvariable=self.out_name_var)
        name_entry.pack(side="left", fill="x", expand=True, padx=(12, 8))
        tk.Label(
            row_name, text="留空用源文件名；多文件自动加序号",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9),
        ).pack(side="left")

        # ---- 转换按钮 + 进度 ----
        action_row = tk.Frame(self.root, bg=BG)
        action_row.pack(fill="x", **pad)
        self.convert_btn = ttk.Button(
            action_row, text="开始转换", command=self.start_convert
        )
        self.convert_btn.pack(side="left")
        ttk.Button(
            action_row, text="打开生成的 md", style="Secondary.TButton",
            command=self.open_md,
        ).pack(side="left", padx=(10, 0))
        ttk.Button(
            action_row, text="打开输出目录", style="Secondary.TButton",
            command=self.open_out_dir,
        ).pack(side="left", padx=(10, 0))
        self.progress = ttk.Progressbar(action_row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(16, 0))

        # ---- 转换记录卡片 ----
        card3 = tk.Frame(
            self.root, bg=CARD, highlightbackground=BORDER, highlightthickness=1
        )
        card3.pack(fill="both", expand=True, **pad)
        tk.Label(
            card3, text="转换记录", bg=CARD, fg=FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self.log_text = tk.Text(
            card3, height=7, state="disabled", wrap="word",
            bg=CARD, fg=FG, borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 9),
        )
        log_scroll = ttk.Scrollbar(card3, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(
            side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12)
        )
        log_scroll.pack(side="right", fill="y", padx=(0, 12), pady=(0, 12))

    def log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ---------- 文件操作 ----------
    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self.add_paths(paths)

    def choose_files(self):
        paths = filedialog.askopenfilenames(title="选择要转换的文件")
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        added = 0
        for p in paths:
            path = Path(p)
            if path.is_dir():
                self.log(f"忽略目录（请拖入具体文件）：{path}")
                continue
            if not path.exists():
                self.log(f"文件不存在：{path}")
                continue
            self.file_paths.append(path)
            added += 1
        self._refresh_list()
        if added:
            self.log(f"已添加 {added} 个文件")

    def remove_selected(self):
        selected = list(self.file_list.curselection())
        if not selected:
            return
        for idx in reversed(selected):
            del self.file_paths[idx]
        self._refresh_list()

    def clear_list(self):
        self.file_paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.file_list.delete(0, "end")
        for p in self.file_paths:
            self.file_list.insert("end", str(p))
        self.file_count_label.config(text=f"共 {len(self.file_paths)} 个文件")

    def choose_out_dir(self):
        d = filedialog.askdirectory(title="选择输出目录（留空则与源文件同目录）")
        if d:
            self.out_dir_var.set(d)

    def open_md(self):
        """打开最近生成的 md 文件。"""
        if self.last_md_path and Path(self.last_md_path).exists():
            os.startfile(str(self.last_md_path))
        else:
            messagebox.showinfo("提示", "还没有可打开的转换结果。")

    def open_out_dir(self):
        """打开最近一次输出所在的文件夹。"""
        if self.last_out_dir and Path(self.last_out_dir).exists():
            os.startfile(str(self.last_out_dir))
        else:
            messagebox.showinfo("提示", "还没有输出目录。")

    # ---------- 转换 ----------
    def start_convert(self):
        if self.busy:
            return
        if not self.file_paths:
            messagebox.showinfo("提示", "请先添加要转换的文件。")
            return

        out_dir = self.out_dir_var.get().strip()
        if out_dir:
            out_dir_path = Path(out_dir)
            if not out_dir_path.exists():
                try:
                    out_dir_path.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    messagebox.showerror("错误", f"无法创建输出目录：\n{exc}")
                    return
            out_dir = str(out_dir_path)

        self.busy = True
        self.total_count = len(self.file_paths)
        self.ok_count = 0
        self.bad_count = 0
        self.convert_btn.config(state="disabled")
        self.progress.stop()
        if self.total_count > 1:
            # 多文件：进度条按已完成文件数推进
            self.progress.configure(mode="determinate", maximum=self.total_count, value=0)
            self.status_label.config(text=f"正在转换 第 1/{self.total_count} 个…")
        else:
            # 单文件：用滚动动画表示转换进行中
            self.progress.configure(mode="indeterminate", maximum=100, value=0)
            self.progress.start(10)
            self.status_label.config(text="正在转换…")
        self.log(f"开始转换 {self.total_count} 个文件")

        out_name = self.out_name_var.get().strip()
        files = list(self.file_paths)
        worker = threading.Thread(
            target=self._worker, args=(files, out_dir, out_name), daemon=True
        )
        worker.start()
        # 启动队列轮询（busy 已为 True，会持续调度直到收到结束哨兵）
        self._poll_queue()

    def _worker(self, files, out_dir, out_name):
        total = len(files)
        for idx, f in enumerate(files, start=1):
            # 先通知界面开始处理该文件（更新“第 x/n 个”提示）
            self.result_queue.put(("start", idx, total, f))
            self.result_queue.put(
                ("done", *_convert_one(f, out_dir, out_name, idx, total))
            )
        self.result_queue.put(None)  # 哨兵：全部完成

    def _poll_queue(self):
        try:
            while True:
                item = self.result_queue.get_nowait()
                if item is None:
                    self._finish()
                    return
                tag = item[0]
                if tag == "start":
                    self._on_start(*item[1:])
                else:
                    self._handle_result(*item[1:])
        except queue.Empty:
            pass
        if self.busy:
            self.root.after(80, self._poll_queue)

    def _on_start(self, idx, total, src):
        self.status_label.config(text=f"正在转换 第 {idx}/{total} 个：{src.name}")

    def _handle_result(self, src, kind, detail):
        name = src.name
        if self.total_count > 1:
            self.progress.step(1)
        if kind == "ok":
            self.ok_count += 1
            self.log(f"[成功] {name} → {detail}")
            # 记录最近生成的 md 路径，供“打开”按钮使用
            self.last_md_path = Path(detail)
            self.last_out_dir = self.last_md_path.parent
        elif kind == "unsupported":
            self.bad_count += 1
            self.log(f"[不支持] {name}：该文件格式无法转换为 Markdown")
            self._alert_if_single("不支持的格式", f"文件 {name} 的格式不受支持，无法转换为 Markdown。")
        elif kind == "missing_dep":
            self.bad_count += 1
            self.log(f"[缺少依赖] {name}：{detail}")
            self._alert_if_single("缺少依赖", f"转换 {name} 需要额外的依赖组件：\n{detail}")
        elif kind == "failed":
            self.bad_count += 1
            self.log(f"[失败] {name}：{detail}")
            self._alert_if_single("转换失败", f"文件 {name} 转换失败：\n{detail}")
        else:
            self.bad_count += 1
            self.log(f"[错误] {name}：{detail}")
            self._alert_if_single("出错", f"处理 {name} 时出错：\n{detail}")

    def _alert_if_single(self, title, msg):
        """单文件转换时弹出提示；批量转换时只记日志，避免连环弹窗。"""
        if self.total_count <= 1:
            messagebox.showwarning(title, msg)

    def _finish(self):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 0
        self.convert_btn.config(state="normal")
        self.status_label.config(
            text=f"转换完成：成功 {self.ok_count} 个，失败 {self.bad_count} 个"
        )
        if self.total_count > 1 and self.bad_count > 0:
            messagebox.showinfo(
                "转换完成",
                f"转换完成：成功 {self.ok_count} 个，失败 {self.bad_count} 个。\n"
                "详情见下方转换记录。",
            )


def main():
    root = TkinterDnD.Tk()
    MarkItDownApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
