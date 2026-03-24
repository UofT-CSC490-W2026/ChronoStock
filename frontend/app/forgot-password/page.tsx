"use client";

import { useState } from "react";
import Link from "next/link";
import { requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setSubmitted(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex flex-col items-center justify-center min-h-screen px-4 bg-slate-950">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white tracking-tight">
            Chrono<span className="text-indigo-400">Stock</span>
          </h1>
          <p className="text-slate-400 text-sm mt-2">Reset your password</p>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-xl">
          {submitted ? (
            <div className="text-center">
              <p className="text-sm text-slate-300">
                If <span className="text-white font-medium">{email}</span> is registered, a reset
                link has been sent. Check your inbox (or server logs in dev mode).
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium text-slate-300">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition"
                  placeholder="you@example.com"
                />
              </div>

              {error && (
                <p className="text-sm text-red-400 bg-red-950/40 border border-red-900 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium text-sm transition-colors"
              >
                {loading ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}
        </div>

        <p className="text-center text-sm text-slate-500 mt-6">
          <Link href="/login" className="text-indigo-400 hover:text-indigo-300 transition-colors">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
