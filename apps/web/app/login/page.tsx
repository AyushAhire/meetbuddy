"use client";

import { signIn } from "next-auth/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Logo } from "@/app/components/logo";

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});
type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  });

  async function onSubmit(data: LoginForm) {
    setError(null);
    const result = await signIn("credentials", { ...data, redirect: false });
    if (result?.error) setError("Invalid email or password");
    else router.push("/meetings");
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-[360px] animate-fade-in-up">

        {/* Wordmark */}
        <div className="flex items-center gap-2 justify-center mb-8">
          <Logo size={24} />
          <span className="font-semibold text-sm text-foreground tracking-tight">MeetBuddy</span>
        </div>

        {/* Card */}
        <div className="surface p-6">
          <h1 className="text-base font-semibold text-foreground mb-0.5">Sign in</h1>
          <p className="text-xs text-muted-foreground mb-5">Enter your credentials to continue</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-3.5">
            <div>
              <label className="field-label">Email</label>
              <input
                {...register("email")}
                type="email"
                placeholder="you@example.com"
                className="field-input"
              />
              {errors.email && (
                <p className="text-destructive text-xs mt-1">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label className="field-label">Password</label>
              <input
                {...register("password")}
                type="password"
                placeholder="••••••••"
                className="field-input"
              />
              {errors.password && (
                <p className="text-destructive text-xs mt-1">{errors.password.message}</p>
              )}
            </div>

            {error && (
              <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary w-full py-2.5"
            >
              {isSubmitting ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="my-4 flex items-center gap-2">
            <div className="flex-1 h-px bg-border" />
            <span className="text-[11px] text-muted-foreground">or</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <button
            onClick={() => signIn("google", { callbackUrl: "/meetings" })}
            className="btn-ghost w-full py-2 text-xs justify-center"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" className="flex-shrink-0">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continue with Google
          </button>
        </div>

        <p className="text-center text-[11px] text-muted-foreground mt-4">
          No account?{" "}
          <a href="/register" className="text-primary hover:underline underline-offset-2">
            Register
          </a>
        </p>
      </div>
    </div>
  );
}
