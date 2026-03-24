"use client";

import Image from "next/image";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import SearchBar from "@/components/ui/SearchBar";

export default function Navbar({ showSearch = false }: { showSearch?: boolean }) {
  const { user, logout } = useAuth();

  const truncateEmail = (email: string) => {
    if (email.length <= 24) return email;
    return email.slice(0, 21) + "...";
  };

  return (
    <header className="flex items-center gap-4 px-6 py-3 border-b border-slate-800 bg-slate-950 shrink-0">
      <Link href="/" className="flex items-center gap-2">
        <Image src="/logo.png" alt="ChronoStock" width={50} height={50} className="rounded-md" style={{ width: 50, height: "auto" }} />
        <span className="text-lg font-bold tracking-tight text-white">
          Chrono<span className="text-indigo-400">Stock</span>
        </span>
      </Link>

      <Link
        href="/"
        className="text-sm text-slate-400 hover:text-slate-200 transition-colors px-1 shrink-0"
      >
        Home
      </Link>
      <Link
        href="/compare"
        className="text-sm text-slate-400 hover:text-slate-200 transition-colors px-1 shrink-0"
      >
        Compare
      </Link>
      {user && (
        <Link
          href="/watchlist"
          className="text-sm text-slate-400 hover:text-slate-200 transition-colors px-1 shrink-0"
        >
          Watchlist
        </Link>
      )}

      {showSearch && (
        <div className="flex-1 flex justify-center px-4">
          <SearchBar />
        </div>
      )}

      {!showSearch && <div className="flex-1" />}

      {user ? (
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-400 hidden sm:block" title={user.email}>
            {truncateEmail(user.email)}
          </span>
          <button
            onClick={logout}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-sm text-slate-300 transition-colors"
          >
            Sign out
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className="px-3 py-1.5 rounded-lg text-sm text-slate-300 hover:text-white transition-colors"
          >
            Log in
          </Link>
          <Link
            href="/signup"
            className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white font-medium transition-colors"
          >
            Sign up
          </Link>
        </div>
      )}
    </header>
  );
}
