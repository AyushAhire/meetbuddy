export const config = {
  matches: ["https://meet.google.com/*"],
}

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

// ── Microphone capture via direct port from sidepanel ────────────────────────
// chrome.tabs.connect (sidepanel → content) bypasses the MV3 service worker,
// which gets killed between chunks and loses the forwarding port.

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "mic-audio") return;

  let micRecorder: MediaRecorder | null = null;
  let micChunks: Blob[] = [];
  let micSeq = 0;

  const deviceId: string | undefined = undefined; // set from first message

  function flush() {
    if (!micChunks.length) return;
    const blob = new Blob(micChunks, { type: "audio/webm" });
    micChunks = [];
    const seq = micSeq++;
    const reader = new FileReader();
    reader.onloadend = () => {
      try {
        port.postMessage({ type: "MIC_CHUNK", audio_b64: (reader.result as string).split(",")[1], seq });
      } catch {}
    };
    reader.readAsDataURL(blob);
  }

  port.onMessage.addListener(async (msg) => {
    if (msg.type === "START_MIC") {
      if (micRecorder) return;
      try {
        const constraints: MediaStreamConstraints = {
          audio: msg.deviceId ? { deviceId: { exact: msg.deviceId } } : true,
          video: false,
        };
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        micRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
        micRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) {
            micChunks.push(e.data);
            flush();
          }
        };
        micRecorder.start(5_000);
        port.postMessage({ type: "MIC_READY" });
      } catch (e: any) {
        port.postMessage({ type: "MIC_ERROR", message: e?.message });
      }
    }

    if (msg.type === "LIST_DEVICES") {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const mics = devices
        .filter((d) => d.kind === "audioinput")
        .map((d) => ({ deviceId: d.deviceId, label: d.label || `Mic ${d.deviceId.slice(0, 6)}` }));
      port.postMessage({ type: "DEVICE_LIST", mics });
    }
  });

  port.onDisconnect.addListener(() => {
    micRecorder?.stream.getTracks().forEach((t) => t.stop());
    micRecorder = null;
  });
});
