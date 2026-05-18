import "./style.css"
import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, AlertCircle, Settings, ChevronDown, ChevronUp } from "lucide-react";

type RecordingError = "no_token" | "api_error" | "ws_error" | "capture_failed";

const ERROR_MESSAGES: Record<RecordingError, string> = {
  no_token: "No access token set — expand Settings below to add one.",
  api_error: "Could not reach the MeetBuddy server.",
  ws_error: "Lost connection to the server.",
  capture_failed: "Could not capture tab audio.",
};

const CHUNK_MS = 5_000;
const DEFAULT_API = "http://localhost:8000";

export default function SidePanel() {
  const [recording, setRecording] = useState(false);
  const [meetingId, setMeetingId] = useState<string | null>(null);
  const [onMeet, setOnMeet] = useState(false);
  const [error, setError] = useState<RecordingError | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [apiUrl, setApiUrl] = useState(DEFAULT_API);
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);
  const [audioDevices, setAudioDevices] = useState<{ deviceId: string; label: string }[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const seqRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bgPortRef = useRef<chrome.runtime.Port | null>(null);
  const micPortRef = useRef<chrome.runtime.Port | null>(null);

  // Load settings and detect Meet tab on mount
  useEffect(() => {
    chrome.storage.local.get(["accessToken", "apiUrl", "meetTabReady", "audioDeviceId"], (s) => {
      if (s.accessToken) setToken(s.accessToken as string);
      if (s.apiUrl) setApiUrl(s.apiUrl as string);
      if (s.audioDeviceId) setSelectedDeviceId(s.audioDeviceId as string);
      setOnMeet(!!s.meetTabReady);
    });


    // Long-lived port so background can push mic chunks forwarded from content script
    const port = chrome.runtime.connect({ name: "sidepanel" });
    bgPortRef.current = port;
    port.onMessage.addListener((msg: { type: string; audio_b64?: string; seq?: number }) => {
      if (msg.type === "MIC_CHUNK" && msg.audio_b64 && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "chunk", source: "mic", audio_b64: msg.audio_b64, seq: msg.seq }));
      }
    });

    // Poll for stream ID captured during the action click
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

    if (!tok) {
      setError("no_token");
      setShowSettings(true);
      return;
    }

    let mId: string;
    try {
      const res = await fetch(`${api}/api/v1/meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
        body: JSON.stringify({ platform: "google_meet", started_at: new Date().toISOString() }),
      });
      if (!res.ok) {
        console.error("[MeetBuddy] createMeeting:", res.status, await res.text());
        setError("api_error");
        return;
      }
      mId = (await res.json()).id;
    } catch (e) {
      console.error("[MeetBuddy] createMeeting network error:", e);
      setError("api_error");
      return;
    }

    // Tab audio capture (remote participants)
    let stream: MediaStream;
    try {
      const tabStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId },
        } as MediaTrackConstraints,
        video: false,
      });

      // Play tab audio through <audio> element so user can still hear the meeting
      const audioEl = new Audio();
      audioEl.srcObject = tabStream;
      audioEl.play().catch(() => {});
      audioElRef.current = audioEl;

      // Mix tab + mic into one stream via AudioContext → one MediaRecorder → clean audio file
      const ctx = new AudioContext();
      await ctx.resume();
      audioCtxRef.current = ctx;
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(tabStream).connect(dest);

      streamRef.current = new MediaStream([...tabStream.getTracks()]);

      stream = dest.stream;
    } catch (e: any) {
      console.error("[MeetBuddy] getUserMedia:", e?.name, e?.message);
      setError("capture_failed");
      return;
    }

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

      // Connect to content script for mic capture — small delay lets the freshly injected script register
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
        } catch (e) {
          console.warn("[MeetBuddy] could not connect to content script for mic:", e);
        }
      }), 500);
    };

    ws.onerror = () => { setError("ws_error"); cleanup(); };
    ws.onclose = () => { if (recording) cleanup(); };
  }

  function saveSettings() {
    chrome.storage.local.set({ accessToken: token, apiUrl: apiUrl, audioDeviceId: selectedDeviceId }, () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div className="p-4 font-sans text-sm min-h-screen flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-bold">MeetBuddy</span>
      </div>


      {recording ? (
        <div>
          <div className="flex items-center gap-2 text-green-600 mb-3">
            <Mic className="w-4 h-4 animate-pulse" />
            <span className="font-medium">Recording...</span>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Audio is being captured locally and will be processed after the meeting.
          </p>
          <button
            onClick={cleanup}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-100 text-red-700 rounded-md text-xs font-medium hover:bg-red-200"
          >
            <MicOff className="w-3.5 h-3.5" />
            Stop recording
          </button>
        </div>
      ) : (
        <div>
          <div className="flex items-center gap-2 text-gray-400 mb-4">
            <MicOff className="w-4 h-4" />
            <span>Not recording</span>
          </div>

          {error && (
            <div className="flex items-start gap-2 text-amber-700 bg-amber-50 rounded-md p-2.5 mb-3 text-xs">
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
              <span>{ERROR_MESSAGES[error]}</span>
            </div>
          )}

          {onMeet && !error && (
            <p className="text-xs text-blue-600 bg-blue-50 rounded-md p-2.5 mb-3">
              Click the <strong>MeetBuddy extension icon</strong> in the toolbar to start recording.
            </p>
          )}

          {!onMeet && (
            <p className="text-xs text-gray-400">Join a Google Meet to start recording.</p>
          )}
        </div>
      )}

      {/* Settings */}
      <div className="mt-auto pt-4 border-t border-gray-100">
        <button
          onClick={() => setShowSettings((s) => !s)}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700"
        >
          <Settings className="w-3.5 h-3.5" />
          Settings
          {showSettings ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>

        {showSettings && (
          <div className="mt-3 space-y-2">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">API URL</label>
              <input
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Access Token</label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Paste your API token"
                className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            {audioDevices.length > 0 && (
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Microphone</label>
                <select
                  value={selectedDeviceId}
                  onChange={(e) => setSelectedDeviceId(e.target.value)}
                  className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
                >
                  <option value="">Default microphone</option>
                  {audioDevices.map((d) => (
                    <option key={d.deviceId} value={d.deviceId}>{d.label}</option>
                  ))}
                </select>
              </div>
            )}
            <button
              onClick={saveSettings}
              className="w-full bg-blue-600 text-white rounded py-1.5 text-xs font-medium hover:bg-blue-700"
            >
              {saved ? "Saved!" : "Save"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
