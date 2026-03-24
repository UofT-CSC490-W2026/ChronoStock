"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import Navbar from "@/components/ui/Navbar";
import CompareChart, { STOCK_COLORS, CompareStock } from "@/components/chart/CompareChart";
import { fetchStockData, searchTickers } from "@/lib/api";
import { StockData, OHLCBar, NewsEvent } from "@/types";
import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";

// ── Types ─────────────────────────────────────────────────────────────────────

type TimeRange = "1W" | "1M" | "6M" | "1Y" | "5Y" | "ALL";

const RANGES: { label: string; value: TimeRange }[] = [
  { label: "1W", value: "1W" },
  { label: "1M", value: "1M" },
  { label: "6M", value: "6M" },
  { label: "1Y", value: "1Y" },
  { label: "5Y", value: "5Y" },
  { label: "All", value: "ALL" },
];

const RANGE_DAYS: Record<Exclude<TimeRange, "ALL">, number> = {
  "1W": 7, "1M": 30, "6M": 182, "1Y": 365, "5Y": 1825,
};

const MAX_STOCKS = 5;

// ── Helpers ────────────────────────────────────────────────────────────────────

function filterBars(bars: OHLCBar[], range: TimeRange): OHLCBar[] {
  if (!bars.length || range === "ALL") return bars;
  const last = bars[bars.length - 1].time;
  const d = new Date(last + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - RANGE_DAYS[range]);
  const from = d.toISOString().slice(0, 10);
  return bars.filter((b) => b.time >= from);
}

function filterEvents(events: NewsEvent[], bars: OHLCBar[]): NewsEvent[] {
  if (!bars.length) return [];
  const from = bars[0].time;
  const to = bars[bars.length - 1].time;
  return events.filter((ev) => ev.time >= from && ev.time <= to);
}

function pctChange(bars: OHLCBar[]): number | null {
  if (bars.length < 2) return null;
  const start = bars[0].close;
  const end = bars[bars.length - 1].close;
  return ((end - start) / start) * 100;
}

// ── Ticker search dropdown ─────────────────────────────────────────────────────

function TickerSearch({ onAdd, excluded }: { onAdd: (ticker: string) => void; excluded: string[] }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ ticker: string; companyName: string }[]>([]);
  const [open, setOpen] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!query.trim()) { setResults([]); setOpen(false); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const res = await searchTickers(query);
      setResults(res.filter((r) => !excluded.includes(r.ticker)));
      setOpen(true);
    }, 250);
  }, [query, excluded]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function select(ticker: string) {
    onAdd(ticker);
    setQuery("");
    setOpen(false);
    setResults([]);
  }

  return (
    <div ref={wrapRef} className="relative">
      <input
        className="w-56 rounded-lg bg-slate-800 border border-slate-700 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        placeholder="Add ticker…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && results.length > 0) select(results[0].ticker);
        }}
      />
      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-64 rounded-lg bg-slate-800 border border-slate-700 shadow-xl z-50 overflow-hidden">
          {results.map((r) => (
            <button
              key={r.ticker}
              className="w-full text-left px-4 py-2 text-sm hover:bg-slate-700 flex items-center gap-3"
              onClick={() => select(r.ticker)}
            >
              <span className="font-mono font-bold text-indigo-400">{r.ticker}</span>
              <span className="text-slate-400 truncate">{r.companyName}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ComparePage() {
  const { user } = useAuth();
  const [tickers, setTickers] = useState<string[]>([]);
  const [stockMap, setStockMap] = useState<Record<string, StockData>>({});
  const [loadingTickers, setLoadingTickers] = useState<Set<string>>(new Set());
  const [range, setRange] = useState<TimeRange>("1Y");
  // Per-ticker event visibility toggle (logged-in users only)
  const [eventVisible, setEventVisible] = useState<Record<string, boolean>>({});

  // Fetch data when a ticker is added
  async function addTicker(ticker: string) {
    const upper = ticker.toUpperCase();
    if (tickers.includes(upper) || tickers.length >= MAX_STOCKS) return;
    setTickers((prev) => [...prev, upper]);
    setLoadingTickers((prev) => new Set(prev).add(upper));
    setEventVisible((prev) => ({ ...prev, [upper]: true }));
    try {
      const data = await fetchStockData(upper);
      setStockMap((prev) => ({ ...prev, [upper]: data }));
    } catch {
      // Remove if fetch failed
      setTickers((prev) => prev.filter((t) => t !== upper));
    } finally {
      setLoadingTickers((prev) => { const s = new Set(prev); s.delete(upper); return s; });
    }
  }

  function removeTicker(ticker: string) {
    setTickers((prev) => prev.filter((t) => t !== ticker));
    setStockMap((prev) => { const m = { ...prev }; delete m[ticker]; return m; });
    setEventVisible((prev) => { const m = { ...prev }; delete m[ticker]; return m; });
  }

  function toggleEventVisible(ticker: string) {
    setEventVisible((prev) => ({ ...prev, [ticker]: !prev[ticker] }));
  }

  // Build compare stocks for the chart
  const compareStocks: CompareStock[] = useMemo(() => {
    return tickers
      .map((ticker, i) => {
        const data = stockMap[ticker];
        if (!data) return null;
        const fb = filterBars(data.bars, range);
        const fe = filterEvents(data.events, fb);
        return { ticker, bars: fb, color: STOCK_COLORS[i % STOCK_COLORS.length], events: fe };
      })
      .filter((s): s is CompareStock => s !== null);
  }, [tickers, stockMap, range]);

  const visibleEventTickers = useMemo(
    () => new Set(tickers.filter((t) => eventVisible[t])),
    [tickers, eventVisible]
  );

  // All visible events across all stocks (for sidebar)
  const allVisibleEvents = useMemo(() => {
    const evs: (NewsEvent & { ticker: string; color: string })[] = [];
    for (const s of compareStocks) {
      if (!visibleEventTickers.has(s.ticker)) continue;
      for (const ev of s.events) {
        evs.push({ ...ev, ticker: s.ticker, color: s.color });
      }
    }
    return evs.sort((a, b) => b.time.localeCompare(a.time));
  }, [compareStocks, visibleEventTickers]);

  const SENTIMENT_DOT: Record<NewsEvent["sentiment"], string> = {
    positive: "bg-green-500", negative: "bg-red-500", neutral: "bg-amber-500",
  };

  return (
    <div className="flex flex-col h-screen bg-slate-950 text-slate-200">
      <Navbar showSearch={false} />

      <div className="flex flex-1 overflow-hidden">
        {/* ── Main column ── */}
        <div className="flex flex-col flex-1 overflow-hidden p-4 gap-3">

          {/* Header */}
          <div className="flex items-center gap-3 flex-wrap">
            <h2 className="text-xl font-bold text-white shrink-0">Compare Stocks</h2>

            {/* Selected ticker chips */}
            {tickers.map((ticker, i) => {
              const data = stockMap[ticker];
              const loading = loadingTickers.has(ticker);
              const fb = data ? filterBars(data.bars, range) : [];
              const pct = pctChange(fb);
              const color = STOCK_COLORS[i % STOCK_COLORS.length];
              return (
                <div
                  key={ticker}
                  className="flex items-center gap-1.5 pl-2.5 pr-1 py-1 rounded-lg border border-slate-700 bg-slate-800"
                >
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <Link href={`/stock/${ticker}`} className="font-mono font-bold text-sm hover:underline" style={{ color }}>
                    {ticker}
                  </Link>
                  {loading && <span className="text-xs text-slate-500 animate-pulse ml-1">…</span>}
                  {!loading && pct !== null && (
                    <span className={`text-xs font-medium ml-1 ${pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                    </span>
                  )}
                  <button
                    onClick={() => removeTicker(ticker)}
                    className="ml-1 text-slate-500 hover:text-red-400 transition-colors text-sm px-0.5"
                    aria-label={`Remove ${ticker}`}
                  >
                    ×
                  </button>
                </div>
              );
            })}

            {/* Search to add */}
            {tickers.length < MAX_STOCKS && (
              <TickerSearch onAdd={addTicker} excluded={tickers} />
            )}

            {/* Range selector — pushed to right */}
            <div className="ml-auto flex gap-1 bg-slate-900 rounded-lg p-1 border border-slate-800">
              {RANGES.map((r) => (
                <button
                  key={r.value}
                  onClick={() => setRange(r.value)}
                  className={`px-3 py-1 rounded-md text-sm font-medium transition-all ${
                    range === r.value
                      ? "bg-indigo-600 text-white shadow"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chart */}
          <div className="flex-1 rounded-xl overflow-hidden border border-slate-800">
            {tickers.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500">
                <svg className="w-12 h-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4v16" />
                </svg>
                <p className="text-sm">Search and add stocks above to compare</p>
              </div>
            ) : (
              <CompareChart stocks={compareStocks} visibleEventTickers={visibleEventTickers} />
            )}
          </div>

          {/* Footer note */}
          <p className="text-xs text-slate-600">Chart shows % change from start of selected range for fair comparison.</p>
        </div>

        {/* ── Sidebar ── */}
        <aside className="w-72 shrink-0 border-l border-slate-800 overflow-y-auto p-4 flex flex-col gap-4">
          {user ? (
            <>
              {/* Per-ticker event toggles */}
              {tickers.length > 0 && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
                    Event Filters
                  </p>
                  <div className="flex flex-col gap-2">
                    {tickers.map((ticker, i) => {
                      const color = STOCK_COLORS[i % STOCK_COLORS.length];
                      const data = stockMap[ticker];
                      const eventCount = data
                        ? filterEvents(data.events, filterBars(data.bars, range)).length
                        : 0;
                      return (
                        <button
                          key={ticker}
                          onClick={() => toggleEventVisible(ticker)}
                          className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors text-left ${
                            eventVisible[ticker]
                              ? "border-slate-600 bg-slate-800"
                              : "border-slate-800 bg-slate-900 opacity-50"
                          }`}
                        >
                          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                          <span className="font-mono font-bold flex-1" style={{ color }}>{ticker}</span>
                          <span className="text-xs text-slate-500">{eventCount} events</span>
                          <span className={`text-xs ${eventVisible[ticker] ? "text-indigo-400" : "text-slate-600"}`}>
                            {eventVisible[ticker] ? "On" : "Off"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Combined event list */}
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-3">
                  Key Events
                </p>
                {allVisibleEvents.length === 0 ? (
                  <p className="text-sm text-slate-600">
                    {tickers.length === 0
                      ? "Add stocks to see events."
                      : "No events for this period."}
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {allVisibleEvents.map((ev) => (
                      <div
                        key={`${ev.ticker}-${ev.id}`}
                        className="rounded-xl border border-slate-700 bg-slate-800/50 px-3 py-2.5"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: ev.color }} />
                          <span className="text-[10px] font-mono font-bold" style={{ color: ev.color }}>{ev.ticker}</span>
                          <span className="text-[11px] font-mono text-slate-500 ml-auto">{ev.time}</span>
                          <span className={`w-1.5 h-1.5 rounded-full ${SENTIMENT_DOT[ev.sentiment]}`} />
                        </div>
                        <p className="text-xs font-medium text-slate-200 leading-snug">{ev.title}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">{ev.source}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-4">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Key Events</p>
              <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-center text-sm text-slate-500">
                <Link href="/login" className="text-indigo-400 hover:text-indigo-300 font-medium transition-colors">
                  Sign in
                </Link>{" "}
                to see AI-powered key events across all selected stocks.
              </div>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
