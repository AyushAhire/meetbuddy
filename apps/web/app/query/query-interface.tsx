"use client";

import { useState } from "react";
import { queryApi, type QueryResponse } from "@/lib/api";
import { formatTime } from "@/lib/utils";
import { Search, ExternalLink } from "lucide-react";
import Link from "next/link";

interface Props {
  accessToken: string;
}

export function QueryInterface({ accessToken }: Props) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await queryApi.ask(accessToken, question);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleSubmit} className="flex gap-2 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What did we decide about the product roadmap?"
            className="w-full pl-9 pr-4 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Searching..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-destructive text-sm mb-4">{error}</p>}

      {result && (
        <div className="space-y-6">
          <div className="border rounded-lg p-4">
            <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Answer</h2>
            <p className="text-sm leading-relaxed">{result.answer}</p>
          </div>

          {result.sources.length > 0 && (
            <div>
              <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Sources</h2>
              <div className="space-y-2">
                {result.sources.map((src) => (
                  <div key={src.chunk_id} className="border rounded-md p-3 text-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted-foreground">
                        at {formatTime(src.start_time)}
                      </span>
                      <Link
                        href={`/meetings/${src.meeting_id}`}
                        className="text-xs text-primary hover:underline flex items-center gap-1"
                      >
                        View meeting <ExternalLink className="w-3 h-3" />
                      </Link>
                    </div>
                    <p className="text-muted-foreground">{src.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
