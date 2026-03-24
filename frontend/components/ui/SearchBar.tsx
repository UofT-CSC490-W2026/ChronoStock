"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { searchTickers } from "@/lib/api";

export default function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ ticker: string; companyName: string }[]>([]);
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const res = await searchTickers(query);
      setResults(res);
      setOpen(res.length > 0);
    }, 250);
  }, [query]);

  function select(ticker: string) {
    setQuery("");
    setOpen(false);
    router.push(`/stock/${ticker}`);
  }

  return (
    <div className="relative w-full max-w-sm">
      <input
        className="w-full rounded-lg bg-slate-800 border border-slate-700 px-4 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder="Search ticker or company…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && results.length > 0) select(results[0].ticker);
        }}
      />
      {open && (
        <div className="absolute top-full mt-1 w-full rounded-lg bg-slate-800 border border-slate-700 shadow-xl z-50 overflow-hidden">
          {results.map((r) => (
            <button
              key={r.ticker}
              className="w-full text-left px-4 py-2 text-sm hover:bg-slate-700 flex items-center gap-3"
              onClick={() => select(r.ticker)}
            >
              <span className="font-mono font-bold text-indigo-400">{r.ticker}</span>
              <span className="text-slate-400">{r.companyName}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
