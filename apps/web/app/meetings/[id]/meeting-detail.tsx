"use client";

import { useQuery } from "@tanstack/react-query";
import { meetingsApi, type Meeting, type TranscriptChunk } from "@/lib/api";
import { formatDuration, formatTime } from "@/lib/utils";
import { format } from "date-fns";
import { CheckSquare, MessageSquare, Lightbulb, Clock } from "lucide-react";
import { useState } from "react";

interface Props {
  meeting: Meeting;
  accessToken: string;
}

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

  const insights = meeting.insights;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1">
          {meeting.title ?? `${meeting.platform} meeting`}
        </h1>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>{format(new Date(meeting.started_at), "MMMM d, yyyy 'at' h:mm a")}</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {formatDuration(meeting.duration_secs)}
          </span>
          <span className="capitalize px-2 py-0.5 bg-muted rounded-full text-xs">{meeting.status}</span>
        </div>
      </div>

      {audioData?.url && (
        <div className="mb-6">
          <audio controls src={audioData.url} className="w-full h-10" />
        </div>
      )}

      {meeting.status === "processing" && (
        <div className="border rounded-lg p-4 bg-muted/50 mb-6 text-sm text-muted-foreground">
          Processing your meeting... This may take a few minutes.
        </div>
      )}

      <div className="flex gap-1 border-b mb-6">
        {(["summary", "transcript"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px capitalize transition-colors ${
              activeTab === tab
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "summary" && insights && (
        <div className="space-y-6">
          {insights.summary && (
            <section>
              <h2 className="font-semibold mb-2 flex items-center gap-2">
                <MessageSquare className="w-4 h-4" /> Summary
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">{insights.summary}</p>
            </section>
          )}

          {insights.action_items.length > 0 && (
            <section>
              <h2 className="font-semibold mb-3 flex items-center gap-2">
                <CheckSquare className="w-4 h-4" /> Action Items
              </h2>
              <ul className="space-y-2">
                {insights.action_items.map((item, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm p-3 border rounded-md">
                    <CheckSquare className="w-4 h-4 mt-0.5 text-muted-foreground flex-shrink-0" />
                    <div>
                      <p>{item.text}</p>
                      {(item.owner || item.due_date) && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {item.owner && <span>Owner: {item.owner}</span>}
                          {item.owner && item.due_date && <span> · </span>}
                          {item.due_date && <span>Due: {item.due_date}</span>}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {insights.decisions.length > 0 && (
            <section>
              <h2 className="font-semibold mb-3 flex items-center gap-2">
                <Lightbulb className="w-4 h-4" /> Decisions
              </h2>
              <ul className="space-y-2">
                {insights.decisions.map((d, i) => (
                  <li key={i} className="text-sm p-3 border rounded-md">
                    <p className="font-medium">{d.text}</p>
                    {d.context && <p className="text-muted-foreground mt-1">{d.context}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {insights.topics.length > 0 && (
            <section>
              <h2 className="font-semibold mb-3">Topics Discussed</h2>
              <div className="flex flex-wrap gap-2">
                {insights.topics.map((t, i) => (
                  <span key={i} className="px-3 py-1 bg-secondary text-secondary-foreground rounded-full text-xs">
                    {t.name}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {activeTab === "summary" && !insights && meeting.status === "done" && (
        <p className="text-muted-foreground text-sm">No insights available for this meeting.</p>
      )}

      {activeTab === "transcript" && (
        <div className="space-y-2">
          {!transcript && <p className="text-muted-foreground text-sm">Loading transcript...</p>}
          {transcript?.map((chunk) => (
            <TranscriptLine key={chunk.id} chunk={chunk} />
          ))}
          {transcript?.length === 0 && meeting.status === "recording" && (
            <p className="text-muted-foreground text-sm">Transcript will appear once the recording is processed.</p>
          )}
          {transcript?.length === 0 && meeting.status !== "recording" && (
            <p className="text-muted-foreground text-sm">No transcript available.</p>
          )}
        </div>
      )}
    </div>
  );
}

function TranscriptLine({ chunk }: { chunk: TranscriptChunk }) {
  return (
    <div className="flex gap-3 text-sm py-2 border-b last:border-0">
      <span className="text-xs text-muted-foreground w-12 flex-shrink-0 pt-0.5">
        {formatTime(chunk.start_time)}
      </span>
      <div>
        {chunk.speaker_name && (
          <span className="font-medium text-xs text-primary block mb-0.5">{chunk.speaker_name}</span>
        )}
        <p className="leading-relaxed">{chunk.text}</p>
      </div>
    </div>
  );
}
