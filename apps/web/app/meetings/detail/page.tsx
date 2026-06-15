"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { meetingsApi } from "@/lib/api";
import { MeetingDetail } from "./meeting-detail";

function DetailInner() {
  const id = useSearchParams().get("id") ?? "";

  const { data: meeting, isLoading, error } = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => meetingsApi.get(id),
    enabled: !!id,
    refetchInterval: (q) =>
      (q.state.data?.status === "processing" || q.state.data?.status === "recording") ? 5_000 : false,
  });

  return (
    <div className="min-h-screen">
      <header className="app-nav px-5 h-12 flex items-center gap-3">
        <a
          href="/meetings"
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
            <path d="M15 18l-6-6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Meetings
        </a>
        <span className="text-muted-foreground/40 text-xs">/</span>
        <span className="text-xs text-muted-foreground truncate max-w-[200px] sm:max-w-xs">
          {meeting ? (meeting.title ?? `${meeting.platform} meeting`) : "…"}
        </span>
      </header>

      <main className="max-w-4xl mx-auto px-5 py-8 pb-16">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Could not load this meeting.</p>}
        {meeting && <MeetingDetail meeting={meeting} />}
      </main>
    </div>
  );
}

export default function MeetingDetailPage() {
  return (
    <Suspense fallback={null}>
      <DetailInner />
    </Suspense>
  );
}
