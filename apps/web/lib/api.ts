// Local desktop build: the dashboard is served from the same origin as the
// API, so calls are same-origin and need no token (single-user local mode).
// NEXT_PUBLIC_API_URL can still point elsewhere for dev.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const API = `${BASE}/api/v1`;

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };

  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail ?? "API error");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Meeting {
  id: string;
  user_id: string;
  title: string | null;
  platform: string;
  started_at: string;
  ended_at: string | null;
  duration_secs: number | null;
  status: string;
  audio_url: string | null;
  created_at: string;
  insights: MeetingInsights | null;
}

export interface MeetingInsights {
  summary: string | null;
  action_items: ActionItem[];
  decisions: Decision[];
  topics: Topic[];
  participants: Record<string, unknown>[];
}

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

export interface TranscriptChunk {
  id: string;
  text: string;
  start_time: number;
  end_time: number;
  speaker_label: string | null;
  speaker_name: string | null;
}

export interface QueryResponse {
  answer: string;
  sources: QuerySource[];
}

export interface QuerySource {
  chunk_id: string;
  meeting_id: string;
  text: string;
  start_time: number;
}

export const meetingsApi = {
  list: (status?: string) =>
    apiFetch<Meeting[]>(`/meetings${status ? `?status=${status}` : ""}`),

  get: (id: string) =>
    apiFetch<Meeting>(`/meetings/${id}`),

  transcript: (id: string) =>
    apiFetch<TranscriptChunk[]>(`/meetings/${id}/transcript`),

  audioUrl: (id: string) =>
    apiFetch<{ url: string }>(`/meetings/${id}/audio`),

  delete: (id: string) =>
    apiFetch<void>(`/meetings/${id}`, { method: "DELETE" }),
};

export const queryApi = {
  ask: (q: string, meetingIds: string[] = []) =>
    apiFetch<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify({ q, meeting_ids: meetingIds }),
    }),
};
