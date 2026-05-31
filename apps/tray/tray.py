#!/usr/bin/env python3
"""
MeetBuddy Tray — system-tray controller for the audio capture daemon.

Starts capture.py --daemon in the background, then lets you start/stop
recording from the tray icon without touching a terminal.

Install deps first:
    pip install pystray pillow
    # capture.py also needs:  pip install httpx
"""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# Prefer the xorg backend on Linux — works on both X11 and Wayland+Xwayland
# and avoids the AppIndicator3/AyatanaAppIndicator3 GIR dependency.
os.environ.setdefault("PYSTRAY_BACKEND", "xorg")

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing deps — run:  pip install pystray pillow")
    sys.exit(1)

DAEMON_PORT = 7779
CONFIG_FILE = Path.home() / ".config" / "meetbuddy" / "tray.json"
CAPTURE_PY  = Path(__file__).parent.parent / "capture" / "capture.py"
# Use the API venv's python if available (it has httpx), otherwise fall back
_VENV_PY    = Path(__file__).parent.parent / "api" / ".venv" / "bin" / "python"
PYTHON      = str(_VENV_PY) if _VENV_PY.exists() else sys.executable


# ── Config ─────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return {"token": "", "api": "http://localhost:8000"}


def save_config(cfg: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── Daemon HTTP helpers ────────────────────────────────────────────────────

def _req(path: str, method: str = "GET", body: dict | None = None) -> dict | None:
    url  = f"http://127.0.0.1:{DAEMON_PORT}/{path}"
    data = json.dumps(body).encode() if body else None
    hdrs = {"Content-Type": "application/json"} if data else {}
    req  = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def daemon_status() -> dict | None:
    return _req("status")


def daemon_start(token: str, api: str) -> bool:
    r = _req("start", "POST", {"token": token, "api": api})
    return bool(r and r.get("ok"))


def daemon_stop() -> bool:
    r = _req("stop", "POST")
    return bool(r and r.get("ok"))


# ── Tray icons ─────────────────────────────────────────────────────────────

def _make_icon(recording: bool) -> Image.Image:
    sz  = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    bg  = (239, 68, 68, 255) if recording else (99, 102, 241, 255)
    d.ellipse([2, 2, sz - 2, sz - 2], fill=bg)

    if recording:
        # White square = stop
        d.rectangle([20, 20, 44, 44], fill=(255, 255, 255, 255))
    else:
        # Simple mic shape
        d.rectangle([26, 12, 38, 34], fill=(255, 255, 255, 255))
        d.arc([18, 28, 46, 48], start=180, end=0, fill=(255, 255, 255, 255), width=4)
        d.line([32, 48, 32, 54], fill=(255, 255, 255, 255), width=4)
        d.line([24, 54, 40, 54], fill=(255, 255, 255, 255), width=4)

    return img


# ── Settings via zenity (no tkinter dependency) ────────────────────────────

def _settings_window(cfg: dict, on_save) -> None:
    """Open a settings dialog using zenity (pre-installed on GNOME)."""
    def _prompt(title: str, text: str, current: str, hide: bool = False) -> str | None:
        cmd = ["zenity", "--entry", f"--title=MeetBuddy - {title}",
               f"--text={text}", f"--entry-text={current}"]
        if hide:
            cmd.append("--hide-text")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                return r.stdout.strip()
        except FileNotFoundError:
            pass
        return None

    api = _prompt("Settings", "API URL:", cfg.get("api", "http://localhost:8000"))
    if api is None:
        return  # user cancelled

    tok = _prompt("Settings", "Access Token\n(get from the MeetBuddy dashboard → Meetings):",
                  cfg.get("token", ""), hide=True)
    if tok is None:
        return

    cfg["api"]   = api
    cfg["token"] = tok
    save_config(cfg)
    on_save(cfg)


# ── Main tray application ──────────────────────────────────────────────────

class TrayApp:
    def __init__(self):
        self.cfg        = load_config()
        self._proc: subprocess.Popen | None = None
        self._recording = False

        self._icon = pystray.Icon(
            "meetbuddy",
            _make_icon(False),
            "MeetBuddy | idle",
            menu=pystray.Menu(
                pystray.MenuItem("Record / Stop", self._toggle, default=True),
                pystray.MenuItem("Settings…",    self._open_settings),
                pystray.MenuItem("Open dashboard", self._open_dashboard),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

        if not CAPTURE_PY.exists():
            print(f"[tray] WARNING: capture.py not found at {CAPTURE_PY}")
        else:
            self._launch_daemon()

        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Daemon lifecycle ────────────────────────────────────────────────────

    def _launch_daemon(self) -> None:
        self._proc = subprocess.Popen(
            [PYTHON, str(CAPTURE_PY), "--daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Give it a moment to bind
        time.sleep(1.2)

    def _ensure_daemon(self) -> None:
        """Restart daemon if it died."""
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            self._launch_daemon()

    # ── Background poller ───────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while True:
            time.sleep(2)
            self._ensure_daemon()
            st = daemon_status()
            if st is None:
                continue

            rec     = bool(st.get("recording"))
            elapsed = int(st.get("elapsed_s", 0))
            size_mb = st.get("size_mb", 0.0)

            if rec != self._recording:
                self._recording = rec
                self._icon.icon = _make_icon(rec)

            self._icon.title = (
                f"MeetBuddy | {elapsed // 60:02d}:{elapsed % 60:02d}  {size_mb:.1f} MB"
                if rec else "MeetBuddy | idle"
            )

    # ── Menu callbacks ──────────────────────────────────────────────────────

    def _toggle(self, icon, item) -> None:
        if self._recording:
            daemon_stop()
            return
        tok = self.cfg.get("token", "").strip()
        if not tok:
            self._open_settings(icon, item)
            return
        ok = daemon_start(tok, self.cfg.get("api", "http://localhost:8000"))
        if not ok:
            print("[tray] daemon_start failed — is the daemon running?")

    def _open_settings(self, icon, item) -> None:
        def _on_save(new_cfg):
            self.cfg = new_cfg
        threading.Thread(
            target=_settings_window, args=(self.cfg, _on_save), daemon=True
        ).start()

    def _open_dashboard(self, icon, item) -> None:
        api = self.cfg.get("api", "http://localhost:8000")
        webbrowser.open(api.replace(":8000", ":3000") + "/meetings")

    def _quit(self, icon, item) -> None:
        if self._recording:
            daemon_stop()
        if self._proc:
            self._proc.terminate()
        icon.stop()

    def run(self) -> None:
        self._icon.run()


if __name__ == "__main__":
    TrayApp().run()
