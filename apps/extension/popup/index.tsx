import "../style.css"
import { useEffect, useState } from "react";
import { Settings, ExternalLink } from "lucide-react";

const API_URL_KEY = "apiUrl";
const TOKEN_KEY = "accessToken";

export default function Popup() {
  const [apiUrl, setApiUrl] = useState("http://localhost:8000");
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);

  const [micGranted, setMicGranted] = useState<boolean | null>(null);

  useEffect(() => {
    chrome.storage.local.get([API_URL_KEY, TOKEN_KEY], (result) => {
      if (result[API_URL_KEY]) setApiUrl(result[API_URL_KEY] as string);
      if (result[TOKEN_KEY]) setToken(result[TOKEN_KEY] as string);
    });

    // Popup opens via user gesture — best place to grant mic permission once
    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
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
    <div className="w-72 p-4 font-sans text-sm">
      <div className="flex items-center gap-2 mb-4">
        <span className="font-bold">MeetBuddy</span>
        <Settings className="w-4 h-4 text-gray-400 ml-auto" />
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">API URL</label>
          <input
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
            className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">
            Access Token
            <a
              href={`${apiUrl}/login`}
              target="_blank"
              rel="noreferrer"
              className="ml-1 text-blue-500 inline-flex items-center gap-0.5"
            >
              Get token <ExternalLink className="w-2.5 h-2.5" />
            </a>
          </label>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste your API token"
            className="w-full border rounded px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <button
          onClick={save}
          className="w-full bg-blue-600 text-white rounded py-1.5 text-xs font-medium hover:bg-blue-700"
        >
          {saved ? "Saved!" : "Save settings"}
        </button>

        <div className={`text-xs px-2 py-1.5 rounded ${micGranted === true ? "bg-green-50 text-green-700" : micGranted === false ? "bg-red-50 text-red-700" : "bg-gray-50 text-gray-500"}`}>
          {micGranted === true ? "✓ Microphone access granted" : micGranted === false ? "✗ Microphone access denied — click Allow when Chrome prompts" : "Checking microphone..."}
        </div>
      </div>
    </div>
  );
}
