"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Navbar from "@/components/ui/Navbar";
import { useAuth } from "@/contexts/AuthContext";
import {
  fetchWatchlist,
  fetchPrices,
  fetchStockData,
  removeFromWatchlist,
  TrendingItem,
} from "@/lib/api";
import { StockData, OHLCBar } from "@/types";

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ bars }: { bars: OHLCBar[] }) {
  const recent = bars.slice(-60);
  if (recent.length < 2) {
    return <div className="w-28 h-10 rounded bg-slate-800 animate-pulse" />;
  }

  const closes = recent.map((b) => b.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;

  const W = 112, H = 40;
  const pts = closes
    .map((c, i) => {
      const x = (i / (closes.length - 1)) * W;
      const y = H - ((c - min) / range) * (H - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const isUp = closes[closes.length - 1] >= closes[0];
  const color = isUp ? "#34d399" : "#f87171";

  // Filled area path: line + close along bottom
  const firstX = 0;
  const lastX = W;
  const areaPath = `M ${pts.split(" ").join(" L ")} L ${lastX},${H} L ${firstX},${H} Z`;

  return (
    <svg width={W} height={H} className="overflow-visible shrink-0">
      <defs>
        <linearGradient id={`sg-${isUp}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#sg-${isUp})`} />
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── 52-week range bar ──────────────────────────────────────────────────────────

function WeekRange({
  low, high, current,
}: {
  low: number; high: number; current?: number;
}) {
  const pct = current != null && high > low
    ? Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100))
    : null;

  return (
    <div className="flex flex-col gap-1 min-w-[120px]">
      <div className="relative h-1 rounded-full bg-slate-700 w-full">
        {pct !== null && (
          <div
            className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-indigo-400 border border-slate-950"
            style={{ left: `calc(${pct}% - 4px)` }}
          />
        )}
      </div>
      <div className="flex justify-between text-[10px] text-slate-500">
        <span>${low.toFixed(0)}</span>
        <span>${high.toFixed(0)}</span>
      </div>
    </div>
  );
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fNum(n?: number) {
  if (n == null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

function fVol(n?: number) {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
}

// ── Row skeleton ──────────────────────────────────────────────────────────────

function RowSkeleton() {
  return (
    <div className="flex items-center gap-5 px-5 py-4 border-b border-slate-800 animate-pulse">
      <div className="w-24 h-4 rounded bg-slate-800" />
      <div className="w-36 h-3 rounded bg-slate-800" />
      <div className="w-28 h-10 rounded bg-slate-800 ml-auto" />
      <div className="w-16 h-4 rounded bg-slate-800" />
      <div className="w-12 h-4 rounded bg-slate-800" />
      <div className="w-16 h-4 rounded bg-slate-800" />
      <div className="w-10 h-4 rounded bg-slate-800" />
      <div className="w-28 h-4 rounded bg-slate-800" />
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

interface RowData {
  ticker: string;
  price?: TrendingItem;
  stock?: StockData;
  loaded: boolean;
}

export default function WatchlistPage() {
  const { user, token } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<RowData[]>([]);
  const [initialising, setInitialising] = useState(true);

  useEffect(() => {
    if (!user || !token) {
      router.replace("/login");
      return;
    }

    async function load() {
      if (!token) return;
      setInitialising(true);
      const wl = await fetchWatchlist(token).catch(() => []);
      const tickers = wl.map((w) => w.ticker);

      // Seed rows immediately so skeletons appear in order
      setRows(tickers.map((t) => ({ ticker: t, loaded: false })));
      setInitialising(false);

      // Fetch prices for all tickers in one shot
      const prices = await fetchPrices(tickers);
      const priceMap = Object.fromEntries(prices.map((p) => [p.ticker, p]));

      // Fetch full stock data per ticker in parallel
      const stockResults = await Promise.allSettled(
        tickers.map((t) => fetchStockData(t))
      );

      setRows(
        tickers.map((t, i) => ({
          ticker: t,
          price: priceMap[t],
          stock:
            stockResults[i].status === "fulfilled"
              ? stockResults[i].value
              : undefined,
          loaded: true,
        }))
      );
    }

    load();
  }, [user, token, router]);

  async function handleRemove(ticker: string) {
    if (!token) return;
    try {
      await removeFromWatchlist(ticker, token);
      setRows((prev) => prev.filter((r) => r.ticker !== ticker));
    } catch { /* ignore */ }
  }

  if (initialising) {
    return (
      <div className="flex flex-col h-screen bg-slate-950 text-slate-200">
        <Navbar />
        <div className="flex flex-1 items-center justify-center text-slate-500 animate-pulse">
          Loading watchlist…
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-200">
      <Navbar />

      <main className="flex-1 px-6 py-6 max-w-7xl mx-auto w-full">
        <h1 className="text-2xl font-bold text-white mb-6">My Watchlist</h1>

        {rows.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500">
            <svg className="w-12 h-12 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.562.562 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
            </svg>
            <p className="text-sm">No stocks saved yet.</p>
            <Link href="/" className="text-indigo-400 hover:text-indigo-300 text-sm transition-colors">
              Search for stocks to add →
            </Link>
          </div>
        ) : (
          <div className="rounded-xl border border-slate-800 overflow-hidden">
            {/* Table header */}
            <div className="grid grid-cols-[1fr_160px_140px_100px_80px_80px_80px_160px_40px] items-center gap-4 px-5 py-2.5 bg-slate-900 border-b border-slate-800">
              {["Symbol", "Company", "30D Trend", "Price", "Day", "Mkt Cap", "P/E", "52W Range", ""].map(
                (h) => (
                  <span key={h} className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
                    {h}
                  </span>
                )
              )}
            </div>

            {/* Rows */}
            {rows.map((row) => {
              if (!row.loaded) return <RowSkeleton key={row.ticker} />;

              const meta = row.stock?.meta;
              const bars = row.stock?.bars ?? [];
              const price = row.price?.price ?? (bars.length ? bars[bars.length - 1].close : undefined);
              const changePct = row.price?.changePct;
              const isUp = (changePct ?? 0) >= 0;

              return (
                <div
                  key={row.ticker}
                  className="grid grid-cols-[1fr_160px_140px_100px_80px_80px_80px_160px_40px] items-center gap-4 px-5 py-3.5 border-b border-slate-800 hover:bg-slate-900/50 transition-colors"
                >
                  {/* Symbol */}
                  <Link
                    href={`/stock/${row.ticker}`}
                    className="font-mono font-bold text-indigo-400 hover:text-indigo-300 transition-colors text-sm"
                  >
                    {row.ticker}
                  </Link>

                  {/* Company */}
                  <span className="text-sm text-slate-400 truncate">
                    {row.price?.companyName ?? row.stock?.companyName ?? "—"}
                  </span>

                  {/* Sparkline */}
                  <div className="flex items-center">
                    {bars.length >= 2 ? (
                      <Sparkline bars={bars} />
                    ) : (
                      <div className="w-28 h-10 rounded bg-slate-800 animate-pulse" />
                    )}
                  </div>

                  {/* Price */}
                  <span className="text-sm font-semibold text-slate-200">
                    {price != null ? `$${price.toFixed(2)}` : "—"}
                  </span>

                  {/* Day change */}
                  <span className={`text-sm font-medium ${isUp ? "text-green-400" : "text-red-400"}`}>
                    {changePct != null
                      ? `${isUp ? "+" : ""}${changePct.toFixed(2)}%`
                      : "—"}
                  </span>

                  {/* Market cap */}
                  <span className="text-sm text-slate-300">{fNum(meta?.marketCap)}</span>

                  {/* P/E */}
                  <span className="text-sm text-slate-300">
                    {meta?.peRatio != null ? meta.peRatio.toFixed(1) : "—"}
                  </span>

                  {/* 52W Range */}
                  {meta?.weekLow52 != null && meta?.weekHigh52 != null ? (
                    <WeekRange low={meta.weekLow52} high={meta.weekHigh52} current={price} />
                  ) : (
                    <span className="text-sm text-slate-600">—</span>
                  )}

                  {/* Remove */}
                  <button
                    onClick={() => handleRemove(row.ticker)}
                    className="text-slate-600 hover:text-red-400 transition-colors text-lg leading-none justify-self-center"
                    aria-label={`Remove ${row.ticker}`}
                  >
                    ×
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
