"use client";

import { QueryInterface } from "./query-interface";
import { Logo } from "@/app/components/logo";

export default function QueryPage() {
  return (
    <div className="min-h-screen">
      <header className="app-nav px-5 h-12 flex items-center gap-3">
        <a href="/meetings" className="flex items-center gap-2">
          <Logo size={20} />
          <span className="font-semibold text-sm text-foreground tracking-tight">MeetBuddy</span>
        </a>
        <span className="text-muted-foreground/40 text-xs">/</span>
        <span className="text-xs text-muted-foreground">Ask AI</span>
      </header>

      <main className="max-w-3xl mx-auto px-5 py-8 pb-16">
        <div className="mb-6 animate-fade-in-up">
          <h1 className="text-xl font-semibold text-foreground tracking-tight">Ask AI</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Search across all your meeting history with natural language.
          </p>
        </div>
        <QueryInterface />
      </main>
    </div>
  );
}
