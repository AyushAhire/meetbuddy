#!/usr/bin/env python3
"""
MeetBuddy Desktop Capture — PipeWire + Python
Records mic + all speaker output, mixes, and uploads to MeetBuddy.

Usage:
  python3 capture.py --token <jwt>    one-shot recording
  python3 capture.py --daemon         background daemon (controlled from web UI)
  python3 capture.py --list           show audio devices

Token: http://localhost:3000/meetings → Copy token button.
"""

import argparse
import array
import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import httpx


DAEMON_PORT   = 7779
RATE          = 16_000
CHANNELS      = 1
WIDTH         = 2           # s16le
SIZE_LIMIT_MB = 28          # ~15 min of 16 kHz mono WAV; API compresses to FLAC before Groq
BT_RESCAN_S   = 5           # re-scan for new BT sinks every N seconds


# ─── PipeWire helpers ─────────────────────────────────────────────────────────

def _wpctl(target: str, field: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["wpctl", "inspect", target], stderr=subprocess.DEVNULL, text=True
        )
        for line in out.splitlines():
            if f"{field} = " in line:
                return line.split("=")[1].strip().strip('"')
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return None


def pw_list_nodes() -> list[dict]:
    try:
        out = subprocess.check_output(
            ["pw-cli", "list-objects", "Node"], stderr=subprocess.DEVNULL, text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    nodes, cur = [], {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("id "):
            if cur.get("media.class"): nodes.append(cur)
            cur = {"id": line.split()[1].rstrip(",")}
        for key in ("node.name", "node.description", "media.class"):
            if f"{key} = " in line:
                cur[key] = line.split(f"{key} = ")[1].strip().strip('"')
    if cur.get("media.class"): nodes.append(cur)
    return [n for n in nodes if "Audio" in n.get("media.class", "")]


def detect_defaults() -> tuple[str, str, str, str]:
    """Return (mic_node, mic_desc, sink_node, sink_desc) for the current OS defaults."""
    mic_node  = _wpctl("@DEFAULT_AUDIO_SOURCE@", "node.name")  or ""
    mic_desc  = _wpctl("@DEFAULT_AUDIO_SOURCE@", "node.description") or mic_node
    sink_node = _wpctl("@DEFAULT_AUDIO_SINK@",   "node.name")  or ""
    sink_desc = _wpctl("@DEFAULT_AUDIO_SINK@",   "node.description") or sink_node
    return mic_node, mic_desc, sink_node, sink_desc


def all_bt_sinks(nodes: list[dict]) -> list[dict]:
    """All Bluetooth output sinks — covers both A2DP and HFP profile nodes."""
    return [
        n for n in nodes
        if n.get("media.class") == "Audio/Sink"
        and "bluez" in n.get("node.name", "")
    ]


# ─── PCM mixing ───────────────────────────────────────────────────────────────

def mix_s16le(a: bytes, b: bytes) -> bytes:
    if not a: return b
    if not b: return a
    la, lb = len(a), len(b)
    if la < lb: a += b"\x00" * (lb - la)
    elif lb < la: b += b"\x00" * (la - lb)
    arr_a = array.array("h", a)
    arr_b = array.array("h", b)
    return bytes(array.array("h", (
        max(-32768, min(32767, x + y)) for x, y in zip(arr_a, arr_b)
    )))


# ─── API helpers ──────────────────────────────────────────────────────────────

def api_create_meeting(base: str, token: str) -> str:
    r = httpx.post(
        f"{base}/api/v1/meetings",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"platform": "desktop", "started_at": datetime.now(timezone.utc).isoformat()},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["id"]


def api_upload_audio(base: str, token: str, meeting_id: str, wav_path: Path) -> None:
    with open(wav_path, "rb") as f:
        r = httpx.post(
            f"{base}/api/v1/upload/audio?meeting_id={meeting_id}",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("recording.wav", f, "audio/wav")},
            timeout=120,
        )
    r.raise_for_status()


def api_complete(base: str, token: str, meeting_id: str) -> None:
    httpx.post(
        f"{base}/api/v1/upload/complete",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"meeting_id": meeting_id},
        timeout=10,
    ).raise_for_status()


def api_poll_status(base: str, token: str, meeting_id: str) -> str:
    r = httpx.get(
        f"{base}/api/v1/meetings/{meeting_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("status", "unknown")


# ─── pw-record coroutine ──────────────────────────────────────────────────────

async def record_node(node: str, q: asyncio.Queue, stop: asyncio.Event,
                      is_monitor: bool = False) -> None:
    """
    Capture from a PipeWire node into q.
    is_monitor=True sets stream.capture.sink=true so WirePlumber wires this
    capture stream to the sink's monitor ports. Without this, BT sinks (HFP and
    A2DP) silently produce no audio even though their monitor ports exist.
    """
    cmd = ["pw-record", "--target", node]
    if is_monitor:
        cmd += ["-P", "stream.capture.sink=true"]
    cmd += ["--format", "s16", "--rate", str(RATE), "--channels", str(CHANNELS), "-"]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    READ = RATE * WIDTH * CHANNELS // 5   # ~200 ms
    try:
        while not stop.is_set():
            chunk = await proc.stdout.read(READ)
            if not chunk: break
            await q.put(chunk)
    finally:
        try: proc.terminate(); await proc.wait()
        except Exception: pass


# ─── Core recording loop ──────────────────────────────────────────────────────

async def do_record(
    mic: str,
    initial_sinks: list[str],
    out: Path,
    stop: asyncio.Event,
    status_cb=None,
) -> int:
    """
    Record mic + all sink monitors simultaneously.
    Re-scans for new BT sinks every BT_RESCAN_S seconds so HFP profile
    switches mid-call are automatically captured.
    """
    mic_q  = asyncio.Queue(maxsize=50)
    mon_qs : dict[str, asyncio.Queue]  = {}
    mon_ts : dict[str, asyncio.Task]   = {}

    async def _add_sink(name: str) -> None:
        if name in mon_qs: return
        q = asyncio.Queue(maxsize=50)
        mon_qs[name] = q
        mon_ts[name] = asyncio.create_task(record_node(name, q, stop, is_monitor=True))

    for s in initial_sinks:
        await _add_sink(s)

    mic_task   = asyncio.create_task(record_node(mic, mic_q, stop))
    frames     = 0
    t0         = time.monotonic()
    last_scan  = t0

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(WIDTH)
        wf.setframerate(RATE)

        while not stop.is_set():
            await asyncio.sleep(0.1)

            # Periodically add any new BT sinks (HFP appears mid-call)
            if time.monotonic() - last_scan > BT_RESCAN_S:
                for n in all_bt_sinks(pw_list_nodes()):
                    await _add_sink(n["node.name"])
                last_scan = time.monotonic()

            mic_buf = b"".join(mic_q.get_nowait() for _ in range(mic_q.qsize()))

            mon_buf = b""
            for q in mon_qs.values():
                mon_buf = mix_s16le(mon_buf, b"".join(q.get_nowait() for _ in range(q.qsize())))

            if not mic_buf and not mon_buf:
                continue

            mixed = mix_s16le(mic_buf, mon_buf)
            wf.writeframes(mixed)
            frames += len(mixed) // (WIDTH * CHANNELS)

            size_mb = out.stat().st_size / (1024 * 1024)
            if status_cb: status_cb(time.monotonic() - t0, size_mb)
            if size_mb >= SIZE_LIMIT_MB:
                stop.set()

        # flush remainder
        mic_buf = b"".join(mic_q.get_nowait() for _ in range(mic_q.qsize()))
        mon_buf = b""
        for q in mon_qs.values():
            mon_buf = mix_s16le(mon_buf, b"".join(q.get_nowait() for _ in range(q.qsize())))
        if mic_buf or mon_buf:
            wf.writeframes(mix_s16le(mic_buf, mon_buf))

        await asyncio.gather(mic_task, *mon_ts.values(), return_exceptions=True)

    return frames


# ─── Upload + pipeline trigger ────────────────────────────────────────────────

async def upload_and_process(
    api: str, token: str, meeting_id: str, wav_path: Path, verbose: bool = True
) -> None:
    if verbose: print("  Uploading…")
    api_upload_audio(api, token, meeting_id, wav_path)
    if verbose: print("  Triggering pipeline…\n")
    api_complete(api, token, meeting_id)
    if not verbose: return

    last = ""
    for _ in range(120):
        try: st = api_poll_status(api, token, meeting_id)
        except Exception: st = "processing"
        msg = {"processing": "  ⏳ Transcribing…", "done": "  ✓  Done", "failed": "  ✗  Failed"}.get(st, f"  … {st}")
        if msg != last: print(msg); last = msg
        if st in ("done", "failed"): break
        await asyncio.sleep(2)

    web = api.replace(":8000", ":3000")
    print(f"\n  View → {web}/meetings/{meeting_id}\n")


# ─── Device resolution ────────────────────────────────────────────────────────

def resolve_devices(args: argparse.Namespace) -> tuple[str, str, list[str], str]:
    """
    Returns (mic_node, mic_desc, sink_nodes, sinks_desc).
    Always includes the default sink + every BT sink found.
    """
    nodes = pw_list_nodes()
    mic_node, mic_desc, default_sink, default_sink_desc = detect_defaults()

    if args.mic:
        mic_node = args.mic; mic_desc = args.mic

    # Build sink list: default + all BT sinks (deduped)
    bt = [n["node.name"] for n in all_bt_sinks(nodes)]
    sinks = list(dict.fromkeys([default_sink] + bt))  # preserve order, dedup

    if args.monitor:
        sinks = [args.monitor]

    if not mic_node or not sinks:
        print("Could not detect audio devices. Run --list to see what's available.")
        sys.exit(1)

    desc = default_sink_desc
    if len(sinks) > 1:
        extra = len(sinks) - 1
        desc += f" + {extra} BT sink{'s' if extra > 1 else ''}"

    return mic_node, mic_desc, sinks, desc


# ─── Daemon mode ──────────────────────────────────────────────────────────────

class _DS:
    recording = False; meeting_id = None
    elapsed_s = 0.0;   size_mb = 0.0
    mic_desc  = "";     mon_desc = ""
    _stop: asyncio.Event | None = None

    def to_dict(self):
        return dict(recording=self.recording, meeting_id=self.meeting_id,
                    elapsed_s=round(self.elapsed_s), size_mb=round(self.size_mb, 1),
                    mic=self.mic_desc, monitor=self.mon_desc)

_ds    = _DS()
_sq: asyncio.Queue   # (token, api_url) start requests


async def _http(reader, writer):
    try:
        raw = await asyncio.wait_for(reader.read(2048), timeout=3)
    except Exception:
        writer.close(); return

    lines = raw.decode(errors="replace").split("\r\n")
    parts  = lines[0].split(" ") if lines else []
    method = parts[0] if parts else "GET"
    path   = parts[1] if len(parts) > 1 else "/"

    try:
        body = json.loads(raw.decode(errors="replace").split("\r\n\r\n", 1)[1])
    except Exception:
        body = {}

    if method == "OPTIONS":
        writer.write(b"HTTP/1.1 204 No Content\r\nAccess-Control-Allow-Origin: *\r\n"
                     b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                     b"Access-Control-Allow-Headers: Content-Type\r\n\r\n")
        await writer.drain(); writer.close(); return

    code, resp = 200, {}
    if path == "/status":
        resp = _ds.to_dict()
    elif path == "/start" and method == "POST":
        if _ds.recording:
            code, resp = 400, {"error": "already recording"}
        elif not body.get("token"):
            code, resp = 400, {"error": "token required"}
        else:
            await _sq.put((body["token"], body.get("api", "http://localhost:8000")))
            resp = {"ok": True}
    elif path == "/stop" and method == "POST":
        if not _ds.recording or not _ds._stop:
            code, resp = 400, {"error": "not recording"}
        else:
            _ds._stop.set(); resp = {"ok": True}
    else:
        code, resp = 404, {"error": "not found"}

    body_b = json.dumps(resp).encode()
    writer.write(
        f"HTTP/1.1 {code} OK\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body_b)}\r\nAccess-Control-Allow-Origin: *\r\n"
        f"Connection: close\r\n\r\n".encode() + body_b
    )
    await writer.drain(); writer.close()


async def _daemon_loop(initial_mic, initial_sinks, initial_mic_desc, initial_mon_desc):
    global _sq
    _sq = asyncio.Queue()
    _ds.mic_desc = initial_mic_desc
    _ds.mon_desc = initial_mon_desc

    print(f"  Daemon ready → http://localhost:{DAEMON_PORT}")
    print(f"  Mic     : {initial_mic_desc}")
    print(f"  Monitor : {initial_mon_desc}")
    print(f"  Open http://localhost:3000 and click Record.\n")

    while True:
        token, api_url = await _sq.get()
        stop = asyncio.Event()
        _ds._stop = stop

        # Re-detect devices at recording start so BT switches are picked up.
        try:
            import argparse as _ap
            _args = _ap.Namespace(mic=None, monitor=None)
            mic_node, mic_desc, sinks, mon_desc = resolve_devices(_args)
        except SystemExit:
            mic_node, mic_desc, sinks, mon_desc = initial_mic, initial_mic_desc, initial_sinks, initial_mon_desc
        _ds.mic_desc = mic_desc
        _ds.mon_desc = mon_desc

        try: meeting_id = api_create_meeting(api_url, token)
        except Exception as e:
            print(f"  Could not create meeting: {e}"); continue

        _ds.recording = True; _ds.meeting_id = meeting_id
        _ds.elapsed_s = 0;    _ds.size_mb = 0
        print(f"  ● Recording — {meeting_id}  mic={mic_desc}  monitor={mon_desc}")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = Path(tmp.name)

        def _tick(e, s): _ds.elapsed_s = e; _ds.size_mb = s

        try:
            frames = await do_record(mic_node, sinks, wav_path, stop, status_cb=_tick)
            elapsed = frames / RATE
            print(f"  ■ {int(elapsed//60)}m {int(elapsed%60)}s  "
                  f"({wav_path.stat().st_size/(1024*1024):.1f} MB)")
            if frames > 0:
                await upload_and_process(api_url, token, meeting_id, wav_path, verbose=False)
                print(f"  ✓ Processing started")
        finally:
            wav_path.unlink(missing_ok=True)
            _ds.recording = False; _ds.meeting_id = None; _ds._stop = None


async def run_daemon(mic_node, sinks, mic_desc, mon_desc):
    server = await asyncio.start_server(_http, "127.0.0.1", DAEMON_PORT)
    async with server:
        await asyncio.gather(server.serve_forever(),
                             _daemon_loop(mic_node, sinks, mic_desc, mon_desc))


# ─── One-shot mode ────────────────────────────────────────────────────────────

async def run_oneshot(args, mic_node, mic_desc, sinks, mon_desc):
    token = args.token or os.environ.get("MEETBUDDY_TOKEN", "")
    if not token:
        print("Error: --token <jwt> required (or set MEETBUDDY_TOKEN)."); sys.exit(1)

    print(f"\nMeetBuddy Capture")
    print(f"  Mic     : {mic_desc}")
    print(f"  Monitor : {mon_desc}\n")

    try: meeting_id = api_create_meeting(args.api, token)
    except Exception as e:
        print(f"  Could not create meeting: {e}\n  Is the API at {args.api}?"); sys.exit(1)

    print(f"  Meeting : {meeting_id}\n  Recording… Ctrl+C to stop.\n")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT,  lambda: stop.set())
    loop.add_signal_handler(signal.SIGTERM, lambda: stop.set())

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        def _tick(e, s):
            print(f"\r  {int(e//60):02d}:{int(e%60):02d}  {s:.1f} MB", end="", flush=True)

        frames = await do_record(mic_node, sinks, wav_path, stop, status_cb=_tick)
        elapsed = frames / RATE
        print(f"\n\n  Recorded {int(elapsed//60)}m {int(elapsed%60)}s  "
              f"({wav_path.stat().st_size/(1024*1024):.1f} MB)")
        if frames == 0: print("  No audio captured."); return
        await upload_and_process(args.api, token, meeting_id, wav_path)
    finally:
        wav_path.unlink(missing_ok=True)


# ─── CLI ──────────────────────────────────────────────────────────────────────

async def main_async(args):
    if args.list:
        nodes = pw_list_nodes()
        mic_node, mic_desc, sink_node, sink_desc = detect_defaults()
        print(f"\n  Default mic    : {mic_desc}  ({mic_node})")
        print(f"  Default output : {sink_desc}  ({sink_node})")
        bt = all_bt_sinks(nodes)
        if bt:
            print(f"  BT sinks       : {', '.join(n['node.name'] for n in bt)}")
        print(f"\n  {'CLASS':<30} {'NODE NAME':<55} DESCRIPTION")
        print("  " + "─" * 105)
        for n in nodes:
            print(f"  {n.get('media.class',''):<30} {n.get('node.name',''):<55} {n.get('node.description','')}")
        print(); return

    mic_node, mic_desc, sinks, mon_desc = resolve_devices(args)

    if args.daemon:
        await run_daemon(mic_node, sinks, mic_desc, mon_desc)
    else:
        await run_oneshot(args, mic_node, mic_desc, sinks, mon_desc)


def _daemon_ctl(action: str, token: str, api: str) -> None:
    """Send a start/stop/status command to a running daemon."""
    import urllib.request, urllib.error
    url = f"http://127.0.0.1:{DAEMON_PORT}/{action}"
    try:
        if action in ("start", "stop"):
            data = json.dumps({"token": token, "api": api}).encode()
            req  = urllib.request.Request(url, data=data, method="POST",
                                          headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as r:
            body = json.loads(r.read())
        if action == "status":
            if body.get("recording"):
                elapsed = int(body.get("elapsed_s", 0))
                print(f"  Recording  {elapsed//60:02d}:{elapsed%60:02d}  "
                      f"{body.get('size_mb', 0):.1f} MB  [{body.get('meeting_id','?')[:8]}]")
            else:
                print("  Idle (daemon running)")
        else:
            print("  OK")
    except urllib.error.URLError:
        print(f"  Daemon not running — start it with: capture.py --daemon")
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description="MeetBuddy audio capture — PipeWire")
    p.add_argument("--api",     default="http://localhost:8000")
    p.add_argument("--token",   help="JWT token (or MEETBUDDY_TOKEN env var)")
    p.add_argument("--mic",     help="Override mic node name")
    p.add_argument("--monitor", help="Override output sink node name")
    p.add_argument("--daemon",  action="store_true", help=f"Run as daemon on :{DAEMON_PORT}")
    p.add_argument("--list",    action="store_true", help="List devices and exit")
    p.add_argument("--start",   action="store_true", help="Tell daemon to start recording")
    p.add_argument("--stop",    action="store_true", help="Tell daemon to stop recording")
    p.add_argument("--status",  action="store_true", help="Show daemon recording status")
    args = p.parse_args()

    if args.start or args.stop or args.status:
        action = "start" if args.start else "stop" if args.stop else "status"
        tok    = args.token or os.environ.get("MEETBUDDY_TOKEN", "")
        if action == "start" and not tok:
            print("Error: --token <jwt> required to start recording."); sys.exit(1)
        _daemon_ctl(action, tok, args.api)
        return

    asyncio.run(main_async(args))

if __name__ == "__main__":
    main()
