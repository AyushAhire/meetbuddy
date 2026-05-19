import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { MeetingsList } from "./meetings-list";
import { CopyTokenButton } from "./copy-token-button";

export default async function MeetingsPage() {
  const session = await auth();
  if (!session) redirect("/login");

  const accessToken = (session as unknown as Record<string, unknown>).accessToken as string;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Nav */}
      <header className="app-nav flex-shrink-0 px-5 h-12 flex items-center gap-4">
        <div className="flex items-center gap-2 mr-auto">
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
        </div>

        <a href="/query" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          Ask AI
        </a>
        <CopyTokenButton token={accessToken} />
        <span className="text-xs text-muted-foreground hidden sm:block">{session.user?.email}</span>
      </header>

      {/* Scrollable content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-5 py-8">
          <div className="mb-6 animate-fade-in-up">
            <h1 className="text-xl font-semibold text-foreground tracking-tight">Meetings</h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              AI-generated summaries and action items from your calls
            </p>
          </div>

          <MeetingsList accessToken={accessToken} />
        </div>

        {/* Footer boundary */}
        <div className="max-w-4xl mx-auto px-5 pb-8 pt-6 flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground/40">MeetBuddy · Privacy-first</span>
          <a
            href="https://github.com"
            className="text-[11px] text-muted-foreground/40 hover:text-muted-foreground transition-colors"
          >
            GitHub
          </a>
        </div>
      </main>
    </div>
  );
}
