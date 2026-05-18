"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useState } from "react";
import { authApi } from "@/lib/api";

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
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-md p-8 rounded-lg border bg-card shadow-sm">
        <h1 className="text-2xl font-bold mb-2">Create your account</h1>
        <p className="text-muted-foreground mb-6 text-sm">Start capturing meeting intelligence</p>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="text-sm font-medium block mb-1">Name</label>
            <input
              {...register("name")}
              type="text"
              placeholder="Your name"
              className="w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            {errors.name && <p className="text-destructive text-xs mt-1">{errors.name.message}</p>}
          </div>

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
            {isSubmitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="text-xs text-center text-muted-foreground mt-4">
          Already have an account?{" "}
          <a href="/login" className="text-primary hover:underline">Sign in</a>
        </p>
      </div>
    </div>
  );
}
