import { StockData, OHLCBar, NewsEvent } from "@/types";

// Deterministic pseudo-random number generator (LCG)
function makeRng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = Math.imul(1664525, s) + 1013904223;
    return (s >>> 0) / 0xffffffff;
  };
}

function tradingDays(startDate: string, count: number): string[] {
  const dates: string[] = [];
  const d = new Date(startDate + "T12:00:00Z");
  while (dates.length < count) {
    const day = d.getUTCDay();
    if (day !== 0 && day !== 6) dates.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return dates;
}

function generateBars(
  startDate: string,
  count: number,
  startPrice: number,
  dailyVolatilityPct: number,
  dailyTrendPct: number,
  seed: number
): OHLCBar[] {
  const rand = makeRng(seed);
  const dates = tradingDays(startDate, count);
  const bars: OHLCBar[] = [];
  let price = startPrice;

  for (const time of dates) {
    const changePct = (rand() - 0.48) * dailyVolatilityPct * 2 + dailyTrendPct;
    const open = parseFloat(price.toFixed(2));
    price = Math.max(5, price * (1 + changePct / 100));
    const close = parseFloat(price.toFixed(2));
    const high = parseFloat((Math.max(open, close) * (1 + rand() * 0.008)).toFixed(2));
    const low = parseFloat((Math.min(open, close) * (1 - rand() * 0.008)).toFixed(2));
    const volume = Math.floor((rand() * 60 + 30) * 1e6);
    bars.push({ time, open, high, low, close, volume });
  }
  return bars;
}

// ── AAPL — from 2020-01-02, ~1320 trading days (~5.25 years) ─────────────────
const aaplBars = generateBars("2020-01-02", 1320, 75, 1.6, 0.05, 42);

const aaplEvents: NewsEvent[] = [
  // 2020
  {
    id: "aapl-2020-1",
    time: "2020-01-28",
    title: "iPhone China Factories Close",
    summary: "Apple warns of revenue miss as COVID-19 forces closure of Chinese manufacturing and retail. First major company to issue a pandemic-related guidance cut.",
    sentiment: "negative",
    source: "Apple IR",
  },
  {
    id: "aapl-2020-2",
    time: "2020-03-13",
    title: "All Retail Stores Close Globally",
    summary: "Apple closes all 458 retail stores outside China as COVID-19 becomes a pandemic. Stock recovers quickly as investors bet on services resilience.",
    sentiment: "negative",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2020-3",
    time: "2020-06-22",
    title: "Apple Silicon Announced",
    summary: "Apple announces transition from Intel to its own ARM-based chips for Macs. First Apple Silicon Macs arrive in November. Analysts call it the most important platform shift in a decade.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2020-4",
    time: "2020-07-30",
    title: "Q3 FY2020 Blowout Earnings",
    summary: "Revenue $59.7B, up 11% despite the pandemic. iPhone, Mac, iPad, and Services all beat estimates. Stock hits all-time high.",
    sentiment: "positive",
    source: "Apple IR",
  },
  {
    id: "aapl-2020-5",
    time: "2020-08-31",
    title: "4-for-1 Stock Split",
    summary: "Apple completes a 4-for-1 stock split, making shares more accessible to retail investors. Trading volume surges. Stock briefly crosses $2T market cap.",
    sentiment: "positive",
    source: "Apple IR",
  },
  {
    id: "aapl-2020-6",
    time: "2020-10-13",
    title: "iPhone 12 — First 5G iPhone",
    summary: "Apple launches iPhone 12 lineup with 5G support and OLED displays across all models. Analysts forecast a record upgrade supercycle.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  // 2021
  {
    id: "aapl-2021-1",
    time: "2021-01-27",
    title: "Q1 FY2021 Record Earnings",
    summary: "Revenue $111.4B, first quarter ever to break $100B. iPhone 12 5G cycle drives record results across all geographies. EPS $1.68 vs $1.41 expected.",
    sentiment: "positive",
    source: "Apple IR",
  },
  {
    id: "aapl-2021-2",
    time: "2021-04-26",
    title: "AirTag & M1 iPad Pro Launched",
    summary: "Apple launches AirTag tracking accessory and first M1-powered iPad Pro. Services revenue crosses $16.9B quarterly run rate.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2021-3",
    time: "2021-09-14",
    title: "iPhone 13 & Apple Watch Series 7",
    summary: "Apple unveils iPhone 13 with larger batteries and improved cameras. Analysts note lack of a major design refresh but strong demand from 5G laggards.",
    sentiment: "neutral",
    source: "Apple Newsroom",
  },
  // 2022
  {
    id: "aapl-2022-1",
    time: "2022-01-03",
    title: "Apple Hits $3 Trillion Market Cap",
    summary: "Apple briefly becomes the first company to reach a $3 trillion market capitalisation intraday. Driven by strong iPhone 13 demand and Services growth.",
    sentiment: "positive",
    source: "Bloomberg",
  },
  {
    id: "aapl-2022-2",
    time: "2022-05-26",
    title: "Stock Enters Bear Market",
    summary: "Apple falls over 20% from its January peak amid broad tech selloff driven by rising interest rates and recession fears. Worst H1 performance since 2008.",
    sentiment: "negative",
    source: "Reuters",
  },
  {
    id: "aapl-2022-3",
    time: "2022-09-07",
    title: "iPhone 14 — Dynamic Island",
    summary: "Apple launches iPhone 14 Pro with Dynamic Island notch replacement and always-on display. Standard iPhone 14 is largely unchanged — analysts flag widening pro/standard gap.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2022-4",
    time: "2022-11-07",
    title: "Zhengzhou Factory Unrest",
    summary: "Worker protests at Foxconn's Zhengzhou iPhone factory cut Pro model production by up to 30%. Analysts cut Q4 iPhone estimates by 6–8M units.",
    sentiment: "negative",
    source: "Wall Street Journal",
  },
  // 2023
  {
    id: "aapl-2023-1",
    time: "2023-02-02",
    title: "Q1 FY2023 Miss on iPhone",
    summary: "Revenue $117.2B vs $121.1B expected. iPhone miss attributed to Zhengzhou supply disruption. Services and Mac beat. Gross margin guidance higher than expected.",
    sentiment: "negative",
    source: "Apple IR",
  },
  {
    id: "aapl-2023-2",
    time: "2023-06-05",
    title: "Vision Pro Unveiled at WWDC",
    summary: "Apple announces Vision Pro spatial computing headset at $3,499 starting price, launching early 2024. Seen as a long-term platform bet; near-term financial impact limited.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2023-3",
    time: "2023-09-12",
    title: "iPhone 15 — USB-C & Titanium",
    summary: "Apple migrates iPhone to USB-C under EU mandate. iPhone 15 Pro features titanium frame and A17 Pro chip. Analysts debate whether China slowdown limits upside.",
    sentiment: "neutral",
    source: "Apple Newsroom",
  },
  // 2024
  {
    id: "aapl-2024-1",
    time: "2024-01-19",
    title: "China iPhone Sales Slowdown",
    summary: "Reports of weaker iPhone 15 demand in China amid Huawei competition and nationalist sentiment. Several sell-side analysts cut Q1 unit estimates by 3–5%.",
    sentiment: "negative",
    source: "Wall Street Journal",
  },
  {
    id: "aapl-2024-2",
    time: "2024-02-01",
    title: "Q1 FY2024 Earnings Beat",
    summary: "Revenue $119.6B vs $117.9B expected. EPS $2.18 vs $2.10. Services hits record $23.1B. Vision Pro launches same week.",
    sentiment: "positive",
    source: "Apple IR",
  },
  {
    id: "aapl-2024-3",
    time: "2024-03-21",
    title: "DOJ Antitrust Lawsuit",
    summary: "US Department of Justice files a landmark antitrust suit against Apple alleging illegal monopolisation of the smartphone market. Stock drops ~4% intraday.",
    sentiment: "negative",
    source: "Reuters",
  },
  {
    id: "aapl-2024-4",
    time: "2024-05-02",
    title: "Q2 FY2024 + $110B Buyback",
    summary: "Q2 revenue $90.75B beats estimates. Apple announces the largest buyback in its history at $110B. Stock surges 6% after-hours.",
    sentiment: "positive",
    source: "Apple IR",
  },
  {
    id: "aapl-2024-5",
    time: "2024-06-10",
    title: "Apple Intelligence at WWDC",
    summary: "Apple announces on-device AI features across iOS 18, iPadOS 18, and macOS Sequoia, with an OpenAI/Siri integration. Strong analyst upgrades follow.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2024-6",
    time: "2024-09-09",
    title: "iPhone 16 Launched",
    summary: "Apple unveils iPhone 16 lineup with Camera Control and Apple Intelligence support. Pre-order volumes up ~10% vs iPhone 15 cycle.",
    sentiment: "positive",
    source: "Apple Newsroom",
  },
  {
    id: "aapl-2024-7",
    time: "2024-10-31",
    title: "Q4 FY2024 Record Full Year",
    summary: "Full-year revenue $391B, a new record. Q4 EPS $1.64 vs $1.60 expected. Apple Intelligence rollout sustains premium valuation narrative.",
    sentiment: "positive",
    source: "Apple IR",
  },
];

// ── TSLA — from 2020-01-02, ~1320 trading days ────────────────────────────────
const tslaBars = generateBars("2020-01-02", 1320, 28, 3.2, 0.07, 99);

const tslaEvents: NewsEvent[] = [
  // 2020
  {
    id: "tsla-2020-1",
    time: "2020-02-03",
    title: "Stock Doubles in 6 Weeks",
    summary: "Tesla shares surge past $800 (pre-split), doubling from $400 in early January driven by strong Q4 deliveries, Shanghai factory ramp, and retail investor momentum.",
    sentiment: "positive",
    source: "Bloomberg",
  },
  {
    id: "tsla-2020-2",
    time: "2020-03-18",
    title: "Fremont Factory Shutdown",
    summary: "Tesla suspends Fremont production amid COVID-19 shelter-in-place orders, defying Alameda County guidance initially. Production resumes May 11.",
    sentiment: "negative",
    source: "Reuters",
  },
  {
    id: "tsla-2020-3",
    time: "2020-07-01",
    title: "Q2 Deliveries Beat — Profitability Streak",
    summary: "Tesla delivers 90,650 vehicles in Q2, beating estimates of 72,000 despite the pandemic. Marks the beginning of four consecutive profitable quarters, qualifying for S&P 500 inclusion.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2020-4",
    time: "2020-08-11",
    title: "5-for-1 Stock Split",
    summary: "Tesla announces a 5-for-1 stock split, effective August 31. Retail investor demand surges. Stock nearly triples from split announcement to year-end.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2020-5",
    time: "2020-11-16",
    title: "Added to S&P 500 Index",
    summary: "S&P Dow Jones Indices confirms Tesla will join the S&P 500 on December 21 as one of the largest additions ever. Index funds must buy ~$80B of stock.",
    sentiment: "positive",
    source: "S&P Global",
  },
  // 2021
  {
    id: "tsla-2021-1",
    time: "2021-01-26",
    title: "Q4 2020 Earnings — First Full Profitable Year",
    summary: "Tesla posts its first full-year GAAP profit. Q4 EPS $0.80 vs $1.03 expected but revenue $10.7B beats. Musk confirms Cybertruck, Semi, and Roadster on track.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2021-2",
    time: "2021-02-08",
    title: "Tesla Buys $1.5B in Bitcoin",
    summary: "Tesla discloses a $1.5B Bitcoin purchase and plans to accept it as payment. Bitcoin surges; Tesla adds paper gains but faces criticism over ESG inconsistency.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2021-3",
    time: "2021-05-12",
    title: "Tesla Drops Bitcoin Payments",
    summary: "Elon Musk announces Tesla will no longer accept Bitcoin citing environmental concerns. Crypto markets crash; Tesla stock falls on credibility concerns.",
    sentiment: "negative",
    source: "Twitter/X",
  },
  {
    id: "tsla-2021-4",
    time: "2021-10-25",
    title: "Hertz Orders 100,000 Teslas",
    summary: "Hertz announces an order of 100,000 Model 3s — the largest EV fleet purchase in history. Tesla briefly crosses $1 trillion market cap.",
    sentiment: "positive",
    source: "Bloomberg",
  },
  // 2022
  {
    id: "tsla-2022-1",
    time: "2022-04-07",
    title: "Musk Buys 9% Twitter Stake",
    summary: "Musk discloses a 9.2% passive stake in Twitter, becoming its largest shareholder. Tesla investors worry about distraction; stock drops ~5%.",
    sentiment: "negative",
    source: "SEC Filing",
  },
  {
    id: "tsla-2022-2",
    time: "2022-08-05",
    title: "3-for-1 Stock Split",
    summary: "Tesla completes a 3-for-1 stock split. Comes amid a partial stock recovery from the H1 selloff.",
    sentiment: "neutral",
    source: "Tesla IR",
  },
  {
    id: "tsla-2022-3",
    time: "2022-10-27",
    title: "Musk Closes Twitter Deal",
    summary: "Musk completes $44B Twitter acquisition. Tesla stock falls sharply as investors fear distraction and forced stock sales to fund the deal.",
    sentiment: "negative",
    source: "Reuters",
  },
  {
    id: "tsla-2022-4",
    time: "2022-12-22",
    title: "Musk Sells $3.6B More Tesla Shares",
    summary: "Musk sells another $3.6B of Tesla stock — the fifth tranche of sales in 2022 totalling ~$23B. Stock hits a two-year low.",
    sentiment: "negative",
    source: "SEC Filing",
  },
  // 2023
  {
    id: "tsla-2023-1",
    time: "2023-01-13",
    title: "Global Price Cuts Up to 20%",
    summary: "Tesla slashes prices by up to 20% globally to stimulate demand and preserve market share against Chinese EV rivals. Margin concerns dominate analyst notes.",
    sentiment: "negative",
    source: "Tesla",
  },
  {
    id: "tsla-2023-2",
    time: "2023-04-19",
    title: "Q1 2023 Margin Miss",
    summary: "Gross margin falls to 19.3% from 29.1% a year earlier due to price cuts. Revenue $23.3B beats but profitability narrative damaged. Stock drops ~9%.",
    sentiment: "negative",
    source: "Tesla IR",
  },
  {
    id: "tsla-2023-3",
    time: "2023-11-01",
    title: "Cybertruck Delivery Event",
    summary: "Tesla delivers first Cybertrucks at a Texas event. Starting price $60,990 — higher than initially promised. Musk calls it 'a product unlike anything else'.",
    sentiment: "positive",
    source: "Tesla",
  },
  // 2024
  {
    id: "tsla-2024-1",
    time: "2024-01-26",
    title: "Q4 2023 Earnings — Margin Warning",
    summary: "EPS $0.71 vs $0.74 expected. Gross margin 17.6%. Musk warns 2024 growth 'notably lower'. Stock crashes ~12%.",
    sentiment: "negative",
    source: "Tesla IR",
  },
  {
    id: "tsla-2024-2",
    time: "2024-04-23",
    title: "Q1 2024 Miss + 10% Layoffs",
    summary: "Revenue $21.3B vs $22.3B expected. Tesla announces 10% global workforce reduction. Musk pivots messaging to autonomy and Robotaxi.",
    sentiment: "negative",
    source: "Tesla IR",
  },
  {
    id: "tsla-2024-3",
    time: "2024-07-23",
    title: "Q2 2024 Earnings Beat",
    summary: "Revenue $25.2B vs $24.8B expected. Deliveries up 4.8% QoQ. Margin recovery to 18%. Robotaxi event confirmed for October. Stock surges 10%.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2024-4",
    time: "2024-10-23",
    title: "Q3 2024 Blowout Earnings",
    summary: "EPS $0.72 vs $0.58 expected. Record deliveries 462,890. Gross margin 19.8%. Full-year guidance raised. Stock +22% next day.",
    sentiment: "positive",
    source: "Tesla IR",
  },
  {
    id: "tsla-2024-5",
    time: "2024-11-06",
    title: "Post-Election Rally",
    summary: "Tesla surges 15% as Trump wins. Musk's ties to the incoming administration raise expectations of FSD regulatory tailwinds.",
    sentiment: "positive",
    source: "Bloomberg",
  },
];

export const mockStockData: Record<string, StockData> = {
  AAPL: { ticker: "AAPL", companyName: "Apple Inc.", bars: aaplBars, events: aaplEvents },
  TSLA: { ticker: "TSLA", companyName: "Tesla, Inc.", bars: tslaBars, events: tslaEvents },
};
