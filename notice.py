# -*- coding: utf-8 -*-
"""启动声明窗口：提示本软件免费开源，谨防付费受骗。

防护设计（分层，越往下越难删）
--------------------------------
第 1 层  声明文案混淆存放 + HMAC 签名（notice_core.py），改文案即校验失败。
第 2 层  校验失败 → 强制每次启动都弹声明，并在主界面顶部常驻红色警告条。
         也就是说「删掉声明」不会让程序更清爽，只会更烦。
第 3 层  主界面标题栏、状态栏、帮助区都常驻「开源免费 · 请勿付费购买」。
第 4 层（最有效）每个导出文件都带免费声明与项目地址：图纸有水印、清单有页脚、
         HTML 有声明区、PNG 元数据里有来源。删代码的人删不掉已发出去的图纸。

勾选「不再显示」后写入 settings.json，下次不再弹；但一旦检测到篡改，
该设置会被忽略并强制重新显示。
"""

from __future__ import annotations

import tkinter as tk

import bauhaus as bh
import notice_core
import settings

NOTICE_VERSION = 2


def _c() -> dict:
    return notice_core.content()


def should_show() -> bool:
    """是否需要显示启动声明（内容被改动过就一定显示）。"""
    ok, _reason = notice_core.verify()
    if not ok:
        return True
    data = settings.load()
    if not data.get("notice_dismissed"):
        return True
    return int(data.get("notice_version") or 0) < NOTICE_VERSION


def integrity() -> tuple[bool, str]:
    return notice_core.verify()


class StartupNotice:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.agreed = tk.BooleanVar(value=False)
        self.result: bool | None = None      # True=继续使用, False=退出程序
        self._build()
        self._center()
        self.window.grab_set()
        self.window.focus_force()
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ 界面 --

    def _build(self) -> None:
        c = _c()
        intact, reason = integrity()

        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.window.title(c.get("title", "重要声明"))
        self.window.configure(bg=bh.BLACK)
        self.window.resizable(False, False)
        bh.set_window_icon(self.window)

        outer = tk.Frame(self.window, bg=bh.BLACK, padx=3, pady=3)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=bh.WHITE)
        card.pack(fill="both", expand=True)

        # ---- 顶部：黑底标题条 + 三原色几何图形 ----
        header = tk.Frame(card, bg=bh.BLACK)
        header.pack(fill="x")
        self.head_canvas = tk.Canvas(header, height=54, bg=bh.BLACK,
                                     highlightthickness=0)
        self.head_canvas.pack(fill="x")
        self.head_canvas.bind("<Configure>", self._paint_header)

        body = tk.Frame(card, bg=bh.WHITE, padx=30, pady=22)
        body.pack(fill="both", expand=True)

        headline = tk.Frame(body, bg=bh.WHITE)
        headline.pack(anchor="w", fill="x")
        chip = tk.Canvas(headline, width=18, height=18, bg=bh.WHITE,
                         highlightthickness=0)
        chip.pack(side="left", pady=(4, 0))
        bh.draw_square(chip, 0, 0, 18, bh.RED)
        tk.Label(headline, text=c.get("header", ""), bg=bh.WHITE, fg=bh.BLACK,
                 font=bh.font(16, True), justify="left", wraplength=540).pack(
            side="left", padx=(10, 0))

        tk.Frame(body, bg=bh.YELLOW, height=8).pack(fill="x", pady=(16, 0))

        tk.Label(body, text=c.get("headline", ""), bg=bh.WHITE, fg=bh.RED,
                 font=bh.font(20, True), anchor="w", justify="left",
                 wraplength=560).pack(anchor="w", pady=(18, 0))

        tk.Label(body, text=c.get("subhead", ""), bg=bh.WHITE, fg=bh.BLACK,
                 font=bh.font(11, True), anchor="w", justify="left",
                 wraplength=560).pack(anchor="w", pady=(8, 0))

        tk.Label(body, text=c.get("detail", ""), bg=bh.WHITE, fg=bh.INK,
                 font=bh.font(10), justify="left", anchor="w",
                 wraplength=560).pack(anchor="w", pady=(12, 0))

        source_row = tk.Frame(body, bg=bh.WHITE)
        source_row.pack(anchor="w", fill="x", pady=(12, 0))
        tk.Label(source_row, text="项目地址", bg=bh.WHITE, fg=bh.GRAY_4,
                 font=bh.font(9)).pack(side="left")
        tk.Label(source_row, text=c.get("source", notice_core.SOURCE_URL), bg=bh.WHITE,
                 fg=bh.BLUE, font=bh.font(10, True)).pack(side="left", padx=(8, 0))

        if not intact:
            warn = tk.Frame(body, bg=bh.RED)
            warn.pack(fill="x", pady=(14, 0))
            tk.Label(warn, text=f"⚠ 检测到声明内容被修改：{reason}\n"
                                f"程序仍可正常使用，但此窗口每次启动都会出现。",
                     bg=bh.RED, fg=bh.WHITE, font=bh.font(9, True),
                     justify="left", anchor="w", wraplength=540,
                     padx=10, pady=8).pack(fill="x")

        tk.Frame(body, bg=bh.GRAY_1, height=1).pack(fill="x", pady=(18, 0))

        bh.SquareCheck(body, c.get("check_text", "我已了解，不再显示此窗口"),
                       self.agreed, accent=bh.BLUE, bg=bh.WHITE,
                       size=16, wrap=520).pack(anchor="w", pady=(16, 0))

        buttons = tk.Frame(body, bg=bh.WHITE)
        buttons.pack(fill="x", pady=(20, 0))
        tk.Label(buttons, text=c.get("footer", ""), bg=bh.WHITE, fg=bh.GRAY_4,
                 font=bh.font(9), justify="left", wraplength=300).pack(side="left")
        bh.BauhausButton(buttons, "我知道了，开始使用", self._on_ok,
                         kind="primary").pack(side="right")
        bh.BauhausButton(buttons, "退出", self._on_close,
                         kind="ghost").pack(side="right", padx=(0, 10))

        self.window.bind("<Return>", lambda e: self._on_ok())
        self.window.bind("<Escape>", lambda e: self._on_close())

    def _paint_header(self, event=None) -> None:
        c = self.head_canvas
        c.delete("all")
        w = event.width if event else c.winfo_width()
        c.create_rectangle(0, 0, w, 54, fill=bh.BLACK, outline=bh.BLACK)
        # 左侧：程序图标（拼豆 + 包豪斯）；没有图标文件时退回手绘三原色几何
        logo = bh.logo_photo(30)
        if logo is not None:
            self._logo_photo = logo          # 防止被回收
            c.create_image(20, 27, image=logo, anchor="w")
            text_x = 20 + logo.width() + 14
        else:
            bh.draw_square(c, 18, 18, 18, bh.RED)
            bh.draw_circle(c, 44, 18, 18, bh.YELLOW)
            c.create_rectangle(70, 22, 100, 32, fill=bh.BLUE, outline=bh.BLUE)
            text_x = 116
        c.create_text(text_x, 27, text=_c().get("title", "重要声明"), anchor="w",
                      fill=bh.WHITE, font=bh.font(13, True))
        c.create_text(w - 18, 27, text="OPEN SOURCE · FREE OF CHARGE",
                      anchor="e", fill=bh.GRAY_3, font=bh.font(8, True))

    def _center(self) -> None:
        self.window.update_idletasks()
        w = self.window.winfo_reqwidth()
        h = self.window.winfo_reqheight()
        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 3)
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.window.after(120, lambda: self.window.attributes("-topmost", False))

    # ------------------------------------------------------------ 行为 --

    def _on_ok(self) -> None:
        self.result = True
        if self.agreed.get():
            ok, _reason = integrity()
            # 只有声明完好时才允许「不再显示」，被改过就必须每次提醒
            settings.save({
                "notice_dismissed": bool(ok),
                "notice_version": NOTICE_VERSION if ok else 0,
                "notice_integrity": "ok" if ok else "broken",
            })
        self.window.grab_release()
        self.window.destroy()

    def _on_close(self) -> None:
        self.result = False
        self.window.grab_release()
        self.window.destroy()


def show_notice(root: tk.Tk) -> bool:
    """显示声明窗口；返回 True 表示可以继续使用程序。"""
    dlg = StartupNotice(root)
    root.wait_window(dlg.window)
    return bool(dlg.result)
