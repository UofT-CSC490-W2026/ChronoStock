"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import Navbar from "@/components/ui/Navbar";
import { fetchNews, fetchStockData, StockNews } from "@/lib/api";

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
  "1W": 7,
  "1M": 30,
  "6M": 182,
  "1Y": 365,
  "5Y": 1825,
};

function isTimeRange(value: string | null): value is TimeRange {
  return value === "1W" || value === "1M" || value === "6M" || value === "1Y" || value === "5Y" || value === "ALL";
}

function parseDate(value: string): Date | null {
  const normalized = value.length >= 10 ? value.slice(0, 10) : value;
  const date = new Date(`${normalized}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function filterByTimeline(items: StockNews[], range: TimeRange): StockNews[] {
  if (range === "ALL" || items.length === 0) return items;

  const newsDates = items
    .map((item) => parseDate(item.time))
    .filter((date): date is Date => date !== null)
    .sort((a, b) => b.getTime() - a.getTime());

  if (newsDates.length === 0) return items;

  const newest = new Date(newsDates[0]);
  newest.setUTCDate(newest.getUTCDate() - RANGE_DAYS[range]);

  return items.filter((item) => {
    const itemDate = parseDate(item.time);
    return itemDate !== null && itemDate >= newest;
  });
}

export default function StockNewsPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const queryRange = searchParams.get("range");
  const defaultRange: TimeRange = isTimeRange(queryRange) ? queryRange : "1Y";
  const [news, setNews] = useState<StockNews[]>([]);
  const [companyName, setCompanyName] = useState("");
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<TimeRange>(defaultRange);
  const [titleFilter, setTitleFilter] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      const [newsData, stockData] = await Promise.all([
        fetchNews(ticker),
        fetchStockData(ticker).catch(() => null),
      ]);
      if (cancelled) return;

      setNews(newsData);
      setCompanyName(stockData?.companyName ?? "");
      setLoading(false);
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const sortedNews = useMemo(
    () => [...news].sort((a, b) => b.time.localeCompare(a.time)),
    [news]
  );

  const visibleNews = useMemo(() => {
    const timelineFiltered = filterByTimeline(sortedNews, range);
    const query = titleFilter.trim().toLowerCase();
    if (!query) return timelineFiltered;
    return timelineFiltered.filter((item) => item.title.toLowerCase().includes(query));
  }, [sortedNews, range, titleFilter]);

  const newsDateStats = useMemo(() => {
    const dates = sortedNews
      .map((item) => parseDate(item.time))
      .filter((date): date is Date => date !== null);
    if (!dates.length) return null;
    const minTs = Math.min(...dates.map((d) => d.getTime()));
    const maxTs = Math.max(...dates.map((d) => d.getTime()));
    const spanDays = Math.round((maxTs - minTs) / (24 * 60 * 60 * 1000));
    return { spanDays, uniqueDays: new Set(dates.map((d) => d.toISOString().slice(0, 10))).size };
  }, [sortedNews]);

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-200">
      <Navbar showSearch />

      <main className="flex-1 w-full max-w-6xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between gap-4 flex-wrap mb-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-1">News Timeline</p>
            <h1 className="text-2xl font-bold text-white">
              {ticker.toUpperCase()}
              {companyName && <span className="ml-3 text-base font-normal text-slate-400">{companyName}</span>}
            </h1>
          </div>
          <Link
            href={`/stock/${ticker}`}
            className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 text-sm text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
          >
            Back to chart
          </Link>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 mb-4 flex flex-wrap items-end gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2">Timeline</p>
            <div className="flex gap-1 bg-slate-900 rounded-lg p-1 border border-slate-800">
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

          <label className="flex-1 min-w-[240px]">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-2 block">
              Filter by title
            </span>
            <input
              value={titleFilter}
              onChange={(e) => setTitleFilter(e.target.value)}
              placeholder="Type keywords (e.g. earnings, merger, guidance)"
              className="w-full rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </label>
        </div>

        {loading ? (
          <div className="py-16 text-center text-slate-500 animate-pulse">Loading news…</div>
        ) : visibleNews.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            No news matches this timeline and title filter.
          </div>
        ) : (
          <>
            <p className="text-xs text-slate-500 mb-1">{visibleNews.length} articles shown</p>
            {newsDateStats && newsDateStats.uniqueDays <= 1 && (
              <p className="text-[11px] text-slate-600 mb-3">
                Data provider currently returned only same-day news, so wider timeline options may look identical.
              </p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {visibleNews.map((item) => (
                <article key={item.id} className="rounded-xl border border-slate-700 bg-slate-800/50 overflow-hidden">
                  {item.thumbnail && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.thumbnail} alt="" className="w-full h-40 object-cover" />
                  )}
                  <div className="p-4">
                    <div className="flex items-center gap-2 mb-2 text-xs">
                      <span className="font-mono text-slate-500">{item.time}</span>
                      {item.publisher && (
                        <span className="text-slate-500 ml-auto truncate max-w-[180px]">{item.publisher}</span>
                      )}
                    </div>
                    <h2 className="text-sm font-semibold text-slate-100 leading-snug mb-2">{item.title}</h2>
                    {item.summary && <p className="text-xs text-slate-300 leading-relaxed">{item.summary}</p>}
                    {item.url && (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block mt-3 text-xs text-indigo-400 hover:underline"
                      >
                        Read full article →
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
