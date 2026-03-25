"use client";

import { useEffect, useState } from "react";
import Navbar from "@/components/ui/Navbar";
import { fetchMarketSummary, fetchMarketAnalysis, fetchIndicatorHistory } from "@/lib/api";
import { MarketSummary, MacroIndicator, MarketAnalysis, IndicatorHistory } from "@/types";
import { useAuth } from "@/contexts/AuthContext";
import { TrendingUp, TrendingDown, Minus, Sparkles, Clock, BookOpen, Zap, Eye, LineChart, X } from "lucide-react";
import MacroChart from "@/components/chart/MacroChart";

// ── Macro indicator helpers ────────────────────────────────────────────────────

function formatValue(indicator: MacroIndicator): string {
  const { value, unit } = indicator;
  if (unit === "pts" || unit === "$/oz" || unit === "$/bbl") {
    return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  if (unit === "$/lb") return value.toFixed(4);
  if (unit === "K jobs" || unit === "K") {
    return value >= 0 ? `+${value.toLocaleString()}` : value.toLocaleString();
  }
  return value.toFixed(2);
}

function formatChange(indicator: MacroIndicator): string | null {
  const { change, changePct, unit } = indicator;
  if (change == null) return null;
  const sign = change >= 0 ? "+" : "";
  if (changePct != null) {
    const pctSign = changePct >= 0 ? "+" : "";
    return `${sign}${change.toFixed(2)} (${pctSign}${changePct.toFixed(2)}%)`;
  }
  if (unit === "% YoY" || unit === "%" || unit === "pp") {
    const bps = Math.round(change * 100);
    return `${bps >= 0 ? "+" : ""}${bps} bps`;
  }
  if (unit === "K jobs" || unit === "K") return `${sign}${change.toLocaleString()} K vs prev`;
  return `${sign}${change.toFixed(2)}`;
}

function trendDirection(indicator: MacroIndicator): "up" | "down" | "flat" {
  const delta = indicator.change ?? indicator.changePct ?? 0;
  if (Math.abs(delta) < 0.0001) return "flat";
  return delta > 0 ? "up" : "down";
}

const INVERTED_INDICATORS = new Set([
  "VIX", "Unemployment Rate", "Initial Jobless Claims", "HY Credit Spread",
  "CPI (YoY)", "Core CPI (YoY)", "PCE (YoY)", "Core PCE (YoY)",
]);

function changeColor(indicator: MacroIndicator): string {
  const dir = trendDirection(indicator);
  if (dir === "flat") return "text-slate-400";
  const isPositive = INVERTED_INDICATORS.has(indicator.name) ? dir === "down" : dir === "up";
  return isPositive ? "text-green-400" : "text-red-400";
}

function TrendIcon({ indicator }: { indicator: MacroIndicator }) {
  const dir = trendDirection(indicator);
  const color = changeColor(indicator);
  if (dir === "up") return <TrendingUp size={14} className={color} />;
  if (dir === "down") return <TrendingDown size={14} className={color} />;
  return <Minus size={14} className="text-slate-500" />;
}

function IndicatorCard({ indicator, onClick }: { indicator: MacroIndicator; onClick: () => void }) {
  const changeStr = formatChange(indicator);
  const color = changeColor(indicator);
  return (
    <div
      onClick={onClick}
      className="group bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-2 hover:border-indigo-500/60 hover:bg-slate-800/80 transition-colors cursor-pointer"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-slate-200 leading-snug">{indicator.name}</span>
        <div className="flex items-center gap-1.5 shrink-0">
          <LineChart size={13} className="text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
          <TrendIcon indicator={indicator} />
        </div>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-xl font-bold text-white tabular-nums">{formatValue(indicator)}</span>
        <span className="text-xs text-slate-500">{indicator.unit}</span>
      </div>
      {changeStr && <span className={`text-xs font-medium tabular-nums ${color}`}>{changeStr}</span>}
      <p className="text-xs text-slate-500 leading-relaxed mt-auto">{indicator.description}</p>
      <div className="flex items-center justify-between mt-1">
        <span className="text-xs text-slate-600">{indicator.source}</span>
        <span className="text-xs text-slate-600">as of {indicator.asOf}</span>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-3 animate-pulse">
      <div className="h-4 bg-slate-700 rounded w-3/4" />
      <div className="h-7 bg-slate-700 rounded w-1/2" />
      <div className="h-3 bg-slate-700 rounded w-1/3" />
      <div className="h-8 bg-slate-700 rounded w-full mt-auto" />
    </div>
  );
}

// ── AI Analysis components ─────────────────────────────────────────────────────

const REGIME_STYLES: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  bullish: { bg: "bg-green-950", border: "border-green-700", text: "text-green-300", dot: "bg-green-400" },
  bearish: { bg: "bg-red-950", border: "border-red-800", text: "text-red-300", dot: "bg-red-400" },
  neutral: { bg: "bg-slate-800", border: "border-slate-600", text: "text-slate-300", dot: "bg-slate-400" },
  mixed:   { bg: "bg-amber-950", border: "border-amber-700", text: "text-amber-300", dot: "bg-amber-400" },
};

const DRIVER_SENTIMENT: Record<string, string> = {
  positive: "text-green-400 bg-green-950 border-green-800",
  negative: "text-red-400 bg-red-950 border-red-900",
  neutral:  "text-slate-400 bg-slate-800 border-slate-700",
};

function AnalysisSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-16 bg-slate-800 rounded-xl" />
      <div className="space-y-3">
        <div className="h-4 bg-slate-800 rounded w-full" />
        <div className="h-4 bg-slate-800 rounded w-5/6" />
        <div className="h-4 bg-slate-800 rounded w-4/6" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 bg-slate-800 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function AIAnalysisSection({ token }: { token: string }) {
  const [analysis, setAnalysis] = useState<MarketAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMarketAnalysis(token)
      .then(setAnalysis)
      .catch((e) => setError(e.message ?? "Failed to generate analysis"))
      .finally(() => setLoading(false));
  }, [token]);

  const generatedAt = analysis
    ? new Date(analysis.generatedAt).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
      })
    : null;

  const regime = analysis ? REGIME_STYLES[analysis.regimeSentiment] ?? REGIME_STYLES.neutral : null;

  return (
    <section className="mb-12">
      {/* Section header */}
      <div className="flex items-center gap-2 mb-6">
        <Sparkles size={16} className="text-indigo-400" />
        <h2 className="text-xs font-semibold uppercase tracking-widest text-indigo-400">
          AI Market Analysis
        </h2>
        <span className="text-xs text-slate-600 ml-1">· logged-in only</span>
      </div>

      {loading && <AnalysisSkeleton />}

      {error && (
        <div className="rounded-xl bg-red-950 border border-red-800 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {analysis && regime && (
        <div className="space-y-6">

          {/* Regime badge + summary */}
          <div className={`rounded-xl border px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3 ${regime.bg} ${regime.border}`}>
            <div className="flex items-center gap-2 shrink-0">
              <span className={`w-2.5 h-2.5 rounded-full ${regime.dot} animate-pulse`} />
              <span className={`text-xs font-bold uppercase tracking-widest ${regime.text}`}>
                {analysis.regimeSentiment}
              </span>
            </div>
            <div className="w-px h-4 bg-slate-700 hidden sm:block" />
            <p className={`text-sm font-medium ${regime.text}`}>{analysis.summary}</p>
          </div>

          {/* Regime description */}
          <div className="rounded-xl bg-slate-800/60 border border-slate-700 px-5 py-4">
            <p className="text-sm text-slate-300 leading-relaxed">{analysis.regime}</p>
          </div>

          {/* What happened — narrative */}
          <div className="rounded-xl bg-slate-900 border border-slate-800 px-5 py-5">
            <div className="flex items-center gap-2 mb-4">
              <BookOpen size={14} className="text-slate-400" />
              <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">What Happened & Why</span>
            </div>
            <div className="space-y-3">
              {analysis.narrative.split("\n").filter(Boolean).map((para, i) => (
                <p key={i} className="text-sm text-slate-300 leading-relaxed">{para}</p>
              ))}
            </div>
          </div>

          {/* Key drivers */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Zap size={14} className="text-slate-400" />
              <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Key Drivers</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {analysis.keyDrivers.map((driver) => (
                <div
                  key={driver.title}
                  className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-3 hover:border-slate-600 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-200 leading-snug">{driver.title}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium shrink-0 ${DRIVER_SENTIMENT[driver.sentiment]}`}>
                      {driver.sentiment}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{driver.explanation}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Historical context */}
          <div className="rounded-xl bg-slate-900 border border-slate-800 px-5 py-5">
            <div className="flex items-center gap-2 mb-4">
              <Clock size={14} className="text-slate-400" />
              <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">Historical Context</span>
            </div>
            <div className="space-y-3">
              {analysis.historicalContext.split("\n").filter(Boolean).map((para, i) => (
                <p key={i} className="text-sm text-slate-300 leading-relaxed">{para}</p>
              ))}
            </div>
          </div>

          {/* What to watch */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Eye size={14} className="text-slate-400" />
              <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">What to Watch</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {analysis.watchlist.map((item) => (
                <div
                  key={item.indicator}
                  className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex flex-col gap-2 hover:border-slate-600 transition-colors"
                >
                  <span className="text-sm font-semibold text-indigo-400">{item.indicator}</span>
                  <p className="text-xs text-slate-300 leading-relaxed">{item.currentSignal}</p>
                  <p className="text-xs text-slate-500 leading-relaxed border-t border-slate-700 pt-2 mt-1">
                    {item.whyItMatters}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Generated timestamp */}
          {generatedAt && (
            <p className="text-xs text-slate-600 text-right">
              Generated {generatedAt} · refreshes every 12 hours
            </p>
          )}
        </div>
      )}
    </section>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MarketPage() {
  const { user, token } = useAuth();
  const [summary, setSummary] = useState<MarketSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedIndicator, setSelectedIndicator] = useState<MacroIndicator | null>(null);
  const [history, setHistory] = useState<IndicatorHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    fetchMarketSummary()
      .then(setSummary)
      .catch((e) => setError(e.message ?? "Failed to load market data"));
  }, []);

  function handleIndicatorClick(indicator: MacroIndicator) {
    setSelectedIndicator(indicator);
    setHistory(null);
    setHistoryError(null);
    setHistoryLoading(true);
    fetchIndicatorHistory(indicator.name)
      .then(setHistory)
      .catch((e: Error) => setHistoryError(e.message ?? "Failed to load history"))
      .finally(() => setHistoryLoading(false));
  }

  function closeModal() {
    setSelectedIndicator(null);
    setHistory(null);
    setHistoryError(null);
  }

  const updatedAt = summary
    ? new Date(summary.cachedAt).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
      })
    : null;

  return (
    <div className="flex flex-col min-h-screen bg-slate-950">
      <Navbar showSearch />

      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white tracking-tight mb-1">
            Market <span className="text-indigo-400">Overview</span>
          </h1>
          <p className="text-slate-400 text-sm">
            Key macroeconomic indicators — and for members, an AI-powered narrative of what&apos;s driving markets.
          </p>
          {updatedAt && (
            <p className="text-slate-600 text-xs mt-1">Macro data updated {updatedAt} · refreshes every 6 hours</p>
          )}
        </div>

        {error && (
          <div className="rounded-xl bg-red-950 border border-red-800 px-4 py-3 text-sm text-red-300 mb-6">
            {error}
          </div>
        )}

        {/* AI analysis — logged-in users only */}
        {user && token ? (
          <AIAnalysisSection token={token} />
        ) : (
          <div className="mb-10 rounded-xl bg-slate-900 border border-slate-800 px-5 py-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Sparkles size={16} className="text-indigo-400 shrink-0" />
              <div>
                <p className="text-sm text-slate-200 font-medium">AI Market Analysis</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  See what happened, why it happened, and what to watch — powered by Claude on AWS Bedrock.
                </p>
              </div>
            </div>
            <a
              href="/login"
              className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm text-white font-medium transition-colors shrink-0"
            >
              Sign in
            </a>
          </div>
        )}

        {/* Macro indicators — everyone */}
        {!summary && !error && (
          <div className="space-y-8">
            {Array.from({ length: 3 }).map((_, i) => (
              <section key={i}>
                <div className="h-5 bg-slate-800 rounded w-48 mb-4 animate-pulse" />
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {Array.from({ length: 4 }).map((_, j) => <SkeletonCard key={j} />)}
                </div>
              </section>
            ))}
          </div>
        )}

        {summary && (
          <div className="space-y-10">
            {summary.categories.map((category) => (
              <section key={category.name}>
                <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500 mb-4">
                  {category.name}
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                  {category.indicators.map((indicator) => (
                    <IndicatorCard
                      key={indicator.name}
                      indicator={indicator}
                      onClick={() => handleIndicatorClick(indicator)}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>

      {/* Indicator history modal */}
      {selectedIndicator && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={closeModal}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl mx-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-start justify-between gap-4 shrink-0">
              <div>
                <h3 className="text-base font-semibold text-white">{selectedIndicator.name}</h3>
                <div className="flex items-baseline gap-1.5 mt-1">
                  <span className="text-2xl font-bold text-white tabular-nums">
                    {formatValue(selectedIndicator)}
                  </span>
                  <span className="text-sm text-slate-500">{selectedIndicator.unit}</span>
                  {formatChange(selectedIndicator) && (
                    <span className={`text-sm font-medium tabular-nums ml-1 ${changeColor(selectedIndicator)}`}>
                      {formatChange(selectedIndicator)}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">{selectedIndicator.description}</p>
              </div>
              <button
                onClick={closeModal}
                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors shrink-0"
              >
                <X size={16} />
              </button>
            </div>

            {/* Chart area */}
            <div className="px-4 pb-4" style={{ height: "320px" }}>
              {historyLoading && (
                <div className="w-full h-full flex items-center justify-center text-slate-500 text-sm animate-pulse">
                  Loading historical data…
                </div>
              )}
              {historyError && (
                <div className="w-full h-full flex items-center justify-center text-red-400 text-sm">
                  {historyError}
                </div>
              )}
              {history && !historyLoading && (
                <MacroChart
                  data={history.data}
                  unit={history.unit}
                  fromIndex={0}
                />
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-800 flex items-center justify-between shrink-0">
              <span className="text-xs text-slate-600">
                Source: {selectedIndicator.source} · as of {selectedIndicator.asOf}
              </span>
              {history && (
                <span className="text-xs text-slate-600">
                  {history.data.length} data points (5Y)
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
