# -*- coding: utf-8 -*-
"""生成程序图标：拼豆（带中孔的珠子）+ 包豪斯（三原色 / 几何构成 / 网格）。

设计说明
--------
· 主体是 4 颗放大到极致的拼豆，2×2 排布、轻微重叠 —— 既是「珠子」也是「构成」。
· 每颗珠子中间留孔，这是拼豆最核心的识别特征（也对应包豪斯的圆）。
· 配色只用包豪斯三原色 + 白：红 #D62828、黄 #F2B705、蓝 #1B5FC1、白。
· 背景是深黑底 + 极淡的拼豆板网格（pegboard），暗示「拼」这个动作。
· 全部是正圆、直线、直角，没有渐变、圆角阴影。

输出：app.ico（16~256 多尺寸）、app.png（256）、_预览/图标设计.png（放大展示）

运行：python make_icon.py
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 包豪斯色板
RED = (214, 40, 40)
YELLOW = (242, 183, 5)
BLUE = (27, 95, 193)
WHITE = (255, 255, 255)
BLACK = (20, 22, 26)
GRID = (44, 47, 54)

S = 1024                      # 主图边长
SS = 4                        # 超采样倍数（先画大图再缩小，边缘更干净）

# 四颗珠子的位置（相对坐标 0~1）与颜色：分两行、彼此相切不相压
BEADS = [
    (0.315, 0.315, RED),
    (0.685, 0.315, YELLOW),
    (0.315, 0.685, BLUE),
    (0.685, 0.685, WHITE),
]
BEAD_R = 0.185                # 珠子半径（相对边长）
HOLE_R = 0.062                # 中孔半径
RING = 1.46                   # 孔外那一圈「豆壁」的相对半径


def _draw_beads(d, n: int, with_bg: bool) -> None:
    """画四颗拼豆：正圆本体 + 中孔 + 孔外一圈豆壁高光。"""
    r = BEAD_R * n
    hr = HOLE_R * n
    for fx, fy, color in BEADS:
        cx, cy = fx * n, fy * n
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
        # 孔外一圈更亮的「豆壁」：让孔看起来是穿过去的，而不是画上去的黑点
        lighter = tuple(min(255, int(c + (255 - c) * 0.34)) for c in color)
        d.ellipse((cx - hr * RING, cy - hr * RING, cx + hr * RING, cy + hr * RING),
                  outline=lighter, width=max(1, int(n * 0.009)))
        # 中孔
        if with_bg:
            d.ellipse((cx - hr, cy - hr, cx + hr, cy + hr), fill=BLACK)
        else:
            d.ellipse((cx - hr, cy - hr, cx + hr, cy + hr), fill=(0, 0, 0, 0))


def build_master(size: int = S) -> Image.Image:
    """画一张主图（含背景网格、珠子、中孔）。"""
    n = size * SS
    img = Image.new("RGB", (n, n), BLACK)
    d = ImageDraw.Draw(img)

    # --- 拼豆板网格：每 1/8 一格，淡淡的方块点 ---
    step = n / 8
    dot = step * 0.085
    for i in range(1, 8):
        for j in range(1, 8):
            cx, cy = i * step, j * step
            d.rectangle((cx - dot, cy - dot, cx + dot, cy + dot), fill=GRID)

    _draw_beads(d, n, with_bg=True)

    # --- 左上角一条黄色短横：包豪斯的直线元素，也呼应拼豆板的一"格" ---
    d.rectangle((n * 0.045, n * 0.045, n * 0.045 + n * 0.155, n * 0.045 + n * 0.038),
                fill=YELLOW)

    img = img.resize((size, size), Image.LANCZOS)
    return img


def build_transparent(size: int) -> Image.Image:
    """透明背景版本（给标题栏/网页用）：去掉黑底与网格，只留珠子与色块。"""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = BEAD_R * n
    hr = HOLE_R * n
    for fx, fy, color in BEADS:
        cx, cy = fx * n, fy * n
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (255,))
        lighter = tuple(min(255, int(c + (255 - c) * 0.34)) for c in color)
        d.ellipse((cx - hr * RING, cy - hr * RING, cx + hr * RING, cy + hr * RING),
                  outline=lighter + (255,), width=max(1, int(n * 0.009)))
        d.ellipse((cx - hr, cy - hr, cx + hr, cy + hr), fill=(0, 0, 0, 0))
    d.rectangle((n * 0.045, n * 0.045, n * 0.045 + n * 0.155, n * 0.045 + n * 0.038),
                fill=YELLOW + (255,))
    return img.resize((size, size), Image.LANCZOS)


def main() -> int:
    out_dir = os.path.join(BASE_DIR, "_预览")
    os.makedirs(out_dir, exist_ok=True)

    master = build_master(S)
    master.save(os.path.join(out_dir, "图标设计.png"))

    # 透明版大图（放在标题条上用）
    build_transparent(256).save(os.path.join(BASE_DIR, "app_icon.png"))

    # Windows 图标：多尺寸打包
    ico_path = os.path.join(BASE_DIR, "app.ico")
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    master.save(ico_path, format="ICO",
                sizes=[(s, s) for s in sizes])

    # 顺带导出几张常见尺寸，方便别处引用
    for s in (16, 32, 48, 64, 128, 256):
        master.resize((s, s), Image.LANCZOS).save(
            os.path.join(out_dir, f"图标_{s}.png"))

    print("已生成：")
    print("  程序图标(ico)：", ico_path, os.path.getsize(ico_path), "字节")
    print("  标题栏图标(png)：", os.path.join(BASE_DIR, "app_icon.png"))
    print("  设计稿：", os.path.join(out_dir, "图标设计.png"))
    print(f"  ico 内含尺寸：{sizes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
