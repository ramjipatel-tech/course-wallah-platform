"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Lock, Mail, ArrowRight, AlertCircle, Sparkles, GraduationCap } from "lucide-react";
import { api } from "@/lib/api";
import { CourseWallahLogo } from "@/components/brand/CourseWallahLogo";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextUrl = searchParams.get("next") || "/student";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await api.studentLogin({ email, password });
      router.push(nextUrl);
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[75vh] flex items-center justify-center py-10">
      <div className="w-full max-w-md p-8 sm:p-10 cw-card-elevated rounded-3xl border border-cw-border/80 shadow-2xl space-y-8">
        {/* Header */}
        <div className="text-center space-y-3">
          <div className="flex justify-center">
            <CourseWallahLogo size="lg" withTagline={false} />
          </div>
          <h1 className="text-2xl font-black text-white tracking-tight">
            Student Login
          </h1>
          <p className="text-xs sm:text-sm text-cw-muted">
            Access your registered curriculum, lecture streams, and study notes.
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3.5 bg-rose-500/10 border border-rose-500/25 rounded-2xl flex items-center gap-2.5 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-cw-text">Email Address</label>
            <div className="relative flex items-center">
              <Mail className="w-4 h-4 absolute left-3.5 text-cw-muted pointer-events-none" />
              <input
                type="email"
                required
                placeholder="student@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-cw-text">Password</label>
            </div>
            <div className="relative flex items-center">
              <Lock className="w-4 h-4 absolute left-3.5 text-cw-muted pointer-events-none" />
              <input
                type="password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-cw-surface border border-cw-border rounded-xl text-sm text-white placeholder-cw-muted focus:outline-none focus:border-cw-primary focus:ring-2 focus:ring-cw-primary/20 transition-all"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-cw-primary hover:bg-cw-primary-hover text-white font-bold text-sm rounded-xl shadow-lg shadow-blue-500/20 flex items-center justify-center gap-2 disabled:opacity-40 transition-all hover:scale-[1.02] active:scale-[0.98] mt-2"
          >
            <span>{loading ? "Authenticating..." : "Sign In"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* Footer Link */}
        <div className="text-center pt-2 border-t border-cw-border/60 text-xs text-cw-muted">
          <span>New to Course Wallah? </span>
          <Link
            href={`/register?next=${encodeURIComponent(nextUrl)}`}
            className="font-bold text-cw-primary hover:underline"
          >
            Create an Account
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-[60vh] flex items-center justify-center text-cw-muted">Loading...</div>}>
      <LoginForm />
    </Suspense>
  );
}
