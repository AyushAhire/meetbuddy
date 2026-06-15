#!/usr/bin/env python3
"""
MeetBuddy — single-window desktop app + system tray (Linux).

Supervises the whole local stack in one process:
  • starts the FastAPI backend (SQLite, local files, no login) on 127.0.0.1:8000
  • starts the PipeWire capture daemon on 127.0.0.1:7779
  • shows the served dashboard in a native window

Left-click tray icon  → show / hide the window
Right-click           → Quit (stops the backend + daemon)

Install deps:
    pip install pystray pillow pywebview
"""

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

os.environ.setdefault("PYSTRAY_BACKEND", "xorg")

try:
    import pystray
    from PIL import Image, ImageDraw
    import webview
except ImportError:
    print("Missing deps — run:  pip install pystray pillow pywebview")
    sys.exit(1)

try:
    import cairosvg
    import io as _io
    _HAVE_CAIROSVG = True
except ImportError:
    _HAVE_CAIROSVG = False

# ── Paths & ports ─────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent.parent
API_DIR     = ROOT / "apps" / "api"
CAPTURE_PY  = ROOT / "apps" / "capture" / "capture.py"
WEB_OUT     = ROOT / "apps" / "web" / "out"
FAVICON_SVG = Path(__file__).parent / "icon.svg"

_VENV_PY = API_DIR / ".venv" / "bin" / "python"
PYTHON   = str(_VENV_PY) if _VENV_PY.exists() else sys.executable

API_HOST, API_PORT = "127.0.0.1", 8000
DAEMON_PORT        = 7779
APP_URL            = f"http://{API_HOST}:{API_PORT}"

DATA_DIR = Path(os.environ.get("MEETBUDDY_DATA_DIR") or (Path.home() / ".local" / "share" / "MeetBuddy"))


def _backend_env() -> dict:
    """Environment forcing the fully-local backend (overrides any dev .env)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["MEETBUDDY_DATA_DIR"] = str(DATA_DIR)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DATA_DIR / 'meetbuddy.db'}"
    env["MEETBUDDY_STORAGE_BACKEND"] = "local"
    env["MEETBUDDY_WEB_DIR"] = str(WEB_OUT)
    return env


def _get(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _daemon_status() -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{DAEMON_PORT}/status", timeout=2) as r:
            import json
            return json.loads(r.read())
    except Exception:
        return None


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_icon(recording: bool) -> Image.Image:
    if _HAVE_CAIROSVG and FAVICON_SVG.exists():
        try:
            svg = FAVICON_SVG.read_text()
            if recording:
                svg = svg.replace("#3D7BFF", "#ef4444").replace("#080A0E", "#1a0000")
            png = cairosvg.svg2png(bytestring=svg.encode(), output_width=64, output_height=64)
            return Image.open(_io.BytesIO(png)).convert("RGBA")
        except Exception:
            pass
    sz = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (239, 68, 68, 255) if recording else (99, 102, 241, 255)
    d.ellipse([2, 2, sz - 2, sz - 2], fill=bg)
    if recording:
        d.rectangle([20, 20, 44, 44], fill=(255, 255, 255, 255))
    else:
        d.rectangle([26, 12, 38, 34], fill=(255, 255, 255, 255))
        d.arc([18, 28, 46, 48], start=180, end=0, fill=(255, 255, 255, 255), width=4)
        d.line([32, 48, 32, 54], fill=(255, 255, 255, 255), width=4)
        d.line([24, 54, 40, 54], fill=(255, 255, 255, 255), width=4)
    return img


# ── Supervisor + tray application ─────────────────────────────────────────────

class TrayApp:
    def __init__(self):
        self._api_proc: subprocess.Popen | None = None
        self._daemon_proc: subprocess.Popen | None = None
        self._recording = False
        self._window: "webview.Window | None" = None
        self._win_visible = True
        self._stopping = False

        # The system tray icon is optional. Many desktops (GNOME/Wayland) have no
        # XEmbed systray for pystray to dock into, so default to window-only and
        # let users opt in with MEETBUDDY_TRAY=1.
        self._icon = None
        if os.environ.get("MEETBUDDY_TRAY") == "1":
            try:
                self._icon = pystray.Icon(
                    "meetbuddy",
                    _make_icon(False),
                    "MeetBuddy | starting",
                    menu=pystray.Menu(
                        pystray.MenuItem("Show / Hide MeetBuddy", self._on_click, default=True),
                        pystray.Menu.SEPARATOR,
                        pystray.MenuItem("Quit", self._quit),
                    ),
                )
            except Exception as exc:
                print(f"[tray] system tray unavailable ({exc}); running window-only")
                self._icon = None

    # ── Backend lifecycle ─────────────────────────────────────────────────────

    def start_backend(self, wait_health: float = 30.0) -> bool:
        """Start the API + capture daemon. Returns True once the API is healthy."""
        env = _backend_env()
        log = open(DATA_DIR / "app.log", "a")

        if not WEB_OUT.joinpath("index.html").exists():
            print(f"[tray] WARNING: dashboard not built at {WEB_OUT} — run `pnpm build` in apps/web")

        self._api_proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "main:app", "--host", API_HOST, "--port", str(API_PORT)],
            cwd=str(API_DIR), env=env, stdout=log, stderr=log,
        )
        if CAPTURE_PY.exists():
            self._daemon_proc = subprocess.Popen(
                [PYTHON, str(CAPTURE_PY), "--daemon"],
                cwd=str(API_DIR), env=env, stdout=log, stderr=log,
            )
        else:
            print(f"[tray] WARNING: capture.py not found at {CAPTURE_PY}")

        deadline = time.time() + wait_health
        while time.time() < deadline:
            if self._api_proc.poll() is not None:
                print("[tray] API process exited early — see app.log")
                return False
            if _get(f"{APP_URL}/health"):
                return True
            time.sleep(0.4)
        print("[tray] API did not become healthy in time")
        return False

    def stop_backend(self) -> None:
        for proc in (self._daemon_proc, self._api_proc):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def _restart_daemon_if_dead(self) -> None:
        if self._daemon_proc and self._daemon_proc.poll() is not None and not self._stopping:
            self._daemon_proc = subprocess.Popen(
                [PYTHON, str(CAPTURE_PY), "--daemon"],
                cwd=str(API_DIR), env=_backend_env(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    # ── Tray icon poller (reflects recording state) ───────────────────────────

    def _poll_loop(self) -> None:
        while not self._stopping:
            time.sleep(2)
            self._restart_daemon_if_dead()
            st = _daemon_status()
            if st is None:
                continue
            rec = bool(st.get("recording"))
            elapsed = int(st.get("elapsed_s", 0))
            size_mb = st.get("size_mb", 0.0)
            self._recording = rec
            if self._icon is not None:
                self._icon.icon = _make_icon(rec)
                self._icon.title = (
                    f"MeetBuddy | {elapsed // 60:02d}:{elapsed % 60:02d}  {size_mb:.1f} MB"
                    if rec else "MeetBuddy | ready"
                )

    # ── Window show / hide ────────────────────────────────────────────────────

    def _on_click(self, icon, item) -> None:
        if self._window is None:
            return
        if self._win_visible:
            self._window.hide()
            self._win_visible = False
        else:
            self._window.show()
            self._win_visible = True

    def _quit(self, icon, item) -> None:
        self._stopping = True
        self.stop_backend()
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
        icon.stop()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        ok = self.start_backend()
        threading.Thread(target=self._poll_loop, daemon=True).start()

        # Point the window at the served dashboard (or the docs if the build is missing).
        url = APP_URL if ok and WEB_OUT.joinpath("index.html").exists() else f"{APP_URL}/docs"
        self._window = webview.create_window(
            "MeetBuddy",
            url=url,
            width=1120,
            height=760,
            min_size=(800, 560),
            background_color="#0c0c0e",
        )

        if self._icon is not None:
            try:
                self._icon.run_detached()
            except Exception as exc:
                print(f"[tray] could not start tray icon ({exc}); running window-only")
                self._icon = None

        try:
            webview.start(debug=False)
        finally:
            self._stopping = True
            self.stop_backend()
            if self._icon is not None:
                try:
                    self._icon.stop()
                except Exception:
                    pass


if __name__ == "__main__":
    TrayApp().run()
