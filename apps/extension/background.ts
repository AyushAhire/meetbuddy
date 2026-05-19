const MEET_PATTERN = /https:\/\/meet\.google\.com\/.+/;

// Stream ID obtained during the action-click invocation — valid for ~8 s
let pendingCapture: { streamId: string; ts: number } | null = null;

// Long-lived port from the sidepanel — used to forward mic chunks from content script
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

// Fires only for Meet tabs (where popup is disabled)
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id || !tab.url || !MEET_PATTERN.test(tab.url)) return;

  // Open sidepanel — must be called directly inside a user-gesture handler
  try {
    await chrome.sidePanel.open({ windowId: tab.windowId! });
  } catch (e) {
    console.error("[MeetBuddy] sidePanel.open failed:", e);
  }

  // Get stream ID while the extension is invoked (the only moment tabCapture works)
  chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id }, (streamId) => {
    if (chrome.runtime.lastError) {
      console.error("[MeetBuddy] getMediaStreamId:", chrome.runtime.lastError.message);
      return;
    }
    pendingCapture = { streamId, ts: Date.now() };

    // If sidepanel is already open and listening, notify it immediately
    chrome.runtime.sendMessage({ type: "CAPTURE_READY", streamId }).catch(() => {
      // Sidepanel not open yet — it will poll on mount via GET_PENDING_CAPTURE
    });
  });
});

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

  if (msg.type === "STOP_RECORDING") {
    chrome.storage.local.remove("recordingState");
    sendResponse({ ok: true });
  }

});
