const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API = `${BASE}/api/v1`;

interface FetchOptions extends RequestInit {
  token?: string;
}

async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { token, ...rest } = opts;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(rest.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API}${path}`, { ...rest, headers });
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

export const authApi = {
  register: (email: string, password: string, name?: string) =>
    apiFetch<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    }),

  login: (email: string, password: string) =>
    apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  refresh: (refreshToken: string) =>
    apiFetch<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    }),
};

export const meetingsApi = {
  list: (token: string, status?: string) =>
    apiFetch<Meeting[]>(`/meetings${status ? `?status=${status}` : ""}`, { token }),

  get: (token: string, id: string) =>
    apiFetch<Meeting>(`/meetings/${id}`, { token }),

  transcript: (token: string, id: string) =>
    apiFetch<TranscriptChunk[]>(`/meetings/${id}/transcript`, { token }),

  audioUrl: (token: string, id: string) =>
    apiFetch<{ url: string }>(`/meetings/${id}/audio`, { token }),

  delete: (token: string, id: string) =>
    apiFetch<void>(`/meetings/${id}`, { method: "DELETE", token }),
};

export const queryApi = {
  ask: (token: string, q: string, meetingIds: string[] = []) =>
    apiFetch<QueryResponse>("/query", {
      method: "POST",
      token,
      body: JSON.stringify({ q, meeting_ids: meetingIds }),
    }),
};
