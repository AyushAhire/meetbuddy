import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { meetingsApi } from "@/lib/api";
import { MeetingDetail } from "./meeting-detail";

interface Props { params: { id: string } }

export default async function MeetingDetailPage({ params }: Props) {
  const session = await auth();
  if (!session) redirect("/login");

  const token = (session as unknown as Record<string, unknown>).accessToken as string;
  const meeting = await meetingsApi.get(token, params.id);

  return (
    <div className="min-h-screen">
      {/* Nav */}
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
          {meeting.title ?? `${meeting.platform} meeting`}
        </span>
        <span className="text-xs text-muted-foreground ml-auto hidden sm:block">{session.user?.email}</span>
      </header>

      {/* Scrollable content */}
      <main className="max-w-4xl mx-auto px-5 py-8 pb-16">
        <MeetingDetail meeting={meeting} accessToken={token} />
      </main>
    </div>
  );
}
