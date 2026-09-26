# -*- coding: utf-8 -*-
"""界面截图：启动声明窗口 + 主界面（包豪斯风格），保存到 _预览 目录。

运行：python screenshot.py
"""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import notice as notice_mod   # noqa: E402
import settings               # noqa: E402
import studio                 # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "_预览")


def pump(root: tk.Tk, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def _hwnd_of(root: tk.Tk) -> int:
    frame = root.frame()
    return int(frame, 16) if frame.startswith("0x") else int(frame)


def grab_window(root: tk.Tk):
    """用 Win32 PrintWindow 直接取窗口画面（不受遮挡、不受 DPI 缩放影响）。"""
    from PIL import Image, ImageGrab

    root.lift()
    root.update()
    time.sleep(0.5)
    root.update()

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hwnd = _hwnd_of(root)
        rect = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        hdc = user32.GetWindowDC(wintypes.HWND(hwnd))
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        gdi32.SelectObject(mem, bmp)
        ok = user32.PrintWindow(wintypes.HWND(hwnd), mem, 2)   # PW_RENDERFULLCONTENT

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = w
        header.biHeight = -h
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(header), 0)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(wintypes.HWND(hwnd), hdc)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        print(f"PrintWindow 成功：{w}x{h}")
        if ok:
            return img
    except Exception as exc:      # noqa: BLE001
        print("PrintWindow 失败，改用整屏裁剪：", exc)
    return ImageGrab.grab(all_screens=True)


def save(img, name: str) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print("界面截图：", path, img.size)


def main() -> int:
    # 先把「不再显示」清掉，保证每次都能拍到启动声明
    settings.save({"notice_dismissed": False, "notice_version": 0})

    root = tk.Tk()
    root.withdraw()

    # ---- 1) 启动声明窗口 ----
    notice = notice_mod.StartupNotice(root)
    pump(root, 1.0)
    save(grab_window(notice.window), "启动声明.png")
    notice.window.grab_release()
    notice.window.destroy()
    root.update()

    # ---- 2) 主界面 ----
    root.deiconify()
    app = studio.StudioApp(root)
    root.geometry("1380x940+20+10")
    root.update()
    pump(root, 0.8)

    sample = os.path.join(BASE_DIR, "示例图片.png")
    if os.path.exists(sample):
        app.load_image(sample)
    deadline = time.time() + 30
    while app.pattern is None and time.time() < deadline:
        pump(root, 0.1)
    pump(root, 1.6)
    save(grab_window(root), "界面截图.png")

    app.var_link.set(True)
    app.var_cols.set(64)
    app.var_rows.set(64)
    deadline = time.time() + 30
    while (app.pattern is None or app.pattern.cols != 64) and time.time() < deadline:
        pump(root, 0.1)
    pump(root, 1.6)
    save(grab_window(root), "界面截图_64x64.png")

    app.var_mode.set("flat")
    app.render_chart()
    pump(root, 1.5)
    save(grab_window(root), "界面截图_成品效果.png")

    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
