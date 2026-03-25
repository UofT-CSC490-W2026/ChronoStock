export interface OHLCBar {
  time: string; // "YYYY-MM-DD"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface NewsEvent {
  id: string;
  time: string; // "YYYY-MM-DD" — maps to chart x-axis
  title: string;
  summary: string;
  sentiment: "positive" | "negative" | "neutral";
  source: string;
  url?: string;
  sentimentReasoning?: string;
}

export interface StockMeta {
  marketCap?: number;
  revenue?: number;
  netIncome?: number;
  eps?: number;
  sharesOutstanding?: number;
  peRatio?: number;
  forwardPE?: number;
  dividendRate?: number;
  dividendYield?: number;
  exDividendDate?: string;
  volume?: number;
  previousClose?: number;
  dayLow?: number;
  dayHigh?: number;
  weekLow52?: number;
  weekHigh52?: number;
  beta?: number;
  analystRating?: string;
  priceTarget?: number;
  earningsDate?: string;
}

export interface StockData {
  ticker: string;
  companyName: string;
  assetType?: "equity" | "index" | "crypto" | "etf" | "unknown";
  bars: OHLCBar[];
  events: NewsEvent[];
  meta?: StockMeta;
}

export interface IndicatorHistory {
  name: string;
  unit: string;
  data: { time: string; value: number }[];
  cachedAt: string;
}

export interface MacroIndicator {
  name: string;
  value: number;
  previousValue?: number;
  change?: number;
  changePct?: number;
  unit: string;
  description: string;
  source: string;
  asOf: string;
}

export interface MacroCategory {
  name: string;
  indicators: MacroIndicator[];
}

export interface MarketSummary {
  categories: MacroCategory[];
  cachedAt: string;
}

export interface KeyDriver {
  title: string;
  explanation: string;
  sentiment: "positive" | "negative" | "neutral";
}

export interface WatchIndicator {
  indicator: string;
  currentSignal: string;
  whyItMatters: string;
}

export interface MarketAnalysis {
  regime: string;
  regimeSentiment: "bullish" | "bearish" | "neutral" | "mixed";
  summary: string;
  narrative: string;
  keyDrivers: KeyDriver[];
  historicalContext: string;
  watchlist: WatchIndicator[];
  generatedAt: string;
}
