import "./style.css"
import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, AlertCircle, Settings, ChevronDown, ChevronUp, Check, ExternalLink } from "lucide-react";

type RecordingError = "no_token" | "api_error" | "ws_error" | "capture_failed";

const ERROR_MESSAGES: Record<RecordingError, string> = {
  no_token:       "No access token set. Open Settings to add one.",
  api_error:      "Could not reach the MeetBuddy server.",
  ws_error:       "Lost connection to the server.",
  capture_failed: "Could not capture tab audio.",
};

const CHUNK_MS   = 5_000;
const DEFAULT_API = "http://localhost:8000";
const WAVE_DELAYS = [0, 140, 70, 210, 105];

export default function SidePanel() {
  const [recording, setRecording]       = useState(false);
  const [meetingId, setMeetingId]       = useState<string | null>(null);
  const [onMeet, setOnMeet]             = useState(false);
  const [error, setError]               = useState<RecordingError | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [apiUrl, setApiUrl]             = useState(DEFAULT_API);
  const [token, setToken]               = useState("");
  const [saved, setSaved]               = useState(false);
  const [audioDevices, setAudioDevices] = useState<{ deviceId: string; label: string }[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");

  const wsRef       = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioElRef  = useRef<HTMLAudioElement | null>(null);
  const chunksRef   = useRef<Blob[]>([]);
  const seqRef      = useRef(0);
  const timerRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const bgPortRef   = useRef<chrome.runtime.Port | null>(null);
  const micPortRef  = useRef<chrome.runtime.Port | null>(null);

  useEffect(() => {
    chrome.storage.local.get(["accessToken", "apiUrl", "meetTabReady", "audioDeviceId"], (s) => {
      if (s.accessToken)   setToken(s.accessToken as string);
      if (s.apiUrl)        setApiUrl(s.apiUrl as string);
      if (s.audioDeviceId) setSelectedDeviceId(s.audioDeviceId as string);
      setOnMeet(!!s.meetTabReady);
    });

    const port = chrome.runtime.connect({ name: "sidepanel" });
    bgPortRef.current = port;
    port.onMessage.addListener((msg: { type: string; audio_b64?: string; seq?: number }) => {
      if (msg.type === "MIC_CHUNK" && msg.audio_b64 && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "chunk", source: "mic", audio_b64: msg.audio_b64, seq: msg.seq }));
      }
    });

    chrome.runtime.sendMessage({ type: "GET_PENDING_CAPTURE" }, (resp) => {
      if (resp?.streamId) startRecording(resp.streamId);
    });

    const storageListener = (changes: Record<string, chrome.storage.StorageChange>) => {
      if ("meetTabReady" in changes) setOnMeet(!!changes.meetTabReady.newValue);
    };
    const msgListener = (msg: { type: string; streamId?: string }) => {
      if (msg.type === "CAPTURE_READY" && msg.streamId) startRecording(msg.streamId);
    };

    chrome.storage.onChanged.addListener(storageListener);
    chrome.runtime.onMessage.addListener(msgListener);
    return () => {
      chrome.storage.onChanged.removeListener(storageListener);
      chrome.runtime.onMessage.removeListener(msgListener);
      port.disconnect();
    };
  }, []);

  function flushChunk() {
    if (!chunksRef.current.length || wsRef.current?.readyState !== WebSocket.OPEN) return;
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];
    const seq = seqRef.current++;
    const reader = new FileReader();
    reader.onloadend = () => {
      const b64 = (reader.result as string).split(",")[1];
      wsRef.current?.send(JSON.stringify({ type: "chunk", source: "tab", audio_b64: b64, seq }));
    };
    reader.readAsDataURL(blob);
  }

  function cleanup() {
    if (timerRef.current) clearInterval(timerRef.current);
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    audioCtxRef.current?.close();
    audioCtxRef.current = null;
    if (audioElRef.current) {
      audioElRef.current.pause();
      audioElRef.current.srcObject = null;
      audioElRef.current = null;
    }
    micPortRef.current?.disconnect();
    micPortRef.current = null;
    flushChunk();
    wsRef.current?.send(JSON.stringify({ type: "stop" }));
    wsRef.current?.close();
    recorderRef.current = null;
    wsRef.current = null;
    streamRef.current = null;
    chunksRef.current = [];
    seqRef.current = 0;
    chrome.storage.local.remove("recordingState");
    setRecording(false);
    setMeetingId(null);
  }

  async function startRecording(streamId: string) {
    setError(null);
    const stored = await chrome.storage.local.get(["accessToken", "apiUrl"]);
    const tok = (stored.accessToken as string | undefined) ?? token;
    const api = (stored.apiUrl as string | undefined) ?? apiUrl;
    if (!tok) { setError("no_token"); setShowSettings(true); return; }

    let mId: string;
    try {
      const res = await fetch(`${api}/api/v1/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
        body: JSON.stringify({ platform: "google_meet", started_at: new Date().toISOString() }),
      });
      if (!res.ok) { setError("api_error"); return; }
      mId = (await res.json()).id;
    } catch { setError("api_error"); return; }

    let stream: MediaStream;
    try {
      const tabStream = await navigator.mediaDevices.getUserMedia({
        audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } } as MediaTrackConstraints,
        video: false,
      });
      const audioEl = new Audio();
      audioEl.srcObject = tabStream;
      audioEl.play().catch(() => {});
      audioElRef.current = audioEl;
      const ctx = new AudioContext();
      await ctx.resume();
      audioCtxRef.current = ctx;
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(tabStream).connect(dest);
      streamRef.current = new MediaStream([...tabStream.getTracks()]);
      stream = dest.stream;
    } catch { setError("capture_failed"); return; }

    const wsBase = api.replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/api/v1/ws/${mId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      recorderRef.current = recorder;
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      recorder.start();
      timerRef.current = setInterval(flushChunk, CHUNK_MS);
      chrome.storage.local.set({ recordingState: { meetingId: mId, status: "recording" } });
      setMeetingId(mId);
      setRecording(true);

      setTimeout(() => chrome.tabs.query({ url: "https://meet.google.com/*" }, (tabs) => {
        const tab = tabs.find((t) => t.id && t.status === "complete");
        if (!tab?.id) return;
        try {
          const micPort = chrome.tabs.connect(tab.id, { name: "mic-audio" });
          micPortRef.current = micPort;
          micPort.onMessage.addListener((msg: { type: string; audio_b64?: string; seq?: number; mics?: { deviceId: string; label: string }[] }) => {
            if (msg.type === "MIC_CHUNK" && msg.audio_b64 && ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: "chunk", source: "mic", audio_b64: msg.audio_b64, seq: msg.seq }));
            }
            if (msg.type === "DEVICE_LIST" && msg.mics) setAudioDevices(msg.mics);
          });
          micPort.postMessage({ type: "LIST_DEVICES" });
          micPort.postMessage({ type: "START_MIC", deviceId: selectedDeviceId || undefined });
        } catch (e) { console.warn("[MeetBuddy] mic:", e); }
      }), 500);
    };

    ws.onerror = () => { setError("ws_error"); cleanup(); };
    ws.onclose = () => { if (recording) cleanup(); };
  }

  function saveSettings() {
    chrome.storage.local.set({ accessToken: token, apiUrl, audioDeviceId: selectedDeviceId }, () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  const S = { padding: "0", margin: "0" } as const;

  return (
    <div style={{ minHeight: "100vh", background: "#0c0c0e", color: "#ededed", display: "flex", flexDirection: "column" }}>

      {/* Nav */}
      <div style={{ padding: "11px 14px", borderBottom: "1px solid #1e1e20", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 20, height: 20, borderRadius: 4, background: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
            <rect x="6" y="4" width="4" height="16" rx="1" fill="white" />
            <rect x="14" y="4" width="4" height="16" rx="1" fill="white" />
          </svg>
        </div>
        <span style={{ fontWeight: 600, fontSize: 13 }}>MeetBuddy</span>
        <a
          href="http://localhost:3000/meetings"
          target="_blank"
          rel="noreferrer"
          style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#555", textDecoration: "none" }}
        >
          Dashboard <ExternalLink style={{ width: 10, height: 10 }} />
        </a>
      </div>

      {/* Body */}
      <div style={{ flex: 1, padding: "16px 14px" }}>
        {recording ? (
          /* ── Recording ── */
          <div className="animate-fade-in-up" style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 20 }}>
            {/* Waveform */}
            <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 20, marginBottom: 14 }}>
              {WAVE_DELAYS.map((delay, i) => (
                <div key={i} className="wave-bar" style={{ animationDelay: `${delay}ms` }} />
              ))}
            </div>

            {/* Status */}
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 6 }}>
              <div className="blink-dot" style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", flexShrink: 0 }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "#22c55e" }}>Recording</span>
            </div>

            {meetingId && (
              <p style={{ fontSize: 10, color: "#444", fontFamily: "monospace", marginBottom: 18 }}>
                {meetingId.slice(0, 8)}…
              </p>
            )}

            <p style={{ fontSize: 11, color: "#555", textAlign: "center", lineHeight: 1.65, marginBottom: 20, maxWidth: 200 }}>
              Audio is being captured locally and will be processed after the meeting ends.
            </p>

            <button className="btn-danger" onClick={cleanup}>
              <MicOff style={{ width: 12, height: 12 }} />
              Stop recording
            </button>
          </div>
        ) : (
          /* ── Idle ── */
          <div className="animate-fade-in-up">
            {/* Error */}
            {error && (
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: "9px 11px", borderRadius: 6, marginBottom: 12, background: "rgba(245,158,11,0.07)", border: "1px solid rgba(245,158,11,0.2)", color: "#f59e0b", fontSize: 11, lineHeight: 1.55 }}>
                <AlertCircle style={{ width: 12, height: 12, marginTop: 1, flexShrink: 0 }} />
                {ERROR_MESSAGES[error]}
              </div>
            )}

            {/* Status card */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "24px 16px", borderRadius: 8, background: "#111113", border: "1px solid #222224", textAlign: "center" }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: "#1a1a1c", border: "1px solid #262629", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
                <MicOff style={{ width: 16, height: 16, color: "#3a3a3e" }} />
              </div>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#666", marginBottom: 6 }}>Not recording</p>
              {onMeet ? (
                <p style={{ fontSize: 11, color: "#4a4a4e", lineHeight: 1.6, maxWidth: 190 }}>
                  Click the <strong style={{ color: "#666" }}>MeetBuddy icon</strong> in the Chrome toolbar to start.
                </p>
              ) : (
                <p style={{ fontSize: 11, color: "#3e3e42", lineHeight: 1.6 }}>
                  Join a Google Meet to start recording.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Settings */}
      <div style={{ borderTop: "1px solid #1e1e20", padding: "10px 14px" }}>
        <button
          onClick={() => setShowSettings((s) => !s)}
          style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#555", background: "none", border: "none", cursor: "pointer", padding: 0, width: "100%", fontFamily: "inherit" }}
        >
          <Settings style={{ width: 12, height: 12 }} />
          Settings
          <span style={{ marginLeft: "auto" }}>
            {showSettings ? <ChevronUp style={{ width: 11, height: 11 }} /> : <ChevronDown style={{ width: 11, height: 11 }} />}
          </span>
        </button>

        {showSettings && (
          <div className="animate-fade-in-up" style={{ marginTop: 11, display: "flex", flexDirection: "column", gap: 9 }}>
            <div>
              <label className="field-label">API URL</label>
              <input className="ext-input" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} />
            </div>
            <div>
              <label className="field-label">Access Token</label>
              <input type="password" className="ext-input" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste your API token" />
            </div>
            {audioDevices.length > 0 && (
              <div>
                <label className="field-label">Microphone</label>
                <select className="ext-input" value={selectedDeviceId} onChange={(e) => setSelectedDeviceId(e.target.value)}>
                  <option value="">Default microphone</option>
                  {audioDevices.map((d) => (
                    <option key={d.deviceId} value={d.deviceId}>{d.label}</option>
                  ))}
                </select>
              </div>
            )}
            <button className="btn-primary" onClick={saveSettings}>
              {saved ? <><Check style={{ width: 12, height: 12 }} /> Saved</> : "Save"}
            </button>
          </div>
        )}
      </div>

    </div>
  );
}
