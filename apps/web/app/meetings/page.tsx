import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { MeetingsList } from "./meetings-list";
import { CopyTokenButton } from "./copy-token-button";

export default async function MeetingsPage() {
  const session = await auth();
  if (!session) redirect("/login");

  const accessToken = (session as Record<string, unknown>).accessToken as string;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg">MeetBuddy</span>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <a href="/query" className="hover:text-foreground">Ask AI</a>
          <CopyTokenButton token={accessToken} />
          <span>{session.user?.email}</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">Your Meetings</h1>
        </div>
        <MeetingsList accessToken={accessToken} />
      </main>
    </div>
  );
}
