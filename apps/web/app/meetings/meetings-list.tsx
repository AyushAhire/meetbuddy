"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { meetingsApi, type Meeting } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import { format } from "date-fns";
import { Calendar, Clock, CheckSquare, Trash2, CheckCheck } from "lucide-react";
import Link from "next/link";

interface Props { accessToken: string }

const STATUS: Record<string, { color: string; label: string; pulse?: boolean }> = {
  done:       { color: "#22c55e", label: "Done" },
  processing: { color: "#f59e0b", label: "Processing", pulse: true },
  recording:  { color: "#6366f1", label: "Recording",  pulse: true },
  failed:     { color: "#ef4444", label: "Failed" },
};

export function MeetingsList({ accessToken }: Props) {
  const queryClient = useQueryClient();
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data: meetings, isLoading, error } = useQuery({
    queryKey: ["meetings"],
    queryFn: () => meetingsApi.list(accessToken),
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });

  const deleteMutation = useMutation({
    mutationFn: (ids: string[]) => Promise.all(ids.map((id) => meetingsApi.delete(accessToken, id))),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      setSelected(new Set());
      setSelecting(false);
    },
  });

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function deleteSelected() {
    if (!selected.size) return;
    if (!confirm(`Delete ${selected.size} recording${selected.size > 1 ? "s" : ""}?`)) return;
    deleteMutation.mutate([...selected]);
  }

  if (isLoading) {
    return (
      <div className="space-y-px">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-14 rounded surface animate-pulse" style={{ animationDelay: `${i * 80}ms` }} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-xs text-destructive surface px-4 py-3">
        Failed to load meetings.
      </p>
    );
  }

  if (!meetings?.length) {
    return (
      <div className="surface py-16 text-center animate-fade-in-up">
        <p className="text-sm font-medium text-foreground mb-1">No meetings yet</p>
        <p className="text-xs text-muted-foreground">
          Install the browser extension to start capturing meetings.
        </p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-3">
        {selecting ? (
          <>
            <button onClick={() => setSelected(new Set(meetings.map((m) => m.id)))} className="btn-ghost">
              <CheckCheck className="w-3 h-3" /> All
            </button>
            <button
              onClick={deleteSelected}
              disabled={!selected.size || deleteMutation.isPending}
              className="btn-danger"
            >
              <Trash2 className="w-3 h-3" />
              {deleteMutation.isPending ? "Deleting…" : `Delete${selected.size ? ` (${selected.size})` : ""}`}
            </button>
            <button onClick={() => { setSelecting(false); setSelected(new Set()); }} className="btn-ghost ml-auto">
              Cancel
            </button>
          </>
        ) : (
          <button onClick={() => setSelecting(true)} className="btn-ghost ml-auto">
            <Trash2 className="w-3 h-3" /> Select
          </button>
        )}
      </div>

      {/* List */}
      <div className="surface divide-y divide-border overflow-hidden">
        {meetings.map((m, i) => (
          <MeetingRow
            key={m.id}
            meeting={m}
            selecting={selecting}
            selected={selected.has(m.id)}
            onToggle={() => toggleSelect(m.id)}
            index={i}
          />
        ))}
      </div>
    </div>
  );
}

function MeetingRow({
  meeting, selecting, selected, onToggle, index,
}: {
  meeting: Meeting;
  selecting: boolean;
  selected: boolean;
  onToggle: () => void;
  index: number;
}) {
  const status = STATUS[meeting.status] ?? { color: "#737373", label: meeting.status };
  const actionItemCount = meeting.insights?.action_items?.length ?? 0;

  const row = (
    <div
      className="flex items-center gap-3 px-4 py-3 surface-hover animate-fade-in-up"
      style={{
        animationDelay: `${Math.min(index * 40, 320)}ms`,
        ...(selecting && selected ? { background: "hsl(245 58% 61% / 0.06)" } : {}),
      }}
    >
      {selecting && (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          onClick={(e) => e.stopPropagation()}
          className="w-3.5 h-3.5 flex-shrink-0 accent-primary"
        />
      )}

      {/* Status dot */}
      <span
        className={`status-dot flex-shrink-0 ${status.pulse ? "animate-blink" : ""}`}
        style={{ background: status.color }}
      />

      {/* Title + meta */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate leading-snug">
          {meeting.title ?? `${meeting.platform} meeting`}
        </p>
        <div className="flex items-center gap-3 mt-0.5 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            {format(new Date(meeting.started_at), "MMM d, yyyy")}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatDuration(meeting.duration_secs)}
          </span>
          {actionItemCount > 0 && (
            <span className="flex items-center gap-1" style={{ color: "hsl(245 58% 70%)" }}>
              <CheckSquare className="w-3 h-3" />
              {actionItemCount} action{actionItemCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Status label */}
      <span className="text-[11px] flex-shrink-0" style={{ color: status.color }}>
        {status.label}
      </span>

      {!selecting && (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="flex-shrink-0 text-muted-foreground/40">
          <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </div>
  );

  if (selecting) return <div onClick={onToggle} className="cursor-pointer">{row}</div>;
  return <Link href={`/meetings/${meeting.id}`}>{row}</Link>;
}
