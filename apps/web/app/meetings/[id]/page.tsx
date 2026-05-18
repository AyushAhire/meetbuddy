import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { meetingsApi } from "@/lib/api";
import { MeetingDetail } from "./meeting-detail";

interface Props {
  params: { id: string };
}

export default async function MeetingDetailPage({ params }: Props) {
  const session = await auth();
  if (!session) redirect("/login");

  const token = (session as Record<string, unknown>).accessToken as string;
  const meeting = await meetingsApi.get(token, params.id);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/meetings" className="text-sm text-muted-foreground hover:text-foreground">
            ← Meetings
          </a>
          <span className="text-muted-foreground">/</span>
          <span className="font-medium text-sm truncate max-w-xs">
            {meeting.title ?? `${meeting.platform} meeting`}
          </span>
        </div>
        <span className="text-sm text-muted-foreground">{session.user?.email}</span>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <MeetingDetail meeting={meeting} accessToken={token} />
      </main>
    </div>
  );
}
