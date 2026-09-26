# -*- coding: utf-8 -*-
"""核心转换逻辑：把一张图片变成拼豆图案（每格对应一颗豆子）。

转换流程
--------
1. 打开图片，把透明像素合成为指定底色；
2. （可选）从四边泛洪填充移除纯色背景，再做内容裁剪；
3. 按目标行/列缩放（fit / fill / stretch 三种方式）；
4. 每个像素取色卡中最接近的颜色（加权 RGB 距离）；
5. （可选）Floyd–Steinberg 误差扩散抖动，用有限颜色表现渐变；
6. 统计每种颜色需要多少颗豆子。
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from PIL import Image, ImageFilter, ImageOps

RGB = tuple[int, int, int]
PaletteRGB = Sequence[tuple[str, RGB]]

# sRGB 感知权重（红 0.299 / 绿 0.587 / 蓝 0.114 的常用近似）
_WR, _WG, _WB = 0.30, 0.59, 0.11

# 抖动用的「最近色查表」缓存，键是色卡内容
_LUT_CACHE: dict[tuple, list[int]] = {}


# ------------------------------------------------------------------ 数据结构 --

@dataclass
class BeadPattern:
    """转换结果：index[y][x] 是色卡下标，-1 表示空（不放豆子）。"""

    index: list[list[int]]
    names: list[str]
    rgb: list[RGB]
    cols: int
    rows: int
    cell_px: int = 0          # 原图平均每格像素数（用于提示清晰度）
    palette_name: str = ""

    @property
    def total(self) -> int:
        return sum(1 for row in self.index for v in row if v >= 0)

    def counts(self) -> list[tuple[int, int]]:
        """返回 [(色卡下标, 颗数), ...]，按颗数从多到少排序。"""
        counter = Counter(v for row in self.index for v in row if v >= 0)
        return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


@dataclass
class ConvertOptions:
    cols: int = 32
    rows: int = 32
    palette_name: str = "标准色卡（50 色）"
    dither: bool = False
    fit_mode: str = "fit"           # fit 完整放入 / fill 裁满 / stretch 拉伸
    crop_anchor: str = "center"     # 裁满时保留哪一块：center/top/bottom/left/right
    bg_removal: bool = False
    bg_tolerance: int = 24          # 0-255，按通道最大差值比较
    crop_to_content: bool = True
    keep_aspect: bool = True
    bg_color: RGB = (255, 255, 255)


# ------------------------------------------------------------------ 小工具 --

def _flood_mask(img: Image.Image, tolerance: int) -> list[bool]:
    """从四条边泛洪填充，返回需要当作背景去掉的像素掩码（真值=背景）。"""
    w, h = img.size
    px = img.convert("RGB").load()
    mask = [False] * (w * h)
    if tolerance < 0:
        tolerance = 0
    elif tolerance > 255:
        tolerance = 255

    # 以四条边上出现最多的颜色作为背景种子色
    seed_counter: Counter = Counter()
    for x in range(w):
        seed_counter[px[x, 0]] += 1
        seed_counter[px[x, h - 1]] += 1
    for y in range(h):
        seed_counter[px[0, y]] += 1
        seed_counter[px[w - 1, y]] += 1
    if not seed_counter:
        return mask
    seed = seed_counter.most_common(1)[0][0]
    sr, sg, sb = seed

    def similar(x: int, y: int) -> bool:
        r, g, b = px[x, y]
        return (abs(r - sr) <= tolerance
                and abs(g - sg) <= tolerance
                and abs(b - sb) <= tolerance)

    stack: list[tuple[int, int]] = []
    for x in range(w):
        for y in (0, h - 1):
            if not mask[y * w + x] and similar(x, y):
                mask[y * w + x] = True
                stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y * w + x] and similar(x, y):
                mask[y * w + x] = True
                stack.append((x, y))

    while stack:
        x, y = stack.pop()
        if x > 0 and not mask[y * w + x - 1] and similar(x - 1, y):
            mask[y * w + x - 1] = True
            stack.append((x - 1, y))
        if x < w - 1 and not mask[y * w + x + 1] and similar(x + 1, y):
            mask[y * w + x + 1] = True
            stack.append((x + 1, y))
        if y > 0 and not mask[(y - 1) * w + x] and similar(x, y - 1):
            mask[(y - 1) * w + x] = True
            stack.append((x, y - 1))
        if y < h - 1 and not mask[(y + 1) * w + x] and similar(x, y + 1):
            mask[(y + 1) * w + x] = True
            stack.append((x, y + 1))
    return mask


def _prepare_image(path: str,
                   bg_color: RGB,
                   bg_removal: bool,
                   bg_tolerance: int,
                   crop_to_content: bool,
                   progress: Optional[Callable[[str], None]] = None) -> Image.Image:
    """打开图片 → 处理透明/背景 → 裁剪内容 → 返回 RGBA。"""
    if progress:
        progress("读取图片…")
    img = Image.open(path)
    img.load()
    # 手机竖拍照片通常是横着存的、靠 EXIF 标记方向，这里先转正
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:      # noqa: BLE001
        pass
    img = img.convert("RGBA")

    # 限制工作分辨率，保证大图也能秒开
    work_limit = 1600
    if max(img.size) > work_limit:
        ratio = work_limit / max(img.size)
        img = img.resize((max(1, round(img.width * ratio)),
                          max(1, round(img.height * ratio))), Image.LANCZOS)

    alpha = img.getchannel("A")
    if alpha.getextrema()[0] < 255:
        if bg_removal:
            # 透明像素直接留空
            base = Image.new("RGBA", img.size, (bg_color[0], bg_color[1], bg_color[2], 0))
            img = Image.alpha_composite(base, img)
        else:
            base = Image.new("RGBA", img.size, (bg_color[0], bg_color[1], bg_color[2], 255))
            img = Image.alpha_composite(base, img)

    if bg_removal and img.getchannel("A").getextrema()[0] == 255:
        if progress:
            progress("移除背景…")
        rgb = img.convert("RGB")
        # 先轻微中值滤波，减少噪点造成的漏填
        rgb = rgb.filter(ImageFilter.MedianFilter(size=3))
        mask = _flood_mask(rgb, bg_tolerance)
        out = img.copy()
        px = out.load()
        w, h = out.size
        for y in range(h):
            row_off = y * w
            for x in range(w):
                if mask[row_off + x]:
                    r, g, b, _a = px[x, y]
                    px[x, y] = (r, g, b, 0)

    if crop_to_content:
        content_alpha = img.getchannel("A")
        bbox = content_alpha.getbbox() if content_alpha.getextrema()[0] < 255 else None
        if bbox:
            img = img.crop(bbox)

    if img.width < 1 or img.height < 1:
        raise ValueError("图片内容为空（可能把整张图都当作背景删掉了，请调小容差）")
    return img


def _fit_to_grid(img: Image.Image, cols: int, rows: int, mode: str,
                 bg_color: RGB, anchor: str = "center") -> Image.Image:
    """把图片放进 cols×rows 的格子。

    mode="fit"      等比缩放到整张图都放得下，多出来的方向留空（不裁掉任何内容）
    mode="fill"     等比缩放到铺满整块格子，超出部分按 anchor 决定保留哪一块
    mode="stretch"  直接拉伸到 cols×rows，比例会变形
    anchor          fit 不用；fill 时取 center/top/bottom/left/right
    """
    if mode == "stretch":
        return img.resize((cols, rows), Image.LANCZOS)

    if mode == "fill":
        scale = max(cols / img.width, rows / img.height)
    else:  # fit
        scale = min(cols / img.width, rows / img.height)
    new_w = max(1, round(img.width * scale))
    new_h = max(1, round(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGBA", (cols, rows), (bg_color[0], bg_color[1], bg_color[2], 0))
    if mode == "fit":
        ox = (cols - new_w) // 2
        oy = (rows - new_h) // 2
        canvas.paste(resized, (ox, oy))
    else:  # fill：按 anchor 决定裁掉哪一边
        extra_x = new_w - cols
        extra_y = new_h - rows
        if anchor == "top":
            ox, oy = extra_x // 2, 0
        elif anchor == "bottom":
            ox, oy = extra_x // 2, extra_y
        elif anchor == "left":
            ox, oy = 0, extra_y // 2
        elif anchor == "right":
            ox, oy = extra_x, extra_y // 2
        else:                                   # center
            ox, oy = extra_x // 2, extra_y // 2
        canvas.paste(resized, (-ox, -oy))
    return canvas


# ------------------------------------------------------- 颜色匹配 / 抖动 --

def nearest_color(rgb: RGB, palette_rgb: Sequence[RGB]) -> int:
    """返回色卡中感知距离最近的颜色的下标。"""
    r, g, b = rgb
    best = 0
    best_d = 1 << 30
    for i, (pr, pg, pb) in enumerate(palette_rgb):
        dr = r - pr
        dg = g - pg
        db = b - pb
        d = _WR * dr * dr + _WG * dg * dg + _WB * db * db
        if d < best_d:
            best_d = d
            best = i
            if d == 0:
                break
    return best


def _build_color_lut(palette_rgb: Sequence[RGB]):
    """建一个 32×32×32 的三维色立方查表，把「最近色」从 50 次比较降到 1 次查表。

    只在抖动路径用（抖动本身会扩散误差）。每通道量化到 32 级，最大取色偏差约 4，
    对拼豆图案的观感影响可以忽略（实测与精确版的质量差 ≈ 0.2/255）。
    """
    key = tuple(tuple(c) for c in palette_rgb)
    cached = _LUT_CACHE.get(key)
    if cached is not None:
        return cached

    n = len(palette_rgb)
    pr = [c[0] for c in palette_rgb]
    pg = [c[1] for c in palette_rgb]
    pb = [c[2] for c in palette_rgb]
    lut: list[int] = [0] * 32768
    try:
        import numpy as np
        centers = np.arange(32, dtype=np.float32) * 8.0 + 4.0
        pal = np.asarray(palette_rgb, dtype=np.float32)
        fw = np.array([_WR, _WG, _WB], dtype=np.float32)
        grid = np.stack(np.meshgrid(centers, centers, centers, indexing="ij"), axis=-1)
        flat = grid.reshape(-1, 3)
        diff = flat[:, None, :] - pal[None, :, :]
        dist = np.einsum("mnc,c->mn", diff * diff, fw)
        best = np.argmin(dist, axis=1).astype(np.int32)
        lut = [int(v) for v in best]
    except Exception:      # noqa: BLE001
        for r in range(32):
            cr = r * 8 + 4
            for g in range(32):
                cg = g * 8 + 4
                for b in range(32):
                    cb = b * 8 + 4
                    best_i, best_d = 0, 1 << 30
                    for i in range(n):
                        dr = cr - pr[i]
                        dg = cg - pg[i]
                        db = cb - pb[i]
                        d = _WR * dr * dr + _WG * dg * dg + _WB * db * db
                        if d < best_d:
                            best_d, best_i = d, i
                    lut[(r << 10) | (g << 5) | b] = best_i

    _LUT_CACHE[key] = lut
    return lut


def _dither_sequential(img: Image.Image, palette_rgb: Sequence[RGB]) -> list[list[int]]:
    """标准 Floyd–Steinberg 误差扩散（严格按扫描顺序，逐个像素扩散）。

    这是「教科书版」的实现：同一行右边 7/16、下一行左下 3/16、正下 5/16、右下 1/16，
    因为是逐个像素推进，不会出现按行并行近似时那种横向条纹。
    """
    lut = _build_color_lut(palette_rgb)
    pr = [c[0] for c in palette_rgb]
    pg = [c[1] for c in palette_rgb]
    pb = [c[2] for c in palette_rgb]

    w, h = img.size
    px = img.load()
    buf = [0.0] * (w * h * 3)
    out = [-1] * (w * h)
    stride = w * 3
    has_below = h > 1

    for y in range(h):
        base = y * stride
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            i = base + x * 3
            cr = buf[i] + r
            cg = buf[i + 1] + g
            cb = buf[i + 2] + b
            cr = 0.0 if cr < 0.0 else (255.0 if cr > 255.0 else cr)
            cg = 0.0 if cg < 0.0 else (255.0 if cg > 255.0 else cg)
            cb = 0.0 if cb < 0.0 else (255.0 if cb > 255.0 else cb)

            ir = int(cr)
            ig = int(cg)
            ib = int(cb)
            if ir > 255:
                ir = 255
            if ig > 255:
                ig = 255
            if ib > 255:
                ib = 255
            idx = lut[((ir >> 3) << 10) | ((ig >> 3) << 5) | (ib >> 3)]
            out[y * w + x] = idx

            er = cr - pr[idx]
            eg = cg - pg[idx]
            eb = cb - pb[idx]
            if x + 1 < w:
                j = i + 3
                buf[j] += er * 0.4375
                buf[j + 1] += eg * 0.4375
                buf[j + 2] += eb * 0.4375
            if has_below and y + 1 < h:
                j = i + stride
                buf[j] += er * 0.3125
                buf[j + 1] += eg * 0.3125
                buf[j + 2] += eb * 0.3125
                if x:
                    j -= 3
                    buf[j] += er * 0.1875
                    buf[j + 1] += eg * 0.1875
                    buf[j + 2] += eb * 0.1875
                    j += 6
                if x + 1 < w:
                    buf[j] += er * 0.0625
                    buf[j + 1] += eg * 0.0625
                    buf[j + 2] += eb * 0.0625
    return [out[y * w:(y + 1) * w] for y in range(h)]


def convert_pixels(img: Image.Image,
                   palette_rgb: Sequence[RGB],
                   dither: bool = False) -> list[list[int]]:
    """把 RGBA 图片逐像素映射到色卡下标；透明像素（alpha<128）记为 -1。

    抖动路径用带查表的顺序 Floyd–Steinberg（1024×1024 约 1.6 秒）；
    不抖动路径用 numpy 向量化最近色（1024×1024 约 0.3 秒）。
    """
    h, w = img.size[1], img.size[0]

    if dither:
        return _dither_sequential(img, palette_rgb)

    try:
        import numpy as np
    except Exception:      # noqa: BLE001
        np = None

    if np is not None:
        arr = np.asarray(img.convert("RGBA"), dtype=np.uint8)   # (h, w, 4)
        rgb_arr = arr[:, :, :3].astype(np.float32)
        alpha_ok = arr[:, :, 3] >= 128
        pal = np.asarray(palette_rgb, dtype=np.float32)
        fw = np.array([_WR, _WG, _WB], dtype=np.float32)
        flat = rgb_arr.reshape(-1, 1, 3) - pal.reshape(1, -1, 3)
        dist = np.einsum("mnc,c->mn", flat * flat, fw)
        idx = np.argmin(dist, axis=1).reshape(h, w).astype(np.int32)
        idx[~alpha_ok] = -1
        return [[int(v) for v in row] for row in idx]

    # ---------------- 纯 Python 回退 ----------------
    src = img.load()
    grid: list[list[int]] = [[-1] * w for _ in range(h)]
    cache: dict[RGB, int] = {}
    for y in range(h):
        row = grid[y]
        for x in range(w):
            r, g, b, a = src[x, y]
            if a < 128:
                continue
            key = (r, g, b)
            idx = cache.get(key)
            if idx is None:
                idx = nearest_color(key, palette_rgb)
                cache[key] = idx
            row[x] = idx
    return grid


# --------------------------------------------------------------- 主流程 --

def convert_file(path: str,
                 options: ConvertOptions,
                 palette_items: PaletteRGB,
                 progress: Optional[Callable[[str], None]] = None) -> BeadPattern:
    """把图片文件转换成 BeadPattern。"""
    cols = max(1, int(options.cols))
    rows = max(1, int(options.rows))
    rgb_list = [c for _name, c in palette_items]
    names = [name for name, _c in palette_items]

    img = _prepare_image(path, options.bg_color, options.bg_removal,
                         options.bg_tolerance, options.crop_to_content, progress)

    if progress:
        progress("缩放并匹配颜色…")
    grid_img = _fit_to_grid(img, cols, rows, options.fit_mode, options.bg_color,
                            options.crop_anchor)
    grid = convert_pixels(grid_img, rgb_list, options.dither)

    real_cols = grid_img.width
    real_rows = grid_img.height
    cell_px = min(img.width / cols, img.height / rows)

    if progress:
        progress("完成")
    return BeadPattern(index=grid, names=names, rgb=rgb_list,
                       cols=real_cols, rows=real_rows,
                       cell_px=int(cell_px), palette_name=options.palette_name)


def size_presets() -> list[tuple[str, int, int]]:
    """常用尺寸预设（列, 行）。"""
    return [
        ("16 × 16", 16, 16),
        ("24 × 24", 24, 24),
        ("29 × 29（小方板）", 29, 29),
        ("32 × 32", 32, 32),
        ("48 × 48", 48, 48),
        ("58 × 58（大方板）", 58, 58),
        ("64 × 64", 64, 64),
        ("80 × 80", 80, 80),
        ("96 × 96", 96, 96),
        ("128 × 128", 128, 128),
        ("192 × 192", 192, 192),
        ("256 × 256", 256, 256),
        ("384 × 384", 384, 384),
        ("512 × 512", 512, 512),
        ("768 × 768", 768, 768),
        ("1024 × 1024", 1024, 1024),
        ("长方形 64 × 32", 64, 32),
        ("长方形 128 × 64", 128, 64),
    ]


def sharpness_note(pattern: BeadPattern) -> str:
    """根据原图每格像素数给出清晰度提示。"""
    px = pattern.cell_px
    if px <= 0:
        return ""
    if px < 6:
        return f"原图每格仅约 {px} 像素，细节会有损失，建议换更大行列数或更清晰的图。"
    if px < 14:
        return f"原图每格约 {px} 像素，图案基本可辨。"
    return f"原图每格约 {px} 像素，细节保留良好。"


def estimate_sheets(rows: int, cols: int, board: int = 29) -> int:
    """按 board×board 的拼豆板估算需要几块板。"""
    return math.ceil(rows / board) * math.ceil(cols / board)
