# -*- coding: utf-8 -*-
"""GUI 冒烟测试：真实创建窗口、载入图片、等待转换、渲染图纸、检查清单，然后退出。

不会弹出文件对话框，也不会阻塞（窗口建好后立即 withdraw）。
运行：python guitest.py
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

import studio   # noqa: E402

FAILS: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  [OK]   " if cond else "  [失败] ") + msg)
    if not cond:
        FAILS.append(msg)


def pump(root: tk.Tk, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def main() -> int:
    print("=" * 66)
    print("GUI 冒烟测试")
    print("=" * 66)

    # 清掉上次保存的窗口/尺寸偏好，保证测试从默认状态开始（也顺带验证设置可重置）
    import settings
    settings.save({"notice_dismissed": True, "notice_version": 1,
                   "window_geometry": "", "last_palette": "",
                   "last_cols": 32, "last_rows": 32, "last_fit_mode": "fit"})

    root = tk.Tk()
    app = studio.StudioApp(root)
    root.withdraw()
    pump(root, 0.6)
    check(app.chart_canvas.winfo_exists() == 1, "主窗口与画布创建成功")

    sample = os.path.join(BASE_DIR, "示例图片.png")
    check(os.path.exists(sample), "示例图片存在")

    print("\n[1] 载入图片并等待转换 (32×32)")
    app.load_image(sample)
    deadline = time.time() + 40
    while app.pattern is None and time.time() < deadline:
        pump(root, 0.1)
    check(app.pattern is not None, "转换完成并拿到图案")
    if app.pattern is None:
        return 1
    check(app.pattern.cols == 32 and app.pattern.rows == 32, "尺寸为 32×32")
    legend = app.legend_text.get("1.0", "end").strip().splitlines()
    check(len(legend) == len(app.pattern.counts()),
          f"清单行数 = 颜色数（{len(app.pattern.counts())}）")
    check(all("颗" in line for line in legend), "清单每行都有颗数")
    deadline = time.time() + 5
    while app.chart_image is None and time.time() < deadline:
        pump(root, 0.1)
    check(app.chart_image is not None,
          f"图纸已渲染到画布（渲染错误：{app._chart_error or '无'}）")
    check("颗豆子" in app.var_summary.get(), f"摘要：{app.var_summary.get()}")

    print("\n[2] 切换行列数（模拟输入 64 / 64）")
    app.var_link.set(True)
    app.var_cols.set(64)
    app.var_rows.set(64)
    deadline = time.time() + 40
    while (app.pattern is None or app.pattern.cols != 64) and time.time() < deadline:
        pump(root, 0.1)
    check(app.pattern is not None and app.pattern.cols == 64, "重新转换为 64×64")

    print("\n[3] 切换色卡 / 抖动 / 填充方式 / 去背景")
    app.var_palette.set("极简色卡（16 色）")
    app.request_convert(force=True)
    deadline = time.time() + 40
    while time.time() < deadline:
        pump(root, 0.1)
        if app._worker and not app._worker.is_alive():
            pump(root, 0.3)
            break
    check(app.pattern is not None and len(app.pattern.counts()) <= 16,
          f"极简色卡生效（用了 {len(app.pattern.counts()) if app.pattern else 0} 色）")

    for var, value, label in ((app.var_dither, True, "抖动"),
                              (app.var_bg_removal, True, "去背景"),
                              (app.var_fit, "fill", "裁满")):
        if isinstance(var, tk.BooleanVar):
            var.set(value)
        else:
            var.set(value)
        app.request_convert(force=True)
        deadline = time.time() + 40
        while time.time() < deadline:
            pump(root, 0.1)
            if app._worker and not app._worker.is_alive():
                pump(root, 0.3)
                break
        check(app.pattern is not None, f"切换「{label}」后仍能生成图案")

    print("\n[4] 图纸显示选项")
    for label, var in (("关闭坐标", app.var_ruler), ("关闭网格线", app.var_gridlines)):
        var.set(not var.get())
        app.render_chart()
        pump(root, 0.5)
        check(app.chart_image is not None, f"{label} 后仍能渲染")
        var.set(not var.get())
    app.var_mode.set("flat")
    app.render_chart()
    pump(root, 0.6)
    check(app.chart_image is not None, "成品效果模式渲染正常")
    app.var_mode.set("bead")

    print("\n[5] 缩放（每个可用档位都必须有可见变化）")
    sizes = {}
    usable = []
    for label, _factor in studio.ZOOM_STEPS:
        app.var_zoom.set(label)
        app._on_zoom()
        pump(root, 0.8)
        sizes[label] = (app.chart_image.width(), app.chart_image.height())
        check(app.chart_image is not None and app.chart_image.width() > 0,
              f"「{label}」渲染成功 → {sizes[label][0]}×{sizes[label][1]} px")
    for label, _factor in studio.ZOOM_STEPS:
        if app.seg_zoom._enabled.get(label, True):
            usable.append(label)
    distinct = len(set(sizes[label] for label in usable))
    check(distinct == len(usable),
          f"{len(usable)} 个可用档位产生 {distinct} 种不同尺寸（必须各不相同）")
    numeric = [sizes[lbl][0] for lbl, f in studio.ZOOM_STEPS if f > 0 and lbl in usable]
    check(numeric == sorted(numeric) and len(set(numeric)) == len(numeric),
          f"可用倍率尺寸递增：{numeric}")
    check(len(usable) >= 3, f"64×64 至少 3 个档位可用：{'/'.join(usable)}")
    check("适应" in usable and "1×" in usable, "「适应」和「1×」始终可用")
    check(app.var_zoom_hint.get() != "", f"缩放提示有内容：{app.var_zoom_hint.get()}")
    # 「适应」和「1×」不能是同一个尺寸，否则用户会以为点了没反应
    check(sizes["适应"] != sizes["1×"],
          f"「适应」{sizes['适应'][0]}px ≠ 「1×」{sizes['1×'][0]}px（曾经相等＝点击无效）")
    app.var_zoom.set("适应")
    app._on_zoom()
    pump(root, 0.8)

    print("\n[6] 超大尺寸 512 / 1024")
    for size in (512, 1024):
        app.var_link.set(True)
        app.var_cols.set(size)
        app.var_rows.set(size)
        deadline = time.time() + 180
        while (app.pattern is None or app.pattern.cols != size
               or app.pattern.rows != size) and time.time() < deadline:
            pump(root, 0.1)
        pump(root, 1.5)
        ok = (app.pattern is not None and app.pattern.cols == size
              and app.pattern.rows == size and app.pattern.total == size * size)
        check(ok, f"{size}×{size} 生成 {app.pattern.total if app.pattern else 0} 颗豆子")
        check(app.chart_image is not None and app.chart_image.width() > 100,
              f"{size}×{size} 图纸已渲染（{app.chart_image.width()}px）")

    app.var_zoom.set("2×")
    app._on_zoom()
    pump(root, 1.5)
    check(app.chart_image is not None and app.chart_image.width() > 1000,
          f"1024 图纸放大到 2× 仍可渲染（{app.chart_image.width()}px）")
    app.var_zoom.set("适应")
    app._on_zoom()
    pump(root, 1.0)

    print("\n[7] 复制清单到剪贴板")
    app.copy_counts()
    pump(root, 0.2)
    text = root.clipboard_get()
    check("拼豆豆子清单" in text and len(text) > 20, "剪贴板内容正确")

    print("\n[8] 导出（不弹对话框，直接调 painter）")
    import painter
    out = os.path.join(BASE_DIR, "自检输出", "gui")
    os.makedirs(out, exist_ok=True)
    app.var_link.set(True)
    app.var_cols.set(48)
    app.var_rows.set(48)
    app.request_convert(force=True)
    deadline = time.time() + 40
    while time.time() < deadline:
        pump(root, 0.1)
        if app.pattern is not None and app.pattern.cols == 48 and not (
                app._worker and app._worker.is_alive()):
            break
    files = painter.export_all(app.pattern, out, "GUI_48x48", cell=24, title="GUI 测试")
    check(all(os.path.getsize(f) > 0 for f in files), f"导出 {len(files)} 个文件均非空")

    print("\n[9] 关闭窗口")
    root.destroy()
    check(True, "窗口正常销毁")

    print("\n" + "=" * 66)
    if FAILS:
        print(f"GUI 冒烟测试未通过 {len(FAILS)} 项：")
        for f in FAILS:
            print("   -", f)
        return 1
    print("GUI 冒烟测试全部通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
