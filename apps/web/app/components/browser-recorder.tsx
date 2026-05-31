"use client";

import { useEffect, useRef, useState } from "react";

type Phase = "idle" | "starting" | "recording" | "stopping";

function fmt(secs: number) {
  return `${Math.floor(secs / 60).toString().padStart(2, "0")}:${(secs % 60).toString().padStart(2, "0")}`;
}

export function BrowserRecorder({ token, apiUrl = "http://localhost:8000" }: { token: string; apiUrl?: string }) {
  const [phase, setPhase]       = useState<Phase>("idle");
  const [elapsed, setElapsed]   = useState(0);
  const [micOk, setMicOk]       = useState<boolean | null>(null);
  const [error, setError]       = useState<string | null>(null);

  const wsRef          = useRef<WebSocket | null>(null);
  const tabRecRef      = useRef<MediaRecorder | null>(null);
  const micRecRef      = useRef<MediaRecorder | null>(null);
  const tabStreamRef   = useRef<MediaStream | null>(null);
  const micStreamRef   = useRef<MediaStream | null>(null);
  const tabSeq         = useRef(0);
  const micSeq         = useRef(0);
  const timerRef       = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { stop(true); }, []);

  async function start() {
    setError(null);
    setPhase("starting");

    // 1. Create meeting
    let meetingId: string;
    try {
      const r = await fetch(`${apiUrl}/api/v1/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ platform: "browser", started_at: new Date().toISOString() }),
      });
      if (!r.ok) throw new Error("API error " + r.status);
      meetingId = (await r.json()).id;
    } catch (e) {
      setError("Could not reach MeetBuddy API — is the server running?");
      setPhase("idle");
      return;
    }

    // 2. Tab audio via screen share — user picks the Meet tab
    let tabStream: MediaStream;
    try {
      tabStream = await (navigator.mediaDevices as any).getDisplayMedia({
        audio: true,
        video: true,   // required by Chrome; video tracks are stopped immediately below
      });
      // Drop video tracks — we only want audio
      tabStream.getVideoTracks().forEach((t) => t.stop());
    } catch (e) {
      setError("Screen share cancelled — please share the Google Meet tab with audio.");
      setPhase("idle");
      return;
    }

    if (tabStream.getAudioTracks().length === 0) {
      setError("No audio track from screen share. Make sure to tick 'Share tab audio' in the picker.");
      tabStream.getTracks().forEach((t) => t.stop());
      setPhase("idle");
      return;
    }

    // 3. Mic
    let micStream: MediaStream | null = null;
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
        video: false,
      });
      setMicOk(true);
    } catch {
      setMicOk(false); // record without mic rather than aborting
    }

    // 4. WebSocket
    const wsBase = apiUrl.replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/api/v1/ws/${meetingId}`);
    const wsOk = await new Promise<boolean>((res) => {
      ws.onopen  = () => res(true);
      ws.onerror = () => res(false);
    });
    if (!wsOk) {
      setError("WebSocket connection failed.");
      tabStream.getTracks().forEach((t) => t.stop());
      micStream?.getTracks().forEach((t) => t.stop());
      setPhase("idle");
      return;
    }
    ws.onclose = () => { if (phase === "recording") stop(); };
    wsRef.current       = ws;
    tabStreamRef.current = tabStream;
    micStreamRef.current = micStream;
    tabSeq.current = 0;
    micSeq.current = 0;

    function makeRecorder(stream: MediaStream, source: "tab" | "mic", seqRef: React.MutableRefObject<number>) {
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      mr.ondataavailable = (e) => {
        if (e.data.size === 0 || ws.readyState !== WebSocket.OPEN) return;
        const reader = new FileReader();
        reader.onloadend = () => {
          const b64 = (reader.result as string).split(",")[1];
          ws.send(JSON.stringify({ type: "chunk", source, audio_b64: b64, seq: seqRef.current++ }));
        };
        reader.readAsDataURL(e.data);
      };
      mr.start(5_000);
      return mr;
    }

    tabRecRef.current = makeRecorder(tabStream, "tab", tabSeq);
    if (micStream) micRecRef.current = makeRecorder(micStream, "mic", micSeq);

    // Stop if the tab share ends (user clicks the browser's "Stop sharing" button)
    tabStream.getAudioTracks()[0].onended = () => stop();

    setElapsed(0);
    setPhase("recording");
    timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
  }

  function stop(silent = false) {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (!silent) setPhase("stopping");

    tabRecRef.current?.stop();
    micRecRef.current?.stop();
    tabStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    tabRecRef.current  = null;
    micRecRef.current  = null;
    tabStreamRef.current = null;
    micStreamRef.current = null;

    // Drain final chunks before sending stop
    setTimeout(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
        wsRef.current.close();
      }
      wsRef.current = null;
      if (!silent) {
        setPhase("idle");
        setMicOk(null);
        setElapsed(0);
        window.dispatchEvent(new Event("meetbuddy:refresh"));
      }
    }, 1_500);
  }

  // ── UI ──────────────────────────────────────────────────────────────────────

  if (phase === "recording") {
    return (
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "#ef4444" }}>
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse inline-block" />
          {fmt(elapsed)}
          {micOk === false && (
            <span title="Mic capture failed — recording meeting audio only" style={{ color: "rgba(255,180,0,0.7)" }}>
              {" "}· mic ⚠
            </span>
          )}
        </div>
        <button
          onClick={() => stop()}
          className="text-xs px-2.5 py-1 rounded font-medium"
          style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", color: "#f87171" }}
        >
          Stop
        </button>
      </div>
    );
  }

  if (phase === "starting" || phase === "stopping") {
    return (
      <span className="text-xs px-2.5 py-1 rounded" style={{ color: "rgba(255,255,255,0.3)" }}>
        {phase === "starting" ? "Starting…" : "Saving…"}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {error && (
        <span title={error} className="text-xs cursor-help" style={{ color: "#f59e0b" }}>⚠</span>
      )}
      <button
        onClick={start}
        className="text-xs px-2.5 py-1 rounded font-medium flex items-center gap-1.5"
        style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.18)", color: "#f87171" }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />
        Record
      </button>
    </div>
  );
}
