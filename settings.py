# -*- coding: utf-8 -*-
"""用户设置的保存与读取（启动声明的「不再显示」勾选会记在这里）。

存放在程序目录下的 settings.json；如果目录不可写（例如放在只读位置），
自动退回 %APPDATA%\\PerlerBeadStudio\\settings.json。
"""

from __future__ import annotations

import json
import os
import tempfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_FILE = os.path.join(APP_DIR, "settings.json")
ROAMING_FILE = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "PerlerBeadStudio", "settings.json")

DEFAULTS: dict = {
    "notice_dismissed": False,     # 是否勾选过「不再显示启动声明」
    "notice_version": 0,           # 已确认的声明版本号
    "window_geometry": "",         # 上次窗口位置大小
    "last_palette": "",
    "last_cols": 0,
    "last_rows": 0,
    "last_fit_mode": "",
}


def _read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception:      # noqa: BLE001
        pass
    return {}


def _writable_dir(path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), delete=True):
            pass
        return True
    except Exception:      # noqa: BLE001
        return False


def settings_path() -> str:
    """返回实际可写的配置文件路径。"""
    if _writable_dir(LOCAL_FILE):
        return LOCAL_FILE
    return ROAMING_FILE


def load() -> dict:
    """读取设置，缺失项用默认值补齐。"""
    data = dict(DEFAULTS)
    for path in (LOCAL_FILE, ROAMING_FILE):
        if os.path.exists(path):
            data.update(_read(path))
            break
    return data


def save(data: dict) -> bool:
    """写入设置；失败时返回 False（不影响程序运行）。"""
    merged = dict(load())
    merged.update(data)
    for path in (LOCAL_FILE, ROAMING_FILE):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(merged, fh, ensure_ascii=False, indent=2)
            return True
        except Exception:      # noqa: BLE001
            continue
    return False


def get(key: str, default=None):
    return load().get(key, DEFAULTS.get(key, default))


def set_value(key: str, value) -> bool:
    return save({key: value})
