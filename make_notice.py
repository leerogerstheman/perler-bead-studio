# -*- coding: utf-8 -*-
"""生成 notice_core.py 里的混淆内容与 HMAC 签名。

改声明文案时：先改本文件的 NOTICE 字典，运行本脚本，把输出的 _BLOB / _SIGNATURE
替换进 notice_core.py（或直接运行本脚本自动改写文件）。

运行：python make_notice.py
"""

from __future__ import annotations

import base64
import os
import re
import sys
import zlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import notice_core   # noqa: E402

NOTICE = {
    "title": "重要声明",
    "header": "本软件在 GitHub 上开源，不收取任何费用",
    "org": "拼豆图案生成器 · Perler Bead Studio",
    "source": "github.com/leerogerstheman/perler-bead-studio",
    "headline": "若您付费以获取此工具，请立即退款",
    "subhead": "本程序是开源免费软件，任何人都不应以任何形式向您收费",
    "detail": ("本程序是开源免费软件，任何人都可以自由下载、使用与分享。\n"
               "开发者不会通过任何渠道收费；如果您是从某个店铺、网盘、群聊或"
               "「代下载」服务付费得到的，那笔钱与本项目无关，请尽快申请退款。\n"
               "声明内容带有数字签名，删除或修改声明不会让程序变得「更好用」，"
               "只会让每次启动都重新提醒您。"),
    "check_text": "我已了解，不再显示此窗口",
    "footer": "继续使用即表示您已阅读并理解上述内容",
    "watermark": "开源免费 · 请勿付费购买 · github.com/leerogerstheman/perler-bead-studio",
}


def pack(parts: dict) -> str:
    text = "\n".join(
        f"{name}=" + str(parts[name]).replace("\\", "\\\\").replace("\n", "\\n")
        for name in notice_core.FIELDS)
    raw = text.encode("utf-8")
    return base64.b64encode(notice_core._xor(zlib.compress(raw, 9))).decode("ascii")


def wrap(blob: str, width: int = 74) -> str:
    chunks = [blob[i:i + width] for i in range(0, len(blob), width)]
    return "\n".join(f'    "{c}"' for c in chunks)


def main() -> int:
    missing = [f for f in notice_core.FIELDS if f not in NOTICE]
    if missing:
        print("缺少字段：", missing)
        return 1

    blob = pack(NOTICE)
    signature = notice_core.sign(NOTICE)

    path = os.path.join(BASE_DIR, "notice_core.py")
    with open(path, "r", encoding="utf-8") as fh:
        source = fh.read()

    new_source = re.sub(r"_BLOB = \(\n(?:.*\n)*?\)",
                        "_BLOB = (\n" + wrap(blob) + "\n)", source, count=1)
    new_source = re.sub(r'_SIGNATURE = "[0-9a-f]*"',
                        f'_SIGNATURE = "{signature}"', new_source, count=1)
    if new_source == source:
        print("警告：没有找到可替换的 _BLOB / _SIGNATURE，请检查 notice_core.py")
        return 1
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_source)

    print(f"已写入 notice_core.py")
    print(f"  混淆内容长度：{len(blob)} 字符")
    print(f"  签名：{signature}")
    print(f"  水印：{NOTICE['watermark']}")
    print("  请另开进程运行 noticetest.py 校验（本进程内的模块已缓存）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
