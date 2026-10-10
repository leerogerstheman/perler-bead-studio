# -*- coding: utf-8 -*-
"""网页界面：用标准库 http.server 提供界面，浏览器打开即用。

为什么不引入 pywebview 之类的第三方库
--------------------------------------
本项目的全部第三方依赖是 **Pillow**（图像处理，绕不开），外加 Windows 自带的
Python。拷走整个文件夹就能跑，是这个工具存在的意义。

pywebview 会带来它自己的一串依赖（pythonnet / cef 之类），还要在打包时额外处理。
而界面这一层需要的只是「把 HTML 给浏览器看」——`http.server` 是标准库，一行依赖都
不用加，在自带运行时里也照常工作。

所以：**界面用网页，后端仍然是原来那套逻辑**。core.py 和 painter.py 一个字都没改，
转换、渲染、导出的行为与桌面版完全一致。

与桌面版的关系
--------------
studio.py（tkinter）原样保留，两者并存：

    启动.bat          桌面版（tkinter）
    启动网页版.bat     网页版（本文件）

两者共用 core.py / painter.py / palette.py / settings.py。网页版不需要 tkinter。

接口
----
    GET  /                    界面
    GET  /app.css /app.js     静态资源
    GET  /api/meta            色卡、尺寸预设、填充方式等选项
    POST /api/image           上传图片（请求体就是图片字节）
    POST /api/sample          载入内置示例图
    GET  /api/thumb           当前图片的缩略图（PNG）
    POST /api/convert         按选项转换，返回统计与预览地址
    GET  /api/preview.png     渲染图纸（PNG）
    POST /api/export          导出全部文件
    POST /api/reveal          在资源管理器中打开导出目录

运行
----
    python webui.py            默认端口 8756，自动打开浏览器
    python webui.py --port 9000 --no-browser
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import core
import painter
import palette as palette_mod
import settings

APP_TITLE = "拼豆图纸生成器"

# ---------------------------------------------------------------- 路径 --

def _base_dir() -> str:
    """程序所在目录（打包成 exe 后取 exe 自己的目录，与 settings.py 一致）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
WEBUI_DIR = os.path.join(BASE_DIR, "webui")
EXPORT_DIR = os.path.join(BASE_DIR, "导出")


def _writable_base() -> str:
    """上传的图片放哪：程序目录可写就放程序目录，否则退回设置文件所在的目录。

    与 settings.py 同样的考虑——程序可能被放在只读位置（光盘、受管目录），
    那时不能因为写不进去就整个不能用。
    """
    try:
        probe = os.path.join(BASE_DIR, ".pbs-write-probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.remove(probe)
        return BASE_DIR
    except Exception:      # noqa: BLE001
        return os.path.dirname(settings.settings_path()) or BASE_DIR


UPLOAD_DIR = os.path.join(_writable_base(), "uploads")


def _ensure_dirs() -> None:
    for d in (EXPORT_DIR, UPLOAD_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:      # noqa: BLE001
            pass


# ---------------------------------------------------------------- 状态 --

class Session:
    """一次运行期间的状态：当前图片、上次转换结果、上次用的选项。

    http.server 是多线程的，转换又是 CPU 密集的，所以状态全部走这把锁。
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.image_path: str = ""
        self.image_name: str = ""
        self.image_w = 0
        self.image_h = 0
        self.pattern: core.BeadPattern | None = None
        self.options: core.ConvertOptions | None = None
        self.elapsed = 0.0
        self.exported: list[str] = []


SESSION = Session()


def _load_image_file(path: str, name: str) -> None:
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    SESSION.image_path = path
    SESSION.image_name = name
    SESSION.image_w = w
    SESSION.image_h = h
    # 换了图，之前的转换结果就作废了
    SESSION.pattern = None


# ---------------------------------------------------------------- 选项 --

def meta_payload() -> dict:
    return {
        "title": APP_TITLE,
        "palettes": palette_mod.palette_names(),
        "presets": [{"label": lbl, "cols": c, "rows": r} for lbl, c, r in core.size_presets()],
        "fitModes": [
            {"value": "fit", "label": "完整放入（不裁切）"},
            {"value": "fill", "label": "裁切填满（铺满整块板）"},
            {"value": "stretch", "label": "拉伸（会变形）"},
        ],
        "anchors": [
            {"value": "center", "label": "居中"},
            {"value": "top", "label": "靠上"},
            {"value": "bottom", "label": "靠下"},
            {"value": "left", "label": "靠左"},
            {"value": "right", "label": "靠右"},
        ],
        "defaults": {
            "cols": 32, "rows": 32,
            "palette": palette_mod.palette_names()[0],
            "dither": False, "fit": "fit", "anchor": "center",
            "bgRemoval": False, "tolerance": 24,
        },
        "exportDir": EXPORT_DIR,
    }


def _options_from(payload: dict) -> core.ConvertOptions:
    def num(key: str, fallback: int, lo: int, hi: int) -> int:
        try:
            v = int(payload.get(key, fallback))
        except Exception:      # noqa: BLE001
            v = fallback
        return max(lo, min(hi, v))

    name = str(payload.get("palette") or "")
    if name not in palette_mod.palette_names():
        name = palette_mod.palette_names()[0]

    fit = str(payload.get("fit") or "fit")
    if fit not in ("fit", "fill", "stretch"):
        fit = "fit"

    anchor = str(payload.get("anchor") or "center")
    if anchor not in ("center", "top", "bottom", "left", "right"):
        anchor = "center"

    return core.ConvertOptions(
        cols=num("cols", 32, 4, 1024),
        rows=num("rows", 32, 4, 1024),
        palette_name=name,
        dither=bool(payload.get("dither")),
        fit_mode=fit,
        crop_anchor=anchor,
        bg_removal=bool(payload.get("bgRemoval")),
        bg_tolerance=num("tolerance", 24, 0, 255),
        crop_to_content=True,
        keep_aspect=True,
    )


# ---------------------------------------------------------------- 转换 --

def do_convert(payload: dict) -> dict:
    if not SESSION.image_path or not os.path.exists(SESSION.image_path):
        raise ValueError("还没有选择图片")

    opts = _options_from(payload)
    items = palette_mod.get_palette(opts.palette_name)

    t0 = time.time()
    pattern = core.convert_file(SESSION.image_path, opts, items)
    elapsed = time.time() - t0

    with SESSION.lock:
        SESSION.pattern = pattern
        SESSION.options = opts
        SESSION.elapsed = elapsed

    counts = []
    for idx, n in pattern.counts():
        r, g, b = pattern.rgb[idx]
        counts.append({"name": pattern.names[idx], "hex": "#%02X%02X%02X" % (r, g, b), "count": n})

    return {
        "ok": True,
        "cols": pattern.cols,
        "rows": pattern.rows,
        "total": pattern.total,
        "colors": len(counts),
        "elapsed": round(elapsed, 2),
        "cellPx": pattern.cell_px,
        "sheets": core.estimate_sheets(pattern.rows, pattern.cols),
        "note": core.sharpness_note(pattern),
        "counts": counts,
        "image": {"name": SESSION.image_name, "w": SESSION.image_w, "h": SESSION.image_h},
    }


def _preview_cell(pattern: core.BeadPattern, target_px: int = 1400) -> int:
    """选一个格子边长，让渲染出来的图大致落在 target_px 上下。"""
    span = max(pattern.cols, pattern.rows)
    cell = int(target_px / max(1, span))
    return max(4, min(64, cell))


def render_preview(query: dict) -> bytes:
    import io
    with SESSION.lock:
        pattern = SESSION.pattern
    if pattern is None:
        raise ValueError("还没有可预览的图纸")

    def flag(key: str, default: bool = True) -> bool:
        v = (query.get(key) or [None])[0]
        if v is None:
            return default
        return v not in ("0", "false", "no")

    mode = (query.get("mode") or ["bead"])[0]
    if mode not in ("bead", "flat"):
        mode = "bead"

    try:
        cell = int((query.get("cell") or ["0"])[0])
    except Exception:      # noqa: BLE001
        cell = 0
    if cell <= 0:
        cell = _preview_cell(pattern)

    img = painter.render_chart(
        pattern, cell=cell,
        ruler=flag("ruler"), grid_lines=flag("grid"),
        show_coords=flag("coords"), mode=mode, watermark=False,
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def do_export(payload: dict) -> dict:
    with SESSION.lock:
        pattern = SESSION.pattern
    if pattern is None:
        raise ValueError("还没有可导出的图纸")

    base = str(payload.get("baseName") or "").strip()
    if not base:
        stem = os.path.splitext(os.path.basename(SESSION.image_path))[0] or "拼豆图纸"
        base = stem
    # 只保留文件名安全字符，避免把路径写到导出目录之外
    base = "".join(ch for ch in base if ch not in '\\/:*?"<>|').strip() or "拼豆图纸"

    title = str(payload.get("title") or "").strip() or base
    folder = os.path.join(EXPORT_DIR, f"{base}_{pattern.cols}x{pattern.rows}")
    files = painter.export_all(pattern, folder, base, title=title)

    with SESSION.lock:
        SESSION.exported = files

    return {
        "ok": True,
        "folder": folder,
        "files": [{"name": os.path.basename(p), "path": p,
                   "size": os.path.getsize(p) if os.path.exists(p) else 0} for p in files],
    }


# ---------------------------------------------------------------- HTTP --

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PerlerBeadStudioWeb/1.0"
    protocol_version = "HTTP/1.1"

    # 默认的 stderr 日志会刷屏；只留一行简明记录
    def log_message(self, fmt, *args):      # noqa: A003
        if os.environ.get("PBS_WEB_VERBOSE"):
            sys.stderr.write("  %s\n" % (fmt % args))

    # ---------------------------------------------------------- 工具 --

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, payload: dict, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _read_body(self, limit: int = 64 * 1024 * 1024) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except Exception:      # noqa: BLE001
            length = 0
        if length <= 0:
            return b""
        if length > limit:
            raise ValueError("请求体过大")
        return self.rfile.read(length)

    def _static(self, rel: str) -> None:
        # 只允许 webui/ 下的文件，防止路径穿越
        target = os.path.normpath(os.path.join(WEBUI_DIR, rel))
        if not target.startswith(os.path.normpath(WEBUI_DIR)):
            self._error("禁止访问", 403)
            return
        if not os.path.isfile(target):
            self._error("找不到 %s" % rel, 404)
            return
        ext = os.path.splitext(target)[1].lower()
        with open(target, "rb") as fh:
            self._send(200, fh.read(), CONTENT_TYPES.get(ext, "application/octet-stream"))

    # ---------------------------------------------------------- 路由 --

    def do_GET(self):       # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path in ("/", "/index.html"):
                self._static("index.html")
            elif path in ("/app.css", "/app.js"):
                self._static(path.lstrip("/"))
            elif path == "/api/meta":
                self._json(meta_payload())
            elif path == "/api/thumb":
                self._thumb()
            elif path == "/api/preview.png":
                self._send(200, render_preview(query), "image/png")
            else:
                self._error("未知路径 %s" % path, 404)
        except Exception as exc:      # noqa: BLE001
            traceback.print_exc()
            self._error(str(exc), 500)

    def do_POST(self):      # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/image":
                self._upload()
            elif path == "/api/sample":
                self._sample()
            elif path == "/api/convert":
                self._json(do_convert(self._payload()))
            elif path == "/api/export":
                self._json(do_export(self._payload()))
            elif path == "/api/reveal":
                self._reveal()
            else:
                self._error("未知路径 %s" % path, 404)
        except Exception as exc:      # noqa: BLE001
            traceback.print_exc()
            self._error(str(exc), 500)

    def _payload(self) -> dict:
        body = self._read_body()
        if not body:
            return {}
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:      # noqa: BLE001
            raise ValueError("请求体不是合法 JSON")
        if not isinstance(data, dict):
            raise ValueError("请求体必须是对象")
        return data

    # ------------------------------------------------------ 各端点 --

    def _upload(self) -> None:
        from PIL import Image
        body = self._read_body()
        if not body:
            self._error("没有收到图片数据")
            return
        _ensure_dirs()
        name = os.path.basename(self.headers.get("X-Filename") or "上传图片.png")
        ext = os.path.splitext(name)[1].lower() or ".png"
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"):
            ext = ".png"
        safe = "".join(ch for ch in os.path.splitext(name)[0] if ch not in '\\/:*?"<>|').strip() or "上传图片"
        path = os.path.join(UPLOAD_DIR, safe + ext)
        with open(path, "wb") as fh:
            fh.write(body)
        try:
            with Image.open(path) as im:
                im.verify()          # 确认真的是图片，而不是改了扩展名的别的东西
        except Exception as exc:      # noqa: BLE001
            try:
                os.remove(path)
            except OSError:
                pass
            self._error("这不是一个能识别的图片文件：%s" % exc)
            return
        with SESSION.lock:
            _load_image_file(path, name)
            w, h = SESSION.image_w, SESSION.image_h
        self._json({"ok": True, "name": name, "w": w, "h": h})

    def _sample(self) -> None:
        path = os.path.join(BASE_DIR, "示例图片.png")
        if not os.path.exists(path):
            import make_sample
            make_sample.main()
        if not os.path.exists(path):
            self._error("示例图片生成失败，请直接上传自己的图片")
            return
        with SESSION.lock:
            _load_image_file(path, "示例图片.png")
            w, h = SESSION.image_w, SESSION.image_h
        self._json({"ok": True, "name": "示例图片.png", "w": w, "h": h})

    def _thumb(self) -> None:
        import io
        from PIL import Image
        with SESSION.lock:
            path = SESSION.image_path
        if not path or not os.path.exists(path):
            self._error("还没有选择图片", 404)
            return
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((640, 640))
            buf = io.BytesIO()
            im.save(buf, format="PNG")
        self._send(200, buf.getvalue(), "image/png")

    def _reveal(self) -> None:
        folder = str(self._payload().get("folder") or EXPORT_DIR)
        if not os.path.isdir(folder):
            self._error("目录不存在：%s" % folder)
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)      # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as exc:      # noqa: BLE001
            self._error("打不开目录：%s" % exc)
            return
        self._json({"ok": True})


# ---------------------------------------------------------------- 启动 --

def _free_port(preferred: int) -> int:
    """优先用固定端口，被占用时让系统随便给一个。"""
    for candidate in (preferred, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", candidate))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError("找不到可用端口")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    port = 8756
    open_browser = True
    for i, a in enumerate(argv):
        if a == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])
        elif a == "--no-browser":
            open_browser = False
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0

    if not os.path.isdir(WEBUI_DIR):
        print("找不到界面目录：%s" % WEBUI_DIR)
        return 1

    _ensure_dirs()
    port = _free_port(port)
    url = "http://127.0.0.1:%d/" % port

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True

    print()
    print("  " + "=" * 58)
    print("   %s · 网页版" % APP_TITLE)
    print("  " + "=" * 58)
    print()
    print("   地址 / URL    %s" % url)
    print("   导出目录      %s" % EXPORT_DIR)
    print()
    print("   只监听本机。按 Ctrl+C 停止。")
    print("   Localhost only. Press Ctrl+C to stop.")
    print()

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。\n")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
