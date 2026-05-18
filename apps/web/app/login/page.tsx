"use client";

import { signIn } from "next-auth/react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";

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
    const result = await signIn("credentials", {
      email: data.email,
      password: data.password,
      redirect: false,
    });
    if (result?.error) {
      setError("Invalid email or password");
    } else {
      router.push("/meetings");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md p-8 rounded-lg border bg-card shadow-sm">
        <h1 className="text-2xl font-bold mb-2">Welcome to MeetBuddy</h1>
        <p className="text-muted-foreground mb-6 text-sm">Sign in to your account</p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="text-sm font-medium block mb-1">Email</label>
            <input
              {...register("email")}
              type="email"
              placeholder="you@example.com"
              className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.email && <p className="text-destructive text-xs mt-1">{errors.email.message}</p>}
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">Password</label>
            <input
              {...register("password")}
              type="password"
              placeholder="••••••••"
              className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.password && <p className="text-destructive text-xs mt-1">{errors.password.message}</p>}
          </div>

          {error && <p className="text-destructive text-sm">{error}</p>}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-primary text-primary-foreground py-2 rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="my-4 flex items-center gap-2">
          <div className="flex-1 h-px bg-border" />
          <span className="text-xs text-muted-foreground">or</span>
          <div className="flex-1 h-px bg-border" />
        </div>

        <button
          onClick={() => signIn("google", { callbackUrl: "/meetings" })}
          className="w-full border py-2 rounded-md text-sm font-medium hover:bg-accent flex items-center justify-center gap-2"
        >
          Continue with Google
        </button>

        <p className="text-xs text-center text-muted-foreground mt-4">
          No account?{" "}
          <a href="/register" className="text-primary hover:underline">Register</a>
        </p>
      </div>
    </div>
  );
}
