"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useState } from "react";
import { authApi } from "@/lib/api";
import { Logo } from "@/app/components/logo";

const registerSchema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
  password: z.string().min(6),
});
type RegisterForm = z.infer<typeof registerSchema>;

export default function RegisterPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  });

  async function onSubmit(data: RegisterForm) {
    setError(null);
    try {
      await authApi.register(data.email, data.password, data.name);
      await signIn("credentials", { email: data.email, password: data.password, redirect: false });
      router.push("/meetings");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
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
          <h1 className="text-base font-semibold text-foreground mb-0.5">Create account</h1>
          <p className="text-xs text-muted-foreground mb-5">Start capturing meeting intelligence</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-3.5">
            <div>
              <label className="field-label">Name</label>
              <input {...register("name")} type="text" placeholder="Your name" className="field-input" />
              {errors.name && <p className="text-destructive text-xs mt-1">{errors.name.message}</p>}
            </div>

            <div>
              <label className="field-label">Email</label>
              <input {...register("email")} type="email" placeholder="you@example.com" className="field-input" />
              {errors.email && <p className="text-destructive text-xs mt-1">{errors.email.message}</p>}
            </div>

            <div>
              <label className="field-label">Password</label>
              <input {...register("password")} type="password" placeholder="••••••••" className="field-input" />
              {errors.password && <p className="text-destructive text-xs mt-1">{errors.password.message}</p>}
            </div>

            {error && (
              <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 px-3 py-2 rounded">
                {error}
              </p>
            )}

            <button type="submit" disabled={isSubmitting} className="btn-primary w-full py-2.5">
              {isSubmitting ? "Creating account…" : "Create account"}
            </button>
          </form>
        </div>

        <p className="text-center text-[11px] text-muted-foreground mt-4">
          Already have an account?{" "}
          <a href="/login" className="text-primary hover:underline underline-offset-2">Sign in</a>
        </p>
      </div>
    </div>
  );
}
