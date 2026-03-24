import { StockMeta } from "@/types";

interface Props {
  meta: StockMeta;
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fNum(n?: number): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

function fPrice(n?: number): string {
  if (n == null) return "—";
  return `$${n.toFixed(2)}`;
}

function fPlain(n?: number, decimals = 2): string {
  if (n == null) return "—";
  return n.toFixed(decimals);
}

function fPct(n?: number): string {
  if (n == null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function fVol(n?: number): string {
  if (n == null) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return `${n}`;
}

const ANALYST_COLOR: Record<string, string> = {
  "Strong Buy": "text-green-400",
  "Buy": "text-green-400",
  "Hold": "text-amber-400",
  "Underperform": "text-red-400",
  "Sell": "text-red-400",
};

// ── Beginner tooltips ─────────────────────────────────────────────────────────

const TOOLTIPS: Record<string, string> = {
  "Market Cap":    "Total value of all shares outstanding. Larger = bigger company.",
  "Revenue (ttm)": "Total sales over the last 12 months (trailing twelve months).",
  "EPS":           "Earnings Per Share — company profit divided by number of shares. Higher = more profit per share.",
  "P/E":           "Price-to-Earnings — how much you pay per $1 of profit. Lower can mean cheaper relative to earnings.",
  "Fwd P/E":       "Like P/E but uses next year's expected earnings instead of last year's actual earnings.",
  "Beta":          "How much the stock moves vs. the broader market. >1 = more volatile, <1 = more stable.",
  "Volume":        "Number of shares traded today. Higher volume = stronger interest in the stock.",
  "Prev Close":    "Yesterday's closing price — a reference for measuring today's move.",
  "Day's Range":   "The lowest and highest price the stock reached during today's trading session.",
  "52W Range":     "The lowest and highest price over the past 52 weeks (one year).",
  "Dividend":      "Cash paid to shareholders per share each year, plus the yield as a % of the current stock price.",
  "Earnings Date": "The date when the company will next report its quarterly financial results.",
  "Analysts":      "Consensus recommendation from Wall Street analysts covering this stock.",
  "Price Target":  "The average analyst estimate for where the stock price will be in 12 months.",
};

// ── Stat cell ─────────────────────────────────────────────────────────────────

function Stat({
  label,
  value,
  highlight,
  tooltip,
}: {
  label: string;
  value: string;
  highlight?: string;
  tooltip?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="relative group flex items-center gap-0.5">
        <span className="text-[10px] uppercase tracking-wider text-slate-500 whitespace-nowrap">
          {label}
        </span>
        {tooltip && (
          <>
            <span className="text-[9px] text-slate-600 cursor-default select-none">ⓘ</span>
            <div className="pointer-events-none absolute bottom-full left-0 mb-1.5 w-48 z-50 rounded-lg border border-slate-700 bg-slate-900 shadow-xl px-2.5 py-2 text-[11px] leading-snug text-slate-300 font-normal normal-case tracking-normal opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              {tooltip}
            </div>
          </>
        )}
      </div>
      <span className={`text-sm font-medium whitespace-nowrap ${highlight ?? "text-slate-200"}`}>
        {value}
      </span>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function StockMetaBar({ meta }: Props) {
  const range52 =
    meta.weekLow52 != null && meta.weekHigh52 != null
      ? `${fPrice(meta.weekLow52)} – ${fPrice(meta.weekHigh52)}`
      : "—";

  const dayRange =
    meta.dayLow != null && meta.dayHigh != null
      ? `${fPrice(meta.dayLow)} – ${fPrice(meta.dayHigh)}`
      : "—";

  const dividend =
    meta.dividendRate != null
      ? `${fPrice(meta.dividendRate)} (${fPct(meta.dividendYield)})`
      : "—";

  return (
    <div className="grid grid-cols-7 gap-x-2 gap-y-3 px-1 py-3 border-t border-b border-slate-800 divide-x divide-slate-800 [&>*]:pl-3 [&>*:nth-child(7n+1)]:pl-0 [&>*:nth-child(7n+1)]:border-l-0">
      <Stat label="Market Cap"    value={fNum(meta.marketCap)}       tooltip={TOOLTIPS["Market Cap"]} />
      <Stat label="Revenue (ttm)" value={fNum(meta.revenue)}         tooltip={TOOLTIPS["Revenue (ttm)"]} />
      <Stat label="EPS"           value={fPrice(meta.eps)}           tooltip={TOOLTIPS["EPS"]} />
      <Stat label="P/E"           value={fPlain(meta.peRatio)}       tooltip={TOOLTIPS["P/E"]} />
      <Stat label="Fwd P/E"       value={fPlain(meta.forwardPE)}     tooltip={TOOLTIPS["Fwd P/E"]} />
      <Stat label="Beta"          value={fPlain(meta.beta)}          tooltip={TOOLTIPS["Beta"]} />
      <Stat label="Volume"        value={fVol(meta.volume)}          tooltip={TOOLTIPS["Volume"]} />
      <Stat label="Prev Close"    value={fPrice(meta.previousClose)} tooltip={TOOLTIPS["Prev Close"]} />
      <Stat label="Day's Range"   value={dayRange}                   tooltip={TOOLTIPS["Day's Range"]} />
      <Stat label="52W Range"     value={range52}                    tooltip={TOOLTIPS["52W Range"]} />
      <Stat label="Dividend"      value={dividend}                   tooltip={TOOLTIPS["Dividend"]} />
      {meta.earningsDate && (
        <Stat label="Earnings Date" value={meta.earningsDate} tooltip={TOOLTIPS["Earnings Date"]} />
      )}
      {meta.analystRating && (
        <Stat
          label="Analysts"
          value={meta.analystRating}
          highlight={ANALYST_COLOR[meta.analystRating] ?? "text-slate-200"}
          tooltip={TOOLTIPS["Analysts"]}
        />
      )}
      {meta.priceTarget != null && (
        <Stat label="Price Target" value={fPrice(meta.priceTarget)} tooltip={TOOLTIPS["Price Target"]} />
      )}
    </div>
  );
}
