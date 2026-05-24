const MEET_PATTERN = /https:\/\/meet\.google\.com\/.+/;

let pendingCapture: { streamId: string; ts: number } | null = null;
let sidepanelPort: chrome.runtime.Port | null = null;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "sidepanel") {
    sidepanelPort = port;
    port.onDisconnect.addListener(() => { sidepanelPort = null; });
  }
});

function disablePopupForTab(tabId: number) {
  chrome.action.setPopup({ popup: "", tabId });
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url) {
    if (MEET_PATTERN.test(tab.url)) {
      disablePopupForTab(tabId);
      chrome.storage.local.set({ meetTabReady: true });
    }
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab.url && MEET_PATTERN.test(tab.url)) disablePopupForTab(tabId);
  } catch {}
});

chrome.tabs.onRemoved.addListener(async () => {
  const tabs = await chrome.tabs.query({ url: "https://meet.google.com/*" });
  if (tabs.length === 0) chrome.storage.local.set({ meetTabReady: false });
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !tab.url || !MEET_PATTERN.test(tab.url)) return;

  try {
    await chrome.sidePanel.open({ windowId: tab.windowId! });
  } catch (e) {
    console.error("[MeetBuddy] sidePanel.open failed:", e);
  }

  chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id }, (streamId) => {
    if (chrome.runtime.lastError) {
      console.error("[MeetBuddy] getMediaStreamId:", chrome.runtime.lastError.message);
      return;
    }
    pendingCapture = { streamId, ts: Date.now() };
    chrome.runtime.sendMessage({ type: "CAPTURE_READY", streamId }).catch(() => {});
  });
});

// Relay audio chunks from offscreen document → sidepanel port.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_PENDING_CAPTURE") {
    const TTL = 8_000;
    if (pendingCapture && Date.now() - pendingCapture.ts < TTL) {
      sendResponse({ streamId: pendingCapture.streamId });
      pendingCapture = null;
    } else {
      pendingCapture = null;
      sendResponse({ streamId: null });
    }
    return true;
  }

  if (msg.type === "OFFSCREEN_CHUNK") {
    sidepanelPort?.postMessage({ type: "OFFSCREEN_CHUNK", audio_b64: msg.audio_b64, seq: msg.seq });
    return false;
  }

  if (msg.type === "START_OFFSCREEN") {
    handleStartOffscreen(msg).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: e?.message }));
    return true;
  }

  if (msg.type === "STOP_OFFSCREEN") {
    chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP" }).catch(() => {});
    chrome.storage.local.remove("recordingState");
    sendResponse({ ok: true });
    return false;
  }

  if (msg.type === "STOP_RECORDING") {
    chrome.runtime.sendMessage({ type: "OFFSCREEN_STOP" }).catch(() => {});
    chrome.storage.local.remove("recordingState");
    sendResponse({ ok: true });
    return false;
  }
});

async function handleStartOffscreen(msg: { streamId: string; micDeviceId?: string }) {
  const offscreenUrl = chrome.runtime.getURL("tabs/offscreen.html");

  const existing = await chrome.offscreen.hasDocument();
  if (!existing) {
    await chrome.offscreen.createDocument({
      url: offscreenUrl,
      reasons: [
        chrome.offscreen.Reason.USER_MEDIA,
        chrome.offscreen.Reason.AUDIO_PLAYBACK,
      ],
      justification: "Capture and mix tab and microphone audio for meeting recording",
    });
  }

  // Small delay to let the offscreen document's message listener register.
  await new Promise<void>((r) => setTimeout(r, 200));

  await chrome.runtime.sendMessage({
    type: "OFFSCREEN_START",
    streamId: msg.streamId,
    micDeviceId: msg.micDeviceId,
  });
}
