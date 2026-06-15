"use client";

import { useEffect, useState, useCallback } from "react";

const DAEMON = "http://localhost:7779";

interface DaemonStatus {
  recording: boolean;
  meeting_id: string | null;
  elapsed_s: number;
  size_mb: number;
  mic: string;
  monitor: string;
}

function fmt(secs: number) {
  const m = Math.floor(secs / 60).toString().padStart(2, "0");
  const s = (secs % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export function RecordingControl({ token = "local" }: { token?: string }) {
  const [status, setStatus] = useState<DaemonStatus | null>(null);
  const [daemonUp, setDaemonUp] = useState(false);
  const [busy, setBusy] = useState(false);

  const poll = useCallback(async () => {
    try {
      const r = await fetch(`${DAEMON}/status`, { signal: AbortSignal.timeout(1500) });
      if (r.ok) {
        const data: DaemonStatus = await r.json();
        setStatus(data);
        setDaemonUp(true);
      }
    } catch {
      setDaemonUp(false);
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, [poll]);

  // Auto-refresh meetings list when recording stops
  const wasRecording = status?.recording;
  useEffect(() => {
    if (wasRecording === false && daemonUp) {
      // brief delay so the server has time to process
      setTimeout(() => window.dispatchEvent(new Event("meetbuddy:refresh")), 2000);
    }
  }, [wasRecording, daemonUp]);

  async function startRecording() {
    setBusy(true);
    try {
      await fetch(`${DAEMON}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, api: "http://localhost:8000" }),
      });
      await poll();
    } finally {
      setBusy(false);
    }
  }

  async function stopRecording() {
    setBusy(true);
    try {
      await fetch(`${DAEMON}/stop`, { method: "POST" });
      await poll();
    } finally {
      setBusy(false);
    }
  }

  // Daemon not running — show hint
  if (!daemonUp) {
    return (
      <span
        title="Start the capture daemon: python3 apps/capture/capture.py --daemon"
        className="text-xs px-2.5 py-1 rounded border cursor-help hidden sm:inline-flex items-center gap-1.5"
        style={{ color: "rgba(255,255,255,0.2)", borderColor: "rgba(255,255,255,0.07)" }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-current inline-block" />
        Daemon off
      </span>
    );
  }

  if (status?.recording) {
    return (
      <div className="flex items-center gap-2">
        {/* Blinking red dot + timer */}
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "#ef4444" }}>
          <span
            className="w-1.5 h-1.5 rounded-full bg-red-500 animate-blink inline-block"
          />
          {fmt(status.elapsed_s)}
          <span style={{ color: "rgba(255,255,255,0.3)" }}>·</span>
          <span style={{ color: "rgba(255,255,255,0.35)" }}>{status.size_mb} MB</span>
        </div>
        {/* Stop */}
        <button
          onClick={stopRecording}
          disabled={busy}
          className="text-xs px-2.5 py-1 rounded font-medium transition-all"
          style={{
            background: "rgba(239,68,68,0.12)",
            border: "1px solid rgba(239,68,68,0.25)",
            color: "#f87171",
          }}
        >
          Stop
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={startRecording}
      disabled={busy}
      className="text-xs px-2.5 py-1 rounded font-medium transition-all flex items-center gap-1.5"
      style={{
        background: "rgba(239,68,68,0.08)",
        border: "1px solid rgba(239,68,68,0.18)",
        color: "#f87171",
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
      {busy ? "Starting…" : "Record"}
    </button>
  );
}
