# -*- coding: utf-8 -*-
"""拼豆色卡（palette）。

内置色卡参考常见 5mm 拼豆（Hama / Perler / Artkal 通用色号）整理，
颜色值为近似屏幕显示值，仅用于图案设计参考。

自定义色卡：在 palettes/ 目录下放一个 JSON 文件即可，格式为
    {"名称": "我的色卡", "colors": [["色名", "#RRGGBB"], ...]}
"""

from __future__ import annotations

import json
import os

# ---------------------------------------------------------------- 内置色卡 --

# 完整色卡（约 50 色）
FULL_PALETTE: list[tuple[str, str]] = [
    ("白色", "#FFFFFF"),
    ("奶白", "#F7F3E9"),
    ("浅灰", "#C9C9C9"),
    ("中灰", "#8D8D8D"),
    ("深灰", "#4D4D4D"),
    ("黑色", "#1A1A1A"),
    ("浅粉", "#FFC7D5"),
    ("粉红", "#F79FC4"),
    ("玫红", "#E8478C"),
    ("深玫红", "#C01763"),
    ("大红", "#E2352B"),
    ("深红", "#A81C1C"),
    ("酒红", "#7A1420"),
    ("珊瑚红", "#FF7A66"),
    ("橙红", "#FF5A18"),
    ("橙色", "#F7941D"),
    ("浅橙", "#FFBE73"),
    ("杏色", "#FBD3A6"),
    ("肤色", "#F6C9A8"),
    ("深肤色", "#C98C63"),
    ("深棕", "#6B4226"),
    ("黄棕", "#8B5A2B"),
    ("米色", "#EFE0C4"),
    ("浅黄", "#FFF3A6"),
    ("柠檬黄", "#FFE83D"),
    ("黄色", "#FFD400"),
    ("金黄", "#F2B705"),
    ("深黄", "#D89B00"),
    ("黄绿", "#C8D93B"),
    ("浅绿", "#A8E06B"),
    ("草绿", "#6FC63C"),
    ("绿色", "#2E9E4F"),
    ("深绿", "#17663A"),
    ("墨绿", "#0E4429"),
    ("薄荷绿", "#9FE3C4"),
    ("青绿", "#2FB6A3"),
    ("青色", "#22C1D6"),
    ("浅蓝", "#87CEEB"),
    ("淡蓝", "#BADEF8"),
    ("天蓝", "#3FA9F5"),
    ("蓝色", "#1B5FC1"),
    ("深蓝", "#123B7A"),
    ("藏蓝", "#0D2447"),
    ("蓝紫", "#6A6AD6"),
    ("浅紫", "#C79BE0"),
    ("紫色", "#7B3FA0"),
    ("深紫", "#4B1E6E"),
    ("淡紫", "#DFC9F2"),
    ("浅咖", "#C49A6C"),
    ("灰蓝", "#6E8CA0"),
    ("银灰", "#B9C2CC"),
]

# 精简色卡（32 色），豆子种类少、成本低，做小图很方便
SIMPLE_PALETTE: list[tuple[str, str]] = [
    ("白色", "#FFFFFF"),
    ("浅灰", "#B8B8B8"),
    ("深灰", "#5A5A5A"),
    ("黑色", "#1A1A1A"),
    ("浅粉", "#FFC7D5"),
    ("粉红", "#F07EB0"),
    ("玫红", "#D0346B"),
    ("大红", "#D62828"),
    ("深红", "#8E1B1B"),
    ("珊瑚红", "#FF7A5A"),
    ("橙色", "#F7941D"),
    ("杏色", "#FBD3A6"),
    ("肤色", "#F3C49B"),
    ("深棕", "#6B4226"),
    ("米色", "#EFE0C4"),
    ("浅黄", "#FFF08C"),
    ("黄色", "#FFD400"),
    ("金黄", "#E0A800"),
    ("黄绿", "#B5D33C"),
    ("浅绿", "#8FD35B"),
    ("草绿", "#4FAE3C"),
    ("绿色", "#2E8B4F"),
    ("深绿", "#17663A"),
    ("薄荷绿", "#A6E3C8"),
    ("青绿", "#2FB6A3"),
    ("浅蓝", "#8FD3F4"),
    ("淡蓝", "#BADEF8"),
    ("天蓝", "#3FA9F5"),
    ("蓝色", "#1B5FC1"),
    ("深蓝", "#123B7A"),
    ("蓝紫", "#6A6AD6"),
    ("紫色", "#7B3FA0"),
    ("浅紫", "#C79BE0"),
]

# 极简色卡（16 色），适合 16x16 这类超小图
MINI_PALETTE: list[tuple[str, str]] = [
    ("白色", "#FFFFFF"),
    ("黑色", "#1A1A1A"),
    ("浅灰", "#B8B8B8"),
    ("深灰", "#5A5A5A"),
    ("大红", "#D62828"),
    ("粉红", "#F07EB0"),
    ("橙色", "#F7941D"),
    ("肤色", "#F3C49B"),
    ("黄色", "#FFD400"),
    ("草绿", "#4FAE3C"),
    ("深绿", "#17663A"),
    ("天蓝", "#3FA9F5"),
    ("蓝色", "#1B5FC1"),
    ("紫色", "#7B3FA0"),
    ("深棕", "#6B4226"),
    ("米色", "#EFE0C4"),
]

BUILTIN: dict[str, list[tuple[str, str]]] = {
    "标准色卡（50 色）": FULL_PALETTE,
    "精简色卡（32 色）": SIMPLE_PALETTE,
    "极简色卡（16 色）": MINI_PALETTE,
}


# ---------------------------------------------------------------- 工具函数 --

def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"颜色格式不正确：{value!r}")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def build_palette(items) -> list[tuple[str, tuple[int, int, int]]]:
    """把 [('名称', '#RRGGBB'), ...] 变成 [(名称, (r, g, b)), ...]。"""
    out: list[tuple[str, tuple[int, int, int]]] = []
    for name, value in items:
        out.append((str(name), _hex_to_rgb(value)))
    if not out:
        raise ValueError("色卡为空")
    return out


def palette_names() -> list[str]:
    """返回可选色卡名（含 palettes/ 目录下的自定义色卡）。"""
    names = list(BUILTIN.keys())
    for name, _ in load_custom_palettes().items():
        if name not in names:
            names.append(name)
    return names


def get_palette(name: str) -> list[tuple[str, tuple[int, int, int]]]:
    """按名称取色卡，找不到时回退到标准色卡。"""
    if name in BUILTIN:
        return build_palette(BUILTIN[name])
    custom = load_custom_palettes()
    if name in custom:
        return build_palette(custom[name])
    return build_palette(FULL_PALETTE)


def palettes_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "palettes")


def load_custom_palettes() -> dict[str, list[tuple[str, str]]]:
    """读取 palettes/*.json 自定义色卡。

    支持两种写法：
        {"名称": "xxx", "colors": [["红", "#FF0000"], ...]}
        {"红": "#FF0000", "绿": "#00FF00"}          # 直接键值对
    """
    result: dict[str, list[tuple[str, str]]] = {}
    folder = palettes_dir()
    if not os.path.isdir(folder):
        return result
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(".json"):
            continue
        path = os.path.join(folder, filename)
        try:
            # utf-8-sig：兼容记事本 / PowerShell 写出的带 BOM 的 JSON
            with open(path, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except Exception:
            continue
        stem = os.path.splitext(filename)[0]
        if isinstance(data, dict) and "colors" in data:
            name = str(data.get("名称") or data.get("name") or stem)
            items = data["colors"]
        elif isinstance(data, dict):
            name = stem
            items = list(data.items())
        elif isinstance(data, list):
            name = stem
            items = data
        else:
            continue
        colors: list[tuple[str, str]] = []
        for entry in items:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                colors.append((str(entry[0]), str(entry[1])))
        if colors:
            result[name] = colors
    return result
