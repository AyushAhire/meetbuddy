"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { meetingsApi, type Meeting } from "@/lib/api";
import { formatDuration } from "@/lib/utils";
import { format } from "date-fns";
import { Calendar, Clock, CheckSquare, Trash2, CheckCheck } from "lucide-react";
import Link from "next/link";

interface Props {
  accessToken: string;
}

const STATUS_COLORS: Record<string, string> = {
  done: "bg-green-100 text-green-800",
  processing: "bg-yellow-100 text-yellow-800",
  recording: "bg-blue-100 text-blue-800",
  failed: "bg-red-100 text-red-800",
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
    mutationFn: (ids: string[]) =>
      Promise.all(ids.map((id) => meetingsApi.delete(accessToken, id))),
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

  function selectAll() {
    setSelected(new Set(meetings?.map((m) => m.id) ?? []));
  }

  function deleteSelected() {
    if (!selected.size) return;
    if (!confirm(`Delete ${selected.size} recording${selected.size > 1 ? "s" : ""}?`)) return;
    deleteMutation.mutate([...selected]);
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 rounded-lg bg-muted animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) return <p className="text-destructive">Failed to load meetings.</p>;

  if (!meetings?.length) {
    return (
      <div className="text-center py-16 text-muted-foreground">
        <p className="text-lg font-medium mb-2">No meetings yet</p>
        <p className="text-sm">Install the browser extension to start capturing meetings.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-4">
        {selecting ? (
          <>
            <button onClick={selectAll} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border rounded hover:bg-accent">
              <CheckCheck className="w-3.5 h-3.5" /> Select all
            </button>
            <button
              onClick={deleteSelected}
              disabled={!selected.size || deleteMutation.isPending}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-40"
            >
              <Trash2 className="w-3.5 h-3.5" />
              {deleteMutation.isPending ? "Deleting…" : `Delete${selected.size ? ` (${selected.size})` : ""}`}
            </button>
            <button onClick={() => { setSelecting(false); setSelected(new Set()); }} className="text-xs px-3 py-1.5 border rounded hover:bg-accent ml-auto">
              Cancel
            </button>
          </>
        ) : (
          <button onClick={() => setSelecting(true)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border rounded hover:bg-accent ml-auto">
            <Trash2 className="w-3.5 h-3.5" /> Select to delete
          </button>
        )}
      </div>

      <div className="space-y-3">
        {meetings.map((m) => (
          <MeetingCard
            key={m.id}
            meeting={m}
            selecting={selecting}
            selected={selected.has(m.id)}
            onToggle={() => toggleSelect(m.id)}
          />
        ))}
      </div>
    </div>
  );
}

function MeetingCard({
  meeting,
  selecting,
  selected,
  onToggle,
}: {
  meeting: Meeting;
  selecting: boolean;
  selected: boolean;
  onToggle: () => void;
}) {
  const statusColor = STATUS_COLORS[meeting.status] ?? "bg-gray-100 text-gray-800";
  const actionItemCount = meeting.insights?.action_items?.length ?? 0;

  const content = (
    <div className={`border rounded-lg p-4 transition-colors ${selecting ? (selected ? "border-blue-500 bg-blue-50" : "hover:bg-accent/50 cursor-pointer") : "hover:bg-accent/50"}`}>
      <div className="flex items-start gap-3">
        {selecting && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            onClick={(e) => e.stopPropagation()}
            className="mt-1 w-4 h-4 accent-blue-600 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium truncate">
              {meeting.title ?? `${meeting.platform} meeting`}
            </h3>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor}`}>
              {meeting.status}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5" />
              {format(new Date(meeting.started_at), "MMM d, yyyy")}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {formatDuration(meeting.duration_secs)}
            </span>
            {actionItemCount > 0 && (
              <span className="flex items-center gap-1">
                <CheckSquare className="w-3.5 h-3.5" />
                {actionItemCount} action item{actionItemCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
          {meeting.insights?.summary && (
            <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{meeting.insights.summary}</p>
          )}
        </div>
      </div>
    </div>
  );

  if (selecting) {
    return <div onClick={onToggle}>{content}</div>;
  }

  return <Link href={`/meetings/${meeting.id}`}>{content}</Link>;
}
