"""绒球桌面版入口。

双击后：启动本地服务 → 打开原生窗口（pywebview / WebView2）。
窗口失败时退回默认浏览器，保证还能用。

参数：
    --headless   只启动服务并自检，不打开窗口（构建/测试用）
    --browser    不开原生窗口，直接用浏览器
    --port N     指定端口（默认自动挑空闲端口）
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _single_instance():
    """Windows 命名互斥量。返回 (handle, is_first)。"""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, "RongqiuSingleInstance_v1")
        return handle, kernel32.GetLastError() != 183
    except Exception:
        return None, True


def _notify(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, text, "绒球", 0x40)
    except Exception:
        print(text)


def _find_browser() -> str | None:
    """找 Edge / Chrome，用 --app 打开无地址栏的应用窗口。"""
    candidates = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env, "")
        if not base:
            continue
        candidates += [
            os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def _browser_has_profile(profile: str) -> bool:
    """Edge/Chrome 真正承载窗口的进程，会带着 --user-data-dir=... 启动。

    Popen 拿到的那个入口进程可能很快退出（把窗口移交给新的浏览器进程），
    所以不能 wait Popen，只能轮询带这个 profile 的进程是否还在。
    """
    try:
        import psutil
    except Exception:
        return False
    needle = str(profile).lower()
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "msedge" not in name and "chrome" not in name:
                continue
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            if needle and needle in cmdline:
                return True
        except Exception:
            continue
    return False


def _find_window_host():
    """找内嵌窗口宿主（由 tools/RongqiuWindow.cs 编译而来）。"""
    if getattr(sys, "frozen", False):
        candidates = [Path(sys.executable).resolve().parent / "RongqiuWindow.exe"]
    else:
        candidates = [
            Path(__file__).resolve().parent / "dist" / "Rongqiu" / "RongqiuWindow.exe",
            Path(__file__).resolve().parent / "RongqiuWindow.exe",
        ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _wait_http(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()

    from rongqiu import paths

    paths.ensure_home()
    log_path = paths.HOME / "app.log"
    if paths.FROZEN:
        # 打包版没有控制台；把标准输出接到空设备，避免第三方库写 None 崩溃。
        try:
            sys.stdout = open(os.devnull, "w")
            sys.stderr = open(os.devnull, "w")
        except OSError:
            pass
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.info("启动；frozen=%s home=%s", paths.FROZEN, paths.HOME)

    handle = None
    if not args.headless:
        handle, first = _single_instance()
        if not first:
            logging.info("已有实例在运行")
            _notify("绒球已经在运行了。")
            return 0

    port = args.port or _free_port()
    url = f"http://127.0.0.1:{port}"

    from app.server import app as fastapi_app
    import uvicorn

    # log_config=None：不要用 uvicorn 默认的 stdout 日志配置。
    # 打包成窗口程序后 sys.stdout 是 None，默认配置会让服务线程直接崩掉。
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=port,
                            log_config=None, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    def _serve():
        try:
            server.run()
        except Exception:
            logging.exception("服务线程崩溃")

    thread = threading.Thread(target=_serve, name="rongqiu-server", daemon=True)
    thread.start()

    if not _wait_http(url + "/api/env"):
        logging.error("服务启动失败，日志：%s", log_path)
        if not args.headless:
            _notify("绒球没能启动，查看日志：" + str(log_path))
        server.should_exit = True
        return 1

    logging.info("服务就绪 %s", url)

    if args.headless:
        try:
            with urllib.request.urlopen(url + "/api/stats", timeout=5) as resp:
                logging.info("headless OK；/api/stats=%s", resp.status)
        except Exception as exc:
            logging.warning("headless 自检失败：%s", exc)
        server.should_exit = True
        try:
            thread.join(timeout=5)
        except Exception:
            pass
        return 0

    window = None
    try:
        if args.browser:
            webbrowser.open(url)
        else:
            host = _find_window_host()
            if host:
                logging.info("启动内嵌窗口：%s", host)
                window = subprocess.Popen([
                    str(host), url, str(paths.HOME / "webview2"),
                ])
                window.wait()
                logging.info("窗口已关闭")
            else:
                logging.warning("没有找到 RongqiuWindow.exe，退回默认浏览器")
                webbrowser.open(url)
    except Exception:
        logging.exception("窗口启动失败，退回默认浏览器")
        try:
            if window is None:
                webbrowser.open(url)
        except Exception:
            pass

    try:
        # 没有原生窗口时保持服务存活，直到用户点「退出绒球」
        if window is None:
            while thread.is_alive():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        logging.info("退出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
