import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { QueryInterface } from "./query-interface";

export default async function QueryPage() {
  const session = await auth();
  if (!session) redirect("/login");

  return (
    <div className="min-h-screen">
      {/* Nav */}
      <header className="app-nav px-5 h-12 flex items-center gap-3">
        <a href="/meetings" className="flex items-center gap-2">
          <div
            className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0"
            style={{ background: "hsl(245 58% 61%)" }}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
              <rect x="6" y="4" width="4" height="16" rx="1" fill="white" />
              <rect x="14" y="4" width="4" height="16" rx="1" fill="white" />
            </svg>
          </div>
          <span className="font-semibold text-sm text-foreground tracking-tight">MeetBuddy</span>
        </a>
        <span className="text-muted-foreground/40 text-xs">/</span>
        <span className="text-xs text-muted-foreground">Ask AI</span>
        <span className="text-xs text-muted-foreground ml-auto hidden sm:block">{session.user?.email}</span>
      </header>

      {/* Scrollable content */}
      <main className="max-w-3xl mx-auto px-5 py-8 pb-16">
        <div className="mb-6 animate-fade-in-up">
          <h1 className="text-xl font-semibold text-foreground tracking-tight">Ask AI</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Search across all your meeting history with natural language.
          </p>
        </div>
        <QueryInterface accessToken={(session as unknown as Record<string, unknown>).accessToken as string} />
      </main>
    </div>
  );
}
