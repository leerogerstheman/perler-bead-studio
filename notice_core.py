# -*- coding: utf-8 -*-
"""启动声明的内容与完整性校验（防篡改）。

设计说明（重要）
----------------
1. 声明文案不以明文存在源码里，而是压缩 + 异或 + base64 存放，避免被人一眼看到、
   顺手删掉（只是提高门槛，不是加密）。
2. 文案自带 HMAC-SHA256 签名。任何对文案的修改都会导致校验失败。
3. 校验失败的后果不是崩溃，而是：强制每次启动都显示声明 + 界面顶部常驻红色警告条
   + 导出文件里仍然带免费声明。也就是说，删声明没有收益。
4. 真正难删掉的一层不在这里，而在导出文件的水印：倒卖的人能删代码，
   删不掉已经发给买家的图纸上的声明。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import zlib

# 混淆用的种子（仅用于避免明文，可公开）
_SEED = b"pb-studio/2026/open-source-notice"

# HMAC 密钥（客户端软件的密钥必然可被提取，这里的作用是防「顺手改」而非防破解）
_SECRET = bytes([
    0x9C, 0x3F, 0xA1, 0x57, 0xE2, 0x08, 0xB4, 0x6D,
    0x15, 0xC8, 0x7A, 0x33, 0xF0, 0x9E, 0x42, 0xD7,
    0x66, 0x1B, 0x8C, 0xE5, 0x29, 0xB3, 0x54, 0xFA,
    0x0D, 0x71, 0xCE, 0x88, 0x36, 0xAF, 0x92, 0x4C,
])

# 逐字段混淆后的声明内容（顺序：title, header, org, source, headline, subhead,
# detail, check_text, footer, watermark）
_BLOB = (
    "CLi44Lkbvil7qsVOOGgPomPVh4suOZ/EMWDpY0dQPaXNLXh3+39AUuB8s7IqGqaX689RPy1o7K"
    "Elqrm0n0XbuYjpWhe2rhxBg7WAM22bKwMEqLMm7XJlzkLRLThnpeZpMOq2huoqIJaqJ7LikviY"
    "nT3mdykxD4gioA8uHkIm7bWDCf13r0XsessuVrL6XfheruB5k9ZnwxiehbnMw98oCQGYpl+TNj"
    "SfwWYO7WoNQOfyfBAIigNgSwi0GEYY2fVR/6WZBgQAKavAuT4rKaKUprHdvXmNwlTv2N8xe2QU"
    "UGJf8rhy3Yd3r6PEt2uFnnUWx4o/wTe7iHisyV4FMnaRVbEZVDU/kCFXYiXM6y92q82hexaygL"
    "cJTQHxgARnnsmCKOVkr9ylNj8ngHF7VSx4eORij3jqo+NrSYtZOR3UfoeT87waCj6XKJPFZSud"
    "smK8xmcVqkrnPWzGsnFf7/STNWxLq48RuqGNjzNdoScKX2p+7K46JBx7xnEUrQK11WNcQ8dq4b"
    "Ih4VKADyLmxf7Fw5qGBvyFiD0qIMPRYkcNta0ZOMF7iEPFXRmKfMqmIu2gn4R9VYJ3Ht4ea11t"
    "9G1Nsaf5DmOyhf/02RdiLGiV1x+vOW1TLzEz/cQHSASsHuPouU1qR3DPcPvYf+sYT7c7+pUPVu"
    "uJdjztxhI7oOT5cnxnAio6TNhLd6rFusvXRzs22Nh1WNpHWfQ+/Dgbde4r7TjM2rGpFNq4/LAV"
    "u3REli7Zet3H+mnz7ijyGtlLigBDt3TWSVC7iiGOYv1Sq5PFkUHdMd7GNds/SnPrYat/T27xXF"
    "sXrPLxABNQy5EE742J7dFyjx0o0YH6/sMCa43MXHq53JiTN4aMeP8ePt8="
)
_SIGNATURE = "33fb2951ab5920e0188d6e3654c84da561a18255c8cc2b1c3fe9ba64fec93c90"

FIELDS = ("title", "header", "org", "source", "headline", "subhead",
          "detail", "check_text", "footer", "watermark")


def _xor(data: bytes) -> bytes:
    seed = _SEED
    n = len(seed)
    return bytes(b ^ seed[i % n] for i, b in enumerate(data))


def _unpack(blob: str) -> str:
    raw = base64.b64decode(blob.encode("ascii"))
    return zlib.decompress(_xor(raw)).decode("utf-8")


def _canonical(parts: dict) -> bytes:
    """按固定顺序拼接用于签名的规范文本（字段内的换行转义，保证一行一字段）。"""
    lines = []
    for name in FIELDS:
        value = str(parts.get(name, "")).replace("\\", "\\\\").replace("\n", "\\n")
        lines.append(f"{name}={value}")
    return "\n".join(lines).encode("utf-8")


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\\\", "\\")


def sign(parts: dict) -> str:
    """计算签名（生成内容时使用，正式包里只比对）。"""
    return hmac.new(_SECRET, _canonical(parts), hashlib.sha256).hexdigest()


def _load() -> dict:
    parts: dict[str, str] = {}
    try:
        for line in _unpack(_BLOB).split("\n"):
            if "=" in line:
                key, _, value = line.partition("=")
                parts[key.strip()] = _unescape(value)
    except Exception:      # noqa: BLE001
        return {}
    return parts


def verify() -> tuple[bool, str]:
    """校验声明内容是否被改动。返回 (是否完好, 说明)。"""
    parts = _load()
    if not parts:
        return False, "声明内容缺失或无法解析"
    missing = [f for f in FIELDS if f not in parts]
    if missing:
        return False, f"声明内容缺少字段：{','.join(missing)}"
    if not hmac.compare_digest(sign(parts), _SIGNATURE):
        return False, "声明内容与签名不一致（已被修改）"
    return True, "ok"


#: 声明模块本身出问题时的兜底文案，保证任何情况下都能把「免费」说清楚
_FALLBACK = {
    "title": "重要声明",
    "header": "本软件在 GitHub 上开源，不收取任何费用",
    "org": "拼豆图案生成器 · Perler Bead Studio",
    "source": "github.com/perler-bead-studio",
    "headline": "若您付费以获取此工具，请立即退款",
    "subhead": "本程序是开源免费软件，任何人都不应以任何形式向您收费",
    "detail": ("本程序是开源免费软件，任何人都可以自由下载、使用与分享。"
               "开发者不会通过任何渠道收费；如果您是付费得到的，请尽快申请退款。"),
    "check_text": "我已了解，不再显示此窗口",
    "footer": "继续使用即表示您已阅读并理解上述内容",
    "watermark": "开源免费 · 请勿付费购买",
}


def content() -> dict:
    """取声明内容（同时给出是否被篡改）；任何异常都退回兜底文案。"""
    try:
        parts = _load()
        ok, reason = verify()
    except Exception as exc:      # noqa: BLE001
        parts, ok, reason = {}, False, f"声明模块异常：{exc}"
    if not parts:
        parts = dict(_FALLBACK)
    for name in FIELDS:
        if not parts.get(name):
            parts[name] = _FALLBACK.get(name, "")
    parts["_intact"] = ok
    parts["_reason"] = reason
    return parts


# ------------------------------------------------------------------ 对外 --

#: 官方来源：写进导出文件，让买家能追溯到原作者
SOURCE_URL = "github.com/perler-bead-studio"

#: 写进每个导出文件的水印（简短版，避免影响图纸可读性）
def watermark_text() -> str:
    parts = content()
    return parts.get("watermark", "开源免费软件 · 请勿付费购买")


def full_notice_text() -> str:
    parts = content()
    return (f"{parts.get('header', '')}\n"
            f"{parts.get('headline', '')}\n"
            f"{parts.get('subhead', '')}\n\n"
            f"{parts.get('detail', '')}\n\n"
            f"项目地址：{parts.get('source', SOURCE_URL)}")


def export_notice_lines() -> list[str]:
    """导出到清单/HTML 里的声明行。"""
    parts = content()
    return [
        parts.get("header", "本软件开源免费"),
        parts.get("subhead", "若您付费以获取此工具，请立即退款"),
        f"项目地址：{parts.get('source', SOURCE_URL)}",
    ]


def short_banner() -> str:
    parts = content()
    return f"{parts.get('header', '')} · {parts.get('subhead', '')}"
