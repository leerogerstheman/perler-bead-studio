# -*- coding: utf-8 -*-
"""拼豆图案生成器 —— 图形界面（包豪斯风格）。

运行：双击 启动.bat，或执行  python studio.py

界面外观遵循包豪斯设计原则：三原色 + 黑白、直角直线、方形色块按钮、
粗细对比的排版；功能与逻辑与之前完全一致。
"""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bauhaus as bh
import notice as notice_mod
import notice_core
import palette as palette_mod
import painter
import settings
from core import (BeadPattern, ConvertOptions, convert_file, estimate_sheets,
                  sharpness_note, size_presets)

APP_TITLE = "拼豆图案生成器"
APP_SUBTITLE = "PERLER BEAD STUDIO"
APP_VERSION = "1.1"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(BASE_DIR, "导出")

# 常用色引用（统一走 bauhaus 主题）
BG = bh.PAPER
PANEL = bh.PANEL_BG
BORDER = bh.BLACK
TEXT = bh.INK
MUTED = bh.GRAY_4
ACCENT = bh.RED
CHART_BG = painter.BG_COLOR
CANVAS_BG_FOR_CHART = "#FBFBF9"
WHITE_FOR_TEXT = bh.WHITE

FILE_TYPES = [
    ("常用图片", "*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff"),
    ("PNG / APNG", "*.png *.apng"),
    ("JPEG", "*.jpg *.jpeg *.jpe *.jfif"),
    ("WEBP", "*.webp"),
    ("BMP / DIB", "*.bmp *.dib"),
    ("GIF", "*.gif"),
    ("TIFF", "*.tif *.tiff"),
    ("图标 ICO / CUR", "*.ico *.cur"),
    ("其它常见格式", "*.tga *.pcx *.ppm *.pgm *.pbm *.pnm *.dds *.psd *.xbm *.xpm"),
    ("所有文件", "*.*"),
]

ZOOM_STEPS = [("适应", 0.0), ("1×", 1.0), ("2×", 2.0), ("3×", 3.0), ("5×", 5.0)]

# 长方形图片变成方形图案的三种处理方式
FIT_MODES = {
    "fit": "不裁掉任何内容：整张图等比缩小后放进方形格子，短边方向留空（空格不放豆子）。",
    "fill": "不留空、豆子占满整块：等比放大到铺满方形格子，长边多出来的部分裁掉。",
    "stretch": "不做等比：直接把图片拉成方形，人物会变胖/变瘦，一般不建议。",
}

CROP_ANCHORS = [
    ("居中", "center"),
    ("靠上（留头部）", "top"),
    ("靠下", "bottom"),
    ("靠左", "left"),
    ("靠右", "right"),
]

MAX_GRID = 1024
SLIDER_MAX = 256
BEAD_DRAW_LIMIT = 26000

#: 1× 时每格的像素数（2×/3×/5× 在此基础上按倍数放大）
BROWSE_CELL = 12
#: 图纸最长边的像素预算：超过就按比例缩小，避免百万格图案渲染到一半卡死
MAX_RENDER_PIXELS = 6000

SIDEBAR_W = 340
SIDE_PAD = 16
WRAP = SIDEBAR_W - SIDE_PAD * 2 - 22


class StudioApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.image_path: str = ""
        self.pattern: BeadPattern | None = None
        self.chart_image = None
        self.fit_cell: float = 20.0
        self.fit_fraction: float = 1.0     # 适应窗口比例（判断 1× 是否需要再缩小）
        self.zoom_factor: float = 0.0
        self._last_canvas_size = (0, 0)
        self._render_job = None
        self._queued_convert = False
        self._chart_error = ""
        self._events: queue.Queue = queue.Queue()
        self._scale_lock = False
        self._applying = False

        prefs = settings.load()
        self.var_path = tk.StringVar(value="尚未选择图片")
        palettes = palette_mod.palette_names()
        default_palette = prefs.get("last_palette") or palettes[0]
        if default_palette not in palettes:
            default_palette = palettes[0]
        self.var_palette = tk.StringVar(value=default_palette)
        start_cols = int(prefs.get("last_cols") or 32) or 32
        start_rows = int(prefs.get("last_rows") or 32) or 32
        start_cols = max(4, min(MAX_GRID, start_cols))
        start_rows = max(4, min(MAX_GRID, start_rows))
        self.var_cols = tk.IntVar(value=start_cols)
        self.var_rows = tk.IntVar(value=start_rows)
        self.var_link = tk.BooleanVar(value=start_cols == start_rows)
        self.var_preset = tk.StringVar(value=self._preset_label(start_cols, start_rows))
        self.var_dither = tk.BooleanVar(value=False)
        self.var_fit = tk.StringVar(value=prefs.get("last_fit_mode") or "fit")
        if self.var_fit.get() not in FIT_MODES:
            self.var_fit.set("fit")
        self.var_anchor = tk.StringVar(value="居中")
        self.var_fit_hint = tk.StringVar(value=FIT_MODES[self.var_fit.get()])
        self.var_bg_removal = tk.BooleanVar(value=False)
        self.var_tolerance = tk.IntVar(value=24)
        self.var_crop = tk.BooleanVar(value=True)
        self.var_ruler = tk.BooleanVar(value=True)
        self.var_gridlines = tk.BooleanVar(value=True)
        self.var_mode = tk.StringVar(value="bead")
        self.var_zoom = tk.StringVar(value="适应")
        self.var_zoom_hint = tk.StringVar(value="")
        self.var_status = tk.StringVar(value="就绪 — 请先选择一张图片")
        self.var_detail = tk.StringVar(value="把鼠标移到图纸上可以查看每一格的坐标和色号")
        self.var_summary = tk.StringVar(value="—")

        self._config_style()
        self._build_ui()
        self._bind_events()
        self._on_fit_change()
        self._on_tolerance(self.var_tolerance.get())
        self._refresh_preset_choices()
        self.root.after(80, self._poll_events)
        self.root.after(400, self._tick_refresh)
        self.root.after(200, self._draw_welcome)
        self.root.after(1200, self._apply_ttk_theming)

    @staticmethod
    def _preset_label(cols: int, rows: int) -> str:
        for name, c, r in size_presets():
            if c == cols and r == rows:
                return name
        return "自定义"

    # ------------------------------------------------------------ 外观 --

    def _config_style(self) -> None:
        self.root.title(f"{APP_TITLE} · {APP_SUBTITLE} v{APP_VERSION}")
        self.root.geometry(settings.get("window_geometry") or "1380x940")
        self.root.minsize(1080, 700)
        self.root.configure(bg=BG)
        bh.set_window_icon(self.root)

        self.style = ttk.Style()
        bh.setup_ttk_styles(self.style, self.root)
        self.colors = settings.get("theme_colors") or {}

    # ------------------------------------------------ 侧栏布局辅助 --

    def _sidebar_block(self, parent, title: str, number: str, accent: str) -> tk.Frame:
        """一个包豪斯小节：标题（色块编号 + 标题 + 细线）+ 内容区。"""
        wrap = tk.Frame(parent, bg=PANEL)
        wrap.pack(fill="x", padx=0, pady=(0, 2))
        head = tk.Frame(wrap, bg=PANEL)
        head.pack(fill="x", padx=SIDE_PAD, pady=(16, 8))
        bh.SectionHeader(head, title, accent=accent, number=number).pack(fill="x")
        body = tk.Frame(wrap, bg=PANEL)
        body.pack(fill="x", padx=SIDE_PAD, pady=(0, 14))
        return body

    def _labeled_row(self, parent, label: str, wrap: int = WRAP) -> tk.Frame:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(row, text=label, bg=PANEL, fg=MUTED, font=bh.font(bh.SIZE_SMALL),
                 anchor="w").pack(anchor="w")
        inner = tk.Frame(row, bg=PANEL)
        inner.pack(fill="x", pady=(4, 0))
        return inner

    def _hint(self, parent, text: str, color: str = MUTED) -> tk.Label:
        lbl = tk.Label(parent, text=text, bg=PANEL, fg=color, font=bh.font(bh.SIZE_SMALL),
                       justify="left", anchor="w", wraplength=WRAP)
        lbl.pack(anchor="w", pady=(2, 0))
        return lbl

    # -------------------------------------------------------------- UI --

    def _build_ui(self) -> None:
        # 行：0 顶部标题条 / 1 篡改警告（平时隐藏）/ 2 主体 / 3 状态栏
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(3, weight=0)

        # ---------- 顶部黑色标题条（构成主义排版）----------
        top = tk.Canvas(self.root, height=62, bg=bh.BLACK, highlightthickness=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.bind("<Configure>", self._paint_topbar)
        self.top_canvas = top

        # ---------- 左侧控制栏 ----------
        sidebar_holder = tk.Frame(self.root, bg=PANEL, width=SIDEBAR_W)
        sidebar_holder.grid(row=2, column=0, sticky="nsw")
        sidebar_holder.grid_propagate(False)
        sidebar_holder.columnconfigure(0, weight=1)
        sidebar_holder.rowconfigure(0, weight=1)

        self.canvas_scroll = tk.Canvas(sidebar_holder, bg=PANEL, highlightthickness=0,
                                       width=SIDEBAR_W)
        self.canvas_scroll.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(sidebar_holder, orient="vertical", command=self.canvas_scroll.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.canvas_scroll.configure(yscrollcommand=sb.set)

        inner = tk.Frame(self.canvas_scroll, bg=PANEL)
        inner_id = self.canvas_scroll.create_window((0, 0), window=inner, anchor="nw",
                                                    width=SIDEBAR_W - 18)
        inner.bind("<Configure>",
                   lambda e: self.canvas_scroll.configure(scrollregion=self.canvas_scroll.bbox("all")))
        self.canvas_scroll.bind(
            "<Configure>",
            lambda e: self.canvas_scroll.itemconfigure(inner_id, width=max(240, e.width - 18)))
        self._bind_wheel(self.canvas_scroll)

        self._section_image(inner)
        self._section_size(inner)
        self._section_style(inner)
        self._section_view(inner)
        self._section_export(inner)
        self._section_help(inner)

        # ---------- 右侧工作区 ----------
        right = tk.Frame(self.root, bg=BG)
        right.grid(row=2, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_toolbar(right)

        body = tk.Frame(right, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 0))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        wrap = tk.Frame(body, bg=bh.BLACK, bd=0)
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.chart_canvas = tk.Canvas(wrap, bg=CANVAS_BG_FOR_CHART, highlightthickness=0,
                                      bd=0, width=420, height=360)
        self.chart_canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vbar = ttk.Scrollbar(wrap, orient="vertical", command=self.chart_canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns", pady=2)
        hbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.chart_canvas.xview)
        hbar.grid(row=1, column=0, sticky="ew", padx=2)
        self.chart_canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        self._build_counts_panel(right)
        self._build_statusbar()
        self._build_integrity_banner()

    def _build_toolbar(self, parent) -> None:
        bar = tk.Frame(parent, bg=PANEL)
        bar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 10))
        bh.Rule(bar, thickness=2, color=bh.BLACK).pack(fill="x", side="bottom")

        left = tk.Frame(bar, bg=PANEL)
        left.pack(side="left", pady=(0, 10))
        tk.Label(left, text="拼豆图纸", bg=PANEL, fg=bh.BLACK,
                 font=bh.font(13, True)).pack(side="left")
        zoom_box = tk.Frame(left, bg=PANEL)
        zoom_box.pack(side="left", padx=(18, 0))
        tk.Label(zoom_box, text="缩放", bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL)).pack(side="left", padx=(0, 8))
        bh.Segmented(zoom_box, ZOOM_STEPS, self.var_zoom, command=self._on_zoom,
                     accent=bh.BLUE, small=True).pack(side="left")
        self.seg_zoom = zoom_box.winfo_children()[-1]
        tk.Label(zoom_box, textvariable=self.var_zoom_hint, bg=PANEL, fg=bh.GRAY_4,
                 font=bh.font(8)).pack(side="left", padx=(10, 0))

        right = tk.Frame(bar, bg=PANEL)
        right.pack(side="right", pady=(0, 10))
        bh.BauhausButton(right, "导出全部文件", self.export_all,
                         kind="primary").pack(side="right")
        bh.BauhausButton(right, "导出图纸 PNG", self.export_png,
                         kind="default", small=True).pack(side="right", padx=(0, 8))

    def _build_counts_panel(self, parent) -> None:
        counts = tk.Frame(parent, bg=PANEL)
        counts.grid(row=2, column=0, sticky="ew", padx=14, pady=(12, 0))
        counts.columnconfigure(0, weight=1)

        head = tk.Frame(counts, bg=PANEL)
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(10, 0))
        bh.SectionHeader(head, "豆子用量清单", accent=bh.YELLOW, number="✳").pack(fill="x")
        head2 = tk.Frame(counts, bg=PANEL)
        head2.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(8, 0))
        tk.Label(head2, textvariable=self.var_summary, bg=PANEL, fg=bh.RED,
                 font=bh.font(11, True), anchor="w").pack(side="left")
        bh.BauhausButton(head2, "复制清单", self.copy_counts, kind="ghost",
                         small=True).pack(side="right")
        bh.BauhausButton(head2, "打开导出文件夹", self.open_export_dir, kind="ghost",
                         small=True).pack(side="right", padx=(0, 6))

        self.legend_text = tk.Text(counts, height=3, width=10, wrap="none", bd=0,
                                   bg=WHITE_FOR_TEXT, fg=TEXT, font=bh.mono(10),
                                   padx=10, pady=5, highlightthickness=0,
                                   cursor="arrow", insertbackground=WHITE_FOR_TEXT)
        self.legend_text.grid(row=2, column=0, sticky="ew", padx=(14, 0), pady=(7, 10))
        lsb = ttk.Scrollbar(counts, orient="vertical", command=self.legend_text.yview)
        lsb.grid(row=2, column=1, sticky="ns", pady=(7, 10))
        self.legend_text.configure(yscrollcommand=lsb.set)
        self.legend_text.tag_configure("odd", background="#F1EEE8")
        self.legend_text.configure(state="disabled")

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg=bh.BLACK, height=28)
        bar.grid(row=3, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        tk.Label(bar, textvariable=self.var_status, bg=bh.BLACK, fg=bh.WHITE,
                 font=bh.font(bh.SIZE_SMALL), anchor="w").pack(
            side="left", padx=14, fill="x", expand=True)
        # 常驻声明（包豪斯黄块），任何时候都能看到软件是免费的
        tk.Label(bar, text=f"  {notice_core.watermark_text()}  ", bg=bh.YELLOW, fg=bh.BLACK,
                 font=bh.font(bh.SIZE_SMALL, True), cursor="hand2").pack(side="right")
        tk.Label(bar, textvariable=self.var_detail, bg=bh.BLACK, fg=bh.GRAY_2,
                 font=bh.font(bh.SIZE_SMALL), anchor="e").pack(side="right", padx=14)

    def _build_integrity_banner(self) -> None:
        """声明被篡改时，顶部常驻红色警告条（删声明的代价）。"""
        self.integrity_banner = tk.Frame(self.root, bg=bh.RED)
        # 默认不显示，检测到问题再 grid
        label = tk.Label(self.integrity_banner, bg=bh.RED, fg=bh.WHITE,
                         font=bh.font(bh.SIZE_SMALL, True), anchor="w",
                         justify="left", padx=14, pady=6)
        label.pack(fill="x")
        button = tk.Label(self.integrity_banner, text="查看声明", bg=bh.WHITE, fg=bh.RED,
                          font=bh.font(bh.SIZE_SMALL, True), padx=10, pady=2,
                          cursor="hand2")
        button.pack(side="right", padx=10, pady=4)
        button.bind("<Button-1>", lambda e: self.show_notice_again())
        self.integrity_label = label

        ok, reason = notice_mod.integrity()
        if not ok:
            self.integrity_label.configure(
                text="⚠ 检测到本程序的免费声明被删除或修改　"
                     f"（{reason}）　本软件开源免费，请勿付费购买；"
                     "声明每次启动都会重新提醒，删除它不会让程序更好用。")
            self.integrity_banner.grid(row=1, column=0, columnspan=2, sticky="ew")

    def show_notice_again(self) -> None:
        """随时重新查看声明（状态栏与帮助区都能点）。"""
        dlg = notice_mod.StartupNotice(self.root)
        self.root.wait_window(dlg.window)

    def _paint_topbar(self, event=None) -> None:
        """顶部标题条：黑色底 + 三原色几何图形 + 标题（包豪斯海报式构图）。"""
        c = self.top_canvas
        c.delete("all")
        w = event.width if event else c.winfo_width()
        c.create_rectangle(0, 0, w, 62, fill=bh.BLACK, outline=bh.BLACK)
        bh.draw_square(c, 18, 22, 18, bh.RED)
        bh.draw_circle(c, 42, 22, 18, bh.YELLOW)
        c.create_rectangle(66, 26, 90, 36, fill=bh.BLUE, outline=bh.BLUE)
        c.create_text(104, 24, text=APP_TITLE, anchor="w", fill=bh.WHITE,
                      font=bh.font(15, True))
        c.create_text(104, 43, text=f"{APP_SUBTITLE}  ·  OPEN SOURCE  ·  FREE",
                      anchor="w", fill=bh.GRAY_3, font=bh.font(8, True))
        # 右侧：三原色竖条，纯装饰但符合包豪斯色彩构成
        x = w - 74
        for i, color in enumerate((bh.RED, bh.YELLOW, bh.BLUE, bh.WHITE)):
            c.create_rectangle(x + i * 16, 20, x + i * 16 + 12, 42,
                               fill=color, outline=color)

    # ------------------------------------------------- 侧栏各小节 --

    def _section_image(self, parent) -> None:
        body = self._sidebar_block(parent, "选择图片", "1", bh.RED)

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        entry = tk.Entry(row, textvariable=self.var_path, state="readonly",
                         bg=WHITE_FOR_TEXT, fg=TEXT, font=bh.font(bh.SIZE_SMALL),
                         relief="solid", bd=1, readonlybackground=WHITE_FOR_TEXT,
                         highlightthickness=0)
        entry.grid(row=0, column=0, sticky="ew", ipady=5)
        bh.BauhausButton(row, "浏览…", self.choose_image, kind="blue",
                         small=True).grid(row=0, column=1, padx=(8, 0))

        btns = tk.Frame(body, bg=PANEL)
        btns.pack(fill="x", pady=(8, 0))
        bh.BauhausButton(btns, "示例图片", self.load_sample, kind="accent",
                         small=True).pack(side="left")
        bh.BauhausButton(btns, "打开导出文件夹", self.open_export_dir, kind="ghost",
                         small=True).pack(side="left", padx=(8, 0))

        prev_wrap = tk.Frame(body, bg=bh.BLACK, bd=0)
        prev_wrap.pack(fill="x", pady=(10, 0))
        self.preview = tk.Label(prev_wrap, bg="#EDEAE4", width=286, height=130,
                                text="图片预览", fg=bh.GRAY_4, font=bh.font(9),
                                relief="flat")
        self.preview.pack(padx=2, pady=2)

    def _section_size(self, parent) -> None:
        body = self._sidebar_block(parent, "行列数（1 格 = 1 颗豆子）", "2", bh.BLUE)

        preset_row = tk.Frame(body, bg=PANEL)
        preset_row.pack(fill="x")
        tk.Label(preset_row, text="常用尺寸", bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL)).pack(anchor="w")
        self.cmb_preset = ttk.Combobox(preset_row, textvariable=self.var_preset,
                                       state="readonly", width=22, font=bh.font(10))
        self.cmb_preset.pack(fill="x", pady=(4, 0))
        self.cmb_preset.bind("<<ComboboxSelected>>", self._on_preset)

        spin = tk.Frame(body, bg=PANEL)
        spin.pack(fill="x", pady=(10, 0))
        spin.columnconfigure(1, weight=1)
        spin.columnconfigure(4, weight=1)
        tk.Label(spin, text="列", bg=PANEL, fg=MUTED, font=bh.font(bh.SIZE_SMALL)).grid(
            row=0, column=0, sticky="w")
        self.spin_cols = ttk.Spinbox(spin, from_=4, to=MAX_GRID, textvariable=self.var_cols,
                                     width=6, font=bh.font(10))
        self.spin_cols.grid(row=0, column=1, sticky="ew", padx=(6, 14))
        tk.Label(spin, text="行", bg=PANEL, fg=MUTED, font=bh.font(bh.SIZE_SMALL)).grid(
            row=0, column=2, sticky="w")
        self.spin_rows = ttk.Spinbox(spin, from_=4, to=MAX_GRID, textvariable=self.var_rows,
                                     width=6, font=bh.font(10))
        self.spin_rows.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        bh.SquareCheck(body, "保持正方形（列 = 行）", self.var_link,
                       command=self._on_link, accent=bh.BLUE, bg=PANEL, size=15).pack(
            anchor="w", pady=(10, 0))

        scale_row = tk.Frame(body, bg=PANEL)
        scale_row.pack(fill="x", pady=(8, 0))
        self.scale_size = bh.SquareSlider(scale_row, 8, SLIDER_MAX, command=self._on_scale,
                                          accent=bh.BLUE, width=WRAP - 66)
        self.scale_size.pack(side="left")
        tk.Label(scale_row, text="拖动调整", bg=PANEL, fg=MUTED,
                 font=bh.font(8)).pack(side="left", padx=(8, 0))
        self.scale_size.set(32)

        self._hint(body, "列 / 行可输入 4 ~ 1024 的任意整数（滑块只覆盖常用范围）。\n"
                         "常用：32×32 头像 · 64×64 宠物照 · 128×128 起更像像素画。")

    def _section_style(self, parent) -> None:
        body = self._sidebar_block(parent, "颜色风格", "3", bh.YELLOW)

        pal_row = tk.Frame(body, bg=PANEL)
        pal_row.pack(fill="x")
        tk.Label(pal_row, text="色卡", bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL)).pack(anchor="w")
        combo = ttk.Combobox(pal_row, textvariable=self.var_palette, state="readonly",
                             values=palette_mod.palette_names(), width=22, font=bh.font(10))
        combo.pack(fill="x", pady=(4, 0))
        combo.bind("<<ComboboxSelected>>", lambda e: self.request_convert())

        tk.Label(body, text="长方形图片怎么变成方形图案", bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL), anchor="w").pack(anchor="w", pady=(12, 6))
        seg = bh.Segmented(body, (("完整放入 留白", "fit"), ("裁切填满", "fill"),
                                  ("拉伸", "stretch")), self.var_fit,
                           command=self._on_fit_change, accent=bh.RED, small=True)
        seg.pack(anchor="w")
        self.seg_fit = seg
        tk.Label(body, textvariable=self.var_fit_hint, bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL), justify="left", anchor="w",
                 wraplength=WRAP).pack(anchor="w", pady=(6, 0))

        anchor_row = tk.Frame(body, bg=PANEL)
        anchor_row.pack(fill="x", pady=(10, 0))
        self.lbl_anchor = tk.Label(anchor_row, text="裁切位置", bg=PANEL, fg=MUTED,
                                   font=bh.font(bh.SIZE_SMALL))
        self.lbl_anchor.pack(side="left")
        self.cmb_anchor = ttk.Combobox(anchor_row, textvariable=self.var_anchor,
                                       state="readonly", values=[a[0] for a in CROP_ANCHORS],
                                       width=14, font=bh.font(10))
        self.cmb_anchor.pack(side="right")
        self.cmb_anchor.bind("<<ComboboxSelected>>", lambda e: self.request_convert())

        bh.SquareCheck(body, "颜色抖动（渐变更细腻，颜色会变杂）", self.var_dither,
                       command=self.request_convert, accent=bh.RED, bg=PANEL,
                       size=15, wrap=WRAP - 24).pack(anchor="w", pady=(12, 0))

        bh.SquareCheck(body, "去掉纯色背景（该处不放豆子）", self.var_bg_removal,
                       command=self._on_bg_toggle, accent=bh.RED, bg=PANEL,
                       size=15, wrap=WRAP - 24).pack(anchor="w", pady=(8, 0))

        tol_row = tk.Frame(body, bg=PANEL)
        tol_row.pack(fill="x", pady=(8, 0))
        self.lbl_tol = tk.Label(tol_row, text=f"容差 {self.var_tolerance.get()}",
                                bg=PANEL, fg=MUTED, font=bh.font(bh.SIZE_SMALL),
                                width=12, anchor="w")
        self.lbl_tol.pack(side="left")
        self.scale_tol = bh.SquareSlider(tol_row, 0, 90, command=self._on_tolerance,
                                         accent=bh.RED, width=WRAP - 110)
        self.scale_tol.pack(side="right")
        self.scale_tol.set(self.var_tolerance.get())

        bh.SquareCheck(body, "自动裁剪留白（只保留主体）", self.var_crop,
                       command=self.request_convert, accent=bh.RED, bg=PANEL,
                       size=15, wrap=WRAP - 24).pack(anchor="w", pady=(10, 0))

    def _section_view(self, parent) -> None:
        body = self._sidebar_block(parent, "图纸显示", "4", bh.BLACK)

        bh.SquareCheck(body, "显示行列坐标", self.var_ruler, command=self.render_chart,
                       accent=bh.BLACK, bg=PANEL, size=15).pack(anchor="w")
        bh.SquareCheck(body, "显示网格线", self.var_gridlines, command=self.render_chart,
                       accent=bh.BLACK, bg=PANEL, size=15).pack(anchor="w", pady=(8, 0))

        tk.Label(body, text="图纸样式", bg=PANEL, fg=MUTED,
                 font=bh.font(bh.SIZE_SMALL), anchor="w").pack(anchor="w", pady=(12, 6))
        bh.Segmented(body, (("圆豆子图纸", "bead"), ("成品像素效果", "flat")),
                     self.var_mode, command=self.render_chart, accent=bh.BLACK,
                     small=True).pack(anchor="w")

    def _section_export(self, parent) -> None:
        body = self._sidebar_block(parent, "导出", "5", bh.RED)
        bh.BauhausButton(body, "导出全部文件", self.export_all,
                         kind="primary").pack(fill="x")
        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x", pady=(8, 0))
        bh.BauhausButton(row, "导出 PNG", self.export_png, kind="default",
                         small=True).pack(side="left", fill="x", expand=True)
        bh.BauhausButton(row, "打开文件夹", self.open_export_dir, kind="ghost",
                         small=True).pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._hint(body, f"导出目录：{EXPORT_DIR}")

    def _section_help(self, parent) -> None:
        body = self._sidebar_block(parent, "使用说明", "?", bh.GRAY_3)
        tips = ("1. 选图后自动生成 32×32 图纸，改行列数会实时重算；\n"
                "2. 鼠标移到右侧图纸上可看每格坐标与色号；\n"
                "3. 「导出全部文件」含图纸 PNG、效果图、豆子清单\n"
                "   TXT/CSV、格子编号 CSV、可打印网页 HTML；\n"
                "4. 图案超过 4 万格会自动跳过 SVG，超过 40 万格跳过 HTML；\n"
                "5. 自定义色卡：把 JSON 放进 palettes 文件夹。")
        self._hint(body, tips)
        foot = tk.Frame(body, bg=PANEL)
        foot.pack(fill="x", pady=(12, 0))
        bh.draw_rule(foot_canvas := tk.Canvas(foot, height=10, bg=PANEL,
                                              highlightthickness=0, width=WRAP), 0, 5, WRAP, 5,
                     color=bh.GRAY_2, width=1)
        foot_canvas.pack(fill="x")
        tk.Label(body, text="开源免费 · 请勿付费购买本工具", bg=PANEL, fg=bh.RED,
                 font=bh.font(bh.SIZE_SMALL, True)).pack(anchor="w", pady=(6, 0))
        again = tk.Label(body, text="→ 点这里重新查看免费声明", bg=PANEL, fg=bh.BLUE,
                         font=bh.font(bh.SIZE_SMALL), cursor="hand2")
        again.pack(anchor="w", pady=(4, 0))
        again.bind("<Button-1>", lambda e: self.show_notice_again())

    # -------------------------------------------------------- 事件绑定 --

    def _bind_events(self) -> None:
        self.var_cols.trace_add("write", lambda *_: self._on_size_change(manual=True))
        self.var_rows.trace_add("write", lambda *_: self._on_size_change(manual=True))
        self.chart_canvas.bind("<Configure>", self._on_canvas_resize)
        self.chart_canvas.bind("<Motion>", self._on_canvas_motion)
        self.chart_canvas.bind("<Leave>", lambda e: self.var_detail.set(
            "把鼠标移到图纸上可以查看每一格的坐标和色号"))
        self.root.bind("<Control-o>", lambda e: self.choose_image())
        self.root.bind("<Control-s>", lambda e: self.export_all())
        self.root.bind("<F5>", lambda e: self.request_convert())
        self.root.bind("<Escape>", lambda e: self.root.focus_set())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _bind_wheel(self, widget) -> None:
        def _on_wheel(event):
            widget.yview_scroll(-1 if event.delta > 0 else 1, "units")
        widget.bind("<Enter>", lambda e: widget.bind_all("<MouseWheel>", _on_wheel))
        widget.bind("<Leave>", lambda e: widget.unbind_all("<MouseWheel>"))

    def _apply_ttk_theming(self) -> None:
        """把下拉框弹出列表也刷成黑白配色（需要窗口已创建）。"""
        try:
            self.root.option_add("*TCombobox*Listbox.background", bh.WHITE)
            self.root.option_add("*TCombobox*Listbox.foreground", bh.INK)
            self.root.option_add("*TCombobox*Listbox.selectBackground", bh.BLUE)
            self.root.option_add("*TCombobox*Listbox.selectForeground", bh.WHITE)
        except Exception:      # noqa: BLE001
            pass

    def _on_close(self) -> None:
        try:
            settings.save({
                "window_geometry": self.root.winfo_geometry(),
                "last_palette": self.var_palette.get(),
                "last_cols": int(self.var_cols.get()),
                "last_rows": int(self.var_rows.get()),
                "last_fit_mode": self.var_fit.get(),
            })
        except Exception:      # noqa: BLE001
            pass
        self.root.destroy()

    # ------------------------------------------------------ 交互回调 --

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(title="选择一张图片", filetypes=FILE_TYPES)
        if path:
            self.load_image(path)

    def load_sample(self) -> None:
        path = os.path.join(BASE_DIR, "示例图片.png")
        if not os.path.exists(path):
            messagebox.showinfo("没有示例图片",
                                "示例图片不存在。\n可以运行 python make_sample.py 生成，"
                                "或直接选择你自己的图片。")
            return
        self.load_image(path)

    def load_image(self, path: str) -> None:
        self.image_path = path
        self.var_path.set(path)
        self._update_preview(path)
        base = os.path.splitext(os.path.basename(path))[0]
        self.var_status.set(f"已载入 — {os.path.basename(path)}")
        self.root.title(f"{APP_TITLE} · v{APP_VERSION} — {base}")
        self.request_convert(force=True)

    def _update_preview(self, path: str) -> None:
        try:
            from PIL import Image, ImageOps, ImageTk
            img = Image.open(path)
            img.load()
            try:
                img = ImageOps.exif_transpose(img)   # 手机竖拍照片先转正
            except Exception:      # noqa: BLE001
                pass
            img = img.convert("RGBA")
            w, h = img.size
            box_w, box_h = 286, 150
            ratio = min(box_w / w, box_h / h)
            size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
            img = img.resize(size, Image.LANCZOS)
            flat = Image.new("RGB", size, (237, 234, 228))
            flat.paste(img, (0, 0), img)
            self._preview_photo = ImageTk.PhotoImage(flat)
            self.preview.configure(image=self._preview_photo, text="",
                                   width=size[0], height=size[1])
        except Exception as exc:      # noqa: BLE001
            self.preview.configure(image="", text=f"预览失败：{exc}")

    def _refresh_preset_choices(self) -> None:
        if hasattr(self, "cmb_preset"):
            self.cmb_preset.configure(values=[p[0] for p in size_presets()])

    def _on_preset(self, _event=None) -> None:
        label = self.var_preset.get()
        for name, cols, rows in size_presets():
            if name != label:
                continue
            if name == "自定义" or (cols == self.var_cols.get() and rows == self.var_rows.get()):
                return
            self._applying = True
            self.var_link.set(cols == rows)
            self.var_cols.set(cols)
            self.var_rows.set(rows)
            self._applying = False
            if 8 <= cols <= SLIDER_MAX:
                self._scale_lock = True
                self.scale_size.set(cols)
                self._scale_lock = False
            self.request_convert()
            return

    def _on_link(self) -> None:
        if self.var_link.get():
            self._applying = True
            self.var_rows.set(self.var_cols.get())
            self._applying = False
            self.request_convert()

    def _on_scale(self, value) -> None:
        """拖动尺寸滑块：只处理整数档，避免连续触发重算。"""
        if self._scale_lock:
            return
        size = int(float(value))
        if size >= 16:
            size -= size % 2          # 大尺寸吸附到偶数
        if size == self.var_cols.get():
            return
        self._scale_lock = True
        self.var_cols.set(size)
        if self.var_link.get():
            self.var_rows.set(size)
        self._scale_lock = False
        self._on_size_change()

    def _on_size_change(self, manual: bool = False) -> None:
        if self._applying or self._scale_lock:
            return
        try:
            cols = int(self.var_cols.get())
            rows = int(self.var_rows.get())
        except (tk.TclError, ValueError):
            return
        cols = max(4, min(MAX_GRID, cols))
        rows = max(4, min(MAX_GRID, rows))
        if self.var_link.get() and manual:
            focus = self.root.focus_get()
            if focus is self.spin_cols and rows != cols:
                self._applying = True
                self.var_rows.set(cols)
                self._applying = False
            elif focus is self.spin_rows and rows != cols:
                self._applying = True
                self.var_cols.set(rows)
                self._applying = False
        label = self._preset_label(cols, rows)
        if label != self.var_preset.get():
            self._applying = True
            self.var_preset.set(label)
            self._applying = False
        self.request_convert()

    def _on_fit_change(self) -> None:
        """切换填充方式时更新说明文字，并决定「裁切位置」是否可用。"""
        mode = self.var_fit.get()
        self.var_fit_hint.set(FIT_MODES.get(mode, ""))
        usable = mode == "fill"
        try:
            self.cmb_anchor.configure(state="readonly" if usable else "disabled")
            self.lbl_anchor.configure(fg=MUTED if usable else bh.GRAY_2)
        except Exception:      # noqa: BLE001
            pass
        self.request_convert()

    def _on_bg_toggle(self) -> None:
        self.request_convert()

    def _on_tolerance(self, value) -> None:
        tol = int(float(value))
        if tol == self.var_tolerance.get():
            return
        self.var_tolerance.set(tol)
        try:
            self.lbl_tol.configure(text=f"容差 {tol}")
        except Exception:      # noqa: BLE001
            pass
        if self.var_bg_removal.get():
            self._tolerance_stamp = time.time()

    def _on_zoom(self) -> None:
        label = self.var_zoom.get()
        for name, factor in ZOOM_STEPS:
            if name == label:
                self.zoom_factor = factor
                break
        if self.zoom_factor <= 0:
            self.var_zoom_hint.set("整张图纸放进窗口")
        else:
            self.var_zoom_hint.set(f"每格约 {int(round(self._effective_cell()))} 像素，"
                                   f"超出窗口请拖动滚动条")
        self.render_chart()

    def _on_canvas_resize(self, event) -> None:
        if (event.width, event.height) == self._last_canvas_size:
            return
        self._last_canvas_size = (event.width, event.height)
        self.render_chart()

    def _on_canvas_motion(self, event) -> None:
        if not self.pattern:
            return
        cell = self._effective_cell()
        pad = self._ruler_pad(cell)
        x = self.chart_canvas.canvasx(event.x)
        y = self.chart_canvas.canvasy(event.y)
        col = int((x - pad) // cell)
        row = int((y - pad) // cell)
        if 0 <= col < self.pattern.cols and 0 <= row < self.pattern.rows:
            idx = self.pattern.index[row][col]
            if idx < 0:
                self.var_detail.set(f"第 {col + 1} 列 · 第 {row + 1} 行：空格（不放豆子）")
            else:
                r, g, b = self.pattern.rgb[idx]
                count = dict(self.pattern.counts()).get(idx, 0)
                self.var_detail.set(
                    f"第 {col + 1} 列 · 第 {row + 1} 行：{self.pattern.names[idx]} "
                    f"#{r:02X}{g:02X}{b:02X}（全图共 {count} 颗）")
        else:
            self.var_detail.set("把鼠标移到图纸上可以查看每一格的坐标和色号")

    # -------------------------------------------------- 转换（后台线程）--

    def _tick_refresh(self) -> None:
        """容差滑块等连续操作后延迟重算，避免卡顿。"""
        stamp = getattr(self, "_tolerance_stamp", 0)
        if stamp and time.time() - stamp > 0.45:
            self._tolerance_stamp = 0
            self.request_convert()
        self.root.after(220, self._tick_refresh)

    def request_convert(self, force: bool = False) -> None:
        if not self.image_path:
            if force:
                self.var_status.set("请先选择一张图片")
            return
        if getattr(self, "_worker", None) and self._worker.is_alive():
            if not force:
                self._queued_convert = True
            return
        self._start_convert()

    def _current_options(self) -> ConvertOptions:
        cols = max(4, min(MAX_GRID, int(self.var_cols.get())))
        rows = max(4, min(MAX_GRID, int(self.var_rows.get())))
        anchor = "center"
        for label, value in CROP_ANCHORS:
            if label == self.var_anchor.get():
                anchor = value
                break
        return ConvertOptions(
            cols=cols,
            rows=rows,
            palette_name=self.var_palette.get(),
            dither=bool(self.var_dither.get()),
            fit_mode=self.var_fit.get(),
            crop_anchor=anchor,
            bg_removal=bool(self.var_bg_removal.get()),
            bg_tolerance=int(self.var_tolerance.get()),
            crop_to_content=bool(self.var_crop.get()),
        )

    def _start_convert(self) -> None:
        options = self._current_options()
        palette_items = palette_mod.get_palette(options.palette_name)
        path = self.image_path
        self.var_status.set(f"正在转换 — {options.cols} × {options.rows} …")

        def work() -> None:
            try:
                t0 = time.time()
                pattern = convert_file(path, options, palette_items,
                                       progress=lambda msg: self._events.put(("status", msg)))
                self._events.put(("pattern", pattern, time.time() - t0))
            except Exception as exc:      # noqa: BLE001
                self._events.put(("error", str(exc)))

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "status":
                    self.var_status.set(event[1])
                elif kind == "pattern":
                    self._apply_pattern(event[1], event[2])
                elif kind == "error":
                    self.var_status.set(f"转换失败 — {event[1]}")
                    messagebox.showerror("转换失败", event[1])
        except queue.Empty:
            pass
        self.root.after(60, self._poll_events)

    def _apply_pattern(self, pattern: BeadPattern, elapsed: float) -> None:
        self.pattern = pattern
        self._fill_counts(pattern)
        self.render_chart()

        sheets = estimate_sheets(pattern.rows, pattern.cols)
        note = sharpness_note(pattern)
        self.var_summary.set(
            f"{pattern.cols} 列 × {pattern.rows} 行 · {pattern.total} 颗豆子 · "
            f"{len(pattern.counts())} 种颜色 · 约需 {sheets} 块 29×29 拼豆板 · "
            f"{elapsed:.2f} 秒")
        self.var_detail.set(note)
        self.var_status.set(f"完成 — {os.path.basename(self.image_path)} → "
                            f"{pattern.cols} × {pattern.rows}")
        if self._queued_convert:
            self._queued_convert = False
            self.request_convert()

    def _fill_counts(self, pattern: BeadPattern) -> None:
        """把每种颜色的用量填进清单（带颜色小方块，等宽字体对齐）。"""
        from PIL import Image as PILImage, ImageDraw, ImageTk

        text = self.legend_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        self._legend_photos = []

        counts = pattern.counts()
        name_width = max([len(pattern.names[i]) for i, _c in counts] + [4])
        for order, (idx, count) in enumerate(counts, start=1):
            r, g, b = pattern.rgb[idx]
            size = 12
            chip = PILImage.new("RGBA", (size, size), (255, 255, 255, 0))
            ImageDraw.Draw(chip).rectangle((0, 0, size - 1, size - 1),
                                           fill=(r, g, b, 255), outline=(20, 22, 26, 255))
            photo = ImageTk.PhotoImage(chip)
            self._legend_photos.append(photo)

            tag = ("odd",) if order % 2 else ()
            text.insert("end", " ")
            text.image_create("end", image=photo)
            name = pattern.names[idx]
            pad = "　" * (name_width - len(name) + 1)
            text.insert("end", f" {order:>2}. {name}{pad}#{r:02X}{g:02X}{b:02X}"
                               f"{count:>6} 颗\n", tag)
        if not counts:
            text.insert("end", "（没有可放置的豆子）\n")
        text.configure(state="disabled")
        text.yview_moveto(0)

    # ------------------------------------------------------ 图纸渲染 --

    def _ruler_pad(self, cell: float) -> float:
        return max(cell * 1.15, 22) if self.var_ruler.get() else 0

    def _max_cell(self) -> float:
        """按像素预算算出当前图案允许的最大每格像素数。"""
        pattern = self.pattern
        if not pattern:
            return BROWSE_CELL
        biggest = max(pattern.cols, pattern.rows)
        return max(2.0, MAX_RENDER_PIXELS / max(1, biggest))

    def _zoom_base(self) -> float:
        """1× 对应的每格像素数。

        常规图案就是 BROWSE_CELL（12px）；超大图案（像素预算不够）会自动降下来，
        这样 1×/2×/3×/5× 依然层层不同，而不是全部顶到同一个上限。
        """
        return max(1.0, min(float(BROWSE_CELL), self._max_cell() / 5.0))

    def _cell_for_factor(self, factor: float) -> float:
        """给定倍数，算出实际生效的每格像素数（受像素预算限制）。"""
        cap = self._max_cell()
        base = self._zoom_base()
        if factor <= 1.0 and self.fit_cell >= base * 0.80:
            base = max(1.0, base * 0.6)      # 小图：让 1× 明显比「适应」更紧凑
        return min(max(1.0, base * factor), cap)

    def _update_zoom_availability(self) -> None:
        """把超过渲染上限的档位置灰，避免点了没反应。"""
        seg = getattr(self, "seg_zoom", None)
        if seg is None or not self.pattern:
            return
        cap = self._max_cell()
        available = {}
        for label, factor in ZOOM_STEPS:
            if factor <= 0:
                available[label] = True
                continue
            available[label] = self._cell_for_factor(factor) < cap - 0.05
        seg.set_availability(available)

    def _effective_cell(self) -> float:
        """当前每格应该画多少像素。"""
        if self.zoom_factor <= 0:
            return self.fit_cell
        return self._cell_for_factor(self.zoom_factor)

    def _max_cell(self) -> float:
        """按像素预算算出当前图案允许的最大每格像素数。"""
        pattern = self.pattern
        if not pattern:
            return BROWSE_CELL
        biggest = max(pattern.cols, pattern.rows)
        return max(2.0, MAX_RENDER_PIXELS / max(1, biggest))

    def _draw_welcome(self) -> None:
        canvas = self.chart_canvas
        canvas.delete("all")
        w = canvas.winfo_width() or 800
        h = canvas.winfo_height() or 600
        # 包豪斯式欢迎画面：三原色方块 + 圆 + 标题
        cx, cy = w / 2, h / 2
        canvas.create_rectangle(cx - 96, cy - 78, cx - 76, cy - 58, fill=bh.RED, outline=bh.RED)
        canvas.create_oval(cx - 68, cy - 78, cx - 48, cy - 58, fill=bh.YELLOW, outline=bh.YELLOW)
        canvas.create_rectangle(cx - 40, cy - 74, cx - 14, cy - 62, fill=bh.BLUE, outline=bh.BLUE)
        canvas.create_text(cx, cy - 8, text="选择一张图片，开始生成拼豆图纸",
                           font=bh.font(15, True), fill=bh.BLACK)
        canvas.create_text(cx, cy + 26,
                           text="左侧「浏览…」选图 → 设定行列数 → 这里实时显示图纸与豆子用量",
                           font=bh.font(10), fill=bh.GRAY_4)
        canvas.create_line(cx - 150, cy + 52, cx + 150, cy + 52, fill=bh.GRAY_2, width=2)

    def render_chart(self) -> None:
        if self._render_job:
            self.root.after_cancel(self._render_job)
        self._render_job = self.root.after(60, self._render_chart_now)

    def _render_chart_now(self) -> None:
        self._render_job = None
        self._chart_error = ""
        pattern = self.pattern
        if not pattern:
            self._draw_welcome()
            return
        try:
            self._render_chart_inner(pattern)
        except Exception as exc:      # noqa: BLE001
            self._chart_error = str(exc)
            self.var_status.set(f"图纸渲染失败 — {exc}")

    def _render_chart_inner(self, pattern: BeadPattern) -> None:
        from PIL import Image, ImageTk

        canvas = self.chart_canvas
        avail_w = max(160, canvas.winfo_width() - 4)
        avail_h = max(160, canvas.winfo_height() - 4)
        ruler = bool(self.var_ruler.get())
        mode = self.var_mode.get()

        # 「适应」的每格像素直接按可视区域算。
        # 注意刻度边距（ruler pad）本身是按每格大小算的，所以它相当于多占
        # 2 × pad/cell 个格子宽度；这里把它并进格数一起解方程，图纸才不会偏小。
        pad_cells = 2.0 * (1.15 if ruler else 0.0)
        self.fit_cell = max(0.35, min(avail_w / (pattern.cols + pad_cells),
                                      avail_h / (pattern.rows + pad_cells)))
        # 刻度边距有一个 22px 的保底值，小图时按保底重算一次
        if ruler and self._ruler_pad(self.fit_cell) > self.fit_cell * 1.15 + 0.01:
            avail_w -= 44.0
            avail_h -= 44.0
            self.fit_cell = max(0.35, min(avail_w / pattern.cols, avail_h / pattern.rows))

        cell = self._effective_cell()
        # 大图自动降级为「纯色格子」，避免画几万个圆点卡住界面
        heavy = pattern.cols * pattern.rows > BEAD_DRAW_LIMIT and cell < 18
        draw_mode = "flat" if heavy else ("flat" if mode == "flat" else "bead")
        cell_px = max(2, int(round(cell)))
        img = painter.render_chart(pattern, cell=cell_px, ruler=ruler,
                                   grid_lines=bool(self.var_gridlines.get()) and not heavy,
                                   show_coords=ruler and cell_px >= 8,
                                   mode=draw_mode)

        scale = cell / cell_px
        if abs(scale - 1) > 0.02 and scale > 0:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                             Image.LANCZOS if scale < 1 else Image.NEAREST)
        self.chart_image = ImageTk.PhotoImage(img)

        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=self.chart_image)
        canvas.configure(scrollregion=(0, 0, img.width, img.height))
        # 缩放提示：显示真实生效的每格像素数，并刷新哪些档位还能用
        self._update_zoom_availability()
        real_cell = img.width / max(1, pattern.cols + (self._ruler_pad(1.0) * 2 if ruler else 0))
        if self.zoom_factor > 0:
            capped = self._cell_for_factor(self.zoom_factor) >= self._max_cell() - 0.05
            self.var_zoom_hint.set(
                f"每格约 {real_cell:.0f} 像素·拖动滚动条查看"
                + ("（已达渲染上限）" if capped else ""))
        else:
            self.var_zoom_hint.set(f"整张图纸放进窗口（每格约 {real_cell:.1f} 像素）")
        if heavy:
            self.var_detail.set("图纸较大，预览已切换为纯色格子（导出的 PNG 仍是完整图纸）")

    # ---------------------------------------------------------- 导出 --

    def _ensure_pattern(self) -> bool:
        if not self.pattern:
            messagebox.showinfo("还没有图纸", "请先选择一张图片并生成图纸。")
            return False
        return True

    def _export_folder(self) -> str:
        base = os.path.splitext(os.path.basename(self.image_path))[0] or "拼豆图纸"
        folder = os.path.join(EXPORT_DIR, f"{base}_{self.pattern.cols}x{self.pattern.rows}")
        os.makedirs(folder, exist_ok=True)
        return folder

    def export_png(self) -> None:
        if not self._ensure_pattern():
            return
        assert self.pattern
        base = os.path.splitext(os.path.basename(self.image_path))[0]
        default_name = f"{base}_{self.pattern.cols}x{self.pattern.rows}_图纸.png"
        os.makedirs(EXPORT_DIR, exist_ok=True)
        path = filedialog.asksaveasfilename(title="保存图纸 PNG", defaultextension=".png",
                                            initialfile=default_name, initialdir=EXPORT_DIR,
                                            filetypes=[("PNG 图片", "*.png")])
        if not path:
            return
        cell = painter.export_cell_size(self.pattern.cols, self.pattern.rows)
        painter.export_png(self.pattern, path, cell=cell,
                           title=f"{self.pattern.cols} × {self.pattern.rows} 拼豆图纸")
        self.var_status.set(f"已导出 — {path}")
        if messagebox.askyesno("导出完成", f"图纸已保存到：\n{path}\n\n现在打开吗？"):
            self._open_path(path)

    def export_all(self) -> None:
        if not self._ensure_pattern():
            return
        assert self.pattern
        try:
            folder = self._export_folder()
            base = f"{os.path.basename(folder)}"
            cell = painter.export_cell_size(self.pattern.cols, self.pattern.rows)
            files = painter.export_all(self.pattern, folder, base, cell=cell,
                                       title=f"{self.pattern.cols} × {self.pattern.rows} 拼豆图纸")
        except Exception as exc:      # noqa: BLE001
            messagebox.showerror("导出失败", str(exc))
            return
        self.var_status.set(f"已导出 {len(files)} 个文件 — {folder}")
        if messagebox.askyesno("导出完成",
                               f"已生成 {len(files)} 个文件：\n{folder}\n\n现在打开文件夹吗？"):
            self._open_path(folder)

    def copy_counts(self) -> None:
        if not self._ensure_pattern():
            return
        assert self.pattern
        lines = [f"拼豆豆子清单（{self.pattern.cols} 列 × {self.pattern.rows} 行，"
                 f"共 {self.pattern.total} 颗）"]
        for order, (idx, count) in enumerate(self.pattern.counts(), start=1):
            r, g, b = self.pattern.rgb[idx]
            lines.append(f"{order}. {self.pattern.names[idx]}  #{r:02X}{g:02X}{b:02X}  {count} 颗")
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.var_status.set("豆子清单已复制到剪贴板")

    def open_export_dir(self) -> None:
        os.makedirs(EXPORT_DIR, exist_ok=True)
        self._open_path(EXPORT_DIR)

    @staticmethod
    def _open_path(path: str) -> None:
        try:
            os.startfile(path)      # type: ignore[attr-defined]
        except Exception as exc:    # noqa: BLE001
            messagebox.showinfo("无法打开", str(exc))


def main() -> None:
    root = tk.Tk()
    bh.set_window_icon(root)
    root.withdraw()
    # 启动声明：说明本软件开源免费，谨防付费受骗（勾选后不再显示）
    if notice_mod.should_show():
        if not notice_mod.show_notice(root):
            root.destroy()
            return
    root.deiconify()
    StudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
