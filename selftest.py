# -*- coding: utf-8 -*-
"""自检脚本：不打开界面，直接跑一遍转换 + 导出流程，确认功能正常。

运行：python selftest.py
"""

from __future__ import annotations

import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except Exception:
        pass

import palette as palette_mod          # noqa: E402
import painter                          # noqa: E402
from core import ConvertOptions, convert_file, estimate_sheets   # noqa: E402

OUT_DIR = os.path.join(BASE_DIR, "自检输出")
FAILS: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  [OK]   " if condition else "  [失败] ") + message)
    if not condition:
        FAILS.append(message)


def ensure_samples() -> list[str]:
    import make_sample
    make_sample.main()
    return [os.path.join(BASE_DIR, n) for n in
            ("示例图片.png", "示例_渐变色卡.png", "示例_爱心透明底.png")]


def main() -> int:
    print("=" * 66)
    print("拼豆图案生成器 · 自检")
    print("=" * 66)

    samples = ensure_samples()
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1. 色卡
    print("\n[1] 色卡")
    for name in palette_mod.palette_names():
        items = palette_mod.get_palette(name)
        check(len(items) >= 8, f"{name} 载入 {len(items)} 种颜色")

    # 2. 基础转换：16×16 / 32×32 / 64×64
    print("\n[2] 不同行列数转换（示例图片）")
    cat = samples[0]
    for cols, rows in ((16, 16), (29, 29), (32, 32), (64, 64), (48, 64)):
        opts = ConvertOptions(cols=cols, rows=rows)
        t0 = time.time()
        pattern = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
        dt = time.time() - t0
        ok = (pattern.cols == cols and pattern.rows == rows
              and pattern.total > 0 and len(pattern.counts()) >= 2)
        check(ok, f"{cols}×{rows} → {pattern.total} 颗豆子 / "
                  f"{len(pattern.counts())} 色 / {dt:.2f}s")

    # 3. 抖动与填充方式
    print("\n[3] 抖动 / 填充方式 / 色卡切换")
    opts = ConvertOptions(cols=32, rows=32, dither=True)
    pattern_dither = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
    check(len(pattern_dither.counts()) >= 4,
          f"开启抖动后有 {len(pattern_dither.counts())} 种颜色（应比不开更多）")

    for mode in ("fit", "fill", "stretch"):
        opts = ConvertOptions(cols=40, rows=24, fit_mode=mode)
        p = convert_file(samples[1], opts, palette_mod.get_palette(opts.palette_name))
        check(p.cols == 40 and p.rows == 24, f"填充方式 {mode} 输出 40×24")

    for name in palette_mod.palette_names():
        opts = ConvertOptions(cols=24, rows=24, palette_name=name)
        p = convert_file(cat, opts, palette_mod.get_palette(name))
        check(len(p.counts()) <= len(palette_mod.get_palette(name)),
              f"色卡「{name}」最多用到 {len(p.counts())} 种颜色")

    # 4. 背景移除 / 透明图
    print("\n[4] 背景移除与透明图片")
    heart = samples[2]
    opts = ConvertOptions(cols=32, rows=32, crop_to_content=True)
    p_keep = convert_file(heart, opts, palette_mod.get_palette(opts.palette_name))
    opts2 = ConvertOptions(cols=32, rows=32, bg_removal=True, bg_tolerance=30,
                           crop_to_content=True)
    p_rm = convert_file(heart, opts2, palette_mod.get_palette(opts2.palette_name))
    check(p_rm.total < p_keep.total,
          f"去掉背景后豆子数减少：{p_keep.total} → {p_rm.total}")

    # 5. 导出
    print("\n[5] 导出文件")
    opts = ConvertOptions(cols=32, rows=32)
    pattern = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
    files = painter.export_all(pattern, OUT_DIR, "自检_32x32", cell=28, title="自检图纸")
    check(len(files) >= 6, f"导出了 {len(files)} 个文件")
    for path in files:
        size = os.path.getsize(path) if os.path.exists(path) else -1
        check(size > 0, f"{os.path.basename(path)}（{size} 字节）")

    # 6. 各种图片格式
    print("\n[6] 各种图片格式")
    import tempfile
    from PIL import Image as PILImage
    from core import _prepare_image

    src_img = PILImage.open(samples[0]).convert("RGB")
    heart_img = PILImage.open(samples[2])
    fmt_cases = [
        ("JPG", ".jpg", src_img),
        ("PNG", ".png", src_img),
        ("WEBP", ".webp", src_img),
        ("BMP", ".bmp", src_img),
        ("GIF", ".gif", src_img.convert("P", palette=PILImage.ADAPTIVE)),
        ("TIFF", ".tiff", src_img),
        ("PNG 透明", ".png", heart_img),
        ("WEBP 透明", ".webp", heart_img),
        ("JPG 灰度", ".jpg", src_img.convert("L")),
        ("JPG CMYK", ".jpg", src_img.convert("CMYK")),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for label, ext, image in fmt_cases:
            path = os.path.join(tmp, f"fmt{ext}")
            try:
                image.save(path)
            except Exception as exc:      # noqa: BLE001
                check(False, f"{label} 保存失败：{exc}")
                continue
            try:
                p = convert_file(path, ConvertOptions(cols=32, rows=32),
                                 palette_mod.get_palette("标准色卡（50 色）"))
                check(p.total > 0 and len(p.counts()) >= 1,
                      f"{label} → {p.total} 颗 / {len(p.counts())} 色")
            except Exception as exc:      # noqa: BLE001
                check(False, f"{label} 转换失败：{exc}")

        # 手机竖拍照片：靠 EXIF 标记方向，必须自动转正
        for orient, expect in ((6, (200, 300)), (8, (200, 300)), (3, (300, 200)), (1, (300, 200))):
            img = PILImage.new("RGB", (300, 200), (255, 255, 255))
            exif = PILImage.Exif()
            exif[274] = orient
            path = os.path.join(tmp, f"rot{orient}.jpg")
            img.save(path, exif=exif)
            size = _prepare_image(path, (255, 255, 255), False, 24, True).size
            check(size == expect,
                  f"EXIF Orientation={orient} → 转正为 {size[0]}×{size[1]}")

    # 7. 长方形图片怎么变成方形图案
    print("\n[7] 长方形 / 竖图 / 全景图")
    import tempfile
    from PIL import Image as PILImage

    def _rect_image(w: int, h: int, path: str) -> str:
        """上亮下暗、左红右蓝的测试图，用来看清裁掉了哪块、留白在哪。"""
        img = PILImage.new("RGB", (w, h))
        px = img.load()
        for y in range(h):
            shade = 1.0 - 0.8 * (y / max(1, h - 1))
            for x in range(w):
                base = (220, 60, 60) if x < w / 2 else (60, 90, 220)
                px[x, y] = tuple(int(c * shade) for c in base)
        img.save(path)
        return path

    palette_items = palette_mod.get_palette("标准色卡（50 色）")

    def _mean_rgb(pat, indexes) -> tuple[int, int, int]:
        vals = [pat.rgb[i] for i in indexes if i >= 0]
        if not vals:
            return (0, 0, 0)
        return tuple(sum(v[c] for v in vals) // len(vals) for c in range(3))     # type: ignore[return-value]

    with tempfile.TemporaryDirectory() as tmp:
        wide = _rect_image(960, 540, os.path.join(tmp, "wide.png"))
        tall = _rect_image(300, 900, os.path.join(tmp, "tall.png"))

        # 模式 fit：不许裁掉内容，短边方向应该是空格
        p_fit = convert_file(wide, ConvertOptions(cols=32, rows=32, fit_mode="fit"), palette_items)
        empty = sum(1 for row in p_fit.index for v in row if v < 0)
        check(0 < empty < 32 * 32, f"横图用「完整放入」：上下留白 {empty} 格，内容没被裁掉")
        check(all(v < 0 for v in p_fit.index[0]),
              "横图用「完整放入」：顶行是空格")
        check(any(v >= 0 for v in p_fit.index[p_fit.rows // 2]),
              "横图用「完整放入」：中间行有豆子")

        # 模式 fill：不留空，豆子占满
        p_fill = convert_file(wide, ConvertOptions(cols=32, rows=32, fit_mode="fill"), palette_items)
        check(p_fill.total == 32 * 32, "横图用「裁切填满」：1024 格全部有豆子（无留白）")

        # 模式 stretch：也不留空，但比例会变
        p_st = convert_file(wide, ConvertOptions(cols=32, rows=32, fit_mode="stretch"), palette_items)
        check(p_st.total == 32 * 32, "横图用「拉伸」：1024 格全部有豆子")

        # 竖图 + 裁切位置：靠上要保留更亮的上半部分，靠下保留更暗的下半部分
        bright = {}
        for anchor in ("center", "top", "bottom"):
            p = convert_file(tall, ConvertOptions(cols=32, rows=32, fit_mode="fill",
                                                  crop_anchor=anchor), palette_items)
            bright[anchor] = sum(_mean_rgb(p, set(p.index[0])))
        check(bright["top"] > bright["center"] > bright["bottom"],
              f"竖图裁切位置生效：靠上 {bright['top']} > 居中 {bright['center']} "
              f"> 靠下 {bright['bottom']}（保留的部分越来越暗）")

        # 竖图在 fit 模式下左右留白
        p_tall_fit = convert_file(tall, ConvertOptions(cols=32, rows=32, fit_mode="fit"),
                                  palette_items)
        check(all(v < 0 for v in (row[0] for row in p_tall_fit.index)),
              "竖图用「完整放入」：左右留白")

        # 长方形图案格子：输出可以不是正方形
        p_wide_grid = convert_file(wide, ConvertOptions(cols=64, rows=32, fit_mode="fill"),
                                   palette_items)
        check(p_wide_grid.cols == 64 and p_wide_grid.rows == 32,
              "可以输出长方形图案：64 列 × 32 行")

        # 全景/超宽图不崩
        pano = _rect_image(1200, 200, os.path.join(tmp, "pano.png"))
        for mode in ("fit", "fill", "stretch"):
            p = convert_file(pano, ConvertOptions(cols=48, rows=48, fit_mode=mode), palette_items)
            check(p.total > 0, f"全景图 6:1 用 {mode} 正常：{p.total} 颗")

    # 8. 超大尺寸（最高 1024 × 1024）
    print("\n[8] 超大尺寸 256 / 512 / 1024")
    big = os.path.join(OUT_DIR, "大尺寸")
    os.makedirs(big, exist_ok=True)
    for n in (256, 512, 1024):
        opts = ConvertOptions(cols=n, rows=n)
        t0 = time.time()
        pattern = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
        dt = time.time() - t0
        ok = pattern.total == n * n and pattern.cols == n and pattern.rows == n
        check(ok, f"{n}×{n} → {pattern.total} 颗 / {len(pattern.counts())} 色 / 转换 {dt:.2f}s")

    # 1024 开抖动（顺序 Floyd–Steinberg + 查表）
    opts = ConvertOptions(cols=1024, rows=1024, dither=True)
    t0 = time.time()
    p1024 = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
    dt = time.time() - t0
    check(len(p1024.counts()) > 25,
          f"1024×1024 开抖动：{len(p1024.counts())} 色 / 耗时 {dt:.2f}s（应 < 4s）")

    # 1024 的导出：图纸 + 清单，超大时自动跳过 SVG / HTML
    t0 = time.time()
    files = painter.export_all(p1024, big, "大尺寸_1024", title="1024 × 1024")
    dt = time.time() - t0
    check(len(files) == 5, f"1024×1024 导出 {len(files)} 个文件（SVG/HTML 自动跳过）/ {dt:.2f}s")
    for path in files:
        check(os.path.getsize(path) > 0, f"{os.path.basename(path)}（{os.path.getsize(path) // 1024} KB）")

    # 长方形 + 去背景在超大尺寸下也要正常
    opts = ConvertOptions(cols=1024, rows=256, bg_removal=True, bg_tolerance=28)
    p_wide = convert_file(samples[2], opts, palette_mod.get_palette(opts.palette_name))
    check(p_wide.cols == 1024 and p_wide.rows == 256,
          f"1024×256 长方形图案 + 去背景：{p_wide.total} 颗")

    # 9. 边界情况
    print("\n[9] 边界情况")
    opts = ConvertOptions(cols=4, rows=4, dither=True)
    p_small = convert_file(cat, opts, palette_mod.get_palette(opts.palette_name))
    check(p_small.cols == 4 and p_small.rows == 4, "极小尺寸 4×4 可用")

    big = painter.render_chart(pattern, cell=8)
    check(big.width > 0 and big.height > 0, f"小格子渲染正常（{big.width}×{big.height}）")
    check(estimate_sheets(64, 64) == 9, "64×64 估算 9 块 29×29 拼豆板")

    print("\n" + "=" * 66)
    if FAILS:
        print(f"自检结束：{len(FAILS)} 项未通过")
        for item in FAILS:
            print("   -", item)
        return 1
    print("自检结束：全部通过 ✔")
    print(f"输出目录：{OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
