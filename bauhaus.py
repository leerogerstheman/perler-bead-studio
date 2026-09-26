# -*- coding: utf-8 -*-
"""包豪斯（Bauhaus）风格界面组件。

设计原则（1919–1933 包豪斯 / 现代主义）：
    · 只用基本几何形：正方形、长方形、圆、粗线
    · 三原色 + 黑白色阶：红 #D62828、蓝 #1B5FC1、黄 #F2B705、黑 #14161A
    · 无圆角、无渐变、无阴影；直线与直角
    · 功能决定形式：颜色只用来表达层级与状态，不做装饰性堆砌
    · 字重对比：标题粗黑，说明文字小号灰

这个模块只负责「外观」，不含业务逻辑。
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import font as tkfont

# ------------------------------------------------------------------ 色板 --

RED = "#D62828"
BLUE = "#1B5FC1"
YELLOW = "#F2B705"
BLACK = "#14161A"
INK = "#23262D"
PAPER = "#F4F2ED"        # 米白底（包豪斯常用纸色）
WHITE = "#FFFFFF"
GRAY_1 = "#E7E4DD"
GRAY_2 = "#C9C6BE"
GRAY_3 = "#8A8C93"
GRAY_4 = "#5A5D65"

# 语义色
CANVAS_BG = "#FBFBF9"
PANEL_BG = WHITE
ACCENT = RED
ACCENT_ALT = BLUE
HIGHLIGHT = YELLOW
LINE = BLACK

FONT_FAMILY = "Microsoft YaHei UI"
FONT_FAMILY_MONO = "Consolas"

SIZE_TITLE = 15
SIZE_SECTION = 11
SIZE_BODY = 10
SIZE_SMALL = 9


def font(size: int = SIZE_BODY, bold: bool = False) -> tuple:
    return (FONT_FAMILY, size, "bold") if bold else (FONT_FAMILY, size)


def mono(size: int = SIZE_BODY, bold: bool = False) -> tuple:
    return (FONT_FAMILY_MONO, size, "bold") if bold else (FONT_FAMILY_MONO, size)


# ------------------------------------------------------------ 绘图小工具 --

def draw_square(canvas: tk.Canvas, x: int, y: int, size: int, fill: str,
                outline: str = "") -> int:
    """实心方块——包豪斯最基本的元素。"""
    return canvas.create_rectangle(x, y, x + size, y + size,
                                   fill=fill, outline=outline or fill, width=1)


def draw_circle(canvas: tk.Canvas, x: int, y: int, size: int, fill: str) -> int:
    return canvas.create_oval(x, y, x + size, y + size, fill=fill, outline=fill)


def draw_rule(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int,
              color: str = BLACK, width: int = 2) -> int:
    return canvas.create_line(x1, y1, x2, y2, fill=color, width=width)


# ---------------------------------------------------------------- 基础块 --

class Rule(tk.Frame):
    """一条分隔线（包豪斯爱用的粗黑细线对比）。"""

    def __init__(self, master, thickness: int = 2, color: str = BLACK, **kw):
        super().__init__(master, bg=color, height=thickness, **kw)


class SectionHeader(tk.Frame):
    """小节标题：左侧一个彩色实心方块 + 粗体标题 + 细线延伸。"""

    def __init__(self, master, text: str, accent: str = RED, number: str = "",
                 bg: str = PANEL_BG):
        super().__init__(master, bg=bg)
        self.columnconfigure(2, weight=1)
        chip = tk.Canvas(self, width=16, height=16, bg=bg, highlightthickness=0)
        chip.grid(row=0, column=0, sticky="w")
        draw_square(chip, 1, 1, 14, accent)
        if number:
            chip.create_text(8, 8, text=number, fill=WHITE, font=font(8, True))
        tk.Label(self, text=text, bg=bg, fg=BLACK, font=font(SIZE_SECTION, True),
                 anchor="w").grid(row=0, column=1, sticky="w", padx=(8, 10))
        line = tk.Frame(self, bg=GRAY_2, height=2)
        line.grid(row=0, column=2, sticky="ew", pady=(1, 0))


class BauhausButton(tk.Frame):
    """平面色块按钮：默认黑白，主按钮用三原色；悬停加深，按下内缩。"""

    def __init__(self, master, text: str, command=None, kind: str = "default",
                 width: int | None = None, small: bool = False):
        palette = {
            "default": (BLACK, WHITE, "#000000"),
            "primary": (RED, WHITE, "#A81C1C"),
            "blue": (BLUE, WHITE, "#123B7A"),
            "accent": (YELLOW, BLACK, "#D19E00"),
            "ghost": (WHITE, BLACK, GRAY_1),
        }
        self.base, self.fg, self.hover = palette.get(kind, palette["default"])
        super().__init__(master, bg=self.base, highlightthickness=0,
                         highlightbackground=BLACK, bd=1, relief="solid")
        self.command = command
        self._enabled = True
        pad = (10, 5) if small else (14, 9)
        self.label = tk.Label(self, text=text, bg=self.base, fg=self.fg,
                              font=font(SIZE_SMALL if small else SIZE_BODY, True),
                              padx=pad[0], pady=pad[1], cursor="hand2")
        self.label.pack(fill="both", expand=True)
        if width:
            self.label.configure(width=width)
        for widget in (self, self.label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<Button-1>", self._on_press)
            widget.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _e=None):
        if self._enabled:
            self.configure(bg=self.hover)
            self.label.configure(bg=self.hover)

    def _on_leave(self, _e=None):
        if self._enabled:
            self.configure(bg=self.base)
            self.label.configure(bg=self.base)

    def _on_press(self, _e=None):
        if self._enabled:
            self.label.configure(relief="sunken", bd=1)

    def _on_release(self, _e=None):
        if not self._enabled:
            return
        self.label.configure(relief="flat", bd=0)
        if self.command:
            self.command()

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        color = self.base if enabled else GRAY_2
        self.configure(bg=color)
        self.label.configure(bg=color, fg=self.fg if enabled else GRAY_4,
                             cursor="hand2" if enabled else "arrow")


class SquareCheck(tk.Frame):
    """方形勾选框：白底黑框，选中后填色并画一个叉（包豪斯几何感）。"""

    def __init__(self, master, text: str, variable: tk.BooleanVar,
                 command=None, accent: str = RED, bg: str = PANEL_BG,
                 wrap: int = 0, size: int = 15):
        super().__init__(master, bg=bg)
        self.var = variable
        self.command = command
        self.accent = accent
        self.size = size
        self.box = tk.Canvas(self, width=size, height=size, bg=bg,
                             highlightthickness=0, cursor="hand2")
        self.box.grid(row=0, column=0, sticky="n")
        self.label = tk.Label(self, text=text, bg=bg, fg=INK, font=font(SIZE_BODY),
                              justify="left", anchor="w",
                              wraplength=wrap if wrap else 0, cursor="hand2")
        self.label.grid(row=0, column=1, sticky="w", padx=(8, 0))
        for widget in (self.box, self.label):
            widget.bind("<Button-1>", self._toggle)
        self._redraw()

    def _toggle(self, _e=None):
        self.var.set(not self.var.get())
        self._redraw()
        if self.command:
            self.command()

    def _redraw(self):
        c = self.box
        c.delete("all")
        s = self.size
        if self.var.get():
            c.create_rectangle(0, 0, s - 1, s - 1, fill=self.accent, outline=BLACK, width=2)
            m = s * 0.26
            c.create_line(m, m, s - m, s - m, fill=WHITE, width=2)
            c.create_line(s - m, m, m, s - m, fill=WHITE, width=2)
        else:
            c.create_rectangle(0, 0, s - 1, s - 1, fill=WHITE, outline=BLACK, width=2)

    def refresh(self) -> None:
        self._redraw()


class SquareSlider(tk.Canvas):
    """方形滑杆：一条黑色轨道 + 一个实心方块当滑块（替代圆头 ttk.Scale）。"""

    def __init__(self, master, from_: int, to: int, command=None,
                 accent: str = BLUE, width: int = 190, height: int = 22,
                 bg: str = PANEL_BG):
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, cursor="hand2")
        self.from_ = from_
        self.to = to
        self.command = command
        self.accent = accent
        self.value = from_
        # 注意：不要用 self._w / self._h，tkinter 内部已占用 _w（控件路径名）
        self.track_w = width
        self.track_h = height
        self.bind("<Button-1>", self._on_drag)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_drag)
        self._redraw()

    def _track(self) -> tuple[int, int]:
        return 8, self.track_w - 8

    def _on_drag(self, event):
        x0, x1 = self._track()
        ratio = (event.x - x0) / max(1, (x1 - x0))
        ratio = 0.0 if ratio < 0 else (1.0 if ratio > 1 else ratio)
        self.set(self.from_ + ratio * (self.to - self.from_), notify=True)

    def set(self, value: float, notify: bool = False) -> None:
        value = max(self.from_, min(self.to, value))
        changed = abs(value - self.value) > 1e-9
        self.value = value
        self._redraw()
        if notify and changed and self.command:
            self.command(self.value)

    def get(self) -> float:
        return self.value

    def _redraw(self):
        self.delete("all")
        x0, x1 = self._track()
        y = self.track_h // 2
        self.create_line(x0, y, x1, y, fill=BLACK, width=3)
        ratio = (self.value - self.from_) / max(1e-9, (self.to - self.from_))
        x = x0 + ratio * (x1 - x0)
        self.create_line(x0, y, x, y, fill=self.accent, width=3)
        s = 12
        self.create_rectangle(x - s / 2, y - s / 2, x + s / 2, y + s / 2,
                              fill=self.accent, outline=BLACK, width=2)


class Segmented(tk.Frame):
    """分段选择器：连排方块，选中块填色（比单选圆点更包豪斯）。

    支持逐个置灰：当前图案放不了那么大的档位会被禁用，避免点了没反应。
    """

    def __init__(self, master, options, variable: tk.StringVar, command=None,
                 bg: str = PANEL_BG, accent: str = BLUE, small: bool = False):
        super().__init__(master, bg=bg)
        self.var = variable
        self.command = command
        self.accent = accent
        self.buttons: dict[str, tk.Label] = {}
        self._enabled: dict[str, bool] = {}
        for i, (label, value) in enumerate(options):
            lbl = tk.Label(self, text=label, font=font(SIZE_SMALL, True),
                           bd=1, relief="solid", padx=8 if small else 10,
                           pady=3 if small else 5, cursor="hand2")
            lbl.grid(row=0, column=i, sticky="w")
            lbl.bind("<Button-1>", lambda e, v=value: self._select(v))
            self.buttons[value] = lbl
            self._enabled[value] = True
        self._redraw()

    def _select(self, value):
        if not self._enabled.get(value, True):
            return
        self.var.set(value)
        self._redraw()
        if self.command:
            self.command()

    def set_availability(self, available: dict) -> None:
        """available: {值: 是否可用}；不可用的档位置灰且点击无效。"""
        changed = False
        for value, ok in available.items():
            if self._enabled.get(value) != ok:
                self._enabled[value] = ok
                changed = True
        if changed:
            self._redraw()

    def refresh(self):
        self._redraw()

    def _redraw(self):
        current = self.var.get()
        for value, lbl in self.buttons.items():
            enabled = self._enabled.get(value, True)
            if value == current and enabled:
                lbl.configure(bg=self.accent, fg=WHITE, cursor="hand2")
            elif not enabled:
                lbl.configure(bg=GRAY_1, fg=GRAY_3, cursor="arrow")
            else:
                lbl.configure(bg=WHITE, fg=INK, cursor="hand2")


def resource_path(name: str) -> str:
    """取随程序一起分发的资源路径（打包成 exe 后也能找到）。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def set_window_icon(window: tk.Misc, retry: bool = True) -> None:
    """给窗口设置程序图标（拼豆 + 包豪斯那枚）。

    Windows 上有时候要在窗口映射之后再设一次才生效，所以延迟重设一次。
    """
    ico = resource_path("app.ico")
    png = resource_path("app_icon.png")
    try:
        if os.path.exists(ico):
            window.iconbitmap(default=ico)
    except Exception:      # noqa: BLE001
        pass
    try:
        if os.path.exists(png):
            photo = tk.PhotoImage(file=png)
            window.iconphoto(True, photo)
            window._icon_photo = photo        # 防止被回收     # type: ignore[attr-defined]
    except Exception:      # noqa: BLE001
        pass
    if retry:
        try:
            window.after(400, lambda: set_window_icon(window, retry=False))
        except Exception:      # noqa: BLE001
            pass


def logo_photo(size: int = 40):
    """加载图标 PNG 供界面内显示（用于标题条、声明窗口）。"""
    path = resource_path("app_icon.png")
    if not os.path.exists(path):
        return None
    try:
        photo = tk.PhotoImage(file=path)
        factor = max(1, round(photo.width() / size))
        if factor > 1:
            photo = photo.subsample(factor, factor)
        return photo
    except Exception:      # noqa: BLE001
        return None


def setup_ttk_styles(style, root: tk.Tk) -> None:
    """把 ttk 控件也统一成包豪斯外观（方角、黑白、无渐变）。"""
    style.theme_use("clam")
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT_FAMILY, size=SIZE_BODY)
        except tk.TclError:
            pass

    style.configure(".", background=PAPER, foreground=INK,
                    font=font(SIZE_BODY), borderwidth=0, focuscolor=PAPER)
    style.configure("TFrame", background=PAPER)
    style.configure("Panel.TFrame", background=PANEL_BG)
    style.configure("TLabel", background=PAPER, foreground=INK, font=font(SIZE_BODY))
    style.configure("Panel.TLabel", background=PANEL_BG, foreground=INK)
    style.configure("Muted.TLabel", background=PANEL_BG, foreground=GRAY_4,
                    font=font(SIZE_SMALL))
    style.configure("Title.TLabel", background=PANEL_BG, foreground=BLACK,
                    font=font(SIZE_TITLE, True))

    # 输入框 / 下拉框：白底黑框，方角
    for name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(name, fieldbackground=WHITE, background=WHITE,
                        foreground=INK, bordercolor=BLACK, arrowcolor=BLACK,
                        lightcolor=BLACK, darkcolor=BLACK, insertcolor=BLACK,
                        borderwidth=1, relief="solid", padding=4,
                        selectbackground=BLUE, selectforeground=WHITE)
        style.map(name,
                  fieldbackground=[("readonly", WHITE), ("disabled", GRAY_1)],
                  foreground=[("disabled", GRAY_3)],
                  bordercolor=[("focus", BLUE)],
                  arrowcolor=[("active", RED)])
    style.configure("TCombobox", selectbackground=WHITE, selectforeground=INK)
    root.option_add("*TCombobox*Listbox.background", WHITE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", BLUE)
    root.option_add("*TCombobox*Listbox.selectForeground", WHITE)

    style.configure("Vertical.TScrollbar", background=GRAY_2, troughcolor=PAPER,
                    bordercolor=PAPER, arrowcolor=BLACK, relief="flat", width=12)
    style.configure("Horizontal.TScrollbar", background=GRAY_2, troughcolor=PAPER,
                    bordercolor=PAPER, arrowcolor=BLACK, relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BLUE)])
    style.map("Horizontal.TScrollbar", background=[("active", BLUE)])
