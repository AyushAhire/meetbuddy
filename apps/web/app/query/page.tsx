import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";
import { QueryInterface } from "./query-interface";

export default async function QueryPage() {
  const session = await auth();
  if (!session) redirect("/login");

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/meetings" className="text-sm text-muted-foreground hover:text-foreground">MeetBuddy</a>
          <span className="text-muted-foreground">/</span>
          <span className="font-medium text-sm">Ask AI</span>
        </div>
        <span className="text-sm text-muted-foreground">{session.user?.email}</span>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-1">Ask your meetings</h1>
          <p className="text-muted-foreground text-sm">
            Search across all your meeting history with natural language.
          </p>
        </div>
        <QueryInterface accessToken={(session as Record<string, unknown>).accessToken as string} />
      </main>
    </div>
  );
}
