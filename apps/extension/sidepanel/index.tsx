import { useEffect, useState } from "react";
import { Mic, MicOff } from "lucide-react";

interface RecordingState {
  meetingId: string;
  status: "recording" | "processing";
}

export default function SidePanel() {
  const [recording, setRecording] = useState<RecordingState | null>(null);

  useEffect(() => {
    chrome.storage.local.get("recordingState", (result) => {
      if (result.recordingState) setRecording(result.recordingState as RecordingState);
    });

    const listener = (changes: Record<string, chrome.storage.StorageChange>) => {
      if ("recordingState" in changes) {
        setRecording(changes.recordingState.newValue ?? null);
      }
    };
    chrome.storage.onChanged.addListener(listener);
    return () => chrome.storage.onChanged.removeListener(listener);
  }, []);

  function stopRecording() {
    chrome.runtime.sendMessage({ type: "STOP_RECORDING" });
  }

  return (
    <div className="p-4 font-sans text-sm">
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
            onClick={stopRecording}
            className="flex items-center gap-2 px-3 py-1.5 bg-red-100 text-red-700 rounded-md text-xs font-medium hover:bg-red-200"
          >
            <MicOff className="w-3.5 h-3.5" />
            Stop recording
          </button>
        </div>
      ) : (
        <div className="text-gray-400 flex items-center gap-2">
          <MicOff className="w-4 h-4" />
          <span>Not recording</span>
        </div>
      )}
    </div>
  );
}
