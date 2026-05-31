export const config = {
  matches: ["https://meet.google.com/*"],
}

// ── Mic capture ──────────────────────────────────────────────────────────────

let micRecorder: MediaRecorder | null = null;
let micStream: MediaStream | null = null;
let micSeq = 0;

async function startMic(micDeviceId?: string) {
  try {
    const constraints: MediaTrackConstraints = {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    };
    if (micDeviceId) constraints.deviceId = micDeviceId;

    micStream = await navigator.mediaDevices.getUserMedia({ audio: constraints, video: false });
    micRecorder = new MediaRecorder(micStream, { mimeType: "audio/webm;codecs=opus" });
    micRecorder.ondataavailable = (e) => {
      if (e.data.size === 0) return;
      const reader = new FileReader();
      reader.onloadend = () => {
        const b64 = (reader.result as string).split(",")[1];
        chrome.runtime.sendMessage({ type: "MIC_CHUNK", audio_b64: b64, seq: micSeq++ }).catch(() => {});
      };
      reader.readAsDataURL(e.data);
    };
    micRecorder.start(5_000);
    chrome.runtime.sendMessage({ type: "MIC_STATUS", active: true }).catch(() => {});
  } catch (e) {
    chrome.runtime.sendMessage({ type: "MIC_STATUS", active: false, error: (e as Error).message }).catch(() => {});
  }
}

function stopMic() {
  micRecorder?.stop();
  micStream?.getTracks().forEach((t) => t.stop());
  micRecorder = null;
  micStream = null;
  micSeq = 0;
}

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "START_MIC") startMic(msg.micDeviceId);
  if (msg.type === "STOP_MIC")  stopMic();
});

// ── Participant detection ────────────────────────────────────────────────────

const PARTICIPANT_SELECTOR = "[data-participant-id]";
const DEBOUNCE_MS = 2_000;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;

function extractParticipants(): string[] {
  const tiles = document.querySelectorAll<HTMLElement>(PARTICIPANT_SELECTOR);
  const names: string[] = [];
  tiles.forEach((tile) => {
    const nameEl = tile.querySelector("[data-self-name], .zWGUib, [jsname='r4nke']");
    if (nameEl?.textContent?.trim()) names.push(nameEl.textContent.trim());
  });
  return [...new Set(names)];
}

const observer = new MutationObserver(() => {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    const names = extractParticipants();
    if (names.length > 0) chrome.runtime.sendMessage({ type: "PARTICIPANT_NAMES", names });
  }, DEBOUNCE_MS);
});
observer.observe(document.body, { childList: true, subtree: true });

// ── Mic mute detection ───────────────────────────────────────────────────────
// Watch for Google Meet's data-is-muted attribute changes on the mic button.
// The message is broadcast to all extension contexts so the offscreen document
// receives it directly without needing a background relay.

let lastMuted: boolean | null = null;

function readMuteState(): boolean | null {
  // data-is-muted is the most reliable signal across Meet versions
  const el = document.querySelector<HTMLElement>("[data-is-muted]");
  if (el) return el.getAttribute("data-is-muted") === "true";
  // Fallback: mic button with aria-pressed (pressed = muted in some builds)
  const btn = document.querySelector<HTMLElement>(
    'button[aria-label*="microphone" i], button[aria-label*="mic" i]'
  );
  if (btn) {
    const pressed = btn.getAttribute("aria-pressed");
    if (pressed !== null) return pressed === "true";
  }
  return null;
}

function sendMuteIfChanged() {
  const muted = readMuteState();
  if (muted !== null && muted !== lastMuted) {
    lastMuted = muted;
    chrome.runtime.sendMessage({ type: "MIC_MUTE_CHANGED", muted });
  }
}

const muteObserver = new MutationObserver(sendMuteIfChanged);
muteObserver.observe(document.body, {
  attributes: true,
  attributeFilter: ["data-is-muted", "aria-pressed"],
  subtree: true,
});

// Poll as a fallback for Meet versions that swap elements instead of mutating attrs
setInterval(sendMuteIfChanged, 2_000);
