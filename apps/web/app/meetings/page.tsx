import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { MeetingsList } from "./meetings-list";
import { CopyTokenButton } from "./copy-token-button";
import { RecordingControl } from "@/app/components/recording-control";

export default async function MeetingsPage() {
  const session = await auth();
  if (!session) redirect("/login");

  const accessToken = (session as unknown as Record<string, unknown>).accessToken as string;

  return (
    <div className="min-h-screen">
      <header className="app-nav px-5 h-12 flex items-center gap-4">
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
        <RecordingControl token={accessToken} />
        <CopyTokenButton token={accessToken} />
        <span className="text-xs text-muted-foreground hidden sm:block">{session.user?.email}</span>
      </header>

      <main className="max-w-4xl mx-auto px-5 py-8 pb-16">
        <div className="mb-6 animate-fade-in-up">
          <h1 className="text-xl font-semibold text-foreground tracking-tight">Meetings</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            AI-generated summaries and action items from your calls
          </p>
        </div>
        <MeetingsList accessToken={accessToken} />
      </main>
    </div>
  );
}
