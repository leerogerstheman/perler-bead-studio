# -*- coding: utf-8 -*-
"""图案渲染与导出：拼豆图纸（PNG）、矢量图（SVG）、豆子清单（CSV / TXT / HTML）。"""

from __future__ import annotations

import html
import os
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont
from PIL import PngImagePlugin

import notice_core
from core import BeadPattern

# 配色
BG_COLOR = (250, 250, 252)
EMPTY_COLOR = (240, 242, 246)
EMPTY_DOT = (253, 253, 255)
GRID_MINOR = (203, 207, 214)
GRID_MAJOR = (120, 126, 136)
RULER_BG = (243, 244, 247)
TEXT_COLOR = (70, 74, 82)

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
)


def _load_font(size: int) -> ImageFont.ImageFont:
    """尽量用系统中文字体渲染标题，找不到就退回内置位图字体（只影响标题）。"""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:      # noqa: BLE001
                continue
    try:
        return ImageFont.load_default(size)
    except Exception:              # noqa: BLE001
        return ImageFont.load_default()


def _watermark_text() -> str:
    return notice_core.watermark_text()


def _stamp_watermark(img: Image.Image, lines: list[str] | None = None) -> Image.Image:
    """在图片底部加一条免费声明水印（导出文件都要带，这是最难删掉的一层）。"""
    if not lines:
        lines = notice_core.export_notice_lines()
    bar_h = 22 * len(lines) + 10
    out = Image.new("RGB", (img.width, img.height + bar_h), (255, 255, 255))
    out.paste(img, (0, 0))
    draw = ImageDraw.Draw(out)
    # 左上角一个红色方块，沿用包豪斯的三原色标记
    draw.rectangle((0, img.height, out.width, img.height + bar_h - 1), fill=(255, 255, 255))
    draw.rectangle((0, img.height, out.width, img.height + 3), fill=(214, 40, 40))
    draw.rectangle((10, img.height + 9, 22, img.height + 21), fill=(214, 40, 40))
    font = _load_font(13)
    for i, line in enumerate(lines):
        draw.text((30, img.height + 9 + i * 22), line, fill=(60, 62, 68), font=font)
    return out


def _png_metadata(title: str) -> PngImagePlugin.PngInfo:
    """PNG 元数据里也写上来来源与许可。

    注意：PNG 的 tEXt 块按 Latin-1 编码，中文会乱码，所以这里只用 ASCII；
    中文声明由图片上的水印和底部声明条承担。
    """
    meta = PngImagePlugin.PngInfo()
    c = notice_core.content()
    source = c.get("source", notice_core.SOURCE_URL)
    meta.add_text("Software", "Perler Bead Studio (open source)")
    meta.add_text("Source", f"https://{source}")
    meta.add_text("License", "Free and open source. Do not pay for this tool.")
    meta.add_text("Warning", "If you paid for this software, ask for a refund.")
    meta.add_text("Title", title.replace("\n", " "))
    return meta


def _render_by_palette(pattern: BeadPattern, cell: int, empty_color) -> Image.Image:
    """大图快路径：先把每格下标画成 1 像素/格的索引图，再用最近邻放大。

    比逐格画圆/方块快很多，专门服务 512×512、1024×1024 这种超大图案。
    """
    rows, cols = pattern.rows, pattern.cols
    palette_img = Image.new("P", (cols, rows), 0)
    flat: list[int] = []
    for r, g, b in pattern.rgb:
        flat += [r, g, b]
    flat += [0, 0, 0] * (256 - len(pattern.rgb))
    palette_img.putpalette(flat)

    data = bytearray(cols * rows)
    for y in range(rows):
        row = pattern.index[y]
        base = y * cols
        for x in range(cols):
            idx = row[x]
            data[base + x] = idx if 0 <= idx < 256 else 0
    palette_img.frombytes(bytes(data))
    big = palette_img.resize((cols * cell, rows * cell), Image.NEAREST).convert("RGB")

    # 空格用统一的浅灰表示（色卡里没有的"空"状态）
    if any(v < 0 for row in pattern.index for v in row):
        mask = Image.new("L", (cols, rows), 0)
        mdata = bytearray(cols * rows)
        for y in range(rows):
            row = pattern.index[y]
            base = y * cols
            for x in range(cols):
                if row[x] < 0:
                    mdata[base + x] = 255
        mask.frombytes(bytes(mdata))
        mask = mask.resize((cols * cell, rows * cell), Image.NEAREST)
        big.paste(Image.new("RGB", big.size, tuple(empty_color)), (0, 0), mask)
    return big


def _draw_bead(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float,
               color, outline=None, width: int = 1) -> None:
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 fill=color, outline=outline, width=width)


def render_chart(pattern: BeadPattern,
                 cell: int = 32,
                 ruler: bool = True,
                 grid_lines: bool = True,
                 show_coords: bool = True,
                 mode: str = "bead",
                 title: Optional[str] = None,
                 watermark: bool = False) -> Image.Image:
    """渲染拼豆图纸，返回 PIL 图片。

    cell        每格边长（像素）
    ruler       是否留出坐标刻度边距
    grid_lines  是否画网格线
    show_coords 是否标注行列号
    mode        bead=画成圆豆子 / flat=纯色方块（更接近成品远看效果）
    watermark   是否在右下角压一行「开源免费」水印（导出时打开，界面预览关闭）
    """
    rows, cols = pattern.rows, pattern.cols
    cell = max(2, int(cell))
    pad = 0
    if ruler:
        pad = max(int(cell * 1.15), 22)

    width = cols * cell + pad * 2
    height = rows * cell + pad * 2
    title_h = 0
    if title:
        title_h = max(int(cell * 1.4), 34)
        height += title_h

    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    ox, oy = pad, pad + title_h

    # 刻度背景
    if ruler:
        draw.rectangle((0, 0, width, oy - 1), fill=RULER_BG)
        draw.rectangle((0, 0, ox - 1, height), fill=RULER_BG)

    # 背景（空格）
    draw.rectangle((ox, oy, ox + cols * cell - 1, oy + rows * cell - 1), fill=EMPTY_COLOR)

    index = pattern.index
    rgb = pattern.rgb
    radius = cell * 0.44
    ring = max(1, round(cell / 16))

    # 大图走「索引图 + 最近邻放大」的快路径：1024×1024 从 0.7 秒降到 0.1 秒出头
    fast = mode == "flat" or cell <= 4 or cols * rows > 200000
    if fast:
        palette_img = _render_by_palette(pattern, cell, EMPTY_COLOR)
        img.paste(palette_img, (ox, oy))
    else:
        for y in range(rows):
            row = index[y]
            for x in range(cols):
                idx = row[x]
                left = ox + x * cell
                top = oy + y * cell
                if idx < 0:
                    # 空格：格子够大时点一个淡淡的点，表示这里不放豆子
                    if cell >= 22:
                        dot = max(1.0, cell * 0.055)
                        cx = left + cell / 2
                        cy = top + cell / 2
                        draw.ellipse((cx - dot, cy - dot, cx + dot, cy + dot),
                                     fill=EMPTY_DOT)
                    continue
                color = rgb[idx]
                # 豆子中心留一个小孔，更像真实拼豆
                _draw_bead(draw, left + cell / 2, top + cell / 2, radius, color)
                if cell >= 14:
                    hole = max(1.0, radius * 0.22)
                    cx = left + cell / 2
                    cy = top + cell / 2
                    draw.ellipse((cx - hole, cy - hole, cx + hole, cy + hole),
                                 fill=tuple(int(c * 0.82) for c in color))

    # 网格线
    if grid_lines and cell >= 5:
        step = 1
        for x in range(cols + 1):
            px = ox + x * cell
            major = (x % 5 == 0) or x in (0, cols)
            if major or cell >= 12:
                draw.line((px, oy, px, oy + rows * cell),
                          fill=GRID_MAJOR if major else GRID_MINOR, width=1)
        for y in range(rows + 1):
            py = oy + y * cell
            major = (y % 5 == 0) or y in (0, rows)
            if major or cell >= 12:
                draw.line((ox, py, ox + cols * cell, py),
                          fill=GRID_MAJOR if major else GRID_MINOR, width=1)

    # 外框
    draw.rectangle((ox, oy, ox + cols * cell, oy + rows * cell),
                   outline=(70, 74, 82), width=max(1, cell // 16))

    # 行列坐标：始终标在 5 的倍数处，和 5 格一条的粗网格线对齐
    if ruler and show_coords and cell >= 6:
        label_step = 5 if cell >= 22 else (10 if cell >= 12 else 20)
        for x in range(cols):
            if (x + 1) % label_step and (x + 1) != cols:
                continue
            label = str(x + 1)
            tw = draw.textlength(label)
            draw.text((ox + x * cell + cell / 2 - tw / 2, oy - pad * 0.78),
                      label, fill=TEXT_COLOR)
        for y in range(rows):
            if (y + 1) % label_step and (y + 1) != rows:
                continue
            label = str(y + 1)
            tw = draw.textlength(label)
            draw.text((ox - tw - max(4, pad * 0.18), oy + y * cell + cell / 2 - 6),
                      label, fill=TEXT_COLOR)

    if title:
        font = _load_font(max(12, int(cell * 0.62)))
        bbox = draw.textbbox((0, 0), title, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((width - tw) / 2 - bbox[0], max(3, title_h * 0.16) - bbox[1]),
                  title, fill=(40, 44, 52), font=font)

    # 图纸右下角压一行浅色水印：软件免费、请勿付费购买
    if watermark and cell >= 8:
        wm_font = _load_font(max(11, int(cell * 0.5)))
        wm = _watermark_text()
        bbox = draw.textbbox((0, 0), wm, font=wm_font)
        draw.text((width - (bbox[2] - bbox[0]) - 12, height - (bbox[3] - bbox[1]) - 10),
                  wm, fill=(150, 154, 162), font=wm_font)
    return img


def render_flat(pattern: BeadPattern, zoom: int = 1) -> Image.Image:
    """把图案还原成一张普通像素图（1 格 = 1 像素，再整倍放大）。"""
    zoom = max(1, int(zoom))
    img = Image.new("RGB", (pattern.cols, pattern.rows), EMPTY_COLOR)
    px = img.load()
    for y in range(pattern.rows):
        row = pattern.index[y]
        for x in range(pattern.cols):
            idx = row[x]
            if idx >= 0:
                px[x, y] = pattern.rgb[idx]
    if zoom > 1:
        img = img.resize((pattern.cols * zoom, pattern.rows * zoom), Image.NEAREST)
    return img


# ------------------------------------------------------------------ 导出 --

def export_png(pattern: BeadPattern, path: str, cell: int = 32,
               title: Optional[str] = None, mode: str = "bead") -> str:
    """导出图纸 PNG：带右下角水印、底部声明条、PNG 元数据来源。"""
    img = render_chart(pattern, cell=cell, title=title, mode=mode, watermark=True)
    img = _stamp_watermark(img)
    img.save(path, "PNG", pnginfo=_png_metadata(title or "拼豆图纸"))
    return path


def export_flat_png(pattern: BeadPattern, path: str, zoom: int = 16) -> str:
    """导出「成品效果图」：没有网格线的纯色像素画（同样带声明）。"""
    img = _stamp_watermark(render_flat(pattern, zoom=zoom))
    img.save(path, "PNG", pnginfo=_png_metadata("拼豆成品效果图"))
    return path


_SVG_FONT = "Microsoft YaHei, PingFang SC, sans-serif"


def export_svg(pattern: BeadPattern, path: str, cell: int = 32,
               title: Optional[str] = None, mode: str = "bead") -> str:
    """导出矢量图纸，放大打印不模糊。"""
    rows, cols = pattern.rows, pattern.cols
    pad = max(24, int(cell * 1.15))
    width = cols * cell + pad * 2
    height = rows * cell + pad * 2
    r = cell * 0.44
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                 f'height="{height}" viewBox="0 0 {width} {height}">')
    if title:
        parts.append(f'<title>{html.escape(title)}</title>')
    parts.append(f'<rect width="{width}" height="{height}" fill="rgb(250,250,252)"/>')
    parts.append(f'<rect x="{pad}" y="{pad}" width="{cols * cell}" height="{rows * cell}" '
                 f'fill="rgb(238,240,245)"/>')

    for y in range(rows):
        for x in range(cols):
            idx = pattern.index[y][x]
            if idx < 0:
                continue
            r_, g_, b_ = pattern.rgb[idx]
            cx = pad + x * cell + cell / 2
            cy = pad + y * cell + cell / 2
            fill = f"rgb({r_},{g_},{b_})"
            if mode == "flat":
                parts.append(f'<rect x="{pad + x * cell}" y="{pad + y * cell}" '
                             f'width="{cell}" height="{cell}" fill="{fill}"/>')
            else:
                parts.append(f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{fill}"/>')

    for x in range(cols + 1):
        major = x % 5 == 0 or x in (0, cols)
        stroke = "rgb(120,126,136)" if major else "rgb(205,208,214)"
        w = 1.4 if major else 0.7
        px = pad + x * cell
        parts.append(f'<line x1="{px}" y1="{pad}" x2="{px}" y2="{pad + rows * cell}" '
                     f'stroke="{stroke}" stroke-width="{w}"/>')
    for y in range(rows + 1):
        major = y % 5 == 0 or y in (0, rows)
        stroke = "rgb(120,126,136)" if major else "rgb(205,208,214)"
        w = 1.4 if major else 0.7
        py = pad + y * cell
        parts.append(f'<line x1="{pad}" y1="{py}" x2="{pad + cols * cell}" y2="{py}" '
                     f'stroke="{stroke}" stroke-width="{w}"/>')

    label_step = 5 if cell >= 22 else (10 if cell >= 12 else 20)
    fs = max(8, int(cell * 0.42))
    for x in range(cols):
        if (x + 1) % label_step and (x + 1) != cols:
            continue
        parts.append(f'<text x="{pad + x * cell + cell / 2:g}" y="{pad - 6}" '
                     f'font-family="{_SVG_FONT}" font-size="{fs}" fill="rgb(70,74,82)" '
                     f'text-anchor="middle">{x + 1}</text>')
    for y in range(rows):
        if (y + 1) % label_step and (y + 1) != rows:
            continue
        parts.append(f'<text x="{pad - 6}" y="{pad + y * cell + cell / 2 + fs / 3:g}" '
                     f'font-family="{_SVG_FONT}" font-size="{fs}" fill="rgb(70,74,82)" '
                     f'text-anchor="end">{y + 1}</text>')

    # SVG 里也带上来源声明（矢量图常用在印刷场景）
    c = notice_core.content()
    parts.append(f'<text x="{pad}" y="{height - 8}" font-family="{_SVG_FONT}" '
                 f'font-size="12" fill="rgb(150,154,162)">'
                 f'{html.escape(notice_core.watermark_text())}</text>')
    parts.append(f'<desc>{html.escape(c.get("header", ""))} · '
                 f'{html.escape(c.get("source", notice_core.SOURCE_URL))}</desc>')
    parts.append('</svg>')
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    return path


def export_counts_csv(pattern: BeadPattern, path: str) -> str:
    """导出豆子清单：色号、名称、HEX、颗数（含免费声明页脚）。"""
    import csv
    lines = [["序号", "颜色名称", "HEX", "RGB", "颗数"]]
    for order, (idx, count) in enumerate(pattern.counts(), start=1):
        name = pattern.names[idx]
        r, g, b = pattern.rgb[idx]
        lines.append([str(order), name, f"#{r:02X}{g:02X}{b:02X}",
                      f"{r},{g},{b}", str(count)])
    lines.append(["", "合计", "", "", str(pattern.total)])
    lines.append([])
    for text in notice_core.export_notice_lines():
        lines.append([text])
    # utf-8-sig 让 Excel 直接正常显示中文
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh).writerows(lines)
    return path


def export_grid_csv(pattern: BeadPattern, path: str) -> str:
    """导出每格颜色编号表（0 表示空），方便校对和二次加工；末尾附免费声明。"""
    import csv
    order = {idx: n for n, (idx, _c) in enumerate(pattern.counts(), start=1)}
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        for y in range(pattern.rows):
            writer.writerow([order.get(v, 0) for v in pattern.index[y]])
        writer.writerow([])
        for text in notice_core.export_notice_lines():
            writer.writerow([text])
    return path


def export_checklist_txt(pattern: BeadPattern, path: str,
                         title: str = "") -> str:
    """导出可打印的挑豆清单（带方块勾选）。"""
    counts = pattern.counts()
    lines: list[str] = []
    if title:
        lines.append(title)
    lines.append(f"尺寸：{pattern.cols} 列 × {pattern.rows} 行    共 {pattern.total} 颗    "
                 f"{len(counts)} 种颜色    色卡：{pattern.palette_name}")
    lines.append("=" * 58)
    lines.append(f"{'序号':<5}{'颜色':<8}{'色值':<12}{'颗数':<8}勾选")
    lines.append("-" * 58)
    name_width = max([len(pattern.names[i]) for i, _c in counts] + [2])
    for order, (idx, count) in enumerate(counts, start=1):
        r, g, b = pattern.rgb[idx]
        name = pattern.names[idx]
        # 中文按两个字符宽度对齐（等宽字体下用全角空格补齐）
        pad = "　" * (name_width - len(name))
        lines.append(f"{order:<5}{name}{pad}  {f'#{r:02X}{g:02X}{b:02X}':<12}"
                     f"{count:<8}□")
    lines.append("-" * 58)
    lines.append(f"合计：{pattern.total} 颗")
    lines.append("")
    lines.append("=" * 58)
    for text in notice_core.export_notice_lines():
        lines.append(text)
    lines.append("=" * 58)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


def export_html(pattern: BeadPattern, path: str, cell: int = 26,
                title: str = "拼豆图纸") -> str:
    """导出可在浏览器打开 / 打印的图纸（含图例与豆子清单）。"""
    rows, cols = pattern.rows, pattern.cols
    counts = pattern.counts()
    order = {idx: n for n, (idx, _c) in enumerate(counts, start=1)}

    cells: list[str] = []
    for y in range(rows):
        for x in range(cols):
            idx = pattern.index[y][x]
            if idx < 0:
                cells.append('<i class="e"></i>')
            else:
                r, g, b = pattern.rgb[idx]
                cells.append(f'<i style="--c:rgb({r},{g},{b})" title="{x + 1},{y + 1} '
                             f'{html.escape(pattern.names[idx])} · 编号{order[idx]}"></i>')
    grid_html = "\n".join(cells)

    legend_rows = []
    for n, (idx, count) in enumerate(counts, start=1):
        r, g, b = pattern.rgb[idx]
        legend_rows.append(
            f'<tr><td>{n}</td>'
            f'<td><span class="sw" style="background:rgb({r},{g},{b})"></span></td>'
            f'<td>{html.escape(pattern.names[idx])}</td>'
            f'<td>#{r:02X}{g:02X}{b:02X}</td><td class="num">{count}</td></tr>')
    legend_html = "\n".join(legend_rows)

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} · {cols}×{rows}</title>
<style>
  :root {{ --cell: {cell}px; --line: rgba(90,96,110,.28); --major: rgba(60,66,80,.55); }}
  body {{ margin:0; padding:24px 28px 60px; background:#fafafc; color:#2c3038;
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 6px; }}
  .meta {{ color:#666e7d; font-size:13px; margin-bottom:18px; }}
  .board {{ display:inline-grid; grid-template-columns:repeat({cols},var(--cell)); }}
  .board i {{ width:var(--cell); height:var(--cell); display:block; background:var(--c);
              border-radius:50%; box-sizing:border-box; }}
  .board i.e {{ background:transparent; border-radius:0; }}
  .board i:nth-child(5n+1) {{ box-shadow:-1px 0 0 var(--major); }}
  .grid-wrap {{ display:inline-block; padding:2px; border:1px solid var(--major);
                background:#fff; }}
  table {{ border-collapse:collapse; margin-top:22px; font-size:13px; }}
  th,td {{ border:1px solid #dcdfe6; padding:4px 10px; }}
  th {{ background:#f1f3f7; }}
  td.num {{ text-align:right; }}
  .sw {{ display:inline-block; width:16px; height:16px; border-radius:50%;
         border:1px solid rgba(0,0,0,.15); vertical-align:-3px; }}
  .notice {{ margin-top:26px; border:2px solid #14161A; background:#fff; max-width:760px; }}
  .notice .bar {{ display:flex; align-items:center; gap:10px; background:#14161A;
                  color:#fff; padding:8px 12px; font-weight:700; }}
  .notice .bar i {{ width:14px; height:14px; background:#D62828; display:inline-block; }}
  .notice .bar b {{ width:14px; height:14px; background:#F2B705; border-radius:50%;
                    display:inline-block; }}
  .notice .bar em {{ width:22px; height:10px; background:#1B5FC1; display:inline-block; }}
  .notice p {{ margin:10px 12px; font-size:13px; }}
  .notice .big {{ color:#D62828; font-weight:700; font-size:15px; }}
  @media print {{ body {{ background:#fff; }} .board i {{ box-shadow:none; }} }}
</style>
</head>
<body>
<h1>{html.escape(title)} · {cols} 列 × {rows} 行</h1>
<div class="meta">共 {pattern.total} 颗豆子 · {len(counts)} 种颜色 · 色卡：{html.escape(pattern.palette_name)}</div>
<div class="grid-wrap"><div class="board">
{grid_html}
</div></div>
<table>
<thead><tr><th>编号</th><th>颜色</th><th>名称</th><th>色值</th><th>颗数</th></tr></thead>
<tbody>
{legend_html}
</tbody>
</table>
<div class="notice">
  <div class="bar"><i></i><b></b><em></em>{html.escape(notice_core.content().get('header', ''))}</div>
  <p class="big">{html.escape(notice_core.content().get('headline', ''))}</p>
  <p>{html.escape(notice_core.content().get('subhead', ''))}</p>
  <p>项目地址：{html.escape(notice_core.content().get('source', notice_core.SOURCE_URL))}</p>
</div>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path


def export_cell_size(cols: int, rows: int) -> int:
    """按图案大小挑一个合适的每格像素数，保证导出图纸边长落在合理范围。"""
    biggest = max(cols, rows)
    if biggest <= 96:
        return 32
    if biggest <= 256:
        return 20
    if biggest <= 512:
        return 10
    return 5


def export_all(pattern: BeadPattern, folder: str, base_name: str,
               cell: Optional[int] = None, title: str = "") -> list[str]:
    """一次性导出全部文件，返回生成的文件路径列表。"""
    os.makedirs(folder, exist_ok=True)
    if cell is None:
        cell = export_cell_size(pattern.cols, pattern.rows)
    written: list[str] = []
    written.append(export_png(pattern, os.path.join(folder, f"{base_name}_图纸.png"),
                              cell=cell, title=title or None))
    written.append(export_flat_png(pattern, os.path.join(folder, f"{base_name}_效果图.png")))
    if pattern.cols * pattern.rows <= 40000:
        written.append(export_svg(pattern, os.path.join(folder, f"{base_name}_矢量图纸.svg"),
                                   cell=cell, title=title or None))
    else:
        print(f"图案太大（{pattern.cols}×{pattern.rows}），跳过矢量 SVG 导出")
    written.append(export_checklist_txt(pattern, os.path.join(folder, f"{base_name}_豆子清单.txt"),
                                        title=title))
    written.append(export_counts_csv(pattern, os.path.join(folder, f"{base_name}_豆子清单.csv")))
    written.append(export_grid_csv(pattern, os.path.join(folder, f"{base_name}_格子编号.csv")))
    if pattern.cols * pattern.rows <= 400000:
        written.append(export_html(pattern, os.path.join(folder, f"{base_name}_网页图纸.html"),
                                   title=title or "拼豆图纸"))
    else:
        print(f"图案太大（{pattern.cols}×{pattern.rows}），跳过网页 HTML 导出"
              f"（{pattern.cols * pattern.rows} 个格子会让浏览器卡住）")
    return written
