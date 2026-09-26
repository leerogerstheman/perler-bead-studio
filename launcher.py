# -*- coding: utf-8 -*-
"""启动器：寻找带 tkinter + Pillow 的 Python，检查界面文件后启动图形界面。

一般不用手动运行，双击 启动.bat 即可；也可以在命令行执行 python launcher.py。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 控制台编码可能是 GBK 或重定向到文件，打印中文时不要抛异常
_CONSOLE_SAFE = False
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    except Exception:      # noqa: BLE001
        pass
try:
    "测试".encode(sys.stdout.encoding or "utf-8")
    _CONSOLE_SAFE = True
except Exception:          # noqa: BLE001
    _CONSOLE_SAFE = False


def say(text: str = "") -> None:
    """打印中文，编码不支持时自动降级，绝不让启动器崩在输出上。"""
    try:
        print(text)
    except Exception:      # noqa: BLE001
        try:
            print(text.encode("ascii", "replace").decode("ascii"))
        except Exception:  # noqa: BLE001
            pass


def ask_enter(text: str = "按回车键退出…") -> None:
    try:
        input(text)
    except Exception:      # noqa: BLE001
        pass

CHECK = "import tkinter, PIL; from PIL import Image, ImageTk"

CANDIDATES = [
    os.environ.get("PERLER_PYTHON", ""),
    os.environ.get("DSH_PYTHON", ""),
    os.path.join(os.path.dirname(sys.executable), "python.exe"),
    os.path.join(BASE_DIR, "python", "python.exe"),
    os.path.expandvars(r"%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime"
                       r"\dependencies\python\python.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python313\python.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python310\python.exe"),
    r"C:\Python313\python.exe",
    r"C:\Python312\python.exe",
    r"C:\Python311\python.exe",
    r"C:\Python310\python.exe",
    shutil.which("python") or "",
    shutil.which("python3") or "",
]


def works(exe: str) -> bool:
    """确认解释器真的能跑，并且带 tkinter 与 Pillow。"""
    if not exe or not os.path.exists(exe):
        return False
    if "windowsapps" in exe.lower():        # 微软商店的占位程序，跳过
        return False
    try:
        proc = subprocess.run([exe, "-c", CHECK], capture_output=True, text=True,
                              timeout=90, cwd=BASE_DIR)
    except Exception:                        # noqa: BLE001
        return False
    return proc.returncode == 0


def find_python() -> str | None:
    seen: set[str] = set()
    for exe in CANDIDATES:
        if not exe:
            continue
        key = exe.lower()
        if key in seen:
            continue
        seen.add(key)
        if works(exe):
            return exe

    py = shutil.which("py")
    if py:
        for args in (["-3"], ["-3.13"], ["-3.12"], ["-3.11"], ["-3.10"]):
            try:
                probe = subprocess.run([py] + args + ["-c", CHECK],
                                       capture_output=True, text=True, timeout=90)
            except Exception:                # noqa: BLE001
                continue
            if probe.returncode == 0:
                try:
                    out = subprocess.run([py] + args + ["-c", "import sys;print(sys.executable)"],
                                         capture_output=True, text=True, timeout=90)
                    exe = (out.stdout or "").strip()
                except Exception:            # noqa: BLE001
                    exe = ""
                return exe or py
    return None


def _pythonw(python: str) -> str:
    """有 pythonw.exe 就用它启动，避免多一个黑色控制台窗口。

    winsound 在 pythonw 里不可用，所以用「能否加载 tkinter + PIL」来验证，
    验证不通过就退回带控制台的 python.exe，绝不让窗口起不来。
    """
    if os.path.basename(python).lower() == "pythonw.exe":
        return python
    candidate = os.path.join(os.path.dirname(python), "pythonw.exe")
    if not os.path.exists(candidate):
        return python
    try:
        probe = subprocess.run([candidate, "-c", CHECK], capture_output=True,
                               timeout=90, cwd=BASE_DIR)
    except Exception:      # noqa: BLE001
        return python
    return candidate if probe.returncode == 0 else python


def main() -> int:
    if not os.path.exists(os.path.join(BASE_DIR, "studio.py")):
        say("找不到 studio.py，请确认整个文件夹是一起拷贝过来的。")
        ask_enter()
        return 1

    python = find_python()
    if not python:
        say("=" * 62)
        say("没有找到可用的 Python 环境（需要 Python 3.10+，并已安装 Pillow）。")
        say("解决办法：")
        say("  1. 到 https://www.python.org/downloads/ 安装 Python（勾选 Add to PATH）")
        say("  2. 在命令行执行： pip install pillow")
        say("  3. 再双击 启动.bat")
        say("=" * 62)
        ask_enter()
        return 1

    if os.path.normcase(os.path.abspath(python)) != os.path.normcase(sys.executable):
        say(f"使用 Python：{python}")
    exe = python
    if "--no-window" in sys.argv[1:]:
        exe = _pythonw(python)
    return subprocess.call([exe, os.path.join(BASE_DIR, "studio.py")], cwd=BASE_DIR)


if __name__ == "__main__":
    sys.exit(main())
