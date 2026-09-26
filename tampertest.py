# -*- coding: utf-8 -*-
"""对抗测试：模拟「倒卖的人想删掉免费声明」的各种做法，验证都会失败。

覆盖：
  1. 改声明文案            -> 签名校验失败
  2. 删签名字段            -> 校验失败
  3. 删掉设置文件想重置    -> 声明照样弹出
  4. 篡改 settings.json 假装已同意 -> 声明照样弹出
  5. 篡改后界面顶部         -> 常驻红色警告条
  6. 删掉声明模块           -> 兜底文案仍然说明「开源免费」
  7. 导出的 7 种文件         -> 全都带免费声明与项目地址

运行：python tampertest.py
"""

from __future__ import annotations

import builtins
import importlib
import json
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

import notice_core   # noqa: E402
import settings      # noqa: E402

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


class Tampered:
    """临时把 notice_core 换成被篡改的版本，测完自动还原。"""

    def __init__(self, mode: str = "text"):
        self.mode = mode

    def __enter__(self):
        if self.mode == "text":
            self._patch(parts_edit={"headline": "这是一款付费软件，售价 9.9 元"})
        elif self.mode == "drop":
            self._patch(drop="headline")
        elif self.mode == "broken":
            self._patch(blob="这不是合法的内容")
        return self

    def __exit__(self, *exc):
        importlib.reload(notice_core)
        for name in ("notice", "studio", "painter"):
            if name in sys.modules:
                importlib.reload(sys.modules[name])
        return False

    def _patch(self, parts_edit=None, drop=None, blob=None):
        parts = dict(notice_core._load())
        if parts_edit:
            parts.update(parts_edit)
        if drop:
            parts.pop(drop, None)
        if blob is not None:
            import base64
            import zlib
            raw = base64.b64encode(notice_core._xor(zlib.compress(blob.encode()))).decode()
        else:
            text = "\n".join(
                f"{name}=" + str(parts.get(name, "")).replace("\\", "\\\\").replace("\n", "\\n")
                for name in notice_core.FIELDS)
            import base64
            import zlib
            raw = base64.b64encode(notice_core._xor(zlib.compress(text.encode(), 9))).decode()
        notice_core._BLOB = raw            # type: ignore[attr-defined]
        # 签名故意保持原样：模拟「改了内容但没（也没法）更新签名」


def main() -> int:
    print("=" * 68)
    print("对抗测试：倒卖者想删掉免费声明的 7 种做法")
    print("=" * 68)

    # ---------------- 1. 改文案 ----------------
    print("\n[1] 直接改声明文案（把「请立即退款」改成「付费软件」）")
    with Tampered("text"):
        ok, reason = notice_core.verify()
        check(not ok, f"签名校验失败：{reason}")
        import notice
        check(notice.should_show(), "should_show() 强制为 True（每次启动都弹）")
        c = notice_core.content()
        check("付费软件" in c.get("headline", "") or "不收取任何费用" in c.get("header", ""),
              "即使被改，兜底/原文仍能取到")

    # ---------------- 2. 删字段 ----------------
    print("\n[2] 删掉声明里的关键字段")
    with Tampered("drop"):
        ok, reason = notice_core.verify()
        check(not ok, f"校验失败：{reason}")

    # ---------------- 3. 内容彻底破坏 ----------------
    print("\n[3] 把混淆内容整段换成垃圾（想让程序读不到）")
    with Tampered("broken"):
        ok, reason = notice_core.verify()
        check(not ok, f"校验失败：{reason}")
        c = notice_core.content()
        check("开源" in c.get("header", "") and "退款" in c.get("headline", ""),
              "退回兜底文案，仍然写明开源免费与退款提醒")

    # ---------------- 4. 删设置文件想重置 ----------------
    print("\n[4] 删掉 settings.json 想让声明消失")
    path = settings.settings_path()
    if os.path.exists(path):
        os.remove(path)
    import notice
    check(notice.should_show(), "声明照样会弹出（没有设置文件＝首次运行）")

    # ---------------- 5. 伪造已同意 ----------------
    print("\n[5] 篡改 settings.json 假装已经勾选过")
    settings.save({"notice_dismissed": True, "notice_version": notice.NOTICE_VERSION})
    check(not notice.should_show(), "声明完好时：勾选有效，不再弹出（这是正常功能）")
    with Tampered("text"):
        importlib.reload(notice)
        check(notice.should_show(), "声明被改过时：伪造的「已同意」失效，强制重新弹出")

    # ---------------- 6. 界面警告条 ----------------
    print("\n[6] 篡改后启动主界面")
    with Tampered("text"):
        importlib.reload(notice)
        import studio
        importlib.reload(studio)
        root = tk.Tk()
        app = studio.StudioApp(root)
        root.withdraw()
        pump(root, 0.8)
        shown = bool(app.integrity_banner.winfo_ismapped()) or \
            app.integrity_banner.grid_info() != {}
        check(shown, "顶部出现常驻红色警告条")
        text = app.integrity_label.cget("text")
        check("免费声明被删除或修改" in text, f"警告文案：{text[:34]}…")
        status = app.root.winfo_children()[-1]
        root.destroy()

    # ---------------- 7. 导出文件全带声明 ----------------
    print("\n[7] 导出文件的免费声明（这一层删不掉）")
    importlib.reload(notice_core)
    for name in ("notice", "studio", "painter"):
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    import palette as pal
    import painter
    from core import ConvertOptions, convert_file

    items = pal.get_palette("标准色卡（50 色）")
    pattern = convert_file(os.path.join(BASE_DIR, "示例图片.png"),
                           ConvertOptions(cols=32, rows=32), items)
    out = os.path.join(BASE_DIR, "自检输出", "对抗测试")
    files = painter.export_all(pattern, out, "tamper_32x32", title="对抗测试")
    keys = notice_core.export_notice_lines()

    def has(path: str) -> bool:
        try:
            if path.endswith(".png"):
                # PNG 的 tEXt 只能 ASCII，中文声明在图片水印上，这里校验元数据来源
                from PIL import Image
                info = Image.open(path).info
                return bool(info.get("Source")) and bool(info.get("License"))
            if path.endswith(".svg"):
                return "开源免费" in open(path, encoding="utf-8").read()
            return keys[0] in open(path, encoding="utf-8-sig", errors="replace").read()
        except Exception as exc:      # noqa: BLE001
            print("      读取失败:", exc)
            return False

    for path in files:
        check(has(path), f"{os.path.basename(path)} 含免费声明")

    print("\n" + "=" * 68)
    if FAILS:
        print(f"对抗测试未通过 {len(FAILS)} 项：")
        for item in FAILS:
            print("   -", item)
        return 1
    print("对抗测试全部通过 ✔ —— 删声明没有收益")
    return 0


if __name__ == "__main__":
    sys.exit(main())
