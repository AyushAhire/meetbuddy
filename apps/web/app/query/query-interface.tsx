"use client";

import { useState } from "react";
import { queryApi, type QueryResponse } from "@/lib/api";
import { formatTime } from "@/lib/utils";
import { Search, ExternalLink } from "lucide-react";
import Link from "next/link";

const EXAMPLES = [
  "What action items were assigned last week?",
  "What did we decide about pricing?",
  "Summarize the team's blockers",
];

export function QueryInterface() {
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
      setResult(await queryApi.ask(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="animate-fade-in-up">
      {/* Search bar */}
      <form onSubmit={handleSubmit} className="mb-5">
        <div className="surface flex items-center gap-2 px-3 py-2.5 focus-within:border-primary/50 transition-colors">
          <Search className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What did we decide about the product roadmap?"
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 outline-none"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="btn-primary text-xs px-3 py-1.5 flex-shrink-0"
          >
            {loading ? "Searching…" : "Ask"}
          </button>
        </div>

        {/* Example prompts */}
        {!result && !loading && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setQuestion(ex)}
                className="text-[11px] text-muted-foreground border border-border rounded px-2.5 py-1 hover:border-border/80 hover:text-foreground transition-colors"
                style={{ background: "hsl(var(--secondary))" }}
              >
                {ex}
              </button>
            ))}
          </div>
        )}
      </form>

      {error && (
        <p className="text-xs text-destructive surface px-4 py-3 mb-4 animate-fade-in">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-4 animate-fade-in-up">
          {/* Answer */}
          <div className="surface p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
              Answer
            </p>
            <p className="text-sm text-foreground leading-relaxed">{result.answer}</p>
          </div>

          {/* Sources */}
          {result.sources.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Sources
              </p>
              <div className="surface divide-y divide-border overflow-hidden">
                {result.sources.map((src, i) => (
                  <div key={src.chunk_id} className="px-4 py-3 animate-fade-in-up" style={{ animationDelay: `${i * 50}ms` }}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {formatTime(src.start_time)}
                      </span>
                      <Link
                        href={`/meetings/detail/?id=${src.meeting_id}`}
                        className="text-[11px] text-primary hover:underline underline-offset-2 flex items-center gap-1"
                      >
                        View <ExternalLink className="w-2.5 h-2.5" />
                      </Link>
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">{src.text}</p>
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
