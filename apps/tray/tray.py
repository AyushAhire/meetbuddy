#!/usr/bin/env python3
"""
MeetBuddy Tray — system-tray + native desktop window.

Left-click  → open / show the app window
Right-click → menu with Quit

Install deps:
    pip install pystray pillow pywebview
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

DAEMON_PORT = 7779
CONFIG_FILE = Path.home() / ".config" / "meetbuddy" / "tray.json"
CAPTURE_PY  = Path(__file__).parent.parent / "capture" / "capture.py"
_VENV_PY    = Path(__file__).parent.parent / "api" / ".venv" / "bin" / "python"
PYTHON      = str(_VENV_PY) if _VENV_PY.exists() else sys.executable
FAVICON_SVG = Path(__file__).parent / "icon.svg"


# ── Config ──────────────────────────────────────────────────────────────────

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


# ── Daemon HTTP helpers ──────────────────────────────────────────────────────

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


# ── Tray icons ───────────────────────────────────────────────────────────────

def _make_icon(recording: bool) -> Image.Image:
    """
    Load the favicon SVG and tint it for the current state.
    Falls back to a PIL-drawn icon if cairosvg or the SVG file aren't available.
    """
    if _HAVE_CAIROSVG and FAVICON_SVG.exists():
        try:
            svg = FAVICON_SVG.read_text()
            if recording:
                # Swap blue waveform to red, darken background
                svg = svg.replace("#3D7BFF", "#ef4444").replace("#080A0E", "#1a0000")
            png = cairosvg.svg2png(bytestring=svg.encode(), output_width=64, output_height=64)
            return Image.open(_io.BytesIO(png)).convert("RGBA")
        except Exception:
            pass  # fall through to PIL fallback

    # PIL fallback
    sz  = 64
    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    bg  = (239, 68, 68, 255) if recording else (99, 102, 241, 255)
    d.ellipse([2, 2, sz - 2, sz - 2], fill=bg)
    if recording:
        d.rectangle([20, 20, 44, 44], fill=(255, 255, 255, 255))
    else:
        d.rectangle([26, 12, 38, 34], fill=(255, 255, 255, 255))
        d.arc([18, 28, 46, 48], start=180, end=0, fill=(255, 255, 255, 255), width=4)
        d.line([32, 48, 32, 54], fill=(255, 255, 255, 255), width=4)
        d.line([24, 54, 40, 54], fill=(255, 255, 255, 255), width=4)
    return img


# ── Python API exposed to the webview JS ────────────────────────────────────

class Api:
    def __init__(self, app: "TrayApp"):
        self._app = app

    def get_config(self) -> dict:
        return self._app.cfg.copy()

    def save_config(self, token: str, api_url: str) -> dict:
        self._app.cfg["token"] = token.strip()
        self._app.cfg["api"]   = api_url.strip()
        save_config(self._app.cfg)
        return {"ok": True}

    def get_status(self) -> dict:
        st = _req("status")
        if st:
            st["daemon_up"] = True
            return st
        return {"recording": False, "elapsed_s": 0, "size_mb": 0.0,
                "mic": "", "monitor": "", "meeting_id": None, "daemon_up": False}

    def start_recording(self) -> dict:
        tok = self._app.cfg.get("token", "").strip()
        api = self._app.cfg.get("api", "http://localhost:8000")
        if not tok:
            return {"ok": False, "error": "no_token"}
        # Validate token against API first
        try:
            req = urllib.request.Request(
                f"{api}/api/v1/meetings?limit=1",
                headers={"Authorization": f"Bearer {tok}"},
            )
            urllib.request.urlopen(req, timeout=5).close()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"ok": False, "error": "token_expired"}
        except Exception:
            return {"ok": False, "error": "api_down"}
        r = _req("start", "POST", {"token": tok, "api": api})
        return r if r else {"ok": False, "error": "daemon_down"}

    def stop_recording(self) -> dict:
        r = _req("stop", "POST")
        return r if r else {"ok": False, "error": "daemon_down"}

    def get_meetings(self) -> dict:
        tok = self._app.cfg.get("token", "").strip()
        api = self._app.cfg.get("api", "http://localhost:8000")
        if not tok:
            return {"error": "no_token", "items": []}
        req = urllib.request.Request(
            f"{api}/api/v1/meetings?limit=8",
            headers={"Authorization": f"Bearer {tok}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return {"error": None, "items": json.loads(r.read())}
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"error": "token_expired", "items": []}
            return {"error": "api_error", "items": []}
        except Exception:
            return {"error": "api_down", "items": []}

    def open_meeting(self, meeting_id: str) -> None:
        api = self._app.cfg.get("api", "http://localhost:8000")
        webbrowser.open(api.replace(":8000", ":3000") + f"/meetings/{meeting_id}")

    def open_dashboard(self) -> None:
        api = self._app.cfg.get("api", "http://localhost:8000")
        webbrowser.open(api.replace(":8000", ":3000") + "/meetings")


# ── Embedded HTML app ────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MeetBuddy</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg:#0c0c0e; --surface:#111113; --border:#1e1e20; --border2:#2a2a2e;
    --text:#ededed; --muted:#666; --muted2:#444;
    --indigo:#6366f1; --indigo-d:#4f51c8;
    --green:#22c55e; --red:#ef4444; --amber:#f59e0b;
  }
  html,body { height:100%; overflow:hidden; }
  body {
    background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    font-size:13px; display:flex; flex-direction:column; height:100vh;
    -webkit-font-smoothing:antialiased;
  }

  /* Header */
  .header {
    display:flex; align-items:center; gap:8px;
    padding:12px 14px 11px; border-bottom:1px solid var(--border); flex-shrink:0;
  }
  .logo {
    width:22px; height:22px; background:#080A0E; border-radius:6px;
    border:1px solid #1a1f2e;
    display:flex; align-items:center; justify-content:center; flex-shrink:0;
  }
  .logo svg { width:16px; height:16px; }
  .header-title { font-weight:600; font-size:13px; }
  .spacer { flex:1; }
  .icon-btn {
    background:none; border:none; cursor:pointer; padding:4px; color:var(--muted);
    border-radius:4px; display:flex; align-items:center; justify-content:center;
    transition:color .15s,background .15s;
  }
  .icon-btn:hover { color:var(--text); background:var(--surface); }
  .icon-btn svg { width:14px; height:14px; }

  /* Scroll */
  .scroll {
    flex:1; overflow-y:auto; padding:14px;
    display:flex; flex-direction:column; gap:12px;
  }
  .scroll::-webkit-scrollbar { width:4px; }
  .scroll::-webkit-scrollbar-thumb { background:var(--border2); border-radius:2px; }

  /* Record card */
  .record-card {
    background:var(--surface); border:1px solid var(--border); border-radius:10px;
    padding:20px 16px; display:flex; flex-direction:column; align-items:center; gap:14px;
    transition:border-color .2s;
  }
  .record-card.active { border-color:rgba(239,68,68,.3); }

  .record-btn {
    width:68px; height:68px; border-radius:50%; border:none; cursor:pointer;
    display:flex; align-items:center; justify-content:center;
    transition:transform .15s,opacity .15s;
  }
  .record-btn:hover { transform:scale(1.06); }
  .record-btn:active { transform:scale(.96); }
  .record-btn.idle {
    background:rgba(99,102,241,.1);
    box-shadow:0 0 0 1px rgba(99,102,241,.25);
  }
  .record-btn.recording {
    background:rgba(239,68,68,.1);
    box-shadow:0 0 0 1px rgba(239,68,68,.3);
    animation:pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,100% { box-shadow:0 0 0 1px rgba(239,68,68,.3),0 0 0 0 rgba(239,68,68,.15); }
    50%      { box-shadow:0 0 0 1px rgba(239,68,68,.4),0 0 0 10px rgba(239,68,68,0); }
  }

  .record-status { text-align:center; }
  .timer { font-size:26px; font-weight:700; letter-spacing:.5px; color:var(--red); font-variant-numeric:tabular-nums; }
  .rec-label { font-size:13px; font-weight:600; color:var(--muted); }
  .rec-sub { font-size:11px; color:var(--muted2); margin-top:3px; }

  .devices { display:flex; gap:5px; flex-wrap:wrap; justify-content:center; }
  .chip {
    font-size:10px; padding:2px 8px; border-radius:20px;
    background:rgba(255,255,255,.04); border:1px solid var(--border2); color:var(--muted);
  }

  /* Badges */
  .badge {
    display:inline-flex; align-items:center; gap:3px;
    font-size:10px; padding:2px 7px; border-radius:20px;
  }
  .badge-green { background:rgba(34,197,94,.08); border:1px solid rgba(34,197,94,.2); color:var(--green); }
  .badge-amber { background:rgba(245,158,11,.08); border:1px solid rgba(245,158,11,.2); color:var(--amber); }
  .badge-red   { background:rgba(239,68,68,.08);  border:1px solid rgba(239,68,68,.2);  color:var(--red);   }
  .badge-muted { background:rgba(255,255,255,.04); border:1px solid var(--border2);      color:var(--muted); }
  .dot { width:5px; height:5px; border-radius:50%; background:currentColor; }
  .blink { animation:blink 1.2s ease-in-out infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.25} }

  /* Banners */
  .banner {
    border-radius:7px; padding:9px 11px; font-size:11px; line-height:1.55;
    display:flex; align-items:flex-start; gap:7px;
  }
  .banner svg { width:13px; height:13px; flex-shrink:0; margin-top:1px; }
  .banner-amber { background:rgba(245,158,11,.07); border:1px solid rgba(245,158,11,.2); color:var(--amber); }
  .banner-red   { background:rgba(239,68,68,.07);  border:1px solid rgba(239,68,68,.2);  color:var(--red);   }

  /* Section */
  .section-hdr { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
  .section-title { font-size:10px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:.06em; }
  .text-btn { background:none; border:none; cursor:pointer; font-size:11px; color:var(--muted); font-family:inherit; padding:0; }
  .text-btn:hover { color:var(--text); }

  /* Meeting list */
  .meeting-item {
    display:flex; align-items:center; gap:10px;
    padding:9px 11px; border-radius:7px;
    background:var(--surface); border:1px solid var(--border);
    cursor:pointer; transition:border-color .15s,background .15s; margin-bottom:6px;
  }
  .meeting-item:last-child { margin-bottom:0; }
  .meeting-item:hover { border-color:var(--border2); background:#16161a; }
  .meeting-icon {
    width:28px; height:28px; border-radius:7px; flex-shrink:0;
    background:rgba(99,102,241,.08); border:1px solid rgba(99,102,241,.12);
    display:flex; align-items:center; justify-content:center;
  }
  .meeting-icon svg { width:13px; height:13px; color:var(--indigo); }
  .meeting-info { flex:1; min-width:0; }
  .meeting-time { font-size:12px; font-weight:500; }
  .meeting-plat { font-size:10px; color:var(--muted2); margin-top:2px; text-transform:capitalize; }
  .chevron svg { width:11px; height:11px; color:var(--muted2); }

  .empty { text-align:center; padding:22px; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
  .empty p { font-size:11px; color:var(--muted); }

  /* Settings */
  .settings-toggle {
    display:flex; align-items:center; gap:6px; width:100%;
    background:none; border:none; cursor:pointer;
    font-size:11px; color:var(--muted); font-family:inherit; padding:0;
  }
  .settings-toggle:hover { color:var(--text); }
  .settings-toggle svg { width:12px; height:12px; }
  .caret { margin-left:auto; transition:transform .2s; }
  .settings-toggle.open .caret { transform:rotate(180deg); }

  .settings-body { margin-top:10px; display:flex; flex-direction:column; gap:8px; }
  .field-label { display:block; font-size:10px; color:var(--muted); margin-bottom:4px; text-transform:uppercase; letter-spacing:.04em; }
  .field-input {
    width:100%; background:var(--surface); border:1px solid var(--border2);
    color:var(--text); font-size:12px; font-family:inherit;
    padding:7px 9px; border-radius:6px; outline:none; transition:border-color .15s;
  }
  .field-input:focus { border-color:var(--indigo); }
  .btn-primary {
    width:100%; padding:8px; background:var(--indigo); color:#fff;
    border:none; border-radius:6px; cursor:pointer;
    font-size:12px; font-weight:600; font-family:inherit; transition:background .15s;
  }
  .btn-primary:hover { background:var(--indigo-d); }
  .saved { font-size:11px; color:var(--green); text-align:center; }

  /* Footer */
  .footer {
    padding:8px 14px; border-top:1px solid var(--border);
    display:flex; align-items:center; gap:8px; flex-shrink:0;
  }
  .fdot { width:6px; height:6px; border-radius:50%; background:var(--border2); }
  .fdot.on { background:var(--green); }
  .ftext { font-size:10px; color:var(--muted2); }

  .fade { animation:fadeIn .15s ease; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(3px)} to{opacity:1;transform:none} }
</style>
</head>
<body>

<div class="header">
  <div class="logo">
    <svg viewBox="0 0 32 32" fill="none">
      <line x1="5"  y1="16" x2="5"  y2="16" stroke="#3D7BFF" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="10" y1="12" x2="10" y2="20" stroke="#3D7BFF" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="16" y1="7"  x2="16" y2="25" stroke="#3D7BFF" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="22" y1="11" x2="22" y2="21" stroke="#3D7BFF" stroke-width="2.5" stroke-linecap="round"/>
      <line x1="27" y1="14" x2="27" y2="18" stroke="#3D7BFF" stroke-width="2.5" stroke-linecap="round"/>
    </svg>
  </div>
  <span class="header-title">MeetBuddy</span>
  <div class="spacer"></div>
  <button class="icon-btn" onclick="openDashboard()" title="Open full dashboard">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
      <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
  </button>
</div>

<div class="scroll" id="main">
  <div style="text-align:center;padding:40px;color:#333;font-size:12px;">Loading…</div>
</div>

<div class="footer">
  <div class="fdot" id="fdot"></div>
  <span class="ftext" id="flabel">Connecting…</span>
</div>

<script>
let cfg         = {token:'',api:'http://localhost:8000'};
let status      = {recording:false,elapsed_s:0,size_mb:0,mic:'',monitor:'',meeting_id:null,daemon_up:false};
let meetings    = [];
let meetError   = null;
let recordError = null;
let showSettings = false;
let savedMsg    = false;
// Track last rendered state to avoid unnecessary full re-renders
let lastRecording = null;
let lastDaemonUp  = null;

function fmt(s) {
  return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');
}
function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'})+
    ' · '+d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
}
function statusBadge(s) {
  if (s==='done')       return `<span class="badge badge-green"><span class="dot"></span> Done</span>`;
  if (s==='processing') return `<span class="badge badge-amber"><span class="dot blink"></span> Processing</span>`;
  if (s==='failed')     return `<span class="badge badge-red"><span class="dot"></span> Failed</span>`;
  return `<span class="badge badge-muted">${s||'?'}</span>`;
}
function platLabel(p) {
  return {google_meet:'Google Meet',browser:'Browser',desktop:'Desktop'}[p]||p||'Meeting';
}
function trunc(s,n) { return s&&s.length>n ? s.slice(0,n)+'…' : s; }

async function api(method,...args) {
  try { return await window.pywebview.api[method](...args); }
  catch(e) { return null; }
}

async function poll() {
  const st = await api('get_status');
  if (!st) return;

  const wasRec     = status.recording;
  const prevDaemon = status.daemon_up;
  status = st;

  // Always update footer in-place (cheap, no flicker)
  document.getElementById('fdot').className = 'fdot'+(st.daemon_up?' on':'');
  document.getElementById('flabel').textContent = st.daemon_up
    ? (st.recording ? 'Recording' : 'Ready') : 'Daemon offline';

  // If recording, update timer in-place instead of full re-render
  if (st.recording) {
    const timerEl = document.getElementById('liveTimer');
    const sizeEl  = document.getElementById('liveSize');
    if (timerEl) {
      timerEl.textContent = fmt(st.elapsed_s);
      if (sizeEl) sizeEl.textContent = st.size_mb.toFixed(1)+' MB';
      return; // skip full re-render
    }
  }

  // Full re-render only when recording state or daemon state changes
  const stateChanged = (wasRec !== st.recording) || (prevDaemon !== st.daemon_up);
  if (stateChanged) {
    if (wasRec && !st.recording) {
      recordError = null;
      setTimeout(loadMeetings, 2000);
    }
    render();
  }
}

async function loadMeetings() {
  const r = await api('get_meetings');
  if (!r) return;
  meetError = r.error;
  meetings  = r.items || [];
  // Only re-render the meetings section in-place
  const el = document.getElementById('meetingsSection');
  if (el) el.innerHTML = renderMeetings();
  else render();
}

async function toggleRecord() {
  if (!cfg.token) { showSettings=true; render(); return; }
  if (status.recording) {
    await api('stop_recording');
  } else {
    recordError = null;
    const r = await api('start_recording');
    if (r && !r.ok) {
      const msgs = {
        no_token:      'No token set — open Settings.',
        token_expired: 'Token expired — paste a new one in Settings.',
        api_down:      'Cannot reach API at '+cfg.api,
        daemon_down:   'Capture daemon is not running.',
      };
      recordError = msgs[r.error] || ('Error: '+r.error);
      if (r.error === 'no_token' || r.error === 'token_expired') showSettings = true;
      render();
      return;
    }
  }
  await poll();
}

async function saveSettings() {
  const tok = document.getElementById('iToken').value;
  const url = document.getElementById('iApi').value;
  await api('save_config', tok, url);
  cfg.token=tok; cfg.api=url;
  meetError=null; recordError=null;
  savedMsg=true; render();
  await loadMeetings();
  setTimeout(()=>{ savedMsg=false; render(); }, 2000);
}

function toggleSettings() { showSettings=!showSettings; render(); }
function openMeeting(id)   { api('open_meeting',id); }
function openDashboard()   { api('open_dashboard'); }

function renderMeetings() {
  const errMsgs = {
    token_expired: 'Token expired — paste a new one in Settings.',
    no_token:      'Set your token in Settings to see meetings.',
    api_error:     'Could not reach the API.',
    api_down:      'API is offline.',
  };
  if (meetError) return `<div class="empty"><p style="color:var(--amber)">${errMsgs[meetError]||meetError}</p></div>`;
  if (!meetings.length) return `<div class="empty"><p>No meetings yet</p></div>`;
  return meetings.map(m => `
    <div class="meeting-item" onclick="openMeeting('${m.id}')">
      <div class="meeting-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 00-3-3.87"/>
          <path d="M16 3.13a4 4 0 010 7.75"/>
        </svg>
      </div>
      <div class="meeting-info">
        <div class="meeting-time">${fmtDate(m.created_at||m.started_at)}</div>
        <div class="meeting-plat">${platLabel(m.platform)} &nbsp;${statusBadge(m.status)}</div>
      </div>
      <div class="chevron">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </div>
    </div>`).join('');
}

function render() {
  let h = '';

  if (!cfg.token && !showSettings)
    h += `<div class="banner banner-amber fade">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/>
        <line x1="12" y1="16" x2="12.01" y2="16"/>
      </svg>
      No token — open <strong>Settings</strong> below to connect.
    </div>`;

  if (!status.daemon_up)
    h += `<div class="banner banner-red fade">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/>
        <line x1="9" y1="9" x2="15" y2="15"/>
      </svg>
      Capture daemon offline — restart MeetBuddy Tray.
    </div>`;

  const rec = status.recording;
  h += `<div class="record-card${rec?' active':''} fade">
    <button class="record-btn ${rec?'recording':'idle'}" onclick="toggleRecord()">
      ${rec
        ? `<svg width="26" height="26" viewBox="0 0 24 24" fill="#ef4444"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>`
        : `<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2">
             <rect x="9" y="2" width="6" height="12" rx="3"/>
             <path d="M5 10a7 7 0 0014 0"/>
             <line x1="12" y1="22" x2="12" y2="17"/>
             <line x1="8" y1="22" x2="16" y2="22"/>
           </svg>`
      }
    </button>
    <div class="record-status">
      ${rec
        ? `<div class="timer" id="liveTimer">${fmt(status.elapsed_s)}</div>
           <div class="rec-sub" id="liveSize">${status.size_mb.toFixed(1)} MB</div>`
        : `<div class="rec-label">Not recording</div>
           <div class="rec-sub">Click to start</div>`
      }
    </div>
    ${status.mic||status.monitor ? `
    <div class="devices">
      ${status.mic     ? `<span class="chip">${trunc(status.mic,24)}</span>` : ''}
      ${status.monitor ? `<span class="chip">${trunc(status.monitor,24)}</span>` : ''}
    </div>` : ''}
  </div>`;

  if (recordError)
    h += `<div class="banner banner-red fade" style="font-size:11px">${recordError}</div>`;

  h += `<div class="fade">
    <div class="section-hdr">
      <span class="section-title">Recent meetings</span>
      <button class="text-btn" onclick="loadMeetings()">Refresh</button>
    </div>
    <div id="meetingsSection">${renderMeetings()}</div>
  </div>`;

  h += `<div class="fade">
    <button class="settings-toggle${showSettings?' open':''}" onclick="toggleSettings()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
      </svg>
      Settings
      <svg class="caret" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
    ${showSettings ? `
    <div class="settings-body fade">
      <div>
        <label class="field-label" for="iApi">API URL</label>
        <input class="field-input" id="iApi" value="${cfg.api}">
      </div>
      <div>
        <label class="field-label" for="iToken">Access Token</label>
        <input class="field-input" id="iToken" type="password" value="${cfg.token}" placeholder="Paste from the dashboard">
      </div>
      <button class="btn-primary" onclick="saveSettings()">Save</button>
      ${savedMsg ? `<div class="saved">Saved!</div>` : ''}
    </div>` : ''}
  </div>`;

  document.getElementById('main').innerHTML = h;
}

async function boot() {
  await new Promise(resolve => {
    if (window.pywebview) { resolve(); return; }
    window.addEventListener('pywebviewready', resolve, {once:true});
  });
  cfg = await api('get_config') || cfg;
  await Promise.all([poll(), loadMeetings()]);
  setInterval(poll, 2000);
}

boot();
</script>
</body>
</html>"""


# ── Main tray application ────────────────────────────────────────────────────

class TrayApp:
    def __init__(self):
        self.cfg         = load_config()
        self._proc: subprocess.Popen | None = None
        self._recording  = False
        self._window: webview.Window | None = None
        self._win_visible = False
        self._api        = Api(self)

        self._icon = pystray.Icon(
            "meetbuddy",
            _make_icon(False),
            "MeetBuddy | idle",
            menu=pystray.Menu(
                pystray.MenuItem("Open MeetBuddy", self._on_click, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

        if not CAPTURE_PY.exists():
            print(f"[tray] WARNING: capture.py not found at {CAPTURE_PY}")
        else:
            self._launch_daemon()

        threading.Thread(target=self._poll_loop, daemon=True).start()

    # ── Daemon lifecycle ──────────────────────────────────────────────────────

    def _launch_daemon(self) -> None:
        self._proc = subprocess.Popen(
            [PYTHON, str(CAPTURE_PY), "--daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.2)

    def _ensure_daemon(self) -> None:
        if self._proc and self._proc.poll() is not None:
            self._launch_daemon()

    # ── Tray icon poller ──────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while True:
            time.sleep(2)
            self._ensure_daemon()
            st = _req("status")
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

    # ── Window show / hide ────────────────────────────────────────────────────

    def _on_click(self, icon, item) -> None:
        if self._window is None:
            return  # webview not ready yet
        if self._win_visible:
            self._window.hide()
            self._win_visible = False
        else:
            self._window.show()
            self._win_visible = True

    # ── Quit ──────────────────────────────────────────────────────────────────

    def _quit(self, icon, item) -> None:
        _req("stop", "POST")
        if self._proc:
            self._proc.terminate()
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
        icon.stop()

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> None:
        # Create the window upfront (GTK requires this on the main thread)
        self._window = webview.create_window(
            "MeetBuddy",
            html=HTML,
            js_api=self._api,
            width=380,
            height=580,
            resizable=False,
            background_color="#0c0c0e",
        )

        # Hide window as soon as webview is ready, then hand off to tray clicks
        def _on_webview_start():
            time.sleep(0.3)
            self._window.hide()
            self._win_visible = False

        # pystray runs in its own thread; webview.start() owns the main thread
        self._icon.run_detached()
        webview.start(func=_on_webview_start, debug=False)
        # webview.start() blocks until all windows are destroyed — clean up here
        self._icon.stop()


if __name__ == "__main__":
    TrayApp().run()
