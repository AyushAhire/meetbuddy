export type MeetingPlatform = "google_meet" | "zoom" | "teams" | "unknown";
export type MeetingStatus = "recording" | "processing" | "done" | "failed";
export type EntityType = "person" | "company" | "project" | "topic";

export interface ActionItem {
  text: string;
  owner: string | null;
  due_date: string | null;
}

export interface Decision {
  text: string;
  context: string | null;
}

export interface Topic {
  name: string;
  duration_secs: number;
}

export interface ExtensionMessage {
  type: "PARTICIPANT_NAMES" | "STOP_RECORDING" | "RECORDING_STATUS";
  names?: string[];
  status?: string;
}

export interface WSChunkMessage {
  type: "chunk";
  audio_b64: string;
  seq: number;
}

export interface WSStopMessage {
  type: "stop";
}

export interface WSStatusMessage {
  type: "status";
  message: string;
}

export type WSClientMessage = WSChunkMessage | WSStopMessage;
export type WSServerMessage = WSStatusMessage;
