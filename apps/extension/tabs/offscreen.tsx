// Offscreen document: tab audio capture only.
// Mic is captured in content.ts (Google Meet tab context) — the only MV3
// context where getUserMedia for the microphone works reliably.

let mediaRecorder: MediaRecorder | null = null;
let tabStream: MediaStream | null = null;
let seq = 0;

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "OFFSCREEN_START") {
    startCapture(msg.streamId)
      .then(() => sendResponse({ ok: true }))
      .catch((e: Error) => sendResponse({ ok: false, error: e?.message }));
    return true;
  }
  if (msg.type === "OFFSCREEN_STOP") {
    stopCapture();
    sendResponse({ ok: true });
  }
});

async function startCapture(streamId: string) {
  tabStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId },
    } as MediaTrackConstraints,
    video: false,
  });

  mediaRecorder = new MediaRecorder(tabStream, { mimeType: "audio/webm;codecs=opus" });
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size === 0) return;
    const reader = new FileReader();
    reader.onloadend = () => {
      const b64 = (reader.result as string).split(",")[1];
      chrome.runtime.sendMessage({ type: "OFFSCREEN_CHUNK", audio_b64: b64, seq: seq++, source: "tab" }).catch(() => {});
    };
    reader.readAsDataURL(e.data);
  };
  mediaRecorder.start(5_000);
}

function stopCapture() {
  mediaRecorder?.stop();
  tabStream?.getTracks().forEach((t) => t.stop());
  mediaRecorder = null;
  tabStream = null;
  seq = 0;
}

export default function Offscreen() { return null; }
