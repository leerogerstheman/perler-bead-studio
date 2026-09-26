# -*- coding: utf-8 -*-
"""生成示例图片（无需联网），用来试玩转换效果。

运行：python make_sample.py
生成：
    示例图片.png          卡通猫咪（白底，适合试各种行列数）
    示例_渐变色卡.png      彩色渐变，用来对比「抖动」开关的效果
    示例_爱心透明底.png    透明背景爱心，用来试「去背景 / 透明处不放豆子」
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
W, H = 640, 640


def _background() -> Image.Image:
    """左上浅蓝 → 右下淡黄的柔和渐变背景（低分辨率生成再放大，快且平滑）。"""
    sw, sh = 8, 8
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    for j in range(sh):
        for i in range(sw):
            u = 0.6 * (j / (sh - 1)) + 0.4 * (i / (sw - 1))
            px[i, j] = (int(184 + 50 * u), int(220 + 25 * u), int(248 - 20 * u))
    return small.resize((W, H), Image.BICUBIC)


def make_cat() -> Image.Image:
    img = _background()
    d = ImageDraw.Draw(img)

    # 身体
    d.ellipse((150, 300, 490, 580), fill=(255, 168, 66))
    # 头
    d.ellipse((170, 140, 470, 420), fill=(255, 186, 92))
    # 耳朵
    d.polygon([(185, 190), (215, 70), (300, 165)], fill=(255, 186, 92))
    d.polygon([(455, 190), (425, 70), (340, 165)], fill=(255, 186, 92))
    d.polygon([(212, 178), (232, 112), (285, 170)], fill=(255, 150, 170))
    d.polygon([(428, 178), (408, 112), (355, 170)], fill=(255, 150, 170))
    # 条纹
    d.polygon([(300, 150), (330, 150), (352, 158), (322, 158)], fill=(238, 140, 40))
    d.polygon([(240, 74), (256, 78), (262, 96), (246, 92)], fill=(238, 140, 40))
    d.polygon([(400, 74), (384, 78), (378, 96), (394, 92)], fill=(238, 140, 40))
    # 眼睛
    for cx in (255, 385):
        d.ellipse((cx - 34, 236, cx + 34, 312), fill=(255, 255, 255))
        d.ellipse((cx - 20, 250, cx + 20, 300), fill=(46, 46, 56))
        d.ellipse((cx - 6, 258, cx + 8, 274), fill=(255, 255, 255))
    # 鼻子 + 嘴
    d.polygon([(310, 330), (330, 330), (320, 344)], fill=(240, 110, 130))
    d.arc((288, 330, 352, 378), start=20, end=160, fill=(180, 90, 60), width=4)
    d.arc((268, 322, 320, 372), start=200, end=330, fill=(180, 90, 60), width=4)
    d.arc((320, 322, 372, 372), start=210, end=340, fill=(180, 90, 60), width=4)
    # 胡须
    for dy in (-14, 4, 22):
        d.line((162, 320 + dy, 78, 300 + int(dy * 1.4)), fill=(150, 110, 70), width=3)
        d.line((478, 320 + dy, 562, 300 + int(dy * 1.4)), fill=(150, 110, 70), width=3)
    # 爪子
    for cx in (250, 320, 390):
        d.ellipse((cx - 34, 520, cx + 34, 578), fill=(255, 214, 150))
    return img.filter(ImageFilter.SMOOTH_MORE)


def make_gradient() -> Image.Image:
    """彩色渐变方块，用来检查色彩还原和抖动效果。"""
    img = Image.new("RGB", (W, H))
    px = img.load()
    cols, rows = 8, 6
    for j in range(rows):
        for i in range(cols):
            x0, x1 = i * W // cols, (i + 1) * W // cols
            y0, y1 = j * H // rows, (j + 1) * H // rows
            for y in range(y0, y1):
                for x in range(x0, x1):
                    r = int(255 * (x - x0) / max(1, x1 - x0 - 1))
                    g = int(255 * (y - y0) / max(1, y1 - y0 - 1))
                    b = int(255 * (i + j) / (cols + rows - 2))
                    px[x, y] = (r, g, b)
    return img.filter(ImageFilter.GaussianBlur(1.5))


def make_heart() -> Image.Image:
    """透明背景的爱心：(x²+y²-1)³ - x²y³ ≤ 0 的心形曲线，4 倍超采样抗锯齿。"""
    ss = 4
    big = Image.new("L", (W * ss, H * ss), 0)
    px = big.load()
    for j in range(H * ss):
        ty = 1.35 - 2.7 * (j + 0.5) / (H * ss)
        for i in range(W * ss):
            tx = -1.45 + 2.9 * (i + 0.5) / (W * ss)
            a = tx * tx + ty * ty - 1.0
            if a * a * a - tx * tx * ty * ty * ty <= 0:
                px[i, j] = 255
    mask = big.resize((W, H), Image.LANCZOS)

    # 透明画布 + 渐变红心 + 高光（不去背景也不会出现白底）
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fill = Image.new("RGBA", (W, H))
    fpx = fill.load()
    for j in range(H):
        for i in range(W):
            t = (i / W + j / H) / 2
            fpx[i, j] = (int(198 + 57 * t), int(38 + 40 * t), int(52 + 56 * t), 255)
    body.paste(fill, (0, 0), mask)

    shine = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    sd.ellipse((170, 150, 265, 222), fill=(255, 178, 188, 235))
    sd.ellipse((205, 132, 248, 162), fill=(255, 228, 232, 250))
    body = Image.alpha_composite(body, Image.composite(
        shine, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))
    return body


def main() -> None:
    cat = make_cat()
    cat_path = os.path.join(BASE_DIR, "示例图片.png")
    cat.save(cat_path)
    make_gradient().save(os.path.join(BASE_DIR, "示例_渐变色卡.png"))
    make_heart().save(os.path.join(BASE_DIR, "示例_爱心透明底.png"))
    print("已生成示例图片：")
    for name in ("示例图片.png", "示例_渐变色卡.png", "示例_爱心透明底.png"):
        print("   ", os.path.join(BASE_DIR, name))


if __name__ == "__main__":
    main()
