import "../style.css"
import { useEffect, useState } from "react";
import { Check, ExternalLink, Mic, MicOff } from "lucide-react";

const API_URL_KEY = "apiUrl";
const TOKEN_KEY   = "accessToken";

export default function Popup() {
  const [apiUrl, setApiUrl]     = useState("http://localhost:8000");
  const [token, setToken]       = useState("");
  const [saved, setSaved]       = useState(false);
  const [micGranted, setMicGranted] = useState<boolean | null>(null);

  useEffect(() => {
    chrome.storage.local.get([API_URL_KEY, TOKEN_KEY], (result) => {
      if (result[API_URL_KEY]) setApiUrl(result[API_URL_KEY] as string);
      if (result[TOKEN_KEY])   setToken(result[TOKEN_KEY] as string);
    });
    navigator.mediaDevices
      .getUserMedia({ audio: true, video: false })
      .then((s) => { s.getTracks().forEach((t) => t.stop()); setMicGranted(true); })
      .catch(() => setMicGranted(false));
  }, []);

  function save() {
    chrome.storage.local.set({ [API_URL_KEY]: apiUrl, [TOKEN_KEY]: token }, () => {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    });
  }

  return (
    <div style={{ width: 300, background: "#0c0c0e", color: "#ededed" }}>

      {/* Header */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid #1e1e20", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 20, height: 20, borderRadius: 4, background: "#6366f1", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
            <rect x="6" y="4" width="4" height="16" rx="1" fill="white" />
            <rect x="14" y="4" width="4" height="16" rx="1" fill="white" />
          </svg>
        </div>
        <span style={{ fontWeight: 600, fontSize: 13 }}>MeetBuddy</span>
        <span style={{ marginLeft: "auto", fontSize: 10, color: "#555" }}>Settings</span>
      </div>

      {/* Form */}
      <div style={{ padding: "14px", display: "flex", flexDirection: "column", gap: 11 }}>
        <div>
          <label className="field-label">API URL</label>
          <input className="ext-input" value={apiUrl} onChange={(e) => setApiUrl(e.target.value)} />
        </div>

        <div>
          <label className="field-label">
            Access Token &nbsp;
            <a
              href="http://localhost:3000/meetings"
              target="_blank"
              rel="noreferrer"
              style={{ color: "#6366f1", fontSize: 10, fontWeight: 500, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 2 }}
            >
              Get token <ExternalLink style={{ width: 9, height: 9 }} />
            </a>
          </label>
          <input
            type="password"
            className="ext-input"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste your API token"
          />
        </div>

        <button className="btn-primary" onClick={save}>
          {saved ? <><Check style={{ width: 12, height: 12 }} /> Saved</> : "Save settings"}
        </button>

        {/* Mic badge */}
        <div style={{
          display: "flex", alignItems: "center", gap: 7,
          padding: "7px 10px", borderRadius: 5, fontSize: 11,
          background: micGranted === true ? "rgba(34,197,94,0.07)" : micGranted === false ? "rgba(239,68,68,0.07)" : "rgba(255,255,255,0.03)",
          border: `1px solid ${micGranted === true ? "rgba(34,197,94,0.2)" : micGranted === false ? "rgba(239,68,68,0.2)" : "#1e1e20"}`,
          color: micGranted === true ? "#22c55e" : micGranted === false ? "#ef4444" : "#555",
        }}>
          {micGranted === false
            ? <MicOff style={{ width: 12, height: 12, flexShrink: 0 }} />
            : <Mic style={{ width: 12, height: 12, flexShrink: 0 }} />}
          {micGranted === true ? "Microphone granted" : micGranted === false ? "Microphone denied — click Allow" : "Checking microphone…"}
        </div>
      </div>
    </div>
  );
}
