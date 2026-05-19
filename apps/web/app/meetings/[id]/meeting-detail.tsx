"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingsApi, type Meeting, type TranscriptChunk } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/utils";
import { format } from "date-fns";
import { CheckSquare, MessageSquare, Lightbulb, Clock } from "lucide-react";
import { useState } from "react";

interface Props { meeting: Meeting; accessToken: string }

const STATUS: Record<string, { color: string; label: string }> = {
  done:       { color: "#22c55e", label: "Done" },
  processing: { color: "#f59e0b", label: "Processing" },
  recording:  { color: "#6366f1", label: "Recording" },
  failed:     { color: "#ef4444", label: "Failed" },
};

export function MeetingDetail({ meeting, accessToken }: Props) {
  const [activeTab, setActiveTab] = useState<"summary" | "transcript">("summary");

  const { data: transcript } = useQuery({
    queryKey: ["transcript", meeting.id],
    queryFn: () => meetingsApi.transcript(accessToken, meeting.id),
    enabled: activeTab === "transcript",
  });

  const { data: audioData } = useQuery({
    queryKey: ["audio", meeting.id],
    queryFn: () => meetingsApi.audioUrl(accessToken, meeting.id),
    enabled: !!meeting.audio_url,
    retry: false,
  });

  const status = STATUS[meeting.status] ?? { color: "#737373", label: meeting.status };
  const insights = meeting.insights;

  return (
    <div className="animate-fade-in-up">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start gap-3 mb-2">
          <h1 className="text-xl font-semibold text-foreground tracking-tight flex-1 leading-snug">
            {meeting.title ?? `${meeting.platform} meeting`}
          </h1>
          <span
            className="text-[11px] font-medium px-2 py-0.5 rounded-full flex-shrink-0 mt-1"
            style={{ color: status.color, background: `${status.color}18`, border: `1px solid ${status.color}30` }}
          >
            {status.label}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{format(new Date(meeting.started_at), "MMMM d, yyyy 'at' h:mm a")}</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(meeting.duration_secs)}
          </span>
        </div>
      </div>

      {/* Audio */}
      {audioData?.url && (
        <div className="surface p-3 mb-5">
          <audio controls src={audioData.url} className="w-full h-8" />
        </div>
      )}

      {/* Processing notice */}
      {meeting.status === "processing" && (
        <div
          className="mb-5 px-4 py-3 rounded text-xs flex items-center gap-2 animate-blink"
          style={{ background: "hsl(40 90% 55% / 0.08)", border: "1px solid hsl(40 90% 55% / 0.2)", color: "#f59e0b" }}
        >
          <span className="status-dot flex-shrink-0" style={{ background: "#f59e0b" }} />
          Processing your meeting — this may take a few minutes.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-0 border-b border-border mb-5">
        {(["summary", "transcript"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className="text-xs font-medium px-4 py-2.5 capitalize border-b-2 -mb-px transition-colors"
            style={
              activeTab === tab
                ? { borderColor: "hsl(var(--primary))", color: "hsl(var(--foreground))" }
                : { borderColor: "transparent", color: "hsl(var(--muted-foreground))" }
            }
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Summary */}
      {activeTab === "summary" && insights && (
        <div className="space-y-5 animate-fade-in">
          {insights.summary && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5" /> Summary
              </h2>
              <p className="text-sm text-foreground/80 leading-relaxed">{insights.summary}</p>
            </section>
          )}

          {insights.action_items.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
                <CheckSquare className="w-3.5 h-3.5" /> Action Items
              </h2>
              <div className="surface divide-y divide-border overflow-hidden">
                {insights.action_items.map((item, i) => (
                  <div key={i} className="px-4 py-3 flex items-start gap-3 animate-fade-in-up" style={{ animationDelay: `${i * 50}ms` }}>
                    <CheckSquare className="w-3.5 h-3.5 mt-0.5 flex-shrink-0 text-primary" />
                    <div>
                      <p className="text-sm text-foreground">{item.text}</p>
                      {(item.owner || item.due_date) && (
                        <p className="text-[11px] text-muted-foreground mt-1">
                          {item.owner && <span>Owner: {item.owner}</span>}
                          {item.owner && item.due_date && " · "}
                          {item.due_date && <span>Due: {item.due_date}</span>}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {insights.decisions.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2 flex items-center gap-1.5">
                <Lightbulb className="w-3.5 h-3.5" /> Decisions
              </h2>
              <div className="surface divide-y divide-border overflow-hidden">
                {insights.decisions.map((d, i) => (
                  <div key={i} className="px-4 py-3 animate-fade-in-up" style={{ animationDelay: `${i * 50}ms` }}>
                    <p className="text-sm font-medium text-foreground">{d.text}</p>
                    {d.context && <p className="text-xs text-muted-foreground mt-1">{d.context}</p>}
                  </div>
                ))}
              </div>
            </section>
          )}

          {insights.topics.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Topics
              </h2>
              <div className="flex flex-wrap gap-1.5">
                {insights.topics.map((t, i) => (
                  <span
                    key={i}
                    className="text-[11px] px-2.5 py-1 rounded-full border border-border text-muted-foreground"
                    style={{ background: "hsl(var(--secondary))" }}
                  >
                    {t.name}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {activeTab === "summary" && !insights && meeting.status === "done" && (
        <p className="text-sm text-muted-foreground animate-fade-in">No insights available for this meeting.</p>
      )}

      {/* Transcript */}
      {activeTab === "transcript" && (
        <div className="animate-fade-in">
          {!transcript && <p className="text-sm text-muted-foreground">Loading transcript…</p>}
          <div className="surface divide-y divide-border overflow-hidden">
            {transcript?.map((chunk) => <TranscriptLine key={chunk.id} chunk={chunk} />)}
          </div>
          {transcript?.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {meeting.status === "recording" ? "Transcript will appear once the recording is processed." : "No transcript available."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function TranscriptLine({ chunk }: { chunk: TranscriptChunk }) {
  return (
    <div className="flex gap-4 px-4 py-3 text-sm">
      <span className="text-[11px] text-muted-foreground/50 w-12 flex-shrink-0 pt-px font-mono">
        {formatTime(chunk.start_time)}
      </span>
      <div>
        {chunk.speaker_name && (
          <span className="text-[11px] font-semibold text-primary block mb-0.5">{chunk.speaker_name}</span>
        )}
        <p className="text-sm text-foreground/75 leading-relaxed">{chunk.text}</p>
      </div>
    </div>
  );
}
