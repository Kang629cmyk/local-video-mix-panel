from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5010
URL = f"http://{HOST}:{PORT}"
SCRIPT_PATH = ROOT / "scripts" / "panel_app.py"
LOG_PATH = ROOT / "panel_launcher.log"


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


def show_message(title: str, message: str, icon: int = 0x40) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, title, icon)


def server_ready(timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def iter_python_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    seen: set[str] = set()

    def add_command(executable: str | None, *extra: str) -> None:
        if not executable:
            return
        key = os.path.normcase(executable)
        if key in seen:
            return
        seen.add(key)
        commands.append([executable, *extra, str(SCRIPT_PATH)])

    current = Path(sys.executable)
    if current.name.lower().startswith("python"):
        add_command(str(current))

    for name in ("pythonw.exe", "pythonw", "python.exe", "python"):
        add_command(shutil.which(name))

    py_launcher = shutil.which("py.exe") or shutil.which("py")
    add_command(py_launcher, "-3")
    return commands


def creation_flags() -> int:
    return (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


def start_server() -> None:
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"找不到面板程式：{SCRIPT_PATH}")

    last_error: Exception | None = None
    for command in iter_python_commands():
        try:
            log(f"啟動面板：{' '.join(command)}")
            subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags(),
            )
            return
        except Exception as exc:
            last_error = exc
            log(f"啟動失敗：{exc!r}")

    if last_error is not None:
        raise last_error
    raise RuntimeError("找不到可用的 Python 啟動方式。")


def wait_for_server(max_wait_seconds: float = 20.0) -> bool:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if server_ready():
            log("面板伺服器已就緒。")
            return True
        time.sleep(0.5)
    return False


def open_browser() -> None:
    try:
        if hasattr(os, "startfile"):
            os.startfile(URL)  # type: ignore[attr-defined]
            log("已用 os.startfile 開啟瀏覽器。")
            return
    except Exception as exc:
        log(f"os.startfile 開啟失敗：{exc!r}")

    try:
        subprocess.Popen(["cmd", "/c", "start", "", URL], creationflags=creation_flags())
        log("已用 cmd start 開啟瀏覽器。")
        return
    except Exception as exc:
        log(f"cmd start 開啟失敗：{exc!r}")

    webbrowser.open(URL, new=2)
    log("已用 webbrowser.open 開啟瀏覽器。")


def main() -> None:
    try:
        log("收到開啟面板要求。")
        if not server_ready():
            log("目前尚未有面板伺服器，準備啟動。")
            start_server()
            if not wait_for_server():
                raise RuntimeError("面板已嘗試啟動，但 20 秒內沒有回應。")
        else:
            log("偵測到既有面板伺服器。")
        open_browser()
    except Exception as exc:
        log(f"開啟失敗：{exc!r}")
        show_message("Open Panel Failed", str(exc), 0x10)


if __name__ == "__main__":
    main()
