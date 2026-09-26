# -*- coding: utf-8 -*-
"""启动声明测试：勾选「不再显示」后必须真的不再弹出，并且设置要落盘。

运行：python noticetest.py
"""

from __future__ import annotations

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

import notice as notice_mod   # noqa: E402
import settings               # noqa: E402

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


def read_file() -> dict:
    path = settings.settings_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def main() -> int:
    print("=" * 66)
    print("启动声明测试")
    print("=" * 66)

    path = settings.settings_path()
    print(f"设置文件：{path}")

    # ---- 1) 首次启动：应该显示 ----
    print("\n[1] 首次启动（没有勾选过）")
    settings.save({"notice_dismissed": False, "notice_version": 0})
    check(notice_mod.should_show(), "首次启动 should_show() == True")

    root = tk.Tk()
    root.withdraw()
    dlg = notice_mod.StartupNotice(root)
    pump(root, 0.6)
    check(dlg.window.winfo_exists() == 1, "声明窗口已创建")
    check(dlg.agreed.get() is False, "勾选框默认未选中")
    # 文案检查
    texts = []
    def walk(w):
        try:
            texts.append(str(w.cget("text")))
        except Exception:
            pass
        for c in w.winfo_children():
            walk(c)
    walk(dlg.window)
    joined = " ".join(texts)
    check("不收取任何费用" in joined, "包含「不收取任何费用」文案")
    check("请立即退款" in joined, "包含「请立即退款」文案")
    check("不再显示" in joined, "包含「不再显示此窗口」勾选项")

    # ---- 2) 不勾选直接继续：下次还应显示 ----
    print("\n[2] 不勾选，点「我知道了」")
    dlg._on_ok()
    pump(root, 0.3)
    check(dlg.result is True, "返回结果 True（允许继续使用）")
    check(read_file().get("notice_dismissed") is False, "未写入 dismissed")
    check(notice_mod.should_show(), "下次启动仍会显示")

    # ---- 3) 勾选后再继续：下次不再显示 ----
    print("\n[3] 勾选「不再显示」后点「我知道了」")
    dlg2 = notice_mod.StartupNotice(root)
    pump(root, 0.4)
    dlg2.agreed.set(True)
    dlg2._on_ok()
    pump(root, 0.3)
    data = read_file()
    check(data.get("notice_dismissed") is True, "已写入 notice_dismissed = true")
    check(data.get("notice_version") == notice_mod.NOTICE_VERSION,
          f"已记录声明版本 {data.get('notice_version')}")
    check(not notice_mod.should_show(), "再次启动 should_show() == False（不再弹出）")

    # ---- 4) 模拟重启：新建窗口也不应弹 ----
    print("\n[4] 模拟重启程序")
    check(not notice_mod.should_show(), "重启后依然不显示")

    # ---- 5) 声明版本升级后应重新提示 ----
    print("\n[5] 声明内容更新（版本号提高）")
    settings.save({"notice_dismissed": True, "notice_version": 0})
    check(notice_mod.should_show(), "旧版本号 -> 重新显示新声明")
    settings.save({"notice_dismissed": True, "notice_version": notice_mod.NOTICE_VERSION})
    check(not notice_mod.should_show(), "同版本号 -> 不显示")

    # ---- 6) 关闭窗口 = 退出程序 ----
    print("\n[6] 直接关掉声明窗口")
    settings.save({"notice_dismissed": False, "notice_version": 0})
    dlg3 = notice_mod.StartupNotice(root)
    pump(root, 0.4)
    dlg3._on_close()
    pump(root, 0.3)
    check(dlg3.result is False, "返回结果 False（应退出程序）")

    # ---- 7) 设置文件可读可写 ----
    print("\n[7] 设置文件读写")
    ok = settings.save({"notice_dismissed": True, "last_cols": 64})
    check(ok, "写入成功")
    check(settings.get("last_cols") == 64, "读回 last_cols = 64")
    check(os.path.exists(path), "settings.json 存在")

    root.destroy()
    print("\n" + "=" * 66)
    if FAILS:
        print(f"启动声明测试未通过 {len(FAILS)} 项：")
        for item in FAILS:
            print("   -", item)
        return 1
    print("启动声明测试全部通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
